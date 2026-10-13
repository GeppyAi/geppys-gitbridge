from fastapi import FastAPI, Depends, HTTPException, Query, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import List, Optional
import os
import re
import time

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

@app.get("/api/settings")
def get_settings():
    from gitbridge.services.workspace_service import WorkspaceService
    token = os.getenv("GITHUB_TOKEN", "")
    username = os.getenv("GITHUB_USERNAME", "")
    gemini_key = os.getenv("GEMINI_API_KEY", "")
    masked_token = f"{token[:4]}...{token[-4:]}" if len(token) > 8 else ("configured" if token else "")
    masked_gemini = f"{gemini_key[:4]}...{gemini_key[-4:]}" if len(gemini_key) > 8 else ("configured" if gemini_key else "")
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
    token = settings.get("github_token", "").strip()
    username = settings.get("github_username", "").strip()
    workspace_dir = settings.get("geppy_apps_dir", "").strip()
    gemini_key = settings.get("gemini_api_key", "").strip()
    
    if workspace_dir:
        WorkspaceService.set_workspace_dir(workspace_dir)

    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    if not os.path.exists(env_path):
        env_path = ".env"

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
    if gemini_key:
        env_data["GEMINI_API_KEY"] = gemini_key
        os.environ["GEMINI_API_KEY"] = gemini_key

    with open(env_path, "w", encoding="utf-8") as f:
        for k, v in env_data.items():
            f.write(f"{k}={v}\n")

    return {
        "message": "Settings updated successfully",
        "github_token_configured": bool(os.getenv("GITHUB_TOKEN")),
        "gemini_api_key_configured": bool(os.getenv("GEMINI_API_KEY")),
        "geppy_apps_dir": WorkspaceService.get_workspace_dir()
    }

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

    is_live = app_obj.slug in ACTIVE_SERVERS
    live_url = ACTIVE_SERVERS[app_obj.slug]["url"] if is_live else app_obj.live_url

    icon_url = app_obj.icon_url
    if icon_url and icon_url.startswith("/api/apps/"):
        fname = icon_url.split("/")[-1]
        from gitbridge.services.workspace_service import WorkspaceService
        assets_dir = WorkspaceService.ensure_app_assets_dir(app_obj)
        fpath = os.path.join(assets_dir, fname) if assets_dir else None
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

@app.post("/api/apps/{slug}/launch")
def launch_app_endpoint(slug: str, db: Session = Depends(get_db)):
    app_obj = db.query(AppProfileModel).filter(AppProfileModel.slug == slug).first()
    if not app_obj:
        raise HTTPException(status_code=404, detail=f"App with slug '{slug}' not found")

    from gitbridge.services.launcher_service import AppLauncherService
    result = AppLauncherService.launch_localhost(app_obj)
    
    # Save detected live_url to database profile if launched
    if result.get("launched") and result.get("target"):
        app_obj.live_url = result["target"]
        db.commit()

    return result

@app.post("/api/apps/{slug}/set-icon")
def set_app_icon_endpoint(slug: str, payload: dict = {}, db: Session = Depends(get_db)):
    app_obj = db.query(AppProfileModel).filter(AppProfileModel.slug == slug).first()
    if not app_obj:
        raise HTTPException(status_code=404, detail=f"App with slug '{slug}' not found")

    icon_url = payload.get("icon_url") or payload.get("url")
    if not icon_url:
        raise HTTPException(status_code=400, detail="icon_url parameter is required")

    app_obj.icon_url = icon_url
    db.commit()
    db.refresh(app_obj)

    return serialize_app_profile(app_obj, db)

@app.get("/api/servers")
def get_active_servers():
    from gitbridge.services.launcher_service import AppLauncherService
    return AppLauncherService.list_active_servers()

@app.delete("/api/servers/{slug}")
def stop_active_server(slug: str):
    from gitbridge.services.launcher_service import AppLauncherService
    stopped = AppLauncherService.stop_localhost_server(slug)
    return {"slug": slug, "stopped": stopped}

@app.post("/api/servers/{slug}/stop")
def stop_server_post(slug: str):
    from gitbridge.services.launcher_service import AppLauncherService
    stopped = AppLauncherService.stop_localhost_server(slug)
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
    return res

@app.post("/api/servers/stop-all")
def stop_all_servers_endpoint():
    from gitbridge.services.launcher_service import AppLauncherService
    count = AppLauncherService.stop_all_servers()
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

    if not file_path:
        raise HTTPException(status_code=400, detail="file_path is required")

    from gitbridge.services.workspace_service import WorkspaceService
    res = WorkspaceService.save_app_file(app_obj, file_path, content)
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("message", "Could not save file"))
    return res

@app.post("/api/chat")
def chat_api_endpoint(payload: dict = {}, db: Session = Depends(get_db)):
    prompt = payload.get("message", "").strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="Message prompt is required")

    app_slug = payload.get("app_slug")
    file_path = payload.get("file_path")
    history = payload.get("history", [])

    from gitbridge.services.chat_service import ChatService
    response_text = ChatService.process_chat_message(prompt=prompt, app_slug=app_slug, file_path=file_path, history=history, db=db)

    return {
        "sender": "ai",
        "text": response_text,
        "app_slug": app_slug,
        "file_path": file_path
    }

# --- Chrome Extension Companion API Endpoints ---
@app.get("/api/extension/detect-app")
def extension_detect_app_endpoint(url: str = Query(...), db: Session = Depends(get_db)):
    """Detect which app is running at the given browser tab URL."""
    from gitbridge.services.extension_service import ExtensionService
    from gitbridge.services.launcher_service import ACTIVE_SERVERS
    match = ExtensionService.detect_active_app(url, ACTIVE_SERVERS, db)
    if not match:
        return {"matched": False, "app": None}
    app_obj = db.query(AppProfileModel).filter(AppProfileModel.slug == match["slug"]).first()
    return {
        "matched": True,
        "match_type": match["match_type"],
        "app": serialize_app_profile(app_obj, db) if app_obj else None
    }

@app.post("/api/extension/brainstorm")
def extension_brainstorm_endpoint(payload: dict = {}, db: Session = Depends(get_db)):
    """Conversational brainstorming endpoint that outputs inspiring concepts and real-time task backlog."""
    message = payload.get("message", "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message is required")
    slug = payload.get("slug")
    file_path = payload.get("file_path")
    history = payload.get("history", [])

    from gitbridge.services.extension_service import ExtensionService
    result = ExtensionService.brainstorm(slug=slug, message=message, history=history, file_path=file_path, db=db)
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

@app.post("/api/extension/apply-design")
def extension_apply_design_endpoint(payload: dict = {}, db: Session = Depends(get_db)):
    """Apply an AI design suggestion, brainstorm task, or user prompt to code."""
    slug = payload.get("slug", "")
    file_path = payload.get("file_path", "")
    current_code = payload.get("current_code", "")
    instruction = payload.get("instruction", "").strip()

    if not instruction:
        raise HTTPException(status_code=400, detail="Instruction is required")

    from gitbridge.services.extension_service import ExtensionService
    result = ExtensionService.apply_design(slug=slug, file_path=file_path, current_code=current_code, instruction=instruction, db=db)
    return result

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

# --- SOT (Source of Truth) & Contextiles API Endpoints ---
@app.get("/api/sot/modifiers")
def get_sot_modifiers_endpoint():
    """Return categorized modifier taxonomy and archetype definitions."""
    from gitbridge.services.sot_service import SOTService
    return {
        "modifiers": SOTService.get_modifiers_taxonomy(),
        "archetypes": SOTService.get_archetypes()
    }

@app.post("/api/sot/ai-suggest-modifiers")
def ai_suggest_sot_modifiers_endpoint(payload: dict = {}):
    """Use Gemini to brainstorm an optimal modifier recipe based on reference text and archetype."""
    reference_text = payload.get("reference_text", "")
    archetype = payload.get("archetype", "character")
    app_name = payload.get("app_name")
    from gitbridge.services.sot_service import SOTService
    return SOTService.suggest_modifiers_ai(reference_text, archetype, app_name)

@app.post("/api/sot/ai-autofill")
def ai_autofill_contextile_endpoint(payload: dict = {}):
    """Intelligently autofill an entire Contextile from a creator's seed prompt or concept."""
    prompt = payload.get("prompt", "")
    archetype = payload.get("archetype")
    app_name = payload.get("app_name")
    from gitbridge.services.sot_service import SOTService
    return SOTService.ai_autofill_contextile(prompt, archetype, app_name)

@app.post("/api/sot/generate-contextile")
def generate_ai_contextile_endpoint(payload: dict = {}, db: Session = Depends(get_db)):
    """AI Generate a complete Context Style Contextile (e.g. '70s baseball card') with master prompt, modifiers, and preview thumbnail."""
    concept = payload.get("concept", "") or payload.get("prompt", "")
    if not concept:
        raise HTTPException(status_code=400, detail="Concept or prompt is required")
    archetype = payload.get("archetype")
    save_immediately = payload.get("save_immediately", True)
    from gitbridge.services.sot_service import SOTService
    return SOTService.generate_ai_contextile(
        concept=concept,
        archetype=archetype,
        save_immediately=save_immediately,
        db=db
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
    """List all saved Source-of-Truth Contextiles."""
    from gitbridge.services.sot_service import SOTService
    ctxs = SOTService.list_contextiles(db, app_slug=app_slug)
    return [
        {
            "id": c.id,
            "name": c.name,
            "title": c.title,
            "description": c.description,
            "archetype": c.archetype or "character",
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
    """Create or update a Source of Truth Contextile."""
    from gitbridge.services.sot_service import SOTService
    ctx = SOTService.create_contextile(payload, db)
    return {
        "id": ctx.id,
        "name": ctx.name,
        "title": ctx.title,
        "description": ctx.description,
        "archetype": ctx.archetype,
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
        "message": f"Contextile '@{ctx.name}' saved successfully!"
    }

@app.get("/api/sot/contextiles/{name}")
def get_contextile_endpoint(name: str, db: Session = Depends(get_db)):
    """Get single Contextile by handle name."""
    from gitbridge.services.sot_service import SOTService
    ctx = SOTService.get_contextile(name, db)
    if not ctx:
        raise HTTPException(status_code=404, detail=f"Contextile '@{name}' not found")
    return {
        "id": ctx.id,
        "name": ctx.name,
        "title": ctx.title,
        "description": ctx.description,
        "archetype": ctx.archetype or "character",
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

@app.post("/api/asset-lab/synthesize")
def synthesize_asset_recipe_endpoint(payload: dict = {}):
    """Mix multiple SOT contextiles, reference images, and directives into a Master Synthesis Blueprint."""
    ingredients = payload.get("ingredients", [])
    custom_prompt = payload.get("custom_prompt", "")
    target_format = payload.get("target_format", "app_icon")
    fidelity_mode = payload.get("fidelity_mode", "balanced")
    overrides = payload.get("overrides", {})
    reference_images = payload.get("reference_images", [])
    app_context = payload.get("app_context")
    variables = payload.get("variables", {})

    from gitbridge.services.asset_lab_service import AssetLabService
    recipe = AssetLabService.synthesize_blend(
        ingredients=ingredients,
        custom_prompt=custom_prompt,
        target_format=target_format,
        fidelity_mode=fidelity_mode,
        overrides=overrides,
        reference_images=reference_images,
        app_context=app_context,
        variables=variables
    )
    return recipe

@app.post("/api/asset-lab/generate")
def generate_asset_lab_visual_endpoint(payload: dict = {}):
    """Generate the actual fine-tuned visual asset PNG and persist in the lab repository."""
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
        variables=variables
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
    result = WorkspaceService.push_app_to_github(app_obj, commit_message=msg, make_private=make_private, push_remote=push_remote, db=db)
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

@app.post("/api/sync/sheets")
def sync_sheets_api(db: Session = Depends(get_db)):
    apps = db.query(AppProfileModel).all()
    app_dicts = [
        {
            "slug": a.slug,
            "name": a.name,
            "description": a.description,
            "status": a.status.value if hasattr(a.status, 'value') else str(a.status),
            "github_url": a.github_url,
            "ai_studio_link": a.ai_studio_link,
            "tech_stack": a.tech_stack,
            "tags": a.tags,
            "version": a.version,
            "updated_at": a.updated_at
        }
        for a in apps
    ]
    sheets_service = GoogleSheetsService()
    success = sheets_service.sync_catalog_to_sheets(app_dicts)
    if not success:
        sheets_service.export_to_csv_preview(app_dicts)
    return {"message": "Sheets Sync Triggered", "google_sheets_updated": success}

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
