from app.connectors.base import Connector
from app.connectors.demo import DemoConnector
from app.connectors.microsoft import MicrosoftConnector
from app.connectors.slack import SlackConnector
from app.connectors.wearables import FitbitConnector, OuraConnector

CONNECTORS: dict[str, Connector] = {
    c.provider: c
    for c in (SlackConnector(), MicrosoftConnector(), FitbitConnector(), OuraConnector())
}
DEMO = DemoConnector()


def get_connector(provider: str) -> Connector | None:
    return CONNECTORS.get(provider)
