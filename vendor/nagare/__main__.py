"""python -m nagare snapshot.json -o nagare.svg"""

import argparse
import json

from .render import render


def main():
    ap = argparse.ArgumentParser(prog="nagare", description="Draw a year of GitHub activity as an ink koi pond.")
    ap.add_argument("snapshot")
    ap.add_argument("-o", "--output", default="nagare.svg")
    ap.add_argument("--theme", choices=["auto", "paper", "night"], default="auto",
                    help="auto follows the reader's light/dark setting")
    a = ap.parse_args()
    with open(a.snapshot) as f:
        svg = render(json.load(f), a.theme)
    with open(a.output, "w") as f:
        f.write(svg)
    print(f"{a.output}: {len(svg) / 1024:.0f} KB")


if __name__ == "__main__":
    main()
