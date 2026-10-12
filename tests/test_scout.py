import json, sys, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))

from papertrail.composer import letter_token, load_words, enumerate_puzzles
from papertrail.guard import validate_clue
from papertrail.llm import FakeLLM
from papertrail.models import Stop
from papertrail.scout import (Transcript, Word, build_stops, drop_repeats, extract, feature_problems, load_stops, locate,
                             parse_json, strip_sign_word)


def make_tr(sentences):
    """sentences: [(text, silent_seconds_before)] -> Transcript with 0.4 s per word."""
    words, t = [], 0.0
    for text, pause in sentences:
        t += pause
        for w in text.split():
            words.append(Word(w, t, t + 0.4, 1.0))
            t += 0.4
    return Transcript(words)


STRUCTURED = make_tr([
    ("Stop one. Sign Banyan Bakery. I see a yellow shop with a blue awning.", 0),
    ("Stop two. Sign Royal Tailors. I see a narrow shop with a mannequin in the window.", 90),
    ("Stop three. Sign Main Gate. Unsafe. Road crossing here.", 120),
    ("Stop four. Sign Temple Gate. I see a stone gateway with brass bells.", 60),
])


def fake_json(stops):
    return FakeLLM(lambda s, u: json.dumps({"stops": stops}))


def test_checker_drops_invented_and_forces_unsafe():
    proposed = extract(fake_json([
        {"sign": "Banyan Bakery", "feature": "a yellow shop with a blue awning", "unsafe": False},
        {"sign": "Moonlight Pharmacy", "feature": "green cross", "unsafe": False},          # never said
        {"sign": "Royal Tailors", "feature": "a golden dragon statue", "unsafe": False},    # invented detail
        {"sign": "Main Gate", "feature": "", "unsafe": False},                              # said "unsafe"
        {"sign": "Temple Gate", "feature": "a stone gateway with brass bells", "unsafe": False},
    ]), STRUCTURED)
    r = build_stops(STRUCTURED, proposed)
    assert [d["sign"] for d in r["dropped"]] == ["Moonlight Pharmacy"]
    s1, s2, s3, s4 = r["stops"]
    assert s1["confirmed"] and s1["feature"].startswith("a yellow shop")
    assert s2["feature"] == "" and not s2["confirmed"]
    assert not s3["safe"] and not s3["confirmed"]
    assert s4["confirmed"]
    assert s2["minutes_from_prev"] == 1.5 and s4["minutes_from_prev"] == 1.0
    assert r["notes"] == []


def test_model_cannot_clear_unsafe_but_can_add_it():
    proposed = [{"sign": "Banyan Bakery", "feature": "a yellow shop", "unsafe": True}]
    assert build_stops(STRUCTURED, proposed)["stops"][0]["safe"] is False


REAL = ("I start at Sundial and here comes the underpass. I have crossed it and I can see the Marlow. Now, next is the "
        "Director Cottages, then the temple, then the girls hostel, after that the international visitors hostel, "
        "then the dispensary, then the basketball court, then the sports complex, then the squash court and on the "
        "other side is the open air theatre.")


def test_real_gate_recording_flags_mishearing_and_continuous_speech():
    tr = make_tr([(REAL, 0)])
    signs = [l.strip() for l in open(ROOT / "tests" / "fixtures" / "gate_signs.txt") if l.strip()]
    r = build_stops(tr, [{"sign": s, "feature": "", "unsafe": False} for s in signs])
    assert len(r["stops"]) == 12 and r["dropped"] == []
    by = {s["visible_text"]: s for s in r["stops"]}
    assert any("Cottages" in f for f in by["Director Cottage"]["flags"])       # the real mishearing is surfaced
    assert by["Girl's Hostel"]["heard"].lower() == "girls hostel"
    assert any("without pausing" in n for n in r["notes"])                       # timing marked unreliable
    assert all(not s["confirmed"] for s in r["stops"])                           # none had a description yet


def test_low_whisper_confidence_is_flagged():
    tr = make_tr([("Stop one. Sign Banyan Bakery. I see a yellow shop.", 0)])
    for w in tr.words:
        if w.text in ("Banyan", "Bakery."):
            w.prob = 0.4
    r = build_stops(tr, [{"sign": "Banyan Bakery", "feature": "a yellow shop", "unsafe": False}])
    assert any("unsure" in f for f in r["stops"][0]["flags"]) and not r["stops"][0]["confirmed"]


def test_locate_order_and_parse_json_and_load(tmp_path):
    assert locate(STRUCTURED, "Temple Gate")[1] > locate(STRUCTURED, "Royal Tailors")[1]
    assert locate(STRUCTURED, "Zebra Crossing Hospital") is None
    assert parse_json('```json\n{"stops": [{"sign": "A B", "feature": "", "unsafe": false}]}\n```')[0]["sign"] == "A B"
    path = tmp_path / "stops.json"
    path.write_text(json.dumps([
        {"id": "s1", "visible_text": "Banyan Bakery", "feature": "yellow", "minutes_from_prev": 0, "confirmed": True},
        {"id": "s2", "visible_text": "Royal Tailors", "feature": "", "minutes_from_prev": 2, "confirmed": False}]))
    assert [s.id for s in load_stops(str(path))] == ["s1"]
    assert len(load_stops(str(path), require_confirmed=False)) == 2


def test_letter_token_and_token_aware_guard():
    assert letter_token("Girl's Hostel", "first") == "Girl"
    assert letter_token("Girl's Hostel", "last") == "Hostel"
    assert letter_token("Girl's Hostel", "nth:-2") == "Hostel"
    sign = Stop("t", "Open Air Theatre", "x")
    ok = "A semicircle of concrete steps faces a stage under the sky, ideal for evening shows."
    assert validate_clue(ok, sign, "first") == []
    # 'stairs' no longer trips on the word 'air'
    assert validate_clue("A curved set of grey stairs leads down to a stage beside the wide lawn.", sign) == []
    # the word that supplies the letter is banned; other words of the sign are not
    assert validate_clue("Find the open grassy bowl with concrete steps facing a stage today.", sign, "first")
    assert validate_clue("Find the open grassy bowl with concrete steps facing a stage today.", sign, "last") == []
    assert validate_clue("Find the open air theatre with concrete steps facing a stage today.", sign, "last")


def test_word_list_is_clean_and_works_on_real_signs():
    words = set(load_words())
    assert len(words) > 5000
    for bad in ("ADELE", "ADIDAS", "AETNA", "EBITDA", "SHIT", "PORN"):
        assert bad not in words
    stops = [Stop(f"s{i}", t, "x", 2) for i, t in enumerate(l.strip() for l in open(ROOT / "tests" / "fixtures" / "gate_signs.txt") if l.strip())]
    assert len(enumerate_puzzles(stops, words, 5, 7)) > 100


def test_unsafe_said_before_the_sign_belongs_to_that_stop():
    tr = make_tr([("Stop one. Sign Banyan Bakery. I see a yellow shop with blue awning.", 0),
                  ("Stop two. Unsafe road crossing. Sign Main Gate. I see a green gate.", 60),
                  ("Stop three. Sign Temple Gate. I see brass bells.", 60)])
    p = [{"sign": "Banyan Bakery", "feature": "yellow shop", "unsafe": False},
         {"sign": "Main Gate", "feature": "green gate", "unsafe": False},
         {"sign": "Temple Gate", "feature": "brass bells", "unsafe": False}]
    assert [s["safe"] for s in build_stops(tr, p)["stops"]] == [True, False, True]


def test_short_word_description_is_kept_if_it_was_said():
    tr = make_tr([("Stop one. Sign Banyan Bakery. I see a red car by the big oak.", 0)])
    s = build_stops(tr, [{"sign": "Banyan Bakery", "feature": "a red car", "unsafe": False}])["stops"][0]
    assert s["feature"] == "a red car" and s["confirmed"]


def test_guard_is_whole_word_and_blocklist_applies(tmp_path):
    inn = Stop("x", "Inn", "f")
    assert validate_clue("A stone building at the beginning of the lane with a wooden bench outside it today.", inn, "first") == []
    assert validate_clue("Find the old inn on the corner with a wooden bench outside and a lantern above it.", inn, "first")
    assert validate_clue("Look for the girls hostel building with a tall white gate and roses around it.",
                         Stop("g", "Girl's Hostel", "f"), "last")
    assert "KIDNAP" not in load_words() and "HEROIN" not in load_words()


def test_load_stops_keeps_walking_time_of_left_out_stops(tmp_path):
    path = tmp_path / "stops.json"
    path.write_text(json.dumps([
        {"id": "s1", "visible_text": "Banyan Bakery", "feature": "x", "minutes_from_prev": 0, "confirmed": True},
        {"id": "s2", "visible_text": "Royal Tailors", "feature": "", "minutes_from_prev": 2, "confirmed": False},
        {"id": "s3", "visible_text": "Temple Gate", "feature": "y", "minutes_from_prev": 3, "confirmed": True}]))
    assert [s.minutes_from_prev for s in load_stops(str(path))] == [0.0, 5.0]


FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "real_scout_transcript.json"
REAL_PROPOSALS = [("Sain Sundial", "big hostel with a circular court in the middle"), ("Sain Underpass", "connecting bridge"),
                  ("Sain Marlow", "lavish hotel like bungalow"), ("Sain Directors Residence", "white house behind a low stone wall"),
                  ("Sain Temple", "old shrine"), ("Sain Girls Hostel", "many girls going and coming out"),
                  ("Sain Admin Block", "huge center of control building"), ("Sain Football Ground", "huge green field"),
                  ("Management Department", "many students doing the MBA course here"),
                  ("Sain Lecture Theater 2", "many students going for attending lectures"), ("Sain Nut Meg", "cup of coffee")]


def test_real_recording_with_whisper_loops_becomes_eleven_stops():
    # a real 20-minute walk: Whisper repeated "This is the connecting bridge..." 28 times during silent walking
    words = [Word(**d) for d in json.loads(FIXTURE.read_text())]
    clean = Transcript(drop_repeats(words))
    assert len(words) == 696 and len(clean.words) < 200
    assert clean.text.count("connecting bridge") == 1 and "Stop 3, Sain Marlow." in clean.text   # real markers survive
    res = build_stops(clean, [{"sign": s, "feature": f, "unsafe": False} for s, f in REAL_PROPOSALS])
    stops = res["stops"]
    assert [s["visible_text"] for s in stops] == ["Sundial", "Underpass", "Marlow", "Directors Residence", "Temple",
                                                  "Girls Hostel", "Admin Block", "Football Ground",
                                                  "Management Department", "Lecture Theater 2", "Nut Meg"]
    assert not res["dropped"] and all(s["safe"] for s in stops)
    assert 12 < sum(s["minutes_from_prev"] for s in stops) < 25          # ~18 min walked, measured from the silences
    girls = stops[5]
    assert not girls["confirmed"] and any("sign words" in f for f in girls["flags"])
    assert any("people" in f for f in stops[9]["flags"])


def test_sign_word_is_stripped_and_description_less_repeats_dropped():
    assert strip_sign_word("Sain Sundial") == "Sundial" and strip_sign_word("Sign Temple Gate") == "Temple Gate"
    assert strip_sign_word("Saint Mary Church") == "Saint Mary Church" and strip_sign_word("Sain") == "Sain"
    tr = make_tr([("Stop one. Sain Banyan Bakery. I see a yellow shop with a blue awning.", 0),
                  ("Stop two. Sain Banyan Bakery.", 30), ("Stop three. Sain Temple Gate. I see brass bells.", 30)])
    res = build_stops(tr, [{"sign": "Sain Banyan Bakery", "feature": "yellow shop", "unsafe": False},
                           {"sign": "Sain Banyan Bakery", "feature": "", "unsafe": False},
                           {"sign": "Sain Temple Gate", "feature": "brass bells", "unsafe": False}])
    assert [s["visible_text"] for s in res["stops"]] == ["Banyan Bakery", "Temple Gate"]
    assert "repeat" in res["dropped"][0]["reason"]


def test_feature_problems():
    assert feature_problems("Girls Hostel", "many girls going and coming out")
    assert feature_problems("Lecture Theater 2", "a hall for lectures")
    assert feature_problems("Temple", "red flag on a tall pole") == []
    assert feature_problems("Temple", "") == []


# ---------------------------------------------------------------- regressions from the real scouting recording
def _real_v2():
    return Transcript.from_json((ROOT / "tests" / "fixtures" / "real_scout_transcript_v2.json").read_text())


REAL_GEMMA = [  # what Gemma actually returned on the real, clean transcript (signs and details as spoken)
    ("Sundial", "big hostel with a circular court in the middle where we play cricket usually", False),
    ("Underpass", "connecting bridge that goes to the other side of the college", True),   # Gemma's wrong guess
    ("Marlow", "lavish hotel like bungalow where usually special guests stay", False),
    ("directors residence", "white house behind a low stone wall with a black gate", False),
    ("temple", "old shrine where daily all the time mantras and bhajans are being enchanted", False),
    ("girls hostel", "many girls going and coming out", False),
    ("Admin Block", "huge centre of control building that contains the office to all the high officials", False),
    ("Football Ground", "huge green field where students play", False),
    ("information technology department", "many computer labs where research is being done", False),
    ("engineering sciences department", "Reiki center of excellence for happiness", False),
    ("management department", "many students doing the MBA course here", False),
    ("lecture theater 2", "many students going for attending lectures", False),
    ("Nutmeg", "many students studying here with a cup of coffee by the side", False),
]


def test_real_recording_gemma_unsafe_guess_is_a_question_not_a_barrier():
    r = build_stops(_real_v2(), [{"sign": a, "feature": b, "unsafe": c} for a, b, c in REAL_GEMMA])
    assert len(r["stops"]) == 13 and r["dropped"] == []
    s2 = r["stops"][1]
    assert s2["visible_text"] == "Underpass" and s2["safe"] is True and not s2["confirmed"]
    assert any("Gemma guessed" in f for f in s2["flags"])
    assert r["stops"][3]["visible_text"] == "Directors Residence"           # lower-case from Whisper is tidied


def test_purpose_and_sound_descriptions_are_flagged_but_visible_ones_pass():
    from papertrail.scout import feature_problems
    assert feature_problems("Marlow", "lavish hotel like bungalow where usually special guests stay")
    assert feature_problems("Temple", "mantras and bhajans are being enchanted")
    assert feature_problems("Sundial", "big hostel with a circular court in the middle") == []
    assert feature_problems("Directors Residence", "white house behind a low stone wall with a black gate") == []


def test_only_spoken_hazard_words_make_a_barrier():
    tr = make_tr([("Stop one. Sign Main Gate. Unsafe road crossing here. I see a tall green gate.", 0)])
    r = build_stops(tr, [{"sign": "Main Gate", "feature": "tall green gate", "unsafe": False}])
    assert r["stops"][0]["safe"] is False


def test_export_warns_about_unsafe_barriers(tmp_path):
    import edit_stops
    p = tmp_path / "stops.json"
    p.write_text(json.dumps([{"id": "s1", "visible_text": "Underpass", "feature": "x", "safe": False, "confirmed": False}]))
    out = tmp_path / "edit.txt"
    edit_stops.export(edit_stops.load(str(p)), str(out))
    assert "marked UNSAFE" in out.read_text()
