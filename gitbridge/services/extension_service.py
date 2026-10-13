import os
import re
import json
import requests
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from urllib.parse import urlparse

from gitbridge.db.models import AppProfileModel
from gitbridge.services.workspace_service import WorkspaceService
from gitbridge.services.sot_service import SOTService

GEMINI_MODELS = ["gemini-2.5-flash", "gemini-1.5-flash", "gemini-3.8-flash"]

def call_gemini(messages: List[Dict[str, Any]], system_instruction: str) -> Optional[str]:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None

    for model in GEMINI_MODELS:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
            payload = {
                "contents": messages,
                "systemInstruction": {"parts": [{"text": system_instruction}]}
            }
            res = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=25)
            if res.status_code == 200:
                data = res.json()
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts:
                        return parts[0].get("text", "").strip()
        except Exception as e:
            print(f"[ExtensionService] Gemini call failed on {model}: {e}")
            continue
    return None

class ExtensionService:

    @staticmethod
    def detect_active_app(url: str, active_servers: Dict[str, Any], db: Session) -> Optional[Dict[str, Any]]:
        """Detect which app corresponds to the given tab URL."""
        if not url:
            return None

        try:
            parsed = urlparse(url)
            port = parsed.port
            hostname = parsed.hostname
        except Exception:
            return None

        # 1. Match by active running server port
        if port and active_servers:
            for slug, s_info in active_servers.items():
                s_url = s_info.get("url", "")
                if f":{port}" in s_url:
                    app = db.query(AppProfileModel).filter(AppProfileModel.slug == slug).first()
                    if app:
                        return {"slug": app.slug, "name": app.name, "match_type": "active_port", "live_url": s_url}

        # 2. Match by live_url in database
        apps = db.query(AppProfileModel).all()
        for app in apps:
            if app.live_url:
                try:
                    app_parsed = urlparse(app.live_url)
                    if port and app_parsed.port == port:
                        return {"slug": app.slug, "name": app.name, "match_type": "configured_port", "live_url": app.live_url}
                    if app_parsed.netloc and app_parsed.netloc == parsed.netloc:
                        return {"slug": app.slug, "name": app.name, "match_type": "exact_netloc", "live_url": app.live_url}
                except Exception:
                    continue

        return None

    @staticmethod
    def brainstorm(
        slug: str,
        message: str,
        history: List[Dict[str, str]] = [],
        file_path: Optional[str] = None,
        db: Optional[Session] = None
    ) -> Dict[str, Any]:
        """Conversational brainstorming mode that ideates and curates an idea & task backlog."""
        app_obj = db.query(AppProfileModel).filter(AppProfileModel.slug == slug).first() if (slug and db) else None

        app_name = app_obj.name if app_obj else "Active Project"
        tech_stack = ", ".join(app_obj.tech_stack or []) if app_obj else "Web"
        description = app_obj.description if app_obj else ""

        # Resolve any SOT Contextile @mentions (e.g. @captain-geppy, @galactic-card-ui)
        sot_grounding = ""
        if db:
            mention_res = SOTService.resolve_mentions(message, db)
            if mention_res.get("has_mentions"):
                sot_grounding = mention_res.get("grounding_prompt", "")

        file_context = ""
        if app_obj and file_path:
            file_res = WorkspaceService.read_app_file(app_obj, file_path)
            if file_res.get("success"):
                file_context = f"\nCurrently open file ({file_path}):\n```\n{file_res['content'][:2500]}\n```\n"

        system_prompt = f"""You are Captain Geppy — Commander and Face of Geppy's Galactic!
You are co-piloting with the user through the boundless Galaxy of Apps that AI makes possible.
Current Planetary Outpost: "{app_name}"
Tech Stack: {tech_stack}
Project Description: {description}

Your mission in Brainstorm Mode is to spark visionary, interstellar visual ideas, striking aesthetics, smooth UX flows, and killer features.
Persona: Charismatic, encouraging, innovative galactic commander ("Captain Geppy here!").
When Source of Truth (SOT) Contextiles are referenced (@handle), anchor all ideas and design specs strictly to those ground-truth standards.
Git & Commit Savvy: You are aware of git changes in this app. When the user asks about changes, commit messages, or syncing to GitHub, advise them they can click 'Commit & Push' in the toolbar or ask you for a commit message!

IMPORTANT INSTRUCTION FOR TASK EXTRACTION:
Whenever you propose concrete ideas, features, or design tweaks that the user could build, also include them in a structured JSON block at the very end of your message wrapped in ```tasks ... ``` fences.
Format of the tasks block:
```tasks
[
  {{
    "title": "Short punchy task title",
    "category": "design" | "feature" | "ux" | "polish",
    "description": "1-sentence explanation of what to implement",
    "suggested_prompt": "Specific instruction for the AI Designer to code this edit"
  }}
]
```
Keep the conversational response inspiring, direct, and actionable. Keep the ```tasks block valid JSON."""

        gemini_messages = []
        for h in history[-8:]:
            role = "user" if h.get("sender") == "user" else "model"
            gemini_messages.append({"role": role, "parts": [{"text": h.get("text", "")}]})

        prompt_payload = f"Context:\nApp: {app_name}\n{sot_grounding}\n{file_context}\n\nBrainstorm prompt:\n{message}"
        gemini_messages.append({
            "role": "user",
            "parts": [{"text": prompt_payload}]
        })

        raw_response = call_gemini(gemini_messages, system_prompt)

        extracted_tasks = []
        clean_text = raw_response or ""

        if raw_response and "```tasks" in raw_response:
            try:
                parts = raw_response.split("```tasks")
                clean_text = parts[0].strip()
                json_part = parts[1].split("```")[0].strip()
                extracted_tasks = json.loads(json_part)
            except Exception as e:
                print(f"[ExtensionService] Task extraction failed: {e}")

        if not raw_response:
            clean_text = f"### 💡 Brainstorm for {app_name}\n\nHere are creative suggestions for **{app_name}**:\n\n1. **Glassmorphism & Neon Accents**: Elevate the UI with subtle blur backdrops (`backdrop-blur-md`) and glowing focus rings.\n2. **Quick Command Palette**: Add a CMD+K / Ctrl+K search bar for instant action navigation.\n3. **Micro-Interactions**: Add subtle spring-physics hover animations on interactive cards and buttons.\n4. **Adaptive Dark Mode**: Introduce a high-contrast slate-950 theme with rich accent gradients."
            extracted_tasks = [
                {
                    "title": "Add Glassmorphic Card Styling",
                    "category": "design",
                    "description": "Upgrade containers with subtle backdrop blur, glowing borders, and rounded corners.",
                    "suggested_prompt": "Refactor card containers with modern glassmorphism (backdrop-blur-md bg-slate-900/60 border border-slate-700/50)"
                },
                {
                    "title": "Add Spring Hover Animations",
                    "category": "polish",
                    "description": "Add hover lift and scale micro-interactions to buttons and cards.",
                    "suggested_prompt": "Add CSS/Tailwind hover transitions: hover:-translate-y-0.5 hover:shadow-lg transition-all duration-200"
                }
            ]

        return {
            "text": clean_text,
            "extracted_tasks": extracted_tasks
        }

    @staticmethod
    def get_proactive_suggestions(
        slug: str,
        file_path: str,
        content: str,
        db: Session
    ) -> List[Dict[str, Any]]:
        """Analyze active code file and proactively generate 3-5 concrete design & feature upgrade suggestions."""
        app_obj = db.query(AppProfileModel).filter(AppProfileModel.slug == slug).first()
        app_name = app_obj.name if app_obj else slug
        tech_stack = ", ".join(app_obj.tech_stack or []) if app_obj else "Web"

        system_prompt = f"""You are a World-Class Frontend & UI/UX Designer and Lead Architect.
You are reviewing a file from "{app_name}" (Tech stack: {tech_stack}).
File Path: {file_path}
Provide 3 to 4 PROACTIVE, highly creative, and concrete design & feature upgrade suggestions that can be immediately applied to this code.
Focus on:
1. Visual polish (Modern typography, glassmorphism, responsive spacing, gradients, dark/light themes)
2. Interactive polish (Micro-interactions, hover effects, feedback states, loaders)
3. UX & Functional upgrades (Keyboard shortcuts, empty states, search/filter, accessibility)

You MUST respond strictly with a valid JSON array of objects. Do NOT include markdown fences around the JSON if possible, or use standard ```json ... ```:
[
  {{
    "id": "sug-1",
    "title": "Short Title (e.g. Modern Glassmorphic Elevation)",
    "category": "Design" | "UX" | "Polish" | "Feature",
    "description": "2-sentence clear explanation of why this improves the app",
    "prompt": "Exact targeted prompt to give the AI code generator to apply this modification",
    "preview_badge": "e.g. Visual Upgrade, +40% Polish, Micro-interaction"
  }}
]"""

        messages = [{
            "role": "user",
            "parts": [{"text": f"Review this file content and give proactive suggestions:\n```\n{content[:4000]}\n```"}]
        }]

        raw = call_gemini(messages, system_prompt)
        if raw:
            try:
                # Strip markdown code fences if present
                clean = raw.strip()
                if clean.startswith("```json"):
                    clean = clean[7:]
                elif clean.startswith("```"):
                    clean = clean[3:]
                if clean.endswith("```"):
                    clean = clean[:-3]
                clean = clean.strip()
                suggestions = json.loads(clean)
                if isinstance(suggestions, list) and len(suggestions) > 0:
                    return suggestions
            except Exception as e:
                print(f"[ExtensionService] Parse proactive suggestions failed: {e}")

        # Intelligent fallback suggestions tailored to file type
        ext = os.path.splitext(file_path)[1].lower() if file_path else ""
        if ext in [".html", ".jsx", ".tsx", ".vue"]:
            return [
                {
                    "id": "sug-glass",
                    "title": "Glassmorphism & Depth Elevation",
                    "category": "Design",
                    "description": "Upgrade static card containers with backdrop blur, translucent dark backgrounds, and subtle hairline borders for a premium 2026 SaaS feel.",
                    "prompt": "Upgrade card containers and hero panels with modern glassmorphism styling (backdrop-blur-xl bg-slate-900/60 border border-slate-700/60 shadow-2xl).",
                    "preview_badge": "Visual Upgrade"
                },
                {
                    "id": "sug-hover",
                    "title": "Fluid Button Hover Micro-Interactions",
                    "category": "Polish",
                    "description": "Give all clickable elements smooth spring transforms, active scale bounce, and glowing hover accents.",
                    "prompt": "Add subtle micro-interactions to all primary and secondary buttons: hover:scale-[1.02] active:scale-[0.98] transition-all duration-150 with subtle glow shadow.",
                    "preview_badge": "Micro-Interaction"
                },
                {
                    "id": "sug-empty",
                    "title": "Helpful Empty & Loading States",
                    "category": "UX",
                    "description": "Add polished fallback illustrations, icon placeholders, and animated skeleton loaders when data is loading or lists are empty.",
                    "prompt": "Implement sleek animated shimmer skeleton placeholders and user-friendly empty state banners.",
                    "preview_badge": "UX Quality"
                }
            ]
        elif ext in [".css", ".scss"]:
            return [
                {
                    "id": "sug-tokens",
                    "title": "Modern Design Token System",
                    "category": "Design",
                    "description": "Add CSS custom properties for rich ambient glows, harmonious typography scales, and seamless dark-mode accents.",
                    "prompt": "Define clean CSS variables for --bg-surface, --accent-glow, --border-hairline, and fluid transitions.",
                    "preview_badge": "Design System"
                },
                {
                    "id": "sug-anim",
                    "title": "Smooth Shimmer & Pulse Keyframes",
                    "category": "Polish",
                    "description": "Add keyframe animations for ambient glow pulses and smooth fade-in transitions on loaded components.",
                    "prompt": "Add keyframe animations for @keyframes pulseGlow and @keyframes fadeInUp with smooth cubic-bezier easing.",
                    "preview_badge": "Animation"
                }
            ]
        else:
            return [
                {
                    "id": "sug-robust",
                    "title": "Add Defensive Validation & Error Handling",
                    "category": "Feature",
                    "description": "Ensure graceful handling with structured try/except blocks and informative error logs.",
                    "prompt": "Add robust error handling, defensive input verification, and clear fallback return values.",
                    "preview_badge": "Architecture"
                },
                {
                    "id": "sug-perf",
                    "title": "Response Caching & Performance Polish",
                    "category": "Polish",
                    "description": "Improve throughput and responsiveness by eliminating redundant lookups.",
                    "prompt": "Optimize execution path with lightweight caching and fast lookups.",
                    "preview_badge": "Performance"
                }
            ]

    @staticmethod
    def apply_design(
        slug: str,
        file_path: str,
        current_code: str,
        instruction: str,
        db: Session
    ) -> Dict[str, Any]:
        """Apply an AI design suggestion, brainstorm task, or user prompt to code."""
        app_obj = db.query(AppProfileModel).filter(AppProfileModel.slug == slug).first()
        app_name = app_obj.name if app_obj else slug

        sot_grounding = ""
        if db:
            mention_res = SOTService.resolve_mentions(instruction, db)
            if mention_res.get("has_mentions"):
                sot_grounding = mention_res.get("grounding_prompt", "")

        system_prompt = f"""You are Captain Geppy's Lead UI/UX & Full-Stack Engineer modifying code for "{app_name}".
File Path: {file_path}
Your task is to implement the user's design/feature edit instruction with total precision.
If SOT Grounding specifications are provided, follow their visual style, tokens, and aesthetic rules strictly.
CRITICAL RULES:
1. Return ONLY the complete, updated code. Do NOT wrap it in markdown commentary before or after.
2. If using markdown code block fences (```code ... ```), ensure the code inside is the complete replacement file content.
3. Preserve all existing functionality, routes, and logic unless specifically asked to change them.
4. Apply modern, high quality, clean code with elegant visual design."""

        prompt_text = f"Instruction: {instruction}\n"
        if sot_grounding:
            prompt_text = f"{sot_grounding}\n{prompt_text}"
        prompt_text += f"\nCurrent File Content:\n```\n{current_code}\n```"

        messages = [{
            "role": "user",
            "parts": [{"text": prompt_text}]
        }]

        raw = call_gemini(messages, system_prompt)
        if raw:
            modified_code = raw.strip()
            # Strip code fence if Gemini wrapped the full file
            lines = modified_code.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            modified_code = "\n".join(lines).strip()

            return {
                "success": True,
                "modified_code": modified_code,
                "explanation": f"Successfully applied: {instruction}"
            }

        return {
            "success": False,
            "modified_code": current_code,
            "explanation": "Gemini API unavailable; could not generate code transformation."
        }

    @staticmethod
    def get_backlog(slug: str, db: Session) -> List[Dict[str, Any]]:
        """Retrieve brainstormed tasks for an app."""
        app_obj = db.query(AppProfileModel).filter(AppProfileModel.slug == slug).first()
        if not app_obj:
            return []
        return app_obj.backlog or []

    @staticmethod
    def save_backlog(slug: str, tasks: List[Dict[str, Any]], db: Session) -> List[Dict[str, Any]]:
        """Save brainstormed tasks for an app."""
        app_obj = db.query(AppProfileModel).filter(AppProfileModel.slug == slug).first()
        if not app_obj:
            return []
        app_obj.backlog = tasks
        db.commit()
        db.refresh(app_obj)
        return app_obj.backlog
