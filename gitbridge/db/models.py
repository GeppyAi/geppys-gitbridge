import json
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean, Enum as SQLEnum
from sqlalchemy.orm import relationship
from gitbridge.db.database import Base
from gitbridge.schemas.app_profile import AppStatus, AssetType

class AppProfileModel(Base):
    __tablename__ = "app_profiles"

    id = Column(Integer, primary_key=True, index=True)
    slug = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String, default="AI, Prompts & Planning", nullable=True)
    status = Column(SQLEnum(AppStatus), default=AppStatus.IN_DEVELOPMENT)
    is_hidden = Column(Boolean, default=False, nullable=False)
    github_url = Column(String, nullable=True)
    github_repo_name = Column(String, nullable=True)
    ai_studio_link = Column(String, nullable=True)
    local_path = Column(String, nullable=True)
    launch_command = Column(String, nullable=True)
    live_url = Column(String, nullable=True)
    icon_url = Column(String, nullable=True)
    _tech_stack = Column("tech_stack", Text, default="[]")
    system_instructions = Column(Text, nullable=True)
    feature_breakdown = Column(Text, nullable=True)
    priority_tier = Column(String, default="Tier 2 (Core Infrastructure)")
    health_report_md = Column(Text, nullable=True)
    last_commit_at = Column(DateTime, nullable=True)
    last_opened_at = Column(DateTime, nullable=True)
    open_issues_count = Column(Integer, default=0)
    _tags = Column("tags", Text, default="[]")
    _backlog = Column("backlog", Text, default="[]")
    _chat_history = Column("chat_history", Text, default="[]")
    version = Column(String, default="0.1.0")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    assets = relationship("MediaAssetModel", back_populates="app", cascade="all, delete-orphan")
    manuals = relationship("DocManualModel", back_populates="app", cascade="all, delete-orphan")

    @property
    def tech_stack(self):
        return json.loads(self._tech_stack or "[]")

    @tech_stack.setter
    def tech_stack(self, value):
        self._tech_stack = json.dumps(value or [])

    @property
    def tags(self):
        return json.loads(self._tags or "[]")

    @tags.setter
    def tags(self, value):
        self._tags = json.dumps(value or [])

    @property
    def backlog(self):
        return json.loads(self._backlog or "[]")

    @backlog.setter
    def backlog(self, value):
        self._backlog = json.dumps(value or [])

    @property
    def chat_history(self):
        return json.loads(self._chat_history or "[]")

    @chat_history.setter
    def chat_history(self, value):
        self._chat_history = json.dumps(value or [])

class MediaAssetModel(Base):
    __tablename__ = "media_assets"

    id = Column(Integer, primary_key=True, index=True)
    app_id = Column(String, ForeignKey("app_profiles.slug"), nullable=False)
    title = Column(String, nullable=False)
    asset_type = Column(SQLEnum(AssetType), default=AssetType.SCREENSHOT)
    file_path = Column(String, nullable=False)
    url = Column(String, nullable=True)
    generation_prompt = Column(Text, nullable=True)
    _tags = Column("tags", Text, default="[]")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    app = relationship("AppProfileModel", back_populates="assets")

    @property
    def tags(self):
        return json.loads(self._tags or "[]")

    @tags.setter
    def tags(self, value):
        self._tags = json.dumps(value or [])

class DocManualModel(Base):
    __tablename__ = "doc_manuals"

    id = Column(Integer, primary_key=True, index=True)
    app_id = Column(String, ForeignKey("app_profiles.slug"), nullable=False)
    title = Column(String, nullable=False)
    summary = Column(Text, nullable=True)
    content_markdown = Column(Text, nullable=False, default="")
    file_path = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    app = relationship("AppProfileModel", back_populates="manuals")

class ContextileModel(Base):
    __tablename__ = "contextiles"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False) # e.g. "captain-geppy" for @captain-geppy
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    archetype = Column(String, default="character", nullable=False) # "character", "icon_set", "ui_component", "brand_asset", "environment", "general"
    reference_type = Column(String, default="text") # "image", "text", "hybrid"
    reference_text = Column(Text, nullable=True)
    reference_image_url = Column(String, nullable=True) # Fallback / primary reference image URL
    primary_image_url = Column(String, nullable=True) # Main reference image for character facial/outfit baseline or key icon standard
    _gallery_images = Column("gallery_images", Text, default="[]") # JSON list of image URLs: ["/api/sot/reference-file/...", ...]
    _modifiers = Column("modifiers", Text, default="{}") # JSON dict of active modifiers
    _tags = Column("tags", Text, default="[]")
    _variables = Column("variables", Text, default="[]") # Dynamic template variables: [{"key": "team_name", "label": "Team Name", "value": "...", "default_value": "..."}]
    assembled_prompt = Column(Text, nullable=True)
    app_slug = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @property
    def gallery_images(self):
        return json.loads(self._gallery_images or "[]")

    @gallery_images.setter
    def gallery_images(self, value):
        self._gallery_images = json.dumps(value or [])

    @property
    def modifiers(self):
        return json.loads(self._modifiers or "{}")

    @modifiers.setter
    def modifiers(self, value):
        self._modifiers = json.dumps(value or {})

    @property
    def tags(self):
        return json.loads(self._tags or "[]")

    @tags.setter
    def tags(self, value):
        self._tags = json.dumps(value or [])

    @property
    def variables(self):
        try:
            return json.loads(self._variables or "[]")
        except Exception:
            return []

    @variables.setter
    def variables(self, value):
        self._variables = json.dumps(value or [])

