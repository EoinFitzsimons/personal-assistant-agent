"""Detect promises the user made ("I'll…", "will do") and incoming requests that still
need a reply. Keyword prefilter first; then the LLM (or rules) confirms and extracts."""

import json
import re
from dataclasses import dataclass, field
from datetime import datetime

from app import llm
from app.connectors.types import Item

STRONG_PATTERN = re.compile(
    r"\b(will do|i'll|i will|i’ll|let me|on it|i can do that|i'm going to|i’m going to|i'll get|will send|"
    r"will share|will follow up|will get back)\b",
    re.I,
)
WEAK_PATTERN = re.compile(r"\bwill\b", re.I)
SELF_SUBJECT_WILL = re.compile(r"\b(i|we)\b[^.?!]{0,30}\bwill\b", re.I)
VAGUE_ACTION_WILL = re.compile(
    r"\b(that|this|it)\s+will\b[^.?!]{0,30}\b(need|do|write|send|follow|fix|look|sort|handle|prepare)", re.I
)
DONE_PATTERN = re.compile(r"\b(done|sent|shared|merged|approved|finished|completed|here it is|attached)\b", re.I)
REQUEST_PATTERN = re.compile(
    r"(\?|\b(can you|could you|would you|please|any update|let me know|can we|are we ok|need you to)\b)", re.I
)
DUE_SOON_PATTERN = re.compile(r"\b(tomorrow|today|tonight|eod|end of day|asap|this afternoon|by noon|first thing)\b", re.I)
LEADING_FILLER = re.compile(r"^(sure|yes|yeah|yep|ok|okay|sounds good|thanks[^,.—-]*|no problem)[,.!—\- ]+", re.I)

INBOX_THRESHOLD = 0.6


@dataclass
class Candidate:
    kind: str  # "commitment" | "follow_up"
    title: str
    details: str
    source_provider: str
    source_link: str
    owed_to: str
    due_soon: bool
    confidence: float
    channel: str = ""
    ts: datetime | None = None
    item_ids: list[str] = field(default_factory=list)


def _threads(items: list[Item]) -> dict[str, list[Item]]:
    threads: dict[str, list[Item]] = {}
    for item in sorted(items, key=lambda i: i.ts):
        threads.setdefault(item.thread_id or item.id, []).append(item)
    return threads


def prefilter_commitments(items: list[Item]) -> list[Item]:
    return [i for i in items if i.author_is_me and (STRONG_PATTERN.search(i.text) or WEAK_PATTERN.search(i.text))]


def _completed_later(item: Item, thread: list[Item]) -> bool:
    return any(o.author_is_me and o.ts > item.ts and DONE_PATTERN.search(o.text) for o in thread if o is not item)


def _replied_later(item: Item, thread: list[Item]) -> bool:
    return any(o.author_is_me and o.ts > item.ts for o in thread)


def _previous_from_other(item: Item, thread: list[Item]) -> Item | None:
    earlier = [o for o in thread if o.ts < item.ts and not o.author_is_me]
    return earlier[-1] if earlier else None


def _clean_task(text: str) -> str:
    text = LEADING_FILLER.sub("", text.strip())
    text = re.sub(r"^will do\b[\s—\-,.!]*", "", text, flags=re.I)
    m = re.search(r"\b(?:i'll|i’ll|i will|will|let me|i'm going to|i’m going to)\s+(.*)", text, re.I)
    task = m.group(1) if m else text
    task = re.split(r"(?<=[.!?])\s", task)[0].rstrip(".! ")
    return task[:1].upper() + task[1:] if task else ""


def _rule_commitment(item: Item, thread: list[Item]) -> Candidate | None:
    if STRONG_PATTERN.search(item.text):
        confidence = 0.85
    elif SELF_SUBJECT_WILL.search(item.text):
        confidence = 0.5
    elif VAGUE_ACTION_WILL.search(item.text):
        confidence = 0.35  # "that will need a write-up": maybe a commitment, let the user decide
    else:
        confidence = 0.2  # "it will rain": not a commitment
    prev = _previous_from_other(item, thread)
    task = _clean_task(item.text)
    if len(task.split()) < 3 and prev:
        task = f"Follow through on: {prev.text[:90]}"
    owed_to = prev.author if prev else ", ".join(item.recipients)
    if confidence < 0.3:
        return None
    return Candidate(
        kind="commitment", title=task or item.text[:90], details=item.text, source_provider=item.provider,
        source_link=item.link, owed_to=owed_to, due_soon=bool(DUE_SOON_PATTERN.search(item.text)),
        confidence=confidence, channel=item.channel, ts=item.ts, item_ids=[item.id],
    )


def _follow_up_candidates(items: list[Item], threads: dict[str, list[Item]]) -> list[Candidate]:
    out = []
    for item in items:
        if item.author_is_me or not item.is_direct or not REQUEST_PATTERN.search(item.text):
            continue
        thread = threads.get(item.thread_id or item.id, [])
        if _replied_later(item, thread):
            continue
        subject = f" — {item.subject}" if item.subject else ""
        out.append(Candidate(
            kind="follow_up", title=f"Reply to {item.author}{subject}", details=item.text,
            source_provider=item.provider, source_link=item.link, owed_to=item.author,
            due_soon=bool(DUE_SOON_PATTERN.search(item.text)), confidence=0.75, channel=item.channel,
            ts=item.ts, item_ids=[item.id],
        ))
    return out


def _llm_confirm(pre: list[Item], threads: dict[str, list[Item]], user_name: str) -> list[Candidate] | None:
    if not pre or not llm.is_enabled():
        return None
    payload = []
    for idx, item in enumerate(pre):
        thread = threads.get(item.thread_id or item.id, [])
        payload.append({
            "index": idx,
            "message": item.text,
            "channel": item.channel,
            "recipients": item.recipients,
            "thread": [{"author": "ME" if t.author_is_me else t.author, "text": t.text[:500],
                        "after_message": t.ts > item.ts} for t in thread[-12:]],
        })
    system = (
        "You detect commitments a user made in their own work messages. For each message decide whether "
        "the user (ME) promised to do something. Ignore statements like 'it will rain'. If a later ME message "
        "in the thread shows it was already done, mark already_done=true. Return JSON: {\"results\": [{\"index\": int, "
        "\"is_commitment\": bool, \"task\": short imperative task, \"owed_to\": person or \"\", \"due_soon\": bool "
        "(due today/tomorrow), \"already_done\": bool, \"confidence\": 0-1}]}"
    )
    data = llm.complete_json(system, f"User name: {user_name}\n" + json.dumps(payload, default=str))
    if not data or "results" not in data:
        return None
    out = []
    for r in data["results"]:
        try:
            item = pre[int(r["index"])]
        except (KeyError, ValueError, IndexError, TypeError):
            continue
        if not r.get("is_commitment") or r.get("already_done"):
            continue
        try:
            confidence = min(max(float(r.get("confidence", 0.7)), 0.0), 1.0)
        except (TypeError, ValueError):
            confidence = 0.7
        out.append(Candidate(
            kind="commitment", title=r.get("task") or _clean_task(item.text), details=item.text,
            source_provider=item.provider, source_link=item.link, owed_to=r.get("owed_to", ""),
            due_soon=bool(r.get("due_soon")), confidence=confidence, channel=item.channel,
            ts=item.ts, item_ids=[item.id],
        ))
    return out


def detect(items: list[Item], user_name: str = "") -> list[Candidate]:
    threads = _threads(items)
    pre = [i for i in prefilter_commitments(items) if not _completed_later(i, threads.get(i.thread_id or i.id, []))]
    commitments = _llm_confirm(pre, threads, user_name)
    if commitments is None:
        commitments = [c for i in pre if (c := _rule_commitment(i, threads.get(i.thread_id or i.id, [])))]
    follow_ups = _follow_up_candidates(items, threads)
    # A request the user already promised to handle is represented by the commitment.
    committed_threads = {next((i.thread_id for i in items if i.id in c.item_ids), "") for c in commitments}
    follow_ups = [f for f in follow_ups
                  if next((i.thread_id for i in items if i.id in f.item_ids), "") not in committed_threads]
    return commitments + follow_ups
