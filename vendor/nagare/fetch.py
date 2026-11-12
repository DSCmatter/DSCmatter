"""Fetch the activity snapshot nagare draws from, via the GitHub GraphQL API.

GITHUB_TOKEN=... python -m nagare.fetch <login> -o snapshot.json

With the workflow's built-in token only public activity is visible. A personal
token with read:user also counts private contributions; private repository
names are never written to the snapshot.

Per-repository commits come as one node per active day, at most 100 per
request. The year is fetched in windows shorter than 100 days, so no
repository can overflow a page and every active day is kept.
"""

import argparse
import datetime as dt
import json
import os
import urllib.request

WINDOW_DAYS = 73          # 5 windows per year, each < 100 days

CALENDAR_QUERY = """
query($login: String!) {
  user(login: $login) {
    login
    repositories(first: 100, ownerAffiliations: OWNER, isFork: false, privacy: PUBLIC,
                 orderBy: {field: STARGAZERS, direction: DESC}) {
      nodes { stargazerCount }
    }
    contributionsCollection {
      contributionCalendar { weeks { contributionDays { date contributionCount } } }
      restrictedContributionsCount
      totalCommitContributions
      totalIssueContributions
      totalPullRequestContributions
      totalPullRequestReviewContributions
      totalRepositoryContributions
    }
  }
  viewer {
    login
    repositories(privacy: PRIVATE, ownerAffiliations: [OWNER, COLLABORATOR, ORGANIZATION_MEMBER]) { totalCount }
  }
}
"""

COMMITS_QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      commitContributionsByRepository(maxRepositories: 100) {
        repository { databaseId name isPrivate }
        contributions(first: 100, orderBy: {field: OCCURRED_AT, direction: DESC}) {
          nodes { occurredAt commitCount }
        }
      }
    }
  }
}
"""


def graphql(token: str, query: str, variables: dict) -> dict:
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        body = json.load(r)
    if body.get("errors"):
        raise SystemExit(f"GitHub API error: {body['errors']}")
    return body["data"]


def windows(end: dt.datetime, days=365, size=WINDOW_DAYS):
    start = end - dt.timedelta(days=days)
    out = []
    while start < end:
        stop = min(start + dt.timedelta(days=size), end)
        out.append((start, stop))
        start = stop
    return out


def iso(t: dt.datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def merge_commits(window_results) -> list:
    """Combine per-window commitContributionsByRepository lists into one per repo."""
    repos = {}
    for result in window_results:
        for item in result["contributionsCollection"]["commitContributionsByRepository"]:
            repo = item["repository"]
            r = repos.setdefault(repo["databaseId"], {
                "id": repo["databaseId"],
                "name": None if repo["isPrivate"] else repo["name"],
                "days": {},
            })
            for n in item["contributions"]["nodes"]:
                day = n["occurredAt"][:10]
                r["days"][day] = r["days"].get(day, 0) + n["commitCount"]
    out = []
    for r in repos.values():
        days = [{"date": d, "count": c} for d, c in sorted(r["days"].items())]
        out.append({
            "id": r["id"],
            "name": r["name"],
            "contributions": sum(d["count"] for d in days),
            "last_contribution": days[-1]["date"] if days else None,
            "days": days,
        })
    out.sort(key=lambda r: -r["contributions"])
    return out


def snapshot(calendar_user: dict, window_results: list) -> dict:
    cc = calendar_user["contributionsCollection"]
    days = [{"date": d["date"], "count": d["contributionCount"]}
            for w in cc["contributionCalendar"]["weeks"] for d in w["contributionDays"]]
    today = dt.date.today().isoformat()
    days = [d for d in days if d["date"] <= today]
    return {
        "login": calendar_user["login"],
        "observed_on": days[-1]["date"] if days else today,
        "days": days,
        "repos": merge_commits(window_results),
        "stars": sum(n["stargazerCount"] for n in calendar_user["repositories"]["nodes"]),
    }


def fetch(token: str, login: str) -> dict:
    data = graphql(token, CALENDAR_QUERY, {"login": login})
    calendar = data["user"]
    cc = calendar["contributionsCollection"]
    v = data.get("viewer") or {}
    viewer = v.get("login", "?")
    kind = ("classic" if token.startswith("ghp_") else "fine-grained" if token.startswith("github_pat_")
            else "actions" if token.startswith("ghs_") else "other")
    private_repos = (v.get("repositories") or {}).get("totalCount", 0)
    print(f"token: {kind}, {private_repos} private repositories visible")
    print(f"reading as {viewer}: {cc['totalCommitContributions']} commits, "
          f"{cc['totalPullRequestContributions']} PRs, {cc['totalIssueContributions']} issues, "
          f"{cc['totalPullRequestReviewContributions']} reviews, {cc['totalRepositoryContributions']} repos created, "
          f"{cc['restrictedContributionsCount']} private contributions hidden from this token")
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    results = [graphql(token, COMMITS_QUERY, {"login": login, "from": iso(a), "to": iso(b)})["user"]
               for a, b in windows(now)]
    snap = snapshot(calendar, results)
    snap["private_contributions"] = cc["restrictedContributionsCount"]
    return snap


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("login")
    ap.add_argument("-o", "--output", default="snapshot.json")
    a = ap.parse_args()
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        raise SystemExit("set GITHUB_TOKEN")
    snap = fetch(token, a.login)
    with open(a.output, "w") as f:
        json.dump(snap, f, indent=1)
    print(f"{a.output}: {len(snap['repos'])} repos, {sum(d['count'] for d in snap['days'])} contributions")


if __name__ == "__main__":
    main()
