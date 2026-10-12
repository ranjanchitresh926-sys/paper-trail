"""Scout step: voice recording -> checked list of stops.

The model only proposes stops. Code decides what survives: every sign must be found in the
transcript, a stop is unsafe only if the speaker said so, descriptions the speaker never said are dropped,
and anything doubtful is marked unconfirmed for the creator to review.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, asdict
from difflib import SequenceMatcher
from typing import Dict, List, Optional

from .composer import letters_only
from .models import Stop

STOPWORDS = set("""the and with that this from there their have into over near next been were what when where which while
about above below behind beside between around after before under very some more just like then than also here
really quite sort kind lots stop sign see saw look looks looking can could would should will shall each other""".split())

SCHEMA = {
    "type": "object",
    "properties": {"stops": {"type": "array", "items": {"type": "object", "properties": {
        "sign": {"type": "string"}, "feature": {"type": "string"}, "unsafe": {"type": "boolean"}},
        "required": ["sign", "feature", "unsafe"]}}},
    "required": ["stops"],
}

EXTRACT_SYSTEM = (
    "You read the transcript of a voice recording made while walking a route and list the stops in walking order. "
    "For each stop give: 'sign' = the name or text the speaker read aloud as printed on a sign, copied exactly as "
    "written in the transcript; 'feature' = ONE short visible detail the speaker said about the place (colour, shape, "
    "object), or an empty string if they said none; 'unsafe' = true ONLY if the speaker explicitly said the word "
    "unsafe, dangerous or hazard about that stop; otherwise false. The speaker says the word 'sign' before reading each sign, and it is often written "
    "as 'Sain', 'Sine' or 'Sane': never include it in the sign text. Ignore the stop numbers. If the same stop "
    "is said twice, list it once. Never invent stops, signs or details that are not in the transcript."
)


@dataclass
class Word:
    text: str
    start: float
    end: float
    prob: float = 1.0


@dataclass
class Transcript:
    words: List[Word]

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)

    def to_json(self) -> str:
        return json.dumps([asdict(w) for w in self.words], ensure_ascii=False)

    @staticmethod
    def from_json(raw: str) -> "Transcript":
        return Transcript([Word(**d) for d in json.loads(raw)])


def transcribe(audio: str, model: str = "small", device: str = "cuda", compute_type: str = "float16",
               language: Optional[str] = "en", download_root: Optional[str] = None) -> Transcript:
    from faster_whisper import WhisperModel
    m = WhisperModel(model, device=device, compute_type=compute_type, download_root=download_root)
    # Walking in silence makes Whisper repeat its last sentence forever (seen on a real 20-minute recording).
    # VAD removes the silences before Whisper sees them; no conditioning stops one loop feeding the next.
    segments, _ = m.transcribe(audio, language=language, word_timestamps=True, vad_filter=True,
                               vad_parameters={"min_silence_duration_ms": 1500, "speech_pad_ms": 300},
                               condition_on_previous_text=False)
    words = [Word(w.word.strip(), w.start, w.end, w.probability) for seg in segments for w in (seg.words or [])
             if w.word.strip()]
    return Transcript(words)


def _norm(s: str) -> str:
    return re.sub(r"[\W_]+", "", s.casefold())


def drop_repeats(words: List[Word], n: int = 10) -> List[Word]:
    """Remove Whisper's repetition loops, keeping the first occurrence of everything.

    Pass 1 works per sentence: a sentence that repeats an earlier one (ignoring its leading "Stop N") is dropped, so a
    real "Stop 3, Sain Marlow." survives even when it directly follows a loop. Pass 2 is a backstop for loops without
    punctuation: any run of n+ identical words seen before is dropped. On a real 20-minute recording 28 of 39 spoken
    blocks were one sentence repeated during silent walking, and loop words were not reliably less confident than
    real ones, so repetition itself is the signal."""
    sentences, cur = [], []
    for w in words:
        cur.append(w)
        if w.text.rstrip().endswith((".", "?", "!")):
            sentences.append(cur)
            cur = []
    if cur:
        sentences.append(cur)
    seen, kept = set(), []
    for sent in sentences:
        text = " ".join(w.text for w in sent)
        key = _norm(re.sub(r"^\s*stop\s*\d+\s*[,.:;]?\s*", "", text, flags=re.I))
        if len(key) >= 8 and key in seen:
            continue
        seen.add(key)
        kept.extend(sent)

    toks = [_norm(w.text) for w in kept]
    grams, drop = set(), [False] * len(kept)
    for i in range(len(kept) - n + 1):
        g = tuple(toks[i:i + n])
        if not all(g):
            continue
        if g in grams:
            for k in range(i, i + n):
                drop[k] = True
        else:
            grams.add(g)
    return [w for w, d in zip(kept, drop) if not d]


_SIGN_WORDS = {"sign", "signs", "sain", "sane", "sine", "sighn", "syne", "saine"}


def strip_sign_word(sign: str) -> str:
    """'Sain Sundial' -> 'Sundial': Whisper writes the spoken word 'sign' in many ways."""
    parts = sign.split()
    if len(parts) > 1 and _norm(parts[0]) in _SIGN_WORDS:
        return " ".join(parts[1:]).strip()
    return sign


def locate(tr: Transcript, sign: str, start_idx: int = 0, min_ratio: float = 0.8):
    """Best (ratio, first_word, end_word) match of `sign` in the transcript at or after start_idx."""
    target = _norm(sign)
    n_tok = max(1, len(re.findall(r"\w+", sign)))
    best = None
    for size in range(max(1, n_tok - 1), n_tok + 2):
        for i in range(start_idx, len(tr.words) - size + 1):
            cand = _norm("".join(w.text for w in tr.words[i:i + size]))
            r = SequenceMatcher(None, target, cand).ratio()
            if r >= min_ratio and (best is None or r > best[0] + 1e-9):
                best = (r, i, i + size)
    return best


def _content_words(text: str) -> List[str]:
    return [w for w in re.findall(r"[a-z]+", text.lower()) if len(w) >= 4 and w not in STOPWORDS]


def _stem(w: str) -> str:
    return w[:-1] if w.endswith("s") and len(w) > 4 else w


_FILLER = {"a", "an", "the", "of", "with", "and", "by", "on", "in", "at", "to", "is", "it", "i"}
_HAZARD = re.compile(r"\b(unsafe|danger|dangerous|hazard|hazardous|traffic)\b")


_PEOPLE = {"people", "person", "student", "students", "girls", "boys", "kids", "children", "officials", "staff", "crowd",
           "men", "women", "going", "coming", "playing", "studying", "doing", "attending", "walking", "sitting",
           "standing", "chanting", "waiting", "working"}


_NONVISUAL = {"where", "usually", "daily", "always", "research", "decisions", "decision", "guests", "guest", "mantras",
              "mantra", "bhajans", "happiness", "excellence", "course", "courses", "stay", "stays", "contains", "taken"}


def feature_problems(sign: str, feature: str) -> List[str]:
    """Why a description would make a poor clue: it repeats the sign, or describes people who move."""
    if not feature.strip():
        return []
    fw = re.findall(r"[a-z]+", feature.lower())
    stems = set(fw) | {w[:-1] for w in fw if w.endswith("s") and len(w) > 3}
    out = []
    leak = sorted({t for t in re.findall(r"[a-z]+", sign.lower()) if len(t) >= 4 and t in stems})
    if leak:
        out.append(f"description uses sign words ({', '.join(leak)}): a clue built on it would give the sign away")
    nonvis = sorted(set(fw) & _NONVISUAL)
    if nonvis:
        out.append(f"description sounds like purpose or sound, not something you can see ({', '.join(nonvis)}): "
                   "describe the building or place itself")
    ppl = sorted(set(fw) & _PEOPLE)
    if ppl:
        out.append(f"description is about people or activity ({', '.join(ppl)}): they move, so players cannot rely on "
                   "it. Describe something fixed: colour, shape, material, steps, a statue, a flag, a tree")
    return out


def _feature_heard(feature: str, transcript_text: str) -> bool:
    words = _content_words(feature) or [w for w in re.findall(r"[a-z]+", feature.lower()) if w not in _FILLER]
    if not words:
        return False
    heard = {_stem(w) for w in re.findall(r"[a-z]+", transcript_text.lower())}
    return sum(_stem(w) in heard for w in words) / len(words) >= 0.5


def parse_json(raw: str) -> List[Dict]:
    raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.M).strip()
    data = json.loads(raw)
    return data["stops"] if isinstance(data, dict) else data


def extract(llm, tr: Transcript) -> List[Dict]:
    return parse_json(llm.chat(EXTRACT_SYSTEM, "Transcript:\n" + tr.text, temperature=0.0, format=SCHEMA))


def build_stops(tr: Transcript, proposed: List[Dict]) -> Dict:
    """Validate proposals against the transcript. Returns {"stops": [...], "dropped": [...], "notes": [...]}."""
    kept, dropped, cursor = [], [], 0
    for item in proposed:
        sign = strip_sign_word(str(item.get("sign", "")).strip().strip("\"'"))
        feature_in = str(item.get("feature", "")).strip()
        if any(_norm(k["sign"]) == _norm(sign) and (not feature_in or _norm(feature_in) == _norm(k["feature"]))
               for k in kept):
            dropped.append({"sign": sign, "reason": "said again with no new description (repeat or recording loop)"})
            continue
        if len(letters_only(sign)) < 3:
            dropped.append({"sign": sign, "reason": "too short or no Latin letters"})
            continue
        hit = locate(tr, sign, cursor)
        if hit is None:
            dropped.append({"sign": sign, "reason": "not found in the transcript (invented or misheard badly)"})
            continue
        ratio, i, j = hit
        cursor = j
        kept.append({"sign": sign, "feature": str(item.get("feature", "")).strip(),
                     "model_unsafe": bool(item.get("unsafe")), "i": i, "j": j, "ratio": ratio})

    # a stop's spoken block starts at its "Stop N" marker (so "Stop 2. Unsafe. Sign: Main Gate" is attributed to
    # Main Gate, not to the stop before it) and ends where the next block starts
    starts = []
    for k, st in enumerate(kept):
        lo = kept[k - 1]["j"] if k else 0
        m = next((x for x in range(st["i"] - 1, max(lo, st["i"] - 8) - 1, -1) if _norm(tr.words[x].text) == "stop"), None)
        starts.append(m if m is not None else st["i"])

    out = []
    for k, st in enumerate(kept):
        i, j = st["i"], st["j"]
        nxt = starts[k + 1] if k + 1 < len(kept) else len(tr.words)
        window = " ".join(w.text for w in tr.words[starts[k]:nxt]).lower()
        heard = " ".join(w.text for w in tr.words[i:j]).strip(" ,.;:!?\"'")
        unsafe = bool(_HAZARD.search(window))        # only what the speaker said makes a stop a barrier
        flags = []
        if st["model_unsafe"] and not unsafe:
            flags.append("Gemma guessed this stop might be unsafe but you never said so. If it is a normal walkway "
                         f"ignore this; if it is a hazard run: python scripts\\edit_stops.py unsafe s{k + 1}")
        if _norm(heard) != _norm(st["sign"]):
            flags.append(f"Whisper heard '{heard}' but the sign was recorded as '{st['sign']}': check the real sign")
        if min(w.prob for w in tr.words[i:j]) < 0.6:
            flags.append("Whisper was unsure of these words: check the real sign")
        feature = st["feature"]
        if feature and not _feature_heard(feature, tr.text):
            flags.append(f"description '{feature}' was not found in what was said, so it was removed")
            feature = ""
        if not feature:
            flags.append("no description: add one so a clue can be written")
        flags.extend(feature_problems(st["sign"], feature))
        # walking time ~ the longest silence between the previous stop's sign and this one
        prev_j = kept[k - 1]["j"] if k else i
        gap = max((tr.words[m + 1].start - tr.words[m].end for m in range(max(prev_j - 1, 0), i)), default=0.0) if k else 0.0
        shown = st["sign"].title() if " " in st["sign"] and st["sign"].islower() else st["sign"]
        out.append({"id": f"s{k + 1}", "visible_text": shown, "feature": feature,
                    "minutes_from_prev": 0.0 if k == 0 else max(0.5, round(gap / 60, 1)),
                    "safe": not unsafe, "heard": heard, "t_start": round(tr.words[i].start, 1),
                    "flags": flags, "confirmed": not flags and not unsafe, "_gap": gap})

    notes = []
    later = [s["_gap"] for s in out[1:]]
    if later and max(later) < 3:
        notes.append("You spoke almost without pausing, so walking times are unreliable: "
                     "estimates default to 0.5 min per leg. Pause and walk silently between stops next time.")
    for s in out:
        s.pop("_gap")
    return {"stops": out, "dropped": dropped, "notes": notes}


def load_stops(path: str, require_confirmed: bool = True) -> List[Stop]:
    data = json.load(open(path, encoding="utf-8"))
    data = data["stops"] if isinstance(data, dict) else data
    out, carry = [], 0.0
    for d in data:
        carry += float(d.get("minutes_from_prev", 0) or 0)
        if require_confirmed and not d.get("confirmed", True):
            continue                                   # left out, but the walk to it still takes time
        out.append(Stop(id=d["id"], visible_text=d["visible_text"], feature=d.get("feature", ""),
                        minutes_from_prev=carry if out else 0.0, safe=bool(d.get("safe", True))))
        carry = 0.0
    return out


def review_markdown(result: Dict) -> str:
    lines = ["# Review the stops before building the hunt", "",
             "Open `stops.json`. For every stop below, check the REAL sign on the street (or your photo of it).",
             "Fix `visible_text` if it differs, add a `feature` if missing, then set `\"confirmed\": true`.",
             "Stops left unconfirmed are not used.", ""]
    for s in result["stops"]:
        mark = "OK " if s["confirmed"] else "CHECK"
        lines.append(f"## {s['id']}  [{mark}]  {s['visible_text']}" + ("  (UNSAFE, will be skipped)" if not s["safe"] else ""))
        lines.append(f"- heard: {s['heard']}  |  at {s['t_start']}s  |  leg: {s['minutes_from_prev']} min")
        lines.append(f"- feature: {s['feature'] or '(none)'}")
        lines += [f"- ! {f}" for f in s["flags"]]
        lines.append("")
    if result["dropped"]:
        lines.append("## Dropped by the checker")
        lines += [f"- {d['sign']!r}: {d['reason']}" for d in result["dropped"]]
        lines.append("")
    lines += [f"NOTE: {n}" for n in result["notes"]]
    return "\n".join(lines) + "\n"
