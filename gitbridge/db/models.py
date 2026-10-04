import json
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import relationship
from gitbridge.db.database import Base
from gitbridge.schemas.app_profile import AppStatus, AssetType

class AppProfileModel(Base):
    __tablename__ = "app_profiles"

    id = Column(Integer, primary_key=True, index=True)
    slug = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    status = Column(SQLEnum(AppStatus), default=AppStatus.IN_DEVELOPMENT)
    github_url = Column(String, nullable=True)
    github_repo_name = Column(String, nullable=True)
    ai_studio_link = Column(String, nullable=True)
    _tech_stack = Column("tech_stack", Text, default="[]")
    system_instructions = Column(Text, nullable=True)
    feature_breakdown = Column(Text, nullable=True)
    _tags = Column("tags", Text, default="[]")
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
