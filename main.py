# main.py
import os, sys, uuid, importlib, logging, re, subprocess, pkg_resources, threading, pathlib, shutil, traceback
from contextlib import contextmanager
from urllib.parse import quote
from fastapi import FastAPI, Request, Depends, HTTPException, Form, Response, WebSocket, status, Body
from fastapi.routing import APIRoute, Mount
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse, HTMLResponse, JSONResponse, FileResponse
from sqlalchemy.orm import Session
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
from jose import jwt, JWTError

from .encrypt import encrypt_token, decrypt_token
from .auth import create_access_token, verify_password, get_current_user, hash_password
from .database import engine, Base, get_db, SessionLocal
from .models import *
from .control_panel import router as control_router, set_templates as set_cp_templates
from .notify import router as notify_router, send_push, broadcast_push
from .ws_manager import manager
from .state import get_state, set_state, clear_state, clear_session, resolve_theme_full
from .style import *
from .interface_manager import router as im_router, set_ws_manager, InterfaceManager, IMResponse, push_fragment, push_to_client, route_ws_intent
from .file_server import *
from . import built_ins as bf

# -- DB init --
Base.metadata.create_all(bind=engine)

# -- Routers and Templates --

base_theme = DEFAULT_THEMES["dark"] # Theme used for the very basic including possibly public pages and logins
VERBOSE = os.getenv("VERBOSE", False)
SERVER_NAME = os.getenv("SERVER_NAME", "Portal Server")
ROOT_DIR = os.getenv("ROOT_DIR", "/app")

app = FastAPI(title = SERVER_NAME)
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts = ["*"])
app.mount("/static", StaticFiles(directory = "core_files/static"), name = "static")
app.include_router(control_router, prefix = "/control-panel")
app.include_router(notify_router)
app.include_router(im_router, prefix = "/im", tags = ["interface-manager"])
set_ws_manager(manager)

templates = Jinja2Templates(directory = "core_files/templates")
templates.env.globals.update(os = os, verbose = VERBOSE, UI = UI, STYLE_GROUPS = STYLE_GROUPS)
set_cp_templates(templates)

# All Data goes here
os.makedirs("./data", exist_ok=True)
os.makedirs("./data/_common", exist_ok=True)
INFO_SRC = pathlib.Path("./core_files/static/information")
INFO_DST = pathlib.Path("./data/_common/Information")

# -- Startup --

@app.on_event("startup")
def startup_db_check(db = Depends(get_db)):
    with contextmanager(get_db)() as db:
        # Admin account
        if not db.query(User).filter(User.role == "admin").first():
            print("--- FIRST RUN: CREATING ADMIN ACCOUNT ---")
            db.add(User(username = os.getenv("ADMIN_USER", "admin"), password_hash = hash_password(os.getenv("ADMIN_PASS", "admin")), role = "admin", settings = {"first_run": True}))
            db.commit()
        # Themes
        if not db.query(Theme).first():
            for slug, cfg in DEFAULT_THEMES.items():
                db.add(Theme(slug=slug, name=cfg["name"], config=cfg, is_active=(slug == "dark")))
            db.commit()
        # UI strings
        if not db.query(UIString).first():
            for k, v in UI_STRINGS.items():
                db.add(UIString(key=k, value=v))
            db.commit()
        # Server state singleton - exactly one row must always exist
        if not db.query(ServerState).first():
            db.add(ServerState(state={}))
            db.commit()

def sync_information_docs():
    """Copies bundled getting-started/about docs into the wiki's shared root on every startup.
    Overwrites only if content differs, so a user's own edits inside data/_common/Information survive restarts unless the shipped doc itself changed."""
    if not INFO_SRC.exists(): return
    INFO_DST.mkdir(parents=True, exist_ok=True)
    for f in INFO_SRC.glob("*.md"):
        dest = INFO_DST / f.name
        src_text = f.read_text(encoding="utf-8")
        if not dest.exists() or dest.read_text(encoding="utf-8") != src_text: dest.write_text(src_text, encoding="utf-8")

sync_information_docs()

# -- Middleware --

@app.middleware("http")
async def inject_context(request: Request, call_next):
    """
    Runs before every request. Resolves the current user and sets request.state.user so state.py can access it without an extra DB hit.
    Theme and ui_data are server-wide constants - safe as Jinja globals.
    User is intentionally NOT set as a global (race condition: one request's user could overwrite another's in a shared template context).
    """
    global base_theme
    db = SessionLocal()
    try:
        UI.reset_toolbar_layout() # reset per-request toolbar index counters
        server_row = db.query(ServerState).first()
        server_default = ((server_row.state or {}).get("_theme", {}).get("server_default", {}) if server_row and server_row.state else {})
        base_theme = {**DEFAULT_THEMES.get("dark", {}), **server_default}
        ui_data = {s.key: s.value for s in db.query(UIString).all()}
        try: user = await get_current_user(request, db=db)
        except Exception: user = None
        request.state.user = user # per-request safe = for concurrent users
        templates.env.globals.update({"theme": base_theme, "ui": ui_data, "get_modules": get_module_list})
    finally:
        db.close()
    return await call_next(request)

# -- Module Security & Deps --

metas = {"module":{}, "tool": {}}

def validate_module_name(name: str) -> bool: return bool(name and not name.startswith((".", "_")) and re.match(r"^[a-zA-Z][a-zA-Z0-9_]*$", name))

def check_module_dependencies(module_path: str):
    req_path = os.path.join(module_path, "requirements.txt")
    if os.path.exists(req_path):
        with open(req_path) as f:
            deps = [l.strip() for l in f if l.strip() and not l.startswith("#")]
        installed = {pkg.key for pkg in pkg_resources.working_set}
        missing = [d for d in deps if d.split("==")[0].lower() not in installed]
        if missing:
            print(f"--- WARNING: {module_path} missing deps: {missing} ---")
            subprocess.check_call([sys.executable, "-m", "pip", "install", *missing])

def load_server_router(path, item, prefix, dependencies={}, router_type="module", path_modifier="", verbose=VERBOSE):
    global metas
    dash = "_" if path_modifier else ""
    main_path = f"{path}/{path_modifier}{dash}{item}.py"
    if not os.path.exists(main_path): return False
    if router_type == "module": os.makedirs(f"./data/{item}", exist_ok=True)
    effective_prefix = "public" if path_modifier == "public" else prefix
    try:
        # Prevent dual-instantiation: reuse the module if the Tool loader just created it
        if router_type == "tool" and not path_modifier:
            mod = Tools[item]
        else:
            # Use an explicit package hierarchy name (e.g., modules.my_module.my_module)
            module_name = f"{router_type}s.{item}.{path_modifier}{dash}{item}".strip('.')
            spec = importlib.util.spec_from_file_location(module_name, main_path)
            mod = importlib.util.module_from_spec(spec)
            # Define the package so relative imports work inside the tool natively
            mod.__package__ = f"{router_type}s.{item}"
            # Register in sys.modules BEFORE execution to prevent dual instantiation
            sys.modules[module_name] = mod
            spec.loader.exec_module(mod)
        has_router = hasattr(mod, "router")
        module_meta = {"label": item.replace("_", " ").title(), "icon": "", "description": "-", "persistence": "public", "public": False}
        module_meta.update(getattr(mod, "MODULE_META", None) or getattr(mod, "TOOL_META", {}))
        if has_router:
            auth_dep = [] if (path_modifier == "public" or module_meta.get("public")) else [Depends(get_current_user)]
            app.include_router(mod.router, prefix=f"/{effective_prefix}/{item}", tags=[f"{item}:{router_type}"], dependencies=auth_dep)
            if verbose: print(f"Loaded {router_type} router: {path_modifier}{dash}{item}")
        elif verbose:
            print(f"Loaded {router_type} (import-only, no router): {path_modifier}{dash}{item}")
        if path_modifier != "public": metas[router_type].update({item: module_meta})
        refresh_cb = dependencies.get("refresh_system") if dependencies else None
        deps_with_meta = {**dependencies, "meta": module_meta}
        if refresh_cb and has_router:
            deps_with_meta["refresh_system"] = refresh_cb(f"/{effective_prefix}/{item}", mod.router)
        if dependencies and hasattr(mod, "init_module"):
            mod.init_module(deps_with_meta)
            if verbose: print(f"Environment injected into module: {item}")
        return True
    except Exception as e:
        print(f"Error loading {path_modifier}{dash}{item} router: {e}")
        traceback.print_exc()
        return False

def load_modules(module_type="module"):
    modules_dir = module_type + "s"
    db = SessionLocal()
    active_theme = db.query(Theme).filter(Theme.is_active == True).first()
    ui_data = {s.key: s.value for s in db.query(UIString).all()}
    db.close()
    # GUARANTEE BASE __init__.py EXISTS (e.g., tools/__init__.py) This makes the root folder a valid package for absolute imports.
    base_init_path = os.path.join(modules_dir, "__init__.py")
    if os.path.exists(modules_dir) and not os.path.exists(base_init_path):
        with open(base_init_path, "w") as f: pass
    def create_refresh_callback(target_prefix, target_router):
        """Creates a scoped callback for a specific level-2 router."""
        def register_sub_routes():
            app.routes[:] = [r for r in app.routes if not (hasattr(r, "path") and r.path.startswith(target_prefix))]
            app.include_router(target_router, prefix=target_prefix)
            app.openapi_schema = None
            if VERBOSE: print(f"--- Refreshed Sub-Routes for: {target_prefix} ---")
        return register_sub_routes
    for item in os.listdir(modules_dir):
        module_path = os.path.join(modules_dir, item)
        if not os.path.isdir(module_path) or not validate_module_name(item): continue
        # GUARANTEE ITEM __init__.py EXISTS (e.g., tools/my_tool/__init__.py) This makes the specific tool/module a valid sub-package.
        item_init_path = os.path.join(module_path, "__init__.py")
        if not os.path.exists(item_init_path):
            with open(item_init_path, "w") as f: pass

        check_module_dependencies(module_path)
        router_dependencies = {"auth":             get_current_user,
                               "db":               get_db,
                               "templates":        templates,
                               "theme":            active_theme.config if active_theme else {},
                               "tools":            Tools,
                               "strings":          ui_data,
                               "get_state":        get_state,
                               "set_state":        set_state,
                               "clear_state":      clear_state,
                               "resolve_theme":    resolve_theme_full,
                               "get_modules":      get_module_list,
                               "send_push":        send_push,
                               "broadcast_push":   broadcast_push,
                               "push_fragment":    push_fragment,
                               "InterfaceManager": InterfaceManager,
                               "ws":               manager,
                               "IMResponse":       IMResponse,
                               "push_to_client":   push_to_client,
                               "encrypt_token":    encrypt_token,
                               "decrypt_token":    decrypt_token,
                               "refresh_system":   create_refresh_callback}
        if module_type == "tool" and os.path.exists(f"{module_path}/{item}.py"):
            try:
                module_name = f"tools.{item}.{item}"
                spec = importlib.util.spec_from_file_location(module_name, f"{module_path}/{item}.py")
                mod = importlib.util.module_from_spec(spec)
                mod.__package__ = f"tools.{item}"
                sys.modules[module_name] = mod
                spec.loader.exec_module(mod)
                Tools[item] = mod
                if VERBOSE: print(f"Loaded Internal Tool: {item}")
            except Exception as e:
                print(f"--- ERROR Loading Internal Tool: {item} ---")
                traceback.print_exc()
        admin_router = load_server_router(module_path, item, prefix=module_type, dependencies=router_dependencies, router_type=module_type, path_modifier="", verbose=VERBOSE)
        if admin_router:
            os.makedirs(f"./data/{item}/static", exist_ok=True)
            app.mount(f"/{module_type}/assets/{item}", StaticFiles(directory=f"./data/{item}/static"), name=f"{module_type}_assets_{item}")
            if os.path.exists(f"{module_path}/public_{item}.py"):
                if VERBOSE: print(f"Mounting Public Router: {item}")
                public_deps = {"templates": templates, "theme": active_theme.config if active_theme else {}, "tools": Tools, "resolve_theme": resolve_theme_full, "get_state": get_state}
                load_server_router(module_path, item, prefix=module_type, dependencies=public_deps, router_type=module_type, path_modifier="public", verbose=VERBOSE)

def refresh_modular_router(primary_router, middle_router_instance, prefix):
    primary_router.routes = [route for route in primary_router.routes if not route.path.startswith(prefix)]
    primary_router.include_router(middle_router_instance, prefix=prefix)

# -- Module & Tool Loader --

Tools = {"built_ins": bf}

def get_module_list(module_type="module"):
    modules_path = f"./{module_type}s"
    if not os.path.exists(modules_path): return []
    return [d for d in os.listdir(modules_path) if os.path.isdir(os.path.join(modules_path, d)) and validate_module_name(d)]

def get_module_access_config() -> dict:
    """Returns {module_name: [allowed_role_or_username, ...]} from ServerState._portal."""
    db = SessionLocal()
    try:
        row = db.query(ServerState).first()
        state = dict(row.state) if (row and row.state) else {}
        return state.get("_portal", {}).get("module_access", {})
    finally: db.close()

def get_accessible_modules(user, module_type="module") -> list:
    """get_module_list filtered by the module_access config for this user."""
    all_mods = get_module_list(module_type)
    cfg = get_module_access_config()
    if not cfg or cfg == {}: return all_mods
    result = []
    for m in all_mods:
        allowed = cfg.get(m)
        if not allowed: result.append(m); continue      # no restriction
        if user and (user.role in allowed or user.username in allowed): result.append(m)
    return result

load_modules("tool")

# -- Auth Routes --

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    next_url = request.query_params.get("next", "")
    return templates.TemplateResponse(name = "login.html", request = request, context = {"request": request, "user": None, "theme": base_theme, "next": next_url})

@app.post("/login")
async def handle_login(response: Response, request: Request, username: str = Form(...), password: str = Form(...), next: str = Form(default="/"), db=Depends(get_db)):
    user = db.query(User).filter(User.username == username).first()
    if user and verify_password(password, user.password_hash):
        token = create_access_token(user.username)
        is_https = request.headers.get("x-forwarded-proto", "http") == "https" or str(request.base_url).startswith("https")
        response.set_cookie(key="access_token", value=token, httponly=True, samesite="none" if is_https else "lax", secure=is_https)
        next_url = next if next.startswith("/") else "/"
        response.headers["HX-Redirect"] = next_url
        return {"status": "ok"}
    return HTMLResponse("<span style='color:#ff4d4f;'>&#x26A0; Invalid username or password.</span>")

@app.get("/logout")
async def logout(request: Request, response: Response):
    clear_session(request)   # free in-memory session state immediately
    response.delete_cookie("access_token")
    return RedirectResponse(url="/login", status_code=302)

# -- Core Routes --

def sync_module_docs():
    """Copies each module's static/README.md (if present) into the _common shared root under Modules/{name}.md, so any module can ship user-facing docs that appear in-wiki automatically.
    Same overwrite-only-if-changed behavior as sync_information_docs()."""
    dest_dir = pathlib.Path("./data/_common/Modules")
    for item in get_module_list():
        src = pathlib.Path(f"./modules/{item}/static/README.md")
        if not src.exists(): continue
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"{item}.md"
        text = src.read_text(encoding="utf-8")
        if not dest.exists() or dest.read_text(encoding="utf-8") != text: dest.write_text(text, encoding="utf-8")

load_modules("module")
sync_module_docs()
templates.env.globals.update(get_modules=get_module_list)

@app.get("/_load_module")
async def load_module(module: str): return RedirectResponse(url=f"/module/{module}/", status_code=302)

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if exc.status_code == 401 and "text/html" in request.headers.get("accept", ""): return RedirectResponse(url=f"/login?next={quote(str(request.url.path), safe='/')}")
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

@app.get("/external_frame", response_class=HTMLResponse)
async def external_frame(url: str, request: Request, user=Depends(get_current_user)):
    safe_url = url if url.startswith(("http://","https://")) else f"http://{url}"
    return HTMLResponse(f"""<div style="height:100%;display:flex;flex-direction:column">
        <div style="padding:.2rem .5rem;font-size:.7rem;color:var(--text_muted);border-bottom:var(--border-thick) solid var(--border);display:flex;justify-content:space-between">
            <span>{safe_url}</span><a href="{safe_url}" target="_blank" style="color:var(--accent)">Open in new tab &#x2192;</a>
        </div>
        <iframe src="{safe_url}" style="flex:1;width:100%;border:none;display:block;" sandbox="allow-same-origin allow-scripts allow-forms allow-popups allow-downloads"></iframe>
    </div>""")

# -- WebSocket --

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, db: Session = Depends(get_db)):
    try:
        await websocket.accept()
    except Exception as e:
        print(f"[WS] accept error: {e}")
    user_id = "anonymous"
    try:
        token = websocket.cookies.get("access_token") or websocket.query_params.get("token", "")
        if token:
            pl = jwt.decode(token, os.getenv("SECRET_KEY", "super-secret-fcss-key"), algorithms=[os.getenv("ALGORITHM", "HS256")])
            username = pl.get("sub")
            if username:
                user = db.query(User).filter(User.username == username).first()
                if user: user_id = user.username
        print(f"[WS] connect: {user_id}")
    except Exception as e:
        print(f"[WS] auth error: {e}")
    await manager.connect(user_id, websocket)
    try:
        while True:
            data = json.loads(await websocket.receive_text())
            if data.get("type"):
                html = await route_ws_intent(user_id, data)
                if html: await manager.send_personal_message(html, user_id)
                else: await manager.on_incoming_message(user_id, data)
            else:
                await manager.on_incoming_message(user_id, data)
    except Exception as e:
        print(f"[WS] error {user_id}: {e}")
    finally:
        await manager.disconnect(user_id, websocket)

# -- PWA Worker --

@app.get("/sw.js")
async def serve_sw(): return FileResponse("./core_files/static/js/sw.js", media_type="application/javascript")

@app.get("/favicon.ico", include_in_schema=False)
async def favicon(): return FileResponse("./core_files/static/icon-192.png")

# -- Home Page --

async def _render_content_area(request, state): return state, f"""<div id="sub-content-area" hx-get="{state.get("tabs", {}).get(state.get("active", ""), {}).get("path", "/launcher")}" hx-trigger="load" hx-target="#content-root" hx-swap="innerHTML">Loading...</div>"""

_shell_im = InterfaceManager(nesting_level = -1, db_path="im_registry.db") # Level -1: portal chrome intents - bridge state, main sidebar, user controls - These never need a content area and are always present regardless of what module is open
_portal_im = InterfaceManager(nesting_level = 0, db_path="im_registry.db") # Level 0: dashboard content - tab navigation, portal-level tab state
_pre = "_portal"
TM = bf.TabManager(namespace = "_nav", tab_bar_id = "portal-nav-bar-inner", content_id = "content-root", render_content_fn = _render_content_area, intent_prefix = _pre, IM = _portal_im, empty = {"tabs": {"launcher-0": {"id": "launcher-0", "path": "/launcher", "label": "Module Launcher", "icon": "", "order": 0}}, "active": "launcher-0"}, nesting_level = 0)

async def _h_portal_init(request, payload, imr):
    """Re-syncs the content area to the current nav/tab state for the shell_uuid the client just rendered - handles reconnects and stale OOB targets after a hard refresh."""
    target = payload.get("target", "")
    if not target: return imr
    state = await get_state(request, scope="user", namespace="_nav") or {}
    state, content_html = await _render_content_area(request, state)
    imr.oob(content_html, target)
    return imr

_portal_im.scripts["portal_init"] = [_h_portal_init]


# # Needs Review ********************************************************************************
# _shell_im.scripts["set_bridge"] = [lambda request, payload, imr: _handle_bridge_state(request, payload, imr)]
# _shell_im.scripts["set_cfg"] = [lambda request, payload, imr: _handle_cfg_state(request, payload, imr)]

async def _handle_bridge_state(request, payload, imr):
    open_val = payload.get("open", "false").lower() == "true"
    await set_state(request, open_val, scope="session", namespace="_im", key="bridge_open")
    return imr

async def _handle_cfg_state(request, payload, imr):
    key = payload.get("key"); val = payload.get("value")
    if key:
        cfg = await get_state(request, scope="user", namespace="_im", key="cfg") or {}
        cfg[key] = val
        await set_state(request, cfg, scope="user", namespace="_im", key="cfg")
    return imr

@app.get("/")
async def dashboard(request: Request, user=Depends(get_current_user)):
    if not user: return RedirectResponse(url="/login")
    admin_link = f"""<a class='nav-link' style='background:none; border:none; text-align:left; width:100%; padding:0.5rem 0; cursor:pointer;' hx-post='/im/in' hx-target='body' hx-swap='none' hx-vals='{json.dumps({'type': f'{_pre}_open_tab', 'path': '/control-panel', 'label': 'Control Panel', 'id': 'control-panel', 'lvl': 0})}'>&#x2699; Control Panel</a>"""
    if user.role == "admin": admin_link += f"""<button class='nav-link' style='background:none; border:none; text-align:left; width:100%; padding:0.5rem 0; cursor:pointer; color:var(--text);' hx-post='/_reset_nav_all' hx-swap='none' onclick="this.innerHTML='&#x231B; Resetting...'; setTimeout(() => this.innerHTML='&#x26A0; Reset All Navs', 2000);">&#x26A0; Reset All Navs</button>
                                               <button class='nav-link' style='background:none; border:none; text-align:left; width:100%; padding:0.5rem 0; cursor:pointer; color:var(--text);' hx-post='/rescan' hx-swap='none' onclick="this.innerHTML='&#x231B; Scanning...'; setTimeout(() => this.innerHTML='&#x27F3; Rescan Files', 2000);">&#x27F3; Rescan Files</button>"""
    ext_links = await get_state(request, scope="single", namespace="_portal", key="ext_links") or []
    ext_nav = "".join(f"""<button style='background:none; border:none; text-align:left; width:100%; padding:0.5rem 0; cursor:pointer; color:var(--text);' hx-post='/im/in' hx-target='body' hx-swap='none' hx-vals='{json.dumps({"type": f"{_pre}_open_tab", "path": f"/external_frame?url={quote(l['url'], safe='')}", "label": l["label"], "id": f"ext-{l.get('id','link')}", "lvl": 0})}'>{l.get("icon","&#x1F310;")} {UI.escape(l["label"])}</button>""" for l in ext_links)
    module_select = UI.dropdown(name="payload", options=[(json.dumps({'type': f'{_pre}_open_tab', 'path': f'/module/{m}/', 'label': m.replace("_", " ").title(), 'id': m.replace("_", "-")}), m.replace('_',' ').title()) for m in get_accessible_modules(user)], htmx_dict={"post": "/im/in", "target": "body", "swap": "none", "trigger": "change", "on::after-request": "this.value=''"}, default_text="Select Module&#x2026;")
    nav = f"""<nav style='flex:1;'>
                   <a href='/' class='nav-link'>&#x2302; Dashboard</a>
                   {admin_link}
                   <label style='font-size:var(--font-size); color:var(--text_muted); text-transform:uppercase; margin-top:1.5rem; display:block; letter-spacing:0.1rem;'>
                       Modules
                       {module_select}
                   </label>
                   {ext_nav}
               </nav>"""
    state = await get_state(request, scope = "user", namespace = "_nav") or {}
    state.setdefault("tabs", {})
    state.setdefault("active", "launcher")
    state, content_area = await _render_content_area(request, state)
    nav_bar = await TM.tab_bar_fn(state, "portal-nav-bar-inner", _pre)
    top_content = f"""<div style="display:flex; flex-direction:column; height:100%;">
                          <div style="padding:0 0.4rem; height:1.5rem; display:flex; align-items:center; font-size:0.5rem; color:var(--text_muted); letter-spacing:0.05rem; border-bottom:var(--border-thick) solid var(--border); flex-shrink:0;">
                              {" "*2 + SERVER_NAME}
                          </div>
                          <div id="portal-nav-bar-outer" style="flex:1; min-height:0; overflow:hidden;">{nav_bar}</div>
                      </div>"""
    return templates.TemplateResponse(name = "base.html", request = request, context = {"request": request, "user": user, "PWA": True, "content": content_area, "code_mirror": True, **_portal_im.template_context(),
                        "main_left_toolbar": nav,
                        "toolbars": {"top": UI.toolbar(side="top", content = top_content, size = "4.5rem", overlay = False, start_open = True, id = "portal-top-bar", nesting_level = 0)}})

@app.get("/launcher", response_class = HTMLResponse)
async def launcher(request: Request):
    global metas
    cards = UI.card("Control Panel", "&#x2699; Control Panel", htmx = {"post": '/im/in', "target": 'body', "swap": 'none', 'vals': json.dumps({"type": f"{_pre}_open_tab", "path": "/control-panel/", "label": "&#x2699; Control Panel", "id": "control-panel", "lvl": 0})})
    cards += "".join([UI.card(m.replace("_", " ").title(), " ".join([metas["module"].get(m, {}).get("icon",""), metas["module"].get(m, {}).get("description","")]), htmx = {"post": '/im/in', "target": 'body', "swap": 'none', 'vals': json.dumps({"type": f"{_pre}_open_tab", "lvl": 0, "path": f"/module/{m}/", "label": m.replace("_"," ").title(), "id": f"mod-{m}"})}) for m in get_accessible_modules(request.state.user)])
    return HTMLResponse(f'<div style="padding:2rem; display:grid; grid-template-columns:repeat(auto-fill,minmax(18rem, 1fr)); gap:1rem;">{cards}</div>')

# -- Debug Routes --

@app.post("/_reset_nav_all", response_class=HTMLResponse)
async def reset_nav_all(request: Request, user=Depends(get_current_user), db=Depends(get_db)):
    """Admin only: wipe _nav namespace and all module namespaces from every user's state so nobody is stuck."""
    if user.role != "admin": return HTMLResponse("Denied", status_code=403)
    namespaces_to_clear = ["_nav"] + list(get_accessible_modules(user))
    rows = db.query(UserState).all()
    for row in rows:
        if row.state:
            s = dict(row.state)
            cleared_any = False
            for ns in namespaces_to_clear:
                if ns in s:
                    s.pop(ns, None)
                    cleared_any = True
            if cleared_any: row.state = s
    db.commit()
    return HTMLResponse(f"<span style='color:var(--accent);'>&#x2713; Nav and Module states cleared for all users.</span>")

@app.post("/rescan")
async def force_rescan():
    from .file_server import get_watchdog
    wd = get_watchdog()
    if not wd: return HTMLResponse("<span style='color:#ffaa44;'>Workspace service not ready yet - try again in a moment.</span>", status_code=503)
    wd.initial_baseline_crawl()
    return HTMLResponse("&#x2713;")

threading.Thread(target=start_workspace_service, args=(ROOT_DIR,), daemon=True).start()
