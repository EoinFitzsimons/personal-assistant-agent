from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass
class Item:
    """A message (Slack/Teams) or email, normalised across providers."""

    id: str
    provider: str
    kind: str  # "message" | "email"
    text: str
    ts: datetime
    author: str
    author_is_me: bool
    channel: str = ""
    thread_id: str = ""
    link: str = ""
    subject: str = ""
    recipients: list[str] = field(default_factory=list)
    is_direct: bool = False


@dataclass
class Event:
    id: str
    provider: str
    title: str
    start: datetime
    end: datetime
    attendees: list[str] = field(default_factory=list)
    organizer: str = ""
    link: str = ""
    all_day: bool = False
    show_as: str = "busy"


@dataclass
class HealthMetric:
    provider: str
    name: str  # "sleep_hours" | "sleep_score" | "readiness" | "steps"
    value: float
    day: date


@dataclass
class SyncResult:
    items: list[Item] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)
    health: list[HealthMetric] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def extend(self, other: "SyncResult") -> None:
        self.items += other.items
        self.events += other.events
        self.health += other.health
        self.errors += other.errors


@dataclass
class TokenSet:
    access_token: str
    refresh_token: str = ""
    expires_in: int | None = None
    account_label: str = ""
    external_user_id: str = ""


@dataclass
class FetchContext:
    since: datetime  # UTC lower bound for messages
    day_start: datetime  # UTC start of the day being planned
    day_end: datetime
    today: date
    user_name: str = ""
