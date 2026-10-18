from fastapi import FastAPI, Depends, HTTPException, Query, UploadFile, File, Form, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session
from typing import List, Optional
import os
import re
import time
import asyncio
import traceback

from gitbridge.db.database import get_db, init_db
from gitbridge.db.models import AppProfileModel, MediaAssetModel, DocManualModel
from gitbridge.schemas.app_profile import (
    AppProfileResponse, AppProfileCreate, AppProfileUpdate,
    MediaAssetBase, MediaAssetCreate, MediaAssetResponse,
    DocManualBase, DocManualCreate, DocManualResponse, AppStatus, AssetType
)
from gitbridge.services.github_service import GitHubService
from gitbridge.services.sheets_service import GoogleSheetsService
from gitbridge.services.ai_studio_service import AIStudioParser

init_db()

app = FastAPI(
    title="Geppy's Galactic API",
    description="App Galaxy Control Plane, SOT Engine & Captain Geppy Context Bridge",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_watchdog_exception_handler(request: Request, exc: Exception):
    """
    Aegis Watchdog Global Exception Guard:
    Ensures unhandled backend exceptions NEVER return plain-text 'Internal Server Error'
    (which causes 'SyntaxError: Unexpected token I, "Internal S"... is not valid JSON' in the frontend),
    and instead records the diagnosis in AntigravityDaemonPool and returns structured JSON with a correction offer.
    """
    tb_str = traceback.format_exc()
    path = request.url.path
    err_entry = None
    try:
        from gitbridge.services.antigravity_service import AntigravityDaemonPool
        err_entry = AntigravityDaemonPool.diagnose_and_record_error(
            raw_error=f"Unhandled exception at {request.method} {path}: {type(exc).__name__}: {str(exc)}\n{tb_str[-800:]}",
            source=f"watchdog-global-guard:{path}",
            slug="geppys-gitbridge",
            file_path="gitbridge/main.py",
            instruction=f"{request.method} {path}",
            model="Aegis Watchdog",
        )
    except Exception as log_err:
        print(f"[WatchdogExceptionHandler] Failed to record error: {log_err}")

    return JSONResponse(
        status_code=500,
        content={
            "error": True,
            "watchdog_caught": True,
            "detail": f"Watchdog intercepted {type(exc).__name__}: {str(exc)}",
            "message": f"Watchdog intercepted {type(exc).__name__}: {str(exc)}",
            "reply": (
                f"🛡️ **Aegis Watchdog Intercepted an Internal Error (`{type(exc).__name__}`)**:\n\n"
                f"Captain Geppy here! The Watchdog caught an unexpected server error on `{path}` (`{str(exc)[:180]}`) "
                f"before it could break your session with an invalid JSON response.\n\n"
                f"Use the **Watchdog Correction Panel** below to apply a self-healing fix or retry cleanly."
            ),
            "antigravity_error": err_entry,
        },
    )


static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/")
def read_root():
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {
        "status": "online",
        "system": "Geppy's GitBridge",
        "version": "0.1.0",
        "docs_url": "/docs"
    }


@app.get("/geppy-chat")
def read_geppy_chat_companion():
    """Serve the standalone Geppy Live Chat & Crew Companion app."""
    chat_path = os.path.join(static_dir, "geppy_chat.html")
    if os.path.exists(chat_path):
        return FileResponse(chat_path)
    return FileResponse(os.path.join(static_dir, "index.html"))


@app.get("/geppy-voice")
def read_geppy_voice_app():
    """Serve the standalone Geppy's Voice Chat app from D:\\Geppy_Apps\\Geppy's Voice Chat."""
    voice_path = r"D:\Geppy_Apps\Geppy's Voice Chat\index.html"
    if os.path.exists(voice_path):
        return FileResponse(voice_path)
    return FileResponse(os.path.join(static_dir, "geppy_chat.html"))


@app.get("/geppy-stream")
def read_geppy_stream_app():
    """Serve the standalone Geppy's Screen Stream app from D:\\Geppy_Apps\\Geppy's Screen Stream."""
    stream_path = r"D:\Geppy_Apps\Geppy's Screen Stream\index.html"
    if os.path.exists(stream_path):
        return FileResponse(stream_path)
    return FileResponse(os.path.join(static_dir, "geppy_chat.html"))


@app.post("/api/geppy-chat/launch")
def launch_geppy_chat_companion_endpoint(payload: dict = {}):
    """Launch the standalone Geppy Live Chat, Voice Chat, or Screen Stream desktop window."""
    from gitbridge.tray_app import launch_geppy_chat_app
    mode = (payload.get("mode") or "default").strip()
    app_slug = (payload.get("app_slug") or payload.get("slug") or "").strip()
    return launch_geppy_chat_app(mode=mode, app_slug=app_slug)


@app.get("/api/settings")
def get_settings():
    from gitbridge.services.workspace_service import WorkspaceService
    from gitbridge.services.central_key_service import CentralKeyService
    token = os.getenv("GITHUB_TOKEN", "")
    username = os.getenv("GITHUB_USERNAME", "")
    gemini_key = CentralKeyService.get_api_key()
    masked_token = f"{token[:4]}...{token[-4:]}" if len(token) > 8 else ("configured" if token else "")
    masked_gemini = CentralKeyService.get_masked_key(gemini_key)
    return {
        "github_username": username,
        "github_token_configured": bool(token),
        "github_token_masked": masked_token,
        "gemini_api_key_configured": bool(gemini_key),
        "gemini_api_key_masked": masked_gemini,
        "geppy_apps_dir": WorkspaceService.get_workspace_dir()
    }

@app.post("/api/settings")
def save_settings(settings: dict):
    from gitbridge.services.workspace_service import WorkspaceService
    from gitbridge.services.central_key_service import CentralKeyService
    token = settings.get("github_token", "").strip()
    username = settings.get("github_username", "").strip()
    workspace_dir = settings.get("geppy_apps_dir", "").strip()
    gemini_key = settings.get("gemini_api_key", "").strip()
    
    if workspace_dir:
        WorkspaceService.set_workspace_dir(workspace_dir)

    env_path = CentralKeyService.get_root_env_path()
    env_data = {}
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                if "=" in line and not line.startswith("#"):
                    parts = line.strip().split("=", 1)
                    if len(parts) == 2:
                        env_data[parts[0]] = parts[1]

    if token:
        env_data["GITHUB_TOKEN"] = token
        os.environ["GITHUB_TOKEN"] = token
    if username:
        env_data["GITHUB_USERNAME"] = username
        os.environ["GITHUB_USERNAME"] = username

    with open(env_path, "w", encoding="utf-8") as f:
        for k, v in env_data.items():
            f.write(f"{k}={v}\n")

    sync_res = None
    if gemini_key:
        sync_res = CentralKeyService.set_central_key(gemini_key, sync_apps=True)

    active_gemini = CentralKeyService.get_api_key()
    return {
        "message": "Settings updated successfully",
        "github_token_configured": bool(os.getenv("GITHUB_TOKEN")),
        "gemini_api_key_configured": bool(active_gemini),
        "gemini_api_key_masked": CentralKeyService.get_masked_key(active_gemini),
        "geppy_apps_dir": WorkspaceService.get_workspace_dir(),
        "sync_result": sync_res
    }

@app.get("/api/keys/gemini")
@app.get("/api/central-api-key")
def get_central_api_key():
    """Universal endpoint for any app or client in Geppy's App Universe to fetch central key."""
    from gitbridge.services.central_key_service import CentralKeyService
    key = CentralKeyService.get_api_key()
    if not key:
        raise HTTPException(status_code=404, detail="No Gemini API Key found in GitBridge Central Vault.")
    return {
        "status": "success",
        "configured": True,
        "gemini_api_key": key,
        "masked_key": CentralKeyService.get_masked_key(key),
        "active_model": "gemini-2.5-flash",
        "supported_models": ["gemini-2.5-flash", "gemini-3.8-flash"],
        "source": "GitBridge Central Vault",
        "gitbridge_url": "http://127.0.0.1:8000"
    }

@app.get("/api/keys/status")
def get_central_key_status_endpoint():
    """Retrieve live configuration status and model info for the central key."""
    from gitbridge.services.central_key_service import CentralKeyService
    return CentralKeyService.get_key_status()

@app.post("/api/keys/test")
def test_central_key_endpoint():
    """Live latency & connection check against Google Gemini API."""
    from gitbridge.services.central_key_service import CentralKeyService
    return CentralKeyService.test_connection()

@app.post("/api/keys/sync-all-apps")
def sync_all_apps_endpoint():
    """Synchronize central Gemini API key across all apps in d:\\Geppy_Apps."""
    from gitbridge.services.central_key_service import CentralKeyService
    return CentralKeyService.sync_all_apps()

@app.post("/api/keys/generate")
def generate_via_central_key_endpoint(payload: dict = {}):
    """Direct AI generation endpoint proxying through GitBridge central key."""
    from gitbridge.services.central_key_service import CentralKeyService
    prompt = (payload.get("prompt") or "").strip()
    system_instruction = (payload.get("system_instruction") or "").strip()
    model = (payload.get("model") or "gemini-2.5-flash").strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="Prompt is required")
    messages = [{"role": "user", "parts": [{"text": prompt}]}]
    res = CentralKeyService.call_gemini(messages, system_instruction, model_preference=model)
    if not res:
        raise HTTPException(status_code=502, detail="Gemini call failed or timed out.")
    return {"status": "success", "text": res, "model": model}

@app.post("/api/workspace/scan")
def scan_workspace_endpoint(db: Session = Depends(get_db)):
    from gitbridge.services.workspace_service import WorkspaceService
    res = WorkspaceService.scan_workspace_directory(db)
    return res

@app.post("/api/apps/{slug}/download-local")
def download_local_endpoint(slug: str, db: Session = Depends(get_db)):
    app_obj = db.query(AppProfileModel).filter(AppProfileModel.slug == slug).first()
    if not app_obj:
        raise HTTPException(status_code=404, detail=f"App with slug '{slug}' not found")

    from gitbridge.services.workspace_service import WorkspaceService
    res = WorkspaceService.download_and_link_app(app_obj, db)
    return res

def serialize_app_profile(app_obj: AppProfileModel, db: Session) -> dict:
    from gitbridge.services.workspace_service import WorkspaceService
    from gitbridge.services.launcher_service import ACTIVE_SERVERS

    sync_info = WorkspaceService.get_app_sync_status(app_obj)
    if sync_info.get("local_path") and app_obj.local_path != sync_info["local_path"]:
        app_obj.local_path = sync_info["local_path"]
        db.commit()

    is_gb = app_obj.slug in ("geppys-gitbridge", "geppy-s-gitbridge", "gitbridge")
    is_live = True if is_gb else (app_obj.slug in ACTIVE_SERVERS)
    live_url = "http://127.0.0.1:8000" if is_gb else (ACTIVE_SERVERS[app_obj.slug]["url"] if is_live else app_obj.live_url)

    icon_url = app_obj.icon_url
    if icon_url and icon_url.startswith("/api/apps/"):
        fname = icon_url.split("/")[-1]
        base_local = sync_info.get("local_path") or app_obj.local_path
        fpath = os.path.join(base_local, "assets", fname) if base_local else None
        if not fpath or not os.path.exists(fpath):
            icon_url = None

    return {
        "id": app_obj.id,
        "slug": app_obj.slug,
        "name": app_obj.name,
        "description": app_obj.description,
        "status": app_obj.status,
        "github_url": app_obj.github_url,
        "github_repo_name": app_obj.github_repo_name,
        "ai_studio_link": app_obj.ai_studio_link,
        "local_path": sync_info.get("local_path") or app_obj.local_path,
        "local_exists": sync_info["local_exists"],
        "github_exists": sync_info["github_exists"],
        "sync_state": sync_info["sync_state"],
        "sync_label": sync_info["sync_label"],
        "launch_command": app_obj.launch_command,
        "live_url": live_url,
        "icon_url": icon_url,
        "is_live": is_live,
        "tech_stack": app_obj.tech_stack,
        "system_instructions": app_obj.system_instructions,
        "feature_breakdown": app_obj.feature_breakdown,
        "priority_tier": app_obj.priority_tier,
        "health_report_md": app_obj.health_report_md,
        "last_commit_at": app_obj.last_commit_at,
        "open_issues_count": app_obj.open_issues_count or 0,
        "tags": app_obj.tags,
        "backlog": getattr(app_obj, "backlog", []) or [],
        "version": app_obj.version or "0.1.0",
        "is_hidden": bool(getattr(app_obj, "is_hidden", False)),
        "created_at": app_obj.created_at,
        "updated_at": app_obj.updated_at,
        "assets": app_obj.assets,
        "manuals": app_obj.manuals
    }

@app.get("/api/apps", response_model=List[AppProfileResponse])
def list_apps(
    status: Optional[AppStatus] = None,
    include_hidden: bool = Query(False),
    only_hidden: bool = Query(False),
    db: Session = Depends(get_db)
):
    query = db.query(AppProfileModel)
    if status:
        query = query.filter(AppProfileModel.status == status)
    if only_hidden:
        query = query.filter(AppProfileModel.is_hidden == True)
    elif not include_hidden:
        query = query.filter((AppProfileModel.is_hidden == False) | (AppProfileModel.is_hidden == None))
    apps = query.all()
    return [serialize_app_profile(a, db) for a in apps]

@app.post("/api/apps/{slug}/hide")
def hide_app_endpoint(slug: str, db: Session = Depends(get_db)):
    app_obj = db.query(AppProfileModel).filter(AppProfileModel.slug == slug).first()
    if not app_obj:
        raise HTTPException(status_code=404, detail=f"App with slug '{slug}' not found")
    app_obj.is_hidden = True
    db.commit()
    return {"slug": slug, "is_hidden": True, "message": f"App '{app_obj.name}' is now hidden from catalog and system tray."}

@app.post("/api/apps/{slug}/unhide")
def unhide_app_endpoint(slug: str, db: Session = Depends(get_db)):
    app_obj = db.query(AppProfileModel).filter(AppProfileModel.slug == slug).first()
    if not app_obj:
        raise HTTPException(status_code=404, detail=f"App with slug '{slug}' not found")
    app_obj.is_hidden = False
    db.commit()
    return {"slug": slug, "is_hidden": False, "message": f"App '{app_obj.name}' restored to catalog and system tray."}

@app.post("/api/apps/{slug}/toggle-hide")
def toggle_hide_app_endpoint(slug: str, db: Session = Depends(get_db)):
    app_obj = db.query(AppProfileModel).filter(AppProfileModel.slug == slug).first()
    if not app_obj:
        raise HTTPException(status_code=404, detail=f"App with slug '{slug}' not found")
    app_obj.is_hidden = not bool(app_obj.is_hidden)
    db.commit()
    status_str = "hidden" if app_obj.is_hidden else "visible"
    return {
        "slug": slug,
        "is_hidden": bool(app_obj.is_hidden),
        "message": f"App '{app_obj.name}' is now {status_str} in catalog and system tray."
    }

@app.get("/api/apps/{slug}", response_model=AppProfileResponse)
def get_app(slug: str, db: Session = Depends(get_db)):
    app_obj = db.query(AppProfileModel).filter(AppProfileModel.slug == slug).first()
    if not app_obj:
        raise HTTPException(status_code=404, detail=f"App with slug '{slug}' not found")
    return serialize_app_profile(app_obj, db)

@app.post("/api/apps", response_model=AppProfileResponse)
def create_app(app_in: AppProfileCreate, db: Session = Depends(get_db)):
    existing = db.query(AppProfileModel).filter(AppProfileModel.slug == app_in.slug).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"App with slug '{app_in.slug}' already exists")

    app_obj = AppProfileModel(
        slug=app_in.slug,
        name=app_in.name,
        description=app_in.description,
        status=app_in.status,
        github_url=app_in.github_url,
        github_repo_name=app_in.github_repo_name,
        ai_studio_link=app_in.ai_studio_link,
        system_instructions=app_in.system_instructions,
        version=app_in.version
    )
    app_obj.tech_stack = app_in.tech_stack
    app_obj.tags = app_in.tags

    db.add(app_obj)
    db.commit()
    db.refresh(app_obj)
    return serialize_app_profile(app_obj, db)

@app.patch("/api/apps/{slug}", response_model=AppProfileResponse)
def update_app(slug: str, app_in: AppProfileUpdate, db: Session = Depends(get_db)):
    app_obj = db.query(AppProfileModel).filter(AppProfileModel.slug == slug).first()
    if not app_obj:
        raise HTTPException(status_code=404, detail=f"App with slug '{slug}' not found")

    update_data = app_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field == "tech_stack":
            app_obj.tech_stack = value
        elif field == "tags":
            app_obj.tags = value
        else:
            setattr(app_obj, field, value)

    db.commit()
    db.refresh(app_obj)
    return serialize_app_profile(app_obj, db)

@app.post("/api/apps/{slug}/analyze")
def analyze_app_endpoint(slug: str, db: Session = Depends(get_db)):
    app_obj = db.query(AppProfileModel).filter(AppProfileModel.slug == slug).first()
    if not app_obj:
        raise HTTPException(status_code=404, detail=f"App with slug '{slug}' not found")

    from gitbridge.services.analyzer_service import AppAnalyzerService
    analyzer = AppAnalyzerService()
    result = analyzer.analyze_and_autofill_app(app_obj, db)
    return result

@app.post("/api/tray/ensure")
def ensure_tray_menu_endpoint():
    """Ensure the Windows System Tray menu is active and running."""
    try:
        from gitbridge.tray_app import ensure_tray_running
        return ensure_tray_running()
    except Exception as e:
        return {"tray_running": False, "error": str(e)}

@app.post("/api/apps/{slug}/launch")
def launch_app_endpoint(slug: str, db: Session = Depends(get_db)):
    # Always ensure the Windows System Tray Menu is running when launching an app
    tray_status = {}
    try:
        from gitbridge.tray_app import ensure_tray_running
        tray_status = ensure_tray_running()
    except Exception:
        pass

    app_obj = db.query(AppProfileModel).filter(AppProfileModel.slug == slug).first()
    if not app_obj:
        raise HTTPException(status_code=404, detail=f"App with slug '{slug}' not found")

    from gitbridge.services.launcher_service import AppLauncherService
    result = AppLauncherService.launch_localhost(app_obj)
    result["tray_status"] = tray_status

    # Save detected live_url to database profile if launched
    if result.get("launched") and result.get("target"):
        app_obj.live_url = result["target"]
        db.commit()

    try:
        from gitbridge.tray_app import refresh_tray_menu
        refresh_tray_menu()
    except Exception:
        pass

    return result

async def _update_icon_async(app_obj, icon_url, db):
    """Internal helper to avoid main-thread blocking."""
    try:
        app_obj.icon_url = icon_url
        db.commit()
        db.refresh(app_obj)
    except Exception as e:
        print(f"Error in background update: {e}")

@app.post("/api/apps/{slug}/set-icon")
async def set_app_icon_endpoint(slug: str, payload: dict = {}, background_tasks: BackgroundTasks = BackgroundTasks(), db: Session = Depends(get_db)):
    app_obj = db.query(AppProfileModel).filter(AppProfileModel.slug == slug).first()
    if not app_obj:
        raise HTTPException(status_code=404, detail=f"App with slug '{slug}' not found")

    icon_url = payload.get("icon_url") or payload.get("url")
    if not icon_url:
        raise HTTPException(status_code=400, detail="icon_url parameter is required")

    # Run DB update in background to prevent UI freeze
    background_tasks.add_task(_update_icon_async, app_obj, icon_url, db)
    return {"message": "Update queued", "slug": slug}

@app.get("/api/servers")
def get_active_servers():
    from gitbridge.services.launcher_service import AppLauncherService
    return AppLauncherService.list_active_servers()

@app.delete("/api/servers/{slug}")
def stop_active_server(slug: str):
    from gitbridge.services.launcher_service import AppLauncherService
    stopped = AppLauncherService.stop_localhost_server(slug)
    try:
        from gitbridge.tray_app import refresh_tray_menu
        refresh_tray_menu()
    except Exception:
        pass
    return {"slug": slug, "stopped": stopped}

@app.post("/api/servers/{slug}/stop")
def stop_server_post(slug: str):
    from gitbridge.services.launcher_service import AppLauncherService
    stopped = AppLauncherService.stop_localhost_server(slug)
    try:
        from gitbridge.tray_app import refresh_tray_menu
        refresh_tray_menu()
    except Exception:
        pass
    return {"slug": slug, "stopped": stopped}

@app.post("/api/servers/{slug}/restart")
def restart_server_endpoint(slug: str, db: Session = Depends(get_db)):
    app_obj = db.query(AppProfileModel).filter(AppProfileModel.slug == slug).first()
    if not app_obj:
        raise HTTPException(status_code=404, detail=f"App with slug '{slug}' not found")

    from gitbridge.services.launcher_service import AppLauncherService
    import time
    AppLauncherService.stop_localhost_server(slug)
    time.sleep(0.8)
    res = AppLauncherService.launch_localhost(app_obj)
    if res.get("launched") and res.get("target"):
        app_obj.live_url = res["target"]
        db.commit()
    try:
        from gitbridge.tray_app import refresh_tray_menu
        refresh_tray_menu()
    except Exception:
        pass
    return res

@app.delete("/api/servers")
@app.post("/api/servers/stop-all")
def stop_all_servers_endpoint():
    from gitbridge.services.launcher_service import AppLauncherService
    count = AppLauncherService.stop_all_servers()
    try:
        from gitbridge.tray_app import refresh_tray_menu
        refresh_tray_menu()
    except Exception:
        pass
    return {"message": f"Stopped {count} active servers", "stopped_count": count}

@app.get("/api/monitor/status")
def get_monitor_status():
    from gitbridge.services.launcher_service import AppLauncherService
    return AppLauncherService.get_monitor_summary()

@app.post("/api/apps/{slug}/open-folder")
def open_app_folder_endpoint(slug: str, db: Session = Depends(get_db)):
    app_obj = db.query(AppProfileModel).filter(AppProfileModel.slug == slug).first()
    if not app_obj:
        raise HTTPException(status_code=404, detail=f"App with slug '{slug}' not found")

    from gitbridge.services.launcher_service import AppLauncherService
    local_path = AppLauncherService.detect_local_path(app_obj)
    if not local_path:
        raise HTTPException(status_code=404, detail=f"Local path for '{slug}' not found on disk")

    success = AppLauncherService.open_local_folder(local_path)
    return {"slug": slug, "local_path": local_path, "opened": success}

@app.post("/api/apps/{slug}/antigravity/launch")
def launch_antigravity_cli_endpoint(slug: str, db: Session = Depends(get_db)):
    app_obj = db.query(AppProfileModel).filter(AppProfileModel.slug == slug).first()
    if not app_obj:
        raise HTTPException(status_code=404, detail=f"App with slug '{slug}' not found")

    from gitbridge.services.workspace_service import WorkspaceService
    res = WorkspaceService.launch_antigravity_cli(app_obj)
    return res

@app.get("/api/apps/{slug}/files/tree")
def get_app_file_tree_endpoint(slug: str, db: Session = Depends(get_db)):
    app_obj = db.query(AppProfileModel).filter(AppProfileModel.slug == slug).first()
    if not app_obj:
        raise HTTPException(status_code=404, detail=f"App with slug '{slug}' not found")

    from gitbridge.services.workspace_service import WorkspaceService
    files = WorkspaceService.get_app_file_tree(app_obj)
    return {"slug": slug, "local_path": app_obj.local_path, "files": files}

@app.get("/api/apps/{slug}/files/content")
def get_app_file_content_endpoint(slug: str, file_path: str = Query(...), db: Session = Depends(get_db)):
    app_obj = db.query(AppProfileModel).filter(AppProfileModel.slug == slug).first()
    if not app_obj:
        raise HTTPException(status_code=404, detail=f"App with slug '{slug}' not found")

    from gitbridge.services.workspace_service import WorkspaceService
    res = WorkspaceService.read_app_file(app_obj, file_path)
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("message", "Could not read file"))
    return res

@app.post("/api/apps/{slug}/files/content")
def save_app_file_content_endpoint(slug: str, payload: dict = {}, db: Session = Depends(get_db)):
    app_obj = db.query(AppProfileModel).filter(AppProfileModel.slug == slug).first()
    if not app_obj:
        raise HTTPException(status_code=404, detail=f"App with slug '{slug}' not found")

    file_path = payload.get("file_path")
    content = payload.get("content", "")
    is_preview_revert = bool(payload.get("is_preview_revert", False))

    if not file_path:
        raise HTTPException(status_code=400, detail="file_path is required")

    from gitbridge.services.workspace_service import WorkspaceService
    res = WorkspaceService.save_app_file(app_obj, file_path, content, is_preview_revert=is_preview_revert)
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("message", "Could not save file"))
    return res

@app.post("/api/apps/{slug}/files/preview-mode")
def set_app_preview_mode_endpoint(slug: str, payload: dict = {}, db: Session = Depends(get_db)):
    app_obj = db.query(AppProfileModel).filter(AppProfileModel.slug == slug).first()
    if not app_obj:
        raise HTTPException(status_code=404, detail=f"App with slug '{slug}' not found")

    enabled = bool(payload.get("enabled", True))
    file_path = payload.get("file_path")
    edited_content = payload.get("edited_content")
    baseline_content = payload.get("baseline_content")

    from gitbridge.services.workspace_service import WorkspaceService
    res = WorkspaceService.set_app_preview_mode(
        app_obj,
        enabled=enabled,
        file_path=file_path,
        edited_content=edited_content,
        baseline_content=baseline_content
    )
    return res

@app.post("/api/chat")
def chat_api_endpoint(payload: dict = {}, db: Session = Depends(get_db)):
    prompt = (payload.get("message") or payload.get("prompt") or "").strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="Message prompt is required")

    app_slug = payload.get("app_slug")
    file_path = payload.get("file_path")
    history = payload.get("history", [])
    is_image = payload.get("is_image", False)
    agent_id = payload.get("agent_id")
    screen_frame_b64 = payload.get("screen_frame_b64")
    voice_mode = bool(payload.get("voice_mode", False))
    include_audio = bool(payload.get("include_audio", False) or voice_mode)
    consult_crew = bool(payload.get("consult_crew", False))
    consult_agents = payload.get("consult_agents")

    from gitbridge.services.chat_service import ChatService
    return ChatService.process_chat(
        prompt=prompt,
        app_slug=app_slug,
        file_path=file_path,
        history=history,
        is_image=is_image,
        agent_id=agent_id,
        screen_frame_b64=screen_frame_b64,
        voice_mode=voice_mode,
        include_audio=include_audio,
        consult_crew=consult_crew,
        consult_agents=consult_agents,
        db=db
    )


@app.post("/api/geppy/tts")
def geppy_ai_tts_endpoint(payload: dict = {}):
    """
    Synthesize natural AI Voice audio for Captain Geppy (or any specialist crew member)
    using Gemini 2.5 Flash Native Audio TTS ('gemini-2.5-flash-preview-tts'), returning a WAV data URL.
    """
    text = (payload.get("text") or payload.get("message") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is required for AI voice synthesis")
    voice_name = (payload.get("voice_name") or payload.get("voice") or "Puck").strip()
    persona = (payload.get("persona") or "Captain Geppy").strip()

    from gitbridge.services.central_key_service import CentralKeyService
    audio_data_url = CentralKeyService.synthesize_speech_wav_b64(
        text=text,
        voice_name=voice_name,
        persona=persona
    )
    return {
        "success": bool(audio_data_url),
        "audio_data_url": audio_data_url,
        "voice_name": voice_name,
        "voice_engine": "gemini-2.5-flash-preview-tts" if audio_data_url else "browser-fallback"
    }


# --- Chrome Extension Companion API Endpoints ---
@app.get("/api/extension/detect-app")
def extension_detect_app_endpoint(url: str = Query(...), db: Session = Depends(get_db)):
    """Detect which app is running at the given browser tab URL."""
    from gitbridge.services.extension_service import ExtensionService
    from gitbridge.services.launcher_service import ACTIVE_SERVERS
    from urllib.parse import urlparse
    match = ExtensionService.detect_active_app(url, ACTIVE_SERVERS, db)
    if not match:
        parsed = urlparse(url)
        suggested_name = f"Port {parsed.port} App" if parsed.port else (parsed.netloc.split(".")[0].title() if parsed.netloc else "New App")
        return {
            "matched": False,
            "app": None,
            "url": url,
            "port": parsed.port,
            "suggested_name": suggested_name
        }
    app_obj = db.query(AppProfileModel).filter(AppProfileModel.slug == match["slug"]).first()
    return {
        "matched": True,
        "match_type": match["match_type"],
        "app": serialize_app_profile(app_obj, db) if app_obj else None
    }

@app.post("/api/apps/{slug}/associate-url")
def associate_app_url_endpoint(slug: str, payload: dict = {}, db: Session = Depends(get_db)):
    """Associate a live browser tab URL / port with an application profile and mark it live."""
    live_url = (payload.get("live_url") or "").strip()
    if not live_url:
        raise HTTPException(status_code=400, detail="live_url is required")
    from gitbridge.services.extension_service import ExtensionService
    result = ExtensionService.associate_app_url(slug=slug, url=live_url, db=db)
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("message", "App not found"))
    return result

@app.post("/api/extension/register-app")
def extension_register_app_endpoint(payload: dict = {}, db: Session = Depends(get_db)):
    """
    Register a newly discovered app tab directly from Galactic Chrome Extension.
    Supports creating a folder in d:\\Geppy_Apps or linking an external folder,
    injects Central Gemini Key, and runs Deep AI Analysis with Help Manual generation.
    """
    from gitbridge.services.central_key_service import CentralKeyService
    from gitbridge.services.analyzer_service import AppAnalyzerService
    from urllib.parse import urlparse

    name = (payload.get("name") or "").strip()
    live_url = (payload.get("live_url") or "").strip()
    local_path = (payload.get("local_path") or payload.get("custom_path") or "").strip()
    create_in_workspace = bool(payload.get("create_in_workspace", True))
    run_deep_analysis = bool(payload.get("run_deep_analysis", True))

    if not name:
        parsed = urlparse(live_url)
        name = f"Port {parsed.port} App" if parsed.port else (parsed.netloc or "New Application")

    base_slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or f"app-{int(time.time())}"
    slug = base_slug
    counter = 2
    while db.query(AppProfileModel).filter(AppProfileModel.slug == slug).first():
        slug = f"{base_slug}-{counter}"
        counter += 1

    resolved_path = None
    if local_path and os.path.exists(local_path):
        resolved_path = os.path.abspath(local_path)
    elif create_in_workspace:
        from gitbridge.services.workspace_service import WorkspaceService
        primary_dir = WorkspaceService.get_workspace_dirs()[0]
        resolved_path = os.path.join(primary_dir, name)
        os.makedirs(resolved_path, exist_ok=True)

    if resolved_path and os.path.exists(resolved_path):
        key = CentralKeyService.get_api_key()
        if key:
            env_file = os.path.join(resolved_path, ".env")
            if not os.path.exists(env_file):
                try:
                    with open(env_file, "w", encoding="utf-8") as f:
                        f.write(
                            f"GEMINI_API_KEY={key}\n"
                            f"GOOGLE_API_KEY={key}\n"
                            f"VITE_GEMINI_API_KEY={key}\n"
                            f"NEXT_PUBLIC_GEMINI_API_KEY={key}\n"
                            f"REACT_APP_GEMINI_API_KEY={key}\n"
                        )
                except Exception as e:
                    print(f"[RegisterApp] Error creating .env in {resolved_path}: {e}")

    app_obj = AppProfileModel(
        slug=slug,
        name=name,
        description=f"Application active at {live_url}" if live_url else "",
        status=AppStatus.IN_DEVELOPMENT,
        live_url=live_url or None,
        local_path=resolved_path
    )
    db.add(app_obj)
    db.commit()
    db.refresh(app_obj)

    analysis_res = None
    if run_deep_analysis:
        try:
            analyzer = AppAnalyzerService()
            analysis_res = analyzer.deep_analyze_and_generate_docs(app_obj, db)
        except Exception as e:
            print(f"[RegisterApp] Deep analysis notice for {slug}: {e}")

    return {
        "success": True,
        "message": f"Successfully registered '{app_obj.name}' in Geppy's Galactic!",
        "app": serialize_app_profile(app_obj, db),
        "analysis": analysis_res
    }

@app.post("/api/apps/{slug}/deep-analyze")
def deep_analyze_app_endpoint(slug: str, db: Session = Depends(get_db)):
    """Trigger deep technical analysis, GitHub description, and User Guide help file generation on any app."""
    app_obj = db.query(AppProfileModel).filter(AppProfileModel.slug == slug).first()
    if not app_obj:
        raise HTTPException(status_code=404, detail=f"App with slug '{slug}' not found")
    from gitbridge.services.analyzer_service import AppAnalyzerService
    analyzer = AppAnalyzerService()
    return analyzer.deep_analyze_and_generate_docs(app_obj, db)

@app.post("/api/extension/brainstorm")
def extension_brainstorm_endpoint(payload: dict = {}, db: Session = Depends(get_db)):
    """Conversational brainstorming endpoint that outputs inspiring concepts, live screen co-design, crew consultation, real-time task backlog, and visual asset generation."""
    message = (payload.get("message") or payload.get("prompt") or "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message is required")
    slug = payload.get("slug")
    file_path = payload.get("file_path")
    history = payload.get("history", [])
    is_image = payload.get("is_image", False)
    agent_id = payload.get("agent_id")
    screen_frame_b64 = payload.get("screen_frame_b64")
    voice_mode = bool(payload.get("voice_mode", False))
    consult_crew = bool(payload.get("consult_crew", False))
    consult_agents = payload.get("consult_agents")

    from gitbridge.services.extension_service import ExtensionService
    result = ExtensionService.brainstorm(
        slug=slug,
        message=message,
        history=history,
        file_path=file_path,
        is_image=is_image,
        agent_id=agent_id,
        screen_frame_b64=screen_frame_b64,
        voice_mode=voice_mode,
        consult_crew=consult_crew,
        consult_agents=consult_agents,
        db=db
    )
    return result

@app.post("/api/extension/proactive-suggestions")
def extension_proactive_suggestions_endpoint(payload: dict = {}, db: Session = Depends(get_db)):
    """Proactively analyze active file and recommend 3-4 concrete design & feature improvements."""
    slug = payload.get("slug", "")
    file_path = payload.get("file_path", "")
    content = payload.get("content", "")

    if not content and slug and file_path:
        app_obj = db.query(AppProfileModel).filter(AppProfileModel.slug == slug).first()
        if app_obj:
            from gitbridge.services.workspace_service import WorkspaceService
            file_res = WorkspaceService.read_app_file(app_obj, file_path)
            if file_res.get("success"):
                content = file_res.get("content", "")

    from gitbridge.services.extension_service import ExtensionService
    suggestions = ExtensionService.get_proactive_suggestions(slug=slug, file_path=file_path, content=content, db=db)
    return {"slug": slug, "file_path": file_path, "suggestions": suggestions}

@app.post("/api/extension/execute")
@app.post("/api/extension/apply-design")
def extension_apply_design_endpoint(payload: dict = {}, db: Session = Depends(get_db)):
    """Apply an AI design suggestion, brainstorm task, or Agent Crew Proceed task to code via Antigravity."""
    slug = (payload.get("slug") or payload.get("app_slug") or "").strip()
    file_path = (payload.get("file_path") or payload.get("target_file") or "").strip()
    current_code = payload.get("current_code", "")
    instruction = (
        payload.get("instruction")
        or payload.get("task_prompt")
        or payload.get("suggested_prompt")
        or payload.get("task_title")
        or ""
    ).strip()
    save_to_disk = bool(payload.get("save_to_disk", True))

    if not instruction:
        raise HTTPException(status_code=400, detail="Instruction is required")

    from gitbridge.services.extension_service import ExtensionService
    result = ExtensionService.apply_design(
        slug=slug,
        file_path=file_path,
        current_code=current_code,
        instruction=instruction,
        db=db,
        save_to_disk=save_to_disk
    )
    return result

@app.get("/api/extension/antigravity/status")
def extension_antigravity_status_endpoint():
    """Return status and capabilities of the integrated Google Antigravity SDK & local IDE."""
    from gitbridge.services.antigravity_service import AntigravityService
    return AntigravityService.get_antigravity_status()

@app.get("/api/extension/antigravity/errors")
def extension_antigravity_errors_endpoint(
    slug: Optional[str] = Query(None),
    unresolved_only: bool = Query(False),
    limit: int = Query(15),
):
    """Return structured Antigravity errors with diagnosis (what_is_the_error, what_needs_done, suggested_replies)."""
    from gitbridge.services.antigravity_service import AntigravityDaemonPool
    errors = AntigravityDaemonPool.get_errors(
        slug=slug,
        unresolved_only=unresolved_only,
        limit=limit,
    )
    open_errors = [e for e in errors if e.get("status") == "open"]
    latest_open = open_errors[0] if open_errors else None
    return {
        "errors": errors,
        "latest_error": latest_open or (errors[0] if errors else None),
        "latest_unresolved": latest_open,
        "open_count": len(open_errors),
    }

@app.post("/api/extension/antigravity/errors/clear")
def extension_antigravity_clear_errors_endpoint(payload: dict = {}):
    """Clear or dismiss Antigravity errors."""
    from gitbridge.services.antigravity_service import AntigravityDaemonPool
    cleared = AntigravityDaemonPool.clear_errors(
        slug=payload.get("slug"),
        error_id=payload.get("error_id"),
    )
    return {"success": True, "cleared": cleared}

@app.post("/api/extension/antigravity/report-error")
def extension_antigravity_report_error_endpoint(payload: dict = {}):
    """Record and diagnose an external or user-reported Antigravity error so Galactic can display diagnosis and accept a reply."""
    from gitbridge.services.antigravity_service import AntigravityDaemonPool
    raw_error = (payload.get("error") or payload.get("raw_error") or payload.get("message") or "").strip()
    if not raw_error:
        raise HTTPException(status_code=400, detail="error message is required")
    entry = AntigravityDaemonPool.diagnose_and_record_error(
        raw_error=raw_error,
        source=payload.get("source") or "galactic-reported",
        slug=payload.get("slug") or payload.get("app_slug") or "",
        file_path=payload.get("file_path") or payload.get("target_file") or "",
        instruction=payload.get("instruction") or "",
        model=payload.get("model") or "",
    )
    return {"success": True, "error": entry}

@app.post("/api/extension/antigravity/respond")
def extension_antigravity_respond_endpoint(payload: dict = {}, db: Session = Depends(get_db)):
    """Accept a user's in-chat response/instruction to Antigravity in Galactic to resolve an error or retry with guidance."""
    from gitbridge.services.antigravity_service import AntigravityService
    slug = (payload.get("slug") or payload.get("app_slug") or "").strip()
    response_text = (
        payload.get("response_text")
        or payload.get("user_response")
        or payload.get("message")
        or payload.get("reply")
        or payload.get("instruction")
        or ""
    ).strip()
    error_id = payload.get("error_id")
    action = payload.get("action") or "reply"
    file_path = payload.get("file_path") or payload.get("target_file")
    original_instruction = payload.get("original_instruction")
    app_obj = db.query(AppProfileModel).filter(AppProfileModel.slug == slug).first() if slug else None
    return AntigravityService.respond_to_antigravity(
        app_obj=app_obj,
        slug=slug,
        response_text=response_text,
        user_response=response_text,
        error_id=error_id,
        action=action,
        file_path=file_path,
        original_instruction=original_instruction,
        db=db,
    )

@app.post("/api/live-stream/frame")
def push_live_screen_stream_frame_endpoint(payload: dict = {}):
    """Push a live screen capture frame from GitBridge ('gitbridge') or Galactic ('galactic') so Geppy can see what we are working on."""
    from gitbridge.services.chat_service import LiveScreenStreamHub
    frame_b64 = (payload.get("frame_b64") or payload.get("image_b64") or "").strip()
    if not frame_b64:
        raise HTTPException(status_code=400, detail="frame_b64 is required")
    source = (payload.get("source") or "galactic").strip()
    return LiveScreenStreamHub.push_frame(
        source=source,
        frame_b64=frame_b64,
        app_slug=payload.get("app_slug") or payload.get("slug"),
        viewport_title=payload.get("viewport_title") or payload.get("title"),
        viewport_url=payload.get("viewport_url") or payload.get("url"),
        width=payload.get("width"),
        height=payload.get("height"),
    )

@app.get("/api/live-stream/status")
def get_live_screen_stream_status_endpoint(include_thumbnails: bool = Query(True)):
    """Return status and latest thumbnails of active GitBridge & Galactic screen streams."""
    from gitbridge.services.chat_service import LiveScreenStreamHub
    return LiveScreenStreamHub.get_status(include_thumbnails=include_thumbnails)

@app.post("/api/live-stream/stop")
def stop_live_screen_stream_endpoint(payload: dict = {}):
    """Stop one or all active screen streams."""
    from gitbridge.services.chat_service import LiveScreenStreamHub
    return LiveScreenStreamHub.stop_stream(source=payload.get("source"))

@app.post("/api/agents/consult")
def consult_agents_with_geppy_endpoint(payload: dict = {}, db: Session = Depends(get_db)):
    """Voice & Live Co-Design endpoint where Geppy consults with the specialized Agent Crew on what the user is working on."""
    from gitbridge.services.agent_crew_service import AgentCrewService
    prompt = (payload.get("prompt") or payload.get("message") or "Review what we are currently working on and advise.").strip()
    app_slug = payload.get("app_slug") or payload.get("slug")
    file_path = payload.get("file_path")
    history = payload.get("history", [])
    agent_ids = payload.get("agent_ids")
    screen_frame_b64 = payload.get("screen_frame_b64")
    voice_mode = bool(payload.get("voice_mode", True))
    return AgentCrewService.consult_crew_with_geppy(
        prompt=prompt,
        app_slug=app_slug,
        file_path=file_path,
        history=history,
        agent_ids=agent_ids,
        screen_frame_b64=screen_frame_b64,
        voice_mode=voice_mode,
        db=db,
    )

@app.post("/api/extension/antigravity/warm")
def extension_antigravity_warm_endpoint(payload: dict = {}, db: Session = Depends(get_db)):
    """Pre-warm persistent Antigravity agent sessions for an app on Port 8001."""
    slug = (payload.get("slug") or "").strip()
    app_obj = db.query(AppProfileModel).filter(AppProfileModel.slug == slug).first() if slug else None
    if not app_obj:
        raise HTTPException(status_code=404, detail=f"App '{slug}' not found")
    from gitbridge.services.antigravity_service import AntigravityService
    return AntigravityService.warm_app_session(app_obj)

@app.post("/api/extension/antigravity/reset")
def extension_antigravity_reset_endpoint(payload: dict = {}, db: Session = Depends(get_db)):
    """Reset persistent Antigravity agent sessions for an app on Port 8001."""
    slug = (payload.get("slug") or "").strip()
    app_obj = db.query(AppProfileModel).filter(AppProfileModel.slug == slug).first() if slug else None
    from gitbridge.services.antigravity_service import AntigravityService, AntigravityDaemonPool
    if app_obj and app_obj.local_path:
        return AntigravityDaemonPool.reset_workspace(app_obj.local_path)
    return {"reset": False, "slug": slug}

@app.post("/api/extension/antigravity/open-ide")
def extension_antigravity_open_ide_endpoint(payload: dict = {}, db: Session = Depends(get_db)):
    """Open the active app workspace (and optional active file) directly in Antigravity Desktop / IDE."""
    slug = (payload.get("slug") or "").strip()
    file_path = (payload.get("file_path") or "").strip() or None
    app_obj = db.query(AppProfileModel).filter(AppProfileModel.slug == slug).first() if slug else None
    if not app_obj:
        raise HTTPException(status_code=404, detail=f"App '{slug}' not found")
    from gitbridge.services.antigravity_service import AntigravityService
    return AntigravityService.launch_antigravity_ide(app_obj, file_path=file_path)

@app.get("/api/apps/{slug}/backlog")
def get_app_backlog_endpoint(slug: str, db: Session = Depends(get_db)):
    from gitbridge.services.extension_service import ExtensionService
    tasks = ExtensionService.get_backlog(slug, db)
    return {"slug": slug, "tasks": tasks}

@app.post("/api/apps/{slug}/backlog")
def save_app_backlog_endpoint(slug: str, payload: dict = {}, db: Session = Depends(get_db)):
    tasks = payload.get("tasks", [])
    from gitbridge.services.extension_service import ExtensionService
    saved = ExtensionService.save_backlog(slug, tasks, db)
    return {"slug": slug, "tasks": saved, "count": len(saved)}

@app.get("/api/apps/{slug}/chat")
def get_app_chat_endpoint(slug: str, db: Session = Depends(get_db)):
    from gitbridge.services.extension_service import ExtensionService
    history = ExtensionService.get_chat_history(slug, db)
    return {"slug": slug, "chat_history": history}

@app.post("/api/apps/{slug}/chat")
def save_app_chat_endpoint(slug: str, payload: dict = {}, db: Session = Depends(get_db)):
    history = payload.get("chat_history", [])
    from gitbridge.services.extension_service import ExtensionService
    saved = ExtensionService.save_chat_history(slug, history, db)
    return {"slug": slug, "chat_history": saved, "count": len(saved)}

@app.post("/api/extension/batch-apply-design")
def extension_batch_apply_design_endpoint(payload: dict = {}, db: Session = Depends(get_db)):
    """Apply a batch or grouped series of design/feature tasks to code in a single operation."""
    slug = payload.get("slug", "")
    file_path = payload.get("file_path", "")
    current_code = payload.get("current_code", "")
    tasks = payload.get("tasks", [])

    if not tasks:
        raise HTTPException(status_code=400, detail="Tasks list is required for batch application")

    from gitbridge.services.extension_service import ExtensionService
    result = ExtensionService.batch_apply_design(slug=slug, file_path=file_path, current_code=current_code, tasks=tasks, db=db)
    return result

@app.get("/api/apps/{slug}/images")
def get_app_images_endpoint(slug: str, db: Session = Depends(get_db)):
    """Discover and list all image assets in the app's local repository folder."""
    from gitbridge.services.app_image_service import AppImageService
    return AppImageService.get_app_images(slug, db)

@app.get("/api/apps/{slug}/images/file")
def serve_app_image_file_endpoint(slug: str, path: str = Query(...), db: Session = Depends(get_db)):
    """Serve a local image or asset file from within the app repository."""
    from gitbridge.services.app_image_service import AppImageService
    abs_path = AppImageService.get_image_file_path(slug, path, db)
    if not abs_path or not os.path.exists(abs_path):
        raise HTTPException(status_code=404, detail="Image file not found in app repository")
    return FileResponse(abs_path)

@app.post("/api/apps/{slug}/images/backup")
def backup_app_images_endpoint(slug: str, db: Session = Depends(get_db)):
    """Create a zip archive of all images in the app repository for safekeeping/backup."""
    from gitbridge.services.app_image_service import AppImageService
    result = AppImageService.backup_images_zip(slug, db)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("message", "Backup failed"))
    return result

@app.post("/api/apps/{slug}/images/drop-asset")
def drop_asset_to_app_endpoint(slug: str, payload: dict = {}, db: Session = Depends(get_db)):
    """Drop a synthesized Asset Lab image into the app's folder and optionally update app icon & code references."""
    asset_url = (payload.get("asset_url") or "").strip() or None
    if not asset_url and payload.get("filename"):
        asset_url = f"/api/asset-lab/file/{payload.get('filename')}"
    svg_content = payload.get("svg_content")
    base64_data = payload.get("base64_data")
    target_folder = payload.get("target_folder", "assets")
    target_filename = payload.get("target_filename")
    set_as_app_icon = bool(payload.get("set_as_app_icon", False))
    update_code_references = bool(payload.get("update_code_references", False))

    if not asset_url and not svg_content and not base64_data:
        raise HTTPException(status_code=400, detail="asset_url, svg_content, or base64_data is required")

    from gitbridge.services.app_image_service import AppImageService
    result = AppImageService.drop_asset_to_app(
        slug=slug,
        asset_url=asset_url,
        target_folder=target_folder,
        target_filename=target_filename,
        set_as_app_icon=set_as_app_icon,
        update_code_references=update_code_references,
        svg_content=svg_content,
        base64_data=base64_data,
        db=db
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("message", "Failed to drop asset"))
    return result

@app.post("/api/apps/{slug}/images/upload")
async def upload_image_to_app_endpoint(
    slug: str,
    file: UploadFile = File(...),
    target_folder: str = Form("assets"),
    set_as_app_icon: bool = Form(False),
    update_code_references: bool = Form(False),
    db: Session = Depends(get_db)
):
    """Directly upload an image from user's PC into the app with automatic HEIC conversion and HTML/manifest updating."""
    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    from gitbridge.services.app_image_service import AppImageService
    result = AppImageService.upload_image_to_app(
        slug=slug,
        file_bytes=contents,
        original_filename=file.filename,
        target_folder=target_folder or "assets",
        set_as_app_icon=bool(set_as_app_icon),
        update_code_references=bool(update_code_references),
        db=db
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("message", "Failed to upload image"))
    return result

# --- SOT (Source of Truth) & Contextiles API Endpoints ---
@app.get("/api/sot/modifiers")
def get_sot_modifiers_endpoint():
    """Return categorized modifier taxonomy, extensive variable dropdown catalog, extraction style keywords, and archetype definitions."""
    from gitbridge.services.sot_service import SOTService
    return {
        "modifiers": SOTService.get_modifiers_taxonomy(),
        "variable_dropdown_catalog": SOTService.get_variable_dropdown_catalog(),
        "archetypes": SOTService.get_archetypes(),
        "extraction_keywords": SOTService.get_extraction_keywords()
    }

@app.post("/api/sot/resolve-mentions")
def resolve_sot_mentions_endpoint(payload: dict = {}, db: Session = Depends(get_db)):
    """Resolve @handle and @<extraction_keyword><Handle> tags (e.g. @vsGeppy, @qGeppy, @matGeppy) in text."""
    text = payload.get("text", "") or payload.get("prompt", "") or payload.get("concept", "")
    from gitbridge.services.sot_service import SOTService
    return SOTService.resolve_mentions(text, db)

@app.post("/api/sot/ai-suggest-modifiers")
def ai_suggest_sot_modifiers_endpoint(payload: dict = {}):
    """Use Gemini to brainstorm an optimal modifier recipe based on reference text and archetype."""
    reference_text = payload.get("reference_text", "")
    archetype = payload.get("archetype", "character")
    app_name = payload.get("app_name")
    from gitbridge.services.sot_service import SOTService
    return SOTService.suggest_modifiers_ai(reference_text, archetype, app_name)

@app.post("/api/sot/ai-autofill")
def ai_autofill_contextile_endpoint(payload: dict = {}, db: Session = Depends(get_db)):
    """Intelligently autofill an entire Contextile from a creator's seed prompt or concept (supports @ and @vs tags)."""
    prompt = payload.get("prompt", "")
    archetype = payload.get("archetype")
    app_name = payload.get("app_name")
    from gitbridge.services.sot_service import SOTService
    return SOTService.ai_autofill_contextile(prompt, archetype, app_name, db=db)

@app.post("/api/sot/generate-contextile")
def generate_ai_contextile_endpoint(payload: dict = {}, db: Session = Depends(get_db)):
    """AI Generate a complete Contextile, Source of Truth, SOT Variant (e.g. '@geppy in a civil war costume'), or Contextile of Truth (Blank) with optional uploaded image and blank_spec."""
    concept = payload.get("concept", "") or payload.get("prompt", "")
    image_url = payload.get("image_url")
    entity_kind = payload.get("entity_kind")
    blank_spec = payload.get("blank_spec")
    parent_sot_handle = payload.get("parent_sot_handle")
    variant_label = payload.get("variant_label")
    if not concept and not image_url:
        raise HTTPException(status_code=400, detail="Concept/prompt or uploaded image is required")
    archetype = payload.get("archetype")
    save_immediately = payload.get("save_immediately", True)
    from gitbridge.services.sot_service import SOTService
    return SOTService.generate_ai_contextile(
        concept=concept or "Physical Blank Contextile of Truth",
        archetype=archetype,
        save_immediately=save_immediately,
        db=db,
        image_url=image_url,
        entity_kind=entity_kind,
        blank_spec=blank_spec,
        parent_sot_handle=parent_sot_handle,
        variant_label=variant_label
    )

@app.post("/api/sot/analyze-blank")
def analyze_blank_contextile_of_truth_endpoint(payload: dict = {}, db: Session = Depends(get_db)):
    """Analyze an uploaded physical blank photo, detect its size/shape/material and compatible fabrication output (Laser B&W burn, Stencil with edge connections, Vinyl, Sublimation), build a calibrated sizing template image, and optionally save as a Contextile of Truth."""
    from gitbridge.services.sot_service import SOTService
    image_url = payload.get("image_url")
    concept = payload.get("concept", "") or payload.get("prompt", "") or payload.get("title", "")
    width_in = payload.get("width_in") if payload.get("width_in") is not None else payload.get("width_value")
    height_in = payload.get("height_in") if payload.get("height_in") is not None else payload.get("height_value")
    safe_margin_in = payload.get("safe_margin_in")
    safe_margin_pct = payload.get("safe_margin_pct")
    shape = payload.get("shape")
    material = payload.get("material")
    fabrication_mode = payload.get("fabrication_mode")
    unit = payload.get("unit") or "in"
    color_mode = payload.get("color_mode")
    requires_edge_bridges = payload.get("requires_edge_bridges")
    paired_contextile_handles = payload.get("paired_contextile_handles")
    handle_override = payload.get("name") or payload.get("handle")
    save_immediately = bool(payload.get("save_immediately", False))
    return SOTService.analyze_blank_image_and_build_template(
        image_url=image_url,
        concept=concept,
        width_in=float(width_in) if width_in is not None and str(width_in).strip() != "" else None,
        height_in=float(height_in) if height_in is not None and str(height_in).strip() != "" else None,
        safe_margin_in=float(safe_margin_in) if safe_margin_in is not None and str(safe_margin_in).strip() != "" else None,
        shape=shape,
        material=material,
        fabrication_mode=fabrication_mode,
        save_immediately=save_immediately,
        db=db,
        handle_override=handle_override,
        unit=unit,
        color_mode=color_mode,
        safe_margin_pct=float(safe_margin_pct) if safe_margin_pct is not None and str(safe_margin_pct).strip() != "" else None,
        requires_edge_bridges=bool(requires_edge_bridges) if requires_edge_bridges is not None else None,
        paired_contextile_handles=paired_contextile_handles if isinstance(paired_contextile_handles, list) else None
    )

@app.post("/api/sot/compile")
def compile_sot_prompt_endpoint(payload: dict = {}):
    """Assemble reference text, archetype, categorized modifiers, and custom tags into compiled SOT prompt."""
    reference_text = payload.get("reference_text", "")
    modifiers = payload.get("modifiers", {})
    custom_tags = payload.get("custom_tags", [])
    archetype = payload.get("archetype", "character")
    primary_image_url = payload.get("primary_image_url")
    gallery_images = payload.get("gallery_images", [])
    from gitbridge.services.sot_service import SOTService
    assembled = SOTService.compile_prompt(
        reference_text, modifiers, custom_tags, archetype, primary_image_url, gallery_images
    )
    return {"assembled_prompt": assembled}

@app.post("/api/sot/upload-reference")
async def upload_sot_reference_endpoint(file: UploadFile = File(...)):
    """Upload single reference image file for Source of Truth Contextile with automatic HEIC/HEIF conversion."""
    from datetime import datetime
    from gitbridge.services.sot_service import SOTService
    from gitbridge.services.image_converter_service import ImageConverterService
    ref_dir = SOTService._get_references_dir()
    contents = await file.read()
    timestamp = int(datetime.utcnow().timestamp())
    orig_name = f"{timestamp}_{file.filename}"
    res = ImageConverterService.save_and_convert_upload(
        file_bytes=contents,
        original_filename=orig_name,
        target_dir=ref_dir,
        target_format="png"
    )
    url = f"/api/sot/reference-file/{res['filename']}"
    return {
        "filename": res["filename"],
        "file_path": res["file_path"],
        "url": url,
        "was_converted": res["was_converted"],
        "original_format": res["original_format"],
        "width": res.get("width"),
        "height": res.get("height")
    }

@app.post("/api/sot/upload-references")
async def upload_sot_references_endpoint(files: List[UploadFile] = File(...)):
    """Upload multiple reference image files with automatic HEIC/HEIF conversion."""
    from datetime import datetime
    from gitbridge.services.sot_service import SOTService
    from gitbridge.services.image_converter_service import ImageConverterService
    ref_dir = SOTService._get_references_dir()
    results = []
    for f in files:
        contents = await f.read()
        timestamp = int(datetime.utcnow().timestamp())
        orig_name = f"{timestamp}_{f.filename}"
        res = ImageConverterService.save_and_convert_upload(
            file_bytes=contents,
            original_filename=orig_name,
            target_dir=ref_dir,
            target_format="png"
        )
        url = f"/api/sot/reference-file/{res['filename']}"
        results.append({
            "filename": res["filename"],
            "file_path": res["file_path"],
            "url": url,
            "was_converted": res["was_converted"],
            "original_format": res["original_format"],
            "width": res.get("width"),
            "height": res.get("height")
        })
    return {"files": results}

@app.get("/api/sot/reference-file/{filename}")
def get_sot_reference_file_endpoint(filename: str):
    """Serve uploaded SOT reference image file."""
    from gitbridge.services.sot_service import SOTService
    ref_dir = SOTService._get_references_dir()
    file_path = os.path.join(ref_dir, filename)
    if not os.path.exists(file_path):
        # Fallback to root assets/sot_references if exists
        alt_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "sot_references", filename)
        if os.path.exists(alt_path):
            file_path = alt_path
        else:
            raise HTTPException(status_code=404, detail="Reference file not found")
    return FileResponse(file_path)

@app.get("/api/sot/contextiles")
def list_contextiles_endpoint(app_slug: Optional[str] = Query(None), db: Session = Depends(get_db)):
    """List all saved Source-of-Truth (SOT) Items, SOT Variants, Contextiles of Truth (Blanks), and Contextile Templates."""
    from gitbridge.services.sot_service import SOTService
    ctxs = SOTService.list_contextiles(db, app_slug=app_slug)
    return [
        {
            "id": c.id,
            "name": c.name,
            "title": c.title,
            "description": c.description,
            "archetype": c.archetype or "character",
            "entity_kind": SOTService.infer_entity_kind(c.archetype, c.modifiers, c.name),
            "is_sot_variant": bool((c.modifiers or {}).get("is_sot_variant") or (c.modifiers or {}).get("parent_sot_handle")) if isinstance(c.modifiers, dict) else False,
            "parent_sot_handle": (c.modifiers or {}).get("parent_sot_handle") if isinstance(c.modifiers, dict) else None,
            "parent_sot_title": (c.modifiers or {}).get("parent_sot_title") if isinstance(c.modifiers, dict) else None,
            "variant_label": (c.modifiers or {}).get("variant_label") if isinstance(c.modifiers, dict) else None,
            "blank_spec": (c.modifiers or {}).get("blank_spec") if isinstance(c.modifiers, dict) else None,
            "embedded_sot_handles": (c.modifiers or {}).get("embedded_sot_handles", []) if isinstance(c.modifiers, dict) else [],
            "option_toggles": (c.modifiers or {}).get("option_toggles", []) if isinstance(c.modifiers, dict) else [],
            "reference_type": c.reference_type,
            "reference_text": c.reference_text,
            "reference_image_url": c.reference_image_url,
            "primary_image_url": c.primary_image_url,
            "gallery_images": c.gallery_images,
            "modifiers": c.modifiers,
            "variables": c.variables or [],
            "tags": c.tags,
            "assembled_prompt": c.assembled_prompt,
            "app_slug": c.app_slug,
            "created_at": c.created_at,
            "updated_at": c.updated_at
        }
        for c in ctxs
    ]

@app.post("/api/sot/contextiles")
def save_contextile_endpoint(payload: dict = {}, db: Session = Depends(get_db)):
    """Create or update a Source of Truth (SOT) Item, SOT Variant, Contextile of Truth (Blank), or Contextile Template."""
    from gitbridge.services.sot_service import SOTService
    ctx = SOTService.create_contextile(payload, db)
    entity_kind = SOTService.infer_entity_kind(ctx.archetype, ctx.modifiers, ctx.name)
    is_var = bool((ctx.modifiers or {}).get("is_sot_variant") or (ctx.modifiers or {}).get("parent_sot_handle")) if isinstance(ctx.modifiers, dict) else False
    kind_label = "SOT Variant" if is_var else ("Contextile of Truth (Blank)" if entity_kind == "contextile_of_truth" else ("Source of Truth" if entity_kind == "sot" else "Contextile Template"))
    return {
        "id": ctx.id,
        "name": ctx.name,
        "title": ctx.title,
        "description": ctx.description,
        "archetype": ctx.archetype,
        "entity_kind": entity_kind,
        "is_sot_variant": is_var,
        "parent_sot_handle": (ctx.modifiers or {}).get("parent_sot_handle") if isinstance(ctx.modifiers, dict) else None,
        "parent_sot_title": (ctx.modifiers or {}).get("parent_sot_title") if isinstance(ctx.modifiers, dict) else None,
        "variant_label": (ctx.modifiers or {}).get("variant_label") if isinstance(ctx.modifiers, dict) else None,
        "blank_spec": (ctx.modifiers or {}).get("blank_spec") if isinstance(ctx.modifiers, dict) else None,
        "embedded_sot_handles": (ctx.modifiers or {}).get("embedded_sot_handles", []) if isinstance(ctx.modifiers, dict) else [],
        "option_toggles": (ctx.modifiers or {}).get("option_toggles", []) if isinstance(ctx.modifiers, dict) else [],
        "reference_type": ctx.reference_type,
        "reference_text": ctx.reference_text,
        "reference_image_url": ctx.reference_image_url,
        "primary_image_url": ctx.primary_image_url,
        "gallery_images": ctx.gallery_images,
        "modifiers": ctx.modifiers,
        "variables": ctx.variables or [],
        "tags": ctx.tags,
        "assembled_prompt": ctx.assembled_prompt,
        "app_slug": ctx.app_slug,
        "message": f"{kind_label} '@{ctx.name}' saved successfully!"
    }

@app.get("/api/sot/contextiles/{name}")
def get_contextile_endpoint(name: str, db: Session = Depends(get_db)):
    """Get single SOT Item, SOT Variant, Contextile of Truth, or Contextile Template by handle name."""
    from gitbridge.services.sot_service import SOTService
    ctx = SOTService.get_contextile(name, db)
    if not ctx:
        raise HTTPException(status_code=404, detail=f"Item '@{name}' not found")
    return {
        "id": ctx.id,
        "name": ctx.name,
        "title": ctx.title,
        "description": ctx.description,
        "archetype": ctx.archetype or "character",
        "entity_kind": SOTService.infer_entity_kind(ctx.archetype, ctx.modifiers, ctx.name),
        "is_sot_variant": bool((ctx.modifiers or {}).get("is_sot_variant") or (ctx.modifiers or {}).get("parent_sot_handle")) if isinstance(ctx.modifiers, dict) else False,
        "parent_sot_handle": (ctx.modifiers or {}).get("parent_sot_handle") if isinstance(ctx.modifiers, dict) else None,
        "parent_sot_title": (ctx.modifiers or {}).get("parent_sot_title") if isinstance(ctx.modifiers, dict) else None,
        "variant_label": (ctx.modifiers or {}).get("variant_label") if isinstance(ctx.modifiers, dict) else None,
        "blank_spec": (ctx.modifiers or {}).get("blank_spec") if isinstance(ctx.modifiers, dict) else None,
        "embedded_sot_handles": (ctx.modifiers or {}).get("embedded_sot_handles", []) if isinstance(c.modifiers if 'c' in locals() else ctx.modifiers, dict) else [],
        "option_toggles": (ctx.modifiers or {}).get("option_toggles", []) if isinstance(ctx.modifiers, dict) else [],
        "reference_type": ctx.reference_type,
        "reference_text": ctx.reference_text,
        "reference_image_url": ctx.reference_image_url,
        "primary_image_url": ctx.primary_image_url,
        "gallery_images": ctx.gallery_images,
        "modifiers": ctx.modifiers,
        "variables": ctx.variables or [],
        "tags": ctx.tags,
        "assembled_prompt": ctx.assembled_prompt,
        "app_slug": ctx.app_slug
    }

@app.delete("/api/sot/contextiles/{name}")
def delete_contextile_endpoint(name: str, db: Session = Depends(get_db)):
    """Delete a Contextile by handle name."""
    from gitbridge.services.sot_service import SOTService
    success = SOTService.delete_contextile(name, db)
    if not success:
        raise HTTPException(status_code=404, detail=f"Contextile '@{name}' not found")
    return {"success": True, "message": f"Contextile '@{name}' deleted"}

@app.post("/api/sot/suggest-variables")
def suggest_contextile_variables_endpoint(payload: dict = {}):
    """Suggest dynamic template variables and slots for a given archetype, concept, or reference text."""
    from gitbridge.services.sot_service import SOTService
    archetype = payload.get("archetype", "character")
    concept = payload.get("concept", "")
    reference_text = payload.get("reference_text", "")
    vars_list = SOTService.suggest_variables_for_concept(archetype=archetype, concept=concept, reference_text=reference_text)
    return {"variables": vars_list}

# --- Asset Laboratory Endpoints ---

@app.get("/api/asset-lab/history")
def get_asset_lab_history_endpoint():
    """Retrieve history of synthesized assets."""
    from gitbridge.services.asset_lab_service import AssetLabService
    return AssetLabService.get_history()

@app.delete("/api/asset-lab/history/{asset_id}")
def delete_asset_lab_history_endpoint(asset_id: str):
    """Delete a synthesized asset from the lab history."""
    from gitbridge.services.asset_lab_service import AssetLabService
    success = AssetLabService.delete_history_item(asset_id)
    if not success:
        raise HTTPException(status_code=404, detail="Asset record not found")
    return {"success": True, "message": f"Asset {asset_id} deleted"}

@app.get("/api/asset-lab/file/{filename}")
def serve_asset_lab_file_endpoint(filename: str):
    """Serve synthesized visual asset PNG file."""
    from gitbridge.services.asset_lab_service import AssetLabService
    file_path = os.path.join(AssetLabService._get_lab_dir(), filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Synthesized asset file not found")
    return FileResponse(file_path)

@app.post("/api/asset-lab/brainstorm-concepts")
def brainstorm_asset_lab_concepts_endpoint(payload: dict = {}, db: Session = Depends(get_db)):
    """Brainstorm 3 diverse asset concepts with visual blueprints, SVG previews, and color palettes."""
    purpose = payload.get("purpose", "")
    style_directive = payload.get("style_directive", "")
    app_slug = payload.get("app_slug")
    brand_contextile = payload.get("brand_contextile")
    style_contextile = payload.get("style_contextile")
    output_contextile = payload.get("output_contextile")
    reference_images = payload.get("reference_images", [])

    from gitbridge.services.asset_lab_service import AssetLabService
    concepts = AssetLabService.brainstorm_concepts(
        purpose=purpose,
        style_directive=style_directive,
        app_slug=app_slug,
        brand_contextile=brand_contextile,
        style_contextile=style_contextile,
        output_contextile=output_contextile,
        reference_images=reference_images,
        db=db
    )
    return {"concepts": concepts, "count": len(concepts)}

@app.post("/api/asset-lab/auto-fill-concepts")
def auto_fill_asset_lab_concepts_endpoint(payload: dict = {}):
    """Port of geppy-s-asset-lab's generateIconDefinitions: AI auto-fills N distinct concepts for a Multi-Concept Grid."""
    count = int(payload.get("count", 4))
    theme_prompt = payload.get("theme_prompt", "") or payload.get("prompt", "")
    asset_type = payload.get("asset_type", "app_icon")
    ingredients_summary = payload.get("ingredients_summary", [])
    app_slug = payload.get("app_slug")

    from gitbridge.services.asset_lab_service import AssetLabService
    concepts = AssetLabService.auto_fill_concepts(
        count=count,
        theme_prompt=theme_prompt,
        asset_type=asset_type,
        ingredients_summary=ingredients_summary,
        app_slug=app_slug
    )
    return {"concepts": concepts, "count": len(concepts)}

@app.post("/api/asset-lab/synthesize")
def synthesize_asset_recipe_endpoint(payload: dict = {}):
    """Mix multiple SOT contextiles, actual Source-of-Truth pictures, and directives into a Master Synthesis Blueprint."""
    ingredients = payload.get("ingredients", [])
    custom_prompt = payload.get("custom_prompt", "")
    target_format = payload.get("target_format", "app_icon")
    fidelity_mode = payload.get("fidelity_mode", "balanced")
    overrides = payload.get("overrides", {})
    reference_images = payload.get("reference_images", [])
    app_context = payload.get("app_context")
    variables = payload.get("variables", {})
    scene_elements = payload.get("scene_elements", [])
    grid_mode = payload.get("grid_mode", "single")
    grid_rows = int(payload.get("grid_rows", 1) or 1)
    grid_cols = int(payload.get("grid_cols", 1) or 1)
    concepts_list = payload.get("concepts_list", [])

    from gitbridge.services.asset_lab_service import AssetLabService
    recipe = AssetLabService.synthesize_blend(
        ingredients=ingredients,
        custom_prompt=custom_prompt,
        target_format=target_format,
        fidelity_mode=fidelity_mode,
        overrides=overrides,
        reference_images=reference_images,
        app_context=app_context,
        variables=variables,
        scene_elements=scene_elements,
        grid_mode=grid_mode,
        grid_rows=grid_rows,
        grid_cols=grid_cols,
        concepts_list=concepts_list
    )
    return recipe

@app.post("/api/asset-lab/generate")
def generate_asset_lab_visual_endpoint(payload: dict = {}):
    """Generate the actual fine-tuned visual asset PNG (plus Reference Sheet & sliced grid cells) and persist in the lab repository."""
    title = payload.get("title", "Fine-Tuned Asset")
    master_prompt = payload.get("master_prompt", "")
    target_format = payload.get("target_format", "app_icon")
    aspect_ratio = payload.get("aspect_ratio", "1:1")
    color_palette = payload.get("color_palette", [])
    composition_blueprint = payload.get("composition_blueprint", "")
    ingredients_summary = payload.get("ingredients_summary", [])
    reference_images = payload.get("reference_images", [])
    app_slug = payload.get("app_slug")
    variables = payload.get("variables", {})
    scene_elements = payload.get("scene_elements", [])
    grid_mode = payload.get("grid_mode", "single")
    grid_rows = int(payload.get("grid_rows", 1) or 1)
    grid_cols = int(payload.get("grid_cols", 1) or 1)
    concepts_list = payload.get("concepts_list", [])
    preserve_source_picture = bool(payload.get("preserve_source_picture", False))
    cutout_bg = payload.get("cutout_bg", None)

    from gitbridge.services.asset_lab_service import AssetLabService
    record = AssetLabService.generate_visual_asset(
        title=title,
        master_prompt=master_prompt,
        target_format=target_format,
        aspect_ratio=aspect_ratio,
        color_palette=color_palette,
        composition_blueprint=composition_blueprint,
        ingredients_summary=ingredients_summary,
        reference_images=reference_images,
        app_slug=app_slug,
        variables=variables,
        scene_elements=scene_elements,
        grid_mode=grid_mode,
        grid_rows=grid_rows,
        grid_cols=grid_cols,
        concepts_list=concepts_list,
        preserve_source_picture=preserve_source_picture,
        cutout_bg=cutout_bg
    )
    return record

@app.post("/api/asset-lab/apply-as-icon")
def apply_lab_asset_as_icon_endpoint(payload: dict = {}, db: Session = Depends(get_db)):
    """Apply a synthesized visual asset as the official app icon in GitBridge."""
    app_slug = payload.get("app_slug")
    file_url = payload.get("file_url")
    if not app_slug or not file_url:
        raise HTTPException(status_code=400, detail="app_slug and file_url are required")

    app_obj = db.query(AppProfileModel).filter(AppProfileModel.slug == app_slug).first()
    if not app_obj:
        raise HTTPException(status_code=404, detail=f"App '{app_slug}' not found")

    app_obj.icon_url = file_url
    db.commit()
    db.refresh(app_obj)
    return {"success": True, "message": f"Asset applied as official icon for {app_obj.name}", "icon_url": file_url}

@app.post("/api/asset-lab/export-to-sot")
def export_lab_asset_to_sot_endpoint(payload: dict = {}, db: Session = Depends(get_db)):
    """Convert a synthesized lab asset into a permanent SOT Contextile."""
    name = payload.get("name")
    title = payload.get("title")
    master_prompt = payload.get("master_prompt", "")
    file_url = payload.get("file_url")
    app_slug = payload.get("app_slug")
    tags = payload.get("tags", ["asset-lab", "hybrid-fusion"])

    if not name:
        raise HTTPException(status_code=400, detail="Contextile name handle is required")

    from gitbridge.services.sot_service import SOTService
    data = {
        "name": name,
        "title": title or name,
        "archetype": "general",
        "reference_type": "hybrid" if file_url else "text",
        "reference_text": master_prompt[:300],
        "reference_image_url": file_url,
        "primary_image_url": file_url,
        "gallery_images": [file_url] if file_url else [],
        "modifiers": {"medium": ["Fine-Tuned Asset Lab"]},
        "tags": tags,
        "assembled_prompt": master_prompt,
        "app_slug": app_slug
    }
    ctx = SOTService.create_contextile(data, db)
    return {"success": True, "contextile": {
        "id": ctx.id,
        "name": ctx.name,
        "title": ctx.title,
        "archetype": ctx.archetype,
        "assembled_prompt": ctx.assembled_prompt,
        "primary_image_url": ctx.primary_image_url
    }}

@app.get("/api/asset-lab/exports/{filename}")
def serve_asset_lab_export_endpoint(filename: str, download: bool = False):
    """Serve exported transparent PNG or print-ready PDF file."""
    from gitbridge.services.output_service import OutputService
    file_path = os.path.join(OutputService._get_exports_dir(), filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Exported asset file not found")
    media_type = "application/pdf" if filename.lower().endswith(".pdf") else "image/png"
    headers = {}
    if download:
        headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return FileResponse(file_path, media_type=media_type, headers=headers)

@app.post("/api/asset-lab/output/process")
def process_asset_output_endpoint(payload: dict = {}, db: Session = Depends(get_db)):
    """Process an asset through the Output Contextile finishing pipeline (BG removal, die-cut rim, 300 DPI PDF)."""
    from gitbridge.services.output_service import OutputService
    from gitbridge.services.asset_lab_service import AssetLabService
    from gitbridge.services.sot_service import SOTService
    from gitbridge.db.models import ContextileModel

    source_image = payload.get("source_image") or ""
    output_contextile_name = payload.get("output_contextile")
    spec = payload.get("spec", {})

    # If an output contextile handle was passed, load its default modifiers
    merged_spec = {}
    if output_contextile_name:
        clean_handle = output_contextile_name.lstrip("@").strip()
        ctx = db.query(ContextileModel).filter(ContextileModel.name == clean_handle).first()
        if ctx and ctx.modifiers:
            merged_spec.update(ctx.modifiers)

    # Merge explicit overrides from request payload
    merged_spec.update(spec)

    # Resolve source image filesystem path
    source_path = None
    if source_image.startswith("/api/asset-lab/file/"):
        fname = source_image.replace("/api/asset-lab/file/", "")
        source_path = os.path.join(AssetLabService._get_lab_dir(), fname)
    elif source_image.startswith("/api/sot/reference-file/"):
        fname = source_image.replace("/api/sot/reference-file/", "")
        source_path = os.path.join(SOTService._get_references_dir(), fname)
    elif source_image.startswith("/api/asset-lab/exports/"):
        fname = source_image.replace("/api/asset-lab/exports/", "")
        source_path = os.path.join(OutputService._get_exports_dir(), fname)
    elif os.path.isabs(source_image) and os.path.exists(source_image):
        source_path = source_image
    else:
        # Fallback search by filename
        candidate_lab = os.path.join(AssetLabService._get_lab_dir(), os.path.basename(source_image))
        candidate_sot = os.path.join(SOTService._get_references_dir(), os.path.basename(source_image))
        if os.path.exists(candidate_lab):
            source_path = candidate_lab
        elif os.path.exists(candidate_sot):
            source_path = candidate_sot

    if not source_path or not os.path.exists(source_path):
        raise HTTPException(status_code=400, detail=f"Source image could not be resolved: {source_image}")

    try:
        result = OutputService.process_pipeline(source_path, merged_spec)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Output processing failed: {str(e)}")

@app.post("/api/asset-lab/output/save-contextile")
def save_output_contextile_endpoint(payload: dict = {}, db: Session = Depends(get_db)):
    """Save the current output designer configuration as a reusable Output Contextile."""
    from gitbridge.services.sot_service import SOTService, generate_contextile_thumbnail
    name = payload.get("name") or f"output-spec-{int(time.time())}"
    clean_name = re.sub(r"[^a-z0-9\-]", "", name.lower().replace(" ", "-"))
    title = payload.get("title") or clean_name.replace("-", " ").title()
    description = payload.get("description") or f"Custom output finishing spec for {title}"
    modifiers = payload.get("modifiers") or {}

    thumb_url = generate_contextile_thumbnail(
        handle=clean_name,
        title=title,
        concept=description,
        archetype="output",
        color_palette=["#FFFFFF", "#06B6D4", "#EC4899"]
    )

    created = SOTService.create_contextile({
        "name": clean_name,
        "title": title,
        "description": description,
        "archetype": "output",
        "reference_type": "hybrid" if thumb_url else "text",
        "reference_text": payload.get("reference_text") or description,
        "primary_image_url": thumb_url,
        "reference_image_url": thumb_url,
        "modifiers": modifiers,
        "tags": ["output", "custom-spec", modifiers.get("print_size", "custom")],
        "assembled_prompt": SOTService.compile_prompt(
            reference_text=description,
            modifiers=modifiers,
            archetype="output"
        )
    }, db)

    return {
        "success": True,
        "message": f"Output Contextile '@{created.name}' saved to SOT Fleet!",
        "contextile": {
            "id": created.id,
            "name": created.name,
            "title": created.title,
            "archetype": created.archetype
        }
    }

# --- Media & HEIC/HEIF Image Conversion Endpoints ---

@app.post("/api/media/convert-heic")
async def convert_heic_media_endpoint(
    files: List[UploadFile] = File(...),
    target_format: str = Form("png"),
    quality: int = Form(95)
):
    """
    Convert uploaded HEIC/HEIF files (or other formats) to high-fidelity PNG, JPEG, or WebP.
    Returns conversion metadata and direct served URLs.
    """
    from gitbridge.services.image_converter_service import ImageConverterService
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "converted_media")
    os.makedirs(out_dir, exist_ok=True)

    results = []
    for f in files:
        contents = await f.read()
        res = ImageConverterService.save_and_convert_upload(
            file_bytes=contents,
            original_filename=f.filename,
            target_dir=out_dir,
            target_format=target_format,
            force_convert_all=True
        )
        file_url = f"/api/media/converted/{res['filename']}"
        results.append({
            "original_filename": res["original_filename"],
            "filename": res["filename"],
            "url": file_url,
            "was_converted": res["was_converted"],
            "format": res["format"],
            "mime_type": res["mime_type"],
            "width": res.get("width"),
            "height": res.get("height"),
            "original_size": res["original_size"],
            "converted_size": res["converted_size"]
        })
    return {"converted_count": len(results), "files": results}

@app.get("/api/media/converted/{filename}")
def serve_converted_media_file_endpoint(filename: str, download: bool = False):
    """Serve converted PNG/JPEG/WebP media file."""
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "converted_media")
    file_path = os.path.join(out_dir, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Converted media file not found")
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'} if download else {}
    media_type = "image/png"
    if filename.lower().endswith(".jpg") or filename.lower().endswith(".jpeg"):
        media_type = "image/jpeg"
    elif filename.lower().endswith(".webp"):
        media_type = "image/webp"
    return FileResponse(file_path, media_type=media_type, headers=headers)

# --- Asset Series Generator Endpoints ---

@app.get("/api/asset-lab/series/presets")
def get_series_presets_endpoint():
    """Return standard variation presets (emotes, actions, app suites, rarities, seasons)."""
    from gitbridge.services.series_service import SeriesService
    return SeriesService.get_presets()

@app.post("/api/asset-lab/series/expand-ai")
def expand_series_variations_endpoint(payload: dict = {}):
    """Use AI or intelligent procedural rules to expand a theme into multiple cohesive variations."""
    from gitbridge.services.series_service import SeriesService
    theme_idea = payload.get("theme_idea", "Variations")
    anchor_title = payload.get("anchor_title", "Captain Geppy")
    anchor_style = payload.get("anchor_style", "3D Icon")
    count = payload.get("count", 5)

    variations = SeriesService.expand_variations_ai(
        theme_idea=theme_idea,
        anchor_title=anchor_title,
        anchor_style=anchor_style,
        count=count
    )
    return {"success": True, "variations": variations}

@app.post("/api/asset-lab/series/generate")
def generate_series_endpoint(payload: dict = {}):
    """Batch synthesize a multi-image series with contact sheet and ZIP package."""
    from gitbridge.services.series_service import SeriesService
    anchor_data = payload.get("anchor_data", {})
    variations = payload.get("variations", [])
    series_title = payload.get("series_title")
    output_contextile = payload.get("output_contextile")
    consistency_level = payload.get("consistency_level", "high")
    app_slug = payload.get("app_slug")

    if not variations:
        raise HTTPException(status_code=400, detail="At least 1 variation directive is required")

    result = SeriesService.generate_series(
        anchor_data=anchor_data,
        variations=variations,
        series_title=series_title,
        output_contextile=output_contextile,
        consistency_level=consistency_level,
        app_slug=app_slug
    )
    return result

@app.get("/api/asset-lab/series/history")
def get_series_history_endpoint():
    """Retrieve history of all synthesized series collections."""
    from gitbridge.services.series_service import SeriesService
    return SeriesService.get_history()

@app.get("/api/asset-lab/series/{series_id}")
def get_series_detail_endpoint(series_id: str):
    """Get metadata and items of a specific series."""
    from gitbridge.services.series_service import SeriesService
    series = SeriesService.get_series(series_id)
    if not series:
        raise HTTPException(status_code=404, detail=f"Series '{series_id}' not found")
    return series

@app.delete("/api/asset-lab/series/{series_id}")
def delete_series_endpoint(series_id: str):
    """Delete a series collection and its files."""
    from gitbridge.services.series_service import SeriesService
    success = SeriesService.delete_series(series_id)
    if not success:
        raise HTTPException(status_code=404, detail="Series not found")
    return {"success": True, "message": f"Series {series_id} deleted"}

@app.get("/api/asset-lab/series/{series_id}/file/{filename}")
def serve_series_file_endpoint(series_id: str, filename: str):
    """Serve a file (PNG, contact sheet, etc.) from a series folder."""
    from gitbridge.services.series_service import SeriesService
    file_path = os.path.join(SeriesService._get_series_dir(), series_id, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Series file not found")
    media_type = "application/pdf" if filename.lower().endswith(".pdf") else "image/png"
    return FileResponse(file_path, media_type=media_type)

@app.get("/api/asset-lab/series/{series_id}/download-zip")
def download_series_zip_endpoint(series_id: str):
    """Download the complete zipped collection of all series variations and contact sheet."""
    from gitbridge.services.series_service import SeriesService
    series_dir = os.path.join(SeriesService._get_series_dir(), series_id)
    zip_path = os.path.join(series_dir, f"{series_id}_collection.zip")
    if not os.path.exists(zip_path):
        SeriesService._create_zip_package(series_dir, zip_path)
    if not os.path.exists(zip_path):
        raise HTTPException(status_code=404, detail="Series ZIP package could not be found")
    return FileResponse(
        zip_path,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{series_id}_collection.zip"'}
    )

@app.get("/api/apps/{slug}/git-status")
def get_app_git_status_endpoint(slug: str, db: Session = Depends(get_db)):
    """Retrieve local git repository status, changed files, branch, and remote sync state."""
    app_obj = db.query(AppProfileModel).filter(AppProfileModel.slug == slug).first()
    if not app_obj:
        raise HTTPException(status_code=404, detail=f"App with slug '{slug}' not found")

    from gitbridge.services.workspace_service import WorkspaceService
    status = WorkspaceService.get_git_status(app_obj)
    status["slug"] = app_obj.slug
    status["name"] = app_obj.name
    status["github_url"] = app_obj.github_url
    return status

@app.post("/api/apps/{slug}/generate-commit-message")
def generate_commit_message_endpoint(slug: str, payload: dict = {}, db: Session = Depends(get_db)):
    """Generate a conventional git commit message based on changed files and session edits using Gemini."""
    app_obj = db.query(AppProfileModel).filter(AppProfileModel.slug == slug).first()
    if not app_obj:
        raise HTTPException(status_code=404, detail=f"App with slug '{slug}' not found")

    from gitbridge.services.workspace_service import WorkspaceService
    files = payload.get("files", [])
    recent_actions = payload.get("recent_actions", [])
    if not files:
        st = WorkspaceService.get_git_status(app_obj)
        files = [f["path"] for f in st.get("files", [])]

    commit_msg = WorkspaceService.generate_commit_message(app_obj, files=files, recent_actions=recent_actions)
    return {"commit_message": commit_msg}

@app.post("/api/apps/{slug}/push-github")
def push_app_github_endpoint(slug: str, payload: dict = {}, db: Session = Depends(get_db)):
    app_obj = db.query(AppProfileModel).filter(AppProfileModel.slug == slug).first()
    if not app_obj:
        raise HTTPException(status_code=404, detail=f"App with slug '{slug}' not found")

    from gitbridge.services.workspace_service import WorkspaceService
    msg = payload.get("commit_message")
    make_private = payload.get("make_private", False)
    push_remote = payload.get("push_remote", True)
    update_changelog_file = payload.get("update_changelog_file", True)
    changelog_entries = payload.get("changelog_entries", [])
    result = WorkspaceService.push_app_to_github(
        app_obj,
        commit_message=msg,
        make_private=make_private,
        push_remote=push_remote,
        update_changelog_file=update_changelog_file,
        changelog_entries=changelog_entries,
        db=db
    )
    return result

@app.post("/api/workspace/push-all-github")
def push_all_workspace_endpoint(db: Session = Depends(get_db)):
    from gitbridge.services.workspace_service import WorkspaceService
    apps = db.query(AppProfileModel).all()
    pushed = 0
    failed = 0
    results = []

    for app_obj in apps:
        if app_obj.local_path and os.path.exists(app_obj.local_path):
            res = WorkspaceService.push_app_to_github(app_obj, db=db)
            if res.get("success"):
                pushed += 1
            else:
                failed += 1
            results.append({"slug": app_obj.slug, "res": res})

    return {"pushed": pushed, "failed": failed, "details": results}

@app.get("/api/assets")
def list_all_media_assets(db: Session = Depends(get_db)):
    from gitbridge.services.workspace_service import WorkspaceService
    apps = db.query(AppProfileModel).all()
    for app_obj in apps:
        if app_obj.local_path and os.path.exists(app_obj.local_path):
            WorkspaceService.sync_app_local_assets(app_obj, db)

    assets = db.query(MediaAssetModel).all()
    res = []
    for a in assets:
        app_obj = db.query(AppProfileModel).filter(AppProfileModel.slug == a.app_id).first()
        app_name = app_obj.name if app_obj else a.app_id
        file_url = a.url or f"/api/apps/{a.app_id}/assets/file/{os.path.basename(a.file_path)}"
        res.append({
            "id": a.id,
            "app_id": a.app_id,
            "app_slug": a.app_id,
            "app_name": app_name,
            "title": a.title,
            "asset_type": a.asset_type.value if hasattr(a.asset_type, "value") else str(a.asset_type),
            "file_path": a.file_path,
            "url": file_url,
            "generation_prompt": a.generation_prompt,
            "tags": a.tags or [],
            "created_at": a.created_at
        })
    return res

@app.get("/api/apps/{slug}/assets/file/{filename}")
def serve_app_asset_file(slug: str, filename: str, db: Session = Depends(get_db)):
    app_obj = db.query(AppProfileModel).filter(AppProfileModel.slug == slug).first()
    if not app_obj:
        raise HTTPException(status_code=404, detail=f"App with slug '{slug}' not found")
    
    from gitbridge.services.workspace_service import WorkspaceService
    assets_dir = WorkspaceService.ensure_app_assets_dir(app_obj)
    
    file_path = None
    if assets_dir:
        cand = os.path.join(assets_dir, filename)
        if os.path.exists(cand) and os.path.isfile(cand):
            file_path = cand

    if not file_path and app_obj.local_path and os.path.exists(app_obj.local_path):
        cand = os.path.join(app_obj.local_path, filename)
        if os.path.exists(cand) and os.path.isfile(cand):
            file_path = cand

    if not file_path:
        raise HTTPException(status_code=404, detail=f"Asset file '{filename}' not found for app '{slug}'")

    if app_obj.local_path:
        abs_file = os.path.abspath(file_path)
        abs_app = os.path.abspath(app_obj.local_path)
        if not abs_file.startswith(abs_app):
            raise HTTPException(status_code=403, detail="Access denied")

    return FileResponse(file_path)

@app.post("/api/apps/{slug}/assets/upload")
async def upload_app_asset(
    slug: str,
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    asset_type: Optional[str] = Form("screenshot"),
    tags: Optional[str] = Form(""),
    db: Session = Depends(get_db)
):
    app_obj = db.query(AppProfileModel).filter(AppProfileModel.slug == slug).first()
    if not app_obj:
        raise HTTPException(status_code=404, detail=f"App with slug '{slug}' not found")

    from gitbridge.services.workspace_service import WorkspaceService
    from gitbridge.services.image_converter_service import ImageConverterService
    assets_dir = WorkspaceService.ensure_app_assets_dir(app_obj)
    if not assets_dir:
        raise HTTPException(status_code=400, detail=f"Local workspace directory for '{slug}' does not exist on disk.")

    contents = await file.read()
    conv_res = ImageConverterService.save_and_convert_upload(
        file_bytes=contents,
        original_filename=file.filename,
        target_dir=assets_dir,
        target_format="png"
    )
    clean_filename = conv_res["filename"]
    target_path = conv_res["file_path"]

    rel_file = os.path.relpath(target_path, app_obj.local_path).replace("\\", "/")
    asset_title = title if title else clean_filename.rsplit(".", 1)[0].replace("-", " ").replace("_", " ").title()
    file_url = f"/api/apps/{slug}/assets/file/{clean_filename}"

    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []

    try:
        atype = AssetType(asset_type)
    except Exception:
        atype = AssetType.SCREENSHOT

    existing = db.query(MediaAssetModel).filter(
        MediaAssetModel.app_id == slug,
        MediaAssetModel.file_path == rel_file
    ).first()

    if existing:
        existing.title = asset_title
        existing.asset_type = atype
        existing.url = file_url
        if tag_list:
            existing.tags = tag_list
        db.commit()
        db.refresh(existing)
        asset_obj = existing
    else:
        asset_obj = MediaAssetModel(
            app_id=slug,
            title=asset_title,
            asset_type=atype,
            file_path=rel_file,
            url=file_url
        )
        asset_obj.tags = tag_list
        db.add(asset_obj)
        db.commit()
        db.refresh(asset_obj)

    return {
        "id": asset_obj.id,
        "app_id": asset_obj.app_id,
        "title": asset_obj.title,
        "asset_type": asset_obj.asset_type.value if hasattr(asset_obj.asset_type, "value") else str(asset_obj.asset_type),
        "file_path": asset_obj.file_path,
        "url": asset_obj.url,
        "tags": asset_obj.tags,
        "created_at": asset_obj.created_at
    }

@app.post("/api/apps/{slug}/assets", response_model=MediaAssetResponse)
def add_media_asset(slug: str, asset_in: MediaAssetBase, db: Session = Depends(get_db)):
    app_obj = db.query(AppProfileModel).filter(AppProfileModel.slug == slug).first()
    if not app_obj:
        raise HTTPException(status_code=404, detail=f"App with slug '{slug}' not found")

    asset_obj = MediaAssetModel(
        app_id=slug,
        title=asset_in.title,
        asset_type=asset_in.asset_type,
        file_path=asset_in.file_path,
        url=asset_in.url,
        generation_prompt=asset_in.generation_prompt
    )
    asset_obj.tags = asset_in.tags

    db.add(asset_obj)
    db.commit()
    db.refresh(asset_obj)
    return asset_obj

@app.post("/api/apps/{slug}/manuals", response_model=DocManualResponse)
def add_doc_manual(slug: str, doc_in: DocManualBase, db: Session = Depends(get_db)):
    app_obj = db.query(AppProfileModel).filter(AppProfileModel.slug == slug).first()
    if not app_obj:
        raise HTTPException(status_code=404, detail=f"App with slug '{slug}' not found")

    manual_obj = DocManualModel(
        app_id=slug,
        title=doc_in.title,
        summary=doc_in.summary,
        content_markdown=doc_in.content_markdown,
        file_path=doc_in.file_path
    )

    db.add(manual_obj)
    db.commit()
    db.refresh(manual_obj)
    return manual_obj

@app.post("/api/sync/github")
def sync_github_api(username: Optional[str] = None, repo: Optional[str] = None, auto_download: bool = Query(False), db: Session = Depends(get_db)):
    gh_service = GitHubService()
    if repo:
        repo_data = gh_service.fetch_repo_details(repo)
        repos = [repo_data] if repo_data else []
    else:
        repos = gh_service.fetch_user_repos(username)
    added = 0
    updated = 0
    cloned = 0

    for r in repos:
        parsed = gh_service.parse_repo_to_profile_dict(r)
        slug = parsed["slug"]
        existing = db.query(AppProfileModel).filter(AppProfileModel.slug == slug).first()

        if not existing:
            app_obj = AppProfileModel(
                slug=slug,
                name=parsed["name"],
                description=parsed["description"],
                status=AppStatus(parsed["status"]),
                github_url=parsed["github_url"],
                github_repo_name=parsed["github_repo_name"],
                version=parsed["version"]
            )
            app_obj.tech_stack = parsed["tech_stack"]
            app_obj.tags = parsed["tags"]
            db.add(app_obj)
            db.commit()
            db.refresh(app_obj)
            added += 1
        else:
            existing.github_url = parsed["github_url"]
            existing.github_repo_name = parsed["github_repo_name"]
            if parsed["description"]:
                existing.description = parsed["description"]
            existing.tech_stack = list(dict.fromkeys(existing.tech_stack + parsed["tech_stack"]))
            db.commit()
            db.refresh(existing)
            app_obj = existing
            updated += 1

        if auto_download and app_obj.github_url:
            if not app_obj.local_path or not os.path.exists(app_obj.local_path):
                from gitbridge.services.workspace_service import WorkspaceService
                res = WorkspaceService.download_and_link_app(app_obj, db)
                if res.get("success"):
                    cloned += 1

    return {"message": "GitHub Sync Completed", "added": added, "updated": updated, "cloned": cloned}

def _serialize_apps_for_sheets(db: Session) -> list:
    apps = db.query(AppProfileModel).order_by(AppProfileModel.name.asc()).all()
    return [
        {
            "slug": a.slug,
            "name": a.name,
            "description": a.description,
            "status": a.status.value if hasattr(a.status, "value") else str(a.status),
            "priority_tier": getattr(a, "priority_tier", "Tier 2") or "Tier 2",
            "github_url": a.github_url,
            "live_url": getattr(a, "live_url", "") or "",
            "ai_studio_link": a.ai_studio_link,
            "tech_stack": a.tech_stack or [],
            "tags": a.tags or [],
            "backlog": getattr(a, "backlog", []) or [],
            "version": a.version,
            "updated_at": a.updated_at,
        }
        for a in apps
    ]


@app.get("/api/sync/sheets/status")
def get_sheets_sync_status(db: Session = Depends(get_db)):
    app_dicts = _serialize_apps_for_sheets(db)
    sheets_service = GoogleSheetsService()
    state = sheets_service.get_state()
    rows = sheets_service.build_rows(app_dicts)
    tsv_data = sheets_service.build_tsv(app_dicts)
    return {
        **state,
        "has_service_account": os.path.exists(sheets_service.credentials_path),
        "has_webhook": bool(sheets_service.webhook_url),
        "row_count": len(app_dicts),
        "tsv": tsv_data,
        "preview_headers": rows[0] if rows else [],
        "preview_rows": rows[1:35] if len(rows) > 1 else [],
    }


@app.post("/api/sync/sheets/config")
def save_sheets_sync_config(payload: dict = {}, db: Session = Depends(get_db)):
    state = GoogleSheetsService.update_config(payload or {})
    return {"success": True, "state": state, "message": "Google Sheets sync settings saved."}


@app.post("/api/sync/sheets")
def sync_sheets_api(payload: dict = {}, db: Session = Depends(get_db)):
    if payload:
        GoogleSheetsService.update_config(payload)
    app_dicts = _serialize_apps_for_sheets(db)
    sheets_service = GoogleSheetsService()
    res = sheets_service.sync_catalog_to_sheets(app_dicts)
    return res


@app.post("/api/sync/sheets/pull")
def pull_sheets_api(payload: dict = {}, db: Session = Depends(get_db)):
    if payload:
        GoogleSheetsService.update_config(payload)
    sheets_service = GoogleSheetsService()
    return sheets_service.pull_catalog_from_sheet(db)


@app.get("/api/sync/sheets/csv")
def download_sheets_csv_api(db: Session = Depends(get_db)):
    from fastapi.responses import FileResponse
    app_dicts = _serialize_apps_for_sheets(db)
    sheets_service = GoogleSheetsService()
    csv_path = sheets_service.export_to_csv_preview(app_dicts)
    return FileResponse(csv_path, media_type="text/csv", filename="app_universe_export.csv")


@app.post("/api/health/analyze")
def analyze_health_api(target: str = "all", db: Session = Depends(get_db)):
    from gitbridge.services.analyzer_service import AppAnalyzerService
    from gitbridge.services.drive_service import GoogleDriveService
    
    analyzer = AppAnalyzerService()
    drive_service = GoogleDriveService()

    if target == "all":
        apps = db.query(AppProfileModel).all()
    else:
        app_obj = db.query(AppProfileModel).filter(AppProfileModel.slug == target).first()
        apps = [app_obj] if app_obj else []

    processed = []
    for a in apps:
        health_md = analyzer.generate_health_card(a)
        a.health_report_md = health_md
        a.feature_breakdown = health_md
        drive_service.save_health_report(a.slug, a.name, health_md)
        processed.append(a.slug)

    db.commit()

    # Generate master datasets
    app_dicts = [
        {
            "slug": a.slug,
            "name": a.name,
            "priority_tier": a.priority_tier,
            "status": a.status.value if hasattr(a.status, 'value') else str(a.status),
            "description": a.description,
            "github_url": a.github_url,
            "tech_stack": a.tech_stack,
            "open_issues_count": a.open_issues_count or 0,
            "last_commit_at": a.last_commit_at,
            "tags": a.tags,
            "version": a.version
        }
        for a in db.query(AppProfileModel).all()
    ]
    drive_service.sync_master_catalog_files(app_dicts)

    return {"message": "Health analysis completed", "processed_apps": processed, "total": len(processed)}

@app.get("/api/health/reports/{slug}")
def get_health_report_api(slug: str, db: Session = Depends(get_db)):
    app_obj = db.query(AppProfileModel).filter(AppProfileModel.slug == slug).first()
    if not app_obj:
        raise HTTPException(status_code=404, detail=f"App with slug '{slug}' not found")
    
    from gitbridge.services.analyzer_service import AppAnalyzerService
    analyzer = AppAnalyzerService()
    health_md = app_obj.health_report_md or analyzer.generate_health_card(app_obj)

    return {
        "slug": slug,
        "name": app_obj.name,
        "priority_tier": app_obj.priority_tier,
        "health_card_markdown": health_md
    }

@app.get("/api/context/universe")
def get_gemini_universe_context(db: Session = Depends(get_db)):
    """Specialized endpoint providing full structured Markdown context dump of Geppy's App Universe for Gemini AI."""
    from gitbridge.services.context_service import GeminiContextService
    context_text = GeminiContextService.generate_universe_markdown(db)
    apps = db.query(AppProfileModel).all()
    return {
        "formatted_context": context_text,
        "app_count": len(apps),
        "apps": [serialize_app_profile(a, db) for a in apps]
    }

@app.get("/api/context/apps/{slug}")
def get_gemini_app_context(slug: str, db: Session = Depends(get_db)):
    """Get targeted Markdown context for a specific app profile."""
    app_obj = db.query(AppProfileModel).filter(AppProfileModel.slug == slug).first()
    if not app_obj:
        raise HTTPException(status_code=404, detail=f"App with slug '{slug}' not found")
    
    from gitbridge.services.context_service import GeminiContextService
    context_text = GeminiContextService.generate_app_markdown(app_obj, db)
    return {
        "slug": slug,
        "name": app_obj.name,
        "formatted_context": context_text,
        "profile": serialize_app_profile(app_obj, db)
    }

@app.post("/api/context/export")
def export_gemini_context_file_endpoint(db: Session = Depends(get_db)):
    """Export master GEMINI_UNIVERSE_CONTEXT.md file directly into local workspace directory."""
    from gitbridge.services.context_service import GeminiContextService
    res = GeminiContextService.export_context_file(db)
    return res

@app.post("/api/context/search")
def search_gemini_context(payload: dict = {}, db: Session = Depends(get_db)):
    """Search context across apps by keyword or tech stack."""
    query_str = payload.get("query", "").lower().strip()
    if not query_str:
        raise HTTPException(status_code=400, detail="Query string 'query' is required")

    apps = db.query(AppProfileModel).all()
    matched_apps = []

    for a in apps:
        searchable = f"{a.name} {a.slug} {a.description} {' '.join(a.tech_stack or [])} {' '.join(a.tags or [])}".lower()
        if query_str in searchable:
            matched_apps.append(a)

    from gitbridge.services.context_service import GeminiContextService
    context_snippets = "\n\n".join([GeminiContextService.generate_app_markdown(a, db) for a in matched_apps])

    return {
        "query": query_str,
        "matched_count": len(matched_apps),
        "formatted_context": context_snippets if context_snippets else f"No apps matching query '{query_str}' found.",
        "matched_slugs": [a.slug for a in matched_apps]
    }


# --- Gemini Mobile Doc Bridge & Auto-Listener Endpoints ---

@app.on_event("startup")
def start_mobile_bridge_listener():
    from gitbridge.services.mobile_bridge_service import MobileBridgeService
    MobileBridgeService.ensure_listener_running()
    try:
        from gitbridge.services.antigravity_service import AntigravityDaemonPool
        AntigravityDaemonPool.ensure_running()
    except Exception as e:
        print(f"Warning: AntigravityService startup skipped: {e}")

@app.get("/api/mobile-bridge/state")
def get_mobile_bridge_state():
    from gitbridge.services.mobile_bridge_service import MobileBridgeService
    MobileBridgeService.ensure_listener_running()
    return MobileBridgeService.get_state()

@app.post("/api/mobile-bridge/config")
def update_mobile_bridge_config(payload: dict = {}):
    from gitbridge.services.mobile_bridge_service import MobileBridgeService
    state = MobileBridgeService.update_config(payload)
    return {"success": True, "state": state}

@app.post("/api/mobile-bridge/sync-master-doc")
def sync_mobile_bridge_master_doc(db: Session = Depends(get_db)):
    from gitbridge.services.mobile_bridge_service import MobileBridgeService
    return MobileBridgeService.generate_master_bridge_doc(db)

@app.post("/api/mobile-bridge/scan")
def scan_mobile_bridge_now(payload: dict = {}):
    from gitbridge.services.mobile_bridge_service import MobileBridgeService
    force = bool(payload.get("force", True))
    return MobileBridgeService.scan_for_modifications(force=force)

@app.post("/api/mobile-bridge/open-folder")
def open_mobile_bridge_folder():
    import subprocess
    from gitbridge.services.mobile_bridge_service import MobileBridgeService
    state = MobileBridgeService.get_state()
    folder = state.get("watch_folder")
    if folder and os.path.exists(folder):
        subprocess.Popen(["explorer", os.path.abspath(folder)])
        return {"success": True, "folder": folder}
    raise HTTPException(status_code=404, detail="Watch folder not found")

@app.post("/api/mobile-bridge/tasks")
def add_mobile_bridge_task(payload: dict = {}):
    from gitbridge.services.mobile_bridge_service import MobileBridgeService
    app_slug = (payload.get("app_slug") or "").strip()
    instruction = (payload.get("instruction") or "").strip()
    target_file = (payload.get("target_file") or "auto").strip()
    auto_execute = bool(payload.get("auto_execute", False))
    if not app_slug or not instruction:
        raise HTTPException(status_code=400, detail="Both app_slug and instruction are required")
    return MobileBridgeService.add_manual_task(app_slug, instruction, target_file, auto_execute)

@app.post("/api/mobile-bridge/tasks/run-all-pending")
def run_all_pending_mobile_bridge_tasks(db: Session = Depends(get_db)):
    from gitbridge.services.mobile_bridge_service import MobileBridgeService
    state = MobileBridgeService.get_state()
    pending = [t for t in state.get("tasks", []) if t.get("status") in ("pending", "failed")]
    results = []
    for t in pending:
        results.append(MobileBridgeService.execute_modification(t["id"], db=db))
    return {"success": True, "executed_count": len(results), "results": results, "state": MobileBridgeService.get_state()}

@app.post("/api/mobile-bridge/tasks/{task_id}/run")
def run_mobile_bridge_task(task_id: str, db: Session = Depends(get_db)):
    from gitbridge.services.mobile_bridge_service import MobileBridgeService
    res = MobileBridgeService.execute_modification(task_id, db=db)
    res["state"] = MobileBridgeService.get_state()
    return res

@app.delete("/api/mobile-bridge/tasks/{task_id}")
def delete_mobile_bridge_task(task_id: str):
    from gitbridge.services.mobile_bridge_service import MobileBridgeService
    return MobileBridgeService.delete_task(task_id)


# --- GitBridge Specialized Agent Crew & Multi-Agent Council Endpoints ---

@app.get("/api/extension/antigravity/live")
def get_antigravity_live_activity_endpoint():
    """Return real-time background AI / Antigravity task telemetry and completion state."""
    from gitbridge.services.antigravity_service import AntigravityDaemonPool
    return AntigravityDaemonPool.get_live_activity()

@app.get("/api/agents")
def list_specialist_agents():
    """List all built-in and custom AI specialist agents in Captain Geppy's Crew."""
    from gitbridge.services.agent_crew_service import AgentCrewService
    agents = AgentCrewService.get_all_agents()
    return {"agents": agents, "count": len(agents)}

@app.post("/api/agents/custom")
def save_custom_specialist_agent(payload: dict = {}):
    """Create or update a custom specialist AI agent."""
    from gitbridge.services.agent_crew_service import AgentCrewService
    agent = AgentCrewService.save_custom_agent(payload)
    return {"success": True, "agent": agent, "agents": AgentCrewService.get_all_agents()}

@app.delete("/api/agents/custom/{agent_id}")
def delete_custom_specialist_agent(agent_id: str):
    """Delete a custom specialist AI agent."""
    from gitbridge.services.agent_crew_service import AgentCrewService
    deleted = AgentCrewService.delete_custom_agent(agent_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Custom agent '{agent_id}' not found")
    return {"success": True, "agents": AgentCrewService.get_all_agents()}

@app.post("/api/agents/run")
def run_specialist_agent_mission_endpoint(payload: dict = {}, db: Session = Depends(get_db)):
    """Execute a focused specialist agent mission (Design, Architecture, Social Media, Growth, QA, Docs)."""
    from gitbridge.services.agent_crew_service import AgentCrewService
    agent_id = (payload.get("agent_id") or "design-architect").strip()
    prompt = (payload.get("prompt") or payload.get("message") or "").strip()
    app_slug = payload.get("app_slug") or payload.get("slug")
    file_path = payload.get("file_path")
    history = payload.get("history", [])
    generate_promo_visual = bool(payload.get("generate_promo_visual", False))
    save_deliverable = bool(payload.get("save_deliverable", True))

    return AgentCrewService.run_agent_mission(
        agent_id=agent_id,
        prompt=prompt,
        app_slug=app_slug,
        file_path=file_path,
        history=history,
        generate_promo_visual=generate_promo_visual,
        save_deliverable_flag=save_deliverable,
        db=db
    )

@app.post("/api/agents/council")
def run_crew_council_endpoint(payload: dict = {}, db: Session = Depends(get_db)):
    """Summon multiple agents together ('Crew Council Mode') to review an app across Design, Architecture, Social Media & Strategy."""
    from gitbridge.services.agent_crew_service import AgentCrewService
    prompt = (payload.get("prompt") or payload.get("message") or "").strip()
    app_slug = payload.get("app_slug") or payload.get("slug")
    agent_ids = payload.get("agent_ids")
    file_path = payload.get("file_path")

    return AgentCrewService.run_crew_council(
        prompt=prompt,
        app_slug=app_slug,
        agent_ids=agent_ids,
        file_path=file_path,
        db=db
    )

@app.get("/api/apps/{slug}/deliverables")
def get_app_deliverables_endpoint(slug: str):
    """Fetch saved Agent Crew deliverables, Social Media Kits, and Council Reports for an app."""
    from gitbridge.services.agent_crew_service import AgentCrewService
    items = AgentCrewService.get_app_deliverables(slug)
    return {"slug": slug, "deliverables": items, "count": len(items)}

@app.post("/api/apps/{slug}/deliverables")
def save_app_deliverable_endpoint(slug: str, payload: dict = {}, db: Session = Depends(get_db)):
    """Save an Agent Crew deliverable or Social Media Kit for an app (optionally publishing to Instruction Manuals)."""
    from gitbridge.services.agent_crew_service import AgentCrewService
    rec = AgentCrewService.save_deliverable(slug, payload, db=db)
    return {"success": True, "deliverable": rec}

@app.delete("/api/apps/{slug}/deliverables/{deliverable_id}")
def delete_app_deliverable_endpoint(slug: str, deliverable_id: str):
    """Delete a saved Agent Crew deliverable."""
    from gitbridge.services.agent_crew_service import AgentCrewService
    deleted = AgentCrewService.delete_deliverable(slug, deliverable_id)
    return {"success": deleted, "deliverable_id": deliverable_id}


