# file_server.py
import sqlite3
import pathlib
import threading
import time
import json
import os
from typing import Dict, Any, Optional, Set

# --- Thread-Safe Global State ---
WORKSPACE_LOCK = threading.Lock()
WORKSPACE_REGISTRY: Dict[str, Dict[str, Any]] = {}
DIRTY_PATHS: Set[str] = set()

DATA_DIR = pathlib.Path("/app/data/_core")
DB_FILE = DATA_DIR / "workspace.db"

LAST_SYNC_TIME: float = 0.0
_SERVICE_INITIALIZED = False
_INIT_LOCK = threading.Lock()
_GLOBAL_OBSERVER = None
_GLOBAL_WATCHDOG = None
SNAPSHOT_FILE = DATA_DIR / "file_structure.json"

class FileWatchdog:
    """Handles full startup crawls, real-time path state mutations, and manual sync hooks."""
    def __init__(self, root_path: str, watch_path=None, debounce_delay: float = 2.0):
        self.root = pathlib.Path(root_path).resolve()
        self.watch_path = watch_path
        self.debounce_delay = debounce_delay
        self.skip_dirs = frozenset({".git", "__pycache__", "node_modules", ".trash", ".venv", "venv"})
        self.skip_suffixes = frozenset({".bak", ".pyc", ".pyo"})
        self._timer: Optional[threading.Timer] = None
        self._timer_lock = threading.Lock()
        self._init_db()

    def _init_db(self):
        """Initialize the SQLite schema."""
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        # Timeout for thread safety
        with sqlite3.connect(DB_FILE, timeout=15.0) as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS registry (path TEXT PRIMARY KEY, parent TEXT, type TEXT, data TEXT)""")
            conn.commit()

    def _schedule_db_sync(self):
        """Debounce the database write operations."""
        with self._timer_lock:
            if self._timer is not None: self._timer.cancel()
            self._timer = threading.Timer(self.debounce_delay, self._process_batch_sync)
            self._timer.daemon = True
            self._timer.start()

    def _process_batch_sync(self):
        """Batch update only changed items (dirty paths) to SQLite."""
        global DIRTY_PATHS
        with WORKSPACE_LOCK:
            paths_to_sync = list(DIRTY_PATHS)
            DIRTY_PATHS.clear()
        if not paths_to_sync: return

        with sqlite3.connect(DB_FILE, timeout=15.0) as conn:
            cursor = conn.cursor()
            for path in paths_to_sync:
                # Check if it exists in memory (update) or was deleted
                with WORKSPACE_LOCK:
                    node_data = WORKSPACE_REGISTRY.get(path)
                if node_data:
                    parent = str(pathlib.Path(path).parent)
                    cursor.execute("REPLACE INTO registry (path, parent, type, data) VALUES (?, ?, ?, ?)", (path, parent, node_data['type'], json.dumps(node_data)))
                else:
                    cursor.execute("DELETE FROM registry WHERE path = ?", (path,))
            conn.commit()

    def initial_baseline_crawl(self):
        """Full scan of the filesystem and update both memory and DB."""
        global WORKSPACE_REGISTRY
        new_registry = {}

        # Build in-memory registry
        abs_root = self.root.as_posix()
        new_registry[abs_root] = {"type": "folder", "name": self.root.name, "child_files_count": 0, "direct_children": []}

        for root, dirs, files in os.walk(self.root):
            dirs[:] = [d for d in dirs if d not in self.skip_dirs and not d.startswith(".")]
            current_dir = pathlib.Path(root).resolve()
            abs_dir = current_dir.as_posix()

            if abs_dir not in new_registry: new_registry[abs_dir] = {"type": "folder", "name": current_dir.name, "child_files_count": 0, "direct_children": []}

            if current_dir != self.root:
                parent_abs = current_dir.parent.as_posix()
                if parent_abs in new_registry and abs_dir not in new_registry[parent_abs]["direct_children"]: new_registry[parent_abs]["direct_children"].append(abs_dir)

            for f in files:
                if f.startswith(".") and f != ".env": continue
                file_path = current_dir / f
                if file_path.suffix.lower() in self.skip_suffixes: continue

                abs_file = file_path.as_posix()
                try: size = file_path.stat().st_size
                except (ValueError, FileNotFoundError): continue

                new_registry[abs_file] = {"type": "file", "name": f, "size": size, "suffix": file_path.suffix.lower()}
                new_registry[abs_dir]["direct_children"].append(abs_file)

        # Calculate directory file counts
        for path_key, node in list(new_registry.items()):
            if node["type"] == "folder":
                prefix = path_key + "/"
                node["child_files_count"] = sum(1 for k, v in new_registry.items() if v["type"] == "file" and k.startswith(prefix))

        # Atomic update to memory and full DB sync
        with WORKSPACE_LOCK:
            WORKSPACE_REGISTRY = new_registry
            # Clear DB and rebuild
            with sqlite3.connect(DB_FILE, timeout=15.0) as conn:
                conn.execute("DELETE FROM registry")
                data_to_insert = [(p, str(pathlib.Path(p).parent), v['type'], json.dumps(v)) for p, v in new_registry.items()]
                conn.executemany("INSERT INTO registry (path, parent, type, data) VALUES (?, ?, ?, ?)", data_to_insert)
                conn.commit()

    def patch_node(self, absolute_path: str, event_type: str):
        """Update memory and queue for database sync."""
        file_path = pathlib.Path(absolute_path).resolve()

        if file_path.suffix.lower() in self.skip_suffixes: return
        if any(part in self.skip_dirs or (part.startswith(".") and part != ".env") for part in file_path.parts): return

        abs_path = file_path.as_posix()
        parent_abs = file_path.parent.as_posix()

        with WORKSPACE_LOCK:
            if event_type == "deleted":
                if abs_path in WORKSPACE_REGISTRY:
                    WORKSPACE_REGISTRY.pop(abs_path)
                    DIRTY_PATHS.add(abs_path)
            else:
                try:
                    # Robust stat check for transient files
                    stat = file_path.stat()
                    is_dir = file_path.is_dir()
                    new_node = {"type": "folder" if is_dir else "file", "name": file_path.name, "size": stat.st_size if not is_dir else 0}
                    if not is_dir: new_node["suffix"] = file_path.suffix.lower()
                    WORKSPACE_REGISTRY[abs_path] = new_node
                    DIRTY_PATHS.add(abs_path)
                except (FileNotFoundError, PermissionError):
                    return

        self._schedule_db_sync()

# --- External Hooks ---

def notify_manual_mutation(absolute_paths: list[str], event_type: str = "modified"):
    """Hook for FileManager to manually push state changes immediately, bypassing watchdog delays."""
    global _GLOBAL_WATCHDOG
    if not _GLOBAL_WATCHDOG: return
    for path in absolute_paths:
        _GLOBAL_WATCHDOG.patch_node(path, event_type)

def get_watchdog(): return _GLOBAL_WATCHDOG

def start_workspace_service(root_path: str = None):
    global _SERVICE_INITIALIZED, _GLOBAL_WATCHDOG, _GLOBAL_OBSERVER
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler

    class DynamicTreeHandler(FileSystemEventHandler):
        def __init__(self, scanner: FileWatchdog): self.scanner = scanner
        def on_created(self, event): self.scanner.patch_node(event.src_path, "created")
        def on_modified(self, event): self.scanner.patch_node(event.src_path, "modified")
        def on_deleted(self, event): self.scanner.patch_node(event.src_path, "deleted")
        def on_moved(self, event):
            self.scanner.patch_node(event.src_path, "deleted")
            self.scanner.patch_node(event.dest_path, "created")

    with _INIT_LOCK:
        if _SERVICE_INITIALIZED: return _GLOBAL_OBSERVER
        _SERVICE_INITIALIZED = True  # claimed immediately - the crawl below runs outside the lock so concurrent reads see a partial/empty registry instead of blocking, never a duplicate crawl
        root = root_path or os.getenv("APP_ROOT", "/app")
        _GLOBAL_WATCHDOG = FileWatchdog(root_path=root)

    _GLOBAL_WATCHDOG.initial_baseline_crawl()

    if os.path.exists(root):
        observer = Observer()
        observer.schedule(DynamicTreeHandler(_GLOBAL_WATCHDOG), path=root, recursive=True)
        observer.start()
        with _INIT_LOCK: _GLOBAL_OBSERVER = observer
    return _GLOBAL_OBSERVER

class FileStructure:
    @staticmethod
    def get_synchronous_slice(abs_path: str) -> list:
        """Looks up absolute path against flat registry entirely in-memory."""
        if not _SERVICE_INITIALIZED: start_workspace_service()
        if not abs_path: return []

        target_path = pathlib.Path(abs_path).resolve().as_posix()
        results = []

        parent_node = WORKSPACE_REGISTRY.get(target_path)
        if not parent_node or parent_node.get("type") != "folder": return []

        for child_key in parent_node.get("direct_children", []):
            child_node = WORKSPACE_REGISTRY.get(child_key)
            if child_node: results.append((child_key, child_node))

        results.sort(key=lambda x: (x[1].get("type") != "folder", x[1].get("name", "").lower()))
        return results

    @staticmethod
    def _normalize_path(user_provided_path: str) -> str:
        """Translates a user-provided path into the absolute key format used in the registry."""
        # If the path already looks absolute, return it resolved
        if user_provided_path.startswith("/app"): return pathlib.Path(user_provided_path).resolve().as_posix()
        # If the path is relative (e.g., 'notes.md' or '_common/notes.md'), force it into the absolute namespace of the Wiki's context.
        virtual_root = "/app/data/_common"
        full_path = pathlib.Path(virtual_root) / user_provided_path.lstrip("/")
        return full_path.resolve().as_posix()

    @staticmethod
    def get_node(abs_path: str) -> Optional[dict]:
        """Safely fetch a specific node from memory without touching the disk."""
        if not _SERVICE_INITIALIZED: start_workspace_service()
        return WORKSPACE_REGISTRY.get(FileStructure._normalize_path(abs_path))
