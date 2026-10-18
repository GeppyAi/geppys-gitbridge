import os
import sys
import json
import socket
import time
import subprocess
import webbrowser
import threading
import re
from typing import Dict, Any, Optional, List, Set

try:
    import psutil
except ImportError:
    psutil = None

# Active Localhost Process Tracker
# Schema: slug -> {
#   "slug": str,
#   "name": str,
#   "process": subprocess.Popen,
#   "pid": int,
#   "all_pids": list[int],
#   "port": int,
#   "all_ports": list[int],
#   "url": str,
#   "command": str,
#   "folder_path": str,
#   "started_at": float,
#   "status": str,
#   "metrics": dict
# }
ACTIVE_SERVERS: Dict[str, Dict[str, Any]] = {}
_STATE_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "db", "active_servers.json")
_WORKSPACE_APP_MAP_CACHE: Dict[str, Dict[str, str]] = {}
_WORKSPACE_APP_MAP_TIME: float = 0.0


def _save_active_servers_state():
    """Persist serializable ACTIVE_SERVERS metadata to disk so server restarts never lose track of running apps."""
    try:
        os.makedirs(os.path.dirname(_STATE_FILE), exist_ok=True)
        serializable = {}
        for slug, info in list(ACTIVE_SERVERS.items()):
            serializable[slug] = {
                "slug": slug,
                "name": info.get("name", slug),
                "pid": info.get("pid"),
                "all_pids": info.get("all_pids", []),
                "port": info.get("port"),
                "all_ports": info.get("all_ports", [info.get("port")] if info.get("port") else []),
                "url": info.get("url"),
                "command": info.get("command", ""),
                "folder_path": info.get("folder_path", ""),
                "started_at": info.get("started_at", time.time()),
                "status": info.get("status", "healthy"),
            }
        with open(_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(serializable, f, indent=2)
    except Exception:
        pass


def _load_active_servers_state():
    """Restore persisted ACTIVE_SERVERS metadata on startup."""
    if not os.path.exists(_STATE_FILE):
        return
    try:
        with open(_STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            for slug, info in data.items():
                if isinstance(info, dict) and slug not in ACTIVE_SERVERS:
                    info["process"] = None
                    info.setdefault("metrics", {
                        "memory_mb": 0.0,
                        "cpu_percent": 0.0,
                        "uptime_seconds": 0,
                        "uptime_str": "0s",
                        "child_pids": [],
                        "is_port_listening": True
                    })
                    ACTIVE_SERVERS[slug] = info
    except Exception:
        pass


def _notify_tray_menu_refresh():
    """Notify the Windows System Tray icon (if active) to rebuild its dynamic menu."""
    try:
        from gitbridge.tray_app import refresh_tray_menu
        refresh_tray_menu()
    except Exception:
        pass


def _get_workspace_apps_lookup() -> Dict[str, Dict[str, str]]:
    """Return a cached mapping of normalized local folder paths -> {slug, name, folder_path}."""
    global _WORKSPACE_APP_MAP_CACHE, _WORKSPACE_APP_MAP_TIME
    now = time.time()
    if _WORKSPACE_APP_MAP_CACHE and (now - _WORKSPACE_APP_MAP_TIME < 12.0):
        return _WORKSPACE_APP_MAP_CACHE

    mapping: Dict[str, Dict[str, str]] = {}
    try:
        from gitbridge.db.database import SessionLocal
        from gitbridge.db.models import AppProfileModel
        from gitbridge.services.workspace_service import WorkspaceService

        db = SessionLocal()
        try:
            apps = db.query(AppProfileModel).all()
            for a in apps:
                if a.slug in ("geppys-gitbridge", "geppy-s-gitbridge", "gitbridge"):
                    continue
                lpath = a.local_path
                if lpath and os.path.exists(lpath):
                    norm_p = os.path.normcase(os.path.abspath(lpath))
                    mapping[norm_p] = {
                        "slug": a.slug,
                        "name": a.name,
                        "folder_path": os.path.abspath(lpath)
                    }
        finally:
            db.close()

        # Also scan workspace directories directly for any folders not yet in local_path
        for wdir in WorkspaceService.get_workspace_dirs():
            if os.path.exists(wdir):
                for entry in os.listdir(wdir):
                    full_p = os.path.join(wdir, entry)
                    if os.path.isdir(full_p) and entry not in (".git", ".venv", "venv", "node_modules", "__pycache__"):
                        norm_p = os.path.normcase(os.path.abspath(full_p))
                        if norm_p not in mapping:
                            slug = entry.lower().replace("'", "-").replace("’", "-").replace(" ", "-").replace("_", "-").replace("--", "-").strip("-")
                            if slug not in ("geppys-gitbridge", "geppy-s-gitbridge", "gitbridge"):
                                mapping[norm_p] = {
                                    "slug": slug,
                                    "name": entry,
                                    "folder_path": os.path.abspath(full_p)
                                }
    except Exception:
        pass

    _WORKSPACE_APP_MAP_CACHE = mapping
    _WORKSPACE_APP_MAP_TIME = now
    return mapping


_SERVER_BOOT_TIME: float = time.time()
_PID_APP_CACHE: Dict[int, Dict[str, Any]] = {}


class ServerMonitor:
    """Background daemon thread monitoring active app servers, detecting terminations,
    auto-discovering running workspace apps on OS ports, tracking CPU/memory telemetry, and preventing port conflicts."""
    _thread: Optional[threading.Thread] = None
    _stop_event = threading.Event()
    _lock = threading.RLock()
    _last_signature: str = ""
    _last_check_time: float = 0.0

    @classmethod
    def start(cls):
        """Start the background monitor daemon if not already running."""
        _load_active_servers_state()
        with cls._lock:
            if cls._thread is None or not cls._thread.is_alive():
                cls._stop_event.clear()
                cls._thread = threading.Thread(target=cls._monitor_loop, daemon=True, name="ServerMonitorThread")
                cls._thread.start()

    @classmethod
    def stop(cls):
        """Signal monitor thread to stop."""
        cls._stop_event.set()

    @classmethod
    def _monitor_loop(cls):
        """Periodic health check and metrics collection loop."""
        while not cls._stop_event.is_set():
            try:
                cls.check_servers_health()
            except Exception:
                pass
            time.sleep(2.5)

    @classmethod
    def _reconcile_os_workspace_processes(cls, all_listening_ports: Set[int], tcp_conns: Optional[List[Any]] = None):
        """Discover any localhost listening processes running inside workspace app directories
        so apps launched from Galactic, terminal, or prior sessions always appear in System Tray & Port Watcher."""
        if not psutil:
            return

        app_lookup = _get_workspace_apps_lookup()
        if not app_lookup:
            return

        discovered_by_slug: Dict[str, Dict[str, Any]] = {}

        if tcp_conns is None:
            try:
                tcp_conns = psutil.net_connections(kind='tcp')
            except Exception:
                return

        if len(_PID_APP_CACHE) > 512:
            _PID_APP_CACHE.clear()

        for conn in tcp_conns:
            if conn.status != 'LISTEN' or not conn.laddr or not conn.pid:
                continue
            port = conn.laddr.port
            if port in (8000, 8001) or port < 1024 or port > 65000:
                continue

            pid = conn.pid
            cached = _PID_APP_CACHE.get(pid)
            if cached is not None:
                matched_app = cached.get("matched_app")
                root_pid = cached.get("root_pid", pid)
                cmd_str = cached.get("cmd_str", "")
            else:
                matched_app = None
                root_pid = pid
                cmd_str = ""
                try:
                    proc = psutil.Process(pid)
                    proc_name = (proc.name() or "").lower()
                    if "localharness" in proc_name or "antigravity" in proc_name:
                        _PID_APP_CACHE[pid] = {"matched_app": None, "root_pid": pid, "cmd_str": ""}
                        continue
                    chain = [proc] + proc.parents()[:4]
                    for p in chain:
                        try:
                            p_cwd = p.cwd()
                            if p_cwd:
                                norm_cwd = os.path.normcase(os.path.abspath(p_cwd))
                                for app_norm_path, app_meta in app_lookup.items():
                                    if norm_cwd == app_norm_path or norm_cwd.startswith(app_norm_path + os.sep):
                                        matched_app = app_meta
                                        root_pid = p.pid
                                        if not cmd_str:
                                            try:
                                                cmd_str = " ".join(p.cmdline())[:180]
                                            except Exception:
                                                pass
                                        break
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            continue
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

                _PID_APP_CACHE[pid] = {
                    "matched_app": matched_app,
                    "root_pid": root_pid,
                    "cmd_str": cmd_str
                }

            if matched_app:
                slug = matched_app["slug"]
                entry = discovered_by_slug.setdefault(slug, {
                    "slug": slug,
                    "name": matched_app["name"],
                    "folder_path": matched_app["folder_path"],
                    "ports": set(),
                    "pids": set(),
                    "root_pid": root_pid,
                    "command": cmd_str or "Local App Server"
                })
                entry["ports"].add(port)
                entry["pids"].add(pid)
                entry["pids"].add(root_pid)

        for slug, disc in discovered_by_slug.items():
            ports_sorted = sorted(list(disc["ports"]))
            # Prefer Vite/frontend port (5173+, 3000+, 8080+) over backend API port 5000 when both exist
            primary_port = ports_sorted[0]
            if len(ports_sorted) > 1:
                non_5000 = [p for p in ports_sorted if p >= 5170 or p != 5000]
                if non_5000:
                    primary_port = non_5000[0]

            if slug in ACTIVE_SERVERS:
                existing = ACTIVE_SERVERS[slug]
                existing_ports = set(existing.get("all_ports") or [])
                if existing.get("port"):
                    existing_ports.add(existing["port"])
                merged_ports = sorted(list(existing_ports | disc["ports"]))
                existing["all_ports"] = merged_ports
                # Update primary port if current primary isn't listening or was backend port 5000
                if existing.get("port") not in all_listening_ports or (existing.get("port") == 5000 and primary_port != 5000):
                    existing["port"] = primary_port
                    existing["url"] = f"http://localhost:{primary_port}"
                existing_pids = set(existing.get("all_pids") or [])
                if existing.get("pid"):
                    existing_pids.add(existing["pid"])
                existing["all_pids"] = sorted(list(existing_pids | disc["pids"]))
                if not existing.get("pid"):
                    existing["pid"] = disc["root_pid"]
            else:
                ACTIVE_SERVERS[slug] = {
                    "slug": slug,
                    "name": disc["name"],
                    "process": None,
                    "pid": disc["root_pid"],
                    "all_pids": sorted(list(disc["pids"])),
                    "port": primary_port,
                    "all_ports": ports_sorted,
                    "url": f"http://localhost:{primary_port}",
                    "command": disc["command"],
                    "folder_path": disc["folder_path"],
                    "started_at": time.time(),
                    "status": "healthy",
                    "metrics": {
                        "memory_mb": 0.0,
                        "cpu_percent": 0.0,
                        "uptime_seconds": 0,
                        "uptime_str": "0s",
                        "child_pids": [],
                        "is_port_listening": True
                    }
                }

    @classmethod
    def check_servers_health(cls):
        """Inspect all running servers, reconcile OS workspace ports, collect metrics, and prune dead servers."""
        tcp_conns = None
        all_listening_ports: Set[int] = set()
        if psutil:
            try:
                tcp_conns = psutil.net_connections(kind='tcp')
                for conn in tcp_conns:
                    if conn.status == 'LISTEN' and conn.laddr:
                        all_listening_ports.add(conn.laddr.port)
            except Exception:
                all_listening_ports = AppLauncherService.get_all_listening_ports()
        else:
            all_listening_ports = AppLauncherService.get_all_listening_ports()

        should_notify = False
        with cls._lock:
            cls._last_check_time = time.time()
            cls._reconcile_os_workspace_processes(all_listening_ports, tcp_conns=tcp_conns)

            for slug, info in list(ACTIVE_SERVERS.items()):
                pid = info.get("pid")
                proc = info.get("process")
                port = info.get("port")
                all_ports = info.get("all_ports") or ([port] if port else [])

                is_proc_alive = False
                child_pids = []
                mem_mb = 0.0
                cpu_pct = 0.0
                seen_metric_pids = set()

                candidate_pids = list(set(([pid] if pid else []) + (info.get("all_pids") or [])))

                if psutil and candidate_pids:
                    for c_pid in candidate_pids:
                        if not c_pid or c_pid in seen_metric_pids:
                            continue
                        try:
                            p = psutil.Process(c_pid)
                            if p.is_running() and p.status() != psutil.STATUS_ZOMBIE:
                                is_proc_alive = True
                                seen_metric_pids.add(p.pid)
                                mem_mb += p.memory_info().rss / (1024 * 1024)
                                try:
                                    cpu_pct += p.cpu_percent(interval=None)
                                except Exception:
                                    pass
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass
                elif proc:
                    is_proc_alive = (proc.poll() is None)

                active_app_ports = [p for p in all_ports if p in all_listening_ports]
                is_port_listening = len(active_app_ports) > 0 or ((port in all_listening_ports) if port else False)

                # If both process is gone and no port is listening, server has died
                if not is_proc_alive and not is_port_listening:
                    print(f"[ServerMonitor] App server '{slug}' (port {port}, pid {pid}) has terminated. Pruning.")
                    ACTIVE_SERVERS.pop(slug, None)
                    continue

                uptime = int(time.time() - info.get("started_at", time.time()))
                hours, rem = divmod(uptime, 3600)
                mins, secs = divmod(rem, 60)
                uptime_str = f"{hours}h {mins}m" if hours else (f"{mins}m {secs}s" if mins else f"{secs}s")

                info["metrics"] = {
                    "memory_mb": round(mem_mb, 1),
                    "cpu_percent": round(cpu_pct, 1),
                    "uptime_seconds": uptime,
                    "uptime_str": uptime_str,
                    "child_pids": child_pids,
                    "is_port_listening": is_port_listening,
                    "all_ports": active_app_ports or all_ports
                }
                info["status"] = "healthy" if is_port_listening else ("starting" if is_proc_alive else "unhealthy")

            # Check if active server signature changed; if so, persist to disk and refresh System Tray menu outside lock
            sig_parts = [f"{k}:{v.get('port')}:{v.get('status')}" for k, v in sorted(ACTIVE_SERVERS.items())]
            new_sig = "|".join(sig_parts)
            if new_sig != cls._last_signature:
                cls._last_signature = new_sig
                should_notify = True

        if should_notify:
            _save_active_servers_state()
            _notify_tray_menu_refresh()

    @classmethod
    def terminate_process_tree(cls, pid: int, timeout: float = 3.0):
        """Cleanly terminate parent process and ALL descendant child processes."""
        if not pid:
            return
        if psutil:
            try:
                parent = psutil.Process(pid)
                children = parent.children(recursive=True)
                for child in children:
                    try:
                        child.terminate()
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
                try:
                    parent.terminate()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

                gone, alive = psutil.wait_procs(children + [parent], timeout=timeout)
                for p in alive:
                    try:
                        p.kill()
                    except Exception:
                        pass
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
            except Exception:
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True)
        else:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True)


# Auto-start server monitor
ServerMonitor.start()


class AppLauncherService:

    @staticmethod
    def get_all_listening_ports() -> Set[int]:
        """Return all TCP ports currently in LISTEN state on localhost/system."""
        ports = set()
        if psutil:
            try:
                for conn in psutil.net_connections(kind='tcp'):
                    if conn.status == 'LISTEN' and conn.laddr:
                        ports.add(conn.laddr.port)
                return ports
            except Exception:
                pass
        
        # Fallback to netstat
        try:
            out = subprocess.check_output(['netstat', '-ano', '-p', 'tcp'], text=True, errors='ignore')
            for line in out.splitlines():
                parts = line.strip().split()
                if len(parts) >= 4 and parts[0] == 'TCP' and parts[3] == 'LISTENING':
                    port_str = parts[1].rsplit(':', 1)[-1]
                    try:
                        ports.add(int(port_str))
                    except Exception:
                        pass
        except Exception:
            pass
        return ports

    @staticmethod
    def get_ports_for_pid(pid: int) -> List[int]:
        """Find all listening TCP ports owned by a specific process PID or any of its child processes."""
        if not pid:
            return []
        pids = [pid]
        if psutil:
            try:
                proc = psutil.Process(pid)
                pids = [proc.pid] + [c.pid for c in proc.children(recursive=True)]
            except Exception:
                pids = [pid]

        listening_ports = []
        if psutil:
            try:
                for conn in psutil.net_connections(kind='tcp'):
                    if conn.status == 'LISTEN' and conn.pid in pids and conn.laddr:
                        listening_ports.append(conn.laddr.port)
            except Exception:
                pass

        if not listening_ports:
            # Fallback to netstat by matching PIDs
            try:
                out = subprocess.check_output(['netstat', '-ano', '-p', 'tcp'], text=True, errors='ignore')
                pid_set = set(pids)
                for line in out.splitlines():
                    parts = line.strip().split()
                    if len(parts) >= 5 and parts[0] == 'TCP' and parts[3] == 'LISTENING':
                        try:
                            line_pid = int(parts[4])
                            if line_pid in pid_set:
                                port = int(parts[1].rsplit(':', 1)[-1])
                                listening_ports.append(port)
                        except Exception:
                            pass
            except Exception:
                pass

        return list(set(listening_ports))

    @staticmethod
    def find_available_port(preferred_port: int = 8080, exclude_ports: Optional[Set[int]] = None) -> int:
        """Find an unassigned available TCP port on localhost, strictly avoiding already occupied ports
        both system-wide and in ACTIVE_SERVERS."""
        if exclude_ports is None:
            exclude_ports = set()
        else:
            exclude_ports = set(exclude_ports)

        # Exclude all ports assigned to active GitBridge servers
        for s in ACTIVE_SERVERS.values():
            p = s.get("port")
            if p:
                exclude_ports.add(p)

        # Exclude GitBridge & Antigravity Service control plane ports
        exclude_ports.update({8000, 8001})

        # Collect current OS listening ports
        listening = AppLauncherService.get_all_listening_ports()
        exclude_ports.update(listening)

        # First check preferred port if it's completely unencumbered
        if preferred_port not in exclude_ports:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    s.bind(('127.0.0.1', preferred_port))
                    return preferred_port
            except Exception:
                pass

        # Scan upward from preferred_port + 1 up to preferred_port + 300
        for port in range(preferred_port + 1, preferred_port + 300):
            if port in exclude_ports:
                continue
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    s.bind(('127.0.0.1', port))
                    return port
            except Exception:
                continue

        # Broader search fallback: 8081 -> 8999
        for port in range(8081, 8999):
            if port in exclude_ports:
                continue
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    s.bind(('127.0.0.1', port))
                    return port
            except Exception:
                continue

        return preferred_port + 10

    @staticmethod
    def detect_local_path(app_obj) -> Optional[str]:
        """Auto-detect if application folder exists in any configured workspace directory."""
        if app_obj.local_path and os.path.exists(app_obj.local_path):
            return app_obj.local_path

        from gitbridge.services.workspace_service import WorkspaceService
        workspace_dirs = WorkspaceService.get_workspace_dirs()

        for base_dir in workspace_dirs:
            if not os.path.exists(base_dir):
                continue

            candidates = [
                os.path.join(base_dir, app_obj.slug),
                os.path.join(base_dir, app_obj.name),
                os.path.join(base_dir, app_obj.name.replace(" ", "-")),
                os.path.join(base_dir, app_obj.name.replace(" ", "_")),
            ]
            if app_obj.github_repo_name and "/" in app_obj.github_repo_name:
                repo_basename = app_obj.github_repo_name.split("/")[-1]
                candidates.append(os.path.join(base_dir, repo_basename))

            for path in candidates:
                if os.path.exists(path):
                    return path

            def norm(s: str) -> str:
                return re.sub(r'[^a-z0-9]', '', (s or "").lower())

            slug_norm = norm(app_obj.slug)
            name_norm = norm(app_obj.name)
            repo_norm = norm(app_obj.github_repo_name.split("/")[-1]) if (app_obj.github_repo_name and "/" in app_obj.github_repo_name) else ""

            try:
                for folder_name in os.listdir(base_dir):
                    full_path = os.path.join(base_dir, folder_name)
                    if os.path.isdir(full_path):
                        folder_norm = norm(folder_name)
                        if folder_norm and (folder_norm == slug_norm or folder_norm == name_norm or (repo_norm and folder_norm == repo_norm)):
                            return full_path
            except Exception:
                pass

        return None

    @staticmethod
    def clone_repository(app_obj) -> Optional[str]:
        """Clone repository from GitHub into Geppy's App Universe if not locally present."""
        if not app_obj.github_url:
            return None

        target_dir = os.path.join("d:\\Geppy_Apps", app_obj.slug)
        if os.path.exists(target_dir):
            return target_dir

        try:
            print(f"[Launcher] Cloning {app_obj.github_url} into {target_dir}...")
            subprocess.run(["git", "clone", app_obj.github_url, target_dir], check=True, timeout=60)
            return target_dir
        except Exception as e:
            print(f"[Launcher] Failed to clone repository: {e}")
            return None

    @staticmethod
    def _ensure_node_server_uses_port_env(folder_path: str):
        """Ensure server.ts / server.js respects process.env.PORT instead of hardcoding 3000."""
        for fname in ("server.ts", "server.js"):
            fpath = os.path.join(folder_path, fname)
            if os.path.exists(fpath):
                try:
                    with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                        text = f.read()
                    if "const PORT = 3000;" in text and "process.env.PORT" not in text:
                        text = text.replace("const PORT = 3000;", "const PORT = Number(process.env.PORT) || 3000;")
                        with open(fpath, "w", encoding="utf-8") as f:
                            f.write(text)
                except Exception:
                    pass

    @staticmethod
    def detect_framework_and_command(folder_path: str, allocated_port: int, app_obj) -> tuple[str, str, str]:
        """Inspect directory files to determine framework, target execution folder, and localhost launch command
        with explicit port configuration."""
        py_bin = sys.executable

        # 0. Check if this is GitBridge itself
        if os.path.exists(os.path.join(folder_path, "gitbridge", "main.py")):
            return f'"{py_bin}" -m uvicorn gitbridge.main:app --port 8000', "http://127.0.0.1:8000", folder_path

        pkg_json_path = os.path.join(folder_path, "package.json")
        node_modules_path = os.path.join(folder_path, "node_modules")

        # 1. Check Node.js / React / Vite / Next.js / Express projects
        if os.path.exists(pkg_json_path):
            try:
                AppLauncherService._ensure_node_server_uses_port_env(folder_path)
                with open(pkg_json_path, "r", encoding="utf-8") as f:
                    pkg = json.load(f)
                    scripts = pkg.get("scripts", {})

                    prefix = "npm install && " if not os.path.exists(node_modules_path) else ""

                    dev_cmd = scripts.get("dev", "").lower()
                    if "dev" in scripts:
                        if "vite" in dev_cmd and "concurrently" not in dev_cmd:
                            # Invoke npx vite directly with --port and --host so hardcoded --port=3000 in package.json never conflicts
                            return f"{prefix}npx vite --port {allocated_port} --host 127.0.0.1", f"http://localhost:{allocated_port}", folder_path
                        elif "next" in dev_cmd:
                            # Forward -p directly to Next.js
                            return f"{prefix}npm run dev -- -p {allocated_port}", f"http://localhost:{allocated_port}", folder_path
                        else:
                            return f"{prefix}npm run dev", f"http://localhost:{allocated_port}", folder_path
                    elif "start" in scripts:
                        return f"{prefix}npm start", f"http://localhost:{allocated_port}", folder_path
                    elif "preview" in scripts:
                        return f"{prefix}npx vite preview --port {allocated_port} --host 127.0.0.1", f"http://localhost:{allocated_port}", folder_path
            except Exception as e:
                print(f"[Launcher] Error inspecting package.json: {e}")

        # 2. Check Python FastAPI / Streamlit / Flask projects
        py_candidates = [
            ("main.py", folder_path, "main"),
            ("app.py", folder_path, "app"),
            ("server.py", folder_path, "server"),
            (os.path.join("app", "main.py"), folder_path, "app.main"),
            (os.path.join("src", "main.py"), folder_path, "src.main"),
            (os.path.join("app", "app.py"), folder_path, "app.app")
        ]

        for rel_file, base_dir, mod_name in py_candidates:
            py_path = os.path.join(base_dir, rel_file)
            if os.path.exists(py_path):
                try:
                    with open(py_path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                        if "streamlit" in content:
                            return f'"{py_bin}" -m streamlit run {rel_file} --server.port {allocated_port}', f"http://localhost:{allocated_port}", base_dir
                        elif "fastapi" in content or "uvicorn" in content:
                            return f'"{py_bin}" -m uvicorn {mod_name}:app --port {allocated_port} --reload', f"http://localhost:{allocated_port}", base_dir
                        elif "flask" in content or "app.run" in content:
                            return f'"{py_bin}" {rel_file}', f"http://localhost:{allocated_port}", base_dir
                except Exception:
                    pass

        # 2b. Check if app/main.py or main.py defines an app object
        for mod, rel_f in [("app.main", os.path.join("app", "main.py")), ("main", "main.py")]:
            if os.path.exists(os.path.join(folder_path, rel_f)):
                return f'"{py_bin}" -m uvicorn {mod}:app --port {allocated_port} --reload', f"http://localhost:{allocated_port}", folder_path

        # 3. Chrome Extension projects (manifest.json with side_panel or popup)
        manifest_path = os.path.join(folder_path, "manifest.json")
        entry_url_suffix = ""
        if os.path.exists(manifest_path):
            try:
                with open(manifest_path, "r", encoding="utf-8", errors="ignore") as mf:
                    mdata = json.load(mf)
                    sp = (mdata.get("side_panel") or {}).get("default_path")
                    ac = (mdata.get("action") or {}).get("default_popup")
                    entry_rel = sp or ac
                    if entry_rel and os.path.exists(os.path.join(folder_path, entry_rel.replace("/", os.sep))):
                        entry_url_suffix = "/" + entry_rel.lstrip("/")
            except Exception:
                pass

        # 4. Static Web Apps (HTML/JS/CSS)
        target_serve_folder = folder_path
        if not entry_url_suffix:
            for sub in ["", "dist", "public", "build", "static", "src", "web", "sidepanel", "popup", "viewer", os.path.join("app", "static")]:
                candidate = os.path.join(folder_path, sub) if sub else folder_path
                if os.path.exists(os.path.join(candidate, "index.html")):
                    target_serve_folder = candidate
                    break
                elif os.path.exists(os.path.join(candidate, "sidepanel.html")):
                    target_serve_folder = folder_path
                    entry_url_suffix = f"/{sub}/sidepanel.html" if sub else "/sidepanel.html"
                    break

        target_url = f"http://localhost:{allocated_port}{entry_url_suffix}"
        return f'"{py_bin}" -m http.server {allocated_port}', target_url, target_serve_folder

    @staticmethod
    def wait_for_port(port: int, host: str = "127.0.0.1", timeout: float = 8.0) -> bool:
        """Poll socket port on both IPv4 (127.0.0.1) and localhost (IPv4/IPv6) until server accepts connections."""
        start = time.time()
        while time.time() - start < timeout:
            for candidate_host in ("127.0.0.1", "localhost"):
                try:
                    with socket.create_connection((candidate_host, port), timeout=0.35):
                        return True
                except Exception:
                    pass
            time.sleep(0.25)
        return False

    @staticmethod
    def launch_localhost(app_obj) -> Dict[str, Any]:
        """Launch the application locally on localhost and return target URL, strictly preventing port collisions."""
        slug = app_obj.slug

        # Special case: Geppy's GitBridge itself runs on port 8000
        if slug in ("geppys-gitbridge", "geppy-s-gitbridge", "gitbridge"):
            return {
                "launched": True,
                "action": "gitbridge_control_plane",
                "target": "http://127.0.0.1:8000",
                "port": 8000,
                "message": "Geppy's GitBridge is active on http://127.0.0.1:8000 (Port 8000)"
            }

        # Reconcile live OS workspace ports first so if the app is already running on a port, we attach to it immediately
        ServerMonitor.check_servers_health()

        # If server is already recorded as running, verify it's genuinely responsive
        if slug in ACTIVE_SERVERS:
            info = ACTIVE_SERVERS[slug]
            port = info.get("port")
            if port and AppLauncherService.wait_for_port(port, timeout=0.8):
                _notify_tray_menu_refresh()
                return {
                    "launched": True,
                    "action": "already_running",
                    "target": info["url"],
                    "port": port,
                    "pid": info.get("pid"),
                    "message": f"Local server is already running on {info['url']}"
                }
            else:
                # Process died or became unresponsive; prune and re-launch
                ACTIVE_SERVERS.pop(slug, None)

        # Find or clone local repository path
        folder_path = AppLauncherService.detect_local_path(app_obj)
        if not folder_path and app_obj.github_url:
            folder_path = AppLauncherService.clone_repository(app_obj)

        if not folder_path or not os.path.exists(folder_path):
            return {
                "launched": False,
                "action": "missing_local_path",
                "target": None,
                "message": f"No local project folder found for '{app_obj.name}'. Please clone or link local directory."
            }

        # Auto-inject the Universal GeppyBug Reporter & Update Bridge into the app's HTML entrypoints
        try:
            from gitbridge.services.bug_report_service import BugReportService
            if not app_obj.local_path:
                app_obj.local_path = folder_path
            BugReportService.inject_bridge_into_app(app_obj)
        except Exception as e:
            print(f"[Launcher] Universal bridge injection notice: {e}")

        # Snapshot all currently listening ports BEFORE launching to prevent misattributing existing servers
        ports_before = AppLauncherService.get_all_listening_ports()
        existing_active_ports = {s["port"] for s in ACTIVE_SERVERS.values() if s.get("port")}
        forbidden_ports = set(ports_before) | existing_active_ports | {8000}

        # Determine framework type to choose preferred port range
        pkg_json_path = os.path.join(folder_path, "package.json")
        is_vite = False
        is_next = False
        is_node_server = False
        is_concurrent_dual = False
        if os.path.exists(pkg_json_path):
            try:
                with open(pkg_json_path, "r", encoding="utf-8") as f:
                    scripts = json.load(f).get("scripts", {})
                    dev_cmd = scripts.get("dev", "").lower()
                    if "concurrently" in dev_cmd:
                        is_concurrent_dual = True
                        is_vite = True
                    elif "vite" in dev_cmd:
                        is_vite = True
                    elif "next" in dev_cmd:
                        is_next = True
                    elif "tsx" in dev_cmd or "node" in dev_cmd or "server" in dev_cmd:
                        is_node_server = True
            except Exception:
                pass

        preferred_port = 5173 if is_vite else (3000 if (is_next or is_node_server) else 8080)
        allocated_port = AppLauncherService.find_available_port(preferred_port=preferred_port, exclude_ports=forbidden_ports)

        # Detect command & execution folder
        if app_obj.launch_command:
            command = app_obj.launch_command.replace("{port}", str(allocated_port))
            url = f"http://localhost:{allocated_port}"
            exec_folder = folder_path
        else:
            command, url, exec_folder = AppLauncherService.detect_framework_and_command(folder_path, allocated_port, app_obj)

        # Preserve any URL suffix (e.g. /sidepanel/sidepanel.html for Chrome extension apps)
        url_suffix = ""
        try:
            from urllib.parse import urlparse
            parsed_u = urlparse(url)
            if parsed_u.path and parsed_u.path != "/":
                url_suffix = parsed_u.path
        except Exception:
            pass

        try:
            print(f"[Launcher] Launching '{slug}' headlessly in {exec_folder} with command: {command} (Allocated Port: {allocated_port})...")

            env = os.environ.copy()
            # For dual concurrent apps (e.g. Geppy's Sparkler where backend expects port 5000 and client uses Vite),
            # do not override PORT so the backend stays on 5000 while Vite opens on 5173+.
            if not is_concurrent_dual:
                env["PORT"] = str(allocated_port)
                env["FLASK_RUN_PORT"] = str(allocated_port)

            # Central API Key & GitBridge Ecosystem Environment Injection
            try:
                from gitbridge.services.central_key_service import CentralKeyService
                central_key = CentralKeyService.get_api_key()
                if central_key:
                    env["GEMINI_API_KEY"] = central_key
                    env["GOOGLE_API_KEY"] = central_key
                    env["VITE_GEMINI_API_KEY"] = central_key
                    env["NEXT_PUBLIC_GEMINI_API_KEY"] = central_key
                    env["REACT_APP_GEMINI_API_KEY"] = central_key
                    env["GEPPY_CENTRAL_KEY"] = central_key
                env["GITBRIDGE_URL"] = "http://127.0.0.1:8000"
            except Exception as e:
                print(f"[Launcher] Environment key injection notice: {e}")

            creationflags = getattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000)
            proc = subprocess.Popen(
                command,
                cwd=exec_folder,
                shell=True,
                env=env,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags
            )

            # Actively monitor the process tree to find the EXACT port this process opened
            found_port = None
            detected_all_ports = []
            start_poll = time.time()
            poll_timeout = 12.0

            while time.time() - start_poll < poll_timeout:
                # 1. Check if the parent process exited prematurely
                if proc.poll() is not None:
                    return {
                        "launched": False,
                        "action": "process_crashed",
                        "target": None,
                        "message": f"Server process exited unexpectedly with code {proc.returncode}."
                    }

                # 2. Check process tree listening ports (most accurate)
                pid_ports = AppLauncherService.get_ports_for_pid(proc.pid)
                valid_pid_ports = [p for p in pid_ports if p not in existing_active_ports and p != 8000]
                if valid_pid_ports:
                    detected_all_ports = sorted(list(set(valid_pid_ports)))
                    if is_concurrent_dual:
                        # Prefer the Vite frontend port (5173+) over backend API port (5000)
                        frontend_ports = [p for p in valid_pid_ports if p >= 5170 or p != 5000]
                        if frontend_ports:
                            found_port = frontend_ports[0]
                            break
                    else:
                        if allocated_port in valid_pid_ports:
                            found_port = allocated_port
                        else:
                            found_port = valid_pid_ports[0]
                        break

                # 3. Check allocated port if it started listening and was NOT listening before
                if allocated_port not in ports_before and allocated_port not in existing_active_ports:
                    if AppLauncherService.wait_for_port(allocated_port, timeout=0.2):
                        found_port = allocated_port
                        break

                # 4. Check snapshot diff for any new listening port
                current_listening = AppLauncherService.get_all_listening_ports()
                new_ports = (current_listening - ports_before) - existing_active_ports - {8000}
                if new_ports:
                    detected_all_ports = sorted(list(new_ports))
                    if allocated_port in new_ports:
                        found_port = allocated_port
                        break
                    elif is_concurrent_dual:
                        fe_new = [p for p in sorted(list(new_ports)) if p >= 5170 or p != 5000]
                        if fe_new:
                            found_port = fe_new[0]
                            break
                    else:
                        found_port = sorted(list(new_ports))[0]
                        break

                time.sleep(0.3)

            # If still not detected, verify if allocated port responds
            if not found_port:
                if AppLauncherService.wait_for_port(allocated_port, timeout=0.5):
                    found_port = allocated_port

            final_port = found_port or allocated_port
            final_url = f"http://localhost:{final_port}{url_suffix}"
            all_ports_list = sorted(list(set(detected_all_ports + [final_port])))

            ACTIVE_SERVERS[slug] = {
                "slug": slug,
                "name": app_obj.name,
                "process": proc,
                "pid": proc.pid,
                "all_pids": [proc.pid],
                "port": final_port,
                "all_ports": all_ports_list,
                "url": final_url,
                "command": command,
                "folder_path": exec_folder,
                "started_at": time.time(),
                "status": "healthy",
                "metrics": {
                    "memory_mb": 0.0,
                    "cpu_percent": 0.0,
                    "uptime_seconds": 0,
                    "uptime_str": "0s",
                    "child_pids": [],
                    "is_port_listening": True,
                    "all_ports": all_ports_list
                }
            }
            app_obj.live_url = final_url

            # Trigger immediate health update, persist state, and notify System Tray menu
            ServerMonitor.check_servers_health()
            _save_active_servers_state()
            _notify_tray_menu_refresh()

            return {
                "launched": True,
                "action": "launched_localhost",
                "target": final_url,
                "command": command,
                "port": final_port,
                "all_ports": ACTIVE_SERVERS.get(slug, {}).get("all_ports", all_ports_list),
                "pid": proc.pid,
                "message": f"Successfully launched '{app_obj.name}' on {final_url} (Port {final_port})!"
            }
        except Exception as e:
            return {
                "launched": False,
                "action": "launch_failed",
                "target": None,
                "message": f"Failed to start local server process: {e}"
            }

    @staticmethod
    def stop_localhost_server(slug: str) -> bool:
        """Stop a running localhost server process for an app and cleanly kill entire process tree and all bound ports."""
        if slug in ("geppys-gitbridge", "geppy-s-gitbridge", "gitbridge"):
            return False
        ServerMonitor.check_servers_health()
        info = ACTIVE_SERVERS.pop(slug, None)

        target_ports: Set[int] = set()
        target_pids: Set[int] = set()
        target_folder: Optional[str] = None

        if info:
            if info.get("port"):
                target_ports.add(int(info["port"]))
            for p in (info.get("all_ports") or []):
                if p:
                    target_ports.add(int(p))
            if info.get("pid"):
                target_pids.add(int(info["pid"]))
            for c_pid in (info.get("all_pids") or []):
                if c_pid:
                    target_pids.add(int(c_pid))
            target_folder = info.get("folder_path")
            proc = info.get("process")
            if proc:
                try:
                    proc.terminate()
                except Exception:
                    pass
        else:
            # Look up folder path from workspace map in case slug wasn't in ACTIVE_SERVERS
            for norm_p, meta in _get_workspace_apps_lookup().items():
                if meta["slug"] == slug:
                    target_folder = meta["folder_path"]
                    break

        # Also find any OS processes currently listening on target_ports or running inside target_folder
        if psutil:
            try:
                norm_target_folder = os.path.normcase(os.path.abspath(target_folder)) if target_folder else None
                for conn in psutil.net_connections(kind='tcp'):
                    if conn.status == 'LISTEN' and conn.laddr and conn.pid and conn.laddr.port not in (8000, 8001):
                        if conn.laddr.port in target_ports:
                            target_pids.add(conn.pid)
                        elif norm_target_folder:
                            try:
                                p = psutil.Process(conn.pid)
                                if "localharness" in (p.name() or "").lower():
                                    continue
                                for anc in [p] + p.parents():
                                    try:
                                        c_dir = anc.cwd()
                                        if c_dir and os.path.normcase(os.path.abspath(c_dir)).startswith(norm_target_folder):
                                            target_pids.add(conn.pid)
                                            target_pids.add(anc.pid)
                                            break
                                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                                        pass
                            except (psutil.NoSuchProcess, psutil.AccessDenied):
                                pass
            except Exception:
                pass

        if not info and not target_pids:
            return False

        for pid_to_kill in list(target_pids):
            if pid_to_kill and pid_to_kill != os.getpid():
                ServerMonitor.terminate_process_tree(pid_to_kill)

        time.sleep(0.25)
        _save_active_servers_state()
        _notify_tray_menu_refresh()
        return True

    @staticmethod
    def stop_all_servers() -> int:
        """Stop all currently active localhost servers (excluding GitBridge control plane on 8000/8001)."""
        ServerMonitor.check_servers_health()
        count = 0
        for slug in list(ACTIVE_SERVERS.keys()):
            if slug in ("geppys-gitbridge", "geppy-s-gitbridge", "gitbridge"):
                continue
            if AppLauncherService.stop_localhost_server(slug):
                count += 1
        _save_active_servers_state()
        _notify_tray_menu_refresh()
        return count

    @staticmethod
    def _build_gitbridge_self_entry() -> Dict[str, Any]:
        """Build the live server entry for Geppy's GitBridge itself (Port 8000 + Antigravity Port 8001) so it is always visible and selectable in Port Watcher."""
        gb_folder = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        uptime = int(max(0, time.time() - _SERVER_BOOT_TIME))
        hours, rem = divmod(uptime, 3600)
        mins, secs = divmod(rem, 60)
        uptime_str = f"{hours}h {mins}m" if hours else (f"{mins}m {secs}s" if mins else f"{secs}s")
        mem_mb = 0.0
        cpu_pct = 0.0
        if psutil:
            try:
                p = psutil.Process(os.getpid())
                mem_mb = round(p.memory_info().rss / (1024 * 1024), 1)
                cpu_pct = round(p.cpu_percent(interval=None), 1)
            except Exception:
                pass
        return {
            "slug": "geppys-gitbridge",
            "name": "Geppy's GitBridge",
            "url": "http://127.0.0.1:8000",
            "port": 8000,
            "all_ports": [8000, 8001],
            "command": "python -m gitbridge.tray_app (Control Plane :8000 + Antigravity :8001)",
            "pid": os.getpid(),
            "folder_path": gb_folder,
            "started_at": _SERVER_BOOT_TIME,
            "status": "healthy",
            "is_control_plane": True,
            "metrics": {
                "memory_mb": mem_mb,
                "cpu_percent": cpu_pct,
                "uptime_seconds": uptime,
                "uptime_str": uptime_str,
                "child_pids": [],
                "is_port_listening": True,
                "all_ports": [8000, 8001]
            }
        }

    @staticmethod
    def list_active_servers(run_health_check: bool = False, include_control_plane: bool = True) -> List[Dict[str, Any]]:
        """List all currently active localhost servers with telemetry.
        Uses background ServerMonitor state by default so HTTP requests return in <1ms."""
        if run_health_check or (time.time() - ServerMonitor._last_check_time > 6.0):
            try:
                ServerMonitor.check_servers_health()
            except Exception:
                pass
        res = []
        if include_control_plane:
            res.append(AppLauncherService._build_gitbridge_self_entry())

        for slug, info in list(ACTIVE_SERVERS.items()):
            if slug in ("geppys-gitbridge", "geppy-s-gitbridge", "gitbridge"):
                continue
            res.append({
                "slug": slug,
                "name": info.get("name", slug.replace("-", " ").title()),
                "url": info["url"],
                "port": info["port"],
                "all_ports": info.get("all_ports", [info["port"]] if info.get("port") else []),
                "command": info["command"],
                "pid": info["pid"],
                "folder_path": info["folder_path"],
                "started_at": info.get("started_at"),
                "status": info.get("status", "healthy"),
                "is_control_plane": False,
                "metrics": info.get("metrics", {})
            })
        return res

    @staticmethod
    def get_monitor_summary() -> Dict[str, Any]:
        """Provide detailed server monitoring metrics, resource usage, and port allocation matrix."""
        servers = AppLauncherService.list_active_servers(run_health_check=False, include_control_plane=True)
        all_listening = AppLauncherService.get_all_listening_ports()
        total_ram = sum(s.get("metrics", {}).get("memory_mb", 0.0) for s in servers)
        total_cpu = sum(s.get("metrics", {}).get("cpu_percent", 0.0) for s in servers)

        # Build port breakdown matrix
        matrix = []
        common_ranges = [
            ("Control Plane (GitBridge & Antigravity)", range(8000, 8002)),
            ("Vite / Frontend", range(5173, 5178)),
            ("Next.js / Node", range(3000, 3005)),
            ("Node / Express API", range(5000, 5004)),
            ("Python / FastAPI", range(8080, 8086)),
            ("Streamlit", range(8501, 8505))
        ]

        active_port_map = {}
        for s in servers:
            active_port_map[s["port"]] = s
            for extra_p in (s.get("all_ports") or []):
                active_port_map[extra_p] = s

        for category, prange in common_ranges:
            category_ports = []
            for p in prange:
                if p in active_port_map:
                    s = active_port_map[p]
                    category_ports.append({
                        "port": p,
                        "status": "active_gitbridge",
                        "app_name": s["name"],
                        "slug": s["slug"],
                        "url": s["url"]
                    })
                elif p in all_listening:
                    category_ports.append({
                        "port": p,
                        "status": "external_in_use",
                        "app_name": "External Service",
                        "slug": None,
                        "url": f"http://localhost:{p}"
                    })
                else:
                    category_ports.append({
                        "port": p,
                        "status": "available",
                        "app_name": None,
                        "slug": None,
                        "url": None
                    })
            matrix.append({
                "category": category,
                "ports": category_ports
            })

        return {
            "servers": servers,
            "server_count": len(servers),
            "total_memory_mb": round(total_ram, 1),
            "total_cpu_percent": round(total_cpu, 1),
            "gitbridge_port": 8000,
            "port_matrix": matrix,
            "all_listening_count": len(all_listening),
            "timestamp": time.time()
        }

    @staticmethod
    def open_local_folder(folder_path: str) -> bool:
        """Open directory in Windows File Explorer."""
        if not folder_path or not os.path.exists(folder_path):
            return False
        try:
            os.startfile(folder_path)
            return True
        except Exception:
            subprocess.Popen(["explorer", folder_path])
            return True
