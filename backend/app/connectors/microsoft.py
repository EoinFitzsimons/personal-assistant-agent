"""Outlook mail + calendar and Teams chat via Microsoft Graph (read-only)."""

import re
from datetime import datetime, timezone

import httpx
from dateutil import parser as dtparser

from app.config import get_settings
from app.connectors.base import Connector, ConnectorError
from app.connectors.types import Event, FetchContext, Item, SyncResult, TokenSet

GRAPH = "https://graph.microsoft.com/v1.0"
MAX_CHATS = 30


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _strip_html(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html or "")).strip()


class MicrosoftConnector(Connector):
    provider = "microsoft"
    display_name = "Outlook & Teams"
    category = "work"
    scopes = ["offline_access", "User.Read", "Mail.Read", "Calendars.Read", "Chat.Read"]

    @property
    def authorize_endpoint(self) -> str:  # type: ignore[override]
        return f"https://login.microsoftonline.com/{get_settings().microsoft_tenant}/oauth2/v2.0/authorize"

    @property
    def _token_endpoint(self) -> str:
        return f"https://login.microsoftonline.com/{get_settings().microsoft_tenant}/oauth2/v2.0/token"

    def is_configured(self) -> bool:
        s = get_settings()
        return bool(s.microsoft_client_id and s.microsoft_client_secret)

    def client_id(self) -> str:
        return get_settings().microsoft_client_id

    def _token(self, data: dict) -> TokenSet:
        s = get_settings()
        resp = httpx.post(self._token_endpoint, data={
            "client_id": s.microsoft_client_id, "client_secret": s.microsoft_client_secret,
            "scope": " ".join(self.scopes), **data,
        }, timeout=30)
        body = resp.json()
        if resp.status_code != 200:
            desc = body.get("error_description", body.get("error", "unknown error"))
            if "AADSTS65001" in desc or "admin" in desc.lower():
                desc = "Your organisation requires an IT admin to approve this app. " + desc
            raise ConnectorError(f"Microsoft sign-in failed: {desc}")
        return TokenSet(access_token=body["access_token"], refresh_token=body.get("refresh_token", ""),
                        expires_in=body.get("expires_in"))

    def exchange_code(self, code: str, redirect_uri: str) -> TokenSet:
        tokens = self._token({"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri})
        me = httpx.get(f"{GRAPH}/me", headers={"Authorization": f"Bearer {tokens.access_token}"}, timeout=30).json()
        tokens.account_label = me.get("mail") or me.get("userPrincipalName") or "Microsoft"
        tokens.external_user_id = me.get("id", "")
        return tokens

    def refresh(self, refresh_token: str) -> TokenSet:
        return self._token({"grant_type": "refresh_token", "refresh_token": refresh_token})

    def fetch(self, access_token: str, ctx: FetchContext) -> SyncResult:
        result = SyncResult()
        headers = {"Authorization": f"Bearer {access_token}", "Prefer": 'outlook.timezone="UTC"'}
        with httpx.Client(headers=headers, timeout=30) as client:

            def get(url: str, **params) -> dict:
                resp = client.get(url if url.startswith("http") else f"{GRAPH}{url}", params=params or None)
                if resp.status_code >= 400:
                    raise ConnectorError(f"Graph {url} failed ({resp.status_code}): {resp.text[:200]}")
                return resp.json()

            me = get("/me")
            my_id = me.get("id", "")
            my_addr = (me.get("mail") or me.get("userPrincipalName") or "").lower()
            select = "id,subject,bodyPreview,from,toRecipients,conversationId,webLink"

            for folder, field, mine in (("inbox", "receivedDateTime", False), ("sentitems", "sentDateTime", True)):
                try:
                    data = get(f"/me/mailFolders/{folder}/messages", **{
                        "$filter": f"{field} ge {_iso(ctx.since)}", "$select": f"{select},{field}",
                        "$top": "100", "$orderby": f"{field} desc"})
                except ConnectorError as exc:
                    result.errors.append(str(exc))
                    continue
                for m in data.get("value", []):
                    sender = (m.get("from") or {}).get("emailAddress", {})
                    recipients = [r["emailAddress"].get("name") or r["emailAddress"].get("address", "")
                                  for r in m.get("toRecipients", [])]
                    result.items.append(Item(
                        id=m["id"], provider="outlook", kind="email", text=m.get("bodyPreview", ""),
                        ts=dtparser.isoparse(m[field]), author=sender.get("name") or sender.get("address", ""),
                        author_is_me=mine or sender.get("address", "").lower() == my_addr,
                        channel="Sent Items" if mine else "Inbox", thread_id=m.get("conversationId", m["id"]),
                        link=m.get("webLink", ""), subject=m.get("subject", ""), recipients=recipients,
                        is_direct=not mine,
                    ))

            try:
                cal = get("/me/calendarView", startDateTime=_iso(ctx.day_start), endDateTime=_iso(ctx.day_end),
                          **{"$select": "id,subject,start,end,attendees,organizer,webLink,isAllDay,showAs,isCancelled",
                             "$top": "100"})
                for ev in cal.get("value", []):
                    if ev.get("isCancelled") or ev.get("showAs") == "free":
                        continue
                    result.events.append(Event(
                        id=ev["id"], provider="outlook", title=ev.get("subject") or "(no title)",
                        start=dtparser.isoparse(ev["start"]["dateTime"] + "Z"),
                        end=dtparser.isoparse(ev["end"]["dateTime"] + "Z"),
                        attendees=[a["emailAddress"].get("name", "") for a in ev.get("attendees", [])],
                        organizer=(ev.get("organizer") or {}).get("emailAddress", {}).get("name", ""),
                        link=ev.get("webLink", ""), all_day=ev.get("isAllDay", False), show_as=ev.get("showAs", "busy"),
                    ))
            except ConnectorError as exc:
                result.errors.append(str(exc))

            try:
                chats = get("/me/chats", **{"$top": str(MAX_CHATS)}).get("value", [])
            except ConnectorError as exc:
                result.errors.append(str(exc))
                chats = []
            for chat in chats[:MAX_CHATS]:
                try:
                    msgs = get(f"/chats/{chat['id']}/messages", **{"$top": "50"}).get("value", [])
                except ConnectorError as exc:
                    result.errors.append(str(exc))
                    continue
                for m in msgs:
                    if m.get("messageType") != "message" or not m.get("createdDateTime"):
                        continue
                    ts = dtparser.isoparse(m["createdDateTime"])
                    if ts < ctx.since:
                        continue
                    sender = ((m.get("from") or {}).get("user") or {})
                    result.items.append(Item(
                        id=m["id"], provider="teams", kind="message",
                        text=_strip_html((m.get("body") or {}).get("content", "")), ts=ts,
                        author=sender.get("displayName", "unknown"), author_is_me=sender.get("id") == my_id,
                        channel=chat.get("topic") or "Teams chat", thread_id=f"chat:{chat['id']}",
                        link=m.get("webUrl", ""), is_direct=chat.get("chatType") == "oneOnOne",
                    ))
        return result
