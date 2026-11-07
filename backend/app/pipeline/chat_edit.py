"""Turn a chat request into structured edit ops. LLM first, regex fallback."""

import json
import re

from app import llm

TIME_RE = r"(\d{1,2}(?::\d{2})?\s*(?:am|pm)?|noon|morning|afternoon|evening)"
NAMED_TIMES = {"noon": "12:00", "morning": "08:00", "afternoon": "14:00", "evening": "18:00"}
KIND_WORDS = {
    "workout": ["workout", "gym", "run", "exercise", "training", "yoga", "walk"],
    "breakfast": ["breakfast"], "lunch": ["lunch"], "dinner": ["dinner"],
}


def normalise_time(value: str) -> str | None:
    value = value.strip().lower()
    if value in NAMED_TIMES:
        return NAMED_TIMES[value]
    m = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", value)
    if not m:
        return None
    h, mins, ampm = int(m.group(1)), int(m.group(2) or 0), m.group(3)
    if ampm == "pm" and h < 12:
        h += 12
    if ampm == "am" and h == 12:
        h = 0
    if not ampm and 1 <= h <= 6:
        h += 12  # "move it to 3" means 15:00 in a workday
    if h > 23 or mins > 59:
        return None
    return f"{h:02d}:{mins:02d}"


def match_item(phrase: str, items: list[dict]) -> dict | None:
    phrase = phrase.lower().strip()
    for tag, words in KIND_WORDS.items():
        if any(w in phrase for w in words):
            hit = next((i for i in items if i.get("tag") == tag), None)
            if hit:
                return hit
    words = set(re.findall(r"[a-z0-9]{3,}", phrase)) - {"the", "my", "and", "with"}
    best, best_score = None, 0
    for item in items:
        score = len(words & set(re.findall(r"[a-z0-9]{3,}", item["title"].lower())))
        if score > best_score:
            best, best_score = item, score
    return best


def _duration(amount: str, unit: str) -> int:
    n = int(amount)
    return n * 60 if unit.startswith("h") else n


def rule_parse(text: str, items: list[dict]) -> tuple[list[dict], str]:
    ops: list[dict] = []
    replies: list[str] = []
    for clause in re.split(r"\s*(?:,|;|\band then\b|\band\b)\s*(?=(?:move|remove|skip|delete|drop|cancel|add|make|shorten)\b)",
                           text.strip(), flags=re.I):
        c = clause.strip().rstrip(".!")
        if m := re.match(rf"(?:please\s+)?(?:move|reschedule|shift|put)\s+(?:my |the )?(.+?)\s+(?:to|at)\s+(?:the\s+)?{TIME_RE}$", c, re.I):
            item, t = match_item(m.group(1), items), normalise_time(m.group(2))
            if item and t:
                ops.append({"op": "move", "item_id": item["id"], "start": t})
                replies.append(f"Moved \"{item['title']}\" to {t}.")
                continue
        if m := re.match(r"(?:please\s+)?(?:remove|skip|delete|drop|cancel)\s+(?:my |the )?(.+)$", c, re.I):
            item = match_item(m.group(1), items)
            if item:
                ops.append({"op": "remove", "item_id": item["id"]})
                replies.append(f"Removed \"{item['title']}\".")
                continue
        if m := re.match(rf"(?:please\s+)?add\s+(.+?)\s+at\s+{TIME_RE}(?:\s+for\s+(\d+)\s*(min|minutes|m|h|hours?))?$", c, re.I):
            t = normalise_time(m.group(2))
            if t:
                dur = _duration(m.group(3), m.group(4)) if m.group(3) else 30
                ops.append({"op": "add", "title": m.group(1).strip().capitalize(), "start": t, "duration_min": dur})
                replies.append(f"Added \"{m.group(1).strip()}\" at {t} for {dur} min.")
                continue
        if m := re.match(r"(?:please\s+)?(?:make|shorten|change|set)\s+(?:my |the )?(.+?)\s+(?:to\s+)?(\d+)\s*(min|minutes|m|h|hours?)(?:\s+long)?$", c, re.I):
            item = match_item(m.group(1), items)
            if item:
                dur = _duration(m.group(2), m.group(3))
                ops.append({"op": "resize", "item_id": item["id"], "duration_min": dur})
                replies.append(f"Changed \"{item['title']}\" to {dur} min.")
                continue
        replies.append(f"I couldn't understand \"{c}\". Try e.g. \"move workout to 7am\", \"skip lunch\", "
                       f"\"add call mum at 6pm for 20 min\" or \"make workout 30 min\".")
    return ops, " ".join(replies)


def parse(text: str, items: list[dict]) -> tuple[list[dict], str]:
    if llm.is_enabled():
        system = (
            "You edit a day plan. Convert the user's request into ops. Allowed ops: "
            "{\"op\":\"move\",\"item_id\":int,\"start\":\"HH:MM\"}, {\"op\":\"remove\",\"item_id\":int}, "
            "{\"op\":\"add\",\"title\":str,\"start\":\"HH:MM\",\"duration_min\":int}, "
            "{\"op\":\"resize\",\"item_id\":int,\"duration_min\":int}. Meetings cannot be moved or removed. "
            "Return JSON {\"ops\": [...], \"reply\": short friendly confirmation}."
        )
        data = llm.complete_json(system, json.dumps({"request": text, "plan_items": items}, default=str))
        if data and isinstance(data.get("ops"), list):
            return data["ops"], str(data.get("reply", "Done."))
    return rule_parse(text, items)
