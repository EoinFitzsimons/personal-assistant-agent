import base64
from datetime import timedelta

import httpx

from app.config import get_settings
from app.connectors.base import Connector, ConnectorError
from app.connectors.types import FetchContext, HealthMetric, SyncResult, TokenSet


class _OAuthHealthConnector(Connector):
    category = "health"
    token_endpoint: str = ""
    basic_auth: bool = False

    def _creds(self) -> tuple[str, str]:
        raise NotImplementedError

    def client_id(self) -> str:
        return self._creds()[0]

    def is_configured(self) -> bool:
        return all(self._creds())

    def _token(self, data: dict) -> TokenSet:
        cid, secret = self._creds()
        headers = {}
        if self.basic_auth:
            headers["Authorization"] = "Basic " + base64.b64encode(f"{cid}:{secret}".encode()).decode()
        else:
            data = {**data, "client_id": cid, "client_secret": secret}
        resp = httpx.post(self.token_endpoint, data=data, headers=headers, timeout=30)
        if resp.status_code != 200:
            raise ConnectorError(f"{self.display_name} token request failed: {resp.text[:200]}")
        body = resp.json()
        return TokenSet(access_token=body["access_token"], refresh_token=body.get("refresh_token", ""),
                        expires_in=body.get("expires_in"), account_label=self.display_name,
                        external_user_id=str(body.get("user_id", "")))

    def exchange_code(self, code: str, redirect_uri: str) -> TokenSet:
        return self._token({"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri})

    def refresh(self, refresh_token: str) -> TokenSet:
        return self._token({"grant_type": "refresh_token", "refresh_token": refresh_token})


class FitbitConnector(_OAuthHealthConnector):
    provider = "fitbit"
    display_name = "Fitbit"
    authorize_endpoint = "https://www.fitbit.com/oauth2/authorize"
    token_endpoint = "https://api.fitbit.com/oauth2/token"
    basic_auth = True
    scopes = ["sleep", "activity", "heartrate", "profile"]

    def _creds(self) -> tuple[str, str]:
        s = get_settings()
        return s.fitbit_client_id, s.fitbit_client_secret

    def fetch(self, access_token: str, ctx: FetchContext) -> SyncResult:
        result = SyncResult()
        h = {"Authorization": f"Bearer {access_token}"}
        today, yesterday = ctx.today, ctx.today - timedelta(days=1)
        try:
            sleep = httpx.get(f"https://api.fitbit.com/1.2/user/-/sleep/date/{today}.json", headers=h, timeout=30).json()
            minutes = sleep.get("summary", {}).get("totalMinutesAsleep")
            if minutes:
                result.health.append(HealthMetric("fitbit", "sleep_hours", round(minutes / 60, 2), today))
            main = [s for s in sleep.get("sleep", []) if s.get("isMainSleep")]
            if main and main[0].get("efficiency"):
                result.health.append(HealthMetric("fitbit", "sleep_score", main[0]["efficiency"], today))
            act = httpx.get(f"https://api.fitbit.com/1/user/-/activities/date/{yesterday}.json", headers=h,
                            timeout=30).json()
            steps = act.get("summary", {}).get("steps")
            if steps is not None:
                result.health.append(HealthMetric("fitbit", "steps", steps, yesterday))
        except (httpx.HTTPError, ValueError) as exc:
            result.errors.append(f"Fitbit fetch failed: {exc}")
        return result


class OuraConnector(_OAuthHealthConnector):
    provider = "oura"
    display_name = "Oura"
    authorize_endpoint = "https://cloud.ouraring.com/oauth/authorize"
    token_endpoint = "https://api.ouraring.com/oauth/token"
    scopes = ["daily", "personal"]

    def _creds(self) -> tuple[str, str]:
        s = get_settings()
        return s.oura_client_id, s.oura_client_secret

    def fetch(self, access_token: str, ctx: FetchContext) -> SyncResult:
        result = SyncResult()
        h = {"Authorization": f"Bearer {access_token}"}
        params = {"start_date": str(ctx.today - timedelta(days=1)), "end_date": str(ctx.today)}
        base = "https://api.ouraring.com/v2/usercollection"
        try:
            for endpoint, name in (("daily_readiness", "readiness"), ("daily_sleep", "sleep_score")):
                data = httpx.get(f"{base}/{endpoint}", headers=h, params=params, timeout=30).json().get("data", [])
                if data and data[-1].get("score") is not None:
                    result.health.append(HealthMetric("oura", name, data[-1]["score"], ctx.today))
            sleeps = httpx.get(f"{base}/sleep", headers=h, params=params, timeout=30).json().get("data", [])
            if sleeps and sleeps[-1].get("total_sleep_duration"):
                result.health.append(
                    HealthMetric("oura", "sleep_hours", round(sleeps[-1]["total_sleep_duration"] / 3600, 2), ctx.today))
            activity = httpx.get(f"{base}/daily_activity", headers=h, params=params, timeout=30).json().get("data", [])
            if activity and activity[0].get("steps") is not None:
                result.health.append(HealthMetric("oura", "steps", activity[0]["steps"], ctx.today - timedelta(days=1)))
        except (httpx.HTTPError, ValueError) as exc:
            result.errors.append(f"Oura fetch failed: {exc}")
        return result
