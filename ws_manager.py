# ws_manager.py
import asyncio, json, logging
from typing import Dict, List
from fastapi import WebSocket

logger = logging.getLogger("ws_manager")
logger.setLevel(logging.WARNING)

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}
        self._listeners = [] # List of async callbacks
        self._lock = asyncio.Lock()

    def subscribe(self, callback): self._listeners.append(callback) # Allows a module to register a listener: ENV['tools']['ws'].subscribe(my_func)

    async def on_incoming_message(self, user_id: str, data: dict):
        """Called by the platform route; notifies all modular subscribers."""
        for callback in self._listeners:
            asyncio.create_task(callback(user_id, data)) # Each module checks for its own 'namespace' or 'intent' inside its own sandbox

    async def connect(self, user_id: str, websocket: WebSocket):
        """Register an already-accepted websocket for user_id."""
        # NOTE: caller must accept() before calling this - do NOT accept here
        async with self._lock:                          # whole block under lock
            conns = self.active_connections.get(user_id)
            if conns is None: self.active_connections[user_id] = [websocket]
            else: conns.append(websocket)
        logger.info("WS connect: %s (users: %d)", user_id, len(self.active_connections))

    async def disconnect(self, user_id: str, websocket: WebSocket):
        """Remove websocket for user_id and close quietly."""
        async with self._lock:
            conns = self.active_connections.get(user_id)
            if conns:
                try: conns.remove(websocket)
                except ValueError: pass
                if not conns: self.active_connections.pop(user_id, None)
        try: await websocket.close()
        except Exception: pass
        logger.info("WS disconnect: %s (users: %d)", user_id, len(self.active_connections))

    async def _safe_send(self, websocket: WebSocket, payload) -> bool:
        try:
            if isinstance(payload, (dict, list)): await websocket.send_json(payload)
            else: await websocket.send_text(str(payload))
            return True
        except Exception as e:
            logger.debug("WS send error: %s", e)
            return False

    async def _prune_dead(self, user_id: str, dead: List[WebSocket]):
        """Removes dead sockets from the registry and force-closes them - a failed send alone doesn't guarantee the client's own WebSocket object ever fires 'close', which leaves a phantom connection that neither side will re-establish on its own."""
        async with self._lock:
            cur = self.active_connections.get(user_id, [])
            for d in dead:
                try: cur.remove(d)
                except ValueError: pass
            if not cur: self.active_connections.pop(user_id, None)
        for d in dead:
            try: await d.close()
            except Exception: pass

    async def send_personal_message(self, message, user_id: str):
        """Send to all connections for user_id, prune dead sockets."""
        async with self._lock: conns = list(self.active_connections.get(user_id, []))
        dead = [ws for ws in conns if not await self._safe_send(ws, message)]
        if dead: await self._prune_dead(user_id, dead)

    async def heartbeat_loop(self, interval: float = 25.0):
        """Periodic keepalive broadcast. Without this, an idle proxy/firewall timeout silently kills the socket and pushed updates (streaming, live status) just stop arriving until the page is reloaded. A failed send now triggers _prune_dead's explicit close(), which the client's reconnect logic in base.html actually picks up."""
        while True:
            await asyncio.sleep(interval)
            try: await self.broadcast({"t": "ping"})
            except Exception: pass

    async def send_to_users(self, message, user_ids: List[str]): await asyncio.gather(*[self.send_personal_message(message, uid) for uid in user_ids], return_exceptions=True)

    async def broadcast(self, message):
        async with self._lock: users = list(self.active_connections.keys())
        await asyncio.gather(*[self.send_personal_message(message, uid) for uid in users], return_exceptions=True)

    def get_stats(self) -> dict: return {"users": len(self.active_connections), "connections": sum(len(v) for v in self.active_connections.values())}

    # --- Module push helpers (injected into ENV["tools"]["ws"]) ---
    async def push(self, user_id: str, event: str, payload: dict): await self.send_personal_message({"type": event, "payload": payload}, user_id) # Typed event push for module use: push(user, 'update', {...})

    async def push_all(self, event: str, payload: dict): await self.broadcast({"type": event, "payload": payload})

manager = ConnectionManager()