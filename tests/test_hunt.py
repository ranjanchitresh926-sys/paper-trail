import json, pathlib, re, sys
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from papertrail.cluelab import SOLVER_SYSTEM
from papertrail.composer import apply_rule, check_value, load_words
from papertrail.hunt import build_hunt, debrief, render_key, render_sheet, route_segments
from papertrail.llm import FakeLLM

SIGNS = ["Sundial", "Underpass", "Marlow", "Director Cottage", "Temple", "Girl's Hostel", "International Visitors Hostel",
         "Dispensary", "Basketball Court", "Sports Complex", "Squash Court", "Open Air Theatre"]
FEATURES = ["hostel block with green shutters", "low concrete tunnel with painted arrows", "tall tower with a clock face",
            "white house behind a stone wall", "small shrine under an old tree", "pink building with a long veranda",
            "guest house with flags out front", "clinic with a red cross painted outside", "fenced court with orange hoops",
            "glass building with a curved roof", "brick building with tiny windows", "grassy bowl with concrete steps"]


def rows(unsafe_at=(), unconfirmed=()):
    return [{"id": f"s{i + 1}", "visible_text": t, "feature": FEATURES[i], "minutes_from_prev": 0 if i == 0 else 2,
             "safe": i not in unsafe_at, "confirmed": i not in unconfirmed} for i, t in enumerate(SIGNS)]


def fake():
    def fn(system, user):
        if system == SOLVER_SYSTEM:
            clue = user.split("\n")[0]
            for line in user.splitlines():
                m = re.match(r"- (\w+): (.*)", line)
                if m and m.group(2) in clue:
                    return m.group(1)
            return "none"
        feature = re.search(r"Place features: (.*)", user).group(1)
        return f"Look along the road for the {feature} and you will spot it quickly from the pavement."
    return FakeLLM(fn)


def test_segments_split_at_hazards_and_carry_minutes():
    segs = route_segments(rows(unsafe_at=(3,), unconfirmed=(1,)))
    assert [[s.id for s in seg] for seg in segs] == [["s1", "s3"], ["s5", "s6", "s7", "s8", "s9", "s10", "s11", "s12"]]
    assert segs[0][1].minutes_from_prev == 4          # the skipped stop's leg is added, not lost
    no_feature = rows(); no_feature[2]["feature"] = ""
    assert "s3" not in [s.id for seg in route_segments(no_feature) for s in seg]


def test_hunt_spells_words_in_walking_order_and_never_spans_a_hazard():
    segs = route_segments(rows(unsafe_at=(5,)))                         # hazard after s5
    hunt = build_hunt(fake(), segs, load_words(), teams=3, seed=2)
    assert len(hunt["teams"]) == 3 and len({t["word"] for t in hunt["teams"]}) == 3
    signs = {f"s{i + 1}": t for i, t in enumerate(SIGNS)}
    for t in hunt["teams"]:
        letters = ""
        for s in t["steps"]:
            letters += apply_rule(signs[s["stop_id"]], s["rule"])
            assert s["clue"] and s["letter"] == apply_rule(signs[s["stop_id"]], s["rule"])
        assert letters == t["word"] and check_value(t["word"]) == t["check"]
        idx = [int(s["stop_id"][1:]) for s in t["steps"]]
        assert idx == sorted(idx) or idx == sorted(idx, reverse=True)       # walking order, either direction
        assert all(i <= 5 for i in idx) or all(i >= 7 for i in idx)         # s6 is the hazard


def test_sheet_never_leaks_signs_or_answer_and_key_has_them():
    hunt = build_hunt(fake(), route_segments(rows()), load_words(), teams=2, seed=1)
    for t in hunt["teams"]:
        page = render_sheet(t, start="the main gate").lower()
        own = [st["sign"].lower() for st in t["steps"]]
        assert not any(x in page for x in own) and t["word"].lower() not in page
        assert "check number" in page and ("the main gate" in page or t["start_sign"].lower() in page)
    key = render_key(hunt)
    assert all(team["word"] in key for team in hunt["teams"])


def test_failure_is_reported_not_hidden():
    leaky = FakeLLM(lambda s, u: "Find the Sundial Underpass Temple Dispensary quickly along this lovely road today.")
    hunt = build_hunt(leaky, route_segments(rows()), load_words(), teams=2, max_tries=3)
    assert hunt["teams"] == [] and len(hunt["skipped"]) == 3
    try:
        build_hunt(fake(), route_segments(rows())[:0] or [[]], load_words())
        assert False
    except ValueError as e:
        assert "usable stops" in str(e)


def test_debrief_points_at_the_changed_stop():
    hunt = build_hunt(fake(), route_segments(rows()), load_words(), teams=2, seed=1)
    t1, t2 = hunt["teams"]
    wrong = list(t2["word"]); wrong[1] = "Q"
    text = debrief(hunt, {1: t1["word"], 2: "".join(wrong)})
    assert f"Team 1: correct ({t1['word']})" in text
    assert t2["steps"][1]["stop_id"] in text and t2["steps"][1]["sign"] in text
    assert "no answer" in debrief(hunt, {1: t1["word"]})


def test_edit_stops_confirm_rules(tmp_path):
    import edit_stops
    p = tmp_path / "stops.json"
    data = rows(unsafe_at=(2,)); data[0]["feature"] = ""
    for d in data:
        d["confirmed"] = False
    p.write_text(json.dumps(data))
    edit_stops.main(["--file", str(p), "confirm", "--all"])
    out = {s["id"]: s for s in json.loads(p.read_text())}
    assert out["s2"]["confirmed"] and not out["s3"]["confirmed"] and not out["s1"]["confirmed"]   # unsafe / no feature refused
    edit_stops.main(["--file", str(p), "set", "s1", "feature", "a green gate"])
    edit_stops.main(["--file", str(p), "set", "s2", "visible_text", "Underpass Road"])
    out = {s["id"]: s for s in json.loads(p.read_text())}
    assert out["s1"]["feature"] == "a green gate" and not out["s1"]["confirmed"] and out["s2"]["visible_text"] == "Underpass Road"
    edit_stops.main(["--file", str(p), "unsafe", "s4"])
    assert json.loads(p.read_text())[3]["safe"] is False


def test_edit_stops_export_apply_roundtrip(tmp_path):
    import edit_stops
    p = tmp_path / "stops.json"
    data = rows()
    data[5]["feature"] = "many girls going and coming out"         # people + sign words -> must not be confirmed
    for d in data:
        d["confirmed"] = False
    p.write_text(json.dumps(data))
    txt = tmp_path / "edit.txt"
    edit_stops.main(["--file", str(p), "export", str(txt)])
    assert "# s6:" in txt.read_text() and "s1 | Sundial |" in txt.read_text()
    lines = txt.read_text().splitlines()
    lines = [("s6 | Girl's Hostel | pink building with a long veranda" if l.startswith("s6 |") else l) for l in lines]
    lines = [("s2 | DELETE |" if l.startswith("s2 |") else l) for l in lines]
    lines = [("s7 | International Visitors Hostel | guest house with flags | unsafe" if l.startswith("s7 |") else l) for l in lines]
    lines.append("s8 | Dispensary | many people waiting outside")
    txt.write_text("\n".join(lines))
    edit_stops.main(["--file", str(p), "apply", str(txt)])
    out = {s["id"]: s for s in json.loads(p.read_text())}
    assert "s2" not in out and out["s3"]["minutes_from_prev"] == 4        # deleted stop's walking time moves on
    assert out["s6"]["confirmed"] and out["s6"]["feature"] == "pink building with a long veranda"
    assert out["s7"]["safe"] is False and not out["s7"]["confirmed"]
    assert not out["s8"]["confirmed"] and out["s1"]["confirmed"]


# ---------------------------------------------------------------- regressions from the first real hunt build
import json as _json
from pathlib import Path as _P
from papertrail.guard import invented_details
from papertrail.cluelab import judge, make_clue
from papertrail.models import Stop

_FX = _P(__file__).resolve().parent / "fixtures"


def _real_stops():
    return [Stop(r["id"], r["visible_text"], r["feature"], r["minutes_from_prev"]) for r in _json.load(open(_FX / "real_stops_v1.json"))]


def test_real_first_hunt_invented_details_are_caught():
    stops = _real_stops()
    by = {s.id: s for s in stops}
    hunt = _json.load(open(_FX / "real_hunt_v1.json"))
    caught = {}
    for t in hunt["teams"]:
        for st in t["steps"]:
            bad = invented_details(st["clue"], by[st["stop_id"]], stops)
            if bad:
                caught[st["stop_id"]] = bad
    # real clues that shipped with invented colours, materials and positions
    assert "brick" in caught["s9"]                       # "weathered brick": the description never said brick
    assert {"curb", "metal"} <= set(caught["s13"])       # "near the curb", "small metal object"
    assert {"metal", "beyond", "green"} <= set(caught["s6"])   # swings "beyond the green expanse": a place it never mentioned
    assert {"grey", "metal"} <= set(caught["s4"])        # "grey" stones, "metal" gate
    assert "distance" in caught["s5"]


def test_good_real_clue_is_not_flagged():
    stops = _real_stops()
    by = {s.id: s for s in stops}
    assert invented_details("A large expanse of green grass stretches out before you, marked by tall, upright frames "
                            "at either end.", by["s8"], stops) == []


def test_judge_rejects_unsupported_claims_and_failure_is_not_fatal():
    ok = FakeLLM(lambda s, u: '{"unsupported": ["travelers"]}')
    assert judge(ok, "x", "big hostel") == ["travelers"]
    assert judge(FakeLLM(lambda s, u: '{"unsupported": []}'), "x", "y") == []
    assert judge(FakeLLM(lambda s, u: "s1"), "x", "y") is None            # unparseable: no answer, not a crash


def test_make_clue_rewrites_when_judge_finds_invention():
    stops = [Stop("a", "Alpha Hall", "tall tower with a red flag"), Stop("b", "Beta Hall", "round pond with ducks")]
    state = {"w": 0}

    def fake(system, user):
        if system.startswith("You write"):
            state["w"] += 1
            return ("Find the tall tower where travellers gather under a flag today" if state["w"] == 1
                    else "Find the tall tower with a red flag flying from the top today")
        if system.startswith("You check"):
            return '{"unsupported": ["travellers gather"]}' if "travellers" in user else '{"unsupported": []}'
        return "a"

    r = make_clue(FakeLLM(fake), stops[0], stops)
    assert r["ok"] and r["attempts"] == 2 and "travellers" not in r["clue"]


def test_each_team_gets_its_own_start_and_total_minutes():
    hunt = build_hunt(fake(), route_segments(rows()), load_words(), teams=2, seed=1)
    for t in hunt["teams"]:
        assert t["total_minutes"] == round(t["minutes"] + t["approach_minutes"], 1)
        page = render_sheet(t).lower()
        if t["start_sign"]:
            assert t["start_sign"].lower() in page and f'{t["total_minutes"]:g} min' in page
    assert "Take this team to" in render_key(hunt) or all(not t["start_sign"] for t in hunt["teams"])


# ---------------------------------------------------------------- second real hunt build: sign hints and hand edits
from papertrail.hunt import render_key as _render_key, render_sheet as _render_sheet, set_clue, set_start, write_files


def _hunt_v2():
    return _json.load(open(_FX / "real_hunt_v2.json"))


def test_real_hunt_v2_letters_and_checksums_are_correct():
    for t in _hunt_v2()["teams"]:
        for st in t["steps"]:
            assert apply_rule(st["sign"], st["rule"]) == st["letter"]
        assert "".join(st["letter"] for st in t["steps"]) == t["word"]
        assert check_value(t["word"]) == t["check"]


def test_sheet_tells_players_which_sign_to_read():
    # A Block has its own sign, so "the sign" alone is ambiguous: the letter count picks the right one
    team1 = _hunt_v2()["teams"][0]
    page = _render_sheet(team1, "Campus Paper Trail", "Sundial")
    assert "<b>31 letters</b>" in page                      # Information Technology Department
    team2 = _hunt_v2()["teams"][1]
    assert "<b>14 letters</b>" in _render_sheet(team2)      # Lecture Theater 2 (digits are not counted)
    assert "digits" in page
    assert "letters in sign" in _render_key(_hunt_v2())


def test_edit_a_clue_and_a_start_by_hand(tmp_path):
    hunt = _hunt_v2()
    assert set_clue(hunt, 2, 5, "The building called D Block is two floors high.") == []
    assert hunt["teams"][1]["steps"][4]["edited"] is True
    bad = set_clue(hunt, 2, 5, "Find the lecture hall in D Block today please friends.")
    assert any("quotes the sign" in b for b in bad)
    set_start(hunt, 1, "Underpass", 0.9)
    assert hunt["teams"][0]["total_minutes"] == 18.3
    write_files(hunt, str(tmp_path / "hunt"), "Campus Paper Trail", "Sundial")
    assert "Underpass" in (tmp_path / "hunt" / "team1.html").read_text()
    assert _json.load(open(tmp_path / "hunt" / "hunt.json"))["meta"]["title"] == "Campus Paper Trail"
    import pytest
    with pytest.raises(ValueError):
        set_clue(hunt, 9, 1, "x")
