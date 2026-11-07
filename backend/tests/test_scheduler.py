from datetime import timedelta

from app.models import DEFAULT_SETTINGS
from app.pipeline.commitments import detect
from app.pipeline.rank import rank
from app.pipeline.scheduler import Block, meal_blocks, schedule, workout_block
from tests.helpers import DAY, TZ, demo_data


def _plan(settings=None):
    settings = settings or dict(DEFAULT_SETTINGS)
    data = demo_data()
    fixed = [Block("meeting", e.title, 30, start=e.start, end=e.end, fixed=True) for e in data.events]
    ranked = rank(detect(data.items), settings)
    flexible = meal_blocks(DAY, settings) + [workout_block(DAY, settings, data.health)]
    flexible += [Block(r.candidate.kind, r.candidate.title, r.duration_min, priority=r.priority) for r in ranked]
    return schedule(DAY, settings, fixed, flexible), settings


def test_no_overlaps():
    placed, _ = _plan()
    timed = sorted([b for b in placed if b.start], key=lambda b: b.start)
    for a, b in zip(timed, timed[1:]):
        assert a.end <= b.start, f"{a.title} overlaps {b.title}"


def test_tasks_inside_working_hours_and_meetings_untouched():
    placed, settings = _plan()
    for b in placed:
        if b.kind in ("commitment", "follow_up") and b.start:
            assert b.start.astimezone(TZ).strftime("%H:%M") >= settings["working_hours"]["start"]
            assert b.end.astimezone(TZ).strftime("%H:%M") <= settings["working_hours"]["end"]
    meetings = [b for b in placed if b.kind == "meeting"]
    assert len(meetings) == 4 and all(m.fixed for m in meetings)


def test_low_recovery_shortens_workout():
    settings = dict(DEFAULT_SETTINGS)
    block = workout_block(DAY, settings, demo_data().health)
    assert block.duration_min < settings["workout"]["duration_min"]
    assert "recovery is low" in block.reason


def test_meals_respect_diet():
    settings = {**DEFAULT_SETTINGS, "diet": {"preferences": ["vegan"], "avoid": []}}
    titles = " ".join(b.title.lower() for b in meal_blocks(DAY, settings))
    for meat in ("chicken", "salmon", "turkey", "eggs", "yoghurt", "feta"):
        assert meat not in titles


def test_higher_priority_task_scheduled_first():
    placed, _ = _plan({**DEFAULT_SETTINGS, "vip_people": ["Sarah Chen"]})
    tasks = [b for b in placed if b.kind in ("commitment", "follow_up") and b.start]
    deck = next(b for b in tasks if "deck" in b.title.lower())
    assert deck.priority == max(t.priority for t in tasks)
    # 60-min task: first gap that fits is after the 09:30–09:45 stand-up (+5 min buffer)
    assert deck.start.strftime("%H:%M") == "09:50"


def test_unfittable_block_is_unscheduled():
    settings = {**DEFAULT_SETTINGS, "working_hours": {"start": "09:00", "end": "09:20"}}
    big = Block("commitment", "Huge task", 120, priority=90)
    placed = schedule(DAY, settings, [], [big])
    assert placed[0].status == "unscheduled" and placed[0].start is None
    assert timedelta(minutes=big.duration_min)
