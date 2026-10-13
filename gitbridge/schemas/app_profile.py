from datetime import datetime
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field

class AppStatus(str, Enum):
    IDEA = "idea"
    IN_DEVELOPMENT = "in_development"
    PRODUCTION = "production"
    ARCHIVED = "archived"

class AssetType(str, Enum):
    ICON = "icon"
    SCREENSHOT = "screenshot"
    BANNER = "banner"
    LOGO = "logo"
    DOC_IMAGE = "doc_image"
    VIDEO_DEMO = "video_demo"
    OTHER = "other"

class MediaAssetBase(BaseModel):
    title: str = Field(..., description="Title or label for the asset")
    asset_type: AssetType = Field(AssetType.SCREENSHOT, description="Type of asset")
    file_path: str = Field(..., description="Relative or absolute path to asset file")
    url: Optional[str] = Field(None, description="Remote host URL or CDN link")
    generation_prompt: Optional[str] = Field(None, description="AI Prompt used to generate the image")
    tags: List[str] = Field(default_factory=list, description="Tags for categorization")

class MediaAssetCreate(MediaAssetBase):
    app_id: str

class MediaAssetResponse(MediaAssetBase):
    id: int
    app_id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class DocManualBase(BaseModel):
    title: str = Field(..., description="Title of the documentation manual")
    summary: Optional[str] = Field(None, description="Short summary")
    content_markdown: str = Field("", description="Full markdown content")
    file_path: Optional[str] = Field(None, description="Path to .md file in docs directory")

class DocManualCreate(DocManualBase):
    app_id: str

class DocManualResponse(DocManualBase):
    id: int
    app_id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class AppProfileBase(BaseModel):
    slug: str = Field(..., description="Unique slug identifier (e.g., 'geppys-gitbridge')")
    name: str = Field(..., description="Full application name")
    description: Optional[str] = Field(None, description="App summary description")
    status: AppStatus = Field(AppStatus.IN_DEVELOPMENT, description="Current lifecycle status")
    github_url: Optional[str] = Field(None, description="GitHub repository URL")
    github_repo_name: Optional[str] = Field(None, description="GitHub repo full name owner/repo")
    ai_studio_link: Optional[str] = Field(None, description="AI Studio prompt/app link")
    local_path: Optional[str] = Field(None, description="Local folder path on disk")
    local_exists: Optional[bool] = Field(False, description="Whether the local directory currently exists on disk")
    github_exists: Optional[bool] = Field(False, description="Whether remote GitHub repository is linked")
    sync_state: Optional[str] = Field("none", description="Sync state: synced, pc_newer, github_newer, local_only, github_only, none")
    sync_label: Optional[str] = Field("No Source", description="Human-readable sync state label")
    launch_command: Optional[str] = Field(None, description="Startup CLI command (e.g., npm start, python main.py)")
    live_url: Optional[str] = Field(None, description="Live web application URL")
    icon_url: Optional[str] = Field(None, description="App icon image URL")
    is_live: Optional[bool] = Field(False, description="Whether this app is currently live running on localhost")
    tech_stack: List[str] = Field(default_factory=list, description="Frameworks, languages, dependencies")
    system_instructions: Optional[str] = Field(None, description="Core AI Studio system instructions / prompt")
    feature_breakdown: Optional[str] = Field(None, description="AI-analyzed feature breakdown & architectural report")
    priority_tier: Optional[str] = Field("Tier 2 (Core Infrastructure)", description="Market / Portfolio priority score")
    health_report_md: Optional[str] = Field(None, description="Generated Markdown Health Card report")
    last_commit_at: Optional[datetime] = Field(None, description="Last commit date from GitHub")
    open_issues_count: Optional[int] = Field(0, description="Count of open GitHub issues and PRs")
    tags: List[str] = Field(default_factory=list, description="Categorization tags")
    backlog: List[dict] = Field(default_factory=list, description="Brainstorm tasks and ideas backlog")
    version: str = Field("0.1.0", description="App version")
    is_hidden: Optional[bool] = Field(False, description="Whether this app is hidden from main catalog & system tray")

class AppProfileCreate(AppProfileBase):
    pass

class AppProfileUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[AppStatus] = None
    is_hidden: Optional[bool] = None
    github_url: Optional[str] = None
    github_repo_name: Optional[str] = None
    ai_studio_link: Optional[str] = None
    local_path: Optional[str] = None
    launch_command: Optional[str] = None
    live_url: Optional[str] = None
    icon_url: Optional[str] = None
    tech_stack: Optional[List[str]] = None
    system_instructions: Optional[str] = None
    feature_breakdown: Optional[str] = None
    priority_tier: Optional[str] = None
    health_report_md: Optional[str] = None
    last_commit_at: Optional[datetime] = None
    open_issues_count: Optional[int] = None
    tags: Optional[List[str]] = None
    backlog: Optional[List[dict]] = None
    version: Optional[str] = None

class AppProfileResponse(AppProfileBase):
    id: int
    created_at: datetime
    updated_at: datetime
    assets: List[MediaAssetResponse] = Field(default_factory=list)
    manuals: List[DocManualResponse] = Field(default_factory=list)

    class Config:
        from_attributes = True

class AppCatalogSummary(BaseModel):
    total_apps: int
    status_counts: dict
    apps: List[AppProfileBase]
