"""Fix and confirm stops without hand-editing JSON.

    python scripts/edit_stops.py list
    python scripts/edit_stops.py set s4 visible_text "Director Cottage"     (correct a sign to what is really printed)
    python scripts/edit_stops.py set s4 feature "a white house behind a low stone wall"
    python scripts/edit_stops.py set s4 minutes 2.5                          (walking time from the previous stop)
    python scripts/edit_stops.py confirm s1 s2 s4                            (you checked these against the real signs)
    python scripts/edit_stops.py confirm --all
    python scripts/edit_stops.py unsafe s6                                   (mark a hazard; "safe s6" undoes it)

Fastest way to fix everything at once:
    python scripts/edit_stops.py export                  (writes stops_edit.txt: one line per stop)
    ... edit that file in VS Code ...
    python scripts/edit_stops.py apply stops_edit.txt    (applies it and confirms the stops that look good)
"""
import argparse, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from papertrail.scout import feature_problems

FIELDS = {"visible_text": "visible_text", "feature": "feature", "minutes": "minutes_from_prev"}


def load(path):
    data = json.load(open(path, encoding="utf-8"))
    return data["stops"] if isinstance(data, dict) else data


def find(stops, sid):
    for s in stops:
        if s["id"] == sid:
            return s
    sys.exit(f"No stop called {sid!r}. Known: {', '.join(s['id'] for s in stops)}")


HEADER = """# One line per stop:   id | sign exactly as printed on the sign | ONE visible, fixed detail [| unsafe]
# - the detail must be something that is still there tomorrow: colour, shape, material, steps, a statue, a flag, a tree
# - do not use words from the sign, and do not describe people or what they do (they move)
# - write DELETE instead of the sign to remove a stop;  add | unsafe at the end of a line for a hazard
# - lines starting with # are ignored. Save this file, then run:  python scripts/edit_stops.py apply stops_edit.txt
"""


def export(stops, path):
    lines = [HEADER]
    for s in stops:
        for p in feature_problems(s["visible_text"], s.get("feature", "")):
            lines.append(f"# {s['id']}: {p}")
        if not s.get("safe", True):
            lines.append(f"# {s['id']}: marked UNSAFE, so no hunt can pass it. If it is a normal walkway, delete '| unsafe' on its line.")
        lines.append(f"{s['id']} | {s['visible_text']} | {s.get('feature', '')}" + ("" if s.get("safe", True) else " | unsafe"))
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def apply_edits(stops, text, force=False):
    """Apply an edited export. Returns (new stops list, messages)."""
    msgs, by_id, delete = [], {s["id"]: s for s in stops}, set()
    for n, line in enumerate(text.splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 3 or parts[0] not in by_id:
            msgs.append(f"line {n}: skipped (need 'id | sign | detail', known id): {line[:60]}")
            continue
        s, sign, feat = by_id[parts[0]], parts[1], parts[2]
        if sign.upper() == "DELETE":
            delete.add(s["id"])
            continue
        unsafe = len(parts) > 3 and parts[3].lower() == "unsafe"
        s["visible_text"], s["feature"], s["safe"] = sign, feat, not unsafe
        problems = feature_problems(sign, feat)
        s["flags"] = problems
        s["confirmed"] = bool(sign and feat) and not unsafe and (force or not problems)
        for p in problems:
            msgs.append(f"{s['id']} ({sign}): {p}" + ("" if force else "  -> NOT confirmed"))
        if not feat and not unsafe:
            msgs.append(f"{s['id']} ({sign}): no detail, so NOT confirmed")
    out, carry = [], 0.0
    for s in stops:
        carry += float(s.get("minutes_from_prev", 0) or 0)
        if s["id"] in delete:
            continue
        s["minutes_from_prev"] = carry if out else 0.0
        out.append(s)
        carry = 0.0
    seen = {}
    for s in out:
        if s.get("confirmed") and s["feature"].strip().lower() in seen:
            msgs.append(f"{s['id']} has the same detail as {seen[s['feature'].strip().lower()]}: clues cannot tell them apart")
        seen.setdefault(s["feature"].strip().lower(), s["id"])
    return out, msgs


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default="stops.json")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    p = sub.add_parser("export"); p.add_argument("path", nargs="?", default="stops_edit.txt")
    p = sub.add_parser("apply"); p.add_argument("path", nargs="?", default="stops_edit.txt")
    p.add_argument("--force", action="store_true", help="confirm even stops whose detail looks weak")
    p = sub.add_parser("set"); p.add_argument("id"); p.add_argument("field", choices=FIELDS); p.add_argument("value")
    p = sub.add_parser("confirm"); p.add_argument("ids", nargs="*"); p.add_argument("--all", action="store_true")
    for name in ("unsafe", "safe"):
        p = sub.add_parser(name); p.add_argument("id")
    a = ap.parse_args(argv)

    stops = load(a.file)
    if a.cmd == "export":
        export(stops, a.path)
        print(f"Wrote {a.path}. Edit it, then: python scripts/edit_stops.py apply {a.path}")
        return
    if a.cmd == "apply":
        stops, msgs = apply_edits(stops, Path(a.path).read_text(encoding="utf-8"), a.force)
        Path(a.file).write_text(json.dumps(stops, indent=2, ensure_ascii=False), encoding="utf-8")
        for m in msgs:
            print("!", m)
    elif a.cmd == "set":
        s = find(stops, a.id)
        key = FIELDS[a.field]
        s[key] = float(a.value) if key == "minutes_from_prev" else a.value.strip()
        s["confirmed"] = False                      # any edit needs a fresh confirmation
    elif a.cmd == "confirm":
        targets = stops if a.all else [find(stops, i) for i in a.ids]
        if not targets:
            sys.exit("Give stop ids, or --all.")
        for s in targets:
            if not s.get("safe", True):
                print(f"{s['id']}: marked unsafe, stays unconfirmed (unsafe stops are never used)")
            elif not str(s.get("feature", "")).strip():
                print(f"{s['id']}: has no description, add one first (set {s['id']} feature \"...\")")
            else:
                s["confirmed"] = True
    elif a.cmd in ("unsafe", "safe"):
        s = find(stops, a.id)
        s["safe"] = a.cmd == "safe"
        s["confirmed"] = False
    if a.cmd in ("set", "confirm", "unsafe", "safe"):
        Path(a.file).write_text(json.dumps(stops, indent=2, ensure_ascii=False), encoding="utf-8")
    for s in stops:
        mark = "CONFIRMED" if s.get("confirmed") else "unconfirmed"
        extra = "" if s.get("safe", True) else "  [UNSAFE]"
        print(f"{s['id']:>4}  {mark:11}  {s['visible_text']!r:34} {s.get('feature') or '(no description)'}{extra}")
    ok = sum(1 for s in stops if s.get("confirmed") and s.get("safe", True) and s.get("feature"))
    print(f"\n{ok} of {len(stops)} stops will be used.")


if __name__ == "__main__":
    main()
