from fastapi import FastAPI, Depends, HTTPException, Query, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import List, Optional
import os

from gitbridge.db.database import get_db, init_db
from gitbridge.db.models import AppProfileModel, MediaAssetModel, DocManualModel
from gitbridge.schemas.app_profile import (
    AppProfileResponse, AppProfileCreate, AppProfileUpdate,
    MediaAssetCreate, MediaAssetResponse,
    DocManualCreate, DocManualResponse, AppStatus, AssetType
)
from gitbridge.services.github_service import GitHubService
from gitbridge.services.sheets_service import GoogleSheetsService
from gitbridge.services.ai_studio_service import AIStudioParser

init_db()

app = FastAPI(
    title="Geppy's GitBridge API",
    description="Central control plane & catalog for Geppy's App Universe",
    version="0.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {
        "status": "online",
        "system": "Geppy's GitBridge",
        "version": "0.1.0",
        "docs_url": "/docs"
    }

@app.get("/api/apps", response_model=List[AppProfileResponse])
def list_apps(status: Optional[AppStatus] = None, db: Session = Depends(get_db)):
    query = db.query(AppProfileModel)
    if status:
        query = query.filter(AppProfileModel.status == status)
    return query.all()

@app.get("/api/apps/{slug}", response_model=AppProfileResponse)
def get_app(slug: str, db: Session = Depends(get_db)):
    app_obj = db.query(AppProfileModel).filter(AppProfileModel.slug == slug).first()
    if not app_obj:
        raise HTTPException(status_code=404, detail=f"App with slug '{slug}' not found")
    return app_obj

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
    return app_obj

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
    return app_obj

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
def sync_github_api(username: Optional[str] = None, db: Session = Depends(get_db)):
    gh_service = GitHubService()
    repos = gh_service.fetch_user_repos(username)
    added = 0
    updated = 0

    for repo in repos:
        parsed = gh_service.parse_repo_to_profile_dict(repo)
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
            added += 1
        else:
            existing.github_url = parsed["github_url"]
            existing.github_repo_name = parsed["github_repo_name"]
            if parsed["description"]:
                existing.description = parsed["description"]
            existing.tech_stack = list(dict.fromkeys(existing.tech_stack + parsed["tech_stack"]))
            updated += 1

    db.commit()
    return {"message": "GitHub Sync Completed", "added": added, "updated": updated}

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

@app.get("/api/context/universe")
def get_gemini_universe_context(db: Session = Depends(get_db)):
    """Specialized endpoint providing full context dump of Geppy's App Universe for Gemini AI."""
    apps = db.query(AppProfileModel).all()
    
    context_text = "# Geppy's App Universe Catalog Context\n\n"
    context_text += f"Total Registered Apps: {len(apps)}\n\n"

    for a in apps:
        context_text += f"## App Profile: {a.name} (`{a.slug}`)\n"
        context_text += f"- **Status**: {a.status.value if hasattr(a.status, 'value') else str(a.status)}\n"
        context_text += f"- **GitHub**: {a.github_url or 'None'}\n"
        context_text += f"- **AI Studio Link**: {a.ai_studio_link or 'None'}\n"
        context_text += f"- **Tech Stack**: {', '.join(a.tech_stack)}\n"
        context_text += f"- **Description**: {a.description or 'No description'}\n"
        if a.system_instructions:
            context_text += f"- **System Instructions / Prompts**:\n```\n{a.system_instructions}\n```\n"
        if a.assets:
            context_text += f"- **Media Assets**: {len(a.assets)} items registered.\n"
        if a.manuals:
            context_text += f"- **Instruction Manuals**: {len(a.manuals)} docs available.\n"
        context_text += "\n---\n\n"

    return {
        "formatted_context": context_text,
        "app_count": len(apps),
        "apps": apps
    }
