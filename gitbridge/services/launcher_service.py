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
#   "port": int,
#   "url": str,
#   "command": str,
#   "folder_path": str,
#   "started_at": float,
#   "status": str,
#   "metrics": dict
# }
ACTIVE_SERVERS: Dict[str, Dict[str, Any]] = {}


class ServerMonitor:
    """Background daemon thread monitoring active app servers, detecting terminations,
    tracking CPU/memory telemetry, and preventing port conflicts."""
    _thread: Optional[threading.Thread] = None
    _stop_event = threading.Event()
    _lock = threading.Lock()

    @classmethod
    def start(cls):
        """Start the background monitor daemon if not already running."""
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
            except Exception as e:
                pass
            time.sleep(2.5)

    @classmethod
    def check_servers_health(cls):
        """Inspect all running servers, collect metrics, and prune dead servers."""
        all_listening_ports = AppLauncherService.get_all_listening_ports()
        
        with cls._lock:
            for slug, info in list(ACTIVE_SERVERS.items()):
                pid = info.get("pid")
                proc = info.get("process")
                port = info.get("port")

                is_proc_alive = False
                child_pids = []
                mem_mb = 0.0
                cpu_pct = 0.0

                if psutil and pid:
                    try:
                        p = psutil.Process(pid)
                        if p.is_running() and p.status() != psutil.STATUS_ZOMBIE:
                            is_proc_alive = True
                            mem_mb += p.memory_info().rss / (1024 * 1024)
                            try:
                                cpu_pct += p.cpu_percent(interval=None)
                            except Exception:
                                pass
                            
                            for c in p.children(recursive=True):
                                try:
                                    if c.is_running() and c.status() != psutil.STATUS_ZOMBIE:
                                        child_pids.append(c.pid)
                                        mem_mb += c.memory_info().rss / (1024 * 1024)
                                        try:
                                            cpu_pct += c.cpu_percent(interval=None)
                                        except Exception:
                                            pass
                                except Exception:
                                    pass
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        is_proc_alive = False
                elif proc:
                    is_proc_alive = (proc.poll() is None)

                is_port_listening = (port in all_listening_ports) if port else False

                # If both process is gone and port is no longer listening, server has died
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
                    "is_port_listening": is_port_listening
                }
                info["status"] = "healthy" if (is_proc_alive and is_port_listening) else ("starting" if is_proc_alive else "unhealthy")

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
            except Exception as e:
                # Fallback to taskkill on Windows
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

        # Exclude GitBridge control plane port
        exclude_ports.add(8000)

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
    def detect_framework_and_command(folder_path: str, allocated_port: int, app_obj) -> tuple[str, str, str]:
        """Inspect directory files to determine framework, target execution folder, and localhost launch command
        with explicit port configuration."""
        py_bin = sys.executable

        pkg_json_path = os.path.join(folder_path, "package.json")
        node_modules_path = os.path.join(folder_path, "node_modules")

        # 1. Check Node.js / React / Vite / Next.js / Express projects
        if os.path.exists(pkg_json_path):
            try:
                with open(pkg_json_path, "r", encoding="utf-8") as f:
                    pkg = json.load(f)
                    scripts = pkg.get("scripts", {})

                    prefix = "npm install && " if not os.path.exists(node_modules_path) else ""

                    dev_cmd = scripts.get("dev", "").lower()
                    if "dev" in scripts:
                        if "vite" in dev_cmd:
                            # Forward --port directly to Vite
                            return f"{prefix}npm run dev -- --port {allocated_port}", f"http://localhost:{allocated_port}", folder_path
                        elif "next" in dev_cmd:
                            # Forward -p directly to Next.js
                            return f"{prefix}npm run dev -- -p {allocated_port}", f"http://localhost:{allocated_port}", folder_path
                        else:
                            return f"{prefix}npm run dev", f"http://localhost:{allocated_port}", folder_path
                    elif "start" in scripts:
                        return f"{prefix}npm start", f"http://localhost:{allocated_port}", folder_path
                    elif "preview" in scripts:
                        return f"{prefix}npm run preview -- --port {allocated_port}", f"http://localhost:{allocated_port}", folder_path
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

        # 3. Static Web Apps (HTML/JS/CSS)
        target_serve_folder = folder_path
        for sub in ["", "dist", "public", "build", "static", "src", os.path.join("app", "static")]:
            candidate = os.path.join(folder_path, sub) if sub else folder_path
            if os.path.exists(os.path.join(candidate, "index.html")):
                target_serve_folder = candidate
                break

        target_url = f"http://localhost:{allocated_port}"
        return f'"{py_bin}" -m http.server {allocated_port}', target_url, target_serve_folder

    @staticmethod
    def wait_for_port(port: int, host: str = "127.0.0.1", timeout: float = 8.0) -> bool:
        """Poll socket port until server accepts connections."""
        start = time.time()
        while time.time() - start < timeout:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(0.4)
                    if s.connect_ex((host, port)) == 0:
                        return True
            except Exception:
                pass
            time.sleep(0.3)
        return False

    @staticmethod
    def launch_localhost(app_obj) -> Dict[str, Any]:
        """Launch the application locally on localhost and return target URL, strictly preventing port collisions."""
        slug = app_obj.slug

        # If server is already recorded as running, verify it's genuinely responsive
        if slug in ACTIVE_SERVERS:
            info = ACTIVE_SERVERS[slug]
            port = info.get("port")
            if port and AppLauncherService.wait_for_port(port, timeout=0.5):
                return {
                    "launched": True,
                    "action": "already_running",
                    "target": info["url"],
                    "port": port,
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

        # Snapshot all currently listening ports BEFORE launching to prevent misattributing existing servers
        ports_before = AppLauncherService.get_all_listening_ports()
        existing_active_ports = {s["port"] for s in ACTIVE_SERVERS.values() if s.get("port")}
        forbidden_ports = set(ports_before) | existing_active_ports | {8000}

        # Determine framework type to choose preferred port range
        pkg_json_path = os.path.join(folder_path, "package.json")
        is_vite = False
        is_next = False
        if os.path.exists(pkg_json_path):
            try:
                with open(pkg_json_path, "r", encoding="utf-8") as f:
                    scripts = json.load(f).get("scripts", {})
                    dev_cmd = scripts.get("dev", "").lower()
                    if "vite" in dev_cmd:
                        is_vite = True
                    elif "next" in dev_cmd:
                        is_next = True
            except Exception:
                pass

        preferred_port = 5173 if is_vite else (3000 if is_next else 8080)
        allocated_port = AppLauncherService.find_available_port(preferred_port=preferred_port, exclude_ports=forbidden_ports)

        # Detect command & execution folder
        if app_obj.launch_command:
            command = app_obj.launch_command.replace("{port}", str(allocated_port))
            url = f"http://localhost:{allocated_port}"
            exec_folder = folder_path
        else:
            command, url, exec_folder = AppLauncherService.detect_framework_and_command(folder_path, allocated_port, app_obj)

        try:
            print(f"[Launcher] Launching '{slug}' headlessly in {exec_folder} with command: {command} (Allocated Port: {allocated_port})...")

            creationflags = getattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000)
            env = os.environ.copy()
            env["PORT"] = str(allocated_port)
            env["FLASK_RUN_PORT"] = str(allocated_port)

            proc = subprocess.Popen(
                command,
                cwd=exec_folder,
                shell=True,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags
            )

            # Actively monitor the process tree to find the EXACT port this process opened
            found_port = None
            start_poll = time.time()
            poll_timeout = 10.0

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
                # Valid ports must not belong to pre-existing active servers
                for p in pid_ports:
                    if p not in existing_active_ports and p != 8000:
                        found_port = p
                        break
                if found_port:
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
                    if allocated_port in new_ports:
                        found_port = allocated_port
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
            final_url = f"http://localhost:{final_port}"

            ACTIVE_SERVERS[slug] = {
                "slug": slug,
                "name": app_obj.name,
                "process": proc,
                "pid": proc.pid,
                "port": final_port,
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
                    "is_port_listening": True
                }
            }
            app_obj.live_url = final_url

            # Trigger immediate health update
            ServerMonitor.check_servers_health()

            return {
                "launched": True,
                "action": "launched_localhost",
                "target": final_url,
                "command": command,
                "port": final_port,
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
        """Stop a running localhost server process for an app and cleanly kill entire process tree."""
        if slug in ACTIVE_SERVERS:
            info = ACTIVE_SERVERS.pop(slug)
            pid = info.get("pid")
            proc = info.get("process")
            if pid:
                ServerMonitor.terminate_process_tree(pid)
            if proc:
                try:
                    proc.terminate()
                except Exception:
                    pass
            time.sleep(0.2)
            return True
        return False

    @staticmethod
    def stop_all_servers() -> int:
        """Stop all currently active localhost servers."""
        count = 0
        for slug in list(ACTIVE_SERVERS.keys()):
            if AppLauncherService.stop_localhost_server(slug):
                count += 1
        return count

    @staticmethod
    def list_active_servers() -> List[Dict[str, Any]]:
        """List all currently active localhost servers with telemetry."""
        ServerMonitor.check_servers_health()
        res = []
        for slug, info in ACTIVE_SERVERS.items():
            res.append({
                "slug": slug,
                "name": info.get("name", slug.replace("-", " ").title()),
                "url": info["url"],
                "port": info["port"],
                "command": info["command"],
                "pid": info["pid"],
                "folder_path": info["folder_path"],
                "started_at": info.get("started_at"),
                "status": info.get("status", "healthy"),
                "metrics": info.get("metrics", {})
            })
        return res

    @staticmethod
    def get_monitor_summary() -> Dict[str, Any]:
        """Provide detailed server monitoring metrics, resource usage, and port allocation matrix."""
        servers = AppLauncherService.list_active_servers()
        all_listening = AppLauncherService.get_all_listening_ports()
        total_ram = sum(s.get("metrics", {}).get("memory_mb", 0.0) for s in servers)
        total_cpu = sum(s.get("metrics", {}).get("cpu_percent", 0.0) for s in servers)

        # Build port breakdown matrix
        matrix = []
        common_ranges = [
            ("Vite / Frontend", range(5173, 5178)),
            ("Next.js / Node", range(3000, 3005)),
            ("Python / FastAPI", range(8080, 8086)),
            ("Streamlit", range(8501, 8505))
        ]

        active_port_map = {s["port"]: s for s in servers}

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
