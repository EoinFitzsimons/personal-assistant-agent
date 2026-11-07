from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import get_settings
from app.connectors.base import ConnectorError
from app.connectors.registry import CONNECTORS, get_connector
from app.db import get_db
from app.models import Connection, User
from app.security import create_token, current_user, decode_token, encrypt

router = APIRouter(tags=["connections"])


def _redirect_uri(provider: str) -> str:
    return f"{get_settings().backend_url}/connections/{provider}/callback"


@router.get("/connections")
def list_connections(user: User = Depends(current_user)):
    connected = {c.provider: c for c in user.connections}
    return [
        {
            "provider": p, "name": c.display_name, "category": c.category, "configured": c.is_configured(),
            "connected": p in connected, "account": connected[p].account_label if p in connected else "",
        }
        for p, c in CONNECTORS.items()
    ]


@router.get("/connections/{provider}/authorize")
def authorize(provider: str, user: User = Depends(current_user)):
    connector = get_connector(provider)
    if connector is None:
        raise HTTPException(404, "Unknown provider")
    if not connector.is_configured():
        raise HTTPException(400, f"{connector.display_name} isn't configured on the server yet (missing OAuth app credentials).")
    state = create_token(user.id, purpose="oauth", ttl=timedelta(minutes=10), extra={"provider": provider})
    return {"url": connector.authorize_url(state, _redirect_uri(provider))}


@router.get("/connections/{provider}/callback")
def callback(provider: str, code: str = "", state: str = "", error: str = ""):
    """Hands the code to the web app, which completes the flow with the signed-in user's token.

    Completing here would let an attacker's authorize URL attach a victim's account to the attacker's user.
    """
    front = get_settings().frontend_url
    if get_connector(provider) is None:
        raise HTTPException(404, "Unknown provider")
    if error or not code:
        return RedirectResponse(f"{front}/settings?{urlencode({'error': error or 'cancelled', 'provider': provider})}")
    return RedirectResponse(f"{front}/settings?{urlencode({'provider': provider, 'code': code, 'state': state})}")


class CompleteIn(BaseModel):
    code: str
    state: str


@router.post("/connections/{provider}/complete")
def complete(provider: str, body: CompleteIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    connector = get_connector(provider)
    if connector is None:
        raise HTTPException(404, "Unknown provider")
    payload = decode_token(body.state, purpose="oauth")
    if payload.get("provider") != provider or payload.get("sub") != str(user.id):
        raise HTTPException(400, "This connection was started by a different account")
    try:
        tokens = connector.exchange_code(body.code, _redirect_uri(provider))
    except ConnectorError as exc:
        raise HTTPException(400, str(exc)[:300]) from exc
    conn = next((c for c in user.connections if c.provider == provider), None) or Connection(user_id=user.id,
                                                                                            provider=provider)
    conn.access_token_enc = encrypt(tokens.access_token)
    conn.refresh_token_enc = encrypt(tokens.refresh_token)
    conn.expires_at = datetime.now(timezone.utc) + timedelta(seconds=tokens.expires_in) if tokens.expires_in else None
    conn.account_label = tokens.account_label
    conn.external_user_id = tokens.external_user_id
    db.add(conn)
    settings = dict(user.settings)
    settings["demo_mode"] = False
    user.settings = settings
    db.commit()
    return {"connected": provider}


@router.delete("/connections/{provider}", status_code=204)
def disconnect(provider: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    for conn in list(user.connections):
        if conn.provider == provider:
            db.delete(conn)
    db.commit()
