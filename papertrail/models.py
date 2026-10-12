from dataclasses import dataclass
from typing import List


@dataclass
class Stop:
    id: str
    visible_text: str            # sign text a player can read from the pavement (Latin letters)
    feature: str                 # short observable description from the scout, used for clues
    minutes_from_prev: float = 0.0
    safe: bool = True            # False = road crossing / hazard: never used as a stop


@dataclass
class Step:
    stop_id: str
    rule: str                    # "first" | "last" | "nth:2" | "nth:3" | "nth:-2"
    letter: str


@dataclass
class Puzzle:
    word: str
    direction: str               # "forward" | "reverse"
    steps: List[Step]
    cost: int                    # lower = easier rules for players
    check: int                   # checksum 1..26, printed on the sheet

    @property
    def letters(self) -> str:
        return "".join(s.letter for s in self.steps)
