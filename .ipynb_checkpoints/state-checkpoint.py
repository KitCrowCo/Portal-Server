# state.py  -  Unified State Accessor
"""
COLLABORATION NOTE
--
Canonical state read/write interface for the entire portal server.
When working on any module or tool: use ONLY these functions.
Do NOT query UserState or ServerState tables directly from modules.
Do NOT use raw session dicts. All state flows through here.

FOUR SCOPES
--
  "user"     Persisted per-user, across all devices and sessions.
             Stored in:  DB : user_state table (UserState.state JSON blob).
             Use for:    personal preferences, open tabs, editor state.

  "single"   One shared state for all authenticated server users.
             Stored in:  DB : server_state table (ServerState.state JSON blob).
             Use for:    server-wide config, collaborative shared views.

  "session"  Ephemeral per-browser-session. Cleared on server restart.
             Stored in:  in-memory Python dict keyed by hashed auth token.
             Use for:    form drafts, transient UI, undo history.

  "public"   No persistence. Reads return empty, writes are no-ops.
             Use for:    public-facing pages with no concept of user state.

NAMESPACING
--
All calls should pass namespace=<module_name> to isolate module state.
  Example:   namespace="dev_studio",  key="active_tab"
             namespace="auction",     key="last_seen_item"

Namespace=None operates on the root dict - reserved for portal shell and core systems. New modules must always pass a namespace.

USAGE
--
  # Read full namespace dict
  state = await get_state(request, scope="user", namespace="my_module")

  # Read one key (returns None cleanly if missing)
  val   = await get_state(request, scope="user", namespace="my_module", key="tab")

  # Write one key
  await set_state(request, "files", scope="user", namespace="my_module", key="tab")

  # Write entire namespace at once
  await set_state(request, {"tab": "files", "scroll": 0}, scope="user", namespace="my_module")

  # Remove one key
  await clear_state(request, scope="user", namespace="my_module", key="tab")

  # Remove entire namespace
  await clear_state(request, scope="user", namespace="my_module")

  # Session scope (lost on server restart - intentional for transient state)
  await set_state(request, form_data, scope="session", namespace="my_module", key="draft")

REQUIREMENT ON main.py
--
inject_context middleware MUST set request.state.user = user (or None).
This lets state calls resolve the current user with zero extra DB hits.
If not set, user-scoped calls return empty rather than raising error by design.
"""

import hashlib
import copy
from typing import Any, Optional
from fastapi import Request
from contextlib import contextmanager
from .database import SessionLocal, get_db
from .models import UserState, ServerState
from .style import DEFAULT_THEMES, get_module_default_theme

# -- In-memory session store --
# { token_hash : { namespace : { key : value } } }
# Tokens are 30-day JWTs. At ~20 users this never becomes a memory concern.
# No TTL/eviction - server restart clears it, which is the expected behavior.
_SESSION_STORE: dict[str, dict] = {}

# -- Internal helpers --

def _token_hash(request: Request) -> Optional[str]:
    """Stable opaque session key derived from the request's auth token. None for anon."""
    token = (request.cookies.get("access_token") or request.headers.get("Authorization", "").removeprefix("Bearer ").strip())
    if not token: return None
    return hashlib.sha256(token.encode()).hexdigest()[:32]

def _get_user(request: Request): return getattr(request.state, "user", None)

def _ns_read(store: dict, namespace: Optional[str], key: Optional[str]) -> Any:
    """Read from a namespaced dict. Returns shallow copy of namespace or single value."""
    bucket = store.get(namespace, {}) if namespace else store
    return dict(bucket) if key is None else bucket.get(key)

def _ns_write(store: dict, namespace: Optional[str], key: Optional[str], value: Any) -> None:
    """Write into a namespaced dict. Mutates store in place."""
    if namespace:
        if not isinstance(store.get(namespace), dict): store[namespace] = {}
        if key is None: store[namespace] = value if isinstance(value, dict) else {"_value": value}
        else: store[namespace][key] = value
    else:
        # Root-level write - portal shell and core systems only
        if key is None:
            if isinstance(value, dict): store.update(value)
        else:
            store[key] = value

def _ns_delete(store: dict, namespace: Optional[str], key: Optional[str]) -> None:
    """Remove a key or entire namespace from store. Prunes empty namespaces. Mutates store in place."""
    if namespace:
        if key is None:
            store.pop(namespace, None)
        elif namespace in store:
            store[namespace].pop(key, None)
            # Prune the namespace if it's now empty
            if not store[namespace]:  store.pop(namespace, None)
    elif key is not None:
        store.pop(key, None)

# -- Public API --

async def get_state(request: Request, scope: str = "user", namespace: Optional[str] = None, key: Optional[str] = None) -> Any:
    """Read state from the given scope. Returns a dict (namespace view), scalar (key lookup), or {} / None if missing. Never raises on missing data."""
    if scope == "public": return {} if key is None else None
    if scope == "session":
        sid = _token_hash(request)
        if not sid: return {} if key is None else None
        return _ns_read(_SESSION_STORE.get(sid, {}), namespace, key)
    with contextmanager(get_db)() as db:
        if scope == "user":
            user = _get_user(request)
            if not user: return {} if key is None else None
            row   = db.query(UserState).filter(UserState.user_id == user.id).first()
            store = dict(row.state) if (row and row.state) else {}
            return _ns_read(store, namespace, key)
        if scope == "single":
            row   = db.query(ServerState).first()
            store = dict(row.state) if (row and row.state) else {}
            return _ns_read(store, namespace, key)
    raise ValueError(f"Unknown scope {scope!r}. Valid: 'user', 'single', 'session', 'public'.")

async def set_state(request: Request, value: Any, scope: str = "user", namespace: Optional[str] = None, key: Optional[str] = None) -> None:
    """Write state to the given scope. Silently no-ops on unauthenticated requests for user/single scope. """
    if scope == "public": return
    if scope == "session":
        sid = _token_hash(request)
        if not sid: return
        if sid not in _SESSION_STORE: _SESSION_STORE[sid] = {}
        _ns_write(_SESSION_STORE[sid], namespace, key, value)
        return
    with contextmanager(get_db)() as db:
        if scope == "user":
            user = _get_user(request)
            if not user: return
            row = db.query(UserState).filter(UserState.user_id == user.id).first()
            if not row:
                row = UserState(user_id=user.id, state={})
                db.add(row)
                db.flush()

            store = copy.deepcopy(row.state) if row.state else {}
            _ns_write(store, namespace, key, value)
            row.state = store
            db.commit()
            return
        if scope == "single":
            row = db.query(ServerState).first()
            if not row:
                row = ServerState(state={})
                db.add(row)
                db.flush()
            store = copy.deepcopy(row.state) if row.state else {}
            _ns_write(store, namespace, key, value)
            row.state = store
            db.commit()
            return
    raise ValueError(f"Unknown scope {scope!r}.")

async def clear_state(request: Request, scope: str = "user", namespace: Optional[str] = None, key: Optional[str] = None) -> None:
    """Remove a key or entire namespace. No-op for 'public' scope."""
    if scope == "public": return
    if scope == "session":
        sid = _token_hash(request)
        if sid and sid in _SESSION_STORE: _ns_delete(_SESSION_STORE[sid], namespace, key)
        return
    with contextmanager(get_db)() as db:
        if scope in ("user", "single"):
            if scope == "user":
                user = _get_user(request)
                if not user: return
                row = db.query(UserState).filter(UserState.user_id == user.id).first()
            else:
                row = db.query(ServerState).first()
            if not row or not row.state: return
            store = dict(row.state)
            _ns_delete(store, namespace, key)
            row.state = store
            db.commit()
            return
    raise ValueError(f"Unknown scope {scope!r}.")

def clear_session(request: Request) -> None:
    """Fully wipe session-scope state for this token. Call on logout to immediately free in-memory storage."""
    sid = _token_hash(request)
    if sid: _SESSION_STORE.pop(sid, None)

async def resolve_theme_full(request: Request, db, module_ns: Optional[str] = None) -> dict:
    """Merges: hardcoded base -> server admin default -> module default -> user general -> user per-module override."""
    merged = dict(DEFAULT_THEMES.get("dark", {}))
    row = db.query(ServerState).first()
    server_default = ((row.state or {}).get("_theme", {}) if row and row.state else {}).get("server_default", {})
    merged.update(server_default)
    if module_ns: merged.update(get_module_default_theme(module_ns))
    user = _get_user(request)
    if user and getattr(user, "custom_theme", None): merged.update(user.custom_theme)
    if module_ns and user:
        override = await get_state(request, scope="user", namespace=f"_theme_{module_ns}", key="overrides")
        if override: merged.update(override)
    return merged
