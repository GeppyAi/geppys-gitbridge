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


def launch_geppy_chat_app(mode: str = "default", app_slug: str = "") -> dict:
    """
    Launch the standalone Geppy's Voice Chat (`D:\\Geppy_Apps\\Geppy's Voice Chat`),
    Geppy's Screen Stream (`D:\\Geppy_Apps\\Geppy's Screen Stream`), or All-in-One Geppy Chat Companion
    external desktop app window (chromeless standalone window via Chrome/Edge `--app=` mode).
    """
    import shutil

    query_parts = []
    if app_slug:
        query_parts.append(f"app={app_slug}")

    if mode == "voice":
        route = "/geppy-voice"
        win_size = "500,850"
    elif mode == "stream":
        route = "/geppy-stream"
        win_size = "640,860"
    else:
        route = "/geppy-chat"
        win_size = "480,820"

    qs = ("?" + "&".join(query_parts)) if query_parts else ""
    target_url = f"{SERVER_URL}{route}{qs}"

    browser_candidates = [
        shutil.which("chrome"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        shutil.which("msedge"),
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]
    exe_path = next((p for p in browser_candidates if p and os.path.exists(p)), None)

    try:
        if exe_path:
            subprocess.Popen(
                [
                    exe_path,
                    f"--app={target_url}",
                    f"--window-size={win_size}",
                    "--new-window",
                ],
                close_fds=True,
            )
            return {"launched": True, "mode": "standalone_app_window", "url": target_url, "exe": exe_path}
    except Exception as e:
        print(f"[TrayApp] Standalone window launch fallback: {e}")

    webbrowser.open(target_url)
    return {"launched": True, "mode": "browser_tab", "url": target_url}


def open_geppy_chat_standalone(icon=None, item=None):
    """Open standalone Geppy Live Chat & Crew Companion app from System Tray."""
    threading.Thread(target=lambda: launch_geppy_chat_app("default"), daemon=True).start()


def open_geppy_voice_chat_standalone(icon=None, item=None):
    """Open standalone Geppy Chat app with Voice Chat & Crew Consultation active."""
    threading.Thread(target=lambda: launch_geppy_chat_app("voice"), daemon=True).start()


def open_geppy_stream_chat_standalone(icon=None, item=None):
    """Open standalone Geppy Chat app with Live Screen Streaming active."""
    threading.Thread(target=lambda: launch_geppy_chat_app("stream"), daemon=True).start()


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
    """Fetch currently running app servers directly from AppLauncherService (with HTTP fallback)."""
    try:
        from gitbridge.services.launcher_service import AppLauncherService
        return AppLauncherService.list_active_servers(run_health_check=False, include_control_plane=True)
    except Exception:
        try:
            with urllib.request.urlopen(f"{SERVER_URL}/api/servers", timeout=1.5) as response:
                return json.loads(response.read().decode())
        except Exception:
            return []

def fetch_all_apps():
    """Fetch all registered apps from DB or API."""
    try:
        from gitbridge.db.database import SessionLocal
        from gitbridge.db.models import AppProfileModel
        from gitbridge.services.launcher_service import ACTIVE_SERVERS
        db = SessionLocal()
        try:
            apps = db.query(AppProfileModel).all()
            out = []
            for a in apps:
                is_gb = a.slug in ("geppys-gitbridge", "geppy-s-gitbridge", "gitbridge")
                is_live = True if is_gb else (a.slug in ACTIVE_SERVERS)
                live_url = "http://127.0.0.1:8000" if is_gb else (ACTIVE_SERVERS[a.slug]["url"] if is_live else a.live_url)
                out.append({
                    "slug": a.slug,
                    "name": a.name,
                    "is_hidden": bool(getattr(a, "is_hidden", False)),
                    "is_live": is_live,
                    "live_url": live_url,
                    "port": 8000 if is_gb else (ACTIVE_SERVERS[a.slug]["port"] if is_live else None)
                })
            return out
        finally:
            db.close()
    except Exception:
        try:
            with urllib.request.urlopen(f"{SERVER_URL}/api/apps", timeout=1.5) as response:
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
                refresh_tray_menu()
            except Exception as e:
                print(f"[TrayApp] Failed to launch '{slug}': {e}")
        threading.Thread(target=do_launch, daemon=True).start()
    return handler

def get_all_app_launch_items():
    """Build dynamic menu items for launching or controlling ALL discovered applications directly from System Tray."""
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
            port = a.get("port")

            if is_live and live_url:
                port_str = f" :{port}" if port else " Live"
                live_submenu = Menu(
                    item(f"🌐 Open {name} ({live_url})", open_server_url(live_url)),
                    item(f"🔄 Restart {name}", restart_single_server(slug)),
                    item(f"⏹️ Stop & Close {name}", stop_single_server(slug))
                )
                items.append(item(f"🟢 {name} ({port_str.strip()})", live_submenu))
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
                refresh_tray_menu()
            except Exception as e:
                print(f"[TrayApp] Failed to restart server '{slug}': {e}")
        threading.Thread(target=do_restart, daemon=True).start()
    return handler

def stop_all_servers(icon=None, item=None):
    """Stop all active localhost app servers cleanly."""
    try:
        from gitbridge.services.launcher_service import AppLauncherService
        AppLauncherService.stop_all_servers()
    except Exception:
        try:
            req = urllib.request.Request(f"{SERVER_URL}/api/servers/stop-all", method="POST")
            urllib.request.urlopen(req, timeout=5)
        except Exception:
            pass
    refresh_tray_menu()

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
                from gitbridge.services.launcher_service import AppLauncherService
                AppLauncherService.stop_localhost_server(slug)
            except Exception:
                try:
                    req = urllib.request.Request(f"{SERVER_URL}/api/servers/{slug}", method="DELETE")
                    urllib.request.urlopen(req, timeout=3)
                except Exception as e:
                    print(f"[TrayApp] Failed to stop server '{slug}': {e}")
            refresh_tray_menu()
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
            all_ports = s.get("all_ports") or ([port] if port else [])
            ports_display = ", ".join(str(p) for p in all_ports) if len(all_ports) > 1 else str(port)
            name = s.get("name") or slug.replace("-", " ").title()
            mem = s.get("metrics", {}).get("memory_mb")
            mem_str = f" • {mem}MB" if mem else ""
            
            app_actions = Menu(
                item(f"🌐 Open {url} in Browser", open_server_url(url)),
                item(f"🔄 Restart {name}", restart_single_server(slug)),
                item(f"⏹️ Stop & Close {name}", stop_single_server(slug))
            )
            title = f"🟢 {name} (Port {ports_display}{mem_str})"
            items.append(item(title, app_actions))

        items.append(Menu.SEPARATOR)
        items.append(item("⏹️ Stop All Running Apps", stop_all_servers))
        items.append(item("📊 Open Port & Server Monitor", open_port_monitor_dashboard))
    else:
        items.append(item("No apps currently running", None, enabled=False))

    return items

def create_dynamic_menu():
    """Build dynamic system tray context menu items, surfacing running apps and the standalone Geppy Chat App directly."""
    servers = get_active_servers()
    count = len(servers) if isinstance(servers, list) else 0
    running_label = f"🟢 Currently Running Apps ({count})" if count > 0 else "⚪ Currently Running Apps (0)"

    menu_items = [
        item("💬 Launch Geppy Chat App (Standalone Window)", open_geppy_chat_standalone, default=True),
        item("🎙️ Geppy Voice Chat + Crew (Standalone App)", open_geppy_voice_chat_standalone),
        item("📺 Geppy Screen Stream Co-Designer (Standalone App)", open_geppy_stream_chat_standalone),
        Menu.SEPARATOR,
        item("🚀 Open Geppy's GitBridge Dashboard", open_dashboard),
        item("📊 Port & Server Monitor", open_port_monitor_dashboard),
        Menu.SEPARATOR,
        item(running_label, Menu(get_running_apps_menu)),
    ]

    # Also surface each running app right at the top level of the Tray Menu for 1-click Open / Restart / Stop!
    if count > 0 and isinstance(servers, list):
        for s in servers:
            slug = s.get("slug", "")
            url = s.get("url", "")
            port = s.get("port", "")
            name = s.get("name") or slug.replace("-", " ").title()
            quick_sub = Menu(
                item(f"🌐 Open {name} ({url})", open_server_url(url)),
                item(f"🔄 Restart {name}", restart_single_server(slug)),
                item(f"⏹️ Stop & Close {name}", stop_single_server(slug))
            )
            menu_items.append(item(f"   ↳ 🟢 {name} (:{port}) — Click to Stop/Open", quick_sub))
        menu_items.append(item(f"   ↳ ⏹️ Stop All Running Apps ({count})", stop_all_servers))

    menu_items.extend([
        Menu.SEPARATOR,
        item("📱 App Launch Directory", Menu(get_all_app_launch_items)),
        item("👨‍🚀 Captain Geppy AI Bridge (Web Tab)", lambda icon, it: webbrowser.open(f"{SERVER_URL}/#chat")),
        item("🛸 Source of Truth (SOT) Engine", lambda icon, it: webbrowser.open(f"{SERVER_URL}/#sot")),
        item("🔍 Scan App Folders", scan_folders),
        item("📁 Open App Folders in Explorer", open_workspace_folder),
        Menu.SEPARATOR,
        item("❌ Exit Geppy's GitBridge", quit_app)
    ])

    return tuple(menu_items)

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

TRAY_ICON_INSTANCE = None
TRAY_THREAD = None
_TRAY_LOCK = threading.Lock()
_DEFAULT_DESKTOP_HANDLE = None

if __name__ == "__main__":
    sys.modules.setdefault("gitbridge.tray_app", sys.modules[__name__])


def _attach_thread_to_interactive_desktop() -> bool:
    """
    Ensure the calling thread is attached to the Windows interactive 'Default' desktop.
    When started from background daemon runners or sandboxed shells, threads may inherit
    an isolated desktop (e.g. exebox-*) where Explorer's Shell_TrayWnd does not exist,
    causing Shell_NotifyIcon(NIM_ADD) to fail with E_FAIL.
    """
    if os.name != "nt":
        return False
    global _DEFAULT_DESKTOP_HANDLE
    try:
        import ctypes
        user32 = ctypes.windll.user32
        if not _DEFAULT_DESKTOP_HANDLE:
            _DEFAULT_DESKTOP_HANDLE = user32.OpenDesktopW("Default", 0, False, 0x10000000)  # GENERIC_ALL
        if _DEFAULT_DESKTOP_HANDLE:
            user32.SetThreadDesktop(_DEFAULT_DESKTOP_HANDLE)
            return True
    except Exception:
        pass
    return False


def _patch_pystray_win32_desktop():
    """Wrap pystray's Win32 Shell_NotifyIcon so any thread invoking it attaches to the Default desktop first."""
    if os.name != "nt":
        return
    try:
        from pystray._util import win32 as _pystray_win32
        if getattr(_pystray_win32, "_gitbridge_desktop_patched", False):
            return
        orig_sni = _pystray_win32.Shell_NotifyIcon

        def _wrapped_shell_notify_icon(code, data):
            _attach_thread_to_interactive_desktop()
            return orig_sni(code, data)

        _pystray_win32.Shell_NotifyIcon = _wrapped_shell_notify_icon
        _pystray_win32._gitbridge_desktop_patched = True
    except Exception:
        pass


def _promote_tray_icon_in_windows_11():
    """Ensure Windows 11 promotes the GitBridge / Python system tray icon directly onto the taskbar tray."""
    if os.name != "nt":
        return
    try:
        import winreg
        base_key_path = r"Control Panel\NotifyIconSettings"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, base_key_path, 0, winreg.KEY_READ) as parent:
            idx = 0
            subkeys = []
            while True:
                try:
                    subkeys.append(winreg.EnumKey(parent, idx))
                    idx += 1
                except OSError:
                    break

        for sk in subkeys:
            full_path = f"{base_key_path}\\{sk}"
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, full_path, 0, winreg.KEY_READ | winreg.KEY_SET_VALUE) as k:
                    exe_path = ""
                    tooltip = ""
                    try:
                        exe_path, _ = winreg.QueryValueEx(k, "ExecutablePath")
                    except OSError:
                        pass
                    try:
                        tooltip, _ = winreg.QueryValueEx(k, "InitialTooltip")
                    except OSError:
                        pass
                    combined = f"{exe_path} {tooltip}".lower()
                    if "python" in combined or "gitbridge" in combined:
                        winreg.SetValueEx(k, "IsPromoted", 0, winreg.REG_DWORD, 1)
            except OSError:
                continue
    except Exception:
        pass


def refresh_tray_menu():
    """Force Windows pystray icon to rebuild its popup menu immediately when running apps change."""
    global TRAY_ICON_INSTANCE
    icon = TRAY_ICON_INSTANCE
    if icon is not None and getattr(icon, "_running", False):
        try:
            _attach_thread_to_interactive_desktop()
            icon.menu = Menu(*create_dynamic_menu())
            icon.update_menu()
        except Exception:
            pass


def register_gitbridge_url_protocol():
    """Register the `gitbridge://` custom URL protocol in HKCU so the Chrome Extension can launch the Tray Menu & Server on demand."""
    if os.name != "nt":
        return False
    try:
        import winreg
        vbs_path = os.path.join(BASE_DIR, "launch_gitbridge_silent.vbs")
        cmd_str = f'wscript.exe "{vbs_path}" "%1"'

        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\gitbridge") as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, "URL:Geppy's GitBridge Protocol")
            winreg.SetValueEx(key, "URL Protocol", 0, winreg.REG_SZ, "")

        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\gitbridge\shell\open\command") as cmd_key:
            winreg.SetValueEx(cmd_key, "", 0, winreg.REG_SZ, cmd_str)
        return True
    except Exception as e:
        print(f"[TrayApp] Protocol registration notice: {e}")
        return False


def _tray_menu_auto_sync_loop():
    """Background loop that keeps the Windows System Tray menu synchronized with running apps."""
    _attach_thread_to_interactive_desktop()
    last_state = None
    while IS_RUNNING:
        try:
            servers = get_active_servers()
            sig = tuple((s.get("slug"), s.get("port")) for s in servers) if isinstance(servers, list) else ()
            if sig != last_state:
                last_state = sig
                refresh_tray_menu()
        except Exception:
            pass
        time.sleep(2.5)


def _run_tray_icon_blocking():
    global TRAY_ICON_INSTANCE
    _attach_thread_to_interactive_desktop()
    _patch_pystray_win32_desktop()
    icon_image = create_tray_icon_image()
    icon = pystray.Icon(
        "geppys_gitbridge_control_plane",
        icon_image,
        "Geppy's GitBridge | System Tray & App Launcher",
        menu=Menu(*create_dynamic_menu())
    )
    TRAY_ICON_INSTANCE = icon

    def _on_tray_setup(ic):
        _attach_thread_to_interactive_desktop()
        ic.visible = True
        _promote_tray_icon_in_windows_11()
        threading.Thread(target=_tray_menu_auto_sync_loop, daemon=True, name="TrayMenuSyncThread").start()

    try:
        icon.run(setup=_on_tray_setup)
    except Exception as e:
        print(f"[TrayApp] Tray icon error: {e}", file=sys.stderr)
    finally:
        TRAY_ICON_INSTANCE = None


def ensure_tray_running() -> dict:
    """Ensure the Windows System Tray menu icon is active. Starts it in a daemon thread if not already running."""
    global TRAY_ICON_INSTANCE, TRAY_THREAD
    register_gitbridge_url_protocol()
    with _TRAY_LOCK:
        if TRAY_ICON_INSTANCE is not None and getattr(TRAY_ICON_INSTANCE, "visible", False):
            refresh_tray_menu()
            _promote_tray_icon_in_windows_11()
            return {"tray_running": True, "action": "already_running"}
        if TRAY_THREAD is not None and TRAY_THREAD.is_alive():
            refresh_tray_menu()
            _promote_tray_icon_in_windows_11()
            return {"tray_running": True, "action": "already_running"}

        TRAY_THREAD = threading.Thread(target=_run_tray_icon_blocking, daemon=True, name="GitBridgeTrayThread")
        TRAY_THREAD.start()
        return {"tray_running": True, "action": "started_tray_menu"}


def main():
    sys.modules["gitbridge.tray_app"] = sys.modules[__name__]
    print("=" * 60)
    print("  Geppy's GitBridge - Windows System Tray & Control Plane")
    print(f"  Web Dashboard: {SERVER_URL}")
    print("=" * 60)

    register_gitbridge_url_protocol()

    # Start Uvicorn in background thread
    uv_thread = threading.Thread(target=run_uvicorn_server, daemon=True)
    uv_thread.start()

    # Automatically open dashboard in browser on start (unless suppressed)
    if not os.environ.get("NO_AUTO_BROWSER"):
        threading.Thread(target=lambda: (time.sleep(1.5), webbrowser.open(SERVER_URL)), daemon=True).start()

    # Run System Tray Icon on a dedicated thread so SetThreadDesktop("Default") always succeeds
    # (Windows SetThreadDesktop can fail on the main thread if CRT/hook handles already exist)
    global TRAY_THREAD
    TRAY_THREAD = threading.Thread(target=_run_tray_icon_blocking, daemon=True, name="GitBridgeTrayThread")
    TRAY_THREAD.start()
    while IS_RUNNING:
        time.sleep(1)


if __name__ == "__main__":
    main()


