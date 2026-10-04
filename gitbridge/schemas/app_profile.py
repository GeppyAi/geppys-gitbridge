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
    tech_stack: List[str] = Field(default_factory=list, description="Frameworks, languages, dependencies")
    system_instructions: Optional[str] = Field(None, description="Core AI Studio system instructions / prompt")
    feature_breakdown: Optional[str] = Field(None, description="AI-analyzed feature breakdown & architectural report")
    tags: List[str] = Field(default_factory=list, description="Categorization tags")
    version: str = Field("0.1.0", description="App version")

class AppProfileCreate(AppProfileBase):
    pass

class AppProfileUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[AppStatus] = None
    github_url: Optional[str] = None
    github_repo_name: Optional[str] = None
    ai_studio_link: Optional[str] = None
    tech_stack: Optional[List[str]] = None
    system_instructions: Optional[str] = None
    feature_breakdown: Optional[str] = None
    tags: Optional[List[str]] = None
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
