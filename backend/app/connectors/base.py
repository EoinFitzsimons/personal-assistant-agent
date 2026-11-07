from abc import ABC, abstractmethod
from urllib.parse import urlencode

from app.connectors.types import FetchContext, SyncResult, TokenSet


class ConnectorError(Exception):
    pass


class Connector(ABC):
    provider: str
    display_name: str
    category: str  # "work" | "health"
    authorize_endpoint: str = ""
    scopes: list[str] = []

    def is_configured(self) -> bool:
        return True

    def authorize_url(self, state: str, redirect_uri: str) -> str:
        params = {
            "client_id": self.client_id(),
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "scope": " ".join(self.scopes),
            "state": state,
        }
        return f"{self.authorize_endpoint}?{urlencode(params)}"

    def client_id(self) -> str:
        return ""

    @abstractmethod
    def exchange_code(self, code: str, redirect_uri: str) -> TokenSet: ...

    def refresh(self, refresh_token: str) -> TokenSet:
        raise ConnectorError(f"{self.display_name} does not support token refresh")

    @abstractmethod
    def fetch(self, access_token: str, ctx: FetchContext) -> SyncResult: ...
