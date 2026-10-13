from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime

class ContextileBase(BaseModel):
    name: str = Field(..., description="Unique handle/slug used for @name mentions, e.g. 'captain-geppy'")
    title: str = Field(..., description="Human-readable title for the Contextile")
    description: Optional[str] = Field(None, description="Detailed description or purpose")
    archetype: str = Field("character", description="Archetype: 'character', 'icon_set', 'ui_component', 'brand_asset', 'environment', or 'general'")
    reference_type: str = Field("text", description="'image', 'text', or 'hybrid'")
    reference_text: Optional[str] = Field(None, description="Base text description or prompt anchor")
    reference_image_url: Optional[str] = Field(None, description="URL or local path to uploaded reference image")
    primary_image_url: Optional[str] = Field(None, description="Primary/main reference image URL (e.g. key character pose or hero icon)")
    gallery_images: List[str] = Field(default_factory=list, description="List of reference images (e.g. icon set pack or character turnarounds)")
    modifiers: Dict[str, Any] = Field(default_factory=dict, description="Active modifiers grouped by category: lighting, theme, era, medium, custom")
    variables: List[Dict[str, Any]] = Field(default_factory=list, description="Dynamic template variables (e.g. team_name, player_name, position, stats)")
    tags: List[str] = Field(default_factory=list, description="Categorization tags")
    assembled_prompt: Optional[str] = Field(None, description="Compiled Source of Truth generation prompt")
    app_slug: Optional[str] = Field(None, description="Optional associated app profile slug")

class ContextileCreate(ContextileBase):
    pass

class ContextileUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    archetype: Optional[str] = None
    reference_type: Optional[str] = None
    reference_text: Optional[str] = None
    reference_image_url: Optional[str] = None
    primary_image_url: Optional[str] = None
    gallery_images: Optional[List[str]] = None
    modifiers: Optional[Dict[str, Any]] = None
    variables: Optional[List[Dict[str, Any]]] = None
    tags: Optional[List[str]] = None
    assembled_prompt: Optional[str] = None
    app_slug: Optional[str] = None

class ContextileResponse(ContextileBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
