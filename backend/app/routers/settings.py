import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import DEFAULT_SETTINGS, User
from app.security import current_user

router = APIRouter(tags=["settings"])
HHMM = r"^\d{2}:\d{2}$"


class WorkingHours(BaseModel):
    start: str = Field(pattern=HHMM)
    end: str = Field(pattern=HHMM)


class Workout(BaseModel):
    preferred_time: str = Field(pattern="^(morning|midday|evening)$")
    duration_min: int = Field(ge=10, le=180)
    types: list[str]


class Diet(BaseModel):
    preferences: list[str] = []
    avoid: list[str] = []


class Meals(BaseModel):
    breakfast: str = Field(pattern=HHMM)
    lunch: str = Field(pattern=HHMM)
    dinner: str = Field(pattern=HHMM)


class SettingsIn(BaseModel):
    name: str | None = None
    timezone: str
    working_hours: WorkingHours
    weekly_goals: list[str]
    vip_people: list[str]
    vip_channels: list[str]
    workout: Workout
    diet: Diet
    meals: Meals
    health_consent: bool
    demo_mode: bool


@router.get("/settings")
def get_settings_(user: User = Depends(current_user)):
    return {**DEFAULT_SETTINGS, **user.settings, "name": user.name}


@router.put("/settings")
def put_settings(body: SettingsIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    try:
        ZoneInfo(body.timezone)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise HTTPException(422, "Unknown timezone") from exc
    if body.working_hours.start >= body.working_hours.end:
        raise HTTPException(422, "Working hours must start before they end")
    data = body.model_dump(exclude={"name"})
    for key in ("weekly_goals", "vip_people", "vip_channels"):
        data[key] = [re.sub(r"\s+", " ", v).strip() for v in data[key] if v.strip()]
    if body.name is not None:
        user.name = body.name.strip()
    user.settings = data
    db.commit()
    return {**data, "name": user.name}
