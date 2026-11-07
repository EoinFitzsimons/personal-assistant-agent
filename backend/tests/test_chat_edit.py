from app.pipeline.chat_edit import normalise_time, rule_parse

ITEMS = [
    {"id": 1, "kind": "workout", "tag": "workout", "title": "Workout: yoga (25 min)"},
    {"id": 2, "kind": "meal", "tag": "lunch", "title": "Lunch: Lentil salad"},
    {"id": 3, "kind": "commitment", "tag": "", "title": "Send the Q3 metrics deck by tomorrow noon"},
]


def test_normalise_time():
    assert normalise_time("7am") == "07:00"
    assert normalise_time("7:30 pm") == "19:30"
    assert normalise_time("3") == "15:00"
    assert normalise_time("noon") == "12:00"
    assert normalise_time("25:00") is None


def test_move_and_skip_in_one_message():
    ops, reply = rule_parse("move my workout to 7am and skip lunch", ITEMS)
    assert ops == [{"op": "move", "item_id": 1, "start": "07:00"}, {"op": "remove", "item_id": 2}]
    assert "Moved" in reply and "Removed" in reply


def test_add_and_resize():
    ops, _ = rule_parse("add call mum at 6pm for 20 min", ITEMS)
    assert ops == [{"op": "add", "title": "Call mum", "start": "18:00", "duration_min": 20}]
    ops, _ = rule_parse("make workout 40 min", ITEMS)
    assert ops == [{"op": "resize", "item_id": 1, "duration_min": 40}]


def test_fuzzy_title_match():
    ops, _ = rule_parse("move the Q3 deck to 10:15", ITEMS)
    assert ops == [{"op": "move", "item_id": 3, "start": "10:15"}]


def test_unknown_request():
    ops, reply = rule_parse("what's the weather", ITEMS)
    assert ops == [] and "couldn't understand" in reply
