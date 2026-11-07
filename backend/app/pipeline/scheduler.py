"""Deterministic placement of flexible blocks around fixed ones. Never produces overlaps."""

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.connectors.types import HealthMetric

BUFFER = timedelta(minutes=5)

MEAL_WINDOWS = {  # tag -> (duration, earliest, latest end)
    "breakfast": (30, "06:30", "10:30"),
    "lunch": (45, "11:30", "15:30"),
    "dinner": (45, "17:30", "22:00"),
}
WORKOUT_WINDOWS = {
    "morning": ("06:30", "07:00", "10:00"),
    "midday": ("12:00", "12:00", "14:30"),
    "evening": ("17:30", "18:00", "21:00"),
}

MEAL_IDEAS = {
    "breakfast": [
        ("Overnight oats with berries and Greek yoghurt", {"vegetarian"}),
        ("Scrambled eggs on wholegrain toast with spinach", {"vegetarian"}),
        ("Tofu scramble with avocado toast", {"vegetarian", "vegan"}),
        ("Chia pudding with mango and almonds", {"vegetarian", "vegan", "gluten-free"}),
        ("Greek yoghurt, banana and nut butter bowl", {"vegetarian", "gluten-free"}),
    ],
    "lunch": [
        ("Chicken, quinoa and roasted veg bowl", {"gluten-free"}),
        ("Lentil and feta salad with wholegrain bread", {"vegetarian"}),
        ("Chickpea and roasted veg wrap with hummus", {"vegetarian", "vegan"}),
        ("Salmon poke bowl with brown rice", {"gluten-free"}),
        ("Black bean burrito bowl", {"vegetarian", "vegan", "gluten-free"}),
    ],
    "dinner": [
        ("Baked salmon, sweet potato and greens", {"gluten-free"}),
        ("Chicken stir-fry with vegetables and rice", {"gluten-free"}),
        ("Vegetable and chickpea curry with brown rice", {"vegetarian", "vegan", "gluten-free"}),
        ("Wholewheat pasta with tomato, spinach and white beans", {"vegetarian", "vegan"}),
        ("Turkey chilli with a side salad", {"gluten-free"}),
    ],
}


@dataclass
class Block:
    kind: str
    title: str
    duration_min: int
    start: datetime | None = None
    end: datetime | None = None
    fixed: bool = False
    priority: float = 0.0
    reason: str = ""
    details: str = ""
    source_provider: str = ""
    source_link: str = ""
    owed_to: str = ""
    confidence: float = 1.0
    status: str = "proposed"
    tag: str = ""
    ref: int | None = None
    extra: dict = field(default_factory=dict)


def parse_hhmm(day: date, value: str, tz: ZoneInfo) -> datetime:
    h, m = (int(x) for x in value.split(":"))
    return datetime.combine(day, time(h, m), tzinfo=tz)


def find_slot(busy: list[tuple[datetime, datetime]], earliest: datetime, latest_end: datetime,
              duration: timedelta) -> datetime | None:
    cursor = earliest
    for b_start, b_end in sorted(busy):
        if b_end + BUFFER <= cursor:
            continue
        if cursor + duration + BUFFER <= b_start:
            break
        cursor = max(cursor, b_end + BUFFER)
    return cursor if cursor + duration <= latest_end else None


def latest_metric(health: list[HealthMetric], name: str) -> float | None:
    values = [m for m in health if m.name == name]
    return max(values, key=lambda m: m.day).value if values else None


def workout_block(day: date, settings: dict, health: list[HealthMetric]) -> Block:
    prefs = settings.get("workout", {})
    duration = int(prefs.get("duration_min", 45))
    types = prefs.get("types") or ["run", "strength", "yoga"]
    readiness = latest_metric(health, "readiness")
    sleep = latest_metric(health, "sleep_hours")
    low = (readiness is not None and readiness < 65) or (sleep is not None and sleep < 6.5)
    if low:
        duration = max(20, int(duration * 0.6) // 5 * 5)
        kind = next((t for t in types if t.lower() in ("yoga", "walk", "mobility", "stretching")), "easy walk")
        bits = []
        if sleep is not None:
            bits.append(f"{sleep:g}h sleep")
        if readiness is not None:
            bits.append(f"readiness {readiness:g}")
        reason = f"Lighter session because recovery is low ({', '.join(bits)})."
    else:
        kind = types[day.toordinal() % len(types)]
        reason = "Recovery looks good, so a full session." if readiness or sleep else "Your planned workout."
    return Block(kind="workout", title=f"Workout: {kind} ({duration} min)", duration_min=duration, reason=reason,
                 tag="workout", priority=60)


def meal_blocks(day: date, settings: dict) -> list[Block]:
    diet = {p.lower() for p in settings.get("diet", {}).get("preferences", [])}
    avoid = [a.lower() for a in settings.get("diet", {}).get("avoid", [])]
    blocks = []
    for tag, (duration, _, _) in MEAL_WINDOWS.items():
        options = [name for name, tags in MEAL_IDEAS[tag]
                   if diet <= tags and not any(a in name.lower() for a in avoid)] or [n for n, _ in MEAL_IDEAS[tag]]
        choice = options[day.toordinal() % len(options)]
        blocks.append(Block(kind="meal", title=f"{tag.capitalize()}: {choice}", duration_min=duration, tag=tag,
                            details="Simple suggestion based on your diet preferences.",
                            reason="Keeps your energy steady around tomorrow's schedule.", priority=70))
    return blocks


def _window(block: Block, day: date, settings: dict, tz: ZoneInfo) -> tuple[datetime, datetime]:
    wh = settings.get("working_hours", {"start": "09:00", "end": "18:00"})
    if block.tag in MEAL_WINDOWS:
        _, earliest, latest = MEAL_WINDOWS[block.tag]
        preferred = settings.get("meals", {}).get(block.tag, earliest)
        return max(parse_hhmm(day, preferred, tz) - timedelta(minutes=30), parse_hhmm(day, earliest, tz)), \
            parse_hhmm(day, latest, tz)
    if block.tag == "workout":
        pref = settings.get("workout", {}).get("preferred_time", "morning")
        _, start, latest = WORKOUT_WINDOWS.get(pref, WORKOUT_WINDOWS["morning"])
        return parse_hhmm(day, start, tz), parse_hhmm(day, latest, tz)
    return parse_hhmm(day, wh["start"], tz), parse_hhmm(day, wh["end"], tz)


def _preferred_start(block: Block, day: date, settings: dict, tz: ZoneInfo, window_start: datetime) -> datetime:
    if block.tag in MEAL_WINDOWS:
        preferred = parse_hhmm(day, settings.get("meals", {}).get(block.tag, MEAL_WINDOWS[block.tag][1]), tz)
        return preferred
    return window_start


def schedule(day: date, settings: dict, fixed: list[Block], flexible: list[Block]) -> list[Block]:
    """Place `flexible` blocks (in the given order, meals/workout first) around `fixed` ones."""
    tz = ZoneInfo(settings.get("timezone", "UTC"))
    busy = [(b.start, b.end) for b in fixed if b.start and b.end]
    placed = list(fixed)
    ordered = sorted(flexible, key=lambda b: (0 if b.tag in MEAL_WINDOWS or b.tag == "workout" else 1, -b.priority))
    for block in ordered:
        win_start, win_end = _window(block, day, settings, tz)
        dur = timedelta(minutes=block.duration_min)
        preferred = _preferred_start(block, day, settings, tz, win_start)
        start = find_slot(busy, preferred, win_end, dur) or find_slot(busy, win_start, win_end, dur)
        if start is None:
            block.start = block.end = None
            block.status = "unscheduled"
        else:
            block.start, block.end = start, start + dur
            if block.status == "unscheduled":
                block.status = "proposed"
            busy.append((block.start, block.end))
        placed.append(block)
    return sorted(placed, key=lambda b: (b.start is None, b.start or datetime.max.replace(tzinfo=tz)))


def overlaps(start: datetime, end: datetime, others: list[Block]) -> Block | None:
    return next((o for o in others if o.start and o.end and start < o.end and o.start < end), None)
