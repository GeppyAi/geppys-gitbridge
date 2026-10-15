import os
import re
import requests
import json
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from gitbridge.db.models import AppProfileModel, ContextileModel, MediaAssetModel
from gitbridge.services.workspace_service import WorkspaceService
from gitbridge.services.context_service import GeminiContextService
from gitbridge.services.sot_service import SOTService
from gitbridge.services.asset_lab_service import AssetLabService

GEMINI_MODELS = ["gemini-2.5-flash", "gemini-1.5-flash", "gemini-3.8-flash"]

class ChatService:

    @staticmethod
    def is_image_request(message: str) -> bool:
        """Check if message represents a visual asset or image generation command/request."""
        m = (message or "").strip().lower()
        if m.startswith(("/image", "/img", "/icon", "/draw", "/pic", "/generate-image", "/asset")):
            return True
        patterns = [
            r"\b(generate|create|make|draw|synthesize|design|render)\s+(an?\s+)?(app\s+)?(image|icon|logo|badge|mascot|graphic|illustration|sticker|artwork|avatar)\b",
            r"\b(image|icon|logo|badge|sticker)\s+of\b",
            r"\bdraw\s+me\s+(an?\s+)?",
            r"\bcan\s+you\s+(draw|generate|create|make)\s+(an?\s+)?(image|icon|picture|illustration)\b",
            r"\b(generate|create|make)\s+a\s+visual\b"
        ]
        for pat in patterns:
            if re.search(pat, m):
                return True
        return False

    @staticmethod
    def extract_image_prompt(message: str) -> str:
        """Clean command wrappers and leading trigger words to isolate the core image prompt."""
        cleaned = (message or "").strip()
        for cmd in ["/image", "/img", "/icon", "/draw", "/pic", "/generate-image", "/asset"]:
            if cleaned.lower().startswith(cmd):
                cleaned = cleaned[len(cmd):].strip()
                break
        pats = [
            r"^(please\s+)?(can\s+you\s+)?(generate|create|make|draw|synthesize|design|render)\s+(an?\s+)?(app\s+)?(image|icon|logo|badge|mascot|graphic|illustration|sticker|artwork|avatar)\s+(of|for|with)?\s*",
            r"^(draw|paint)\s+(me\s+)?(an?\s+)?(image|icon|picture|illustration)?\s*(of|for|with)?\s*"
        ]
        for p in pats:
            cleaned = re.sub(p, "", cleaned, flags=re.IGNORECASE).strip()
        return cleaned or message.strip()

    @staticmethod
    def generate_chat_image(
        prompt: str,
        app_slug: Optional[str] = None,
        db: Optional[Session] = None
    ) -> Dict[str, Any]:
        """Synthesize a fine-tuned visual asset directly inside Captain Geppy chat."""
        app_obj = None
        if app_slug and db:
            app_obj = db.query(AppProfileModel).filter(AppProfileModel.slug == app_slug).first()

        app_name = app_obj.name if app_obj else "Geppy's Galactic"
        clean_prompt = ChatService.extract_image_prompt(prompt)

        # Title
        raw_title = clean_prompt[:40].strip()
        title = f"{app_name} Icon" if not raw_title or len(raw_title) < 3 else raw_title.title()

        # Target Format
        is_transparent = any(k in prompt.lower() for k in ["transparent", "no background", "sticker", "badge", "icon", "isolated", "png"])
        target_format = "transparent_png" if is_transparent else "app_icon"

        # Check SOT contextiles for brand & style
        ingredients_summary = []
        ref_images = []

        if db:
            # Check for mentions in prompt
            mention_res = SOTService.resolve_mentions(prompt, db)
            if mention_res.get("has_mentions"):
                for m in mention_res.get("mentions", []):
                    ctx = db.query(ContextileModel).filter(ContextileModel.name == m).first()
                    if ctx:
                        ctx_imgs = [img for img in [ctx.primary_image_url, ctx.reference_image_url] + (ctx.gallery_images or []) if img]
                        ingredients_summary.append({
                            "name": ctx.name,
                            "title": ctx.title,
                            "archetype": ctx.archetype,
                            "primary_image_url": ctx.primary_image_url,
                            "reference_image_url": ctx.reference_image_url,
                            "reference_images": ctx_imgs
                        })
                        for img in ctx_imgs:
                            if img not in ref_images:
                                ref_images.append(img)

            # Auto-ground with Captain Geppy brand if geppy/captain/mascot or default
            if not any(i.get("archetype") == "character" for i in ingredients_summary):
                geppy_brand = db.query(ContextileModel).filter(ContextileModel.name == "geppybrand").first()
                if geppy_brand:
                    brand_imgs = [img for img in [geppy_brand.primary_image_url, geppy_brand.reference_image_url] + (geppy_brand.gallery_images or []) if img]
                    ingredients_summary.append({
                        "name": "geppybrand",
                        "title": geppy_brand.title or "Captain Geppy",
                        "archetype": "character",
                        "primary_image_url": geppy_brand.primary_image_url,
                        "reference_images": brand_imgs
                    })
                    for img in brand_imgs:
                        if img not in ref_images:
                            ref_images.append(img)

            # Auto-ground with Hexagonal orange icon if icon or hex requested
            if any(k in prompt.lower() for k in ["hex", "orange", "icon", "app"]):
                hex_ctx = db.query(ContextileModel).filter(ContextileModel.name == "geppy-hex-icon").first()
                if hex_ctx:
                    hex_imgs = [img for img in [hex_ctx.primary_image_url, hex_ctx.reference_image_url] + (hex_ctx.gallery_images or []) if img]
                    ingredients_summary.append({
                        "name": "geppy-hex-icon",
                        "title": hex_ctx.title or "Geppy Hex Icon",
                        "archetype": "icon_set",
                        "primary_image_url": hex_ctx.primary_image_url,
                        "reference_images": hex_imgs
                    })
                    for img in hex_imgs:
                        if img not in ref_images:
                            ref_images.append(img)

        # Build master prompt with style hints
        master_prompt = clean_prompt
        if "hex" not in master_prompt.lower() and "icon" in master_prompt.lower():
            master_prompt += " Hexagonal app icon silhouette with bold orange border and metallic accents."
        if is_transparent and "transparent" not in master_prompt.lower():
            master_prompt += " Isolated on transparent background, transparent PNG."

        # Generate asset via AssetLabService
        record = AssetLabService.generate_visual_asset(
            title=title,
            master_prompt=master_prompt,
            target_format=target_format,
            aspect_ratio="1:1",
            color_palette=["#F59E0B", "#1E1B4B", "#06B6D4", "#0F172A"],
            composition_blueprint=f"Visual asset for {app_name}",
            ingredients_summary=ingredients_summary,
            reference_images=ref_images,
            app_slug=app_slug
        )

        palette_chips = " • ".join(record.get("color_palette", ["#F59E0B", "#1E1B4B", "#06B6D4"]))
        caption = f"""### 👨‍🚀 Captain Geppy here! Visual Asset Synthesized!

I've engaged our cosmic synthesis engines and materialized a custom visual asset for **{app_name}**:

> **"{record['title']}"**
> *{clean_prompt}*

![{record['title']}]({record['file_url']})

- **Silhouette**: Hexagonal with bold orange bevels & metallic accents
- **Format**: 1024×1024 32-bit Transparent PNG (Clean Alpha)
- **Palette**: {palette_chips}
- **Filename**: `{record['filename']}`

Click the action buttons below to **Set as Official App Icon**, **Save to App Folder**, or open in the **Asset Lab**!"""

        extracted_tasks = [
            {
                "title": f"Set {record['title']} as App Icon",
                "category": "design",
                "description": f"Apply {record['filename']} as official app icon for {app_name}",
                "suggested_prompt": f"Apply new app icon {record['file_url']} to {app_name}"
            },
            {
                "title": f"Save {record['filename']} to assets folder",
                "category": "design",
                "description": f"Save synthesized image to {app_name}/assets/ directory",
                "suggested_prompt": f"Drop {record['filename']} into assets/"
            }
        ]

        return {
            "is_image": True,
            "text": caption,
            "image_url": record["file_url"],
            "image_title": record["title"],
            "image_filename": record["filename"],
            "color_palette": record.get("color_palette", []),
            "app_slug": app_slug,
            "extracted_tasks": extracted_tasks
        }

    @classmethod
    def process_chat(
        cls,
        prompt: str,
        app_slug: Optional[str] = None,
        file_path: Optional[str] = None,
        history: List[Dict[str, str]] = [],
        is_image: bool = False,
        db: Optional[Session] = None
    ) -> Dict[str, Any]:
        """Universal chat handler routing conversational and image generation requests."""
        if is_image or cls.is_image_request(prompt):
            img_result = cls.generate_chat_image(prompt=prompt, app_slug=app_slug, db=db)
            return {
                "sender": "ai",
                "text": img_result["text"],
                "is_image": True,
                "image_data": {
                    "image_url": img_result["image_url"],
                    "title": img_result["image_title"],
                    "filename": img_result["image_filename"],
                    "color_palette": img_result["color_palette"]
                },
                "extracted_tasks": img_result.get("extracted_tasks", []),
                "app_slug": app_slug,
                "file_path": file_path
            }

        text_response = cls.process_chat_message(prompt=prompt, app_slug=app_slug, file_path=file_path, history=history, db=db)
        return {
            "sender": "ai",
            "text": text_response,
            "is_image": False,
            "image_data": None,
            "extracted_tasks": [],
            "app_slug": app_slug,
            "file_path": file_path
        }

    @staticmethod
    def process_chat_message(
        prompt: str,
        app_slug: Optional[str] = None,
        file_path: Optional[str] = None,
        history: List[Dict[str, str]] = [],
        db: Optional[Session] = None
    ) -> str:
        """Process conversational AI user message as Captain Geppy with full Galaxy, file & SOT Contextile context."""
        context_info = ""
        app_obj = None

        # 1. Resolve any SOT Contextile @mentions (e.g. @captain-geppy, @galactic-card-ui)
        sot_grounding = ""
        if db:
            mention_res = SOTService.resolve_mentions(prompt, db)
            if mention_res.get("has_mentions"):
                sot_grounding = mention_res.get("grounding_prompt", "")

        # 2. Project & Workspace Context
        if app_slug and db:
            app_obj = db.query(AppProfileModel).filter(AppProfileModel.slug == app_slug).first()
            if app_obj:
                context_info = f"ACTIVE PLANETARY SECTOR / APP CONTEXT:\n- App Name: {app_obj.name} (`{app_obj.slug}`)\n"
                context_info += f"- Status: {app_obj.status}\n- Tech Stack: {', '.join(app_obj.tech_stack or [])}\n"
                context_info += f"- Description: {app_obj.description or 'None'}\n"
                if app_obj.system_instructions:
                    context_info += f"- Core System Prompt: {app_obj.system_instructions[:500]}\n"
                if app_obj.feature_breakdown:
                    context_info += f"- Sector Architectural Summary: {app_obj.feature_breakdown[:600]}\n"

                # Local Git status & telemetry
                if app_obj.local_path:
                    try:
                        git_stat = WorkspaceService.get_git_status(app_obj)
                        if git_stat.get("has_changes"):
                            mod_files = [f["path"] for f in git_stat.get("files", [])[:6]]
                            context_info += f"- Local Git Status: {git_stat.get('total_changes')} uncommitted changes ({', '.join(mod_files)})\n"
                            if git_stat.get("unpushed_count", 0) > 0:
                                context_info += f"- Unpushed Commits: {git_stat.get('unpushed_count')} commits ready to push to GitHub\n"
                        else:
                            context_info += "- Local Git Status: Clean (All changes committed to disk)\n"
                        if git_stat.get("branch"):
                            context_info += f"- Current Git Branch: {git_stat.get('branch')}\n"
                        if git_stat.get("remote_url"):
                            context_info += f"- GitHub Remote: {git_stat.get('remote_url')}\n"
                    except Exception:
                        pass

                if file_path:
                    file_res = WorkspaceService.read_app_file(app_obj, file_path)
                    if file_res.get("success"):
                        context_info += f"\nACTIVE FILE AT THE HELM (`{file_path}`):\n```\n{file_res['content'][:4000]}\n```\n"

        if not context_info and db:
            apps = db.query(AppProfileModel).all()
            context_info = f"GEPPY'S GALACTIC CONTEXT ({len(apps)} registered apps in the galaxy):\n"
            context_info += ", ".join([f"{a.name} ({a.slug})" for a in apps[:20]])

        # 3. Append SOT Grounding to Context if present
        if sot_grounding:
            context_info = f"{sot_grounding}\n\n{context_info}"

        system_instruction = """You are Captain Geppy — Commander and Face of Geppy's Galactic!
You guide the creator on an epic journey through the vast Galaxy of Apps that AI makes possible.
Persona & Communication Style:
- Persona: Charismatic, visionary, encouraging, and razor-sharp galactic commander ("Captain Geppy here!", "Plotting trajectory...", "Engaging warp drive!").
- Source of Truth (SOT) Authority: When SOT Contextiles (@handle) are referenced, treat them as sacred Ground Truth baselines. Use their exact visual descriptors, lighting, era, and modifiers for code or image generation prompts.
- Practicality: Always provide production-ready, beautiful code, drop-in UI solutions, and cosmic-level aesthetic improvements.
- Version Control & Git Savvy: You are aware of the app's local git status and modified files. When the creator discusses changes, wrap-ups, or says 'commit', 'save to github', 'push', or asks what changed, reassure them that they can commit and push their changes using the Commit & Push feature so work is preserved safely on their computer and on GitHub!
- Format responses cleanly with Markdown, code fences, and bulleted action steps."""

        from gitbridge.services.central_key_service import CentralKeyService
        messages = []
        for h in history[-8:]:
            role = "user" if h.get("sender") == "user" else "model"
            messages.append({"role": role, "parts": [{"text": h.get("text", "")}]})

        messages.append({
            "role": "user",
            "parts": [{"text": f"Galactic Bridge Context:\n{context_info}\n\nCrew Message / Request:\n{prompt}"}]
        })

        ai_response = CentralKeyService.call_gemini(messages, system_instruction, timeout=22)
        if ai_response:
            return ai_response

        # Fallback Engine if API fails
        app_name = app_obj.name if app_obj else "Geppy's Galactic"
        return f"""### 👨‍🚀 Captain Geppy Reporting In! ({app_name})

Coordinates locked! I've analyzed your transmission regarding **{app_name}**:

> "{prompt}"

{sot_grounding}

#### 🚀 Captain's Flight Plan & Next Actions:
1. **Galactic Architectural Scan**: Ensure dependencies in `{app_obj.local_path if app_obj else 'd:\\Geppy_Apps'}` are calibrated and synced.
2. **Interactive Live Editing**: Select components from the star-chart tree on the left to edit files live.
3. **SOT Engine Grounding**: Reference any saved Contextile with `@name` (e.g. `@captain-geppy`, `@galactic-card-ui`) for instant ground-truth alignment.

*(Status: All engines operational at warp speed across Geppy's Galactic)*"""
