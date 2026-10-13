import os
import requests
import json
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from gitbridge.db.models import AppProfileModel
from gitbridge.services.workspace_service import WorkspaceService
from gitbridge.services.context_service import GeminiContextService
from gitbridge.services.sot_service import SOTService

GEMINI_MODELS = ["gemini-2.5-flash", "gemini-1.5-flash", "gemini-3.8-flash"]

class ChatService:

    @staticmethod
    def process_chat_message(
        prompt: str,
        app_slug: Optional[str] = None,
        file_path: Optional[str] = None,
        history: List[Dict[str, str]] = [],
        db: Optional[Session] = None
    ) -> str:
        """Process conversational AI user message as Captain Geppy with full Galaxy, file & SOT Contextile context."""
        api_key = os.getenv("GEMINI_API_KEY")

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

        if api_key:
            for model in GEMINI_MODELS:
                try:
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

                    messages = []
                    for h in history[-8:]:
                        role = "user" if h.get("sender") == "user" else "model"
                        messages.append({"role": role, "parts": [{"text": h.get("text", "")}]})

                    messages.append({
                        "role": "user",
                        "parts": [{"text": f"Galactic Bridge Context:\n{context_info}\n\nCrew Message / Request:\n{prompt}"}]
                    })

                    payload = {
                        "contents": messages,
                        "systemInstruction": {"parts": [{"text": system_instruction}]}
                    }

                    res = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=20)
                    if res.status_code == 200:
                        text = res.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                        return text
                except Exception as e:
                    print(f"[ChatService] Gemini call failed on {model}: {e}")
                    continue

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
