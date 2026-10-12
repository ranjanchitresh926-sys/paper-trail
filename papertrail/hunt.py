"""Hunt builder: checked stops -> one word, one route and a set of verified clues per team, plus printable sheets.

Code decides everything that can be checked (the word is spelled by the stops' letters in walking order, no hunt
crosses a hazard, no clue quotes the sign). The model only writes clue wording, and a separate solver pass must pick
the right stop from all stops before a clue is accepted (see cluelab.py).
"""
from __future__ import annotations

import html
import json
import random
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from .cluelab import make_clue
from .guard import validate_clue
from .composer import describe_rule, enumerate_puzzles, letters_only, route_minutes
from .models import Puzzle, Step, Stop


def route_segments(rows: Sequence[Dict]) -> List[List[Stop]]:
    """Split the scouted route into hazard-free segments.

    A stop marked unsafe is a barrier: teams walk from stop to stop, so no puzzle may span it. Stops that are
    unconfirmed, have no description or have too few letters are skipped, but the walking time to them is carried
    over to the next kept stop so route times stay accurate.
    """
    segments: List[List[Stop]] = []
    cur: List[Stop] = []
    carry = 0.0
    for d in rows:
        if not d.get("safe", True):
            if cur:
                segments.append(cur)
            cur, carry = [], 0.0
            continue
        carry += float(d.get("minutes_from_prev", 0) or 0)
        feature = str(d.get("feature", "") or "").strip()
        if (not d.get("confirmed", True) or not feature
                or len(letters_only(str(d.get("visible_text", "")))) < 3):
            continue
        cur.append(Stop(id=d["id"], visible_text=str(d["visible_text"]).strip(), feature=feature,
                        minutes_from_prev=carry if cur else 0.0, safe=True))
        carry = 0.0
    if cur:
        segments.append(cur)
    return segments


def load_route(path: str) -> List[List[Stop]]:
    data = json.load(open(path, encoding="utf-8"))
    return route_segments(data["stops"] if isinstance(data, dict) else data)


def _next_puzzle(pool: List[Puzzle], chosen: List[Puzzle], rng: random.Random) -> Optional[Puzzle]:
    """Cheap rules first, but prefer a word whose stops overlap the other teams' as little as possible."""
    used = {c.word for c in chosen}
    top = sorted(pool, key=lambda p: (p.cost, p.word))[: max(60, len(pool) // 2)]
    rng.shuffle(top)
    taken = [{s.stop_id for s in c.steps} for c in chosen]
    best, best_score = None, -1e9
    for p in top[:300]:
        if p.word in used:
            continue
        a = {s.stop_id for s in p.steps}
        score = min((1 - len(a & b) / len(a | b) for b in taken), default=1.0) - 0.01 * p.cost
        if score > best_score:
            best, best_score = p, score
    return best


def build_hunt(llm, segments: Sequence[Sequence[Stop]], words: Sequence[str], teams: int = 3, min_len: int = 5,
               max_len: int = 7, max_minutes: Optional[float] = 25.0, seed: int = 0, max_tries: int = 40,
               max_rewrites: int = 2, judge: bool = True, progress: Callable[[str], None] = lambda m: None) -> Dict:
    candidates = [s for seg in segments for s in seg]
    if len(candidates) < min_len:
        raise ValueError(f"Only {len(candidates)} usable stops (confirmed, safe, with a description); "
                         f"need at least {min_len}. Confirm more stops first.")
    by_id = {s.id: s for s in candidates}
    pool: List[Puzzle] = []
    seg_of: Dict[str, Sequence[Stop]] = {}
    for seg in segments:
        for p in enumerate_puzzles(seg, words, min_len, max_len, max_minutes):
            pool.append(p)
            seg_of[id(p)] = seg
    if not pool:
        raise ValueError("No word can be spelled by these stops within the time limit. Add stops, raise "
                         "--max-minutes, or lower --min-len.")
    progress(f"{len(pool)} possible puzzles from {len(candidates)} stops in {len(segments)} segment(s).")

    rng = random.Random(seed)
    cache: Dict[Tuple[str, str], Dict] = {}
    built: List[Dict] = []
    chosen: List[Puzzle] = []
    skipped: List[Dict] = []
    tries = 0
    while len(built) < teams and pool and tries < max_tries:
        p = _next_puzzle(pool, chosen, rng)
        if p is None:
            break
        pool.remove(p)
        progress(f"Team {len(built) + 1}: trying {p.word} ({p.direction})")
        steps, failed = [], ""
        for n, st in enumerate(p.steps, 1):
            stop = by_id[st.stop_id]
            key = (st.stop_id, st.rule)
            if key not in cache:
                progress(f"  clue {n}/{len(p.steps)} for {st.stop_id} ...")
                cache[key] = make_clue(llm, stop, candidates, rule=st.rule, max_rewrites=max_rewrites, judge_clues=judge)
            r = cache[key]
            if not r["ok"]:
                failed = f"no acceptable clue for {st.stop_id} ({stop.visible_text})"
                break
            steps.append({"n": n, "stop_id": st.stop_id, "sign": stop.visible_text, "rule": st.rule,
                          "rule_text": describe_rule(st.rule), "letter": st.letter, "sign_letters": len(letters_only(stop.visible_text)),
                          "clue": r["clue"], "feature": stop.feature,
                          "attempts": r["attempts"]})
        if failed:
            tries += 1
            skipped.append({"word": p.word, "reason": failed})
            progress(f"  dropped {p.word}: {failed}")
            continue
        chosen.append(p)
        seg = seg_of[id(p)]
        idx = next(i for i, x in enumerate(seg) if x.id == p.steps[0].stop_id)
        sidx = idx - 1 if p.direction == "forward" else idx + 1          # the scouted stop just before clue 1
        has_start = 0 <= sidx < len(seg)
        approach = (seg[idx].minutes_from_prev if p.direction == "forward" else seg[sidx].minutes_from_prev) if has_start else 0.0
        walk = round(route_minutes(p.steps, seg), 1)
        built.append({"team": len(built) + 1, "word": p.word, "direction": p.direction, "check": p.check,
                      "cost": p.cost, "minutes": walk, "approach_minutes": round(approach, 1),
                      "total_minutes": round(walk + approach, 1),
                      "start_sign": seg[sidx].visible_text if has_start else "", "steps": steps})
        progress(f"  team {len(built)} ready: {p.word}")
    return {"teams": built, "skipped": skipped,
            "stats": {"stops": len(candidates), "segments": len(segments), "teams_requested": teams,
                      "clue_attempts": sum(r["attempts"] for r in cache.values()), "clues": len(cache), "judge": judge}}


# ---------------------------------------------------------------- sheets (HTML, print to PDF from the browser)

CSS = """
@page { size: A4; margin: 14mm; }
body { font-family: Georgia, 'Times New Roman', serif; color: #111; max-width: 180mm; margin: 0 auto; line-height: 1.4; }
h1 { margin: 0; font-size: 24pt; } .sub { color: #555; margin: 1mm 0 5mm; font-family: sans-serif; font-size: 10.5pt; }
.step { border: 1.5px solid #888; border-radius: 3mm; padding: 3mm 4mm; margin: 3mm 0; display: flex; gap: 4mm;
        align-items: center; break-inside: avoid; }
.num { font: bold 17pt sans-serif; min-width: 9mm; color: #2a6; } .txt { flex: 1; }
.rule { font: 10pt sans-serif; color: #444; margin-top: 1.5mm; }
.box { width: 15mm; height: 15mm; border: 2px solid #111; flex: none; }
.final { margin-top: 6mm; padding: 4mm; border: 2px solid #111; border-radius: 3mm; break-inside: avoid; }
.final .box { display: inline-block; margin-right: 2mm; vertical-align: middle; }
.note { font: 9.5pt sans-serif; color: #333; margin-top: 4mm; } .note b { color: #000; }
table { border-collapse: collapse; width: 100%; font: 10pt sans-serif; } td, th { border: 1px solid #999; padding: 2mm; text-align: left; vertical-align: top; }
@media print { .noprint { display: none; } }
"""



def _page(title: str, body: str) -> str:
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{html.escape(title)}</title>'
            f"<style>{CSS}</style></head><body>{body}</body></html>")


def render_sheet(team: Dict, title: str = "Paper Trail", start: str = "", note: str = "") -> str:
    """Player sheet. Contains clues and letter rules only: never the signs or the answer."""
    e = html.escape
    rows = "".join(
        f'<div class="step"><div class="num">{s["n"]}</div><div class="txt">{e(s["clue"])}'
        f'<div class="rule">Write the <b>{e(s["rule_text"])}</b> of the sign whose name has '
        f'<b>{s.get("sign_letters") or len(letters_only(s["sign"]))} letters</b>.</div></div><div class="box"></div></div>'
        for s in team["steps"])
    boxes = '<span class="box"></span>' * len(team["word"])
    body = (f"<h1>{e(title)}: Team {team['team']}</h1>"
            f'<div class="sub">{len(team["steps"])} places &middot; about {team.get("total_minutes", team["minutes"]):g} min of walking'
            + (f" &middot; start at: {e(team['start_sign'])}" if team.get("start_sign")
               else (f" &middot; start: {e(start)}" if start else "")) + "</div>"
            "<p>Follow the clues in order. At each place, find the sign and write the letter the clue asks for. "
            "A place can have several signs: yours is the one whose name has the number of letters shown. "
            "Count letters only: skip spaces, apostrophes and digits. Your letters, in order, spell a real word.</p>"
            + rows +
            f'<div class="final"><b>Your word</b> ({len(team["word"])} letters):<br><br>{boxes}'
            f'<div class="note"><b>Check number: {team["check"]}.</b> Give each letter a value (A=1, B=2 ... Z=26) and add '
            "them up. While the total is above 26, subtract 26. You should get the check number. If you don't, a sign may "
            "have changed or a letter is wrong: look again.</div></div>"
            + (f'<div class="note">{e(note)}</div>' if note else ""))
    return _page(f"{title} - Team {team['team']}", body)


def render_key(hunt: Dict, title: str = "Paper Trail") -> str:
    """Organiser's key: words, signs, letters, clues. Keep it away from the teams."""
    e = html.escape
    parts = [f"<h1>{e(title)}: organiser key</h1><div class='sub'>Do not hand this to the teams.</div>"]
    for t in hunt["teams"]:
        trs = "".join(f"<tr><td>{s['n']}</td><td>{e(s['stop_id'])}</td><td>{e(s['sign'])}</td><td>{e(s['rule_text'])}</td>"
                      f"<td>{s.get('sign_letters') or len(letters_only(s['sign']))}</td><td><b>{e(s['letter'])}</b></td><td>{e(s['clue'])}</td><td>{e(s.get('feature', ''))}</td><td>{s.get('attempts', '')}</td></tr>" for s in t["steps"])
        parts.append(f"<h2>Team {t['team']}: {e(t['word'])} (check {t['check']}, ~{t.get('total_minutes', t['minutes']):g} min)</h2>"
                     + (f"<p class='note'>Take this team to: <b>{e(t['start_sign'])}</b></p>" if t.get("start_sign") else "")
                     + f"<table><tr><th>#</th><th>stop</th><th>sign</th><th>rule</th><th>letters in sign</th><th>letter</th><th>clue</th>"
                     f"<th>what the clue was written from (check it is true)</th><th>tries</th></tr>{trs}</table>")
    if hunt.get("skipped"):
        parts.append("<p class='note'>Words dropped because no acceptable clue could be written: "
                     + e(", ".join(f"{s['word']} ({s['reason']})" for s in hunt["skipped"])) + "</p>")
    return _page(f"{title} - key", "".join(parts))


def puzzle_from_team(t: Dict) -> Puzzle:
    return Puzzle(t["word"], t["direction"], [Step(s["stop_id"], s["rule"], s["letter"]) for s in t["steps"]],
                  t.get("cost", 0), t["check"])


def debrief(hunt: Dict, answers: Dict[int, str]) -> str:
    """Compare what each team wrote with the key. Wrong positions point at stops that probably changed."""
    from .composer import check_value, localize_discrepancy
    lines = ["# Debrief", ""]
    for t in hunt["teams"]:
        n = t["team"]
        if n not in answers:
            lines.append(f"## Team {n}: no answer given")
            continue
        obs = "".join(answers[n].upper().split())
        r = localize_discrepancy(obs, puzzle_from_team(t))
        if r["status"] == "ok":
            lines += [f"## Team {n}: correct ({t['word']})", ""]
        elif r["status"] == "length_mismatch":
            lines += [f"## Team {n}: wrote {obs or '(nothing)'}, expected {len(t['word'])} letters ({t['word']})",
                      "- A letter is missing or extra: check with the team which clue they skipped.", ""]
        else:
            lines.append(f"## Team {n}: wrote {obs}, expected {t['word']}")
            for pos in r["wrong_positions"]:
                s = t["steps"][pos]
                lines.append(f"- letter {pos + 1}: wrote {obs[pos]}, expected {s['letter']}. Stop {s['stop_id']} "
                             f"('{s['sign']}', {s['rule_text']}): the sign may have changed, or the team misread it. "
                             f"Go and look.")
            lines.append(f"- their check number would be {check_value(obs)}, expected {t['check']}")
            lines.append("")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- editing and writing files (no model needed)

def write_files(hunt: Dict, out: str, title: str = "Paper Trail", start: str = "", note: str = "") -> None:
    """Write hunt.json, one sheet per team and the organiser key into folder `out`."""
    folder = Path(out)
    folder.mkdir(exist_ok=True)
    hunt["meta"] = {"title": title, "start": start, "note": note}
    (folder / "hunt.json").write_text(json.dumps(hunt, indent=2, ensure_ascii=False), encoding="utf-8")
    for t in hunt["teams"]:
        (folder / f"team{t['team']}.html").write_text(render_sheet(t, title, start, note), encoding="utf-8")
    (folder / "key.html").write_text(render_key(hunt, title), encoding="utf-8")


def _team(hunt: Dict, team: int) -> Dict:
    t = next((x for x in hunt["teams"] if x["team"] == team), None)
    if t is None:
        raise ValueError(f"No team {team}. Teams: {', '.join(str(x['team']) for x in hunt['teams'])}")
    return t


def set_clue(hunt: Dict, team: int, n: int, text: str) -> List[str]:
    """Replace one clue by hand. Returns problems found (a leaked sign, unsafe advice); the edit is still applied."""
    t = _team(hunt, team)
    if not 1 <= n <= len(t["steps"]):
        raise ValueError(f"Team {team} has clues 1 to {len(t['steps'])}")
    st = t["steps"][n - 1]
    problems = validate_clue(text, Stop(st["stop_id"], st["sign"], st.get("feature", "")), st["rule"], min_words=3)
    st["clue"], st["edited"] = text.strip(), True
    return problems


def set_start(hunt: Dict, team: int, sign: str, minutes: Optional[float] = None) -> None:
    t = _team(hunt, team)
    t["start_sign"] = sign.strip()
    if minutes is not None:
        t["approach_minutes"] = round(float(minutes), 1)
    t["total_minutes"] = round(t["minutes"] + t.get("approach_minutes", 0.0), 1)
