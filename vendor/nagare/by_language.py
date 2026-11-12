"""Rewrite a nagare snapshot so every current is a language, not a repository.

python -m nagare.by_language snapshot.json -o snapshot-language.json

Each repository is assigned to its dominant language (the one with the most
bytes) and the languages are summed, keeping the per-day commit counts the
renderer needs. Repositories with no language at all -- READMEs, .github,
docs-only repos -- are skipped and their work falls into the residual
"other activity" current, as does everything GitHub counts but cannot
attribute (pull requests, issues, reviews, private work).

Vendored from monex00/nagare@ee1fcb7 (MIT); this file is not upstream.
"""

import argparse
import json
import os
import sys
import urllib.request
import zlib

REST = "https://api.github.com/repositories/{}/languages"


def languages(repo_id, token):
    req = urllib.request.Request(
        REST.format(repo_id),
        headers={"Authorization": f"bearer {token}", "Accept": "application/vnd.github+json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except Exception as e:                      # 404 = no language data
        print(f"  repo {repo_id}: {e}", file=sys.stderr)
        return {}


def transform(snap, token):
    cache, groups, skipped = {}, {}, 0
    for r in snap["repos"]:
        if r["id"] not in cache:
            langs = languages(r["id"], token)
            cache[r["id"]] = max(langs, key=langs.get) if langs else None
        lang = cache[r["id"]]
        if not lang:
            skipped += 1
            continue
        g = groups.setdefault(lang, {"id": zlib.crc32(lang.encode()), "name": lang,
                                     "contributions": 0, "last_contribution": None, "days": {}})
        g["contributions"] += r["contributions"]
        for d in r.get("days") or []:
            g["days"][d["date"]] = g["days"].get(d["date"], 0) + d["count"]
        last = r.get("last_contribution")
        if last and (not g["last_contribution"] or last > g["last_contribution"]):
            g["last_contribution"] = last
    repos = []
    for g in groups.values():
        days = [{"date": d, "count": c} for d, c in sorted(g["days"].items())]
        repos.append({"id": g["id"], "name": g["name"], "contributions": g["contributions"],
                      "last_contribution": days[-1]["date"] if days else None, "days": days})
    repos.sort(key=lambda r: -r["contributions"])
    out = dict(snap)
    out["repos"] = repos
    print(f"{skipped} repos without language data, skipped")
    print("languages: " + ", ".join(f"{r['name']} {r['contributions']}" for r in repos))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("snapshot")
    ap.add_argument("-o", "--output", default="snapshot-language.json")
    a = ap.parse_args()
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        raise SystemExit("set GITHUB_TOKEN")
    with open(a.snapshot) as f:
        snap = json.load(f)
    out = transform(snap, token)
    with open(a.output, "w") as f:
        json.dump(out, f, indent=1)
    print(f"{a.output}: {len(out['repos'])} languages")


if __name__ == "__main__":
    main()
