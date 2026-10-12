"""Build the hunt from your checked stops.json: one word, route and verified clue set per team, plus printable sheets.

    python scripts/build_hunt.py                       (reads stops.json, writes the folder hunt/)
    python scripts/build_hunt.py --teams 4 --start "main gate" --max-minutes 30

Only stops with "confirmed": true, a description and "safe": true are used. Open hunt/team1.html in a browser and
print it (Ctrl+P, Save as PDF if you want a file). hunt/key.html is yours: it shows the signs and answers."""
import argparse, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from papertrail.composer import load_words
from papertrail.hunt import build_hunt, load_route, write_files
from papertrail.llm import OllamaLLM


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stops", default="stops.json")
    ap.add_argument("--out", default="hunt")
    ap.add_argument("--teams", type=int, default=3)
    ap.add_argument("--min-len", type=int, default=5)
    ap.add_argument("--max-len", type=int, default=7)
    ap.add_argument("--max-minutes", type=float, default=25.0)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--start", default="", help="where teams begin, printed on the sheets")
    ap.add_argument("--title", default="Paper Trail")
    ap.add_argument("--llm-model", default="gemma4:e4b")
    ap.add_argument("--note", default="", help="optional footer printed on every team sheet")
    ap.add_argument("--max-tries", type=int, default=40, help="how many words to try before giving up on a team")
    ap.add_argument("--no-judge", action="store_true", help="skip the extra truthfulness check (faster, less safe)")
    a = ap.parse_args()

    segments = load_route(a.stops)
    print(f"{sum(len(s) for s in segments)} usable stops in {len(segments)} hazard-free segment(s) "
          f"({', '.join(str(len(s)) for s in segments)}).")
    try:
        hunt = build_hunt(OllamaLLM(a.llm_model), segments, load_words(), a.teams, a.min_len, a.max_len,
                          a.max_minutes, a.seed, max_tries=a.max_tries, judge=not a.no_judge, progress=print)
    except ValueError as e:
        sys.exit(f"\nCannot build the hunt: {e}")
    except Exception as e:                                    # Ollama not running, model missing, ...
        sys.exit(f"\nCould not talk to Ollama ({type(e).__name__}: {e}). Is Ollama running? Try: ollama list")

    out = Path(a.out)
    write_files(hunt, a.out, a.title, a.start, a.note)
    got = len(hunt["teams"])
    print(f"\n{got} of {a.teams} team sheets written to {out}{chr(92)}  "
          f"(words: {', '.join(t['word'] for t in hunt['teams']) or 'none'})")
    if got < a.teams:
        print("Fewer teams than asked: more stops, longer --max-minutes or better descriptions give more options.")
    print("Open the team files in a browser to print. Keep key.html to yourself.")


if __name__ == "__main__":
    main()
