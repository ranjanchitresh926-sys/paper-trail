"""Rewrite the team sheets and key from hunt/hunt.json without running any model (use after editing the JSON or upgrading).

    python scripts/render_hunt.py"""
import argparse, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from papertrail.hunt import write_files


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hunt", default="hunt/hunt.json")
    ap.add_argument("--title", default=None)
    ap.add_argument("--start", default=None)
    ap.add_argument("--note", default=None)
    a = ap.parse_args()
    hunt = json.load(open(a.hunt, encoding="utf-8"))
    meta = hunt.get("meta", {})
    write_files(hunt, str(Path(a.hunt).parent), a.title or meta.get("title", "Paper Trail"),
                a.start if a.start is not None else meta.get("start", ""),
                a.note if a.note is not None else meta.get("note", ""))
    print(f"Rewrote {len(hunt['teams'])} team sheets and key.html in {Path(a.hunt).parent}")


if __name__ == "__main__":
    main()
