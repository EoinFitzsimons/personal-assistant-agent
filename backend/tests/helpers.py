from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.connectors.demo import DemoConnector
from app.connectors.types import FetchContext

TZ = ZoneInfo("Europe/Dublin")
DAY = date(2026, 11, 9)


def demo_data():
    start = datetime.combine(DAY, time(0), tzinfo=TZ)
    ctx = FetchContext(since=start - timedelta(hours=48), day_start=start, day_end=start + timedelta(days=1),
                       today=DAY - timedelta(days=1), user_name="Anastasiia")
    return DemoConnector().fetch("demo", ctx)
