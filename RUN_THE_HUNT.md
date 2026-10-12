# Running the hunt

**Before.** Run `build_hunt.py`, then open `hunt/key.html`. For every clue, read the right-hand column ("what the clue was written from") against the real place. If a clue isn't true, fix it: `python scripts/edit_hunt.py clue TEAM NUMBER "new clue"`. Print `team1.html`, `team2.html` and so on, or send them, since they read fine on a phone. Keep `key.html` to yourself.

**What to tell the teams.** Follow the clues in order. At each place, read the sign whose name has the number of letters shown, and write the letter the clue asks for. Your letters spell a word, and the check number at the bottom tells you if you misread something.

**During.** Start the teams together and note each team's start and finish time, any time they asked for help, any clue that confused them, and any sign they misread.

**After.** `python scripts/debrief.py 1=WORD 2=WORD` with the words they actually wrote. It names the stop that probably changed or was misread.
