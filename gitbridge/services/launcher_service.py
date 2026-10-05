import os
import json
import socket
import time
import subprocess
import webbrowser
from typing import Dict, Any, Optional

# Active Localhost Process Tracker
ACTIVE_SERVERS: Dict[str, Dict[str, Any]] = {}

class AppLauncherService:

    @staticmethod
    def find_available_port(start_port: int = 8080) -> int:
        """Find an unassigned available TCP port on localhost."""
        for port in range(start_port, start_port + 100):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                if s.connect_ex(('127.0.0.1', port)) != 0:
                    return port
        return start_port

    @staticmethod
    def detect_local_path(app_obj) -> Optional[str]:
        """Auto-detect if application folder exists in Geppy's App Universe directory."""
        if app_obj.local_path and os.path.exists(app_obj.local_path):
            return app_obj.local_path

        candidates = [
            os.path.join("d:\\Geppy_Apps", app_obj.slug),
            os.path.join("d:\\Geppy_Apps", app_obj.name),
            os.path.join("d:\\Geppy_Apps", app_obj.name.replace(" ", "-")),
            os.path.join("d:\\Geppy_Apps", app_obj.name.replace(" ", "_")),
        ]
        if app_obj.github_repo_name and "/" in app_obj.github_repo_name:
            repo_basename = app_obj.github_repo_name.split("/")[-1]
            candidates.append(os.path.join("d:\\Geppy_Apps", repo_basename))

        for path in candidates:
            if os.path.exists(path):
                return path
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
    def detect_framework_and_command(folder_path: str, allocated_port: int) -> tuple[str, str]:
        """Inspect directory files to determine the framework and localhost launch command."""
        pkg_json_path = os.path.join(folder_path, "package.json")
        if os.path.exists(pkg_json_path):
            try:
                with open(pkg_json_path, "r", encoding="utf-8") as f:
                    pkg = json.load(f)
                    scripts = pkg.get("scripts", {})
                    if "dev" in scripts:
                        return f"npm run dev -- --port {allocated_port}", f"http://localhost:{allocated_port}"
                    elif "start" in scripts:
                        return f"npm start -- --port {allocated_port}", f"http://localhost:{allocated_port}"
            except Exception:
                pass
            return f"npx serve -s . -l {allocated_port}", f"http://localhost:{allocated_port}"

        main_py = os.path.join(folder_path, "main.py")
        app_py = os.path.join(folder_path, "app.py")

        if os.path.exists(main_py):
            with open(main_py, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
                if "fastapi" in content or "uvicorn" in content:
                    return f"python -m uvicorn main:app --port {allocated_port} --reload", f"http://localhost:{allocated_port}"

        if os.path.exists(app_py):
            with open(app_py, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
                if "streamlit" in content:
                    return f"python -m streamlit run app.py --server.port {allocated_port}", f"http://localhost:{allocated_port}"
                elif "fastapi" in content or "uvicorn" in content:
                    return f"python -m uvicorn app:app --port {allocated_port} --reload", f"http://localhost:{allocated_port}"

        # Fallback to Python built-in local static server
        return f"python -m http.server {allocated_port}", f"http://localhost:{allocated_port}"

    @staticmethod
    def launch_localhost(app_obj) -> Dict[str, Any]:
        """Launch the application locally on localhost and open browser."""
        slug = app_obj.slug

        # If server is already running, open it in browser
        if slug in ACTIVE_SERVERS:
            info = ACTIVE_SERVERS[slug]
            webbrowser.open(info["url"])
            return {
                "launched": True,
                "action": "already_running",
                "target": info["url"],
                "message": f"Local server is already running on {info['url']}"
            }

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

        # Allocate available port & detect command
        port = AppLauncherService.find_available_port(start_port=8080)
        
        if app_obj.launch_command:
            command = app_obj.launch_command
            url = f"http://localhost:{port}"
        else:
            command, url = AppLauncherService.detect_framework_and_command(folder_path, port)

        if app_obj.live_url and "localhost" in app_obj.live_url:
            url = app_obj.live_url

        try:
            print(f"[Launcher] Running '{command}' in {folder_path} on {url}...")
            proc = subprocess.Popen(command, cwd=folder_path, shell=True)
            
            ACTIVE_SERVERS[slug] = {
                "process": proc,
                "pid": proc.pid,
                "port": port,
                "url": url,
                "command": command,
                "folder_path": folder_path,
                "started_at": time.time()
            }

            # Wait brief moment and open browser
            time.sleep(1.5)
            webbrowser.open(url)

            return {
                "launched": True,
                "action": "launched_localhost",
                "target": url,
                "command": command,
                "port": port,
                "message": f"Successfully launched local server on {url}!"
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
        """Stop a running localhost server process for an app."""
        if slug in ACTIVE_SERVERS:
            info = ACTIVE_SERVERS.pop(slug)
            proc = info.get("process")
            if proc:
                try:
                    proc.terminate()
                    return True
                except Exception:
                    pass
        return False

    @staticmethod
    def list_active_servers() -> List[Dict[str, Any]]:
        """List all currently active localhost servers."""
        res = []
        for slug, info in ACTIVE_SERVERS.items():
            res.append({
                "slug": slug,
                "url": info["url"],
                "port": info["port"],
                "command": info["command"],
                "pid": info["pid"],
                "folder_path": info["folder_path"]
            })
        return res

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
