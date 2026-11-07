from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class SignupIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    name: str = ""


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    token: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str
    name: str
    settings: dict


class PlanItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    kind: str
    title: str
    details: str
    start: datetime | None
    end: datetime | None
    duration_min: int
    priority: float
    reason: str
    source_provider: str
    source_link: str
    owed_to: str
    confidence: float
    status: str
    fixed: bool
    tag: str


class ChatMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    role: str
    content: str
    created_at: datetime


class PlanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    date: date
    status: str
    error: str
    summary: dict
    items: list[PlanItemOut]
    messages: list[ChatMessageOut]


class ItemPatch(BaseModel):
    status: str | None = Field(default=None, pattern="^(proposed|approved|removed)$")
    start: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    duration_min: int | None = Field(default=None, ge=5, le=480)


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


class ChatOut(BaseModel):
    reply: str
    plan: PlanOut
