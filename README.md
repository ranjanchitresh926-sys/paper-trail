# Paper Trail

Record a walk with your voice, get a puzzle hunt for the same route. Whisper and Gemma run on your own machine, and plain code decides everything that can be checked.

Built for the Hacktoberfest Open-Source AI Challenge, Week 1 (Touch Grass).

## Demo
`docs/index.html` is a single-page demo on an invented route: a sample team sheet, the check number, and the debrief that points at a misread stop. It runs in any browser (the models do not; they need a GPU laptop). To host it: GitHub repo, Settings, Pages, deploy from the `main` branch, `/docs` folder.

## What it does

1. You walk a loop with a voice recorder running. At each stop you say what the sign says and one thing you can see:
   *"Stop 4. Sign: Maple Court. I see: a white house behind a low stone wall."*
2. `scout_to_stops.py` transcribes the recording with faster-whisper and asks Gemma 4 for the list of stops. Code throws out anything that isn't in the transcript.
3. `build_hunt.py` finds real words that the signs' letters spell in walking order, has Gemma write one clue per stop, and prints a sheet per team plus an organiser key.
4. Teams follow the clues, read one letter off each sign, and write the word. A check number tells them if they misread something. `debrief.py` points at the stop if they got it wrong.

I scout by voice because the open map data for my area is too thin to generate routes from.

## Setup

Python 3.10 to 3.13, [Ollama](https://ollama.com), and an NVIDIA GPU (developed on an RTX 5050 with 8 GB).

```
python -m venv .venv
.venv\Scripts\activate                     # Linux/macOS: source .venv/bin/activate
pip install torch --index-url https://download.pytorch.org/whl/cu128
pip install -r requirements.txt
ollama pull gemma4:e4b
ollama pull gemma4:e2b
python check_setup.py
```

On Windows, `setup.bat`, `pull_models.bat` and `check.bat` do the same and keep every cache inside the project folder.

## Use

```
python scripts/scout_to_stops.py scout.m4a        # writes stops.json and stops_review.md
python scripts/edit_stops.py export               # edit stops_edit.txt, then:
python scripts/edit_stops.py apply stops_edit.txt
python scripts/build_hunt.py --teams 2 --start "Main gate" --title "My Paper Trail"
python scripts/debrief.py 1=WORD 2=WORD           # the words the teams actually wrote
```

`SCOUTING.md` covers how to record the walk. `RUN_THE_HUNT.md` is a short guide for the organiser. `edit_hunt.py` and `render_hunt.py` fix a clue or a start place by hand without running a model.

## What the code decides and what the models do

The models propose and write. Code checks:

- every sign must appear in the transcript, and a stop is only unsafe if you said so
- a description you never gave is dropped, and descriptions about people or purpose are flagged
- the word is spelled by the signs' letters in walking order from a cleaned list of common words, so a solvable hunt is guaranteed; every word gets a check number
- a clue is rejected if it quotes the sign or uses a colour, material or position the description never mentioned
- a second Gemma pass lists anything in the clue that the description doesn't support, and a third must pick the right stop out of all the stops before the clue is accepted
- no hunt crosses a stop marked unsafe

## What happened when I used it

- The first scouting recording gave 696 words and 36 phantom stops for 13 real ones. Whisper repeated a sentence every 30 seconds during silences. A voice-activity filter and `condition_on_previous_text=False` brought it to 238 words and 13 stops.
- The first hunt build wrote 21 clues in 32 attempts. At least six of the ten that shipped contained details I never gave ("weathered brick", "near the curb"). The solver check only shows a clue can be told apart from the others, not that it is true, so the invented-details check and the judge pass were added.
- Two friends walked the final hunt, one per team: 20 and 18 minutes, right letters first time. They read the sheets on their phones, and I did not measure screen time.

## Layout

```
papertrail/    the library: scout.py (recording to stops), composer.py (words and letters), cluelab.py (clue writer, judge, solver),
               guard.py (code-side checks), hunt.py (teams, sheets, debrief)
scripts/       command-line entry points
tests/         42 tests, plus fixtures from real runs with the place names changed
data/          the word list and a sample stops file
```

## Tests

```
python -m pytest -q tests        # 42 tests, no models needed
```

Fixtures in `tests/fixtures` come from real runs with the place names changed.

## Limits

One route, two testers who know the place. Latin-letter signs only. Tested on Windows with an NVIDIA GPU. The judge pass has not been measured against human review.

## License

MIT. See `LICENSE`.
