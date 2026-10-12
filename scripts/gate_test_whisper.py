"""Gate test: can Whisper read the signs in your area?

Record yourself reading 10 real signs aloud (any phone voice recorder), write the
signs in `signs.txt` (one per line, same order), then run:

    python scripts/gate_test_whisper.py recording.m4a signs.txt --model small --lang en

Pass = at least 70% of signs matched with <=25% character error.
Tip: for local-script signs, also say the English spelling, and use `--lang` for your language.
"""
import argparse
import re


def norm(s):
    return re.sub(r"[\W_]+", "", s.casefold())


def edit_distance(a, b):
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def best_cer(expected, transcript):
    """Lowest character error rate of `expected` against any window of the transcript."""
    e, t = norm(expected), norm(transcript)
    if not e:
        return 1.0
    best = 1.0
    for size in range(max(1, int(len(e) * 0.7)), int(len(e) * 1.3) + 2):
        for i in range(0, max(1, len(t) - size + 1)):
            best = min(best, edit_distance(e, t[i:i + size]) / len(e))
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("audio")
    ap.add_argument("signs")
    ap.add_argument("--model", default="small")
    ap.add_argument("--lang", default=None)
    ap.add_argument("--device", default="auto", help="auto (uses GPU if available), cuda or cpu")
    ap.add_argument("--compute-type", default=None,
                    help="float16 (default on GPU), float32, bfloat16, int8 (default on CPU)")
    ap.add_argument("--max-cer", type=float, default=0.25)
    args = ap.parse_args()

    from faster_whisper import WhisperModel
    model = WhisperModel(args.model, device=args.device, compute_type=args.compute_type or ("int8" if args.device == "cpu" else "float16"))
    segments, _ = model.transcribe(args.audio, language=args.lang)
    transcript = " ".join(s.text for s in segments)
    print("TRANSCRIPT:\n", transcript, "\n")

    signs = [ln.strip() for ln in open(args.signs, encoding="utf-8") if ln.strip()]
    passed = 0
    for sign in signs:
        cer = best_cer(sign, transcript)
        ok = cer <= args.max_cer
        passed += ok
        print(f"{'PASS' if ok else 'FAIL'}  CER={cer:.2f}  {sign}")
    rate = passed / len(signs)
    print(f"\n{passed}/{len(signs)} signs recognised ({rate:.0%}).  GATE: {'GO' if rate >= 0.7 else 'NO-GO'}")


if __name__ == "__main__":
    main()
