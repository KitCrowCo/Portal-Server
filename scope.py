"""scope.py - who may do what on this portal, the same for people and AI.

A principal is an account (a person or an AI, both portal users) or a sub-user of one: "<parent>/<name>", made for a task (ephemeral, held in memory) or kept (persisted). A thing is "<kind>:<path>" - file:/data/notes, pool:ingest, pipeline:chat_turn, machine:N2, tool:pause - and a grant names a pattern of things (fnmatch, and every thing under a path: "file:/data/notes" covers "file:/data/notes/a.md").
Acts are ordered: see < use < edit (change without asking) < own (decide about it, remove it, grant it); each includes the ones before.
- A portal admin (the primary user) may do everything; asking is still how the stakes rule is kept for things others own too (others()).
- An account may do what it owns and what it was granted (until a grant runs out).
- A sub-user may do only what it was granted AND what its parent may AND what every account it is also bound by may ("also": a person working through the AI user in Athena is bounded by both).
- Granting needs the act on the thing plus the right to pass it on ("may_grant"), or owning it; a sub-user's grants are checked the same way against its parent.
Nothing here changes data outside its own file (data/_core/scopes.json); places that act (files, pipelines, machines, tools) ask may() / check() before acting.
"""
import json, time, uuid, fnmatch, pathlib, threading

ACTS = ("see", "use", "edit", "own")
RANK = {a: i for i, a in enumerate(ACTS)}
PATH = pathlib.Path("./data/_core/scopes.json")
LOCK = threading.Lock()
DB = {"grants": [], "owners": {}, "subs": {}}   # persisted: grants [{id, to, on, act, may_grant, by, until, note, t}], owners {thing pattern: [principal]}, subs {id: sub-user kept across restarts}
LIVE = {}   # sub-users made for a task, gone with the server: id -> {"parent", "also", "name", "until", "t", "note"}
ACCOUNTS = {"t": 0.0, "users": {}}   # name -> {"role", "kind"}, read from the user table, refreshed every few seconds

# --- Store ---
def load():
    """Reads the stored scopes (once at start); a missing file is an empty store."""
    if PATH.exists(): DB.update(json.loads(PATH.read_text()))
    DB["grants"] = [g for g in DB["grants"] if "/" not in g["to"] or g["to"] in DB["subs"]]   # grants of sub-users made for a task end with the server that held them

def _save():
    PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(DB, indent=1))
    tmp.replace(PATH)

# --- Principals ---
def accounts() -> dict:
    """The portal's accounts as {name: {"role", "kind": "person" | "ai"}} (kind from the account's settings)."""
    if time.time() - ACCOUNTS["t"] > 5:
        from .database import SessionLocal
        from .models import User
        with SessionLocal() as db: ACCOUNTS["users"] = {u.username: {"role": u.role, "kind": (u.settings or {}).get("kind", "person")} for u in db.query(User).all()}
        ACCOUNTS["t"] = time.time()
    return ACCOUNTS["users"]

def set_kind(by: str, name: str, k: str):
    """Marks an account as a person or an AI (its settings "kind"); a primary user may."""
    if not admin(by): raise PermissionError(f"{by} may not change what kind of account {name} is")
    if k not in ("person", "ai"): raise ValueError("kind is person or ai")
    from .database import SessionLocal
    from .models import User
    with SessionLocal() as db:
        u = db.query(User).filter(User.username == name).first()
        if not u: raise KeyError(f"no account {name}")
        u.settings = {**(u.settings or {}), "kind": k}
        db.commit()
    ACCOUNTS["t"] = 0.0

def _sub(p: str) -> dict:
    s = LIVE.get(p) or DB["subs"].get(p)
    return s if s and not (s.get("until") and s["until"] < time.time()) else {}

def known(p: str) -> bool: return p in accounts() or bool(_sub(p))
def admin(p: str) -> bool: return accounts().get(p, {}).get("role") == "admin"
def kind(p: str) -> str: return "sub-user" if "/" in p else accounts().get(p, {}).get("kind", "?")
def subs(parent: str = "") -> dict: return {i: {**s, "kept": i in DB["subs"]} for i, s in [*LIVE.items(), *DB["subs"].items()] if _sub(i) and (not parent or s["parent"] == parent)}

# --- Things ---
def covers(pattern: str, thing: str) -> bool: return fnmatch.fnmatchcase(thing, pattern) or thing.startswith(pattern.rstrip("/") + "/")
def owners(thing: str) -> list: return sorted({o for pat, os_ in DB["owners"].items() if covers(pat, thing) for o in os_})
def others(thing: str, who: str) -> list: return [o for o in owners(thing) if o != who]   # who else must agree to an irreversible change (stakes rule)

# --- Checking ---
def _live(g: dict) -> bool: return not (g.get("until") and g["until"] < time.time())

def _direct(p: str, thing: str, act: str) -> tuple:
    """What p holds itself on the thing: (yes, how)."""
    if p in owners(thing): return True, f"{p} owns it"
    g = next((g for g in DB["grants"] if g["to"] == p and _live(g) and covers(g["on"], thing) and RANK[g["act"]] >= RANK[act]), None)
    return (True, f"""granted {g["act"]} on {g["on"]} by {g["by"]}""") if g else (False, f"{p} holds no grant for {act} on {thing}")

def why(p: str, thing: str, act: str) -> tuple:
    """(may p do act on thing, the reason as one line) - the same answer for a person, an AI account or a sub-user."""
    if act not in RANK: raise ValueError(f"unknown act {act!r} - one of {', '.join(ACTS)}")
    if admin(p): return True, f"{p} is a primary user (admin)"
    if not known(p): return False, f"{p} is no account or live sub-user"
    ok, how = _direct(p, thing, act)
    if not ok or not (s := _sub(p)): return ok, how
    for up in [s["parent"], *s.get("also", [])]:   # a sub-user never holds more than everyone it is bound by
        ok2, how2 = why(up, thing, act)
        if not ok2: return False, f"{how}, but {up} may not ({how2})"
    return True, f"""{how}, within {", ".join([s["parent"], *s.get("also", [])])}"""

def may(p: str, thing: str, act: str) -> bool: return why(p, thing, act)[0]

def check(p: str, thing: str, act: str):
    """Raises PermissionError with the reason when p may not; the place that acts calls this first."""
    ok, how = why(p, thing, act)
    if not ok: raise PermissionError(f"{p} may not {act} {thing}: {how}")

def can_grant(by: str, thing: str, act: str) -> tuple:
    """(may by pass act on thing to another, the reason)."""
    if admin(by) or by in owners(thing): return True, f"{by} owns it" if not admin(by) else f"{by} is a primary user"
    g = next((g for g in DB["grants"] if g["to"] == by and _live(g) and g.get("may_grant") and covers(g["on"], thing) and RANK[g["act"]] >= RANK[act]), None)
    if not g: return False, f"{by} may not pass {act} on {thing} to others"
    return (True, f"""{by} may pass it on (grant {g["id"]})""") if not _sub(by) or may(by, thing, act) else (False, f"{by} holds the grant but not within its parent's scope")

# --- Changing ---
def grant(by: str, to: str, on: str, act: str, may_grant: bool = False, until: float = None, note: str = "") -> dict:
    """A new grant from by to to; refused (PermissionError) when by may not pass it on. until: epoch seconds or None for no end."""
    if act not in RANK: raise ValueError(f"unknown act {act!r} - one of {', '.join(ACTS)}")
    if not known(to): raise ValueError(f"{to} is no account or live sub-user")
    ok, how = can_grant(by, on, act)
    if not ok: raise PermissionError(how)
    g = {"id": uuid.uuid4().hex[:10], "to": to, "on": on, "act": act, "may_grant": bool(may_grant), "by": by, "until": until, "note": note, "t": round(time.time())}
    with LOCK:
        DB["grants"].append(g)
        _save()
    return g

def revoke(by: str, gid: str) -> dict:
    """Ends a grant: its grantor, an owner of what it covers, or a primary user may."""
    g = next((g for g in DB["grants"] if g["id"] == gid), None)
    if not g: raise KeyError(f"no grant {gid}")
    if not (admin(by) or g["by"] == by or by in owners(g["on"])): raise PermissionError(f"""{by} neither gave grant {gid} nor owns {g["on"]}""")
    with LOCK:
        DB["grants"] = [x for x in DB["grants"] if x["id"] != gid]
        _save()
    return g

def set_owners(by: str, thing: str, who: list) -> list:
    """Sets who owns a thing (pattern); empty who: no recorded owner. A primary user may; an owner may while no one else owns it (with other owners, each must agree first - stakes rule)."""
    cur = DB["owners"].get(thing, [])
    if not (admin(by) or (by in cur and not [o for o in cur if o != by])): raise PermissionError(f"""{by} may not change who owns {thing}{" - also owned by " + ", ".join(o for o in cur if o != by) if cur else ""}""")
    with LOCK:
        if who: DB["owners"][thing] = sorted(set(who))
        else: DB["owners"].pop(thing, None)
        _save()
    return DB["owners"].get(thing, [])

def owned() -> dict: return {k: list(v) for k, v in DB["owners"].items()}   # every recorded owner: thing pattern -> owners
def grants(to: str = "", by: str = "") -> list: return [{**g, "live": _live(g)} for g in DB["grants"] if (not to or g["to"] == to) and (not by or g["by"] == by)]

# --- Sub-users ---
def spawn(parent: str, name: str, scope: list = (), also: list = (), keep: bool = False, until: float = None, note: str = "") -> str:
    """A sub-user of parent: "<parent>/<name>", given scope [(thing, act)] (each checked as a grant from parent) and bound also by the accounts in also. keep: stored across restarts (a person's standing access in Athena); otherwise gone with the server or at until."""
    if not known(parent): raise ValueError(f"{parent} is no account or live sub-user")
    sid = f"{parent}/{name}"
    for t, a in scope:
        ok, how = can_grant(parent, t, a)
        if not ok: raise PermissionError(f"{sid} cannot be given {a} on {t}: {how}")
    s = {"parent": parent, "also": list(also), "name": name, "until": until, "t": round(time.time()), "note": note}
    with LOCK:
        (DB["subs"] if keep else LIVE)[sid] = s
        DB["grants"] = [g for g in DB["grants"] if g["to"] != sid] + [{"id": uuid.uuid4().hex[:10], "to": sid, "on": t, "act": a, "may_grant": False, "by": parent, "until": until, "note": note, "t": s["t"]} for t, a in scope]
        _save()
    return sid

def end(by: str, sid: str):
    """Ends a sub-user and its grants: its parent (or anyone above it) or a primary user may."""
    s = _sub(sid) or LIVE.get(sid) or DB["subs"].get(sid)
    if not s: raise KeyError(f"no sub-user {sid}")
    if not (admin(by) or sid.startswith(f"{by}/")): raise PermissionError(f"{by} is not above {sid}")
    with LOCK:
        LIVE.pop(sid, None)
        DB["subs"].pop(sid, None)
        DB["grants"] = [g for g in DB["grants"] if g["to"] != sid and not g["to"].startswith(f"{sid}/")]
        _save()

SERVICE = {"may": may, "why": why, "check": check, "can_grant": can_grant, "grant": grant, "revoke": revoke, "grants": grants, "owners": owners, "owned": owned, "others": others, "set_owners": set_owners, "spawn": spawn, "end": end, "subs": subs, "accounts": accounts, "kind": kind, "set_kind": set_kind, "admin": admin, "acts": ACTS}   # offered to tools and modules as the service "scope"
