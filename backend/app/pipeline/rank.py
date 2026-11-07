import json
import re
from dataclasses import dataclass

from app import llm
from app.pipeline.commitments import Candidate

LONG_TASK = re.compile(r"\b(deck|report|draft|write|plan|proposal|review|analysis|write-up|spec|document)\b", re.I)


@dataclass
class RankedTask:
    candidate: Candidate
    priority: float
    duration_min: int
    reason: str


def _matches(name: str, people: list[str]) -> str:
    low = name.lower()
    return next((p for p in people if p and (p.lower() in low or low in p.lower())), "") if low else ""


def _goal_hit(text: str, goals: list[str]) -> str:
    words = set(re.findall(r"[a-z0-9]{4,}", text.lower()))
    for goal in goals:
        if words & set(re.findall(r"[a-z0-9]{4,}", goal.lower())):
            return goal
    return ""


def _rule_rank(c: Candidate, settings: dict) -> RankedTask:
    score = 50.0 if c.kind == "commitment" else 40.0
    reasons = ["you said you'd do this" if c.kind == "commitment" else "they're waiting for your reply"]
    owed = c.owed_to or ""
    vip = next((v for part in owed.split(",") if (v := _matches(part.strip(), settings.get("vip_people", [])))), "")
    if vip:
        score += 20
        reasons.append(f"{vip} is a VIP")
    vip_channel = _matches(c.channel, settings.get("vip_channels", [])) if c.channel else ""
    if vip_channel:
        score += 10
        reasons.append(f"{c.channel} is a priority channel")
    if c.due_soon:
        score += 15
        reasons.append("due soon")
    goal = _goal_hit(f"{c.title} {c.details}", settings.get("weekly_goals", []))
    if goal:
        score += 10
        reasons.append(f"supports your goal \"{goal}\"")
    score *= 0.5 + c.confidence / 2
    duration = 15 if c.kind == "follow_up" else (60 if LONG_TASK.search(c.title + " " + c.details) else 30)
    reason = reasons[0][:1].upper() + reasons[0][1:] + (": " + ", ".join(reasons[1:]) if reasons[1:] else "") + "."
    return RankedTask(c, round(min(score, 100), 1), duration, reason)


def _llm_rank(cands: list[Candidate], settings: dict) -> list[RankedTask] | None:
    if not cands or not llm.is_enabled():
        return None
    context = {k: settings.get(k) for k in ("weekly_goals", "vip_people", "vip_channels", "working_hours")}
    payload = [{"index": i, "kind": c.kind, "task": c.title, "owed_to": c.owed_to, "channel": c.channel,
                "due_soon": c.due_soon, "source_text": c.details[:400]} for i, c in enumerate(cands)]
    system = (
        "You prioritise a person's work tasks for tomorrow. Use their weekly goals, VIP people, VIP channels "
        "and deadlines. Commitments they made deserve a boost, especially to VIPs or when due soon. Return JSON "
        "{\"results\": [{\"index\": int, \"priority\": 0-100, \"duration_min\": 15|30|45|60|90, "
        "\"reason\": one short sentence addressed to the user explaining the priority}]}"
    )
    data = llm.complete_json(system, json.dumps({"user_context": context, "tasks": payload}))
    if not data or "results" not in data:
        return None
    ranked = []
    seen = set()
    for r in data["results"]:
        try:
            idx = int(r["index"])
            c = cands[idx]
        except (KeyError, ValueError, IndexError, TypeError):
            continue
        seen.add(idx)
        ranked.append(RankedTask(c, float(r.get("priority", 50)), int(r.get("duration_min", 30)),
                                 str(r.get("reason", ""))))
    ranked += [_rule_rank(c, settings) for i, c in enumerate(cands) if i not in seen]
    return ranked


def rank(cands: list[Candidate], settings: dict) -> list[RankedTask]:
    ranked = _llm_rank(cands, settings) or [_rule_rank(c, settings) for c in cands]
    return sorted(ranked, key=lambda r: r.priority, reverse=True)
