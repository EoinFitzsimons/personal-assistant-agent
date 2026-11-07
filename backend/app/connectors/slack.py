from datetime import datetime, timezone

import httpx

from app.config import get_settings
from app.connectors.base import Connector, ConnectorError
from app.connectors.types import FetchContext, Item, SyncResult, TokenSet

API = "https://slack.com/api"
MAX_CONVERSATIONS = 60
MAX_THREADS = 40


class SlackConnector(Connector):
    provider = "slack"
    display_name = "Slack"
    category = "work"
    authorize_endpoint = "https://slack.com/oauth/v2/authorize"
    scopes = ["channels:history", "groups:history", "im:history", "mpim:history", "channels:read",
              "groups:read", "im:read", "mpim:read", "users:read"]

    def is_configured(self) -> bool:
        s = get_settings()
        return bool(s.slack_client_id and s.slack_client_secret)

    def client_id(self) -> str:
        return get_settings().slack_client_id

    def authorize_url(self, state: str, redirect_uri: str) -> str:
        from urllib.parse import urlencode

        params = {"client_id": self.client_id(), "user_scope": ",".join(self.scopes),
                  "redirect_uri": redirect_uri, "state": state}
        return f"{self.authorize_endpoint}?{urlencode(params)}"

    def exchange_code(self, code: str, redirect_uri: str) -> TokenSet:
        s = get_settings()
        data = httpx.post(f"{API}/oauth.v2.access", data={
            "client_id": s.slack_client_id, "client_secret": s.slack_client_secret,
            "code": code, "redirect_uri": redirect_uri,
        }, timeout=30).json()
        if not data.get("ok"):
            raise ConnectorError(f"Slack OAuth failed: {data.get('error')}")
        user = data["authed_user"]
        return TokenSet(access_token=user["access_token"], refresh_token=user.get("refresh_token", ""),
                        expires_in=user.get("expires_in"), account_label=data.get("team", {}).get("name", "Slack"),
                        external_user_id=user["id"])

    def _call(self, client: httpx.Client, method: str, **params) -> dict:
        data = client.get(f"{API}/{method}", params=params).json()
        if not data.get("ok"):
            raise ConnectorError(f"Slack {method} failed: {data.get('error')}")
        return data

    def fetch(self, access_token: str, ctx: FetchContext) -> SyncResult:
        result = SyncResult()
        oldest = f"{ctx.since.timestamp():.6f}"
        with httpx.Client(headers={"Authorization": f"Bearer {access_token}"}, timeout=30) as client:
            auth = self._call(client, "auth.test")
            me, team_url = auth["user_id"], auth["url"].rstrip("/")
            names: dict[str, str] = {}

            def name_of(uid: str) -> str:
                if uid not in names:
                    try:
                        u = self._call(client, "users.info", user=uid)["user"]
                        names[uid] = u.get("real_name") or u.get("name") or uid
                    except ConnectorError:
                        names[uid] = uid
                return names[uid]

            convs = self._call(client, "users.conversations", types="public_channel,private_channel,mpim,im",
                               exclude_archived="true", limit=200).get("channels", [])
            threads_fetched = 0
            for conv in convs[:MAX_CONVERSATIONS]:
                cid = conv["id"]
                is_im = bool(conv.get("is_im"))
                label = f"DM with {name_of(conv['user'])}" if is_im else f"#{conv.get('name', cid)}"
                try:
                    history = self._call(client, "conversations.history", channel=cid, oldest=oldest, limit=200)
                except ConnectorError as exc:
                    result.errors.append(str(exc))
                    continue
                messages = list(history.get("messages", []))
                for msg in list(messages):
                    if msg.get("reply_count") and threads_fetched < MAX_THREADS:
                        threads_fetched += 1
                        replies = self._call(client, "conversations.replies", channel=cid, ts=msg["ts"], oldest=oldest)
                        messages += [r for r in replies.get("messages", [])[1:]]
                for msg in messages:
                    if msg.get("subtype") or not msg.get("text"):
                        continue
                    uid = msg.get("user", "")
                    thread = msg.get("thread_ts") or (cid if is_im else msg["ts"])
                    result.items.append(Item(
                        id=f"{cid}:{msg['ts']}", provider="slack", kind="message", text=msg["text"],
                        ts=datetime.fromtimestamp(float(msg["ts"]), tz=timezone.utc),
                        author=name_of(uid) if uid else "unknown", author_is_me=uid == me,
                        channel=label, thread_id=f"{cid}:{thread}", is_direct=is_im or f"<@{me}>" in msg["text"],
                        link=f"{team_url}/archives/{cid}/p{msg['ts'].replace('.', '')}",
                    ))
        return result
