# core_files/interface_manager.py - Interface Manager
import asyncio, json, uuid, pathlib, os
import time
from typing import Any, Optional, List
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import Column, String, Integer, JSON, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from sqlalchemy import create_engine
from .state import get_state, set_state
import traceback

# --- WebFrame Sections (always available for portal server) ---

router = APIRouter()

# html pickup for elements
_ELEMENT_HTML_CACHE = {}

# - WebSocket Manager (late-bound) -
_WS_MANAGER = None
def set_ws_manager(wm) -> None: global _WS_MANAGER; _WS_MANAGER = wm

# - Interface Manager Registry -
_IM_CLASS_REGISTRY = {0:{}}
def register_im(im, level = 1, branch = None) -> None:
    global _IM_CLASS_REGISTRY
    if not branch: branch = str(uuid.uuid4())
    if int(level) not in _IM_CLASS_REGISTRY: _IM_CLASS_REGISTRY[int(level)] = {}
    _IM_CLASS_REGISTRY[int(level)][branch] = im

# --- Module Descriptor ---

_DESCRIPTORS: dict[str, dict] = {}
def load_descriptor(module_name: str, module_path: str) -> dict:
    if module_name in _DESCRIPTORS: return _DESCRIPTORS[module_name]
    p = pathlib.Path(module_path) / "im_config.json"
    try: desc = json.loads(p.read_text()) if p.exists() else {}
    except Exception: desc = {}
    _DESCRIPTORS[module_name] = desc
    for intent_type, steps in desc.get("scripts", {}).items(): register_script(intent_type, steps)
    return desc

def get_descriptor(module_name: str) -> dict: return _DESCRIPTORS.get(module_name, {})

# --- Interface Database ---

Base = declarative_base()

class ElementRegistry(Base):
    __tablename__ = 'element_registry'
    id = Column(String, primary_key=True)  # unique per branch + element
    branch_id = Column(String, index=True)
    nesting_level = Column(Integer)
    element_id = Column(String)
    role = Column(String)
    scope = Column(String)
    metadata_json = Column(JSON)

class Branch(Base):
    __tablename__ = 'branches'
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String)   # no FK - IM db is separate from main app db
    session_id = Column(String)

def register_branch(user_id: str, session_id: str, db: Session) -> str:
    try:
        b = Branch(id=str(uuid.uuid4()), user_id=user_id, session_id=session_id)
        db.add(b); db.commit()
        return b.id
    except Exception as e:
        db.rollback(); print(f"Error registering branch: {e}")
        raise HTTPException(status_code=500, detail="Error registering branch")

def get_branch_id(user_id: str, session_id: str, db: Session) -> Optional[str]:
    try:
        b = db.query(Branch).filter(Branch.user_id == user_id, Branch.session_id == session_id).first()
        return b.id if b else None
    except Exception as e:
        print(f"Error getting branch: {e}"); return None

# --- Script Registry ---
# Module-level scripts registered by name. Steps are either callables or DSL dicts.

_SCRIPTS: dict[str, list] = {}
def register_script(name: str, steps: list) -> None: _SCRIPTS[name] = steps
def get_script(name: str) -> Optional[list]: return _SCRIPTS.get(name)

# --- Server-to-client push helpers (module-level, no IM instance needed) ---

async def push_to_client(user_id: str, data: dict) -> None:
    if _WS_MANAGER and user_id: await _WS_MANAGER.send_personal_message(data, user_id)

async def push_fragment(user_id: str, element_id: str, html: str, swap: str = "innerHTML") -> None: await push_to_client(user_id, {"t": "oob", "id": element_id, "html": html, "swap": swap})

async def push_update(user_id: str, element_id: str, *, html: str = None, props: dict = None, attrs: dict = None, classes: dict = None) -> None:
    msg = {"t": "update", "id": element_id}
    if html is not None: msg["html"] = html
    if props is not None: msg["props"] = props
    if attrs is not None: msg["attrs"] = attrs
    if classes is not None: msg["classes"] = classes
    await push_to_client(user_id, msg)

async def push_trigger(user_id: str, event: str, detail: Any = None) -> None: await push_to_client(user_id, {"t": "trigger", "event": event, "detail": detail})
async def push_refresh_trigger(user_id: str, value: str = None) -> None: await push_fragment(user_id, "portal-refresh-trigger", value or str(int(time.time()))) # Push an OOB update to #portal-refresh-trigger. IB dispatches 'portalRefresh' on the element, which any element using hx-trigger='portalRefresh from:#portal-refresh-trigger' picks up.
async def push_cfg(user_id: str, **flags) -> None: await push_to_client(user_id, {"t": "cfg", "values": flags})
async def kill_client_drag(user_id: str) -> None: await push_to_client(user_id, {"t": "kill_drag"})

# --- Payload Substitution ---

def _sub(value: Any, p: dict) -> Any:
    if not isinstance(value, str): return value
    for k, v in p.items(): value = value.replace(f"{{{k}}}", str(v))
    return value

def _sub_dict(d: Any, p: dict) -> Any:
    if isinstance(d, dict): return {k: _sub_dict(v, p) for k, v in d.items()}
    if isinstance(d, list): return [_sub_dict(i, p) for i in d]
    return _sub(d, p)

# --- WebFrame Tools ---

# -- IMResponse --
class IMResponse:
    """Assembles one HTMX HTTP response (OOB swaps + HX-Trigger headers)."""
    def __init__(self):
        self._triggers: dict = {}
        self._oob:      list = []

    def trigger(self, event: str, detail: Any = True) -> "IMResponse": self._triggers[event] = detail; return self
    def oob(self, html: str, element_id: str, swap: str = "innerHTML") -> "IMResponse": self._oob.append(f'<div id="{element_id}" hx-swap-oob="{swap}">{html}</div>'); return self
    def raw(self, html: str) -> "IMResponse":
        #print(f"[IMR] html={html}")
        self._oob.append(html); return self # Append pre-formed OOB HTML directly (for elements that already carry hx-swap-oob).
    def status(self, message: str, level: str = "info") -> "IMResponse": return self.oob(f'<span class="im-status-{level}">{message}</span>', "im-status-bar")
    def build(self, body: str = "") -> HTMLResponse: full = body + "".join(self._oob); return HTMLResponse(full or " ", headers={"HX-Trigger": json.dumps(self._triggers)} if self._triggers else {})

# --- WebFrame ---
# Operating paradigm: translates WS/HTMX web interface to IM intent/state layer.
# This is the web-specific last-mile between browser and InterfaceManager.

class WSRequestProxy:
    """Username string only - no db objects, safe across task boundaries."""
    def __init__(self, username: str = ""):
        class _U:
            def __init__(s, n): s.username = n; s.role = "user"
        class _S: pass
        self.state = _S(); self.state.user = _U(username)
        class _H:
            def get(self, k, d=""): return d
        self.headers = _H(); self.cookies = {}

async def route_ws_intent(user_id: str, data: dict) -> Optional[str]:
    """Route WS intent through IM registry. user_id is authenticated username string."""
    intent_type = data.get("type", "")
    if not intent_type: return None
    branch = data.get("branch", ""); lvl = int(data.get("lvl", 1))
    target_im = None
    if branch:
        for level_ims in _IM_CLASS_REGISTRY.values():
            if branch in level_ims: target_im = level_ims[branch]; break
    if target_im is None:
        for check_lvl in sorted(_IM_CLASS_REGISTRY.keys(), key=lambda l: abs(l - lvl)):
            for im in _IM_CLASS_REGISTRY.get(check_lvl, {}).values():
                if intent_type in im.scripts: target_im = im; break
            if target_im: break
    if target_im is None or intent_type not in target_im.scripts: return None
    result = await target_im.run_script(target_im.scripts[intent_type], WSRequestProxy(username=user_id), data, IMResponse())
    if not isinstance(result, IMResponse): return None
    html = result.build("").body.decode()
    return html if html.strip() else None

class WebFrame:
    def __init__(self, im: "InterfaceManager"):
        self.im = im

    async def handle_intent(self, intent: dict) -> dict: return await self.im.handle_intent(intent)

    async def render(self, response: dict) -> HTMLResponse:
        if response.get("type") == "html": return HTMLResponse(response.get("content", ""))
        return JSONResponse(response)

    async def handle_initial_load(self, user_id: str, nesting_level: int, branch_id: str):
        """Send DOM structure query to client on initial load."""
        await push_to_client(user_id, {"t": "get_dom_structure", "qid": uuid.uuid4().hex[:8], "level": nesting_level, "branch_id": branch_id})

    async def translate_web_initialization(self, dom_elements: List[dict], db: Session):
        """Takes DOM elements from client and registers them into SQL registry and local cache."""
        new_registrations = []
        for el in dom_elements:
            el_id = el.get("id") or f"gen_{uuid.uuid4().hex[:6]}"
            unique_key = f"{self.im.branch_id}_{el_id}"
            existing = db.query(ElementRegistry).filter_by(id=unique_key).first()
            if not existing:
                db.add(ElementRegistry(id=unique_key, branch_id=self.im.branch_id, nesting_level=self.im.nesting_level, element_id=el_id, role=el.get("role"), scope=el.get("scope"), metadata_json=el))
                new_registrations.append(el_id)
            self.im._registry_cache[(el.get("scope"), el.get("role"))] = el_id
        db.commit()
        self.im._dbg(f"Registered {len(new_registrations)} new elements to branch registry.")
        return new_registrations

    async def sync_registry_to_dom(self, user_id: str, db: Session):
        """Pushes attributes back to browser to lock elements to registry records."""
        elms = db.query(ElementRegistry).filter_by(branch_id=self.im.branch_id).all()
        updates = [{"old_id": e.element_id, "new_id": e.id, "hx_post": "/im/in", "hx_trigger": "click" if e.role == "button" else "change"} for e in elms]
        if updates: await push_to_client(user_id, {"t": "sync_dom", "updates": updates})

# --- Main State/Intent Based Interface Manager ---

class InterfaceManager:
    def __init__(self, nesting_level: int = 1, branch_id: str = None, db_path: str = "im_registry.db", operating_mode=None):
        self.branch_id = branch_id or str(uuid.uuid4())
        self.nesting_level = nesting_level
        self._registry_cache = {}
        self.scripts = {}
        self.engine = create_engine(f"sqlite:///./data/{db_path}", connect_args={"check_same_thread": False})
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.om = (operating_mode or WebFrame)(self)
        register_im(self, self.nesting_level, self.branch_id)

    # This is a web based only ****************************************************************************
    def template_context(self, extra: dict = None) -> dict:
        """Return context dict additions for base.html so data-im-scope matches this IM's branch.
        Modules spread this into their TemplateResponse context dict."""
        ctx = {"shell_id": self.branch_id, "nesting_level": self.nesting_level}
        if extra: ctx.update(extra)
        return ctx

    #if os.getenv("VERBOSE"):
    def _dbg(self, *args):  print(f"[IM][lvl:{self.nesting_level}|Branch:{self.branch_id[:8]}]", *args)

    def resolve_target(self, target: Any) -> Optional[str]:
        """Resolve a (scope, role) dict or role string to an element_id. Cache-first, SQL fallback."""
        if isinstance(target, dict):
            key = (target.get("scope"), target.get("role"))
            if key in self._registry_cache: return self._registry_cache[key]
            db = self.Session()
            res = db.query(ElementRegistry).filter_by(branch_id=self.branch_id, scope=target.get("scope"), role=target.get("role")).first()
            db.close()
        else:
            if target in self._registry_cache: return self._registry_cache[target]
            db = self.Session()
            res = db.query(ElementRegistry).filter_by(branch_id=self.branch_id, role=target).first()
            db.close()
            key = target
        if res:
            self._registry_cache[key] = res.element_id
            return res.element_id
        return None

    def mount_child(self, branch_id: str, manager: "InterfaceManager"):
        """Attach a child IM to this branch."""
        if not hasattr(self, "children"): self.children = {}
        self.children[branch_id] = manager
        manager.parent = self

    async def handle_intent(self, intent: dict, request: Request = None) -> dict:
        intent_type = intent.get("type")
        if intent_type == "initial_load":
            return {"status": "ok", "type": "initial_load"}
        elif intent_type == "update_state":
            return await self.handle_state_update(intent, request)
        elif intent_type == "query_element":
            eid = self.resolve_target(intent.get("target", intent.get("id")))
            return {"status": "ok", "element_id": eid}
        # elif intent_type == "set_bridge":
        #     # IB toggled bridge bar - persist open state to user session
        #     if request:
        #         open_val = intent.get("open", "false").lower() == "true"
        #         await set_state(request, open_val, scope="session", namespace="_im", key="bridge_open")
        #     return {"status": "ok"}
        # elif intent_type == "set_cfg":
        #     # IB updated a feature flag - persist to user preferences
        #     if request:
        #         key = intent.get("key"); val = intent.get("value")
        #         if key:
        #             cfg = await get_state(request, scope="user", namespace="_im", key="cfg") or {}
        #             cfg[key] = val
        #             await set_state(request, cfg, scope="user", namespace="_im", key="cfg")
        #     return {"status": "ok"}
        elif intent_type == "clipboard_set":
            user = getattr(request.state, "user", None) if request else None
            if user: await push_clipboard(str(user.id), intent.get("value", ""))
            return {"status": "ok"}
        elif intent_type in self.scripts:
            # locally registered script takes precedence over global registry
            return await self.run_script(self.scripts[intent_type], request, intent, IMResponse())
        elif intent_type in _SCRIPTS:
            return await self.run_script(_SCRIPTS[intent_type], request, intent, IMResponse())
        else:
            return {"status": "error", "message": f"Unknown intent type: {intent_type}"}

    async def handle_state_update(self, intent: dict, request: Request) -> dict:
        data = intent.get("data"); scope = intent.get("scope"); namespace = intent.get("namespace"); key = intent.get("key")
        if not all([data is not None, scope, namespace, key]): return {"status": "error", "message": "Missing required fields for state update"}
        try:
            await set_state(request, data, scope=scope, namespace=namespace, key=key)
            return {"status": "success"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    # --- Script Executor ---
    async def run_script(self, steps: list, request: Request, payload: dict, imr: IMResponse) -> IMResponse:
        """
        Run steps sequentially. Callable steps: async fn(request, payload, imr) -> imr.
        Dict steps use type-keyed DSL (query, oob, trigger, state_write supported).
        """
        p = dict(payload)
        if "intent" in p and isinstance(p["intent"], dict): p = dict(p["intent"]) # Dig into the actual data container if wrapped
        user = getattr(request.state, "user", None) if request else None
        user_id = str(user.id) if user else ""
        for step in steps:
            try:
                if callable(step):
                    imr = await step(request, p, imr)
                elif isinstance(step, dict):
                    t = step.get("type")
                    if t == "oob": imr.oob(_sub_dict(step.get("html", ""), p), _sub(step.get("id", ""), p), step.get("swap", "innerHTML"))
                    elif t == "trigger": imr.trigger(_sub(step.get("event", ""), p), step.get("detail"))
                    elif t == "state_write":  await set_state(request, _sub_dict(step.get("value"), p), scope=step.get("scope", "user"), namespace=step.get("namespace"), key=step.get("key"))
                    elif t == "push": await push_to_client(user_id, _sub_dict(step.get("payload", {}), p))
                    elif t == "query": p.update(await query_element(user_id, _sub(step.get("id", ""), p), step.get("fields")))
            except Exception as e:
                traceback.print_exc()
        return imr

# --- Routes ---
# Prefix "/im" is added by main.py include_router call, so routes here are /in, /out, etc.

@router.post("/in")
async def handle_intent_route(request: Request) -> HTMLResponse:
    try:
        ct = request.headers.get("content-type", "")
        if "application/json" in ct:
            body = await request.json()
        else:
            form = await request.form(max_part_size=32 * 1024 * 1024)  # was: await request.form() - default 1MiB/field cap was truncating large document autosaves
            body = {}
            for key in form.keys():
                vals = form.getlist(key)
                body[key] = vals if len(vals) > 1 else vals[0]
        if "payload" in body and isinstance(body.get("payload"), str):
            try: body.update(json.loads(body["payload"]))
            except Exception: pass
        hx_prompt = request.headers.get("HX-Prompt")
        if hx_prompt is not None and "name" not in body:
            body["name"] = hx_prompt
        intent_type = body.get("type", "")
        lvl = int(body.get("lvl", 1))   # default 1 - 0 is last resort
        branch = body.get("branch", "")
        target_im = None
        # Exact branch match (any level, highest specificity)
        if branch:
            for level_ims in _IM_CLASS_REGISTRY.values():
                if branch in level_ims: target_im = level_ims[branch]; break

        # IM with intent in its local scripts, nearest level first
        if target_im is None:
            levels_ordered = sorted(_IM_CLASS_REGISTRY.keys(), key=lambda l: abs(l - lvl))
            for check_lvl in levels_ordered:
                for im in _IM_CLASS_REGISTRY.get(check_lvl, {}).values():
                    if intent_type in im.scripts: target_im = im; break
                if target_im: break

        # Intent in global _SCRIPTS: first IM at nearest level handles it
        if target_im is None and intent_type in _SCRIPTS:
            levels_ordered = sorted(_IM_CLASS_REGISTRY.keys(), key=lambda l: abs(l - lvl))
            for check_lvl in levels_ordered:
                ims = _IM_CLASS_REGISTRY.get(check_lvl, {})
                if ims: target_im = next(iter(ims.values())); break

        if target_im is None:
            # If it's a structural interaction intent that nobody has explicitly captured, return a neutral no-op response
            if intent_type in ["tap", "focus_change"]: return HTMLResponse(" ")
            print(f"[IM] no handler for intent={intent_type}")
            return HTMLResponse(" ")

        result = await target_im.handle_intent(body, request)
        if isinstance(result, IMResponse): return result.build() # IMResponse must be built into an HTMLResponse; plain dicts are no-ops
        if isinstance(result, (HTMLResponse, JSONResponse)): return result
        return HTMLResponse(" ")
    except Exception as e:
        print(f"[IM] handle_intent error: {e}")
        return HTMLResponse(" ", status_code=500)

@router.get("/out/{eid}")
async def get_element_html(eid: str) -> HTMLResponse:
    html = _ELEMENT_HTML_CACHE.get(eid)
    return HTMLResponse(html) if html else HTMLResponse("<!-- element not found -->", status_code=404)

@router.get("/context/{module_name}")
async def get_module_context(module_name: str) -> JSONResponse:
    """Return bridge actions and IM config for a module. IB calls this on focused."""
    desc = get_descriptor(module_name)
    return JSONResponse(desc.get("input_bridge", []))

# - Server-scoped Clipboard -
# ** May be deprecated; server-scoped clipboard is kept simple, intent-based handling preferred long term

_CLIPBOARD: dict[str, str] = {}

async def push_clipboard(user_id: str, value: str) -> None:
    _CLIPBOARD[user_id] = value
    await push_to_client(user_id, {"t": "clipboard_sync", "value": value})

@router.get("/clipboard")
async def get_clipboard(request: Request) -> JSONResponse:
    user = getattr(request.state, "user", None)
    return JSONResponse({"value": _CLIPBOARD.get(str(user.id), "") if user else ""})

# - Element Query (async WS round-trip) -
# ** Kept for form-field reads and similar cases where server needs live DOM values.

_ELEMENT_QUERIES: dict[str, "asyncio.Future[dict]"] = {}
async def query_element(user_id: str, element_id: str, fields: list = None, timeout: float = 3.0) -> dict:
    """Ask the client for current state of element_id. Returns {} on timeout."""
    if not _WS_MANAGER: return {}
    qid = uuid.uuid4().hex[:8]
    fut: asyncio.Future = asyncio.get_running_loop().create_future()
    _ELEMENT_QUERIES[qid] = fut
    await push_to_client(user_id, {"t": "query", "qid": qid, "id": element_id, "fields": fields or []})
    try: return await asyncio.wait_for(asyncio.shield(fut), timeout=timeout)
    except asyncio.TimeoutError: return {}
    finally: _ELEMENT_QUERIES.pop(qid, None)

@router.post("/element_data")
async def receive_element_data(request: Request) -> HTMLResponse:
    """Client response to a query_element WS request. Resolves the waiting Future."""
    ct = request.headers.get("content-type", "")
    body = await request.json() if "application/json" in ct else dict(await request.form())
    try: data = json.loads(body.get("data", "{}"))
    except Exception: data = {}
    fut = _ELEMENT_QUERIES.get(body.get("qid", ""))
    if fut and not fut.done(): fut.set_result(data)
    return HTMLResponse(" ")