"""Writer -> guard -> solver loop. A clue is accepted only if code finds no problems
AND an independent solver pass picks the right stop from all candidates."""
from __future__ import annotations

import json
import re
from typing import Dict, List, Optional, Sequence

from .guard import invented_details, validate_clue
from .models import Stop

WRITER_SYSTEM = (
    "You write one clue for a walking puzzle hunt. You know ONLY the facts given as 'Place features'. Use those facts "
    "and nothing else: do not add colours, materials, sizes, positions, distances, surroundings, other places, or what "
    "the place is for or who uses it. Say it plainly, in the same words as the facts where you can (a spiral staircase "
    "stays a spiral staircase). Keep any letter or number given in the facts, such as 'B Block'. Never quote the sign "
    "text. Never tell people to cross roads, climb, or enter private property. Write one complete, grammatical sentence of 8-30 words. Reply with the clue only."
)
JUDGE_SYSTEM = (
    "You check a clue for a walking puzzle hunt against the only facts known about the place. List every specific "
    "detail in the clue that is NOT stated in the facts: a colour, material, position, distance, purpose, nearby place "
    "or object the facts never mention. A plain paraphrase of a stated fact is fine (for example 'towering spires' to "
    "'tall pointed structures'). If everything is supported, return an empty list."
)
JUDGE_SCHEMA = {"type": "object", "properties": {"unsupported": {"type": "array", "items": {"type": "string"}}},
                "required": ["unsupported"]}
SOLVER_SYSTEM = (
    "You are playing a street puzzle hunt. Given a clue and candidate places, reply with the id of the single "
    "best match and nothing else."
)


def judge(llm, clue: str, feature: str) -> Optional[List[str]]:
    """Details in the clue that the description does not support. None = the judge gave no usable answer."""
    try:
        raw = llm.chat(JUDGE_SYSTEM, f"Facts: {feature}\nClue: {clue}", temperature=0.0, format=JUDGE_SCHEMA)
        raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.M).strip()
        return [str(x) for x in json.loads(raw).get("unsupported", []) if str(x).strip()]
    except Exception:
        return None


def solve(llm, clue: str, candidates: Sequence[Stop]) -> Optional[str]:
    listing = "\n".join(f"- {c.id}: {c.feature}" for c in candidates)
    reply = llm.chat(SOLVER_SYSTEM, f"Clue: {clue}\nCandidates:\n{listing}\nAnswer with one id.", temperature=0.0)
    found = [(m.start(), c.id) for c in candidates for m in re.finditer(rf"\b{re.escape(c.id)}\b", reply)]
    return min(found)[1] if found else None


def make_clue(llm, stop: Stop, candidates: Sequence[Stop], rule: Optional[str] = None,
              max_rewrites: int = 2, judge_clues: bool = True) -> Dict:
    """Accepted only if: no sign leak or unsafe advice (code), no invented colours/materials/positions (code), nothing
    unsupported by the description (judge pass), and a solver picks the right stop from all candidates."""
    log: List[Dict] = []
    feedback = ""
    for attempt in range(1, max_rewrites + 2):
        prompt = f"Place features: {stop.feature}\n" + (f"Fix these problems: {feedback}\n" if feedback else "")
        clue = llm.chat(WRITER_SYSTEM, prompt, temperature=0.4)
        problems = validate_clue(clue, stop, rule)
        bad = invented_details(clue, stop, candidates)
        if bad:
            problems.append(f"the clue uses details the description never gave ({', '.join(bad)}): use only the description")
        unsupported = judge(llm, clue, stop.feature) if (judge_clues and not problems) else None
        if unsupported:
            problems.append(f"the clue states things the description does not say ({'; '.join(unsupported)}): remove them")
        if problems:
            log.append({"attempt": attempt, "clue": clue, "problems": problems})
            feedback = "; ".join(problems)
            continue
        picked = solve(llm, clue, candidates)
        log.append({"attempt": attempt, "clue": clue, "solver_picked": picked,
                    "judge": "unsupported-none" if unsupported == [] else "no-answer"})
        if picked == stop.id:
            return {"stop": stop.id, "clue": clue, "ok": True, "attempts": attempt, "log": log}
        other = next((c.feature for c in candidates if c.id == picked), "another place")
        feedback = f"a solver confused it with a place described as: {other}. Add what distinguishes this one."
    return {"stop": stop.id, "clue": None, "ok": False, "attempts": max_rewrites + 1, "log": log}
