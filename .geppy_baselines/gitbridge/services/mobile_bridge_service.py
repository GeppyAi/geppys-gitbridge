import os
import re
import csv
import io
import json
import time
import asyncio
import hashlib
import threading
import subprocess
import requests
from datetime import datetime
from typing import Dict, Any, List, Optional

from gitbridge.db.database import SessionLocal
from gitbridge.db.models import AppProfileModel
from gitbridge.services.workspace_service import WorkspaceService
from gitbridge.services.extension_service import ExtensionService
from gitbridge.services.central_key_service import CentralKeyService


class MobileBridgeService:
    """
    Watches a local synced folder (e.g. Google Drive for Desktop / _Gemini_Bridge)
    AND/OR a linked Google Doc / Google Sheet URL for app modification instructions
    written during mobile Gemini chats, and executes or queues those modifications.
    """

    _lock = threading.Lock()
    _listener_thread: Optional[threading.Thread] = None
    _stop_event = threading.Event()

    @staticmethod
    def _get_state_path() -> str:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        data_dir = os.path.join(base_dir, "db")
        os.makedirs(data_dir, exist_ok=True)
        return os.path.join(data_dir, "mobile_bridge_state.json")

    @classmethod
    def _default_watch_folder(cls) -> str:
        ws_dirs = WorkspaceService.get_workspace_dirs()
        primary = ws_dirs[0] if ws_dirs else "d:\\Geppy_Apps"
        folder = os.path.join(primary, "_Gemini_Bridge")
        os.makedirs(folder, exist_ok=True)
        return folder

    @classmethod
    def get_state(cls) -> Dict[str, Any]:
        path = cls._get_state_path()
        default_folder = cls._default_watch_folder()
        default_state = {
            "listener_enabled": True,
            "auto_run": False,  # False = Review Queue mode, True = Auto-Run mode with Git safety commit
            "poll_interval_seconds": 15,
            "watch_folder": default_folder,
            "google_doc_url": "",
            "last_checked_at": None,
            "last_doc_hash": "",
            "file_signatures": {},  # filepath -> mtime_hash
            "tasks": []  # list of task dicts
        }
        if not os.path.exists(path):
            cls.save_state(default_state)
            return default_state
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for k, v in default_state.items():
                if k not in data:
                    data[k] = v
            if not data.get("watch_folder"):
                data["watch_folder"] = default_folder
            os.makedirs(data["watch_folder"], exist_ok=True)
            return data
        except Exception as e:
            print(f"[MobileBridgeService] Error reading state: {e}")
            return default_state

    @classmethod
    def save_state(cls, state: Dict[str, Any]) -> None:
        path = cls._get_state_path()
        with cls._lock:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(state, f, indent=2, default=str)
            except Exception as e:
                print(f"[MobileBridgeService] Error saving state: {e}")

    @classmethod
    def update_config(cls, payload: Dict[str, Any]) -> Dict[str, Any]:
        state = cls.get_state()
        if "listener_enabled" in payload:
            state["listener_enabled"] = bool(payload["listener_enabled"])
        if "auto_run" in payload:
            state["auto_run"] = bool(payload["auto_run"])
        if "poll_interval_seconds" in payload:
            try:
                state["poll_interval_seconds"] = max(5, min(300, int(payload["poll_interval_seconds"])))
            except Exception:
                pass
        if "watch_folder" in payload and str(payload["watch_folder"]).strip():
            folder = os.path.abspath(str(payload["watch_folder"]).strip())
            try:
                os.makedirs(folder, exist_ok=True)
                state["watch_folder"] = folder
            except Exception as e:
                print(f"[MobileBridgeService] Could not create watch folder {folder}: {e}")
        if "google_doc_url" in payload:
            state["google_doc_url"] = str(payload["google_doc_url"] or "").strip()

        cls.save_state(state)
        cls.ensure_listener_running()
        return state

    @classmethod
    def generate_master_bridge_doc(cls, db) -> Dict[str, Any]:
        """
        Generates or refreshes the central GEMINI_UNIVERSE_BRIDGE.md inside the watched folder,
        preserving any existing Modification Queue items at the top while updating the App Universe catalog below.
        """
        from gitbridge.services.context_service import GeminiContextService

        state = cls.get_state()
        watch_folder = state["watch_folder"]
        os.makedirs(watch_folder, exist_ok=True)
        master_path = os.path.join(watch_folder, "GEMINI_UNIVERSE_BRIDGE.md")

        # Preserve existing queue lines if the file already exists
        existing_queue_block = ""
        if os.path.exists(master_path):
            try:
                with open(master_path, "r", encoding="utf-8", errors="ignore") as f:
                    raw = f.read()
                m = re.search(
                    r"(<!-- MODIFICATION_QUEUE_START -->.*?<!-- MODIFICATION_QUEUE_END -->)",
                    raw,
                    flags=re.DOTALL
                )
                if m:
                    existing_queue_block = m.group(1)
            except Exception:
                pass

        apps = db.query(AppProfileModel).filter(
            (AppProfileModel.is_hidden == False) | (AppProfileModel.is_hidden == None)
        ).all()
        slug_examples = [a.slug for a in apps[:6]] or ["geppys-gitbridge", "geppyai"]

        if not existing_queue_block:
            existing_queue_block = f"""<!-- MODIFICATION_QUEUE_START -->
## ⚡ PENDING APP MODIFICATIONS (Edit or Append Below)

> **Instructions for Mobile Gemini AI**:
> When Geppy asks to modify, fix, restyle, or add features to any app in the Universe, append a checklist item below using this exact format:
> `- [ ] **[app-slug]** (optional/target/file.ext): Detailed modification instructions for the coding agent`
>
> **Available App Slugs**: `{', '.join(slug_examples)}`
> *(Leave file path as `auto` if GitBridge should automatically locate the best file to edit.)*

### Active Queue:
- [x] **[example-slug]** (`auto`): Example completed modification item (leave checked `[x]` so it does not run).
<!-- Add new `- [ ] **[app-slug]** (auto): ...` lines directly below this comment! -->

<!-- MODIFICATION_QUEUE_END -->"""

        universe_md = GeminiContextService.generate_universe_markdown(db)

        full_doc = f"""# 🌉 Geppy's Gemini Mobile Bridge & Live Modification Doc

> **How This Works**:
> 1. Share this file (or a Google Doc / Sheet synced to `{watch_folder}`) with **Gemini on your phone**.
> 2. Discuss app ideas, UI changes, bug fixes, or new features with Gemini.
> 3. Have Gemini append new `- [ ] **[app-slug]** (auto): <instruction>` items into the **Pending App Modifications** section below (or drop a new `.md`/`.txt` note into `{watch_folder}`).
> 4. **GitBridge Listener** detects changes automatically, creates a local Git safety snapshot, applies the code modifications, and marks them `[x]`.

{existing_queue_block}

---

{universe_md}
"""
        with open(master_path, "w", encoding="utf-8") as f:
            f.write(full_doc)

        # Update file signature so generating the template itself doesn't re-trigger old items
        state = cls.get_state()
        state["file_signatures"][master_path] = cls._compute_file_hash(master_path)
        cls.save_state(state)

        return {
            "success": True,
            "filepath": master_path,
            "watch_folder": watch_folder,
            "app_count": len(apps),
            "message": f"Master Bridge Document synced to {master_path}"
        }

    @staticmethod
    def _compute_file_hash(filepath: str) -> str:
        try:
            with open(filepath, "rb") as f:
                return hashlib.sha256(f.read()).hexdigest()[:16]
        except Exception:
            return ""

    @staticmethod
    def _make_task_id(app_slug: str, instruction: str, target_file: str = "auto") -> str:
        norm = f"{app_slug.lower().strip()}|{target_file.lower().strip()}|{re.sub(r'\\s+', ' ', instruction.strip().lower())}"
        return "mod-" + hashlib.sha256(norm.encode("utf-8")).hexdigest()[:12]

    @classmethod
    def fetch_google_url_content(cls, url: str) -> Optional[str]:
        """
        Fetches text/CSV content from a shared Google Doc or Google Sheet URL.
        Supports standard browser URLs by converting them to export endpoints.
        """
        clean = (url or "").strip()
        if not clean:
            return None

        export_url = clean
        # 1. Google Docs URL -> /export?format=txt
        doc_match = re.search(r"docs\.google\.com/document/d/([a-zA-Z0-9_-]+)", clean)
        if doc_match:
            doc_id = doc_match.group(1)
            export_url = f"https://docs.google.com/document/d/{doc_id}/export?format=txt"

        # 2. Google Sheets URL -> /export?format=csv
        sheet_match = re.search(r"docs\.google\.com/spreadsheets/d/([a-zA-Z0-9_-]+)", clean)
        if sheet_match:
            sheet_id = sheet_match.group(1)
            gid_match = re.search(r"[#&?]gid=([0-9]+)", clean)
            gid_param = f"&gid={gid_match.group(1)}" if gid_match else ""
            export_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv{gid_param}"

        try:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) GitBridge/1.0"}
            res = requests.get(export_url, headers=headers, timeout=12)
            if res.status_code == 200 and res.text:
                # Guard against Google sign-in HTML page when doc isn't shared as 'Anyone with link'
                if "<!DOCTYPE html>" in res.text[:300] and "accounts.google.com" in res.text[:2000]:
                    raise ValueError(
                        "Google Doc/Sheet requires sign-in. In Google Docs/Sheets, click Share -> 'Anyone with the link' (Viewer) so GitBridge can read it."
                    )
                return res.text
        except ValueError:
            raise
        except Exception as e:
            print(f"[MobileBridgeService] Error fetching Google URL {clean}: {e}")
        return None

    @classmethod
    def parse_modifications_from_text(
        cls,
        content: str,
        source_label: str,
        known_apps: List[AppProfileModel],
        filename_hint: str = ""
    ) -> List[Dict[str, Any]]:
        """
        Extracts pending modification tasks from:
        1. Structured Markdown checklist lines:
           - [ ] **[app-slug]** (`file_path`): Instruction
           - [ ] [app-slug] Instruction
           - [ ] **App Name**: Instruction
        2. CSV / Google Sheet rows:
           App | File | Instruction | Status
        3. Per-app modification files (e.g. `geppyai.md` or `geppyai-mods.txt`)
        """
        discovered: List[Dict[str, Any]] = []
        if not content or not content.strip():
            return discovered

        # Build lookup map of app slugs & names
        slug_map: Dict[str, str] = {}
        for a in known_apps:
            slug_map[a.slug.lower()] = a.slug
            slug_map[a.name.lower()] = a.slug
            clean_n = re.sub(r"[^a-z0-9]+", "", a.name.lower())
            if clean_n:
                slug_map[clean_n] = a.slug

        def _resolve_slug(raw_app: str) -> Optional[str]:
            if not raw_app:
                return None
            cand = raw_app.strip().strip("*[]()`'\" ").lower()
            if cand in ("example-slug", "app-slug", "slug", "example"):
                return None
            if cand in slug_map:
                return slug_map[cand]
            cand_alnum = re.sub(r"[^a-z0-9]+", "", cand)
            if cand_alnum in slug_map:
                return slug_map[cand_alnum]
            # Partial match
            for k, v in slug_map.items():
                if len(cand) >= 3 and (cand in k or k in cand):
                    return v
            return re.sub(r"[^a-z0-9-]+", "-", cand).strip("-") or None

        # Detect if filename itself matches an app slug (for per-app files dropped in folder)
        inferred_app_from_file = None
        if filename_hint and "GEMINI_UNIVERSE" not in filename_hint.upper():
            stem = os.path.splitext(os.path.basename(filename_hint))[0]
            stem = re.sub(r"[-_]*(mods?|changes?|tasks?|bridge|gemini|notes?)$", "", stem, flags=re.IGNORECASE)
            inferred_app_from_file = _resolve_slug(stem)

        # Restrict to MODIFICATION_QUEUE block if present in GEMINI_UNIVERSE_BRIDGE.md
        scan_text = content
        q_match = re.search(
            r"<!-- MODIFICATION_QUEUE_START -->(.*?)<!-- MODIFICATION_QUEUE_END -->",
            content,
            flags=re.DOTALL
        )
        if q_match:
            scan_text = q_match.group(1)

        # 1. Check if content looks like CSV (from Google Sheets export)
        lines = [l for l in scan_text.splitlines() if l.strip()]
        if lines and ("," in lines[0] or "\t" in lines[0]) and any(
            h in lines[0].lower() for h in ["instruction", "modification", "prompt", "change", "task"]
        ):
            try:
                reader = csv.DictReader(io.StringIO(scan_text))
                for row in reader:
                    norm_row = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
                    status_val = norm_row.get("status", "pending").lower()
                    if status_val in ("done", "completed", "complete", "applied", "x", "[x]", "true"):
                        continue
                    raw_app = norm_row.get("app") or norm_row.get("slug") or norm_row.get("app_slug") or norm_row.get("application") or ""
                    raw_file = norm_row.get("file") or norm_row.get("file_path") or norm_row.get("target_file") or "auto"
                    instr = norm_row.get("instruction") or norm_row.get("modification") or norm_row.get("prompt") or norm_row.get("change") or norm_row.get("task") or ""
                    app_slug = _resolve_slug(raw_app) or inferred_app_from_file
                    if app_slug and instr and len(instr) > 4:
                        discovered.append({
                            "id": cls._make_task_id(app_slug, instr, raw_file or "auto"),
                            "app_slug": app_slug,
                            "target_file": raw_file or "auto",
                            "instruction": instr,
                            "source": source_label
                        })
                if discovered:
                    return discovered
            except Exception:
                pass

        # 2. Parse Markdown Checklist / Bullet lines
        # Pattern A: - [ ] **[app-slug]** (`file_path`): Instruction
        pattern_a = re.compile(
            r"^\s*[-*•]\s*(?:\[\s*\]\s*)?(?:\*\*)?\[?([a-zA-Z0-9_'’\-\s]+?)\]?(?:\*\*)?\s*(?:\(`?([^)`]+)`?\))?\s*:\s*(.+)$"
        )
        current_section_app = inferred_app_from_file

        for raw_line in scan_text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith(">") or line.startswith("<!--"):
                continue

            # Skip completed checklist items `- [x]` or `- [X]`
            if re.match(r"^[-*•]\s*\[[xX✓✔]\]", line):
                continue

            # Track headings like `### GeppyAi` or `## App: geppys-gitbridge`
            if line.startswith("#"):
                hdr_text = re.sub(r"^#+\s*(?:app\s*:\s*)?", "", line, flags=re.IGNORECASE).strip()
                resolved_hdr = _resolve_slug(hdr_text)
                if resolved_hdr and resolved_hdr in slug_map.values():
                    current_section_app = resolved_hdr
                continue

            # Only parse unchecked checklist items `- [ ] ...` in the master doc, or bullets in dedicated notes
            is_unchecked_box = bool(re.match(r"^[-*•]\s*\[\s*\]", line))
            if q_match and not is_unchecked_box:
                continue

            m_a = pattern_a.match(line)
            if m_a:
                cand_app, cand_file, instr = m_a.group(1), (m_a.group(2) or "auto").strip(), m_a.group(3).strip()
                app_slug = _resolve_slug(cand_app)
                if app_slug and instr and len(instr) > 4:
                    discovered.append({
                        "id": cls._make_task_id(app_slug, instr, cand_file),
                        "app_slug": app_slug,
                        "target_file": cand_file,
                        "instruction": instr,
                        "source": source_label,
                        "raw_line": raw_line
                    })
                    continue

            # If we are inside an app section or a per-app file, accept `- [ ] Instruction` or `- Instruction`
            if current_section_app and (is_unchecked_box or (not q_match and line.startswith(("-", "*", "•")))):
                clean_instr = re.sub(r"^[-*•]\s*(?:\[\s*\]\s*)?", "", line).strip()
                if len(clean_instr) > 5:
                    discovered.append({
                        "id": cls._make_task_id(current_section_app, clean_instr, "auto"),
                        "app_slug": current_section_app,
                        "target_file": "auto",
                        "instruction": clean_instr,
                        "source": source_label,
                        "raw_line": raw_line
                    })

        return discovered

    @classmethod
    def select_best_target_file(cls, app_obj: AppProfileModel, instruction: str) -> Optional[str]:
        """
        Automatically chooses the best file to modify inside `app_obj` when target_file is 'auto'.
        """
        files = WorkspaceService.get_app_file_tree(app_obj)
        if not files:
            return None

        # Filter to editable source files
        code_exts = (".html", ".tsx", ".jsx", ".ts", ".js", ".py", ".css", ".vue", ".svelte")
        code_files = [f for f in files if f.lower().endswith(code_exts)]
        if not code_files:
            return files[0]
        if len(code_files) == 1:
            return code_files[0]

        # Ask Gemini which file in the tree best matches the modification instruction
        prompt = (
            f"App: {app_obj.name} ({app_obj.slug})\n"
            f"Modification Instruction: {instruction}\n"
            f"Available Files:\n" + "\n".join(f"- {p}" for p in code_files[:80]) + "\n\n"
            "Return ONLY the exact relative file path from the list above that should be modified for this instruction. No quotes or extra text."
        )
        try:
            picked = CentralKeyService.call_gemini(
                [{"role": "user", "parts": [{"text": prompt}]}],
                "You are an expert code router. Output only the single best file path from the provided list.",
                timeout=12
            )
            if picked:
                clean_pick = picked.strip().strip("`'\" \n\r")
                if clean_pick in code_files:
                    return clean_pick
                for cf in code_files:
                    if cf.lower() == clean_pick.lower() or cf.endswith(clean_pick):
                        return cf
        except Exception as e:
            print(f"[MobileBridgeService] File selection fallback notice: {e}")

        # Intelligent heuristic fallback (prefer static/index.html over root stub index.html)
        priority_suffixes = ["static/index.html", "public/index.html", "src/App.tsx", "src/App.jsx", "App.tsx", "App.jsx", "index.html", "main.py", "page.tsx", "index.tsx", "index.js"]
        for psuf in priority_suffixes:
            for cf in code_files:
                norm_cf = cf.replace("\\", "/").lower()
                if norm_cf == psuf.lower() or norm_cf.endswith("/" + psuf.lower()):
                    return cf
        return code_files[0]

    @classmethod
    def execute_modification(cls, task_id: str, db=None) -> Dict[str, Any]:
        """
        Executes a single modification task:
        1. Resolves the target AppProfileModel & target file
        2. Creates a pre-edit Git safety commit
        3. Runs ExtensionService.apply_design
        4. Writes updated code to disk and creates a post-edit Git commit
        5. Marks the task completed in state and in the bridge doc
        """
        close_db = False
        if db is None:
            db = SessionLocal()
            close_db = True

        try:
            state = cls.get_state()
            task = next((t for t in state.get("tasks", []) if t.get("id") == task_id), None)
            if not task:
                return {"success": False, "message": f"Task '{task_id}' not found"}

            task["status"] = "running"
            task["started_at"] = datetime.now().isoformat()
            cls.save_state(state)

            app_slug = task.get("app_slug", "")
            app_obj = db.query(AppProfileModel).filter(AppProfileModel.slug == app_slug).first()
            if not app_obj:
                # Fuzzy search
                all_apps = db.query(AppProfileModel).all()
                app_obj = next(
                    (a for a in all_apps if app_slug.lower() in a.slug.lower() or app_slug.lower() in a.name.lower()),
                    None
                )

            if not app_obj or not app_obj.local_path or not os.path.exists(app_obj.local_path):
                err_msg = f"Local workspace folder for app '{app_slug}' not found on disk."
                state = cls.get_state()
                t_ref = next((t for t in state.get("tasks", []) if t.get("id") == task_id), None)
                if t_ref:
                    t_ref["status"] = "failed"
                    t_ref["error"] = err_msg
                cls.save_state(state)
                return {"success": False, "message": err_msg}

            target_file = (task.get("target_file") or "auto").strip()
            if not target_file or target_file.lower() == "auto":
                target_file = cls.select_best_target_file(app_obj, task["instruction"])

            if not target_file:
                err_msg = f"No editable source files found in '{app_obj.name}'."
                state = cls.get_state()
                t_ref = next((t for t in state.get("tasks", []) if t.get("id") == task_id), None)
                if t_ref:
                    t_ref["status"] = "failed"
                    t_ref["error"] = err_msg
                cls.save_state(state)
                return {"success": False, "message": err_msg}

            # Read current file content
            read_res = WorkspaceService.read_app_file(app_obj, target_file)
            current_code = read_res.get("content", "") if read_res.get("success") else ""

            # 1. Create Git safety snapshot before editing
            try:
                git_dir = os.path.join(app_obj.local_path, ".git")
                if not os.path.exists(git_dir):
                    subprocess.run(["git", "init"], cwd=app_obj.local_path, capture_output=True, timeout=8)
                subprocess.run(["git", "add", "."], cwd=app_obj.local_path, capture_output=True, timeout=10)
                subprocess.run(
                    ["git", "commit", "-m", f"chore(bridge-backup): snapshot before mobile mod {task_id}"],
                    cwd=app_obj.local_path,
                    capture_output=True,
                    timeout=10
                )
            except Exception as git_err:
                print(f"[MobileBridgeService] Pre-edit git snapshot notice: {git_err}")

            # 2. Apply AI Code Modification
            apply_res = ExtensionService.apply_design(
                slug=app_obj.slug,
                file_path=target_file,
                current_code=current_code,
                instruction=task["instruction"],
                db=db
            )

            if not apply_res.get("success") or not apply_res.get("modified_code"):
                err_msg = apply_res.get("explanation") or "AI code generation did not return modified code."
                state = cls.get_state()
                t_ref = next((t for t in state.get("tasks", []) if t.get("id") == task_id), None)
                if t_ref:
                    t_ref["status"] = "failed"
                    t_ref["error"] = err_msg
                cls.save_state(state)
                return {"success": False, "message": err_msg}

            # 3. Save modified code to file
            save_res = WorkspaceService.save_app_file(app_obj, target_file, apply_res["modified_code"])
            if not save_res.get("success"):
                err_msg = save_res.get("message", "Failed to write modified code to disk.")
                state = cls.get_state()
                t_ref = next((t for t in state.get("tasks", []) if t.get("id") == task_id), None)
                if t_ref:
                    t_ref["status"] = "failed"
                    t_ref["error"] = err_msg
                cls.save_state(state)
                return {"success": False, "message": err_msg}

            # 4. Commit the applied modification locally
            commit_hash = ""
            try:
                short_instr = task["instruction"][:50].strip()
                subprocess.run(["git", "add", target_file], cwd=app_obj.local_path, capture_output=True, timeout=8)
                subprocess.run(
                    ["git", "commit", "-m", f"feat(mobile-bridge): {short_instr}"],
                    cwd=app_obj.local_path,
                    capture_output=True,
                    timeout=10
                )
                commit_hash = subprocess.run(
                    ["git", "rev-parse", "--short", "HEAD"],
                    cwd=app_obj.local_path,
                    capture_output=True,
                    text=True,
                    timeout=5
                ).stdout.strip()
            except Exception:
                pass

            # 5. Mark task as completed in local bridge markdown file if applicable
            cls._mark_checkbox_done_in_file(task)

            state = cls.get_state()
            t_ref = next((t for t in state.get("tasks", []) if t.get("id") == task_id), None)
            if t_ref:
                t_ref["status"] = "completed"
                t_ref["target_file"] = target_file
                t_ref["commit_hash"] = commit_hash
                t_ref["completed_at"] = datetime.now().isoformat()
                t_ref.pop("error", None)
            cls.save_state(state)

            return {
                "success": True,
                "task_id": task_id,
                "app_slug": app_obj.slug,
                "target_file": target_file,
                "commit_hash": commit_hash,
                "message": f"Modified '{target_file}' in {app_obj.name}" + (f" (commit {commit_hash})" if commit_hash else "")
            }
        finally:
            if close_db:
                db.close()

    @classmethod
    def _mark_checkbox_done_in_file(cls, task: Dict[str, Any]) -> None:
        """If the task came from a local Markdown file, flip `- [ ]` to `- [x]` so the doc stays in sync."""
        source_path = task.get("source_path")
        raw_line = task.get("raw_line")
        if not source_path or not os.path.exists(source_path) or not raw_line:
            return
        try:
            with open(source_path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()
            checked_line = re.sub(r"^(\s*[-*•]\s*)\[\s*\]", r"\1[x]", raw_line, count=1)
            if checked_line != raw_line and raw_line in text:
                updated_text = text.replace(raw_line, checked_line, 1)
                with open(source_path, "w", encoding="utf-8") as f:
                    f.write(updated_text)
        except Exception as e:
            print(f"[MobileBridgeService] Checkbox update notice: {e}")

    @classmethod
    def scan_for_modifications(cls, force: bool = False) -> Dict[str, Any]:
        """
        Polls both the watched local folder AND the configured Google Doc/Sheet URL
        for new modification instructions.
        """
        state = cls.get_state()
        watch_folder = state.get("watch_folder") or cls._default_watch_folder()
        os.makedirs(watch_folder, exist_ok=True)

        db = SessionLocal()
        newly_added: List[Dict[str, Any]] = []
        auto_executed: List[Dict[str, Any]] = []
        warnings: List[str] = []

        try:
            known_apps = db.query(AppProfileModel).all()
            existing_ids = {t.get("id") for t in state.get("tasks", [])}

            # Ensure GEMINI_UNIVERSE_BRIDGE.md exists in watch folder
            master_doc_path = os.path.join(watch_folder, "GEMINI_UNIVERSE_BRIDGE.md")
            if not os.path.exists(master_doc_path):
                cls.generate_master_bridge_doc(db)
                state = cls.get_state()

            # 1. Scan all .md, .txt, .csv files in watch_folder
            for entry in os.listdir(watch_folder):
                if not entry.lower().endswith((".md", ".txt", ".csv")):
                    continue
                fpath = os.path.join(watch_folder, entry)
                if not os.path.isfile(fpath):
                    continue
                fhash = cls._compute_file_hash(fpath)
                prev_hash = state.get("file_signatures", {}).get(fpath)
                if not force and prev_hash == fhash:
                    continue

                try:
                    with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                    parsed_items = cls.parse_modifications_from_text(
                        content=content,
                        source_label=f"Local File: {entry}",
                        known_apps=known_apps,
                        filename_hint=entry
                    )
                    for item in parsed_items:
                        if item["id"] not in existing_ids:
                            new_task = {
                                "id": item["id"],
                                "app_slug": item["app_slug"],
                                "target_file": item.get("target_file", "auto"),
                                "instruction": item["instruction"],
                                "source": item["source"],
                                "source_path": fpath,
                                "raw_line": item.get("raw_line", ""),
                                "status": "pending",
                                "created_at": datetime.now().isoformat()
                            }
                            state["tasks"].insert(0, new_task)
                            existing_ids.add(item["id"])
                            newly_added.append(new_task)
                    state["file_signatures"][fpath] = fhash
                except Exception as e:
                    warnings.append(f"Error reading {entry}: {e}")

            # 2. Poll Linked Google Doc / Google Sheet URL if configured
            g_url = (state.get("google_doc_url") or "").strip()
            if g_url:
                try:
                    remote_text = cls.fetch_google_url_content(g_url)
                    if remote_text:
                        r_hash = hashlib.sha256(remote_text.encode("utf-8")).hexdigest()[:16]
                        if force or r_hash != state.get("last_doc_hash"):
                            parsed_remote = cls.parse_modifications_from_text(
                                content=remote_text,
                                source_label="Linked Google Doc/Sheet",
                                known_apps=known_apps
                            )
                            for item in parsed_remote:
                                if item["id"] not in existing_ids:
                                    new_task = {
                                        "id": item["id"],
                                        "app_slug": item["app_slug"],
                                        "target_file": item.get("target_file", "auto"),
                                        "instruction": item["instruction"],
                                        "source": "Google Doc / Sheet",
                                        "status": "pending",
                                        "created_at": datetime.now().isoformat()
                                    }
                                    state["tasks"].insert(0, new_task)
                                    existing_ids.add(item["id"])
                                    newly_added.append(new_task)
                            state["last_doc_hash"] = r_hash
                except Exception as g_err:
                    warnings.append(str(g_err))

            state["last_checked_at"] = datetime.now().isoformat()
            cls.save_state(state)

            # 3. If Auto-Run is enabled, execute newly discovered pending tasks
            if state.get("auto_run") and newly_added:
                for task in newly_added:
                    res = cls.execute_modification(task["id"], db=db)
                    auto_executed.append(res)

            return {
                "success": True,
                "newly_discovered_count": len(newly_added),
                "newly_discovered": newly_added,
                "auto_executed": auto_executed,
                "warnings": warnings,
                "state": cls.get_state()
            }
        finally:
            db.close()

    @classmethod
    def add_manual_task(cls, app_slug: str, instruction: str, target_file: str = "auto", auto_execute: bool = False) -> Dict[str, Any]:
        """Allow adding or testing a modification task directly from the UI or API."""
        state = cls.get_state()
        task_id = cls._make_task_id(app_slug, instruction, target_file) + f"-{int(time.time()) % 10000}"
        new_task = {
            "id": task_id,
            "app_slug": app_slug,
            "target_file": target_file or "auto",
            "instruction": instruction,
            "source": "Bridge UI / Direct",
            "status": "pending",
            "created_at": datetime.now().isoformat()
        }
        state["tasks"].insert(0, new_task)
        cls.save_state(state)

        exec_res = None
        if auto_execute or state.get("auto_run"):
            exec_res = cls.execute_modification(task_id)

        return {
            "success": True,
            "task": new_task,
            "execution": exec_res,
            "state": cls.get_state()
        }

    @classmethod
    def delete_task(cls, task_id: str) -> Dict[str, Any]:
        state = cls.get_state()
        state["tasks"] = [t for t in state.get("tasks", []) if t.get("id") != task_id]
        cls.save_state(state)
        return {"success": True, "state": state}

    @classmethod
    def ensure_listener_running(cls) -> None:
        """Starts the background watcher daemon thread if not already alive."""
        if cls._listener_thread and cls._listener_thread.is_alive():
            return
        cls._stop_event.clear()
        cls._listener_thread = threading.Thread(
            target=cls._background_loop,
            name="GeminiMobileBridgeWatcher",
            daemon=True
        )
        cls._listener_thread.start()

    @classmethod
    def _background_loop(cls) -> None:
        while not cls._stop_event.is_set():
            try:
                state = cls.get_state()
                interval = max(5, int(state.get("poll_interval_seconds", 15)))
                if state.get("listener_enabled", True):
                    cls.scan_for_modifications(force=False)
            except Exception as e:
                print(f"[MobileBridgeService] Watcher loop notice: {e}")
                interval = 15
            cls._stop_event.wait(interval)
