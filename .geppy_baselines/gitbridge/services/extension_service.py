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

from gitbridge.services.central_key_service import CentralKeyService

GEMINI_MODELS = ["gemini-2.5-flash", "gemini-3.8-flash"]

def call_gemini(messages: List[Dict[str, Any]], system_instruction: str, images_b64: Optional[List[str]] = None) -> Optional[str]:
    """Delegate to CentralKeyService for Gemini execution with robust fallback and optional multimodal vision frames."""
    return CentralKeyService.call_gemini(messages, system_instruction, images_b64=images_b64)


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

        # 2. Match GitBridge itself (port 8000 on localhost / 127.0.0.1)
        if port == 8000 or (hostname in ["localhost", "127.0.0.1"] and port == 8000):
            gb_app = db.query(AppProfileModel).filter(AppProfileModel.slug == "geppys-gitbridge").first()
            if gb_app:
                if gb_app.live_url != f"http://localhost:{port}":
                    gb_app.live_url = f"http://localhost:{port}"
                    db.commit()
                return {"slug": gb_app.slug, "name": gb_app.name, "match_type": "gitbridge_server", "live_url": gb_app.live_url}

        # 3. Match by live_url in database
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
    def associate_app_url(slug: str, url: str, db: Session) -> Dict[str, Any]:
        """Associate a live browser tab URL / port with an application profile and mark it live."""
        app = db.query(AppProfileModel).filter(AppProfileModel.slug == slug).first()
        if not app:
            return {"success": False, "message": f"App '{slug}' not found"}

        clean_url = url.strip()
        app.live_url = clean_url
        db.commit()
        db.refresh(app)
        return {
            "success": True,
            "slug": app.slug,
            "name": app.name,
            "live_url": app.live_url,
            "message": f"Successfully linked {app.name} to {clean_url}"
        }

    @staticmethod
    def resolve_best_target_file(
        app_obj: Optional[AppProfileModel],
        instruction: str,
        requested_file_path: Optional[str] = None
    ) -> str:
        """
        Intelligently determine which file in the app's repository should be edited for a given instruction.
        Prevents accidentally editing a root index.html shell when the logic lives in js/physics.js, src/App.tsx, etc.
        """
        if not app_obj:
            return requested_file_path or "index.html"

        files = WorkspaceService.get_app_file_tree(app_obj)
        paths = [f.get("path") for f in (files or []) if f.get("path")]
        if not paths:
            return requested_file_path or "index.html"

        text = (instruction or "").strip()
        text_lower = text.lower()
        req_norm = (requested_file_path or "").replace("\\", "/").strip()

        # 1. Explicit full relative path mentioned in instruction (longest match first)
        for p in sorted(paths, key=len, reverse=True):
            if p.lower() == "index.html" and any(x.lower().endswith("static/index.html") for x in paths):
                continue
            if p.lower() in text_lower:
                return p

        # 2. Explicit filename (basename) mentioned in instruction (e.g. "App.tsx", "physics.js", "server.js")
        for p in sorted(paths, key=len, reverse=True):
            base = os.path.basename(p).lower()
            if base == "index.html":
                if "index.html" not in text_lower:
                    continue
                static_html = next((x for x in paths if x.lower().endswith("static/index.html")), None)
                if static_html:
                    return static_html
            if re.search(r"(?<![a-z0-9_/-])" + re.escape(base) + r"(?![a-z0-9_])", text_lower):
                return p

        # 3. If requested_file_path is explicitly a non-HTML file that exists in paths, verify if it's already specific
        #    (unless another file's stem is strongly named in the instruction)
        stop_words = {
            "the", "and", "for", "with", "that", "this", "from", "into", "when", "what", "where",
            "make", "add", "update", "change", "fix", "step", "task", "implement", "increase",
            "decrease", "reduce", "improve", "create", "ensure", "should", "will", "long", "time",
            "does", "doesn", "not", "all", "app", "application", "page", "mode", "user", "using",
            "more", "less", "very", "too", "can", "use", "set", "new", "current", "default"
        }
        tokens = [
            w for w in re.findall(r"[a-z][a-z0-9_]{2,}", text_lower)
            if w not in stop_words
        ]
        if not tokens:
            return req_norm if req_norm in paths else paths[0]

        # Read candidate files (up to 25 code files) to score both filename stems and actual code symbols/contents
        content_cache: Dict[str, str] = {}
        for p in paths[:28]:
            ext = os.path.splitext(p)[1].lower()
            if ext in (".js", ".jsx", ".ts", ".tsx", ".vue", ".svelte", ".py", ".css", ".scss", ".html"):
                res = WorkspaceService.read_app_file(app_obj, p)
                if res.get("success") and res.get("content"):
                    content_cache[p] = res["content"][:20000]

        def is_vite_or_react_shell_html(p: str) -> bool:
            if not p.lower().endswith(".html"):
                return False
            c = content_cache.get(p, "")
            if not c:
                return False
            return bool(
                len(c.splitlines()) < 65
                and ('id="root"' in c or "id='root'" in c or 'id="app"' in c)
                and ("/src/" in c or "main.tsx" in c or "main.jsx" in c)
            )

        has_dedicated_js_or_ts = any(
            os.path.splitext(p)[1].lower() in (".js", ".jsx", ".ts", ".tsx", ".vue", ".py")
            for p in paths
        )

        wants_css = bool(re.search(r"\b(css|style|stylesheet|color|theme|font|gradient|padding|margin|border|shadow|animation|hover|layout)\b", text_lower))
        wants_html_head = bool(re.search(r"\b(favicon|meta\s+tag|page\s+title|doctype|head\s+tag|link\s+rel)\b", text_lower))
        wants_logic_or_physics = bool(re.search(
            r"\b(physics|friction|damping|velocity|speed|acceleration|ball|collision|bounce|bounciness|gravity|slope|threshold|audio|sound|level|api|fetch|state|hook|handler|function|calculate|logic|stop|stopping|drag|resistance)\b",
            text_lower
        ))

        best_path = req_norm if req_norm in paths else paths[0]
        best_score = -999.0
        scores: Dict[str, float] = {}

        for p in paths:
            score = 0.0
            p_lower = p.lower()
            ext = os.path.splitext(p_lower)[1]
            stem = os.path.splitext(os.path.basename(p_lower))[0]
            dir_parts = [seg for seg in p_lower.split("/")[:-1] if seg]
            code_lower = content_cache.get(p, "").lower()

            # Penalize Vite/React shell index.html unless specifically editing head/meta/favicon
            if is_vite_or_react_shell_html(p) and not wants_html_head:
                score -= 60.0

            # If app has dedicated .js/.tsx files and prompt is about logic/physics/state, penalize plain index.html
            if p_lower.endswith("index.html") and has_dedicated_js_or_ts and wants_logic_or_physics and not wants_html_head:
                score -= 22.0

            # Stem match (e.g. "physics" in instruction matches "js/physics.js", "audio" matches "js/audio.js", "levels" matches "js/levels.js")
            if stem not in ("index", "main", "app", "style", "styles"):
                if stem in text_lower or (stem.endswith("s") and len(stem) > 4 and stem[:-1] in text_lower):
                    score += 45.0
            elif stem in ("app", "main") and ext in (".jsx", ".tsx", ".js", ".ts", ".vue", ".py"):
                score += 8.0

            # Directory segment match
            for d in dir_parts:
                if len(d) >= 3 and d in text_lower:
                    score += 8.0

            # Extension affinity
            if wants_css and ext in (".css", ".scss"):
                score += 18.0
            if wants_logic_or_physics and ext in (".js", ".jsx", ".ts", ".tsx", ".py"):
                score += 14.0

            # Content keyword overlap
            if code_lower:
                matched_tokens = 0
                for tok in set(tokens):
                    if tok in code_lower:
                        matched_tokens += 1
                        # Extra weight if token appears in a function/class/variable declaration or property in this file
                        if re.search(r"\b(let|const|var|function|class|def)\s+" + re.escape(tok) + r"\b", code_lower) or (f".{tok}" in code_lower) or (f"{tok} =" in code_lower):
                            score += 7.5
                        else:
                            score += 2.5
                if matched_tokens >= 3:
                    score += 8.0

            # Slight preference for currently requested file only when scores are otherwise tied and it's not a shell index.html
            if p == req_norm and not (p_lower.endswith("index.html") and wants_logic_or_physics and has_dedicated_js_or_ts):
                score += 4.0

            scores[p] = score
            if score > best_score:
                best_score = score
                best_path = p

        return best_path

    @staticmethod
    def maybe_rebuild_frontend_bundle(app_obj: Optional[AppProfileModel], edited_file_path: str) -> bool:
        """
        If an app serves a pre-built frontend bundle (such as `client/dist` or `dist`) and a source file under
        `client/src/` or `src/` was modified, run a fast `npm run build` so the live server serves the updated UI.
        """
        if not app_obj or not app_obj.local_path or not os.path.exists(app_obj.local_path):
            return False
        norm_rel = (edited_file_path or "").replace("\\", "/").lstrip("/")
        local_root = app_obj.local_path

        try:
            import subprocess
            # Case 1: client/src/... with client/package.json and client/dist
            if norm_rel.startswith("client/") and os.path.exists(os.path.join(local_root, "client", "package.json")) and os.path.exists(os.path.join(local_root, "client", "dist")):
                client_dir = os.path.join(local_root, "client")
                subprocess.run(
                    ["npm", "run", "build"],
                    cwd=client_dir,
                    shell=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=35
                )
                return True
            # Case 2: root src/... with root package.json and dist/index.html, where server serves dist/
            if norm_rel.startswith("src/") and os.path.exists(os.path.join(local_root, "package.json")) and os.path.exists(os.path.join(local_root, "dist", "index.html")):
                # Only rebuild if package.json has a build script and the app is not already running a Vite dev server
                pkg_path = os.path.join(local_root, "package.json")
                with open(pkg_path, "r", encoding="utf-8", errors="ignore") as f:
                    pkg_txt = f.read()
                if '"build"' in pkg_txt and os.path.exists(os.path.join(local_root, "server")):
                    subprocess.run(
                        ["npm", "run", "build"],
                        cwd=local_root,
                        shell=True,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=35
                    )
                    return True
        except Exception as e:
            print(f"[ExtensionService] Notice during frontend bundle rebuild for {app_obj.slug}: {e}")
        return False

    @staticmethod
    def brainstorm(
        slug: str,
        message: str,
        history: List[Dict[str, str]] = [],
        file_path: Optional[str] = None,
        is_image: bool = False,
        agent_id: Optional[str] = None,
        screen_frame_b64: Optional[str] = None,
        voice_mode: bool = False,
        consult_crew: bool = False,
        consult_agents: Optional[List[str]] = None,
        db: Optional[Session] = None
    ) -> Dict[str, Any]:
        """Conversational brainstorming mode that ideates, sees live screen streams, consults the Agent Crew, and curates a task backlog."""
        from gitbridge.services.chat_service import ChatService, LiveScreenStreamHub
        from gitbridge.services.agent_crew_service import AgentCrewService
        from gitbridge.services.antigravity_service import AntigravityDaemonPool

        if screen_frame_b64 and isinstance(screen_frame_b64, str) and len(screen_frame_b64) > 64:
            LiveScreenStreamHub.push_frame(
                source="galactic",
                frame_b64=screen_frame_b64,
                app_slug=slug or "",
                viewport_title=f"Galactic Live Tab ({slug or 'App'})",
            )

        if is_image or ChatService.is_image_request(message):
            img_result = ChatService.generate_chat_image(prompt=message, app_slug=slug, db=db)
            return {
                "text": img_result["text"],
                "spoken_reply": AgentCrewService.build_spoken_summary(img_result["text"]),
                "is_image": True,
                "image_data": {
                    "image_url": img_result["image_url"],
                    "title": img_result["image_title"],
                    "filename": img_result["image_filename"],
                    "color_palette": img_result["color_palette"]
                },
                "extracted_tasks": img_result.get("extracted_tasks", [])
            }

        # Check if user asked Geppy to consult with the Agent Crew (via toggle or voice/text command)
        low_msg = (message or "").lower()
        wants_crew_consult = bool(consult_crew) or any(
            kw in low_msg for kw in (
                "consult with", "consult the", "ask the crew", "ask the agents", "check with the crew",
                "check with the agents", "what do the agents think", "what does the crew think",
                "consult your crew", "consult agents"
            )
        )
        if wants_crew_consult and not agent_id:
            consult_res = AgentCrewService.consult_crew_with_geppy(
                prompt=message,
                app_slug=slug,
                file_path=file_path,
                history=history,
                agent_ids=consult_agents,
                screen_frame_b64=screen_frame_b64,
                voice_mode=voice_mode,
                db=db,
            )
            return {
                "text": consult_res.get("reply", ""),
                "reply": consult_res.get("reply", ""),
                "spoken_reply": consult_res.get("spoken_reply", ""),
                "extracted_tasks": consult_res.get("extracted_tasks", []),
                "consulted_agents": consult_res.get("consulted_agents", []),
                "live_stream_seen": consult_res.get("live_stream_seen", False),
                "antigravity_error": consult_res.get("antigravity_error"),
                "agent": {
                    "id": "geppy-crew-consult",
                    "handle": "crew",
                    "name": "🎙️ Geppy + Agent Crew Consultation",
                    "short_name": "Geppy + Crew",
                    "icon": "🤝",
                    "role": "Live Co-Design & Crew Consultation",
                    "color": "#06b6d4",
                },
                "engine": consult_res.get("engine", "geppy-crew-consultation"),
                "elapsed_ms": consult_res.get("elapsed_ms"),
            }

        # Check if a specialized Agent Crew member or Crew Council was selected or @mentioned
        det = AgentCrewService.detect_agent_from_message(message, explicit_agent_id=agent_id)
        if det["mode"] in ("single", "council"):
            if det["mode"] == "council":
                res = AgentCrewService.run_crew_council(
                    prompt=det["clean_message"],
                    app_slug=slug,
                    file_path=file_path,
                    screen_frame_b64=screen_frame_b64,
                    db=db,
                )
                agent_meta = {
                    "id": "crew-council",
                    "handle": "crew",
                    "name": "⚡ Agent Crew Council",
                    "short_name": "Crew Council",
                    "icon": "⚡",
                    "role": "Multi-Agent Council Review",
                    "color": "#f59e0b",
                }
            else:
                agent_meta = det["agent"]
                res = AgentCrewService.run_agent_mission(
                    agent_id=agent_meta["id"],
                    prompt=det["clean_message"],
                    app_slug=slug,
                    file_path=file_path,
                    history=history,
                    screen_frame_b64=screen_frame_b64,
                    db=db,
                )

            return {
                "text": res.get("reply", ""),
                "reply": res.get("reply", ""),
                "spoken_reply": res.get("spoken_reply", ""),
                "extracted_tasks": res.get("extracted_tasks", []),
                "agent": agent_meta,
                "social_kit": res.get("social_kit"),
                "deliverable": res.get("deliverable"),
                "live_stream_seen": res.get("live_stream_seen", False),
                "engine": res.get("engine", "agent-crew"),
                "elapsed_ms": res.get("elapsed_ms"),
            }

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
        project_files_list: List[str] = []
        best_relevant_file = None
        if app_obj:
            tree = WorkspaceService.get_app_file_tree(app_obj)
            project_files_list = [f.get("path") for f in (tree or []) if f.get("path")]
            if project_files_list:
                file_context += f"\nProject Files in {app_name}: {', '.join(project_files_list[:40])}\n"

            best_relevant_file = ExtensionService.resolve_best_target_file(app_obj, message, file_path)
            files_to_read = []
            if best_relevant_file:
                files_to_read.append(best_relevant_file)
            if file_path and file_path not in files_to_read:
                files_to_read.append(file_path)

            for fp in files_to_read[:2]:
                file_res = WorkspaceService.read_app_file(app_obj, fp)
                if file_res.get("success") and file_res.get("content"):
                    file_context += f"\nFile Content ({fp}):\n```\n{file_res['content'][:3500]}\n```\n"

        # Check active live screen stream frames (from Galactic and/or GitBridge)
        vision_frames, vision_note = LiveScreenStreamHub.get_active_vision_frames(
            extra_frames=[screen_frame_b64] if screen_frame_b64 else None
        )
        if vision_note:
            file_context = f"{vision_note}\n{file_context}"

        # Check active open Antigravity errors
        open_ag_errors = [e for e in AntigravityDaemonPool.get_errors(slug=slug, limit=3) if e.get("status") == "open"]
        if open_ag_errors:
            latest_err = open_ag_errors[0]
            file_context += (
                f"\nACTIVE ANTIGRAVITY ERROR ALERT:\n"
                f"- Title: {latest_err.get('title')}\n"
                f"- What the error is: {latest_err.get('what_is_the_error')}\n"
                f"- What needs to be done: {latest_err.get('what_needs_done')}\n"
            )

        is_gb = bool(slug and slug.lower() in ("geppys-gitbridge", "gitbridge")) or ("gitbridge" in app_name.lower())
        persona_name = "Captain Geppy" if is_gb else "Geppy"
        persona_role = (
            "Captain Geppy — Commander and Face of Geppy's GitBridge!"
            if is_gb
            else f"Geppy — the friendly, upbeat, and dependable AI Architect & IT Specialist co-building \"{app_name}\"!"
        )
        identity_guardrail = (
            ""
            if is_gb
            else f"\nCRITICAL IDENTITY RULE: In \"{app_name}\", your name is strictly \"Geppy\" — NEVER \"Captain Geppy\" or \"Galactic Commander\" (you are only Captain Geppy inside the GitBridge app). Never refer to yourself as Captain Geppy or inject 'Captain Geppy' into code, UI copy, or tasks for \"{app_name}\"."
        )
        voice_hint = (
            "\nVOICE MODE ACTIVE: Begin your response with a warm, natural 2-3 sentence conversational spoken summary suitable for live voice chat before any detailed markdown or task blocks."
            if voice_mode else ""
        )

        system_prompt = f"""You are {persona_role}
Current Application: "{app_name}"
Tech Stack: {tech_stack}
Project Description: {description}

Your mission in Brainstorm & Live Co-Design Mode is to spark creative visual ideas, striking aesthetics, smooth UX flows, bug fixes, and killer features tailored specifically to "{app_name}".
Persona: Friendly, approachable, upbeat, and razor-sharp ("{persona_name} here!").{identity_guardrail}{voice_hint}
Live Screen Vision: When Live Screen Stream frames are attached, you can literally SEE the user's current screen (both Galactic and/or GitBridge). Directly comment on the visible UI layout, colors, components, or errors you see on their screen!
Antigravity Error Awareness: If an Active Antigravity Error Alert is present or the user asks about an Antigravity error, clearly explain WHAT the error is and WHAT needs to be done to resolve it.
When Source of Truth (SOT) Contextiles are referenced (@handle), anchor all ideas and design specs strictly to those ground-truth standards.
Git & Commit Savvy: You are aware of git changes in this app. When the user asks about changes, commit messages, or syncing to GitHub, advise them they can click 'Commit & Push' in the toolbar or ask you for a commit message!

IMPORTANT INSTRUCTION FOR TASK / SERIES EXTRACTION:
Whenever you propose a series of things that need to be done (whether feature ideas, UI/UX improvements, step-by-step plans, or bug/Watchdog fixes), ALWAYS include them in a structured JSON block at the very end of your message wrapped in ```tasks ... ``` fences so the user gets a "Proceed" button to run them systematically.
CRITICAL: For each task, set `"target_file"` to the exact relative file path from the project's file list where that code actually lives (for example, `js/physics.js` for physics/friction logic, `js/app.js` for app state/controls, `src/App.tsx` for React UI, `css/styles.css` for styling — NEVER target `index.html` for JS logic that lives in `.js`/`.ts`/`.tsx` files!).
Format of the tasks block:
```tasks
[
  {{
    "title": "Short punchy step/task title",
    "category": "design" | "feature" | "ux" | "polish" | "fix",
    "target_file": "exact/relative/path/from/project.ext",
    "description": "1-sentence explanation of what this step does",
    "suggested_prompt": "Specific instruction for the AI Designer to code this step in target_file"
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

        raw_response = None
        ag_tool_steps: List[Dict[str, Any]] = []
        ag_engine = "gemini-vision-live" if vision_frames else "gemini-direct"
        ag_elapsed_ms = None
        ag_service_port = None

        # When live screen vision frames are NOT needed, try the warm Antigravity CLI brainstorm session first;
        # when live screen vision frames ARE active, use multimodal Gemini directly so Geppy can literally see the screen pixels!
        if not vision_frames and app_obj and app_obj.local_path and os.path.exists(app_obj.local_path):
            try:
                from gitbridge.services.antigravity_service import AntigravityService
                ag_res = AntigravityService.run_agent_brainstorm(
                    app_obj=app_obj,
                    message=message,
                    history=history,
                    file_path=file_path,
                    sot_grounding=sot_grounding,
                    project_files_list=project_files_list,
                    best_file=best_relevant_file if app_obj else None,
                )
                if ag_res and ag_res.get("raw_response"):
                    raw_response = ag_res["raw_response"]
                    ag_tool_steps = ag_res.get("tool_steps", [])
                    ag_engine = ag_res.get("engine", "google-antigravity-service")
                    ag_elapsed_ms = ag_res.get("elapsed_ms")
                    ag_service_port = ag_res.get("service_port")
            except Exception as ag_err:
                print(f"[ExtensionService] Antigravity brainstorm fallback notice: {ag_err}")

        if not raw_response:
            raw_response = call_gemini(gemini_messages, system_prompt, images_b64=vision_frames if vision_frames else None)

        extracted_tasks = []
        clean_text = raw_response or ""

        if raw_response:
            # Match ```tasks [ ... ] ```, ```json [ ... ] ```, or ``` [ ... ] ``` blocks containing task objects
            fence_pattern = re.compile(r"```(?:tasks|json)?\s*(\[\s*\{[\s\S]*?\}\s*\])\s*```", re.IGNORECASE)
            fence_match = fence_pattern.search(raw_response)
            if fence_match:
                try:
                    candidate_list = json.loads(fence_match.group(1))
                    if isinstance(candidate_list, list) and any(
                        isinstance(item, dict) and (item.get("title") or item.get("suggested_prompt"))
                        for item in candidate_list
                    ):
                        extracted_tasks = candidate_list
                        clean_text = (raw_response[:fence_match.start()] + raw_response[fence_match.end():]).strip()
                except Exception as e:
                    print(f"[ExtensionService] Task JSON fence extraction failed: {e}")

        # Fallback: if Gemini produced a numbered/bulleted series of 2+ actionable items without a JSON fence, extract them automatically
        if not extracted_tasks and clean_text:
            fallback_items = []
            for m in re.finditer(r"(?:^|\n)\s*(?:\d+[\.\)]|[-*•])\s*\*\*([^*:\n]{3,80}):?\*\*[:\s—–-]*(.+?)(?=\n\s*(?:\d+[\.\)]|[-*•]|\n|#|$))", clean_text, re.DOTALL):
                t_title = m.group(1).strip().rstrip(":")
                t_desc = re.sub(r"\s+", " ", m.group(2).strip())
                if t_title and len(t_desc) > 8:
                    cat = "fix" if re.search(r"\b(fix|error|bug|crash|freeze|watchdog|resolve|patch)\b", f"{t_title} {t_desc}", re.I) else "feature"
                    fallback_items.append({
                        "title": t_title[:75],
                        "category": cat,
                        "description": t_desc[:200],
                        "suggested_prompt": f"{t_title}: {t_desc[:300]}"
                    })
            if len(fallback_items) >= 2:
                extracted_tasks = fallback_items[:10]

        # Ensure every extracted task has an accurate target_file resolved against the project's actual file tree
        if app_obj and extracted_tasks:
            for t in extracted_tasks:
                if isinstance(t, dict):
                    combined_task_text = f"{t.get('title', '')} {t.get('description', '')} {t.get('suggested_prompt', '')} {message}"
                    req_tf = t.get("target_file")
                    if req_tf and req_tf in project_files_list and not req_tf.lower().endswith("index.html"):
                        t["target_file"] = req_tf
                    else:
                        t["target_file"] = ExtensionService.resolve_best_target_file(
                            app_obj,
                            combined_task_text,
                            req_tf or file_path
                        )

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

        latest_open_err = [e for e in AntigravityDaemonPool.get_errors(slug=slug, limit=3) if e.get("status") == "open"]
        return {
            "text": clean_text,
            "spoken_reply": AgentCrewService.build_spoken_summary(clean_text),
            "extracted_tasks": extracted_tasks,
            "live_stream_seen": len(vision_frames) > 0,
            "antigravity_error": latest_open_err[0] if latest_open_err else None,
            "engine": ag_engine,
            "service_port": ag_service_port,
            "elapsed_ms": ag_elapsed_ms,
            "tool_steps": ag_tool_steps
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
    def _extract_relevant_file_context(current_code: str, instruction: str, max_chars: int = 52000) -> str:
        """For very large files, return either the full file (if <= max_chars) or the most relevant line windows."""
        if len(current_code) <= max_chars:
            return current_code

        lines = current_code.splitlines()
        total_lines = len(lines)
        # Extract meaningful keywords from instruction
        words = [
            w.lower()
            for w in re.findall(r"[A-Za-z_][A-Za-z0-9_\-]{2,}", instruction or "")
            if w.lower() not in {
                "fix", "runtime", "error", "details", "the", "and", "for", "with", "that", "this",
                "from", "into", "when", "ensure", "handler", "async", "operation", "non", "blocking",
                "proper", "try", "catch", "handling", "resolves", "root", "cause", "cleanly",
                "update", "add", "change", "make", "code", "file", "app", "main", "thread", "hang",
                "stalled", "freeze", "button", "click", "interacting", "implement", "design"
            }
        ]

        scored_windows = []
        window_size = 90
        step = 45
        for start in range(0, total_lines, step):
            end = min(total_lines, start + window_size)
            chunk_text = "\n".join(lines[start:end]).lower()
            score = sum(3 if w in chunk_text else 0 for w in set(words))
            if score > 0:
                scored_windows.append((score, start, end))

        scored_windows.sort(key=lambda x: (-x[0], x[1]))
        selected_ranges = [(0, min(total_lines, 110))]
        for _, s, e in scored_windows[:5]:
            selected_ranges.append((max(0, s - 15), min(total_lines, e + 15)))
        selected_ranges.append((max(0, total_lines - 110), total_lines))

        # Merge overlapping line ranges
        selected_ranges.sort(key=lambda r: r[0])
        merged = []
        for rng in selected_ranges:
            if not merged or rng[0] > merged[-1][1]:
                merged.append([rng[0], rng[1]])
            else:
                merged[-1][1] = max(merged[-1][1], rng[1])

        excerpts = []
        used_chars = 0
        for s, e in merged:
            snippet = "\n".join(lines[s:e])
            header = f"# --- [File Excerpt: lines {s + 1} to {e} of {total_lines}] ---\n"
            if used_chars + len(snippet) > max_chars:
                break
            excerpts.append(header + snippet)
            used_chars += len(snippet)

        return "\n\n".join(excerpts)

    @staticmethod
    def _apply_search_replace_blocks(original_code: str, raw_response: str) -> Optional[str]:
        """Parse <<<<<<< SEARCH ... ======= ... >>>>>>> REPLACE blocks and apply them to original_code."""
        pattern = re.compile(
            r"<{5,9}\s*SEARCH[^\n]*\n(.*?)\n={5,9}\s*\n(.*?)\n>{5,9}\s*REPLACE",
            re.DOTALL
        )
        matches = pattern.findall(raw_response or "")
        if not matches:
            return None

        updated = original_code
        applied_any = False

        for search_block, replace_block in matches:
            search_clean = search_block.strip("\r\n")
            replace_clean = replace_block.strip("\r\n")
            if not search_clean:
                continue

            # 1. Exact substring match
            if search_clean in updated:
                updated = updated.replace(search_clean, replace_clean, 1)
                applied_any = True
                continue

            # 2. Line-by-line trimmed match fallback (handles minor indentation/CRLF differences)
            orig_lines = updated.splitlines()
            search_lines = [ln.strip() for ln in search_clean.splitlines() if ln.strip()]
            if not search_lines:
                continue

            # Locate contiguous sequence of lines whose stripped content matches search_lines
            s_len = len(search_clean.splitlines())
            raw_search_lines = [ln.rstrip("\r") for ln in search_clean.splitlines()]
            found_idx = -1
            for i in range(len(orig_lines) - s_len + 1):
                if all(orig_lines[i + j].strip() == raw_search_lines[j].strip() for j in range(s_len)):
                    found_idx = i
                    break

            if found_idx != -1:
                new_lines = orig_lines[:found_idx] + replace_clean.splitlines() + orig_lines[found_idx + s_len:]
                updated = "\n".join(new_lines)
                if original_code.endswith("\n") and not updated.endswith("\n"):
                    updated += "\n"
                applied_any = True

        return updated if applied_any else None

    @staticmethod
    def _apply_surgical_patch(
        app_name: str,
        file_path: str,
        current_code: str,
        instruction: str,
        sot_grounding: str,
        identity_rule: str
    ) -> Optional[Dict[str, Any]]:
        """Apply targeted SEARCH/REPLACE blocks on large files so output token limits never truncate the file."""
        context_code = ExtensionService._extract_relevant_file_context(current_code, instruction)
        patch_system_prompt = f"""You are Geppy's Lead UI/UX & Full-Stack Engineer modifying a large file for "{app_name}".
File Path: {file_path} ({len(current_code)} chars)
Because this file is large, DO NOT output the entire file. Instead, output ONLY 1 to 4 surgical SEARCH/REPLACE blocks for the exact sections that need to be updated, followed by a brief 1-sentence EXPLANATION.

CRITICAL FORMAT:
<<<<<<< SEARCH
(exact lines copied verbatim from Current File Content, including exact indentation)
=======
(updated replacement lines)
>>>>>>> REPLACE

EXPLANATION: Brief 1-2 sentence summary of what you fixed or updated.

RULES:
1. Every <<<<<<< SEARCH block MUST match existing lines in the file verbatim. Include 3-6 lines of surrounding context so the match is unique.
2. Preserve all existing functionality, imports, routes, and syntax.
3. Do NOT use "# ... existing code ..." placeholders inside REPLACE blocks — write complete valid code for that replaced block.{identity_rule}"""

        prompt_text = f"Instruction: {instruction}\n"
        if sot_grounding:
            prompt_text = f"{sot_grounding}\n{prompt_text}"
        prompt_text += f"\nCurrent File Content:\n```\n{context_code}\n```"

        raw = call_gemini([{"role": "user", "parts": [{"text": prompt_text}]}], patch_system_prompt)
        if not raw:
            return None

        patched = ExtensionService._apply_search_replace_blocks(current_code, raw)
        if not patched or patched == current_code:
            return None

        if file_path and file_path.lower().endswith(".py"):
            import ast
            try:
                ast.parse(patched)
            except SyntaxError:
                return None

        exp_match = re.search(r"EXPLANATION:\s*(.+)", raw, re.DOTALL | re.IGNORECASE)
        explanation = exp_match.group(1).strip() if exp_match else f"Applied targeted patch to `{file_path}`: {instruction}"
        # Strip any leftover fence markers from explanation
        explanation = re.sub(r"<+.*?REPLACE", "", explanation, flags=re.DOTALL).strip()

        return {
            "success": True,
            "modified_code": patched,
            "explanation": explanation or f"Updated `{file_path}` successfully."
        }

    @staticmethod
    def apply_design(
        slug: str,
        file_path: str,
        current_code: str,
        instruction: str,
        db: Session,
        save_to_disk: bool = True
    ) -> Dict[str, Any]:
        """Apply an AI design suggestion, brainstorm task, or user prompt to code."""
        app_obj = db.query(AppProfileModel).filter(AppProfileModel.slug == slug).first()
        app_name = app_obj.name if app_obj else slug

        # 1. Verify / resolve the best target file in the app's repository
        requested_fp = (file_path or "").replace("\\", "/").strip()
        resolved_fp = ExtensionService.resolve_best_target_file(app_obj, instruction, requested_fp) if app_obj else requested_fp
        if resolved_fp and resolved_fp != requested_fp and app_obj:
            read_res = WorkspaceService.read_app_file(app_obj, resolved_fp)
            if read_res.get("success"):
                print(f"[ExtensionService] Smart-rerouted edit from '{requested_fp}' -> '{resolved_fp}' for instruction: {instruction[:70]}")
                file_path = resolved_fp
                current_code = read_res.get("content", "")
        elif app_obj and file_path and not (current_code and current_code.strip()):
            read_res = WorkspaceService.read_app_file(app_obj, file_path)
            if read_res.get("success"):
                current_code = read_res.get("content", "")

        authoritative_baseline = current_code or ""

        def _finalize(result_payload: Dict[str, Any]) -> Dict[str, Any]:
            result_payload["target_file"] = file_path
            result_payload["baseline_code"] = authoritative_baseline
            if result_payload.get("success") and save_to_disk and app_obj and file_path and result_payload.get("modified_code"):
                save_res = WorkspaceService.save_app_file(app_obj, file_path, result_payload["modified_code"])
                rebuilt = ExtensionService.maybe_rebuild_frontend_bundle(app_obj, file_path)
                result_payload["saved_to_disk"] = bool(save_res.get("success", False))
                result_payload["rebuilt_bundle"] = rebuilt
            else:
                result_payload["saved_to_disk"] = False
            try:
                from gitbridge.services.antigravity_service import AntigravityDaemonPool
                if not result_payload.get("success") and not AntigravityDaemonPool.get_errors(slug=slug, limit=1):
                    AntigravityDaemonPool.diagnose_and_record_error(
                        raw_error=result_payload.get("explanation") or "Apply design failed",
                        source="extension-apply-design",
                        slug=slug,
                        file_path=file_path,
                        instruction=instruction,
                    )
                open_errs = [e for e in AntigravityDaemonPool.get_errors(slug=slug, limit=3) if e.get("status") == "open"]
                if open_errs:
                    result_payload["antigravity_error"] = open_errs[0]
            except Exception:
                pass
            return result_payload

        sot_grounding = ""
        if db:
            mention_res = SOTService.resolve_mentions(instruction, db)
            if mention_res.get("has_mentions"):
                sot_grounding = mention_res.get("grounding_prompt", "")

        is_gb = bool(slug and slug.lower() in ("geppys-gitbridge", "gitbridge")) or ("gitbridge" in app_name.lower())
        identity_rule = (
            ""
            if is_gb
            else f"\n5. CRITICAL IDENTITY RULE: This app is \"{app_name}\" (NOT GitBridge). Geppy is simply named \"Geppy\" — NEVER \"Captain Geppy\" or \"Galactic Commander\". Never write 'Captain Geppy' in the code, UI text, or comments unless already present and required."
        )

        # Primary Engine: Google Antigravity SDK Agent (surgical view_file + edit_file across the workspace without file-size limits!)
        if app_obj and app_obj.local_path and os.path.exists(app_obj.local_path):
            try:
                from gitbridge.services.antigravity_service import AntigravityService
                ag_edit = AntigravityService.run_agent_edit(
                    app_obj=app_obj,
                    instruction=instruction,
                    target_file_hint=file_path,
                    current_code_override=current_code if (file_path == requested_fp) else None,
                    sot_grounding=sot_grounding,
                    save_to_disk=save_to_disk
                )
                if ag_edit and ag_edit.get("success") and ag_edit.get("modified_code"):
                    return ag_edit
            except Exception as ag_err:
                print(f"[ExtensionService] Antigravity edit fallback notice: {ag_err}")

        # Fallback for large files (> 9,000 chars): use Surgical SEARCH/REPLACE Patch mode so LLM output never truncates
        if current_code and len(current_code) > 9000:
            patch_res = ExtensionService._apply_surgical_patch(
                app_name=app_name,
                file_path=file_path,
                current_code=current_code,
                instruction=instruction,
                sot_grounding=sot_grounding,
                identity_rule=identity_rule
            )
            if patch_res and patch_res.get("success"):
                return _finalize(patch_res)

        project_files_note = ""
        if app_obj:
            tree = WorkspaceService.get_app_file_tree(app_obj)
            all_paths = [f.get("path") for f in (tree or []) if f.get("path")]
            if all_paths:
                project_files_note = f"\nProject Files in {app_name}: {', '.join(all_paths[:35])}"

        system_prompt = f"""You are Geppy's Lead UI/UX & Full-Stack Engineer modifying code for "{app_name}".
File Path: {file_path}{project_files_note}
Your task is to implement the user's design/feature edit instruction with total precision directly inside `{file_path}`.
If SOT Grounding specifications are provided, follow their visual style, tokens, and aesthetic rules strictly.
CRITICAL RULES:
1. Return ONLY the complete, updated code for `{file_path}`. Do NOT wrap it in markdown commentary before or after.
2. If using markdown code block fences (```code ... ```), ensure the code inside is the complete replacement file content.
3. Preserve all existing functionality, routes, classes, methods, and logic unless specifically asked to change them.
4. Modify the real implementation in `{file_path}` (do NOT inject unused dummy globals or disconnected placeholders).{identity_rule}"""

        prompt_text = f"Instruction: {instruction}\n"
        if sot_grounding:
            prompt_text = f"{sot_grounding}\n{prompt_text}"
        if current_code and current_code.strip():
            prompt_text += f"\nCurrent File Content ({file_path}):\n```\n{current_code}\n```"
        else:
            prompt_text += f"\nTarget File: {file_path} is currently empty or a new file. Generate complete, clean, professional code from scratch for this file."

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

            # Safety guard: if full-file response was truncated on a medium/large file, fall back to surgical patch!
            if current_code and len(current_code) > 4000 and len(modified_code) < len(current_code) * 0.55:
                patch_res = ExtensionService._apply_surgical_patch(
                    app_name=app_name,
                    file_path=file_path,
                    current_code=current_code,
                    instruction=instruction,
                    sot_grounding=sot_grounding,
                    identity_rule=identity_rule
                )
                if patch_res and patch_res.get("success"):
                    return _finalize(patch_res)
                return _finalize({
                    "success": False,
                    "modified_code": current_code,
                    "explanation": "Safety guard blocked saving: AI response appeared truncated for this large file."
                })
            if file_path and file_path.lower().endswith(".py"):
                import ast
                try:
                    ast.parse(modified_code)
                except SyntaxError as syn_err:
                    patch_res = ExtensionService._apply_surgical_patch(
                        app_name=app_name,
                        file_path=file_path,
                        current_code=current_code,
                        instruction=instruction,
                        sot_grounding=sot_grounding,
                        identity_rule=identity_rule
                    )
                    if patch_res and patch_res.get("success"):
                        return _finalize(patch_res)
                    return _finalize({
                        "success": False,
                        "modified_code": current_code,
                        "explanation": f"Safety guard blocked saving truncated/invalid Python file ({syn_err})."
                    })

            return _finalize({
                "success": True,
                "modified_code": modified_code,
                "explanation": f"Successfully updated `{file_path}`: {instruction}"
            })

        return _finalize({
            "success": False,
            "modified_code": current_code,
            "explanation": "Gemini API unavailable; could not generate code transformation."
        })

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

    @staticmethod
    def get_chat_history(slug: str, db: Session) -> List[Dict[str, Any]]:
        """Retrieve brainstorm conversational chat history for an app."""
        app_obj = db.query(AppProfileModel).filter(AppProfileModel.slug == slug).first()
        if not app_obj:
            return []
        return app_obj.chat_history or []

    @staticmethod
    def save_chat_history(slug: str, history: List[Dict[str, Any]], db: Session) -> List[Dict[str, Any]]:
        """Save brainstorm conversational chat history for an app."""
        app_obj = db.query(AppProfileModel).filter(AppProfileModel.slug == slug).first()
        if not app_obj:
            return []
        app_obj.chat_history = history
        db.commit()
        db.refresh(app_obj)
        return app_obj.chat_history

    @staticmethod
    def batch_apply_design(
        slug: str,
        file_path: str,
        current_code: str,
        tasks: List[Dict[str, Any]],
        db: Session
    ) -> Dict[str, Any]:
        """Apply a batch/group of tasks sequentially to code in a single coordinated operation."""
        if not tasks:
            return {"success": False, "message": "No tasks provided in batch", "modified_code": current_code}

        task_prompts = []
        for idx, t in enumerate(tasks):
            desc = t.get("suggested_prompt") or t.get("prompt") or t.get("description") or t.get("title") or ""
            task_prompts.append(f"{idx + 1}. [{t.get('category', 'Upgrade').upper()}] {t.get('title', 'Task')}: {desc}")

        combined_instruction = "Implement the following batch of improvements together in this code:\n" + "\n".join(task_prompts)

        res = ExtensionService.apply_design(
            slug=slug,
            file_path=file_path,
            current_code=current_code,
            instruction=combined_instruction,
            db=db
        )

        return {
            "success": res.get("success", False),
            "modified_code": res.get("modified_code", current_code),
            "task_count": len(tasks),
            "applied_tasks": [t.get("id") or t.get("title") for t in tasks],
            "explanation": f"Successfully applied batch of {len(tasks)} tasks to {os.path.basename(file_path)}"
        }
