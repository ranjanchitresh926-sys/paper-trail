"""Fix a clue or a team's start by hand, then rewrite the sheets. No model needed.

    python scripts/edit_hunt.py list
    python scripts/edit_hunt.py clue 2 5 "A tall tower with a clock face."     (team 2, clue 5)
    python scripts/edit_hunt.py start 1 "Old Gate" --minutes 0.9                                (where team 1 begins)

Edited clues are checked for leaked signs and unsafe advice. Read key.html afterwards."""
import argparse, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from papertrail.hunt import set_clue, set_start, write_files


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hunt", default="hunt/hunt.json")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    p = sub.add_parser("clue"); p.add_argument("team", type=int); p.add_argument("n", type=int); p.add_argument("text")
    p = sub.add_parser("start"); p.add_argument("team", type=int); p.add_argument("sign"); p.add_argument("--minutes", type=float)
    a = ap.parse_args()
    path = Path(a.hunt)
    hunt = json.load(open(path, encoding="utf-8"))
    try:
        if a.cmd == "clue":
            for pr in set_clue(hunt, a.team, a.n, a.text):
                print("! check:", pr)
        elif a.cmd == "start":
            set_start(hunt, a.team, a.sign, a.minutes)
    except ValueError as e:
        sys.exit(str(e))
    if a.cmd != "list":
        meta = hunt.get("meta", {})
        write_files(hunt, str(path.parent), meta.get("title", "Paper Trail"), meta.get("start", ""), meta.get("note", ""))
        print("Saved and rewrote the sheets.")
    for t in hunt["teams"]:
        print(f"\nTeam {t['team']}: {t['word']}  start at: {t.get('start_sign') or '(gathering point)'}  ~{t.get('total_minutes', t['minutes'])} min")
        for s in t["steps"]:
            print(f"  {s['n']}. [{s['sign']}] {s['clue']}" + ("  (edited)" if s.get("edited") else ""))


if __name__ == "__main__":
    main()
