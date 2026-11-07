import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import llm
from app.config import get_settings
from app.db import init_db
from app.routers import auth, connections, plans, settings

logging.basicConfig(level=logging.INFO)



@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="Personal Assistant Agent", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[get_settings().frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
for r in (auth.router, settings.router, connections.router, plans.router):
    app.include_router(r)


@app.get("/health")
def health():
    return {"ok": True, "llm": llm.is_enabled()}
