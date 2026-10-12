import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from papertrail.models import Stop
from papertrail.composer import (apply_rule, best_assignment, check_value, enumerate_puzzles,
                                 localize_discrepancy, pick_for_teams, describe_rule, load_words)
from papertrail.guard import validate_clue, grounded
from papertrail.cluelab import make_clue
from papertrail.llm import FakeLLM

STOPS = [
    Stop("s1", "Banyan Bakery", "yellow bakery with a blue awning", 0),
    Stop("s2", "Royal Tailors", "narrow tailor shop with a mannequin in the window", 3),
    Stop("s3", "Oasis Juice", "juice stall with a green cart", 2),
    Stop("s4", "Wood Works", "carpenter workshop with stacked planks outside", 4),
    Stop("s5", "Newspaper Stand", "red kiosk selling papers by the bus stop", 3),
    Stop("s6", "Temple Gate", "stone gateway with brass bells", 5),
    Stop("s7", "Highway Crossing", "busy road crossing", 2, safe=False),
]


def test_rules():
    assert apply_rule("Banyan Bakery", "first") == "B"
    assert apply_rule("Banyan Bakery", "last") == "Y"
    assert apply_rule("Banyan Bakery", "nth:2") == "A"
    assert apply_rule("Banyan Bakery", "nth:-2") == "R"
    assert apply_rule("ಬೆಂಗಳೂರು", "first") is None
    assert describe_rule("nth:-2") == "2nd-to-last letter"


def test_spells_word_in_walking_order():
    res = best_assignment(STOPS[:6], "BROWN")
    assert res is not None
    steps, cost = res
    assert "".join(s.letter for s in steps) == "BROWN"
    assert [s.stop_id for s in steps] == ["s1", "s2", "s3", "s4", "s5"]
    assert cost == 0


def test_unsafe_stops_never_used_and_checksum():
    puzzles = enumerate_puzzles(STOPS, ["BROWN", "TABLE", "HIGHWAY"], 5, 7)
    assert puzzles, "expected at least one puzzle"
    for p in puzzles:
        assert "s7" not in {s.stop_id for s in p.steps}
        assert p.check == check_value(p.word)
        # letters really come from the rule applied to the sign text
        by_id = {s.id: s for s in STOPS}
        for st in p.steps:
            assert apply_rule(by_id[st.stop_id].visible_text, st.rule) == st.letter


def test_route_minutes_limit():
    assert enumerate_puzzles(STOPS, ["BROWN"], 5, 7, max_minutes=1) == []
    assert enumerate_puzzles(STOPS, ["BROWN"], 5, 7, max_minutes=100)


def test_teams_get_different_words():
    words = load_words(top=20000)
    puzzles = enumerate_puzzles(STOPS, words, 4, 6)
    chosen = pick_for_teams(puzzles, 3, seed=1)
    assert len({p.word for p in chosen}) == len(chosen)


def test_discrepancy_localization():
    p = enumerate_puzzles(STOPS, ["BROWN"], 5, 7)[0]
    ok = localize_discrepancy("BROWN", p)
    assert ok["status"] == "ok" and ok["checksum_matches"]
    bad = localize_discrepancy("BRAWN", p)   # position 2 differs -> stop s3 changed
    assert bad["status"] == "mismatch" and bad["stops"] == ["s3"] and not bad["checksum_matches"]
    assert localize_discrepancy("BRO", p)["status"] == "length_mismatch"


def test_guard():
    stop = STOPS[0]
    assert validate_clue("Find Banyan Bakery near the corner of the street today please", stop)
    assert validate_clue("Cross the road and look for the yellow shop with an awning today", stop)
    assert validate_clue("Take the first letter of the name of the yellow shop with the awning", stop)
    assert validate_clue("Look for the yellow shop with a blue awning beside the old water tap", stop) == []
    assert grounded("Banyan Bakery", "stop one banyan bakery yellow awning")
    assert grounded("Banyan Bakery", "stop one banian bakery yellow awning")   # mild mishearing
    assert not grounded("Moonlight Pharmacy", "stop one banyan bakery yellow awning")


def test_clue_loop_rewrites_leaks_and_checks_solver():
    calls = {"writer": 0}

    def fake(system, user):
        if system.startswith("You write"):
            calls["writer"] += 1
            if calls["writer"] == 1:
                return "Find Banyan Bakery near the corner of the street today please"   # leaks sign text
            return "Look for the yellow shop with a blue awning beside the old water tap"
        return "s1"                                                                       # solver

    r = make_clue(FakeLLM(fake), STOPS[0], STOPS[:6])
    assert r["ok"] and r["attempts"] == 2


def test_clue_loop_fails_when_solver_cannot_pick():
    fake = lambda s, u: ("Look for the yellow shop with a blue awning beside the old water tap"
                         if s.startswith("You write") else "s2")
    r = make_clue(FakeLLM(fake), STOPS[0], STOPS[:6], max_rewrites=1)
    assert not r["ok"] and r["clue"] is None
