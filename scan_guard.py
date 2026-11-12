# scan_guard.py - slows down sources that probe for paths that do not exist (vulnerability scanners), without touching normal use.
# Every 404 a source causes adds 1 to its score; the score halves every SCAN_HALF_LIFE_S seconds, so a source that stops returns to normal on its own.
# At SCAN_THRESHOLD or above, the source's requests are answered 429 before any other work, and each refused request adds to the score too - persisting makes the wait longer.
# Signed-in users' 404s do not count. SCAN_EXEMPT lists addresses or networks never counted (comma-separated, e.g. 192.168.0.0/24,10.0.0.5); loopback is always exempt.
# The address is request.client.host: behind a reverse proxy that is the X-Forwarded-For value ProxyHeadersMiddleware accepted, so its trusted_hosts decides whether a client can forge it.
import os, time, math, ipaddress
from fastapi.responses import PlainTextResponse
from jose import jwt, JWTError
from .auth import SECRET_KEY, ALGORITHM

THRESHOLD, HALF_LIFE = float(os.getenv("SCAN_THRESHOLD", "8")), float(os.getenv("SCAN_HALF_LIFE_S", "600"))
EXEMPT = [ipaddress.ip_network(n.strip(), strict=False) for n in os.getenv("SCAN_EXEMPT", "").split(",") if n.strip()]
_SCORES: dict = {}   # address -> [score, time of last update]
CLIENT_HEADER = os.getenv("SCAN_CLIENT_HEADER", "").strip().lower()

def _exempt(addr: str) -> bool:
    try: ip = ipaddress.ip_address(addr)
    except ValueError: return False
    return ip.is_loopback or any(ip in n for n in EXEMPT)

def _score(addr: str, add: float = 0.0) -> float:
    """The address's decayed score, after adding add."""
    s, t = _SCORES.get(addr, (0.0, time.time()))
    s = s * 0.5 ** ((time.time() - t) / HALF_LIFE) + add
    if s < 0.05: _SCORES.pop(addr, None)
    else: _SCORES[addr] = [s, time.time()]
    if len(_SCORES) > 20000: _prune()
    return s

def _prune():
    """Drops addresses whose score has decayed to nothing (keeps memory bounded when many sources each probe a little)."""
    now = time.time()
    for a, (s, t) in list(_SCORES.items()):
        if s * 0.5 ** ((now - t) / HALF_LIFE) < 0.05: del _SCORES[a]

def _signed_in(request) -> bool:
    token = request.cookies.get("access_token") or (request.headers.get("authorization", "")[7:] if request.headers.get("authorization", "").startswith("Bearer ") else "")
    if not token: return False
    try: return bool(jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM]).get("sub"))
    except JWTError: return False

def _client(request) -> str: return (request.headers.get(CLIENT_HEADER, "").split(",")[0].strip() if CLIENT_HEADER else "") or (request.client.host if request.client else "")

def install(app):
    @app.middleware("http")
    async def scan_guard(request, call_next):
        addr = _client(request)
        if not addr or _exempt(addr) or _signed_in(request): return await call_next(request)
        if not addr or _exempt(addr): return await call_next(request)
        if (s0 := _score(addr)) >= THRESHOLD:
            s = _score(addr, 1.0)
            if s0 < THRESHOLD + 1: print(f"[SCAN] {addr} refused (score {s:.1f}): too many requests for paths that do not exist", flush=True)   # once, as the block starts
            return PlainTextResponse("Too many requests for missing pages - try again later.", status_code=429, headers={"Retry-After": str(int(HALF_LIFE * math.log2(s / THRESHOLD)) + 1)})
        response = await call_next(request)
        if response.status_code == 404 and not getattr(request.state, "user", None): _score(addr, 1.0)
        return response
