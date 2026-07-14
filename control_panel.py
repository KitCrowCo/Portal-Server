# backend/control_panel.py
import asyncio
import json
import os
import re
from typing import Optional
from fastapi import APIRouter, Depends, Request, Form, HTTPException, Body
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy.ext.mutable import MutableDict

from .database import get_db, SessionLocal
from .models import User, Notification, Theme, UIString, ServerState
from .auth import hash_password, verify_password, get_current_user
from .style import UI, DEFAULT_THEMES, get_module_default_theme, set_module_default_theme
from .ws_manager import manager as ws_manager
from .state import set_state, get_state, clear_state, resolve_theme_full

# Set this way so that everything matches main.py
_templates: Jinja2Templates = None
def set_templates(t: Jinja2Templates):
    global _templates
    _templates = t

router = APIRouter()
_pre = "/control-panel"

# --- Helpers --- ****** Does control panel not have access to UI? ********************

def _input(name, placeholder="", type_="text", value="", extra=""): return f'<input name="{name}" type="{type_}" placeholder="{placeholder}" value="{value}" {extra} style="background:var(--bg);border:var(--border-thick) solid var(--border);color:var(--text);padding:0.45rem 0.6rem;border-radius:var(--radius);width:100%;box-sizing:border-box;">'
def _label(text): return f'<label style="font-size:0.75rem;color:var(--text_muted);display:block;margin-bottom:0.3rem;">{text}</label>'
def _field(label, input_html): return f'<div>{_label(label)}{input_html}</div>'
def _btn(label, style="", type_="submit"): return f'<button type="{type_}" class="button" style="{style}">{label}</button>'
def _select(name, options_html, extra_style=""): return f'<select name="{name}" style="background:var(--bg); border:var(--border-thick) solid var(--border); color:var(--text); padding:0.45rem; border-radius:var(--radius); width:100%;{extra_style}">{options_html}</select>'

def _valid_folder(base_dir, name): return os.path.isdir(os.path.join(base_dir, name)) and re.fullmatch(r"^(?![\._])[a-zA-Z0-9\-_ ]+$", name) #True if name is a loadable module/tool - not hidden, not __pycache__, matches identifier pattern.

def try_send_ws(notification: Notification):
    payload = {"type": "broadcast", "title": notification.title, "message": notification.message, "payload": json.loads(notification.payload or "{}")}
    try:
        if notification.recipient and notification.recipient != "all": asyncio.create_task(ws_manager.send_personal_message(payload, notification.recipient))
        else: asyncio.create_task(ws_manager.broadcast(payload))
        return True
    except Exception:
        return False

# --- Main shell ---

# Control Panel has limited options for non admin.
@router.get("/", response_class=HTMLResponse)
def control_panel_main(request: Request, user=Depends(get_current_user)):
    if not user: raise HTTPException(403)
    themes_options = "".join(f'<option value="{k}"{" selected" if user.custom_theme == v else ""}>{v["name"]}</option>' for k, v in DEFAULT_THEMES.items())
    nav_items = []
    nav_items += [("Identity", f"{_pre}/account"), ("Appearance", f"{_pre}/appearance")]
    if user.role == "admin": nav_items += [("User Management", f"{_pre}/users"), ("Notifications", f"{_pre}/notifications"), ("Module Access", f"{_pre}/module-access"), ("External Links", f"{_pre}/ext-links"), ("Server Theme", f"{_pre}/theme/server-default")]
    nav_html = "".join(f'<button type="button" hx-get="{url}" hx-target="#cp-content" hx-swap="innerHTML" class="nav-link" style="background:none; border:none; text-align:left; width:100%; padding:0.35rem 0.5rem; cursor:pointer;">{label}</button>' for label, url in nav_items)
    tools_dir = [[json.dumps({'type':'_portal_open_tab', 'path':f'/tool/{f}/', 'label':f.replace("_", " ").title(), 'id':f.replace("_", "-")}), f.replace("_", " ").title()]  for f in sorted(os.listdir("tools")) if _valid_folder("tools", f)]
    tools_options = "".join(f"<option value='{f[0]}'>{f[1]}</option>" for f in  tools_dir)
    htmx = UI.htmx_html({"post": "/im/in", "target": "body", "swap": "none", "trigger": "change", "on::after-request": "this.value=''"})
    inner = f"""<div style="max-width:100rem; margin:0 auto;display:flex; gap:1.5rem; flex-wrap:wrap;padding:1.5rem;">
                  <aside class="glass" style="flex:0 0 17rem; padding:1rem; display:flex; flex-direction:column; gap:0.25rem; height:fit-content;">
                    {nav_html}
                    <hr style="border:none;border-top:var(--border-thick) solid var(--border);margin:0.6rem 0;">
                    <div style="font-size:0.7rem;color:var(--text_muted);padding:0.1rem 0.5rem 0.3rem;">Tools</div>

                    <select name="payload" {htmx} style="background:var(--bg); color:var(--text); border:var(--border-thick) solid var(--border); padding:0.35rem; border-radius:var(--radius); width:100%;">
                      <option value="">Select:</option>
                      {tools_options}
                    </select>

                    <hr style="border:none;border-top:var(--border-thick) solid var(--border);margin:0.6rem 0;">
                    <div style="font-size:0.7rem;color:var(--text_muted);padding:0.1rem 0.5rem 0.3rem;">Theme</div>

                    <form hx-post="{_pre}/theme/switch" hx-swap="none" hx-on::after-request="if(event.detail.successful) window.location.reload()">
                      <select name="theme_mode" onchange="this.form.requestSubmit()" style="background:var(--bg); color:var(--text);border:var(--border-thick) solid var(--border); padding:0.35rem; border-radius:var(--radius); width:100%; cursor:pointer;">
                        {themes_options}
                      </select>
                    </form>
                  </aside>

                  <section id="cp-content" class="glass" style="flex:1; min-width:28rem; padding:1.5rem; min-height:40rem;">
                    <p style="color:var(--text_muted); font-size:0.9rem; margin-top:0;">Select a panel on the left.</p>
                  </section>
                </div>"""
    lvl = int(request.headers.get("x-shell-level", "1"))
    if _templates: return _templates.TemplateResponse(name = "base.html", request = request, context = {"request": request, "user": user, "content": inner, "title": "Control Panel", "nesting_level": lvl})
    return HTMLResponse(inner)

# --- Account ---

@router.get("/account", response_class=HTMLResponse)
def cp_account_fragment(user=Depends(get_current_user)):
    module_opts = "".join(f'<option value="{m}">{m.replace("_"," ").title()}</option>' for m in get_module_list())
    return HTMLResponse(f"""<h3 style="margin-top:0;">Identity: {user.username}</h3>
                                <form hx-post="{_pre}/account/save" hx-target="#account-msg" style="display:flex;flex-direction:column;gap:0.8rem;max-width:36rem;">
                                  {_field("Current Password", _input("current_password","","password"))}
                                  {_field("New Password", _input("new_password","","password"))}
                                  {_btn("Update Credentials")}
                                  <div id="account-msg" style="font-size:0.8rem;min-height:1.2rem;"></div>
                                </form>
                                <div style="margin-top:1.5rem;padding-top:1rem;border-top:var(--border-thick) solid var(--border);">
                                  <div style="font-size:0.8rem;color:var(--text_muted);margin-bottom:0.4rem;">Override theme for a specific module</div>
                                  <select onchange="if(this.value) window.location.href='{_pre}/theme/module-user/'+this.value" style="background:var(--bg);border:var(--border-thick) solid var(--border);color:var(--text);padding:0.4rem;border-radius:var(--radius);width:100%;">
                                    <option value="">Select module...</option>{module_opts}
                                  </select>
                                </div>""")

@router.post("/account/save", response_class=HTMLResponse)
def cp_account_save(current_password: str = Form(None), new_password: str = Form(None), db=Depends(get_db), user=Depends(get_current_user)):
    if not new_password or not current_password: return HTMLResponse("<span style='color:#ffaa44;'>All fields required.</span>")
    if not verify_password(current_password, user.password_hash): return HTMLResponse("<span style='color:#ff5f5f;'>Authentication failure.</span>")
    try:
        user.password_hash = hash_password(new_password)
        db.commit()
        return HTMLResponse("<span style='color:var(--accent);'>Credentials updated.</span>")
    except Exception as e:
        return HTMLResponse(f"<span style='color:#ff5f5f;'>Error: {e}</span>")

# --- Users (Admin) ---

@router.get("/users", response_class=HTMLResponse)
def cp_users_fragment(db=Depends(get_db), admin=Depends(get_current_user)):
    if admin.role != "admin": return HTMLResponse("Unauthorized")
    users = db.query(User).order_by(User.username).all()
    role_opts = lambda cur: "".join(f'<option value="{r}"{"selected" if cur==r else ""}>{r}</option>' for r in ("user","admin","moderator","guest"))
    rows = "".join(f"""
      <tr style="border-bottom:var(--border-bottom) solid var(--border);">
        <td style="padding:0.4rem 0.5rem;">{u.username}</td>
        <td style="padding:0.4rem 0.5rem;color:var(--text_muted);font-size:0.8rem;">{u.role}</td>
        <td style="padding:0.4rem 0.5rem;">
          <div style="display:flex;gap:0.3rem;">
            <form hx-post="{_pre}/users/edit" hx-target="#cp-content" style="display:inline-flex;gap:0.3rem;">
              <input type="hidden" name="username" value="{u.username}">
              <select name="new_role" style="background:var(--bg);border:var(--border-thick) solid var(--border);color:var(--text);font-size:0.75rem;border-radius:var(--radius);padding:0.2rem;">{role_opts(u.role)}</select>
              <button class="btn-icon" title="Set role">&#x2713;</button>
            </form>
            <form hx-post="{_pre}/users/delete" hx-target="#cp-content" hx-confirm="Delete {u.username}?">
              <input type="hidden" name="username" value="{u.username}">
              <button class="btn-icon" style="color:#ff5f5f;" title="Delete">&#x2715;</button>
            </form>
          </div>
        </td>
      </tr>""" for u in users)
    return HTMLResponse(f"""
    <h3 style="margin-top:0;">User Management</h3>
    <form hx-post="{_pre}/users/add" hx-target="#cp-content" style="display:flex;gap:0.5rem;flex-wrap:wrap;align-items:flex-end;margin-bottom:1.5rem;">
      <div style="flex:1;min-width:11rem;">{_field("Username", _input("username","Username"))}</div>
      <div style="flex:1;min-width:11rem;">{_field("Password", _input("password","Password","password"))}</div>
      <div>{_field("Role", _select("role",'<option value="user">User</option><option value="admin">Admin</option>','width:auto;'))}</div>
      <div style="padding-bottom:0.1rem;">{_btn("Add")}</div>
    </form>
    <table style="width:100%;border-collapse:collapse;font-size:0.85rem;">
      <tr style="color:var(--text_muted);border-bottom:var(--border-bottom) solid var(--border);text-align:left;">
        <th style="padding:0.4rem 0.5rem;">User</th><th>Role</th><th>Actions</th>
      </tr>{rows}
    </table>""")

@router.post("/users/add", response_class=HTMLResponse)
def cp_users_add(username: str = Form(...), password: str = Form(...), role: str = Form("user"), db=Depends(get_db), admin=Depends(get_current_user)):
    if admin.role != "admin": return HTMLResponse("Denied")
    if db.query(User).filter(User.username == username).first(): return HTMLResponse("Identity already exists.")
    db.add(User(username=username, password_hash=hash_password(password), role=role))
    db.commit()
    return cp_users_fragment(db=db, admin=admin)

@router.post("/users/edit", response_class=HTMLResponse)
def cp_users_edit(username: str = Form(...), new_role: str = Form(...), db=Depends(get_db), admin=Depends(get_current_user)):
    if admin.role != "admin": return HTMLResponse("Denied")
    u = db.query(User).filter(User.username == username).first()
    if u: u.role = new_role; db.commit()
    return cp_users_fragment(db=db, admin=admin)

@router.post("/users/delete", response_class=HTMLResponse)
def cp_users_delete(username: str = Form(...), db=Depends(get_db), admin=Depends(get_current_user)):
    if admin.role != "admin": return HTMLResponse("Denied")
    u = db.query(User).filter(User.username == username).first()
    if u: db.delete(u); db.commit()
    return cp_users_fragment(db=db, admin=admin)

def validate_module_name(name: str) -> bool:
    if name.startswith(".") or name.startswith("_"): return False
    return bool(re.fullmatch(r"^(?![\._])[a-zA-Z0-9\-_ ]+$", name))

def get_module_list(module_type="module"):
    modules_path = f"./{module_type}s"
    if not os.path.exists(modules_path): return []
    return [d for d in os.listdir(modules_path) if os.path.isdir(os.path.join(modules_path, d)) and validate_module_name(d)]

@router.get("/module-access", response_class=HTMLResponse)
async def cp_module_access(request: Request, user=Depends(get_current_user)):
    if user.role != "admin": return HTMLResponse("Unauthorized")
    cfg = await get_state(request, scope = "single", namespace = "_portal", key = "module_access")
    form = await request.form()
    modules = get_module_list()
    new_cfg = {}
    for m in modules:
        allowed = form.getlist(f"mod_{m}")
        if allowed: new_cfg[m] = allowed
    await set_state(request, new_cfg, scope = "single", namespace = "_portal", key = "module_access")
    return HTMLResponse("<span style='color:var(--accent);'>&#x2713; Saved.</span>")

@router.get("/module-access", response_class=HTMLResponse)
async def cp_module_access(request: Request, user=Depends(get_current_user)):
    if user.role != "admin": return HTMLResponse("Unauthorized")
    cfg = await get_state(request, scope = "single", namespace = "_portal", key = "module_access")
    all_roles = ["admin", "moderator", "user", "guest"]
    modules = get_module_list()
    rows = ""
    for m in modules:
        allowed = cfg.get(m, [])
        role_checks = "".join(f"""<label style="margin-right:0.5rem; font-size:0.8rem;"><input type="checkbox" name="mod_{m}" value="{r}" {"checked" if r in allowed else ""}> {r}</label>""" for r in all_roles)
        rows += f"""<tr style="border-bottom:var(--border-thick) solid var(--border);">
            <td style="padding:0.4rem 0.6rem; font-family:monospace; font-size:0.85rem;">{m}</td>
            <td style="padding:0.4rem 0.6rem;">{role_checks}</td>
        </tr>"""

    return HTMLResponse(f"""
    <h3 style="margin-top:0;">Module Access Control</h3>
    <p style="color:var(--text_muted); font-size:0.8rem; margin-bottom:1rem;">
        Unchecked modules are accessible to all roles. Check at least one role to restrict access.
    </p>
    <form hx-post="{_pre}/module-access/save" hx-target="#ma-result">
      <table style="width:100%; border-collapse:collapse; font-size:0.85rem;">
        <tr style="color:var(--text_muted); border-bottom:var(--border-thick) solid var(--border);">
          <th style="text-align:left; padding:0.4rem 0.6rem;">Module</th>
          <th style="text-align:left; padding:0.4rem 0.6rem;">Allowed Roles (empty = all)</th>
        </tr>
        {rows}
      </table>
      <button type="submit" class="button" style="margin-top:1rem;">Save Access Config</button>
      <div id="ma-result" style="font-size:0.8rem; margin-top:0.5rem; min-height:1rem;"></div>
    </form>""")

@router.post("/module-access/save", response_class=HTMLResponse)
async def cp_module_access_save(request: Request, user=Depends(get_current_user)):
    if user.role != "admin": return HTMLResponse("Unauthorized")
    form = await request.form()
    modules = get_module_list()
    new_cfg = {}
    for m in modules:
        allowed = form.getlist(f"mod_{m}")
        if allowed: new_cfg[m] = allowed
    await set_state(request, new_cfg, scope = "single", namespace = "_portal", key = "module_access")
    return HTMLResponse("<span style='color:var(--accent);'>&#x2713; Saved.</span>")

# --- Notifications (Admin) ---

@router.get("/notifications", response_class=HTMLResponse)
def cp_notifications_fragment(db=Depends(get_db), user=Depends(get_current_user)):
    if user.role != "admin": return HTMLResponse("Unauthorized")
    all_users = [u.username for u in db.query(User).order_by(User.username).all()]
    user_opts = '<option value="all">Everyone</option>' + "".join(f'<option value="{u}">{u}</option>' for u in all_users)
    role_opts = '<option value="">- or by role -</option>' + "".join(f'<option value="{r}">{r}</option>' for r in ("admin","moderator","user","guest"))

    q = db.query(Notification).order_by(Notification.created_at.desc()).limit(30).all()
    history = "".join(f"""
      <div style="padding:0.5rem 0.7rem;border-bottom:var(--border-bottom) solid var(--border);font-size:0.8rem;">
        <div style="display:flex;justify-content:space-between;gap:0.5rem;">
          <b style="color:var(--text);">{n.title or "(no title)"}</b>
          <span style="font-size:0.65rem;white-space:nowrap;color:{'var(--accent)' if n.sent else 'var(--text_muted)'};">{'msg sent' if n.sent else 'queued'}</span>
        </div>
        <div style="color:var(--text_muted);margin:0.2rem 0;font-size:0.78rem;">{n.message}</div>
        <div style="font-size:0.65rem;color:var(--text_muted);display:flex;justify-content:space-between;">
          <span>{n.recipient or "all"}</span>
          <form hx-post="{_pre}/notifications/push" hx-vals='{{"id":"{n.id}"}}' hx-target="#notify-result" style="margin:0;">
            <button style="background:none;border:none;color:var(--accent);cursor:pointer;padding:0;font-size:0.65rem;">re-push</button>
          </form>
        </div>
      </div>""" for n in q) or "<p style='color:var(--text_muted);font-size:0.85rem;padding:0.5rem;'>No notifications yet.</p>"

    return HTMLResponse(f"""
    <h3 style="margin-top:0;">Notifications</h3>
    <div class="glass" style="padding:1rem;margin-bottom:1.5rem;border-radius:var(--radius);">
      <form hx-post="{_pre}/notify" hx-target="#notify-result" style="display:flex;flex-direction:column;gap:0.7rem;">
        <div style="display:flex;gap:0.7rem;flex-wrap:wrap;">
          <div style="flex:1;min-width:13rem;">{_field("Recipient", _select("recipient", user_opts))}</div>
          <div style="flex:1;min-width:13rem;">{_field("Or by role", _select("recipient_role", role_opts))}</div>
        </div>
        {_field("Title", _input("title","Short subject line"))}
        <div>{_label("Message")}<textarea name="message" placeholder="Body text - " style="background:var(--bg);border:var(--border-thick) solid var(--border);color:var(--text);padding:0.45rem;border-radius:var(--radius);width:100%;min-height:7rem;box-sizing:border-box;font-family:inherit;resize:vertical;"></textarea></div>
        {_btn("Send Notification", "align-self:flex-start;")}
        <div id="notify-result" style="font-size:0.8rem;min-height:1.2rem;"></div>
      </form>
    </div>
    <h4 style="color:var(--text_muted);font-size:0.72rem;text-transform:uppercase;letter-spacing:0.1rem;margin:0 0 0.5rem;">Recent</h4>
    <div style="border:var(--border-thick) solid var(--border);border-radius:var(--radius);overflow:hidden;max-height:38rem;overflow-y:auto;">{history}</div>""")

@router.post("/notify", response_class=HTMLResponse)
def cp_notify(recipient: str = Form("all"), recipient_role: str = Form(""), title: str = Form(...), message: str = Form(...), db=Depends(get_db), user=Depends(get_current_user)):
    if user.role != "admin": return HTMLResponse("Unauthorized")
    effective = f"role:{recipient_role}" if recipient_role else (recipient or "all")
    n = Notification(recipient=effective, title=title, message=message, payload="{}")
    db.add(n)
    db.commit()
    if try_send_ws(n): n.sent = True; db.commit()
    return HTMLResponse(f"<span style='color:var(--accent);'>&#x2713; Sent to {effective}.</span>")

@router.post("/notifications/push", response_class=HTMLResponse)
async def cp_notifications_push(request: Request, db=Depends(get_db), user=Depends(get_current_user)):
    if user.role != "admin": return HTMLResponse("Unauthorized")
    form = dict(await request.form())
    nid  = form.get("id")
    if nid:
        n = db.query(Notification).filter(Notification.id == int(nid)).first()
        if n and try_send_ws(n): n.sent = True; db.commit()
    return HTMLResponse("<span style='color:var(--accent);'>&#x2713; Re-pushed.</span>")

# --- External Links ---

@router.get("/ext-links", response_class=HTMLResponse)
async def cp_ext_links(request: Request, user=Depends(get_current_user)):
    if user.role != "admin": return HTMLResponse("Unauthorized")
    links = await get_state(request, scope="single", namespace="_portal", key="ext_links") or []
    rows = "".join(f"""<div class="ext-link-row" style="display:grid;grid-template-columns:2fr 3fr 1fr 3rem;gap:0.5rem;padding:0.3rem 0;align-items:center;">
        <input type="text" class="el-label" value="{UI.escape(l.get('label',''))}" placeholder="Display name" style="background:var(--bg);border:var(--border-thick) solid var(--border);color:var(--text);padding:0.3rem;border-radius:var(--radius);">
        <input type="text" class="el-url" value="{UI.escape(l.get('url',''))}" placeholder="http://host:port" style="background:var(--bg);border:var(--border-thick) solid var(--border);color:var(--text);padding:0.3rem;border-radius:var(--radius);">
        <input type="text" class="el-icon" value="{UI.escape(l.get('icon','&#x1F310;'))}" placeholder="&amp;#xNNNN;" style="background:var(--bg);border:var(--border-thick) solid var(--border);color:var(--text);padding:0.3rem;border-radius:var(--radius);">
        <button type="button" onclick="this.closest('.ext-link-row').remove()" style="background:none;border:none;color:#ff5f5f;cursor:pointer;font-size:1rem;">&#x2715;</button>
    </div>""" for l in links)
    return HTMLResponse(f"""<h3 style="margin-top:0;">External Links</h3>
        <p style="color:var(--text_muted); font-size:0.8rem; margin-bottom:1rem;">
            Any internal service, shown as a nav shortcut and opened as an embedded frame. Include the full address and port (e.g. <code>http://192.168.1.10:3000</code>). Services that refuse to be framed (X-Frame-Options) open in a new tab instead.
        </p>
        <div id="ext-link-rows">{rows}</div>
        <button type="button" class="ui-btn" style="margin-top:0.5rem;" onclick="extLinkAddRow()">+ Add Link</button>
        <button type="button" class="ui-btn" style="margin-top:1rem;display:block;" onclick="extLinkSave()">Save</button>
        <div id="ext-result" style="font-size:0.8rem;margin-top:0.5rem;min-height:1rem;"></div>
        <script>
        function extLinkAddRow(){{
            document.getElementById('ext-link-rows').insertAdjacentHTML('beforeend', `<div class="ext-link-row" style="display:grid;grid-template-columns:2fr 3fr 1fr 3.2rem;gap:0.5rem;padding:0.3rem 0;align-items:center;">
                <input type="text" class="el-label" placeholder="Display name" style="background:var(--bg);border:var(--border-thick) solid var(--border);color:var(--text);padding:0.3rem;border-radius:var(--radius);">
                <input type="text" class="el-url" placeholder="http://host:port" style="background:var(--bg);border:var(--border-thick) solid var(--border);color:var(--text);padding:0.3rem;border-radius:var(--radius);">
                <input type="text" class="el-icon" value="&amp;#x1F310;" style="background:var(--bg);border:var(--border-thick) solid var(--border);color:var(--text);padding:0.3rem;border-radius:var(--radius);">
                <button type="button" onclick="this.closest('.ext-link-row').remove()" style="background:none;border:none;color:#ff5f5f;cursor:pointer;font-size:1rem;">&#x2715;</button>
            </div>`);
        }}
        async function extLinkSave(){{
            const rows = Array.from(document.querySelectorAll('#ext-link-rows .ext-link-row')).map(r => ({{
                label: r.querySelector('.el-label').value.trim(),
                url: r.querySelector('.el-url').value.trim(),
                icon: r.querySelector('.el-icon').value.trim() || '&#x1F310;',
                id: (r.querySelector('.el-label').value.trim() || 'link').toLowerCase().replace(/[^a-z0-9]/g,'-')
            }})).filter(l => l.label && l.url);
            const r = await fetch('{_pre}/ext-links/save', {{method:'POST', headers:{{'Content-Type':'application/json'}}, body: JSON.stringify(rows)}});
            document.getElementById('ext-result').innerHTML = r.ok ? "<span style='color:var(--accent);'>&#x2713; Saved. Reload dashboard to see changes.</span>" : "<span style='color:#ff5f5f;'>Save failed.</span>";
        }}
        </script>""")

@router.post("/ext-links/save")
async def cp_ext_links_save(request: Request, links: list = Body(...), user=Depends(get_current_user)):
    if user.role != "admin": raise HTTPException(403)
    await set_state(request, links, scope="single", namespace="_portal", key="ext_links")
    return {"status": "ok"}

# --- Appearance ---

@router.get("/appearance", response_class=HTMLResponse)
def cp_appearance_fragment(db: Session = Depends(get_db), user=Depends(get_current_user)):
    user_config = getattr(user, "custom_theme", {}) or {}
    if not user_config:
        active = db.query(Theme).filter(Theme.is_active == True).first()
        user_config = active.config if active else {}

    system_vars = set()
    for candidate in ("frontend/templates/base.html", "templates/base.html", "base.html"):
        try:
            system_vars = set(re.findall(r"--([a-zA-Z0-9_-]+)[:)]", open(candidate).read()))
            break
        except OSError:
            pass

    rows_html = ""
    for key, value in sorted(user_config.items()):
        is_system  = key in system_vars
        badge      = f'<span style="font-size:0.6rem;color:{"var(--accent)" if is_system else "var(--text_muted)"};opacity:0.8;">{"sys" if is_system else "custom"}</span>'
        input_type = "color" if str(value).startswith("#") else "text"
        readonly   = 'readonly style="opacity:0.55;"' if is_system else ""
        color_style = "width:3.8rem;height:3rem;padding:.2rem;cursor:pointer;border-radius:.4rem;" if input_type == "color" else "display:none;"
        rows_html += f"""
        <div class="theme-row" style="display:grid;grid-template-columns:1fr 1.5fr 3.2rem;gap:0.7rem;align-items:center;padding:0.4rem 0.5rem;border-bottom:var(--border-bottom) solid var(--border);">
          <div style="display:flex;flex-direction:column;gap:0.1rem;">{badge}<input type="text" class="key-input" value="{key}" {readonly} style="background:var(--bg);border:var(--border-thick) solid var(--border);color:var(--text);padding:0.3rem 0.4rem;border-radius:var(--radius);font-size:0.78rem;font-family:monospace;width:100%;box-sizing:border-box;"></div>
          <div style="display:flex;gap:0.4rem;align-items:center;">
            <input type="{input_type}" value="{value}" oninput="this.nextElementSibling.value=this.value" style="{color_style}">
            <input type="text" value="{value}" class="val-input" oninput="this.previousElementSibling.value=this.value" style="flex:1;background:var(--bg);border:var(--border-thick) solid var(--border);color:var(--text);padding:0.3rem 0.4rem;border-radius:var(--radius);font-size:0.78rem;min-width:0;">
          </div>
          <button type="button" onclick="this.closest('.theme-row').remove()" style="background:none;border:none;color:#ff5f5f;cursor:pointer;font-size:1rem;padding:0;">&#x2715;</button>
        </div>"""

    return HTMLResponse(f"""
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:1rem;">
      <h3 style="margin:0;">Appearance</h3>
      <div style="display:flex;gap:0.4rem;">
        <button type="button" class="button" onclick="downloadTheme()" style="padding:0.3rem 0.6rem;" title="Export JSON">&#x1F4E5;</button>
        <button type="button" class="button" onclick="document.getElementById('theme-upload').click()" style="padding:0.3rem 0.6rem;" title="Import JSON">&#x1F4E4;</button>
        <input type="file" id="theme-upload" style="display:none" accept=".json" onchange="uploadTheme(this)">
      </div>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1.5fr 3.2rem;gap:0.7rem;padding:0.3rem 0.5rem;font-size:0.7rem;color:var(--text_muted);text-transform:uppercase;letter-spacing:0.05rem;border-bottom:var(--border-bottom) solid var(--border);margin-bottom:0.3rem;">
      <div>Variable</div><div>Value</div><div></div>
    </div>
    <div id="theme-editor-list" style="max-height:42vh;overflow-y:auto;">{rows_html}</div>
    <div style="display:flex;gap:0.5rem;margin-top:0.8rem;padding:0.8rem;border:.2rem dashed var(--border);border-radius:var(--radius);">
      <input type="text" id="new-key-name" placeholder="variable_name" style="flex:1;background:var(--bg);border:var(--border-thick) solid var(--border);color:var(--text);padding:0.4rem;border-radius:var(--radius);min-width:0;">
      <input type="text" id="new-key-val"  placeholder="#hex or value"  style="flex:1;background:var(--bg);border:var(--border-thick) solid var(--border);color:var(--text);padding:0.4rem;border-radius:var(--radius);min-width:0;">
      <button type="button" class="button" onclick="addRow()">Add</button>
    </div>
    <div style="display:flex;gap:0.5rem;margin-top:0.8rem;">
      <button type="button" class="button" style="flex:1;" onclick="saveActiveTheme()">&#x1F4BE; Save</button>
      <button type="button" class="button" style="flex:1;background:var(--bg_panel);" onclick="resetDefaults()">&#x21BA; Reset defaults</button>
    </div>
    <script>
      function getEditorData(){{
        const out={{}};
        document.querySelectorAll('#theme-editor-list .theme-row').forEach(row=>{{
          const k=row.querySelector('.key-input')?.value?.trim();
          const v=row.querySelector('.val-input')?.value?.trim();
          if(k) out[k]=v||'';
        }});
        return out;
      }}
      function addRow(){{
        const k=document.getElementById('new-key-name'),v=document.getElementById('new-key-val');
        if(!k.value.trim()) return;
        const isColor=v.value.startsWith('#');
        const cs=isColor?'width:3.8rem;height:3rem;padding:.2rem;cursor:pointer;border-radius:.4rem;':'display:none;';
        document.getElementById('theme-editor-list').insertAdjacentHTML('beforeend',`
          <div class="theme-row" style="display:grid;grid-template-columns:1fr 1.5fr 3.2rem;gap:0.7rem;align-items:center;padding:0.4rem 0.5rem;border-bottom:var(--border-bottom) solid var(--border);">
            <div style="display:flex;flex-direction:column;gap:0.1rem;"><span style="font-size:0.6rem;color:var(--text_muted);">custom</span><input type="text" class="key-input" value="\${{k.value}}" style="background:var(--bg);border:var(--border-thick) solid var(--border);color:var(--text);padding:0.3rem 0.4rem;border-radius:var(--radius);font-size:0.78rem;font-family:monospace;width:100%;box-sizing:border-box;"></div>
            <div style="display:flex;gap:0.4rem;align-items:center;"><input type="color" value="\${{isColor?v.value:'#ffffff'}}" oninput="this.nextElementSibling.value=this.value" style="\${{cs}}"><input type="text" value="\${{v.value}}" class="val-input" oninput="this.previousElementSibling.value=this.value" style="flex:1;background:var(--bg);border:var(--border-thick) solid var(--border);color:var(--text);padding:0.3rem 0.4rem;border-radius:var(--radius);font-size:0.78rem;min-width:0;"></div>
            <button type="button" onclick="this.closest('.theme-row').remove()" style="background:none;border:none;color:#ff5f5f;cursor:pointer;font-size:1rem;padding:0;">&#x2715;</button>
          </div>`);
        k.value=''; v.value='';
      }}
      async function saveActiveTheme(){{
        const r=await fetch('{_pre}/theme/save',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(getEditorData())}});
        if(r.ok) window.location.reload();
      }}
      async function resetDefaults(){{
        if(!confirm('Reset to system defaults?')) return;
        const r=await fetch('{_pre}/theme/defaults');
        if(!r.ok) return;
        const d=await r.json();
        await fetch('{_pre}/theme/save',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(d)}});
        window.location.reload();
      }}
      function downloadTheme(){{
        const blob=new Blob([JSON.stringify(getEditorData(),null,2)],{{type:'application/json'}});
        const a=document.createElement('a'); a.href=URL.createObjectURL(blob); a.download='theme.json'; a.click();
      }}
      function uploadTheme(input){{
        const file=input.files[0]; if(!file) return;
        const reader=new FileReader();
        reader.onload=async(e)=>{{
          try{{
            const config=JSON.parse(e.target.result);
            const r=await fetch('{_pre}/theme/save',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(config)}});
            if(r.ok) window.location.reload();
          }}catch(err){{alert('Invalid JSON');}}
        }};
        reader.readAsText(file);
      }}
    </script>""")

@router.get("/theme/server-default", response_class=HTMLResponse)
async def cp_theme_server_default(user=Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role != "admin": return HTMLResponse("Unauthorized", status_code=403)
    row = db.query(ServerState).first()
    current = {**DEFAULT_THEMES.get("dark", {}), **((row.state or {}).get("_theme", {}).get("server_default", {}) if row and row.state else {})}
    return HTMLResponse(UI.theme_editor_panel(current, save_url=f"{_pre}/theme/server-default/save", title="Server Default Theme"))

@router.post("/theme/server-default/save")
async def cp_theme_server_default_save(config: dict = Body(...), user=Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role != "admin": raise HTTPException(403)
    row = db.query(ServerState).first()
    if not row: row = ServerState(state={}); db.add(row); db.flush()
    state = dict(row.state or {})
    theme_ns = dict(state.get("_theme", {})); theme_ns["server_default"] = config
    state["_theme"] = theme_ns; row.state = state; db.commit()
    return {"status": "ok"}

@router.get("/theme/module-default/{module_ns}", response_class=HTMLResponse)
async def cp_theme_module_default(module_ns: str, user=Depends(get_current_user)):
    if user.role != "admin": return HTMLResponse("Unauthorized", status_code=403)
    return HTMLResponse(UI.theme_editor_panel(get_module_default_theme(module_ns), save_url=f"{_pre}/theme/module-default/{module_ns}/save", title=f"Module Default: {module_ns}"))

@router.post("/theme/module-default/{module_ns}/save")
async def cp_theme_module_default_save(module_ns: str, config: dict = Body(...), user=Depends(get_current_user)):
    if user.role != "admin": raise HTTPException(403)
    set_module_default_theme(module_ns, config)
    return {"status": "ok"}

@router.get("/theme/module-user/{module_ns}", response_class=HTMLResponse)
async def cp_theme_module_user(module_ns: str, request: Request, user=Depends(get_current_user)):
    current = await resolve_theme_full(request, module_ns=module_ns)
    extra = f'''<button type="button" class="button" style="width:100%;background:var(--bg_panel);" onclick="if(confirm('Remove your override and use the default for this module?')) fetch('{_pre}/theme/module-user/{module_ns}/clear',{{method:'POST'}}).then(()=>window.location.reload())">&#x21BA; Clear override</button>'''
    return HTMLResponse(UI.theme_editor_panel(current, save_url=f"{_pre}/theme/module-user/{module_ns}/save", title=f"My Theme Override: {module_ns}", extra_actions=extra))

@router.post("/theme/module-user/{module_ns}/save")
async def cp_theme_module_user_save(module_ns: str, request: Request, config: dict = Body(...), user=Depends(get_current_user)):
    await set_state(request, config, scope="user", namespace=f"_theme_{module_ns}", key="overrides")
    return {"status": "ok"}

@router.post("/theme/module-user/{module_ns}/clear")
async def cp_theme_module_user_clear(module_ns: str, request: Request, user=Depends(get_current_user)):
    await clear_state(request, scope="user", namespace=f"_theme_{module_ns}", key="overrides")
    return {"status": "ok"}

@router.post("/theme/switch", response_class=HTMLResponse)
def cp_theme_switch(theme_mode: str = Form(...), db: Session = Depends(get_db), user=Depends(get_current_user)):
    if theme_mode not in DEFAULT_THEMES: return HTMLResponse("Unknown theme", status_code=400)
    user.custom_theme = DEFAULT_THEMES[theme_mode]
    db.commit()
    return HTMLResponse("OK")
