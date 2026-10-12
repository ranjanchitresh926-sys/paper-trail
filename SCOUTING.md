# Scouting walk

Pick a loop of 8 to 12 stops that takes 20 to 30 minutes. At least six stops need printed text you can read from the path: signboards, shop names, building names. Start your phone's voice recorder, lock the screen and put it in your pocket.

At each stop, stop walking, wait two seconds and say:

> Stop 4. Sign: Director Cottage. I see: a white house behind a low stone wall with a red gate.

What matters:

- Say the sign exactly as printed. If the board says "Old Mill Cafe", say that, not "cafe".
- "I see" gets one thing that will still be there tomorrow: a colour, a shape, a material, steps, a statue, a flag, a tree. Not people, not what the place is for, not sounds. Leave out words that are on the sign.
- Use a different detail at every stop, so one clue can't fit two places.
- Say "unsafe" only for a real hazard. Unsafe stops are skipped, and anything you don't say is treated as safe.
- Walk in silence between stops. The gaps give the walking times.
- A place with no printed text can't give a letter. Leave it out.

Afterwards save the recording as `scout.m4a`, run `scripts/scout_to_stops.py`, and open `stops_review.md`. Check every sign against the real board. Fix what's wrong with `scripts/edit_stops.py export`, edit `stops_edit.txt`, then `apply`. A stop stays unconfirmed until it has a sign you've checked and a description that passes the checks.
