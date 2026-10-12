"""Turn your scouting recording into stops.json (checked) and stops_review.md.

    python scripts/scout_to_stops.py scout.m4a
    python scripts/scout_to_stops.py scout.m4a --transcript-cache scout_transcript.json   (reuse a transcript)

Whisper runs first, is unloaded, then Gemma structures the stops, so both fit in 8 GB of GPU memory."""
import argparse, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from papertrail.llm import OllamaLLM
from papertrail.scout import Transcript, build_stops, drop_repeats, extract, review_markdown, transcribe


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("audio")
    ap.add_argument("--out", default="stops.json")
    ap.add_argument("--review", default="stops_review.md")
    ap.add_argument("--whisper-model", default="small")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--compute-type", default="float16")
    ap.add_argument("--lang", default="en")
    ap.add_argument("--llm-model", default="gemma4:e4b")
    ap.add_argument("--transcript-cache", default="scout_transcript_v2.json")   # v2: made with VAD, old files are ignored
    ap.add_argument("--retranscribe", action="store_true", help="ignore the cached transcript")
    a = ap.parse_args()

    cache = Path(a.transcript_cache)
    if not a.retranscribe and cache.exists() and cache.stat().st_mtime >= Path(a.audio).stat().st_mtime:
        tr = Transcript.from_json(cache.read_text(encoding="utf-8"))
        print(f"Using cached transcript ({len(tr.words)} words). Delete {cache} to redo it.")
    else:
        tr = transcribe(a.audio, a.whisper_model, a.device, a.compute_type, a.lang,
                        download_root=str(ROOT / "cache" / "hf"))
        cache.write_text(tr.to_json(), encoding="utf-8")
        print(f"Transcribed {len(tr.words)} words.")
    before = len(tr.words)
    tr = Transcript(drop_repeats(tr.words))
    if len(tr.words) < before:
        print(f"Removed {before - len(tr.words)} words of repeated text (Whisper loops while you walked silently).")
    print("\nTRANSCRIPT:\n", tr.text, "\n")

    proposed = extract(OllamaLLM(a.llm_model), tr)
    result = build_stops(tr, proposed)
    out = Path(a.out)
    if out.exists():                                   # keep the creator's edits and confirmations
        backup = out.with_name(out.stem + "_previous.json")
        backup.write_bytes(out.read_bytes())
        print(f"Existing {out} saved as {backup}.")
    out.write_text(json.dumps(result["stops"], indent=2, ensure_ascii=False), encoding="utf-8")
    Path(a.review).write_text(review_markdown(result), encoding="utf-8")

    ok = sum(s["confirmed"] for s in result["stops"])
    print(f"{len(result['stops'])} stops kept ({ok} clean, {len(result['stops']) - ok} need review), "
          f"{len(result['dropped'])} dropped.")
    for n in result["notes"]:
        print("NOTE:", n)
    print("\nNext: python scripts/edit_stops.py export   (then edit stops_edit.txt and run: "
          "python scripts/edit_stops.py apply stops_edit.txt)")


if __name__ == "__main__":
    main()
