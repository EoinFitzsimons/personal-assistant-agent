"""Realistic sample data so the whole flow works before any OAuth app is registered."""

from datetime import datetime, time, timedelta

from app.connectors.base import Connector
from app.connectors.types import Event, FetchContext, HealthMetric, Item, SyncResult, TokenSet


class DemoConnector(Connector):
    provider = "demo"
    display_name = "Demo data"
    category = "work"

    def exchange_code(self, code: str, redirect_uri: str) -> TokenSet:
        return TokenSet(access_token="demo")

    def fetch(self, access_token: str, ctx: FetchContext) -> SyncResult:
        tz = ctx.day_start.tzinfo
        me = ctx.user_name or "Me"
        tomorrow = ctx.day_start.astimezone(tz).date() if tz else ctx.day_start.date()

        def ago(hours: float) -> datetime:
            return ctx.day_start - timedelta(hours=hours)

        def at(h: int, m: int = 0) -> datetime:
            local_tz = ctx.day_start.tzinfo
            return datetime.combine(tomorrow, time(h, m), tzinfo=local_tz)

        items = [
            # Commitment owed to a likely VIP, due tomorrow
            Item("s1", "slack", "message", "Can you send me the Q3 metrics deck before the leadership sync tomorrow?",
                 ago(20), "Sarah Chen", False, "#leadership", "t-q3", "https://slack.com/demo/t-q3"),
            Item("s2", "slack", "message", "Sure, will do — I'll send the Q3 metrics deck by tomorrow noon.",
                 ago(19.5), me, True, "#leadership", "t-q3", "https://slack.com/demo/t-q3"),
            # Commitment already completed later in the thread -> must be dropped
            Item("s3", "slack", "message", "Could you review my PR for the billing service?",
                 ago(30), "Tom Walsh", False, "#eng-billing", "t-pr", "https://slack.com/demo/t-pr"),
            Item("s4", "slack", "message", "I'll review it this afternoon.",
                 ago(29), me, True, "#eng-billing", "t-pr", "https://slack.com/demo/t-pr"),
            Item("s5", "slack", "message", "Done, approved with two small comments.",
                 ago(26), me, True, "#eng-billing", "t-pr", "https://slack.com/demo/t-pr"),
            # Noise: contains "will" but not a commitment
            Item("s6", "slack", "message", "Heads up, it will be raining all day tomorrow so the offsite moves indoors.",
                 ago(10), me, True, "#random", "t-rain", "https://slack.com/demo/t-rain"),
            # Weak / ambiguous commitment -> inbox
            Item("s7", "slack", "message", "Yeah that will probably need a proper write-up at some point.",
                 ago(8), me, True, "#product", "t-writeup", "https://slack.com/demo/t-writeup"),
            # Teams commitment
            Item("m1", "teams", "message", "Are we OK to share the vendor contract with the client?",
                 ago(16), "Priya Nair", False, "Contract review", "c-legal", "https://teams.microsoft.com/demo/c-legal",
                 is_direct=True),
            Item("m2", "teams", "message", "Let me check with legal and get back to you tomorrow.",
                 ago(15.5), me, True, "Contract review", "c-legal", "https://teams.microsoft.com/demo/c-legal",
                 is_direct=True),
            # Incoming email waiting for a reply -> follow-up expected
            Item("e1", "outlook", "email",
                 "Hi, could you confirm the go-live date for the onboarding flow? We need it for our comms plan.",
                 ago(22), "Mark Rivera (Acme Corp)", False, "Inbox", "conv-golive", "https://outlook.office.com/demo/golive",
                 subject="Go-live date for onboarding flow", is_direct=True),
            # Incoming email already answered -> no follow-up
            Item("e2", "outlook", "email", "Can you share the updated roadmap?",
                 ago(40), "Lena Fischer", False, "Inbox", "conv-roadmap", "https://outlook.office.com/demo/roadmap",
                 subject="Roadmap", is_direct=True),
            Item("e3", "outlook", "email", "Here it is — attached the updated roadmap.",
                 ago(38), me, True, "Sent Items", "conv-roadmap", "https://outlook.office.com/demo/roadmap",
                 subject="RE: Roadmap"),
            # Sent email commitment
            Item("e4", "outlook", "email", "Thanks for the session. I will draft the hiring plan for the platform team and circulate it.",
                 ago(12), me, True, "Sent Items", "conv-hiring", "https://outlook.office.com/demo/hiring",
                 subject="Platform team hiring", recipients=["Sarah Chen"]),
        ]
        events = [
            Event("ev1", "outlook", "Team stand-up", at(9, 30), at(9, 45), ["Team"]),
            Event("ev2", "outlook", "1:1 with Sarah", at(11, 0), at(11, 30), ["Sarah Chen"]),
            Event("ev3", "outlook", "Leadership sync", at(14, 0), at(15, 0), ["Sarah Chen", "Leadership"]),
            Event("ev4", "teams", "Design review: onboarding flow", at(16, 0), at(16, 45), ["Design"]),
        ]
        health = [
            HealthMetric("demo", "sleep_hours", 6.1, ctx.today),
            HealthMetric("demo", "readiness", 62, ctx.today),
            HealthMetric("demo", "steps", 4200, ctx.today - timedelta(days=1)),
        ]
        return SyncResult(items=items, events=events, health=health)
