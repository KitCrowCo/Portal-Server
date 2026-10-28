"""
notify.py — Push Notification Service
═══════════════════════════════════════════════════════════════════════════════
Handles web push (VAPID) and in-server WebSocket notification delivery.

VAPID keys must be set as environment variables:
    VAPID_PRIVATE_KEY   base64url-encoded private key
    VAPID_PUBLIC_KEY    base64url-encoded public key
    VAPID_CLAIMS_SUB    mailto: or https: URI identifying the sender

Run setup_vapid.sh once to generate keys and write them to .env.
PushSubscription rows are owned by username. One user may have multiple subscriptions (phone, laptop, etc.). Dead endpoints (404/410) are pruned on each send rather than on a schedule — cheap and avoids a separate job.
WebSocket delivery runs alongside push. If the user is currently connected via WS the notification appears instantly without the OS push channel.
Routes registered here are included by main.py via notify_router.
═══════════════════════════════════════════════════════════════════════════════
"""

import json
import os
import logging
from typing import Optional
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import Column, Integer, String, JSON, Text
from sqlalchemy.orm import Session
from .database import Base, engine, get_db, SessionLocal
from .auth import get_current_user
from pywebpush import webpush, WebPushException
from .ws_manager import manager as _ws_manager

logger = logging.getLogger("notify")

# --- Config ---

VAPID_PRIVATE = os.getenv("VAPID_PRIVATE_KEY", "")
VAPID_PUBLIC  = os.getenv("VAPID_PUBLIC_KEY", "")
VAPID_CLAIMS  = {"sub": os.getenv("VAPID_CLAIMS_SUB", "mailto:admin@localhost")}
PUSH_ENABLED  = bool(VAPID_PRIVATE and VAPID_PUBLIC)

# --- Model ---

class PushSubscription(Base):
    """One row per browser push subscription endpoint. A user may have several."""
    __tablename__ = "push_subscriptions"
    id       = Column(Integer, primary_key=True, index=True)
    username = Column(String, index=True, nullable=False)
    endpoint = Column(Text, unique=True, nullable=False)
    keys     = Column(JSON, nullable=False, default=dict)

# Ensure table exists (same pattern as ensure_db_column in database.py)
Base.metadata.create_all(bind=engine, tables=[PushSubscription.__table__], checkfirst=True)

# --- Core send functions ---

def _try_push(sub: PushSubscription, title: str, body: str, url: str = "/") -> bool:
    """Attempt one push. Returns True if the subscription is dead and should be pruned. Swallows all errors except 404/410 which signal a dead endpoint."""
    if not PUSH_ENABLED: return False
    try:
        webpush(subscription_info={"endpoint": sub.endpoint, "keys": sub.keys}, data=json.dumps({"title": title, "body": body, "icon": "/static/icon-512.png", "url": url}), vapid_private_key=VAPID_PRIVATE, vapid_claims=VAPID_CLAIMS)
        return False
    except Exception as e:
        # pywebpush not installed, or network error — don't prune
        try:
            if isinstance(e, WebPushException) and e.response and e.response.status_code in (404, 410): return True  # dead endpoint — prune it
        except ImportError:
            pass
        logger.debug("Push send error for %s: %s", sub.endpoint[:40], e)
        return False

async def send_push(username: str, title: str, body: str, url: str = "/") -> int:
    """Send push to all subscriptions for username. Prunes dead endpoints.
    Opens its own DB session - never accepts a caller's, since a module's injected
    `db` dependency may be bound to that module's own separate database engine."""
    if _ws_manager:
        try: await _ws_manager.send_personal_message({"type": "notification", "title": title, "body": body, "url": url}, username)
        except Exception as e: logger.debug("WS notify error for %s: %s", username, e)
    if not PUSH_ENABLED: return 0
    db = SessionLocal()
    try:
        subs = db.query(PushSubscription).filter(PushSubscription.username == username).all()
        if not subs: return 0
        dead = [s for s in subs if _try_push(s, title, body, url)]
        for s in dead: db.delete(s)
        if dead: db.commit()
        return len(subs) - len(dead)
    finally: db.close()

async def broadcast_push(title: str, body: str, url: str = "/", role_filter: Optional[str] = None) -> int:
    if _ws_manager:
        try: await _ws_manager.broadcast({"type": "notification", "title": title, "body": body, "url": url})
        except Exception as e: logger.debug("WS broadcast error: %s", e)
    if not PUSH_ENABLED: return 0
    db = SessionLocal()
    try:
        if role_filter:
            from .models import User as _User
            usernames = {u.username for u in db.query(_User).filter(_User.role == role_filter).all()}
            subs = db.query(PushSubscription).filter(PushSubscription.username.in_(usernames)).all()
        else:
            subs = db.query(PushSubscription).all()
        if not subs: return 0
        dead = [s for s in subs if _try_push(s, title, body, url)]
        for s in dead: db.delete(s)
        if dead: db.commit()
        return len(subs) - len(dead)
    finally: db.close()

# --- Router ---

router = APIRouter(tags=["notifications"])

@router.get("/vapid_public_key")
async def vapid_key(): return JSONResponse({"key": VAPID_PUBLIC, "enabled": PUSH_ENABLED}) #Returns the VAPID public key for the browser to register a push subscription.

@router.post("/push/subscribe", response_class=HTMLResponse)
async def push_subscribe(request: Request, db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Register a browser push subscription endpoint for the current user."""
    try: body = await request.json()
    except Exception: return HTMLResponse("Invalid JSON", status_code=400)
    endpoint = body.get("endpoint", "").strip()
    if not endpoint: return HTMLResponse("Missing endpoint", status_code=400)
    existing = db.query(PushSubscription).filter(PushSubscription.endpoint == endpoint).first()
    if not existing:
        db.add(PushSubscription(username=user.username, endpoint=endpoint, keys=body.get("keys", {})))
        db.commit()
    elif existing.username != user.username:
        # Endpoint migrated to a different user (re-registered browser) — update owner
        existing.username = user.username
        existing.keys = body.get("keys", existing.keys)
        db.commit()
    return HTMLResponse("OK")

@router.post("/push/unsubscribe", response_class=HTMLResponse)
async def push_unsubscribe(request: Request, db: Session = Depends(get_db), user=Depends(get_current_user)):
    """Remove a push subscription for the current user."""
    try: body = await request.json()
    except Exception: return HTMLResponse("Invalid JSON", status_code=400)
    endpoint = body.get("endpoint", "")
    deleted = (db.query(PushSubscription).filter(PushSubscription.username == user.username, PushSubscription.endpoint == endpoint).delete())
    if deleted: db.commit()
    return HTMLResponse("OK")

@router.get("/push/status", response_class=HTMLResponse)
async def push_status(db: Session = Depends(get_db), user=Depends(get_current_user)):
    """How many active push subscriptions the current user has."""
    count = db.query(PushSubscription).filter(PushSubscription.username == user.username).count()
    return JSONResponse({"subscriptions": count, "push_enabled": PUSH_ENABLED})