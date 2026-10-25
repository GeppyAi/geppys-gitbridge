import os
import re
import time
import threading
import requests
import json
from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy.orm import Session

from gitbridge.db.models import AppProfileModel, ContextileModel, MediaAssetModel
from gitbridge.services.workspace_service import WorkspaceService
from gitbridge.services.context_service import GeminiContextService
from gitbridge.services.sot_service import SOTService
from gitbridge.services.asset_lab_service import AssetLabService

GEMINI_MODELS = ["gemini-2.5-flash", "gemini-1.5-flash", "gemini-3.8-flash"]


class LiveScreenStreamHub:
    """
    In-memory hub storing live screen stream frames from both GitBridge ('gitbridge')
    and Galactic ('galactic' / active browser tab / screen share) so Geppy and his
    Agent Crew can see what the user is working on in real time.
    """
    _lock = threading.Lock()
    _streams: Dict[str, Dict[str, Any]] = {}
    _ttl_seconds: float = 120.0

    @classmethod
    def push_frame(
        cls,
        source: str,
        frame_b64: str,
        app_slug: Optional[str] = None,
        viewport_title: Optional[str] = None,
        viewport_url: Optional[str] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
    ) -> Dict[str, Any]:
        norm_source = (source or "galactic").strip().lower()
        now = time.time()
        with cls._lock:
            existing = cls._streams.get(norm_source, {})
            frame_count = int(existing.get("frame_count", 0)) + 1
            entry = {
                "source": norm_source,
                "frame_b64": frame_b64,
                "app_slug": app_slug or existing.get("app_slug") or "",
                "viewport_title": viewport_title or existing.get("viewport_title") or "",
                "viewport_url": viewport_url or existing.get("viewport_url") or "",
                "width": width or existing.get("width") or 0,
                "height": height or existing.get("height") or 0,
                "updated_at": now,
                "frame_count": frame_count,
                "active": True,
            }
            cls._streams[norm_source] = entry
            return {
                "source": norm_source,
                "active": True,
                "frame_count": frame_count,
                "app_slug": entry["app_slug"],
                "viewport_title": entry["viewport_title"],
                "updated_at": now,
            }

    @classmethod
    def stop_stream(cls, source: Optional[str] = None) -> Dict[str, Any]:
        with cls._lock:
            if source:
                norm_source = source.strip().lower()
                if norm_source in cls._streams:
                    cls._streams[norm_source]["active"] = False
                    cls._streams[norm_source]["frame_b64"] = ""
            else:
                for k in list(cls._streams.keys()):
                    cls._streams[k]["active"] = False
                    cls._streams[k]["frame_b64"] = ""
        return cls.get_status()

    @classmethod
    def get_status(cls, include_thumbnails: bool = True) -> Dict[str, Any]:
        now = time.time()
        streams_summary: Dict[str, Any] = {}
        active_sources: List[str] = []
        with cls._lock:
            for src, info in list(cls._streams.items()):
                age = now - float(info.get("updated_at", 0))
                is_active = bool(info.get("active")) and age <= cls._ttl_seconds and bool(info.get("frame_b64"))
                if is_active:
                    active_sources.append(src)
                streams_summary[src] = {
                    "source": src,
                    "active": is_active,
                    "age_seconds": round(age, 1),
                    "frame_count": info.get("frame_count", 0),
                    "app_slug": info.get("app_slug", ""),
                    "viewport_title": info.get("viewport_title", ""),
                    "viewport_url": info.get("viewport_url", ""),
                    "width": info.get("width", 0),
                    "height": info.get("height", 0),
                    "frame_b64": info.get("frame_b64", "") if (include_thumbnails and is_active) else "",
                }
        return {
            "streaming": len(active_sources) > 0,
            "is_streaming": len(active_sources) > 0,
            "active_sources": active_sources,
            "streams": streams_summary,
        }

    @classmethod
    def get_active_vision_frames(cls, extra_frames: Optional[List[str]] = None) -> Tuple[List[str], str]:
        """Return list of base64 frames (from extra_frames + active streams) and a text description for system prompt."""
        now = time.time()
        frames: List[str] = []
        descriptions: List[str] = []
        if extra_frames:
            for ef in extra_frames:
                if ef and isinstance(ef, str) and len(ef) > 64:
                    frames.append(ef)
                    descriptions.append("Direct live screen frame attached with this message")

        with cls._lock:
            for src in ("galactic", "gitbridge", "screen"):
                info = cls._streams.get(src)
                if not info:
                    continue
                age = now - float(info.get("updated_at", 0))
                fb64 = info.get("frame_b64") or ""
                if info.get("active") and age <= cls._ttl_seconds and fb64:
                    if fb64 not in frames:
                        frames.append(fb64)
                    title = info.get("viewport_title") or src.upper()
                    url = info.get("viewport_url") or ""
                    descriptions.append(f"Live '{src}' screen stream ({title} {url}, captured {int(age)}s ago)".strip())

            # Also check any other custom sources
            for src, info in cls._streams.items():
                if src in ("galactic", "gitbridge", "screen"):
                    continue
                age = now - float(info.get("updated_at", 0))
                fb64 = info.get("frame_b64") or ""
                if info.get("active") and age <= cls._ttl_seconds and fb64 and fb64 not in frames:
                    frames.append(fb64)
                    descriptions.append(f"Live '{src}' stream (captured {int(age)}s ago)")

        if not frames:
            return [], ""
        context_note = (
            "LIVE SCREEN STREAM VISION ACTIVE:\n"
            "You are currently receiving real-time visual screen frames of what the user is working on:\n- "
            + "\n- ".join(descriptions)
            + "\nDirectly reference what you see on their screen (layout, colors, UI components, code, or errors) as a live co-designer!"
        )
        return frames[:4], context_note


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
                raw_mentions = mention_res.get("contextiles") or mention_res.get("mentions") or []
                for m in raw_mentions:
                    m_handle = (m.get("name") or m.get("handle") or m.get("target_handle")) if isinstance(m, dict) else str(m)
                    if not m_handle:
                        continue
                    ctx = db.query(ContextileModel).filter(ContextileModel.name == m_handle).first()
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

            # Auto-ground with Geppy brand if geppy/mascot or default
            is_gb = bool(app_slug and app_slug.lower() in ("geppys-gitbridge", "gitbridge")) or ("gitbridge" in app_name.lower())
            if not any(i.get("archetype") == "character" for i in ingredients_summary):
                target_brand_name = "captain-geppy" if is_gb else "geppybrand"
                geppy_brand = db.query(ContextileModel).filter(ContextileModel.name == target_brand_name).first()
                if not geppy_brand:
                    geppy_brand = db.query(ContextileModel).filter(ContextileModel.name == "geppybrand").first()
                if geppy_brand:
                    brand_imgs = [img for img in [geppy_brand.primary_image_url, geppy_brand.reference_image_url] + (geppy_brand.gallery_images or []) if img]
                    ingredients_summary.append({
                        "name": geppy_brand.name,
                        "title": "Captain Geppy" if is_gb else "Geppy",
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

        is_gb = bool(app_slug and app_slug.lower() in ("geppys-gitbridge", "gitbridge")) or ("gitbridge" in app_name.lower())
        persona_header = "👨‍🚀 Captain Geppy here! Visual Asset Synthesized!" if is_gb else "✨ Geppy here! Visual Asset Synthesized!"
        palette_chips = " • ".join(record.get("color_palette", ["#F59E0B", "#1E1B4B", "#06B6D4"]))
        caption = f"""### {persona_header}

I've created a custom visual asset for **{app_name}**:

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
    def _attach_optional_ai_voice(
        cls,
        result_dict: Dict[str, Any],
        voice_mode: bool = False,
        include_audio: bool = False,
        app_slug: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Attach active AI model metadata and optional Gemini AI voice (`audio_data_url`) when in voice mode or requested."""
        try:
            from gitbridge.services.central_key_service import CentralKeyService
            mstate = CentralKeyService.get_model_state()
            result_dict.setdefault("model_used", mstate.get("last_used_model") or mstate.get("active_model"))
            result_dict.setdefault("model_mode", mstate.get("mode", "auto"))
            result_dict.setdefault("model_label", mstate.get("mode_label", ""))
            result_dict.setdefault("model_reason", mstate.get("last_selection_reason", ""))
            result_dict["model_state"] = mstate
        except Exception:
            pass

        if not (voice_mode or include_audio):
            return result_dict
        spoken = (result_dict.get("spoken_reply") or result_dict.get("text") or "").strip()
        if not spoken:
            return result_dict
        try:
            from gitbridge.services.central_key_service import CentralKeyService
            is_gb = (not app_slug) or (app_slug.lower() in ("geppys-gitbridge", "gitbridge"))
            persona = "Captain Geppy" if is_gb else "Geppy"
            tts_res = CentralKeyService.synthesize_speech_wav_b64(
                text=spoken,
                voice_name="Puck",
                persona=persona,
                timeout=12,
            )
            if tts_res.get("ok") and tts_res.get("audio_data_url"):
                result_dict["audio_data_url"] = tts_res["audio_data_url"]
                result_dict["voice_engine"] = tts_res.get("model", "gemini-2.5-flash-preview-tts")
                result_dict["voice_name"] = tts_res.get("voice", "Puck")
        except Exception as e:
            print(f"[ChatService] AI voice synthesis notice: {e}")
        return result_dict

    @classmethod
    def process_chat(
        cls,
        prompt: str,
        app_slug: Optional[str] = None,
        file_path: Optional[str] = None,
        history: List[Dict[str, str]] = [],
        is_image: bool = False,
        agent_id: Optional[str] = None,
        screen_frame_b64: Optional[str] = None,
        voice_mode: bool = False,
        consult_crew: bool = False,
        consult_agents: Optional[List[str]] = None,
        include_audio: bool = False,
        model_override: Optional[str] = None,
        db: Optional[Session] = None
    ) -> Dict[str, Any]:
        """
        Universal chat handler routing conversational, specialized agent crew, voice consultation, and image generation requests.
        Protected by the GitBridge Watchdog Self-Healing Engine so unhandled exceptions never return plain-text HTTP 500s.
        """
        if screen_frame_b64 and isinstance(screen_frame_b64, str) and len(screen_frame_b64) > 64:
            try:
                LiveScreenStreamHub.push_frame(
                    source="gitbridge",
                    frame_b64=screen_frame_b64,
                    app_slug=app_slug or "geppys-gitbridge",
                    viewport_title="GitBridge Live Workspace",
                )
            except Exception:
                pass

        from gitbridge.services.agent_crew_service import AgentCrewService
        from gitbridge.services.antigravity_service import AntigravityDaemonPool
        from gitbridge.services.central_key_service import CentralKeyService

        try:
            # Handle explicit model override or natural-language/voice model switch command
            if model_override and model_override.strip():
                CentralKeyService.set_model_mode(model_override.strip(), reason="Selected from UI")
                AntigravityDaemonPool.sync_with_central_model()

            switch_cmd = CentralKeyService.detect_and_apply_model_switch_command(prompt)
            if switch_cmd:
                AntigravityDaemonPool.sync_with_central_model()
                # If the user's message was primarily a command to switch models, confirm immediately
                if len((prompt or "").strip()) <= 90:
                    is_gb = (not app_slug) or (app_slug.lower() in ("geppys-gitbridge", "gitbridge"))
                    leader = "Captain Geppy" if is_gb else "Geppy"
                    mode_lbl = switch_cmd.get("mode_label", switch_cmd.get("mode"))
                    act_mod = switch_cmd.get("active_model", "gemini-3-flash-preview")
                    reason_txt = switch_cmd.get("last_selection_reason", "Updated per your request.")
                    reply_md = (
                        f"### 🧠 {leader} AI Model Updated!\n\n"
                        f"I've switched my AI engine to **{mode_lbl}** (`{act_mod}`).\n\n"
                        f"- **Routing Mode**: `{switch_cmd.get('mode')}`\n"
                        f"- **Active Primary Model**: `{act_mod}`\n"
                        f"- **Why**: {reason_txt}\n\n"
                        f"Whenever my mode is set to **Auto**, I automatically shift gears between **Flash-Lite** (instant voice & quick tasks), **Gemini 3 Flash** (fast coding & live vision), and **Gemini 2.5 Pro** (deep architecture & complex debugging) based on what you need!"
                    )
                    spoken = f"{leader} here! I've switched my AI model to {mode_lbl}. {reason_txt}"
                    res = {
                        "sender": "ai",
                        "text": reply_md,
                        "spoken_reply": spoken,
                        "is_image": False,
                        "image_data": None,
                        "extracted_tasks": [],
                        "model_switched": True,
                        "model_state": switch_cmd,
                        "app_slug": app_slug,
                        "file_path": file_path,
                    }
                    return cls._attach_optional_ai_voice(res, voice_mode=voice_mode, include_audio=include_audio, app_slug=app_slug)

            if is_image or cls.is_image_request(prompt):
                img_result = cls.generate_chat_image(prompt=prompt, app_slug=app_slug, db=db)
                spoken = AgentCrewService.build_spoken_summary(img_result["text"])
                res = {
                    "sender": "ai",
                    "text": img_result["text"],
                    "spoken_reply": spoken,
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
                return cls._attach_optional_ai_voice(res, voice_mode=voice_mode, include_audio=include_audio, app_slug=app_slug)

            # Check if user asked Geppy to consult the crew (either via consult_crew toggle or natural voice/text phrase)
            low_prompt = (prompt or "").lower().strip()
            clean_greeting = re.sub(r"[^a-z\s]", "", low_prompt).strip()
            is_quick_greeting = clean_greeting in (
                "hello", "hi", "hey", "yo", "howdy", "greetings", "good morning", "good afternoon",
                "good evening", "hello captain", "hi captain", "hey captain", "hello geppy", "hi geppy", "hey geppy",
                "can you hear me", "testing", "test"
            )
            explicit_crew_phrase = any(
                kw in low_prompt for kw in (
                    "consult with", "consult the", "ask the crew", "ask the agents", "check with the crew",
                    "check with the agents", "what do the agents think", "what does the crew think",
                    "consult your crew", "consult agents"
                )
            )
            wants_crew_consult = explicit_crew_phrase or (bool(consult_crew) and not is_quick_greeting)

            if wants_crew_consult and not agent_id:
                consult_res = AgentCrewService.consult_crew_with_geppy(
                    prompt=prompt,
                    app_slug=app_slug,
                    file_path=file_path,
                    history=history,
                    agent_ids=consult_agents,
                    screen_frame_b64=screen_frame_b64,
                    voice_mode=voice_mode,
                    db=db,
                )
                res = {
                    "sender": "ai",
                    "text": consult_res["reply"],
                    "spoken_reply": consult_res.get("spoken_reply", ""),
                    "is_image": False,
                    "image_data": None,
                    "extracted_tasks": consult_res.get("extracted_tasks", []),
                    "consulted_agents": consult_res.get("consulted_agents", []),
                    "live_stream_seen": consult_res.get("live_stream_seen", False),
                    "antigravity_error": consult_res.get("antigravity_error"),
                    "agent": {
                        "id": "geppy-crew-consult",
                        "name": "🎙️ Geppy + Agent Crew Consultation",
                        "icon": "🤝",
                        "role": "Live Co-Design & Crew Consultation",
                    },
                    "app_slug": app_slug,
                    "file_path": file_path,
                }
                return cls._attach_optional_ai_voice(res, voice_mode=voice_mode, include_audio=include_audio, app_slug=app_slug)

            det = AgentCrewService.detect_agent_from_message(prompt, explicit_agent_id=agent_id)
            if det["mode"] == "council":
                council_res = AgentCrewService.run_crew_council(
                    prompt=det["clean_message"],
                    app_slug=app_slug,
                    file_path=file_path,
                    screen_frame_b64=screen_frame_b64,
                    db=db,
                )
                res = {
                    "sender": "ai",
                    "text": council_res["reply"],
                    "spoken_reply": council_res.get("spoken_reply", ""),
                    "is_image": False,
                    "image_data": None,
                    "extracted_tasks": council_res.get("extracted_tasks", []),
                    "social_kit": council_res.get("social_kit"),
                    "live_stream_seen": council_res.get("live_stream_seen", False),
                    "agent": {
                        "id": "crew-council",
                        "name": "⚡ Agent Crew Council",
                        "icon": "⚡",
                        "role": "Multi-Agent Review",
                    },
                    "app_slug": app_slug,
                    "file_path": file_path,
                }
                return cls._attach_optional_ai_voice(res, voice_mode=voice_mode, include_audio=include_audio, app_slug=app_slug)
            elif det["mode"] == "single" and det.get("agent"):
                ag = det["agent"]
                mission_res = AgentCrewService.run_agent_mission(
                    agent_id=ag["id"],
                    prompt=det["clean_message"],
                    app_slug=app_slug,
                    file_path=file_path,
                    history=history,
                    screen_frame_b64=screen_frame_b64,
                    db=db,
                )
                res = {
                    "sender": "ai",
                    "text": mission_res["reply"],
                    "spoken_reply": mission_res.get("spoken_reply", ""),
                    "is_image": False,
                    "image_data": None,
                    "extracted_tasks": mission_res.get("extracted_tasks", []),
                    "social_kit": mission_res.get("social_kit"),
                    "live_stream_seen": mission_res.get("live_stream_seen", False),
                    "agent": ag,
                    "app_slug": app_slug,
                    "file_path": file_path,
                }
                return cls._attach_optional_ai_voice(res, voice_mode=voice_mode, include_audio=include_audio, app_slug=app_slug)

            vision_frames, _ = LiveScreenStreamHub.get_active_vision_frames(
                extra_frames=[screen_frame_b64] if screen_frame_b64 else None
            )
            text_response = cls.process_chat_message(
                prompt=prompt,
                app_slug=app_slug,
                file_path=file_path,
                history=history,
                screen_frame_b64=screen_frame_b64,
                voice_mode=voice_mode,
                db=db
            )
            spoken = AgentCrewService.build_spoken_summary(text_response)
            open_errs = [e for e in AntigravityDaemonPool.get_errors(slug=app_slug, limit=3) if e.get("status") == "open"]
            res = {
                "sender": "ai",
                "text": text_response,
                "spoken_reply": spoken,
                "is_image": False,
                "image_data": None,
                "extracted_tasks": [],
                "live_stream_seen": len(vision_frames) > 0,
                "antigravity_error": open_errs[0] if open_errs else None,
                "app_slug": app_slug,
                "file_path": file_path
            }
            return cls._attach_optional_ai_voice(res, voice_mode=voice_mode, include_audio=include_audio, app_slug=app_slug)

        except Exception as watchdog_exc:
            # --- WATCHDOG SELF-HEALING & AUTO-CORRECTION BRIDGE ---
            import traceback
            tb_lines = traceback.extract_tb(watchdog_exc.__traceback__)
            culprit_file = file_path or "gitbridge/services/chat_service.py"
            if tb_lines:
                last_frame = tb_lines[-1]
                fname = os.path.basename(last_frame.filename)
                culprit_file = f"gitbridge/services/{fname}:{last_frame.lineno}" if "services" in last_frame.filename else f"{fname}:{last_frame.lineno}"

            raw_err_msg = f"{type(watchdog_exc).__name__}: {watchdog_exc}"
            print(f"[Watchdog Self-Heal] Caught exception in process_chat ({culprit_file}): {raw_err_msg}")

            watchdog_record = AntigravityDaemonPool.diagnose_and_record_error(
                raw_error=raw_err_msg,
                slug=app_slug or "geppys-gitbridge",
                app_name="Geppy's GitBridge",
                mode="chat_watchdog",
                target_file=culprit_file,
                instruction=prompt,
                error_type_hint="watchdog_chat_healed",
                source="watchdog",
            )

            # Auto-heal by running direct conversational fallback so Captain Geppy still answers!
            try:
                fallback_text = cls.process_chat_message(
                    prompt=prompt,
                    app_slug=app_slug,
                    file_path=file_path,
                    history=history,
                    screen_frame_b64=screen_frame_b64,
                    voice_mode=voice_mode,
                    db=db,
                )
            except Exception:
                is_gb = (not app_slug) or (app_slug.lower() in ("geppys-gitbridge", "gitbridge"))
                leader = "Captain Geppy" if is_gb else "Geppy"
                fallback_text = (
                    f"### 👨‍🚀 {leader} Here! (Watchdog Auto-Healed)\n\n"
                    f"Loud and clear, Commander! You said: **\"{prompt}\"**.\n\n"
                    f"> 🛡️ **Watchdog Notice:** A background sub-service encountered `{raw_err_msg}` at `{culprit_file}`. "
                    f"The Watchdog automatically intercepted it so our conversation and voice link stay online, and prepared a 1-click correction below!"
                )

            spoken = AgentCrewService.build_spoken_summary(fallback_text)
            healed_res = {
                "sender": "ai",
                "text": fallback_text,
                "spoken_reply": spoken,
                "is_image": False,
                "image_data": None,
                "extracted_tasks": [
                    {
                        "title": f"🛡️ Watchdog Fix: Patch {type(watchdog_exc).__name__} in {culprit_file}",
                        "category": "fix",
                        "target_file": culprit_file.split(":")[0],
                        "description": f"Watchdog caught `{raw_err_msg}` during chat processing. Apply surgical fix.",
                        "suggested_prompt": f"Fix `{raw_err_msg}` at `{culprit_file}` so chat processing never hits this error.",
                    }
                ],
                "watchdog_healed": True,
                "watchdog_diagnosis": watchdog_record,
                "antigravity_error": watchdog_record,
                "app_slug": app_slug,
                "file_path": file_path,
            }
            return cls._attach_optional_ai_voice(healed_res, voice_mode=voice_mode, include_audio=include_audio, app_slug=app_slug)

    @staticmethod
    def process_chat_message(
        prompt: str,
        app_slug: Optional[str] = None,
        file_path: Optional[str] = None,
        history: List[Dict[str, str]] = [],
        screen_frame_b64: Optional[str] = None,
        voice_mode: bool = False,
        db: Optional[Session] = None
    ) -> str:
        """Process conversational AI user message as Geppy (or Captain Geppy when inside GitBridge)."""
        context_info = ""
        app_obj = None

        # 1. Resolve any SOT Contextile @mentions (e.g. @geppybrand, @galactic-card-ui)
        sot_grounding = ""
        if db:
            mention_res = SOTService.resolve_mentions(prompt, db)
            if mention_res.get("has_mentions"):
                sot_grounding = mention_res.get("grounding_prompt", "")

        # 2. Project & Workspace Context
        if app_slug and db:
            app_obj = db.query(AppProfileModel).filter(AppProfileModel.slug == app_slug).first()
            if app_obj:
                context_info = f"ACTIVE APP CONTEXT:\n- App Name: {app_obj.name} (`{app_obj.slug}`)\n"
                context_info += f"- Status: {app_obj.status}\n- Tech Stack: {', '.join(app_obj.tech_stack or [])}\n"
                context_info += f"- Description: {app_obj.description or 'None'}\n"
                if app_obj.system_instructions:
                    context_info += f"- Core System Prompt: {app_obj.system_instructions[:500]}\n"
                if app_obj.feature_breakdown:
                    context_info += f"- Architectural Summary: {app_obj.feature_breakdown[:600]}\n"

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
                        context_info += f"\nACTIVE FILE (`{file_path}`):\n```\n{file_res['content'][:4000]}\n```\n"

        if not context_info and db:
            apps = db.query(AppProfileModel).all()
            context_info = f"REGISTERED APPS CONTEXT ({len(apps)} registered apps):\n"
            context_info += ", ".join([f"{a.name} ({a.slug})" for a in apps[:20]])

        # 3. Append SOT Grounding to Context if present
        if sot_grounding:
            context_info = f"{sot_grounding}\n\n{context_info}"

        # 4. Append active Antigravity errors if any exist
        try:
            from gitbridge.services.antigravity_service import AntigravityDaemonPool
            open_errs = [e for e in AntigravityDaemonPool.get_errors(slug=app_slug, limit=3) if e.get("status") == "open"]
            if open_errs:
                latest_err = open_errs[0]
                context_info += (
                    f"\nACTIVE ANTIGRAVITY ERROR ALERT:\n"
                    f"- Title: {latest_err.get('title')}\n"
                    f"- What the error is: {latest_err.get('what_is_the_error')}\n"
                    f"- What needs to be done: {latest_err.get('what_needs_done')}\n"
                )
        except Exception:
            pass

        # 5. Live Screen Stream frames (from GitBridge and/or Galactic)
        vision_frames, vision_note = LiveScreenStreamHub.get_active_vision_frames(
            extra_frames=[screen_frame_b64] if screen_frame_b64 else None
        )
        if vision_note:
            context_info = f"{vision_note}\n\n{context_info}"

        voice_hint = (
            "\nVOICE MODE ACTIVE: Start your response with a natural, conversational 2-3 sentence spoken summary suitable for live voice chat before any detailed code or bullet points."
            if voice_mode else ""
        )

        from gitbridge.services.central_key_service import CentralKeyService
        mstate = CentralKeyService.get_model_state()
        model_awareness = (
            f"\n- Adaptive AI Model Engine: Your current routing mode is `{mstate.get('mode')}` ({mstate.get('mode_label')}). "
            f"You can dynamically switch between `gemini-2.5-flash-lite` (instant voice/greetings), `gemini-3-flash-preview` (fast coding & live vision), "
            f"and `gemini-2.5-pro` (deep architectural reasoning & complex debugging) based on task needs, or whenever the user asks you to switch models."
        )

        is_gb = (not app_slug) or (app_slug.lower() in ("geppys-gitbridge", "gitbridge")) or (app_obj and "gitbridge" in app_obj.name.lower())
        if is_gb:
            system_instruction = f"""You are Captain Geppy — Commander and Face of Geppy's GitBridge!
You guide the creator on an epic journey through the vast Galaxy of Apps that AI makes possible.
Persona & Communication Style:
- Persona: Charismatic, visionary, encouraging, and razor-sharp galactic commander ("Captain Geppy here!").
- Live Screen Co-Designer: When Live Screen Stream frames are attached, you can literally SEE what the user is working on in GitBridge and Galactic — reference their visible screen layout, components, and errors directly!
- Source of Truth (SOT) Authority: When SOT Contextiles (@handle) are referenced, treat them as sacred Ground Truth baselines.
- Practicality: Always provide production-ready, beautiful code, drop-in UI solutions, and aesthetic improvements.
- Version Control & Git Savvy: You are aware of the app's local git status and modified files.{model_awareness}
- Format responses cleanly with Markdown, code fences, and bulleted action steps.{voice_hint}"""
        else:
            target_app_label = app_obj.name if app_obj else app_slug
            system_instruction = f"""You are Geppy — the friendly, upbeat, approachable AI Architect & IT Specialist co-building "{target_app_label}"!
Persona & Communication Style:
- CRITICAL IDENTITY RULE: Your name is simply "Geppy" — NEVER "Captain Geppy" or "Galactic Commander" ("Captain Geppy" is ONLY your persona inside the GitBridge app itself). In "{target_app_label}" and all other apps, you are strictly "Geppy". Never refer to yourself as Captain Geppy or inject "Captain Geppy" into code, UI text, or assets for "{target_app_label}".
- Persona: Friendly, patient, upbeat, and dependable ("Geppy here!").
- Live Screen Co-Designer: When Live Screen Stream frames are attached, you can literally SEE what the user is working on in real time — comment on what is visible on their screen and help them design live!
- Source of Truth (SOT) Authority: When SOT Contextiles (@handle) are referenced, use their exact visual descriptors, lighting, and modifiers.
- Practicality: Always provide production-ready, clean code and UI solutions tailored specifically to "{target_app_label}".
- Version Control & Git Savvy: You are aware of the app's local git status and modified files.{model_awareness}
- Format responses cleanly with Markdown, code fences, and bulleted action steps.{voice_hint}"""

        messages = []
        for h in history[-8:]:
            role = "user" if h.get("sender") == "user" else "model"
            messages.append({"role": role, "parts": [{"text": h.get("text", "")}]})

        messages.append({
            "role": "user",
            "parts": [{"text": f"Workspace Context:\n{context_info}\n\nUser Message / Request:\n{prompt}"}]
        })

        ai_response = CentralKeyService.call_gemini(
            messages,
            system_instruction,
            timeout=25,
            images_b64=vision_frames if vision_frames else None,
            task_hint="voice_chat" if voice_mode else "chat",
        )
        if ai_response:
            return ai_response

        # Fallback Engine if API fails
        app_name = app_obj.name if app_obj else "Geppy's GitBridge"
        heading_name = "Captain Geppy" if is_gb else "Geppy"
        return f"""### ✨ {heading_name} Reporting In! ({app_name})

I've analyzed your request regarding **{app_name}**:

> "{prompt}"

{sot_grounding}

#### 🚀 Next Actions:
1. **Architectural Scan**: Ensure dependencies in `{app_obj.local_path if app_obj else 'd:\\Geppy_Apps'}` are calibrated and synced.
2. **Interactive Live Editing**: Select components from the file tree on the left to edit files live.
3. **SOT Engine Grounding**: Reference any saved Contextile with `@name` (e.g. `@geppybrand`) for instant ground-truth alignment."""

