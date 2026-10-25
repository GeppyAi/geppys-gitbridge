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
    def get_app_runtime_and_context_digest(
        app_obj: Optional[AppProfileModel],
        primary_file_path: Optional[str] = None,
        max_total_chars: int = 14000
    ) -> Dict[str, Any]:
        """
        Gather comprehensive runtime server telemetry (from ACTIVE_SERVERS), entrypoint diagnostics
        (e.g. missing index.html causing http.server directory listings), and multi-file code context
        so both Brainstorm and Edit agents have full architectural awareness in a single shot.
        """
        result = {
            "project_files": [],
            "has_html_entrypoint": False,
            "has_react_or_vite": False,
            "is_http_server_without_html": False,
            "server_info": None,
            "runtime_diagnostic": "",
            "multi_file_context": "",
            "local_path": ""
        }
        if not app_obj:
            return result

        local_path = os.path.abspath(app_obj.local_path) if (app_obj.local_path and os.path.exists(app_obj.local_path)) else ""
        result["local_path"] = local_path

        tree = WorkspaceService.get_app_file_tree(app_obj)
        project_files = [f.get("path") for f in (tree or []) if f.get("path")]
        result["project_files"] = project_files

        lower_files = [p.lower() for p in project_files]
        has_html_entrypoint = any(
            p in ("index.html", "static/index.html", "public/index.html", "src/index.html", "sidepanel.html")
            or p.endswith("/index.html")
            for p in lower_files
        )
        has_react_or_vite = any(
            p.endswith(("app.tsx", "app.jsx", "app.vue", "main.tsx", "main.jsx", "vite.config.ts", "vite.config.js"))
            for p in lower_files
        )
        result["has_html_entrypoint"] = has_html_entrypoint
        result["has_react_or_vite"] = has_react_or_vite

        # Inspect ACTIVE_SERVERS for live localhost command & port
        server_info = None
        try:
            from gitbridge.services.launcher_service import ACTIVE_SERVERS
            server_info = ACTIVE_SERVERS.get(app_obj.slug)
        except Exception:
            pass
        result["server_info"] = server_info

        diag_lines = []
        if local_path:
            diag_lines.append(f"- Local Workspace Directory (Windows OS): `{local_path}` (NEVER use Linux `/home/...` paths; use `os.path.dirname(os.path.abspath(__file__))` or `{local_path}`).")

        if server_info:
            srv_url = server_info.get("url") or f"http://localhost:{server_info.get('port')}"
            srv_cmd = server_info.get("command") or ""
            srv_port = server_info.get("port")
            diag_lines.append(f"- Active Localhost Server: Running on `{srv_url}` (Port `{srv_port}`) via command: `{srv_cmd}`")
            if "http.server" in srv_cmd.lower() and not has_html_entrypoint:
                result["is_http_server_without_html"] = True
                diag_lines.append(
                    f"- ⚠️ CRITICAL ENTRYPOINT ALERT: `{app_obj.name}` is currently served by Python's static `http.server` on `{srv_url}`, "
                    f"and there is NO `index.html` in `{local_path}`! Because `index.html` is missing, the browser only shows a raw "
                    f"`Directory listing for /` page! Creating a standalone Python script (like `dashboard.py` on port 5000) without creating "
                    f"`index.html` in the root folder will leave `{srv_url}` stuck on a directory listing. To make an HTML dashboard or UI load "
                    f"in the browser, you MUST create a complete, self-contained `index.html` in the project root (and if you also use a Flask/FastAPI "
                    f"server, ensure it serves `index.html` at `/` and uses `int(os.environ.get('PORT', {srv_port}))`)."
                )
        elif not has_html_entrypoint and not has_react_or_vite:
            result["is_http_server_without_html"] = True
            diag_lines.append(
                f"- ⚠️ ENTRYPOINT NOTICE: `{app_obj.name}` currently has NO `index.html` or web UI entrypoint (only `{', '.join(project_files[:8])}`). "
                f"When launched on localhost without `index.html`, static serving displays a raw directory listing. To provide a visual dashboard "
                f"or web UI, create `index.html` in the root directory."
            )

        # Check static assets directory (e.g. generated PNGs in static/ or assets/) so dashboard code knows exact asset filenames
        if local_path:
            for asset_sub in ("static", "assets", "public", "."):
                sub_dir = os.path.join(local_path, asset_sub) if asset_sub != "." else local_path
                if os.path.exists(sub_dir) and os.path.isdir(sub_dir):
                    try:
                        img_files = [
                            f for f in os.listdir(sub_dir)
                            if f.lower().endswith((".png", ".jpg", ".jpeg", ".svg", ".webp", ".gif", ".json"))
                            and os.path.isfile(os.path.join(sub_dir, f))
                        ]
                        if img_files:
                            prefix = f"{asset_sub}/" if asset_sub != "." else ""
                            sample_list = ", ".join(f"`{prefix}{fn}`" for fn in sorted(img_files)[:15])
                            diag_lines.append(f"- Discovered Files in `{asset_sub}/`: {sample_list}")
                    except Exception:
                        pass

        result["runtime_diagnostic"] = "\n".join(diag_lines)

        # Read up to 6 key project files so the AI sees the whole picture (especially in small/medium projects)
        priority_files: List[str] = []
        if primary_file_path and primary_file_path in project_files:
            priority_files.append(primary_file_path)
        for p in project_files:
            if p not in priority_files and os.path.splitext(p)[1].lower() in (".html", ".py", ".jsx", ".tsx", ".js", ".ts", ".vue", ".css", ".json"):
                priority_files.append(p)

        used_chars = 0
        context_blocks: List[str] = []
        for fp in priority_files[:6]:
            if used_chars >= max_total_chars:
                break
            f_res = WorkspaceService.read_app_file(app_obj, fp)
            if f_res.get("success") and f_res.get("content"):
                content_str = f_res["content"]
                budget = min(5500, max_total_chars - used_chars)
                snippet = content_str[:budget]
                context_blocks.append(f"File Content (`{fp}`):\n```\n{snippet}\n```")
                used_chars += len(snippet)

        result["multi_file_context"] = "\n\n".join(context_blocks)
        return result

    @staticmethod
    def should_auto_execute_in_chat(
        message: str,
        app_obj: Optional[AppProfileModel],
        project_files: List[str],
        is_http_server_without_html: bool = False
    ) -> bool:
        """
        Determine if a user's message in Galactic Chat is a direct build/create/edit/fix instruction
        (or a report that the dashboard/UI is still showing a directory listing / not loading) that should
        be executed and applied to disk immediately in 1 shot rather than just returning a brainstorm chat reply.
        """
        if not app_obj or not app_obj.local_path or not os.path.exists(app_obj.local_path):
            return False
        msg = (message or "").strip()
        if not msg:
            return False
        msg_lower = msg.lower()

        # Never auto-execute if user explicitly asks only to brainstorm, explain, or list ideas
        if re.search(r"^\s*(brainstorm|give\s+me\s+\d*\s*ideas|what\s+ideas|list\s+ideas|explain\s+how|what\s+is\s+this\s+app)\b", msg_lower):
            return False

        # 1. User says the app is still showing a directory listing or not loading the HTML dashboard
        if re.search(
            r"(giving\s+(me|us)\s+a\s+directory|directory\s+listing|still\s+not\s+loading|not\s+loading\s+that\s+(html\s+)?dashboard|still\s+just\s+a\s+directory|build\s+(an?\s+|the\s+)?(html\s+|web\s+)?dashboard|create\s+(an?\s+|the\s+)?(html\s+|web\s+)?dashboard|make\s+this\s+an\s+actual\s+app)",
            msg_lower
        ):
            return True

        # 2. If the app has NO index.html and the user mentions dashboard, html, ui, frontend, or page
        if is_http_server_without_html and re.search(r"\b(dashboard|html|index\.html|ui|frontend|interface|webpage|web\s+app|gallery)\b", msg_lower):
            return True

        # 3. Direct imperative build/edit/fix command in chat (e.g., "Build a...", "Create a...", "Add a...", "Fix the...", "Update the...")
        if re.search(
            r"^\s*(please\s+|can\s+you\s+|could\s+you\s+|go\s+ahead\s+and\s+|let'?s\s+)?(build|create|implement|add|update|edit|change|modify|fix|wire|replace|redesign|convert|turn\s+this\s+into)\b",
            msg_lower
        ) and not msg_lower.endswith("?"):
            return True

        return False

    @staticmethod
    def resolve_best_target_file(
        app_obj: Optional[AppProfileModel],
        instruction: str,
        requested_file_path: Optional[str] = None
    ) -> str:
        """
        Intelligently determine which file in the app's repository should be edited or created for a given instruction.
        Preserves explicit new filenames (e.g. index.html, dashboard.py, request_tile.py) when creating new files,
        and routes HTML dashboard / directory-listing fixes to index.html when no HTML entrypoint exists yet.
        """
        if not app_obj:
            return requested_file_path or "index.html"

        files = WorkspaceService.get_app_file_tree(app_obj)
        paths = [f.get("path") for f in (files or []) if f.get("path")]
        text = (instruction or "").strip()
        text_lower = text.lower()
        req_norm = (requested_file_path or "").replace("\\", "/").strip()

        lower_paths = [p.lower() for p in paths]
        has_html_entrypoint = any(
            p in ("index.html", "static/index.html", "public/index.html", "src/index.html", "sidepanel.html")
            or p.endswith("/index.html")
            for p in lower_paths
        )
        has_react_or_vite = any(
            p.endswith(("app.tsx", "app.jsx", "app.vue", "main.tsx", "main.jsx"))
            for p in lower_paths
        )

        # 0a. Check if the instruction explicitly asks to create/write a specific filename (e.g. "Create a new file named dashboard.py", "Create index.html")
        new_file_match = re.search(
            r"\b(?:create|add|write|build|named|called|file)\s+(?:a\s+)?(?:new\s+)?(?:file|script|page|template)?\s*(?:named|called)?\s*[`'\" unlocked]*([a-zA-Z0-9_./-]+\.(?:html|py|js|jsx|ts|tsx|css|json|vue))\b",
            text,
            re.IGNORECASE
        )
        if new_file_match:
            candidate_new = new_file_match.group(1).replace("\\", "/").lstrip("/")
            existing_match = next((p for p in paths if p.lower() == candidate_new.lower()), None)
            return existing_match or candidate_new

        # 0b. If the app has NO index.html (and no React/Vite UI) and the instruction is about building/loading/fixing
        #     an HTML dashboard, web UI, gallery, or fixing a "directory listing", target "index.html"!
        wants_dashboard_or_html = bool(re.search(
            r"\b(html|dashboard|index\.html|directory|ui|frontend|interface|webpage|web\s+page|web\s+app|gallery|not\s+loading|actual\s+app)\b",
            text_lower
        ))
        if not has_html_entrypoint and not has_react_or_vite and wants_dashboard_or_html:
            # Unless the instruction specifically names an existing .py file and is ONLY about backend python logic
            if not re.search(r"\b(agent_watcher\.py|request_tile\.py)\b", text_lower):
                return "index.html"

        # 0c. If requested_file_path is a valid new file path (not yet in paths) with a known code extension, honor it!
        if req_norm and not any(p.lower() == req_norm.lower() for p in paths):
            ext_req = os.path.splitext(req_norm)[1].lower()
            if ext_req in (".html", ".py", ".js", ".jsx", ".ts", ".tsx", ".css", ".scss", ".vue", ".json"):
                return req_norm

        if not paths:
            return req_norm or "index.html"

        # 1. Explicit full relative path mentioned in instruction (longest match first)
        for p in sorted(paths, key=len, reverse=True):
            if p.lower() == "index.html" and any(x.lower().endswith("static/index.html") for x in paths):
                continue
            if p.lower() in text_lower:
                return p

        # 2. Explicit filename (basename) mentioned in instruction (e.g. "App.tsx", "physics.js", "dashboard.py", "index.html")
        for p in sorted(paths, key=len, reverse=True):
            base = os.path.basename(p).lower()
            if base == "index.html":
                if "index.html" not in text_lower and not (wants_dashboard_or_html and not has_react_or_vite):
                    continue
                static_html = next((x for x in paths if x.lower().endswith("static/index.html")), None)
                if static_html:
                    return static_html
            if re.search(r"(?<![a-z0-9_/-])" + re.escape(base) + r"(?![a-z0-9_])", text_lower):
                return p

        # 2b. If index.html exists in a non-React/Vite app and the user asks about the HTML dashboard, UI, or directory listing, prefer index.html
        if wants_dashboard_or_html and not has_react_or_vite:
            html_entry = (
                next((x for x in paths if x.lower().endswith("static/index.html")), None)
                or next((x for x in paths if x.lower() == "index.html"), None)
            )
            if html_entry:
                return html_entry

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
            no_win_flag = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) if os.name == "nt" else 0
            # Case 1: client/src/... with client/package.json and client/dist
            if norm_rel.startswith("client/") and os.path.exists(os.path.join(local_root, "client", "package.json")) and os.path.exists(os.path.join(local_root, "client", "dist")):
                client_dir = os.path.join(local_root, "client")
                subprocess.run(
                    ["npm", "run", "build"],
                    cwd=client_dir,
                    shell=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=35,
                    creationflags=no_win_flag,
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
                        timeout=35,
                        creationflags=no_win_flag,
                    )
                    return True
        except Exception as e:
            print(f"[ExtensionService] Notice during frontend bundle rebuild for {app_obj.slug}: {e}")
        return False

    @staticmethod
    def format_visual_references_context(
        visual_references: Optional[List[Dict[str, Any]]] = None
    ) -> tuple[str, List[str]]:
        """
        Extract structured DOM/UI selection metadata and base64 images from user-attached
        visual references (region snips, element clicks, or full-tab screenshots).
        """
        if not visual_references or not isinstance(visual_references, list):
            return "", []

        lines = [
            "USER-SELECTED VISUAL REFERENCE(S) FROM LIVE APP VIEWPORT:",
            "(The user specifically captured/selected the following UI area(s) or DOM element(s) to reference in their request:)"
        ]
        images_b64: List[str] = []

        for idx, ref in enumerate(visual_references[:4], 1):
            if not isinstance(ref, dict):
                continue
            mode = ref.get("mode") or "selection"
            label = ref.get("label") or ("Full Screenshot" if mode == "full" else "Selected UI Region")
            selector = (ref.get("selector") or "").strip()
            tag_name = (ref.get("tag_name") or "").strip()
            elem_text = (ref.get("element_text") or "").strip()
            outer_html = (ref.get("outer_html") or "").strip()
            note = (ref.get("note") or "").strip()
            rect = ref.get("rect") or {}
            styles = ref.get("computed_styles") or {}

            rect_str = ""
            if isinstance(rect, dict) and rect.get("width") and rect.get("height"):
                rect_str = f" ({int(rect.get('width', 0))}×{int(rect.get('height', 0))}px at x={int(rect.get('x', 0))}, y={int(rect.get('y', 0))})"

            lines.append(f"  [{idx}] {label}{rect_str}")
            if selector:
                lines.append(f"      • Target DOM Selector: `{selector}`" + (f" (`<{tag_name}>`)" if tag_name else ""))
            if note:
                lines.append(f"      • User Annotation Note on Selection: \"{note}\"")
            if elem_text:
                lines.append(f"      • Visible Text Inside Selection: \"{elem_text[:260]}\"")
            if styles and isinstance(styles, dict):
                style_pairs = [f"{k}: {v}" for k, v in styles.items() if v]
                if style_pairs:
                    lines.append(f"      • Computed Styles: {', '.join(style_pairs[:8])}")
            if outer_html:
                lines.append(f"      • HTML Snippet of Selected Element:\n```html\n{outer_html[:700]}\n```")

            cropped = ref.get("cropped_b64") or ref.get("image_b64")
            full_annot = ref.get("full_annotated_b64")
            if cropped and isinstance(cropped, str) and len(cropped) > 64:
                images_b64.append(cropped)
            if full_annot and isinstance(full_annot, str) and len(full_annot) > 64 and full_annot != cropped:
                images_b64.append(full_annot)

        return "\n".join(lines), images_b64

    @staticmethod
    def brainstorm(
        slug: str,
        message: str,
        history: List[Dict[str, str]] = [],
        file_path: Optional[str] = None,
        is_image: bool = False,
        agent_id: Optional[str] = None,
        screen_frame_b64: Optional[str] = None,
        visual_references: Optional[List[Dict[str, Any]]] = None,
        voice_mode: bool = False,
        consult_crew: bool = False,
        consult_agents: Optional[List[str]] = None,
        db: Optional[Session] = None
    ) -> Dict[str, Any]:
        """Conversational brainstorming mode that ideates, sees live screen streams, consults the Agent Crew, and curates a task backlog."""
        from gitbridge.services.chat_service import ChatService, LiveScreenStreamHub
        from gitbridge.services.agent_crew_service import AgentCrewService
        from gitbridge.services.antigravity_service import AntigravityDaemonPool

        visual_ref_context, visual_ref_images = ExtensionService.format_visual_references_context(visual_references)
        primary_frame = (visual_ref_images[0] if visual_ref_images else None) or screen_frame_b64

        if primary_frame and isinstance(primary_frame, str) and len(primary_frame) > 64:
            LiveScreenStreamHub.push_frame(
                source="galactic",
                frame_b64=primary_frame,
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
        digest = ExtensionService.get_app_runtime_and_context_digest(app_obj, primary_file_path=file_path)
        if app_obj:
            project_files_list = digest["project_files"]
            if project_files_list:
                file_context += f"\nProject Files in {app_name}: {', '.join(project_files_list[:45])}\n"
            if digest.get("runtime_diagnostic"):
                file_context += f"\nRuntime & Server Architecture Diagnostics:\n{digest['runtime_diagnostic']}\n"

            best_relevant_file = ExtensionService.resolve_best_target_file(app_obj, message, file_path)
            if digest.get("multi_file_context"):
                file_context += f"\n{digest['multi_file_context']}\n"

        # Check active live screen stream frames (from Galactic and/or GitBridge) + user-selected visual reference snippets
        extra_vision_list: List[str] = []
        if visual_ref_images:
            extra_vision_list.extend(visual_ref_images)
        if screen_frame_b64 and screen_frame_b64 not in extra_vision_list:
            extra_vision_list.append(screen_frame_b64)

        vision_frames, vision_note = LiveScreenStreamHub.get_active_vision_frames(
            extra_frames=extra_vision_list if extra_vision_list else None
        )
        if visual_ref_context:
            file_context = f"\n{visual_ref_context}\n{file_context}"
        if vision_note:
            file_context = f"{vision_note}\n{file_context}"

        # Direct 1-Shot Execution from Chat: When the user explicitly asks to build/create/edit/fix something
        # or reports that the HTML dashboard is still not loading / showing a directory listing, execute it directly!
        if (
            not is_image
            and not consult_crew
            and not agent_id
            and app_obj
            and ExtensionService.should_auto_execute_in_chat(
                message=message,
                app_obj=app_obj,
                project_files=project_files_list,
                is_http_server_without_html=bool(digest.get("is_http_server_without_html")),
            )
        ):
            target_for_auto = best_relevant_file or file_path or "index.html"
            auto_edit_res = ExtensionService.apply_design(
                slug=slug,
                file_path=target_for_auto,
                current_code="",
                instruction=message,
                db=db,
                save_to_disk=True,
                visual_references=visual_references,
                screen_frame_b64=screen_frame_b64,
            )
            if auto_edit_res and auto_edit_res.get("success") and auto_edit_res.get("modified_code"):
                final_tf = auto_edit_res.get("target_file") or target_for_auto
                mod_files = auto_edit_res.get("modified_files") or [final_tf]
                explanation = auto_edit_res.get("explanation") or f"Built and applied updates to `{final_tf}`."
                files_str = ", ".join(f"`{f}`" for f in mod_files)
                reply_md = (
                    f"✅ **Done! I built and applied the update directly to {files_str}:**\n\n"
                    f"{explanation}"
                )
                return {
                    "text": reply_md,
                    "spoken_reply": AgentCrewService.build_spoken_summary(explanation),
                    "extracted_tasks": [],
                    "auto_applied": True,
                    "target_file": final_tf,
                    "modified_files": mod_files,
                    "modified_code": auto_edit_res.get("modified_code", ""),
                    "baseline_code": auto_edit_res.get("baseline_code", ""),
                    "saved_to_disk": True,
                    "live_stream_seen": len(vision_frames) > 0,
                    "antigravity_error": auto_edit_res.get("antigravity_error"),
                    "engine": auto_edit_res.get("engine", "antigravity_sdk"),
                    "service_port": auto_edit_res.get("service_port"),
                    "elapsed_ms": auto_edit_res.get("elapsed_ms"),
                    "tool_steps": auto_edit_res.get("tool_steps", []),
                }

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
CRITICAL RULES FOR `target_file` AND DASHBOARDS:
1. If the app has NO `index.html` (or is serving a directory listing via `http.server`) and you propose creating a web UI, HTML dashboard, or gallery, ALWAYS set `"target_file": "index.html"` so the browser immediately renders `index.html` at the root URL!
2. Prefer 1 comprehensive, complete step over 3-4 tiny fragmented micro-steps so the user gets a fully working feature in 1 shot!
3. When creating a new file (such as `index.html`, `dashboard.py`, `request_tile.py`), set `"target_file"` to that exact new filename. When editing existing code, set `"target_file"` to the exact relative file path where that code lives.
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

        # Ensure every extracted task has an accurate target_file resolved against the project's actual file tree (or valid new file)
        if app_obj and extracted_tasks:
            has_react_or_vite = bool(digest.get("has_react_or_vite"))
            for t in extracted_tasks:
                if isinstance(t, dict):
                    combined_task_text = f"{t.get('title', '')} {t.get('description', '')} {t.get('suggested_prompt', '')} {message}"
                    req_tf = (t.get("target_file") or "").replace("\\", "/").strip()
                    ext_tf = os.path.splitext(req_tf)[1].lower() if req_tf else ""
                    if req_tf and req_tf in project_files_list and not (req_tf.lower() == "index.html" and has_react_or_vite):
                        t["target_file"] = req_tf
                    elif req_tf and ext_tf in (".html", ".py", ".js", ".jsx", ".ts", ".tsx", ".css", ".scss", ".vue", ".json") and not (req_tf.lower() == "index.html" and has_react_or_vite):
                        # Honor valid new filename proposed by the AI (e.g. index.html, dashboard.py, request_tile.py)
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
        save_to_disk: bool = True,
        visual_references: Optional[List[Dict[str, Any]]] = None,
        screen_frame_b64: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Apply an AI design suggestion, brainstorm task, or user prompt to code."""
        app_obj = db.query(AppProfileModel).filter(AppProfileModel.slug == slug).first()
        app_name = app_obj.name if app_obj else slug

        visual_ref_context, visual_ref_images = ExtensionService.format_visual_references_context(visual_references)
        edit_images: List[str] = []
        if visual_ref_images:
            edit_images.extend(visual_ref_images)
        if screen_frame_b64 and isinstance(screen_frame_b64, str) and len(screen_frame_b64) > 64 and screen_frame_b64 not in edit_images:
            edit_images.append(screen_frame_b64)

        # 1. Verify / resolve the best target file in the app's repository (supporting both existing files and new files!)
        requested_fp = (file_path or "").replace("\\", "/").strip()
        resolved_fp = ExtensionService.resolve_best_target_file(app_obj, instruction, requested_fp) if app_obj else requested_fp
        if resolved_fp and resolved_fp != requested_fp and app_obj:
            read_res = WorkspaceService.read_app_file(app_obj, resolved_fp)
            if read_res.get("success"):
                print(f"[ExtensionService] Smart-rerouted edit from '{requested_fp}' -> '{resolved_fp}' for instruction: {instruction[:70]}")
                file_path = resolved_fp
                current_code = read_res.get("content", "")
            else:
                print(f"[ExtensionService] Smart-rerouted to new file '{resolved_fp}' (from '{requested_fp}') for instruction: {instruction[:70]}")
                file_path = resolved_fp
                current_code = ""
        elif app_obj and file_path:
            read_res = WorkspaceService.read_app_file(app_obj, file_path)
            if read_res.get("success"):
                if not (current_code and current_code.strip()):
                    current_code = read_res.get("content", "")
            else:
                # Target file does not exist on disk yet — reset current_code so another file's code is never leaked into a new file!
                current_code = ""

        authoritative_baseline = current_code or ""
        digest = ExtensionService.get_app_runtime_and_context_digest(app_obj, primary_file_path=file_path)

        def _finalize(result_payload: Dict[str, Any]) -> Dict[str, Any]:
            result_payload["target_file"] = file_path
            result_payload["baseline_code"] = authoritative_baseline
            if result_payload.get("success") and save_to_disk and app_obj and file_path and result_payload.get("modified_code"):
                save_res = WorkspaceService.save_app_file(app_obj, file_path, result_payload["modified_code"])
                rebuilt = ExtensionService.maybe_rebuild_frontend_bundle(app_obj, file_path)
                result_payload["saved_to_disk"] = bool(save_res.get("success", False))
                result_payload["rebuilt_bundle"] = rebuilt
                try:
                    from gitbridge.services.launcher_service import AppLauncherService
                    AppLauncherService.upgrade_static_server_if_needed(app_obj)
                except Exception:
                    pass
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
        if visual_ref_context:
            sot_grounding = f"{sot_grounding}\n\n{visual_ref_context}".strip()

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
                    current_code_override=current_code if (file_path == requested_fp and current_code) else None,
                    sot_grounding=sot_grounding,
                    save_to_disk=save_to_disk
                )
                if ag_edit and ag_edit.get("success") and ag_edit.get("modified_code"):
                    try:
                        from gitbridge.services.launcher_service import AppLauncherService
                        AppLauncherService.upgrade_static_server_if_needed(app_obj)
                    except Exception:
                        pass
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
        if digest.get("project_files"):
            project_files_note = f"\nProject Files in {app_name}: {', '.join(digest['project_files'][:40])}"
        if digest.get("runtime_diagnostic"):
            project_files_note += f"\nRuntime Diagnostics:\n{digest['runtime_diagnostic']}"

        system_prompt = f"""You are Geppy's Lead UI/UX & Full-Stack Engineer modifying or creating code for "{app_name}".
File Path: {file_path}{project_files_note}
Your task is to implement the user's design/feature edit instruction with total precision directly inside `{file_path}`.
If SOT Grounding specifications are provided, follow their visual style, tokens, and aesthetic rules strictly.
CRITICAL RULES:
1. Return ONLY the complete, updated code for `{file_path}`. Do NOT wrap it in markdown commentary before or after.
2. If using markdown code block fences (```code ... ```), ensure the code inside is the complete replacement file content.
3. Preserve all existing functionality, routes, classes, methods, and logic unless specifically asked to change them.
4. When building an HTML dashboard or `index.html`, generate a COMPLETE, rich, modern, interactive, self-contained HTML5 application (with clean dark-mode CSS, live data/asset fetching, interactive controls, and responsive grid) that works immediately in the browser.{identity_rule}"""

        prompt_text = f"Instruction: {instruction}\n"
        if sot_grounding:
            prompt_text = f"{sot_grounding}\n{prompt_text}"
        if digest.get("multi_file_context"):
            prompt_text += f"\nProject Context & Companion Files:\n{digest['multi_file_context']}\n"
        if current_code and current_code.strip():
            prompt_text += f"\nCurrent Target File Content ({file_path}):\n```\n{current_code}\n```"
        else:
            prompt_text += f"\nTarget File: `{file_path}` is a NEW file (or currently empty). Generate complete, rich, production-ready code from scratch for `{file_path}` that integrates seamlessly with the project files shown above."

        messages = [{
            "role": "user",
            "parts": [{"text": prompt_text}]
        }]

        raw = call_gemini(messages, system_prompt, images_b64=edit_images if edit_images else None)
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
