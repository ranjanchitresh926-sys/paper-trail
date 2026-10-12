"""After the hunt: compare what each team wrote with the key.

    python scripts/debrief.py 1=SUITS 2=MIDST 3=SIEGE        (team=word they wrote; reads hunt/hunt.json)

Mismatched letters point at stops where a sign may have changed since the scouting walk. Writes hunt/debrief.md."""
import argparse, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from papertrail.hunt import debrief


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("answers", nargs="+", help="team=word, e.g. 1=SUITS")
    ap.add_argument("--hunt", default="hunt/hunt.json")
    a = ap.parse_args()
    hunt = json.load(open(a.hunt, encoding="utf-8"))
    answers = {}
    for item in a.answers:
        team, _, word = item.partition("=")
        if not team.strip().isdigit():
            sys.exit(f"Use team=word, for example 1=SUITS (got {item!r})")
        answers[int(team)] = word
    text = debrief(hunt, answers)
    out = Path(a.hunt).with_name("debrief.md")
    out.write_text(text, encoding="utf-8")
    print(text)
    print(f"Saved to {out}")


if __name__ == "__main__":
    main()
