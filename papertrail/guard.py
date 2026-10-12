"""Code-side checks. The model writes; code verifies."""
from __future__ import annotations

import difflib
import re
from typing import List, Optional

from .composer import letter_token
from .models import Stop

UNSAFE = [r"cross (the )?(road|highway|street|tracks)", r"run across", r"climb (the |over )?(wall|fence|gate|tree)",
          r"trespass", r"enter (the )?(private|building|house)"]


def _clue_words(low: str) -> set:
    words = set(re.findall(r"[^\W\d_]+", low))
    return words | {w[:-1] for w in words if len(w) > 3 and w.endswith("s")}


def validate_clue(clue: str, stop: Stop, rule: Optional[str] = None,
                  min_words: int = 8, max_words: int = 45) -> List[str]:
    """Whole-word checks. With `rule`, only the word that supplies the letter is banned (plus the full
    sign); without it, every sign word of 4+ letters is banned."""
    problems: List[str] = []
    low = clue.lower()
    if not (min_words <= len(clue.split()) <= max_words):
        problems.append(f"clue must be {min_words}-{max_words} words")
    words = _clue_words(low)
    sign_tokens = re.findall(r"[^\W\d_]+", stop.visible_text.lower())
    plain = re.findall(r"[^\W\d_]+", re.sub(r"['\u2019]", "", stop.visible_text.lower()))   # "Girl's" -> "girls"
    phrase = r"\b" + r"\W+".join(re.escape(t) for t in plain) + r"s?\b"
    if plain and re.search(phrase, re.sub(r"['\u2019]", "", low)):
        leak = True
    elif rule:
        tok = letter_token(stop.visible_text, rule)
        leak = bool(tok) and tok.lower() in words
    else:
        leak = any(len(t) >= 4 and t in words for t in sign_tokens)
    if leak:
        problems.append("clue quotes the sign text; describe what is visible instead")
    if re.search(r"\b(first|last|second|third|2nd|3rd)\b.{0,12}\bletter\b", low):
        problems.append("clue must not mention which letter is used")
    for pat in UNSAFE:
        if re.search(pat, low):
            problems.append("clue suggests an unsafe action")
            break
    return problems


def _norm(s: str) -> str:
    return re.sub(r"[\W_]+", "", s.casefold())


def grounded(visible_text: str, transcript: str, min_ratio: float = 0.8) -> bool:
    """Reject a model-extracted sign that does not actually appear in the scout transcript."""
    v, t = _norm(visible_text), _norm(transcript)
    if not v:
        return False
    if v in t:
        return True
    size = len(v)
    for i in range(max(1, len(t) - size + 1)):
        if difflib.SequenceMatcher(None, v, t[i:i + size]).ratio() >= min_ratio:
            return True
    return False


_RISKY = set("""red orange yellow green blue purple pink brown black white grey gray golden gold silver beige cream maroon
bright dark pale colourful colorful brick bricks stone stones metal metallic iron steel wooden wood glass concrete marble
tiles tiled granite beyond behind across opposite nearby adjacent distance distant corner curb kerb roadside junction
crossing uphill downhill ahead towards toward""".split())
_GENERIC = set("""building buildings structure structures place area large small huge tall big wide long front side middle
centre center called block floor floors""".split())


try:
    from wordfreq import zipf_frequency as _zipf
except ImportError:                                   # without wordfreq every word counts as rare
    def _zipf(word, lang="en"):
        return 0.0


def _stems(text: str) -> set:
    ws = set(re.findall(r"[a-z]+", text.lower()))
    return ws | {w[:-1] for w in ws if len(w) > 4 and w.endswith("s")} | {w[:-2] for w in ws if len(w) > 5 and w.endswith("es")}


def invented_details(clue: str, stop: Stop, others) -> List[str]:
    """Words in the clue that the stop's own description never used and that are typical inventions: colours,
    materials, positions, or words taken from ANOTHER stop's description. The solver pass only proves a clue can be
    told apart from the others; it cannot tell whether the clue is true. This catches the common culprits."""
    own = _stems(stop.feature)
    elsewhere = set()
    for o in others:
        if o.id != stop.id:
            elsewhere |= _stems(o.feature)
    found = []
    for w in sorted(set(re.findall(r"[a-z]+", clue.lower()))):
        if len(w) < 4:
            continue
        forms = {w, w[:-1] if w.endswith("s") and len(w) > 4 else w, w[:-2] if w.endswith("es") and len(w) > 5 else w}
        if forms & own:
            continue
        if w in _RISKY or (forms & elsewhere and not forms & _GENERIC and _zipf(w, "en") < 4.7):
            found.append(w)
    return found
