"""Core engine: turn scouted stops into a self-verifying letter hunt.

Letters collected in walking order spell a real word. Code guarantees this by
construction; the language model only writes clues (see cluelab.py).
"""
from __future__ import annotations

import random
import re
import unicodedata
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .models import Puzzle, Step, Stop

# (rule, cost): lower cost = easier for players to apply on the street
RULES: List[Tuple[str, int]] = [("first", 0), ("last", 1), ("nth:2", 2), ("nth:3", 3), ("nth:-2", 3)]


def describe_rule(rule: str) -> str:
    if rule == "first":
        return "first letter"
    if rule == "last":
        return "last letter"
    n = int(rule.split(":")[1])
    if n == 2:
        return "2nd letter"
    if n == 3:
        return "3rd letter"
    return "2nd-to-last letter" if n == -2 else f"{-n}th-to-last letter"


def letters_only(text: str) -> str:
    t = unicodedata.normalize("NFKD", text)
    return "".join(c for c in t.upper() if "A" <= c <= "Z")


def apply_rule(text: str, rule: str) -> Optional[str]:
    s = letters_only(text)
    if not s:
        return None
    if rule == "first":
        return s[0]
    if rule == "last":
        return s[-1]
    n = int(rule.split(":")[1])
    idx = n - 1 if n > 0 else n
    try:
        return s[idx]
    except IndexError:
        return None


def letter_options(stop: Stop) -> Dict[str, Tuple[str, int]]:
    """letter -> (cheapest rule that yields it, cost)."""
    opts: Dict[str, Tuple[str, int]] = {}
    for rule, cost in RULES:
        ch = apply_rule(stop.visible_text, rule)
        if ch and (ch not in opts or cost < opts[ch][1]):
            opts[ch] = (rule, cost)
    return opts


def best_assignment(sequence: Sequence[Stop], word: str) -> Optional[Tuple[List[Step], int]]:
    """Cheapest way to spell `word` as a subsequence of `sequence` (one letter per stop)."""
    n, k = len(sequence), len(word)
    opts = [letter_options(s) for s in sequence]
    INF = 10 ** 9
    dp = [[INF] * (k + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        dp[i][0] = 0
    for i in range(1, n + 1):
        for j in range(1, k + 1):
            best = dp[i - 1][j]
            o = opts[i - 1].get(word[j - 1])
            if o is not None and dp[i - 1][j - 1] + o[1] < best:
                best = dp[i - 1][j - 1] + o[1]
            dp[i][j] = best
    if dp[n][k] >= INF:
        return None
    steps: List[Step] = []
    i, j = n, k
    while j > 0:
        if dp[i][j] == dp[i - 1][j]:
            i -= 1
        else:
            rule, _ = opts[i - 1][word[j - 1]]
            steps.append(Step(sequence[i - 1].id, rule, word[j - 1]))
            i -= 1
            j -= 1
    steps.reverse()
    return steps, dp[n][k]


def check_value(word: str) -> int:
    """Checksum 1..26: sum of letter values (A=1) wrapped. Printed on the sheet so
    players can tell if something on the street has changed."""
    return (sum(ord(c) - 64 for c in word.upper()) - 1) % 26 + 1


def route_minutes(steps: Sequence[Step], stops: Sequence[Stop]) -> float:
    idx = {s.id: i for i, s in enumerate(stops)}
    pos = [idx[s.stop_id] for s in steps]
    lo, hi = min(pos), max(pos)
    return sum(stops[i].minutes_from_prev for i in range(lo + 1, hi + 1))


def candidate_words(words: Iterable[str], min_len: int, max_len: int) -> List[str]:
    return sorted({w.upper() for w in words if w.isascii() and w.isalpha() and min_len <= len(w) <= max_len})


def enumerate_puzzles(stops: Sequence[Stop], words: Iterable[str], min_len: int = 5,
                      max_len: int = 7, max_minutes: Optional[float] = None) -> List[Puzzle]:
    usable = [s for s in stops if s.safe]
    available = set()
    for s in usable:
        available |= set(letter_options(s))
    out: List[Puzzle] = []
    cands = candidate_words(words, min_len, max_len)
    for direction, seq in (("forward", usable), ("reverse", usable[::-1])):
        for w in cands:
            if not set(w) <= available:
                continue
            res = best_assignment(seq, w)
            if res is None:
                continue
            steps, cost = res
            if max_minutes is not None and route_minutes(steps, stops) > max_minutes:
                continue
            out.append(Puzzle(w, direction, steps, cost, check_value(w)))
    return out


def pick_for_teams(puzzles: Sequence[Puzzle], teams: int, seed: int = 0) -> List[Puzzle]:
    """Give each team a different word and a route that overlaps others as little as possible,
    so teams cannot simply follow each other."""
    rng = random.Random(seed)
    pool = sorted(puzzles, key=lambda p: (p.cost, p.word))
    pool = pool[: max(teams * 20, len(pool) // 2)]
    rng.shuffle(pool)
    chosen: List[Puzzle] = []
    used = set()

    def stopset(p: Puzzle):
        return {s.stop_id for s in p.steps}

    while pool and len(chosen) < teams:
        best, best_score = None, -1e9
        for p in pool[:300]:
            if p.word in used:
                continue
            if chosen:
                a = stopset(p)
                score = min(1 - len(a & stopset(c)) / len(a | stopset(c)) for c in chosen)
            else:
                score = 1.0
            score -= 0.01 * p.cost
            if score > best_score:
                best, best_score = p, score
        if best is None:
            break
        chosen.append(best)
        used.add(best.word)
        pool.remove(best)
    return chosen


def localize_discrepancy(observed: str, puzzle: Puzzle) -> dict:
    """Compare what a team wrote with the key. Mismatched positions point at stops
    that probably changed since the scout walk."""
    obs = "".join(observed.upper().split())
    if len(obs) != len(puzzle.word):
        return {"status": "length_mismatch", "wrong_positions": [], "stops": []}
    wrong = [i for i, (a, b) in enumerate(zip(obs, puzzle.word)) if a != b]
    return {
        "status": "ok" if not wrong else "mismatch",
        "wrong_positions": wrong,
        "stops": [puzzle.steps[i].stop_id for i in wrong],
        "checksum_matches": check_value(obs) == puzzle.check,
    }


def letter_token(text: str, rule: str) -> Optional[str]:
    """The word of the sign that supplies the letter for `rule` (players read that word)."""
    s = letters_only(text)
    if not s:
        return None
    n = len(s)
    if rule == "first":
        idx = 0
    elif rule == "last":
        idx = n - 1
    else:
        k = int(rule.split(":")[1])
        idx = k - 1 if k > 0 else n + k
    if not 0 <= idx < n:
        return None
    pos = 0
    for tok in re.findall(r"[^\W\d_]+", text):
        length = len(letters_only(tok))
        if pos <= idx < pos + length:
            return tok
        pos += length
    return None


DEFAULT_WORDS = Path(__file__).resolve().parent.parent / "data" / "words.txt"

# Words nobody wants as the answer of a friendly street hunt (violence, crime, drugs, sex, alcohol).
BLOCKED = set("""KIDNAP KIDNAPS ABDUCT ABDUCTED ABDUCTS MURDER MURDERED MURDERS KILLER KILLERS KILLED KILLING CORPSE CORPSES
DEAD DEATH DEATHS DIED DYING SLAVERY WEAPON WEAPONS RIFLE COCAINE HEROIN RACIST SEXUAL NAKED BREAST BREASTS STRIPPER
BLOOD BLOODY HANG HANGED GRAVE TORTURE VICTIM VICTIMS ASSAULT ABUSE ABUSED CRIME CRIMINAL THIEF THIEVES STEAL STOLE
ROBBER SMOKE SMOKING BEER WINE VODKA ALCOHOL SUICIDE BOMB BOMBS TERROR RAPE RAPED""".split())


def load_words(path: Optional[str] = None, top: int = 40000) -> List[str]:
    """Curated common-English list (no names or brands) bundled in data/words.txt."""
    if path is None and DEFAULT_WORDS.exists():
        path = str(DEFAULT_WORDS)
    if path:
        with open(path, encoding="utf-8") as f:
            return [ln.strip() for ln in f if ln.strip() and ln.strip().upper() not in BLOCKED]
    try:
        from wordfreq import top_n_list
    except ImportError as e:
        raise SystemExit("Install wordfreq (pip install wordfreq) or pass a word list file.") from e
    return top_n_list("en", top)
