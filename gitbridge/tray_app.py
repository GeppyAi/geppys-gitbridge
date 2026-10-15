import sys
import os

if sys.stdout is None:
    sys.stdout = open(os.devnull, 'w')
if sys.stderr is None:
    sys.stderr = open(os.devnull, 'w')

import threading
import time
import urllib.request
import json
import webbrowser
import subprocess
from PIL import Image, ImageDraw, ImageFont
import pystray
from pystray import MenuItem as item, Menu

from dotenv import load_dotenv

# Ensure working directory is project root
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

root_env = os.path.join(BASE_DIR, ".env")
if os.path.exists(root_env):
    load_dotenv(root_env, override=False)

from gitbridge.services.workspace_service import WorkspaceService
from gitbridge.services.central_key_service import CentralKeyService


UVICORN_THREAD = None
SERVER_PORT = 8000
SERVER_URL = f"http://127.0.0.1:{SERVER_PORT}"
IS_RUNNING = True

def create_tray_icon_image():
    """Generate a sleek 64x64 icon for Geppy's GitBridge Windows system tray."""
    width = 64
    height = 64
    image = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    
    # Draw indigo rounded square background
    draw.rounded_rectangle([2, 2, width-2, height-2], radius=14, fill=(79, 70, 229, 255))
    
    # Draw inner cyan accent bridge line
    draw.line([12, 44, 24, 24], fill=(129, 140, 248, 255), width=4)
    draw.line([24, 24, 40, 24], fill=(56, 189, 248, 255), width=4)
    draw.line([40, 24, 52, 44], fill=(129, 140, 248, 255), width=4)
    draw.line([10, 44, 54, 44], fill=(255, 255, 255, 255), width=4)

    # Small status indicator dot
    draw.ellipse([46, 6, 56, 16], fill=(52, 211, 153, 255))
    
    return image

def run_uvicorn_server():
    """Run Uvicorn FastAPI server in background thread with retry on port bind."""
    import uvicorn
    from gitbridge.main import app
    while IS_RUNNING:
        try:
            uvicorn.run(app, host="127.0.0.1", port=SERVER_PORT, log_level="error")
            break
        except Exception as e:
            if not IS_RUNNING:
                break
            time.sleep(1)

def open_dashboard(icon=None, item=None):
    """Open Geppy's GitBridge in browser."""
    webbrowser.open(SERVER_URL)

def scan_folders(icon=None, item=None):
    """Trigger API workspace folder scan."""
    try:
        req = urllib.request.Request(f"{SERVER_URL}/api/workspace/scan", method="POST")
        with urllib.request.urlopen(req) as response:
            res = json.loads(response.read().decode())
            print(f"[TrayApp] Workspace Scan Result: {res}")
    except Exception as e:
        print(f"[TrayApp] Scan failed: {e}")

def get_active_servers():
    """Fetch currently running app servers from API."""
    try:
        with urllib.request.urlopen(f"{SERVER_URL}/api/servers", timeout=2) as response:
            return json.loads(response.read().decode())
    except Exception:
        return {}

def fetch_all_apps():
    """Fetch all registered apps from API."""
    try:
        with urllib.request.urlopen(f"{SERVER_URL}/api/apps", timeout=2) as response:
            return json.loads(response.read().decode())
    except Exception:
        return []

def launch_app_handler(slug):
    """Return callback to launch app via API and open browser."""
    def handler(icon, item):
        def do_launch():
            try:
                req = urllib.request.Request(f"{SERVER_URL}/api/apps/{slug}/launch", method="POST")
                with urllib.request.urlopen(req, timeout=15) as response:
                    res = json.loads(response.read().decode())
                    target = res.get("target") or res.get("live_url")
                    if target:
                        webbrowser.open(target)
            except Exception as e:
                print(f"[TrayApp] Failed to launch '{slug}': {e}")
        threading.Thread(target=do_launch, daemon=True).start()
    return handler

def get_all_app_launch_items():
    """Build dynamic menu items for launching ALL discovered applications directly from System Tray."""
    apps = fetch_all_apps()
    items = []
    
    if apps:
        apps_sorted = sorted(apps, key=lambda x: x.get("name", "").lower())
        for a in apps_sorted:
            # Strictly skip hidden apps from System Tray menu
            if a.get("is_hidden"):
                continue
            slug = a.get("slug")
            name = a.get("name", slug)
            is_live = a.get("is_live")
            live_url = a.get("live_url")

            if is_live and live_url:
                title = f"🟢 {name} (Live)"
                items.append(item(title, open_server_url(live_url)))
            else:
                title = f"🚀 Launch {name}"
                items.append(item(title, launch_app_handler(slug)))
    else:
        items.append(item("No registered apps found", None, enabled=False))

    return items

def open_server_url(url):
    """Open specific running app live URL in browser."""
    def handler(icon, item):
        webbrowser.open(url)
    return handler

def open_port_monitor_dashboard(icon=None, item=None):
    """Open Port & Server Monitor in web dashboard."""
    webbrowser.open(f"{SERVER_URL}/#monitor")

def restart_single_server(slug):
    """Return callback handler to restart a specific app server."""
    def handler(icon, item):
        def do_restart():
            try:
                req = urllib.request.Request(f"{SERVER_URL}/api/servers/{slug}/restart", method="POST")
                with urllib.request.urlopen(req, timeout=15) as response:
                    res = json.loads(response.read().decode())
                    target = res.get("target") or res.get("live_url")
                    if target:
                        webbrowser.open(target)
            except Exception as e:
                print(f"[TrayApp] Failed to restart server '{slug}': {e}")
        threading.Thread(target=do_restart, daemon=True).start()
    return handler

def stop_all_servers(icon=None, item=None):
    """Stop all active localhost app servers cleanly."""
    try:
        req = urllib.request.Request(f"{SERVER_URL}/api/servers/stop-all", method="POST")
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        # Fallback to single deletes
        servers = get_active_servers()
        if isinstance(servers, list):
            for s in servers:
                slug = s.get("slug")
                if slug:
                    try:
                        r = urllib.request.Request(f"{SERVER_URL}/api/servers/{slug}", method="DELETE")
                        urllib.request.urlopen(r, timeout=1)
                    except Exception:
                        pass

def open_workspace_folder(icon=None, item=None):
    """Open workspace folders in Windows Explorer."""
    dirs = WorkspaceService.get_workspace_dirs()
    for d in dirs:
        if os.path.exists(d):
            os.startfile(d)

def stop_single_server(slug):
    """Return callback handler to stop a specific app server."""
    def handler(icon, item):
        def do_stop():
            try:
                req = urllib.request.Request(f"{SERVER_URL}/api/servers/{slug}", method="DELETE")
                urllib.request.urlopen(req, timeout=3)
            except Exception as e:
                print(f"[TrayApp] Failed to stop server '{slug}': {e}")
        threading.Thread(target=do_stop, daemon=True).start()
    return handler

def get_running_apps_menu():
    """Build dynamic menu items for Currently Running Apps."""
    servers = get_active_servers()
    items = []
    
    if servers and isinstance(servers, list) and len(servers) > 0:
        for s in servers:
            slug = s.get("slug", "")
            url = s.get("url", "")
            port = s.get("port", "")
            name = s.get("name") or slug.replace("-", " ").title()
            mem = s.get("metrics", {}).get("memory_mb")
            mem_str = f" • {mem}MB" if mem else ""
            
            app_actions = Menu(
                item(f"🌐 Open {url} in Browser", open_server_url(url)),
                item(f"🔄 Restart {name}", restart_single_server(slug)),
                item(f"⏹️ Stop {name}", stop_single_server(slug))
            )
            title = f"🟢 {name} (Port {port}{mem_str})"
            items.append(item(title, app_actions))

        items.append(item("⏹️ Stop All Running Apps", stop_all_servers))
        items.append(item("📊 Open Port & Server Monitor", open_port_monitor_dashboard))
    else:
        items.append(item("No apps currently running", None, enabled=False))

    return items

def create_dynamic_menu():
    """Build dynamic system tray context menu items."""
    servers = get_active_servers()
    count = len(servers) if isinstance(servers, list) else 0
    running_label = f"🟢 Currently Running Apps ({count})" if count > 0 else "⚪ Currently Running Apps"
    
    return (
        item("🚀 Open Geppy's Galactic", open_dashboard, default=True),
        item("👨‍🚀 Captain Geppy AI Bridge", lambda icon, it: webbrowser.open(f"{SERVER_URL}/#chat")),
        item("🛸 Source of Truth (SOT) Engine", lambda icon, it: webbrowser.open(f"{SERVER_URL}/#sot")),
        item("📊 Port & Server Monitor", open_port_monitor_dashboard),
        item(running_label, Menu(get_running_apps_menu)),
        item("📱 Quick Launch App Galaxy", Menu(get_all_app_launch_items)),
        item("🔍 Scan App Folders", scan_folders),
        item("📁 Open App Folders in Explorer", open_workspace_folder),
        item("❌ Exit Geppy's Galactic", quit_app)
    )

def quit_app(icon=None, item=None):
    """Quit system tray application and stop server immediately."""
    global IS_RUNNING
    IS_RUNNING = False
    
    if icon:
        try:
            icon.stop()
        except Exception:
            pass

    def cleanup_and_force_exit():
        try:
            stop_all_servers()
        except Exception:
            pass
        time.sleep(0.2)
        os._exit(0)

    t = threading.Thread(target=cleanup_and_force_exit, daemon=True)
    t.start()
    
    # Fallback force exit after 0.5 seconds
    threading.Timer(0.5, lambda: os._exit(0)).start()

def main():
    print("=" * 60)
    print("  Geppy's GitBridge - Windows System Tray & Control Plane")
    print(f"  Web Dashboard: {SERVER_URL}")
    print("=" * 60)

    # Start Uvicorn in background thread
    uv_thread = threading.Thread(target=run_uvicorn_server, daemon=True)
    uv_thread.start()

    # Automatically open dashboard in browser on start (unless suppressed)
    if not os.environ.get("NO_AUTO_BROWSER"):
        threading.Thread(target=lambda: (time.sleep(1.5), webbrowser.open(SERVER_URL)), daemon=True).start()

    # System Tray Icon Setup
    icon_image = create_tray_icon_image()
    icon = pystray.Icon(
        "geppys_galactic_control_plane",
        icon_image,
        "Geppy's Galactic | Galaxy of Apps Control Plane",
        menu=Menu(create_dynamic_menu)
    )

    try:
        icon.run()
    except Exception as e:
        print(f"[TrayApp] Tray icon error: {e}", file=sys.stderr)
    finally:
        while IS_RUNNING:
            time.sleep(1)

if __name__ == "__main__":
    main()
