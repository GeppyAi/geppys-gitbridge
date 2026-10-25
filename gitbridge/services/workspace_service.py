import os
import json
import time
import threading
import subprocess
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from dotenv import load_dotenv

from gitbridge.db.models import AppProfileModel
from gitbridge.schemas.app_profile import AppStatus

load_dotenv()

_WIN_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) if os.name == "nt" else 0


def _silent_subprocess_kwargs(env: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Build subprocess kwargs that prevent any cmd.exe / git.exe console window from popping up on Windows."""
    merged_env = dict(os.environ)
    if env:
        merged_env.update(env)
    merged_env["GIT_TERMINAL_PROMPT"] = "0"
    merged_env["GCM_INTERACTIVE"] = "never"
    merged_env["GIT_ASKPASS"] = "echo"
    merged_env["SSH_ASKPASS"] = "echo"

    kwargs: Dict[str, Any] = {"env": merged_env}
    if os.name == "nt":
        kwargs["creationflags"] = _WIN_NO_WINDOW
        try:
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = 0  # SW_HIDE
            kwargs["startupinfo"] = si
        except Exception:
            pass
    return kwargs


class WorkspaceService:
    _FOLDER_CACHE: Dict[str, str] = {}
    _FOLDER_CACHE_TIME: float = 0.0
    _UPDATER_LOCK = threading.Lock()
    _UPDATER_CANCEL_EVENT = threading.Event()
    _UPDATER_STATE: Dict[str, Any] = {
        "running": False,
        "status": "idle",
        "only_changed": True,
        "total": 0,
        "processed": 0,
        "pushed": 0,
        "skipped": 0,
        "failed": 0,
        "current_app": None,
        "started_at": None,
        "finished_at": None,
        "items": [],
        "logs": []
    }

    @staticmethod
    def _run_git_silent(
        args: List[str],
        cwd: Optional[str] = None,
        timeout: int = 30,
        check: bool = False,
        env: Optional[Dict[str, str]] = None
    ) -> subprocess.CompletedProcess:
        """Execute a git command completely silently in the background with CREATE_NO_WINDOW."""
        kwargs = _silent_subprocess_kwargs(env)
        return subprocess.run(
            args,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=check,
            **kwargs
        )

    @staticmethod
    def _ensure_safe_gitignore(local_path: str) -> None:
        """Ensure a .gitignore exists in local_path so git add never hangs on node_modules or .venv."""
        if not local_path or not os.path.exists(local_path):
            return
        gitignore_path = os.path.join(local_path, ".gitignore")
        essential_ignores = [
            "node_modules/",
            ".venv/",
            "venv/",
            "__pycache__/",
            "*.pyc",
            ".env",
            ".DS_Store",
            ".tmp.driveupload/",
            ".geppy_baselines/",
            ".geppy_latest/"
        ]
        try:
            if not os.path.exists(gitignore_path):
                with open(gitignore_path, "w", encoding="utf-8") as f:
                    f.write("\n".join(essential_ignores) + "\n")
            else:
                with open(gitignore_path, "r", encoding="utf-8", errors="ignore") as f:
                    existing = f.read()
                missing = [pat for pat in ("node_modules/", ".venv/", "venv/", "__pycache__/") if pat.rstrip("/") not in existing]
                if missing:
                    with open(gitignore_path, "a", encoding="utf-8") as f:
                        f.write("\n" + "\n".join(missing) + "\n")
        except Exception:
            pass

        # Also clean up any stale .git/index.lock left behind by a previously killed git process
        lock_file = os.path.join(local_path, ".git", "index.lock")
        if os.path.exists(lock_file):
            try:
                if time.time() - os.path.getmtime(lock_file) > 15:
                    os.remove(lock_file)
            except Exception:
                pass

    @staticmethod
    def get_workspace_dirs() -> List[str]:
        """Get list of configured local workspace folder paths (defaults to ['d:\\Geppy_Apps'])."""
        raw = os.getenv("GEPPY_APPS_DIR", "d:\\Geppy_Apps").strip()
        import re
        parts = [p.strip() for p in re.split(r'[;,|\n]+', raw) if p.strip()]
        if not parts:
            parts = ["d:\\Geppy_Apps"]
        
        valid_dirs = []
        for p in parts:
            clean_p = os.path.abspath(p)
            try:
                os.makedirs(clean_p, exist_ok=True)
            except Exception:
                pass
            if clean_p not in valid_dirs:
                valid_dirs.append(clean_p)
        return valid_dirs if valid_dirs else [os.path.abspath("d:\\Geppy_Apps")]

    @staticmethod
    def get_workspace_dir() -> str:
        """Get primary or semicolon-joined workspace directories representation."""
        dirs = WorkspaceService.get_workspace_dirs()
        return "; ".join(dirs)

    @staticmethod
    def set_workspace_dir(new_paths: str) -> str:
        """Update GEPPY_APPS_DIR in .env and environment with multi-directory support."""
        import re
        parts = [p.strip() for p in re.split(r'[;,|\n]+', str(new_paths)) if p.strip()]
        clean_dirs = []
        for p in parts:
            clean_p = os.path.abspath(p)
            try:
                os.makedirs(clean_p, exist_ok=True)
            except Exception:
                pass
            if clean_p not in clean_dirs:
                clean_dirs.append(clean_p)
        
        joined_str = "; ".join(clean_dirs) if clean_dirs else os.path.abspath("d:\\Geppy_Apps")
        os.environ["GEPPY_APPS_DIR"] = joined_str

        env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
        if not os.path.exists(env_path):
            env_path = ".env"

        env_data = {}
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    if "=" in line and not line.startswith("#"):
                        k, v = line.strip().split("=", 1)
                        env_data[k] = v

        env_data["GEPPY_APPS_DIR"] = joined_str

        with open(env_path, "w", encoding="utf-8") as f:
            for k, v in env_data.items():
                f.write(f"{k}={v}\n")

        return joined_str

    @staticmethod
    def extract_git_remote_url(folder_path: str) -> Optional[str]:
        """Extract GitHub remote URL from .git/config if present."""
        git_config_path = os.path.join(folder_path, ".git", "config")
        if not os.path.exists(git_config_path):
            return None
        try:
            with open(git_config_path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("url ="):
                        url = line.split("=", 1)[1].strip()
                        if url.endswith(".git"):
                            url = url[:-4]
                        if "git@" in url:
                            url = url.replace("git@github.com:", "https://github.com/")
                        return url
        except Exception:
            pass
        return None

    @staticmethod
    def is_boilerplate_description(desc: Optional[str]) -> bool:
        """Check if description is generic Vite/template boilerplate."""
        if not desc:
            return True
        d_lower = desc.lower().strip()
        if len(d_lower) < 10:
            return True
        boilerplate_keywords = [
            "minimal setup to get react",
            "vite with hmr",
            "official plugins are available",
            "discovered local application",
            "local application located in",
            "react working in vite",
            "create react app",
            "application profile registered in geppy",
            "this template provides a minimal setup",
            "expanding the vite configuration"
        ]
        for kw in boilerplate_keywords:
            if kw in d_lower:
                return True
        return False

    @staticmethod
    def parse_local_app_context(folder_path: str) -> Dict[str, Any]:
        """Parse design docs, READMEs, metadata.json, package.json, and system prompts from local app folder to extract purpose and context."""
        context = {
            "description": None,
            "tech_stack": [],
            "system_instructions": None,
            "version": None,
            "design_notes": None
        }
        if not folder_path or not os.path.exists(folder_path):
            return context

        # 1. Check package.json
        pkg_path = os.path.join(folder_path, "package.json")
        if os.path.exists(pkg_path):
            try:
                with open(pkg_path, "r", encoding="utf-8", errors="ignore") as f:
                    pkg_data = json.load(f)
                    cand_desc = pkg_data.get("description")
                    if cand_desc and not WorkspaceService.is_boilerplate_description(cand_desc):
                        context["description"] = cand_desc.strip()
                    if pkg_data.get("version"):
                        context["version"] = pkg_data["version"].strip()
            except Exception:
                pass

        # 2. Check metadata.json (AI Studio or custom app export)
        meta_path = os.path.join(folder_path, "metadata.json")
        if os.path.exists(meta_path):
            try:
                with open(meta_path, "r", encoding="utf-8", errors="ignore") as f:
                    meta_data = json.load(f)
                    cand_desc = meta_data.get("description")
                    if not context["description"] and cand_desc and not WorkspaceService.is_boilerplate_description(cand_desc):
                        context["description"] = cand_desc.strip()
                    if meta_data.get("system_instructions") or meta_data.get("prompt"):
                        context["system_instructions"] = meta_data.get("system_instructions") or meta_data.get("prompt")
            except Exception:
                pass

        # 3. Check README.md / DESIGN.md / DESIGN_DOCUMENT.md
        doc_candidates = ["README.md", "README", "DESIGN.md", "DESIGN_DOCUMENT.md", "docs/DESIGN.md", "docs/README.md"]
        for cand in doc_candidates:
            cand_path = os.path.join(folder_path, cand)
            if os.path.exists(cand_path):
                try:
                    with open(cand_path, "r", encoding="utf-8", errors="ignore") as f:
                        lines = [line.strip() for line in f.readlines() if line.strip()]
                        if not context["description"]:
                            desc_lines = []
                            for line in lines:
                                if line.startswith("#"):
                                    continue
                                if len(line) > 15:
                                    desc_lines.append(line)
                                if len(desc_lines) >= 2:
                                    break
                            if desc_lines:
                                cand_desc = " ".join(desc_lines)[:350]
                                if not WorkspaceService.is_boilerplate_description(cand_desc):
                                    context["description"] = cand_desc
                        
                        context["design_notes"] = "\n".join(lines[:35])[:1200]
                        break
                except Exception:
                    pass

        # 4. Check for system prompt text files
        prompt_candidates = ["system_instructions.txt", "SYSTEM.md", "prompt.txt", "instructions.md"]
        for pc in prompt_candidates:
            pc_path = os.path.join(folder_path, pc)
            if os.path.exists(pc_path) and not context["system_instructions"]:
                try:
                    with open(pc_path, "r", encoding="utf-8", errors="ignore") as f:
                        context["system_instructions"] = f.read().strip()
                except Exception:
                    pass

        if context["description"] and WorkspaceService.is_boilerplate_description(context["description"]):
            context["description"] = None

        return context

    @staticmethod
    def scan_workspace_directory(db: Session) -> Dict[str, Any]:
        """Scan all configured local folders for existing apps and sync them with database."""
        workspace_dirs = WorkspaceService.get_workspace_dirs()
        new_apps_count = 0
        linked_apps_count = 0
        total_scanned_dirs = 0
        scanned_paths = []

        for workspace_dir in workspace_dirs:
            if not os.path.exists(workspace_dir):
                continue

            try:
                entries = os.listdir(workspace_dir)
            except Exception:
                continue

            total_scanned_dirs += len(entries)
            scanned_paths.append(workspace_dir)

            for entry in entries:
                folder_path = os.path.join(workspace_dir, entry)
                # Skip non-directories, dot-prefixed hidden/temp folders, virtual environments, node_modules, and git folder
                if not os.path.isdir(folder_path) or entry.startswith(".") or entry in [".venv", "venv", "node_modules", ".git", "__pycache__"]:
                    continue

                slug = entry.lower().replace("'", "").replace("’", "").replace(" ", "-").replace("_", "-").replace("--", "-").strip("-")
                alt_slug = entry.lower().replace("'", "-").replace("’", "-").replace(" ", "-").replace("_", "-").replace("--", "-").strip("-")
                name = entry.replace("-", " ").replace("_", " ").title().replace("'S", "'s")
                github_url = WorkspaceService.extract_git_remote_url(folder_path)

                tech_stack = []
                if os.path.exists(os.path.join(folder_path, "package.json")):
                    tech_stack.extend(["Node.js", "JavaScript"])
                if os.path.exists(os.path.join(folder_path, "requirements.txt")) or os.path.exists(os.path.join(folder_path, "main.py")):
                    tech_stack.extend(["Python"])

                local_ctx = WorkspaceService.parse_local_app_context(folder_path)

                existing = db.query(AppProfileModel).filter(
                    (AppProfileModel.slug == slug) | (AppProfileModel.slug == alt_slug) | (AppProfileModel.local_path == folder_path)
                ).first()
                if not existing:
                    entry_norm = WorkspaceService.normalize_slug(entry)
                    for cand in db.query(AppProfileModel).all():
                        if WorkspaceService.normalize_slug(cand.slug) == entry_norm or WorkspaceService.normalize_slug(cand.name) == entry_norm:
                            existing = cand
                            break

                from gitbridge.services.analyzer_service import AppAnalyzerService

                if existing:
                    existing.local_path = folder_path
                    if github_url and not existing.github_url:
                        existing.github_url = github_url
                    if local_ctx.get("description") and (not existing.description or WorkspaceService.is_boilerplate_description(existing.description)):
                        existing.description = local_ctx["description"]
                    if local_ctx.get("system_instructions") and not existing.system_instructions:
                        existing.system_instructions = local_ctx["system_instructions"]
                    if local_ctx.get("version") and existing.version == "0.1.0":
                        existing.version = local_ctx["version"]
                    if not getattr(existing, "category", None) or not AppAnalyzerService.normalize_category(existing.category):
                        existing.category = AppAnalyzerService.infer_app_category(
                            name=existing.name,
                            slug=existing.slug,
                            description=existing.description or "",
                            tech_stack=existing.tech_stack or tech_stack,
                            tags=existing.tags or [],
                        )
                    linked_apps_count += 1
                else:
                    desc = local_ctx.get("description")
                    if not desc or WorkspaceService.is_boilerplate_description(desc):
                        desc = f"{name} - Discovered application module in local workspace directory."
                    inferred_cat = AppAnalyzerService.infer_app_category(
                        name=name,
                        slug=slug,
                        description=desc,
                        tech_stack=tech_stack,
                    )
                    app_obj = AppProfileModel(
                        slug=slug,
                        name=name,
                        description=desc,
                        category=inferred_cat,
                        status=AppStatus.IN_DEVELOPMENT,
                        github_url=github_url,
                        local_path=folder_path,
                        system_instructions=local_ctx.get("system_instructions"),
                        version=local_ctx.get("version") or "0.1.0"
                    )
                    app_obj.tech_stack = tech_stack
                    db.add(app_obj)
                    new_apps_count += 1

        db.commit()
        return {
            "workspace_dirs": workspace_dirs,
            "workspace_dir": "; ".join(workspace_dirs),
            "total_directories": total_scanned_dirs,
            "new_apps": new_apps_count,
            "linked_apps": linked_apps_count,
            "scanned_paths": scanned_paths
        }

    @staticmethod
    def is_valid_local_app_dir(folder_path: Optional[str]) -> bool:
        """Check if folder exists and contains actual source code files besides just .git."""
        if not folder_path or not os.path.exists(folder_path) or not os.path.isdir(folder_path):
            return False
        try:
            files = [f for f in os.listdir(folder_path) if f != ".git"]
            return len(files) > 0
        except Exception:
            return False

    @staticmethod
    def normalize_slug(s: str) -> str:
        """Normalize app slug or name for case-insensitive, punctuation-insensitive folder matching."""
        if not s:
            return ""
        return s.lower().replace("'", "").replace("’", "").replace(" ", "").replace("_", "").replace("-", "")

    @staticmethod
    def get_workspace_folder_map() -> Dict[str, str]:
        """Cache folder mapping (normalized slug -> path) in workspace directories to speed up app sync status lookups."""
        now = time.time()
        if WorkspaceService._FOLDER_CACHE and (now - WorkspaceService._FOLDER_CACHE_TIME < 10.0):
            return WorkspaceService._FOLDER_CACHE

        folder_map = {}
        workspace_dirs = WorkspaceService.get_workspace_dirs()
        for workspace_dir in workspace_dirs:
            if os.path.exists(workspace_dir):
                try:
                    for entry in os.listdir(workspace_dir):
                        full_entry = os.path.join(workspace_dir, entry)
                        if os.path.isdir(full_entry):
                            entry_norm = WorkspaceService.normalize_slug(entry)
                            if entry_norm and entry_norm not in folder_map:
                                if WorkspaceService.is_valid_local_app_dir(full_entry):
                                    folder_map[entry_norm] = full_entry
                except Exception:
                    pass

        WorkspaceService._FOLDER_CACHE = folder_map
        WorkspaceService._FOLDER_CACHE_TIME = now
        return folder_map

    @staticmethod
    def get_app_sync_status(app_obj, deep: bool = False) -> Dict[str, Any]:
        """Determine whether PC or GitHub is newer, or if they are in sync."""
        from datetime import datetime
        
        # Resolve local path if not set or verify case-insensitive folder
        local_path = app_obj.local_path
        if not local_path or not WorkspaceService.is_valid_local_app_dir(local_path):
            folder_map = WorkspaceService.get_workspace_folder_map()
            target_norm_slug = WorkspaceService.normalize_slug(app_obj.slug)
            target_norm_name = WorkspaceService.normalize_slug(app_obj.name)
            local_path = folder_map.get(target_norm_slug) or folder_map.get(target_norm_name)

        has_local = WorkspaceService.is_valid_local_app_dir(local_path)
        has_github = bool(app_obj.github_url and "github.com" in app_obj.github_url)

        if not has_local and not has_github:
            return {
                "local_path": local_path,
                "local_exists": False,
                "github_exists": False,
                "sync_state": "none",
                "sync_label": "No Source"
            }

        if has_github and not has_local:
            return {
                "local_path": local_path,
                "local_exists": False,
                "github_exists": True,
                "sync_state": "github_only",
                "sync_label": "GitHub Only"
            }

        if has_local and not has_github:
            return {
                "local_path": local_path,
                "local_exists": True,
                "github_exists": False,
                "sync_state": "local_only",
                "sync_label": "PC Only"
            }

        # App exists on BOTH PC & GitHub!
        if not deep:
            return {
                "local_path": local_path,
                "local_exists": True,
                "github_exists": True,
                "sync_state": "synced",
                "sync_label": "PC & GitHub Linked"
            }
        local_commit_date = None
        uncommitted_local = False
        git_dir = os.path.join(local_path, ".git")

        if os.path.exists(git_dir):
            try:
                log_res = WorkspaceService._run_git_silent(["git", "log", "-1", "--format=%ct"], cwd=local_path, timeout=5)
                if log_res.returncode == 0 and log_res.stdout.strip():
                    local_commit_date = int(log_res.stdout.strip())

                status_res = WorkspaceService._run_git_silent(["git", "status", "--porcelain"], cwd=local_path, timeout=5)
                if status_res.stdout.strip():
                    uncommitted_local = True
            except Exception:
                pass

        if not local_commit_date and os.path.exists(local_path):
            try:
                local_commit_date = int(os.path.getmtime(local_path))
            except Exception:
                pass

        remote_commit_date = None
        if app_obj.last_commit_at:
            try:
                if isinstance(app_obj.last_commit_at, datetime):
                    remote_commit_date = int(app_obj.last_commit_at.timestamp())
                else:
                    from dateutil.parser import parse
                    remote_commit_date = int(parse(str(app_obj.last_commit_at)).timestamp())
            except Exception:
                pass

        if uncommitted_local:
            sync_state = "pc_newer"
            sync_label = "PC & GitHub (PC has uncommitted changes)"
        elif local_commit_date and remote_commit_date:
            diff = local_commit_date - remote_commit_date
            if abs(diff) < 300:  # Within 5 minutes
                sync_state = "synced"
                sync_label = "PC & GitHub (In Sync)"
            elif diff > 300:
                sync_state = "pc_newer"
                sync_label = "PC & GitHub (PC is Newer)"
            else:
                sync_state = "github_newer"
                sync_label = "PC & GitHub (GitHub is Newer)"
        else:
            sync_state = "synced"
            sync_label = "PC & GitHub Linked"

        return {
            "local_path": local_path,
            "local_exists": True,
            "github_exists": True,
            "sync_state": sync_state,
            "sync_label": sync_label
        }

    @staticmethod
    def download_and_link_app(app_obj, db: Session) -> Dict[str, Any]:
        """Download/clone GitHub repository into local workspace directory so it can run locally."""
        import shutil

        if not app_obj.github_url:
            return {
                "success": False,
                "message": f"App '{app_obj.name}' does not have a GitHub URL configured."
            }

        workspace_dir = WorkspaceService.get_workspace_dir()
        
        # Check if an existing directory matches slug or name (case-insensitive)
        target_dir = None
        if os.path.exists(workspace_dir):
            for entry in os.listdir(workspace_dir):
                full_entry = os.path.join(workspace_dir, entry)
                if os.path.isdir(full_entry):
                    clean_entry_slug = entry.lower().replace(" ", "-").replace("_", "-")
                    if clean_entry_slug == app_obj.slug.lower() or entry.lower() == app_obj.name.lower():
                        target_dir = full_entry
                        break

        if not target_dir:
            target_dir = os.path.join(workspace_dir, app_obj.slug)

        # If directory already exists and is FULLY populated with files, return success
        if WorkspaceService.is_valid_local_app_dir(target_dir):
            app_obj.local_path = target_dir
            db.commit()
            return {
                "success": True,
                "local_path": target_dir,
                "message": f"App is already present in workspace at: {target_dir}"
            }

        token = os.getenv("GITHUB_TOKEN", "").strip()
        raw_url = app_obj.github_url
        if token and "https://" in raw_url and "@" not in raw_url:
            clone_url = raw_url.replace("https://", f"https://{token}@")
        else:
            clone_url = raw_url

        env = dict(os.environ)
        env["GIT_TERMINAL_PROMPT"] = "0"

        try:
            print(f"[WorkspaceService] Downloading {app_obj.name} from {raw_url} into {target_dir}...")
            
            # If target_dir exists but is empty or only contains .git, handle pulling/cloning
            if os.path.exists(target_dir):
                git_dir = os.path.join(target_dir, ".git")
                if os.path.exists(git_dir):
                    # Try setting origin and pulling files into existing folder
                    WorkspaceService._run_git_silent(["git", "remote", "set-url", "origin", clone_url], cwd=target_dir, env=env)
                    WorkspaceService._run_git_silent(["git", "fetch", "origin"], cwd=target_dir, env=env)
                    WorkspaceService._run_git_silent(["git", "reset", "--hard", "origin/main"], cwd=target_dir, env=env)
                    WorkspaceService._run_git_silent(["git", "pull", "origin", "main"], cwd=target_dir, env=env)
                    
                    if not WorkspaceService.is_valid_local_app_dir(target_dir):
                        WorkspaceService._run_git_silent(["git", "reset", "--hard", "origin/master"], cwd=target_dir, env=env)
                        WorkspaceService._run_git_silent(["git", "pull", "origin", "master"], cwd=target_dir, env=env)

            # If folder still doesn't have source files, delete incomplete folder and run full git clone
            if not WorkspaceService.is_valid_local_app_dir(target_dir):
                if os.path.exists(target_dir):
                    shutil.rmtree(target_dir, ignore_errors=True)

                res = WorkspaceService._run_git_silent(["git", "clone", clone_url, target_dir], timeout=180, env=env)
                if res.returncode != 0:
                    clean_err = res.stderr.replace(token, "*****") if token else res.stderr
                    return {
                        "success": False,
                        "message": f"Git clone failed: {clean_err.strip() or 'Unknown git error'}"
                    }

            app_obj.local_path = target_dir
            db.commit()

            return {
                "success": True,
                "local_path": target_dir,
                "message": f"Successfully downloaded GitHub repository into local workspace: {target_dir}"
            }
        except Exception as e:
            err_msg = str(e)
            if token:
                err_msg = err_msg.replace(token, "*****")
            return {
                "success": False,
                "message": f"Failed to download repository: {err_msg}"
            }

    @staticmethod
    def get_git_status(app_obj) -> Dict[str, Any]:
        """Inspect local directory git status, modified files, current branch, and remote sync state."""
        local_path = app_obj.local_path if hasattr(app_obj, "local_path") else app_obj
        if not local_path or not os.path.exists(local_path):
            return {
                "is_git_repo": False,
                "has_changes": False,
                "total_changes": 0,
                "files": [],
                "branch": None,
                "last_commit": None,
                "unpushed_count": 0,
                "has_remote": False,
                "remote_url": None,
                "error": "Directory does not exist on disk"
            }

        git_dir = os.path.join(local_path, ".git")
        is_git_repo = os.path.exists(git_dir) and os.path.isdir(git_dir)

        # Branch detection
        branch = "main"
        if is_git_repo:
            try:
                b_res = WorkspaceService._run_git_silent(["git", "branch", "--show-current"], cwd=local_path, timeout=5)
                if b_res.returncode == 0 and b_res.stdout.strip():
                    branch = b_res.stdout.strip()
                else:
                    head_res = WorkspaceService._run_git_silent(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=local_path, timeout=5)
                    if head_res.returncode == 0 and head_res.stdout.strip():
                        branch = head_res.stdout.strip()
            except Exception:
                pass

        # Porcelain status parse
        files = []
        if is_git_repo:
            try:
                st_res = WorkspaceService._run_git_silent(["git", "status", "--porcelain=v1", "-u"], cwd=local_path, timeout=10)
                for line in st_res.stdout.splitlines():
                    if not line.strip() or len(line) < 3:
                        continue
                    code_prefix = line[:2]
                    filepath = line[3:].strip()
                    if filepath.startswith('"') and filepath.endswith('"'):
                        filepath = filepath[1:-1]

                    status_type = "modified"
                    if "??" in code_prefix:
                        status_type = "untracked"
                    elif "A" in code_prefix:
                        status_type = "added"
                    elif "D" in code_prefix:
                        status_type = "deleted"
                    elif "R" in code_prefix:
                        status_type = "renamed"
                    elif "M" in code_prefix:
                        status_type = "modified"

                    files.append({
                        "path": filepath.replace("\\", "/"),
                        "status": status_type,
                        "code": code_prefix.strip()
                    })
            except Exception as e:
                print(f"[WorkspaceService] git status error for {local_path}: {e}")
        else:
            # If not initialized as git repo yet, count all source files as pending initial commit
            try:
                all_files = []
                for root, dirs, f_list in os.walk(local_path):
                    dirs[:] = [d for d in dirs if d not in [".venv", "venv", "node_modules", ".git", "__pycache__"]]
                    for f in f_list:
                        rel = os.path.relpath(os.path.join(root, f), local_path).replace("\\", "/")
                        all_files.append({"path": rel, "status": "untracked", "code": "??"})
                        if len(all_files) >= 50:
                            break
                    if len(all_files) >= 50:
                        break
                files = all_files
            except Exception:
                pass

        # Last commit detection
        last_commit = None
        if is_git_repo:
            try:
                log_res = WorkspaceService._run_git_silent(["git", "log", "-1", "--format=%h|%s|%cr|%an"], cwd=local_path, timeout=5)
                if log_res.returncode == 0 and log_res.stdout.strip():
                    parts = log_res.stdout.strip().split("|")
                    last_commit = {
                        "hash": parts[0] if len(parts) > 0 else "",
                        "message": parts[1] if len(parts) > 1 else "",
                        "time_ago": parts[2] if len(parts) > 2 else "",
                        "author": parts[3] if len(parts) > 3 else ""
                    }
            except Exception:
                pass

        # Remote URL detection
        has_remote = False
        remote_url = None
        if hasattr(app_obj, "github_url") and app_obj.github_url:
            remote_url = app_obj.github_url
            has_remote = True
        elif is_git_repo:
            try:
                rem_res = WorkspaceService._run_git_silent(["git", "remote", "get-url", "origin"], cwd=local_path, timeout=5)
                if rem_res.returncode == 0 and rem_res.stdout.strip():
                    has_remote = True
                    remote_url = rem_res.stdout.strip()
                    if "@" in remote_url and "https://" in remote_url:
                        remote_url = "https://" + remote_url.split("@")[-1]
            except Exception:
                pass

        # Unpushed commit count
        unpushed_count = 0
        if is_git_repo and has_remote:
            try:
                ahead_res = WorkspaceService._run_git_silent(["git", "rev-list", "--count", f"origin/{branch}..HEAD"], cwd=local_path, timeout=5)
                if ahead_res.returncode == 0 and ahead_res.stdout.strip().isdigit():
                    unpushed_count = int(ahead_res.stdout.strip())
            except Exception:
                pass

        return {
            "is_git_repo": is_git_repo,
            "has_changes": len(files) > 0,
            "total_changes": len(files),
            "files": files,
            "branch": branch,
            "last_commit": last_commit,
            "unpushed_count": unpushed_count,
            "has_remote": has_remote,
            "remote_url": remote_url,
            "local_path": local_path
        }

    @staticmethod
    def generate_commit_message(app_obj, files: List[str] = [], recent_actions: List[str] = []) -> str:
        """Generate a concise, professional Git commit message using Gemini / Captain Geppy."""
        from gitbridge.services.extension_service import call_gemini

        file_summary = ", ".join(files[:8]) if files else "modified files"
        actions_str = "; ".join(recent_actions[-4:]) if recent_actions else ""
        app_name = app_obj.name if app_obj else "Application"

        system_prompt = """You are Geppy's Git Architect.
Generate a concise, professional Git commit message following conventional commits format (e.g. feat(scope): message, fix(scope): message, style(scope): message, refactor(scope): message).
CRITICAL RULES:
1. Output ONLY the single-line commit message string. Do NOT enclose in quotes, backticks, or markdown blocks.
2. Keep it under 65 characters.
3. Be specific to what changed. Never include 'Captain Geppy' in the commit message."""

        user_prompt = f"App: {app_name}\nModified Files: {file_summary}\nRecent Actions: {actions_str}\nGenerate a crisp commit message:"

        try:
            msg = call_gemini([{"role": "user", "parts": [{"text": user_prompt}]}], system_prompt)
            if msg:
                clean = msg.strip().strip('"').strip("'").strip("`")
                clean = clean.splitlines()[0].strip()
                if len(clean) > 5:
                    return clean
        except Exception:
            pass

        if files:
            first_base = os.path.basename(files[0])
            if len(files) == 1:
                return f"feat: update {first_base}"
            return f"feat: update {first_base} and {len(files) - 1} other files"
        return f"feat: update {app_name}"

    @staticmethod
    def push_app_to_github(
        app_obj,
        commit_message: Optional[str] = None,
        make_private: bool = False,
        push_remote: bool = True,
        update_changelog_file: bool = True,
        changelog_entries: Optional[List[Dict[str, Any]]] = None,
        db: Session = None,
        skip_if_clean: bool = False
    ) -> Dict[str, Any]:
        """Stage, commit, and push local application files to GitHub repository silently (zero cmd popups)."""
        from datetime import datetime

        local_path = app_obj.local_path
        if not local_path or not os.path.exists(local_path):
            return {
                "success": False,
                "saved_locally": False,
                "pushed_to_github": False,
                "message": f"Local folder for '{app_obj.name}' does not exist on disk."
            }

        token = os.getenv("GITHUB_TOKEN", "").strip()

        # Ensure safe .gitignore so node_modules / .venv never get staged
        WorkspaceService._ensure_safe_gitignore(local_path)

        # Step 1: Ensure local directory is initialized as git repository
        git_dir = os.path.join(local_path, ".git")
        was_new_repo = False
        if not os.path.exists(git_dir):
            was_new_repo = True
            try:
                WorkspaceService._run_git_silent(["git", "init"], cwd=local_path, check=True)
                WorkspaceService._run_git_silent(["git", "branch", "-M", "main"], cwd=local_path, check=True)
            except Exception as e:
                return {
                    "success": False,
                    "saved_locally": False,
                    "pushed_to_github": False,
                    "message": f"Failed to initialize local git repository: {e}"
                }

        # Step 2: Configure local git identity if not set
        is_gb = bool(app_obj and getattr(app_obj, "slug", "") in ("geppys-gitbridge", "gitbridge"))
        git_user = "Captain Geppy" if is_gb else "Geppy"
        try:
            name_check = WorkspaceService._run_git_silent(["git", "config", "user.name"], cwd=local_path)
            if not name_check.stdout.strip() or (not is_gb and name_check.stdout.strip() == "Captain Geppy"):
                WorkspaceService._run_git_silent(["git", "config", "user.name", git_user], cwd=local_path)
                WorkspaceService._run_git_silent(["git", "config", "user.email", "geppy@geppy.ai"], cwd=local_path)
        except Exception:
            pass

        # Inspect pre-commit modified files so we can include them in CHANGELOG.md if needed
        pre_status_res = WorkspaceService._run_git_silent(["git", "status", "--porcelain"], cwd=local_path, timeout=10)
        pre_changed_lines = [
            l for l in pre_status_res.stdout.splitlines()
            if l.strip() and not any(ig in l for ig in ("node_modules/", ".venv/", "venv/", "__pycache__/"))
        ]

        # Fast-path skip when running Fleet Updater if repo is already clean & synced
        if skip_if_clean and not was_new_repo and not pre_changed_lines and app_obj.github_url and "github.com" in app_obj.github_url:
            try:
                branch_chk = WorkspaceService._run_git_silent(["git", "branch", "--show-current"], cwd=local_path, timeout=5).stdout.strip() or "main"
                ahead_res = WorkspaceService._run_git_silent(["git", "rev-list", "--count", f"origin/{branch_chk}..HEAD"], cwd=local_path, timeout=5)
                if ahead_res.returncode == 0 and ahead_res.stdout.strip() == "0":
                    commit_hash = WorkspaceService._run_git_silent(["git", "rev-parse", "--short", "HEAD"], cwd=local_path, timeout=5).stdout.strip() or "head"
                    return {
                        "success": True,
                        "skipped": True,
                        "saved_locally": True,
                        "pushed_to_github": False,
                        "commit_hash": commit_hash,
                        "branch": branch_chk,
                        "files_committed": 0,
                        "github_url": app_obj.github_url,
                        "message": f"Skipped '{app_obj.name}' — already clean and in sync with GitHub ({commit_hash})."
                    }
            except Exception:
                pass

        msg = (commit_message or f"Update {app_obj.name}").strip()
        first_line_title = msg.splitlines()[0].strip() if msg else f"Update {app_obj.name}"

        # Step 2.5: Automatically update CHANGELOG.md in the app repository if enabled
        changelog_updated = False
        if update_changelog_file and (pre_changed_lines or changelog_entries):
            try:
                changelog_path = os.path.join(local_path, "CHANGELOG.md")
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
                bullet_items = []
                seen_bullets = set()

                if changelog_entries and isinstance(changelog_entries, list):
                    for entry in changelog_entries:
                        if not isinstance(entry, dict):
                            continue
                        fp = entry.get("file_path") or ""
                        summary = (entry.get("summary") or "").strip()
                        explanation = (entry.get("explanation") or "").strip()
                        if not summary:
                            continue
                        prefix = f"**`{fp}`**: " if fp else ""
                        suffix = f" — {explanation}" if explanation and explanation not in summary else ""
                        line_str = f"- {prefix}{summary}{suffix}"
                        if line_str not in seen_bullets:
                            seen_bullets.add(line_str)
                            bullet_items.append(line_str)

                if not bullet_items and "\n" in msg:
                    for raw_line in msg.splitlines()[1:]:
                        stripped = raw_line.strip()
                        if stripped.startswith("- ") or stripped.startswith("* "):
                            if stripped not in seen_bullets:
                                seen_bullets.add(stripped)
                                bullet_items.append(stripped)

                if not bullet_items and pre_changed_lines:
                    for cl in pre_changed_lines[:15]:
                        fp_part = cl[3:].strip().strip('"').replace("\\", "/")
                        if fp_part and fp_part != "CHANGELOG.md":
                            bullet_items.append(f"- Updated `{fp_part}`")

                if bullet_items:
                    new_section = f"## [{now_str}] — {first_line_title}\n" + "\n".join(bullet_items) + "\n\n"
                    header_title = f"# Change Log — {app_obj.name}\n\n"
                    existing_body = ""
                    if os.path.exists(changelog_path):
                        try:
                            with open(changelog_path, "r", encoding="utf-8", errors="ignore") as cf:
                                existing_raw = cf.read()
                            if existing_raw.startswith("# "):
                                parts = existing_raw.split("\n", 1)
                                header_title = parts[0].strip() + "\n\n"
                                existing_body = parts[1].lstrip() if len(parts) > 1 else ""
                            else:
                                existing_body = existing_raw.lstrip()
                        except Exception:
                            existing_body = ""

                    with open(changelog_path, "w", encoding="utf-8") as cf:
                        cf.write(header_title + new_section + existing_body)
                    changelog_updated = True
            except Exception as e:
                print(f"[WorkspaceService] Could not update CHANGELOG.md: {e}")

        # Step 3: Git add all source files (excluding heavy dependency folders)
        try:
            add_res = WorkspaceService._run_git_silent(
                ["git", "add", "--all", "--", ".", ":!node_modules", ":!.venv", ":!venv", ":!__pycache__", ":!.next", ":!.tmp.driveupload"],
                cwd=local_path,
                timeout=25
            )
            if add_res.returncode != 0:
                WorkspaceService._run_git_silent(["git", "add", "."], cwd=local_path, timeout=25, check=True)
        except Exception as e:
            return {
                "success": False,
                "saved_locally": False,
                "pushed_to_github": False,
                "message": f"Git add failed: {e}"
            }

        # Count changed files before commit
        status_res = WorkspaceService._run_git_silent(["git", "status", "--porcelain"], cwd=local_path, timeout=10)
        changed_lines = [l for l in status_res.stdout.splitlines() if l.strip()]
        files_committed_count = len(changed_lines)

        # Step 4: Commit locally
        commit_hash = ""
        if changed_lines:
            try:
                WorkspaceService._run_git_silent(["git", "commit", "-m", msg], cwd=local_path, timeout=20, check=True)
            except Exception as e:
                return {
                    "success": False,
                    "saved_locally": False,
                    "pushed_to_github": False,
                    "message": f"Git commit failed: {e}"
                }

        # Retrieve current commit hash & branch
        try:
            commit_hash = WorkspaceService._run_git_silent(["git", "rev-parse", "--short", "HEAD"], cwd=local_path, timeout=5).stdout.strip()
            branch_name = WorkspaceService._run_git_silent(["git", "branch", "--show-current"], cwd=local_path, timeout=5).stdout.strip() or "main"
        except Exception:
            commit_hash = "head"
            branch_name = "main"

        # If user only wanted local commit
        if not push_remote:
            return {
                "success": True,
                "saved_locally": True,
                "pushed_to_github": False,
                "changelog_updated": changelog_updated,
                "commit_hash": commit_hash,
                "branch": branch_name,
                "commit_message": msg,
                "files_committed": files_committed_count,
                "github_url": app_obj.github_url,
                "message": f"Changes safely committed to your computer disk (commit {commit_hash}) on branch '{branch_name}'."
            }

        # Step 5: Ensure GitHub repository exists remote
        from gitbridge.services.github_service import GitHubService
        gh_service = GitHubService()

        if not app_obj.github_url or "github.com" not in app_obj.github_url:
            try:
                repo_data = gh_service.create_repository(
                    name=app_obj.slug,
                    description=app_obj.description,
                    private=make_private
                )
                html_url = repo_data.get("html_url")
                full_name = repo_data.get("full_name")
                if html_url:
                    app_obj.github_url = html_url
                    app_obj.github_repo_name = full_name
                    if db:
                        db.commit()
            except Exception as e:
                return {
                    "success": True,
                    "saved_locally": True,
                    "pushed_to_github": False,
                    "changelog_updated": changelog_updated,
                    "commit_hash": commit_hash,
                    "branch": branch_name,
                    "commit_message": msg,
                    "files_committed": files_committed_count,
                    "github_url": app_obj.github_url,
                    "warning": f"Changes saved and committed locally ({commit_hash}), but GitHub repo creation failed: {e}",
                    "message": f"Saved locally (commit {commit_hash}). GitHub remote repo could not be created: {e}"
                }

        # Format authenticated remote URL if token is present
        remote_url = app_obj.github_url
        if token and "https://" in remote_url and "@" not in remote_url:
            authenticated_url = remote_url.replace("https://", f"https://{token}@")
        else:
            authenticated_url = remote_url

        # Ensure remote origin is set
        try:
            remotes = WorkspaceService._run_git_silent(["git", "remote"], cwd=local_path, timeout=5).stdout.strip().splitlines()
            if "origin" in remotes:
                WorkspaceService._run_git_silent(["git", "remote", "set-url", "origin", authenticated_url], cwd=local_path, timeout=5, check=True)
            else:
                WorkspaceService._run_git_silent(["git", "remote", "add", "origin", authenticated_url], cwd=local_path, timeout=5, check=True)
        except Exception as e:
            return {
                "success": True,
                "saved_locally": True,
                "pushed_to_github": False,
                "changelog_updated": changelog_updated,
                "commit_hash": commit_hash,
                "branch": branch_name,
                "commit_message": msg,
                "files_committed": files_committed_count,
                "github_url": app_obj.github_url,
                "warning": f"Changes saved locally ({commit_hash}), but remote setup failed: {e}",
                "message": f"Saved locally (commit {commit_hash}). Git remote setup failed: {e}"
            }

        # Step 6: Push to remote silently
        try:
            push_res = WorkspaceService._run_git_silent(["git", "push", "-u", "origin", branch_name], cwd=local_path, timeout=45)
            if push_res.returncode != 0:
                push_res = WorkspaceService._run_git_silent(["git", "push", "origin", "HEAD"], cwd=local_path, timeout=45)
                if push_res.returncode != 0:
                    clean_err = push_res.stderr.strip()
                    if token:
                        clean_err = clean_err.replace(token, "*****")
                    return {
                        "success": True,
                        "saved_locally": True,
                        "pushed_to_github": False,
                        "changelog_updated": changelog_updated,
                        "commit_hash": commit_hash,
                        "branch": branch_name,
                        "commit_message": msg,
                        "files_committed": files_committed_count,
                        "github_url": app_obj.github_url,
                        "warning": f"Changes saved on computer (commit {commit_hash}), but GitHub push failed: {clean_err}",
                        "message": f"Saved locally on PC (commit {commit_hash}). GitHub push error: {clean_err}"
                    }

            if db:
                try:
                    app_obj.last_commit_at = datetime.utcnow()
                    db.commit()
                except Exception:
                    pass

            return {
                "success": True,
                "saved_locally": True,
                "pushed_to_github": True,
                "changelog_updated": changelog_updated,
                "commit_hash": commit_hash,
                "branch": branch_name,
                "commit_message": msg,
                "files_committed": files_committed_count,
                "github_url": app_obj.github_url,
                "message": f"Successfully saved locally (commit {commit_hash}) and pushed to GitHub ({app_obj.github_url})!"
            }
        except Exception as e:
            err_str = str(e)
            if token:
                err_str = err_str.replace(token, "*****")
            return {
                "success": True,
                "saved_locally": True,
                "pushed_to_github": False,
                "changelog_updated": changelog_updated,
                "commit_hash": commit_hash,
                "branch": branch_name,
                "commit_message": msg,
                "files_committed": files_committed_count,
                "github_url": app_obj.github_url,
                "warning": f"Changes saved locally ({commit_hash}), but push encountered: {err_str}",
                "message": f"Saved locally (commit {commit_hash}). Push exception: {err_str}"
            }

    @classmethod
    def get_github_updater_status(cls) -> Dict[str, Any]:
        """Return live telemetry of the contained GitHub Fleet Updater."""
        with cls._UPDATER_LOCK:
            st = dict(cls._UPDATER_STATE)
            if st.get("started_at"):
                end_t = st.get("finished_at") or time.time()
                st["elapsed_seconds"] = round(max(0.0, end_t - st["started_at"]), 1)
            else:
                st["elapsed_seconds"] = 0.0
            return st

    @classmethod
    def cancel_github_updater(cls) -> Dict[str, Any]:
        """Signal the background GitHub Fleet Updater to stop after the current git operation."""
        cls._UPDATER_CANCEL_EVENT.set()
        with cls._UPDATER_LOCK:
            if cls._UPDATER_STATE.get("running"):
                cls._UPDATER_STATE["status"] = "cancelling"
                cls._UPDATER_STATE["logs"].insert(0, "🛑 Cancellation requested — stopping after current operation...")
        return cls.get_github_updater_status()

    @classmethod
    def start_github_updater(
        cls,
        only_changed: bool = True,
        slugs: Optional[List[str]] = None,
        commit_message: Optional[str] = None
    ) -> Dict[str, Any]:
        """Start the contained background GitHub Fleet Updater (zero cmd windows, live progress & cancelable)."""
        with cls._UPDATER_LOCK:
            if cls._UPDATER_STATE.get("running"):
                return cls.get_github_updater_status()

            cls._UPDATER_CANCEL_EVENT.clear()
            cls._UPDATER_STATE = {
                "running": True,
                "status": "running",
                "only_changed": bool(only_changed),
                "total": 0,
                "processed": 0,
                "pushed": 0,
                "skipped": 0,
                "failed": 0,
                "current_app": {"slug": "", "name": "Scanning workspace...", "step": "Initializing"},
                "started_at": time.time(),
                "finished_at": None,
                "items": [],
                "logs": ["🚀 Started silent GitHub Fleet Updater (CREATE_NO_WINDOW active — zero console popups)."]
            }

        def _worker():
            from gitbridge.db.database import SessionLocal
            db = SessionLocal()
            try:
                query = db.query(AppProfileModel).order_by(AppProfileModel.name.asc())
                all_apps = query.all()
                target_apps = []
                for a in all_apps:
                    if slugs and a.slug not in slugs:
                        continue
                    if a.local_path and os.path.exists(a.local_path):
                        target_apps.append(a)

                items_init = [
                    {
                        "slug": a.slug,
                        "name": a.name,
                        "local_path": a.local_path,
                        "status": "pending",
                        "message": "Queued",
                        "commit_hash": "",
                        "github_url": a.github_url or "",
                        "files_committed": 0,
                        "duration_ms": 0
                    }
                    for a in target_apps
                ]
                with cls._UPDATER_LOCK:
                    cls._UPDATER_STATE["total"] = len(target_apps)
                    cls._UPDATER_STATE["items"] = items_init

                for idx, app_obj in enumerate(target_apps):
                    if cls._UPDATER_CANCEL_EVENT.is_set():
                        with cls._UPDATER_LOCK:
                            for rem in cls._UPDATER_STATE["items"][idx:]:
                                if rem["status"] == "pending":
                                    rem["status"] = "cancelled"
                                    rem["message"] = "Cancelled by user"
                            cls._UPDATER_STATE["running"] = False
                            cls._UPDATER_STATE["status"] = "cancelled"
                            cls._UPDATER_STATE["current_app"] = None
                            cls._UPDATER_STATE["finished_at"] = time.time()
                            cls._UPDATER_STATE["logs"].insert(0, "🛑 GitHub Fleet Update cancelled by user.")
                        return

                    t0 = time.time()
                    with cls._UPDATER_LOCK:
                        cls._UPDATER_STATE["current_app"] = {
                            "slug": app_obj.slug,
                            "name": app_obj.name,
                            "step": "Inspecting & syncing with GitHub..."
                        }
                        cls._UPDATER_STATE["items"][idx]["status"] = "running"
                        cls._UPDATER_STATE["items"][idx]["message"] = "Syncing..."

                    res = cls.push_app_to_github(
                        app_obj,
                        commit_message=commit_message,
                        push_remote=True,
                        db=db,
                        skip_if_clean=only_changed
                    )
                    dur_ms = int((time.time() - t0) * 1000)

                    with cls._UPDATER_LOCK:
                        cls._UPDATER_STATE["processed"] = idx + 1
                        item_entry = cls._UPDATER_STATE["items"][idx]
                        item_entry["duration_ms"] = dur_ms
                        item_entry["commit_hash"] = res.get("commit_hash") or ""
                        item_entry["github_url"] = res.get("github_url") or app_obj.github_url or ""
                        item_entry["files_committed"] = res.get("files_committed") or 0
                        item_entry["message"] = res.get("warning") or res.get("message") or ""

                        if res.get("skipped"):
                            cls._UPDATER_STATE["skipped"] += 1
                            item_entry["status"] = "skipped"
                            cls._UPDATER_STATE["logs"].insert(
                                0, f"⏭️ [{idx + 1}/{len(target_apps)}] {app_obj.name}: Already clean & in sync ({dur_ms}ms)"
                            )
                        elif res.get("pushed_to_github"):
                            cls._UPDATER_STATE["pushed"] += 1
                            item_entry["status"] = "pushed"
                            cls._UPDATER_STATE["logs"].insert(
                                0, f"✅ [{idx + 1}/{len(target_apps)}] {app_obj.name}: Pushed commit {item_entry['commit_hash']} ({item_entry['files_committed']} files, {dur_ms}ms)"
                            )
                        else:
                            cls._UPDATER_STATE["failed"] += 1
                            item_entry["status"] = "failed"
                            cls._UPDATER_STATE["logs"].insert(
                                0, f"⚠️ [{idx + 1}/{len(target_apps)}] {app_obj.name}: {item_entry['message']}"
                            )
                        cls._UPDATER_STATE["logs"] = cls._UPDATER_STATE["logs"][:120]

                with cls._UPDATER_LOCK:
                    cls._UPDATER_STATE["running"] = False
                    cls._UPDATER_STATE["status"] = "completed"
                    cls._UPDATER_STATE["current_app"] = None
                    cls._UPDATER_STATE["finished_at"] = time.time()
                    p = cls._UPDATER_STATE["pushed"]
                    s = cls._UPDATER_STATE["skipped"]
                    f = cls._UPDATER_STATE["failed"]
                    cls._UPDATER_STATE["logs"].insert(
                        0, f"🏁 Fleet Update Complete! Pushed: {p} • Skipped (Up-to-Date): {s} • Warnings/Failed: {f}"
                    )
            except Exception as exc:
                with cls._UPDATER_LOCK:
                    cls._UPDATER_STATE["running"] = False
                    cls._UPDATER_STATE["status"] = "error"
                    cls._UPDATER_STATE["current_app"] = None
                    cls._UPDATER_STATE["finished_at"] = time.time()
                    cls._UPDATER_STATE["logs"].insert(0, f"❌ Updater error: {exc}")
            finally:
                db.close()

        t = threading.Thread(target=_worker, daemon=True, name="GitHubFleetUpdater")
        t.start()
        return cls.get_github_updater_status()

    @staticmethod
    def inspect_deep_file_structure(folder_path: str) -> Dict[str, Any]:
        """Perform deep structural scanning of local directory tree, key files, code entrypoints, and configs."""
        if not folder_path or not os.path.exists(folder_path) or not os.path.isdir(folder_path):
            return {"file_tree": [], "sampled_contents": {}, "detected_tech": []}

        file_tree = []
        sampled_contents = {}
        detected_tech = set()

        ignore_dirs = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", ".next", ".tmp.driveupload"}

        for root, dirs, files in os.walk(folder_path):
            dirs[:] = [d for d in dirs if d not in ignore_dirs and not d.startswith(".")]
            rel_root = os.path.relpath(root, folder_path)
            if rel_root == ".":
                rel_root = ""

            for f in files:
                if f.startswith(".") and f not in [".env.example", ".gitignore"]:
                    continue
                rel_path = os.path.join(rel_root, f).replace("\\", "/")
                file_tree.append(rel_path)
                if len(file_tree) >= 60:
                    break
            if len(file_tree) >= 60:
                break

        key_file_patterns = [
            "package.json", "requirements.txt", "pyproject.toml",
            "index.html", "metadata.json", "firebase-blueprint.json",
            "server.ts", "server.js", "main.py", "app.py",
            "src/App.tsx", "src/App.jsx", "src/main.tsx", "src/index.js",
            "README.md", "DESIGN.md"
        ]

        for pattern in key_file_patterns:
            target_file = os.path.join(folder_path, pattern.replace("/", os.sep))
            if os.path.exists(target_file) and os.path.isfile(target_file):
                try:
                    with open(target_file, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read(2500)
                        sampled_contents[pattern] = content.strip()
                except Exception:
                    pass

        tree_str = " ".join(file_tree).lower()
        if "package.json" in sampled_contents:
            pkg = sampled_contents["package.json"].lower()
            if "react" in pkg: detected_tech.add("React")
            if "vite" in pkg: detected_tech.add("Vite")
            if "tailwindcss" in pkg or "tailwind" in pkg: detected_tech.add("Tailwind CSS")
            if "express" in pkg: detected_tech.add("Express")
            if "firebase" in pkg or "firestore" in pkg: detected_tech.add("Firebase")
            if "typescript" in pkg or ".ts" in tree_str: detected_tech.add("TypeScript")
            if "electron" in pkg: detected_tech.add("Electron")
            if "next" in pkg: detected_tech.add("Next.js")
            if "vue" in pkg: detected_tech.add("Vue.js")

        if "requirements.txt" in sampled_contents or "main.py" in sampled_contents or ".py" in tree_str:
            detected_tech.add("Python")
            if "fastapi" in str(sampled_contents).lower(): detected_tech.add("FastAPI")
            if "flask" in str(sampled_contents).lower(): detected_tech.add("Flask")
            if "sqlalchemy" in str(sampled_contents).lower(): detected_tech.add("SQLite / SQLAlchemy")

        if "index.html" in sampled_contents:
            detected_tech.add("HTML5")

        return {
            "file_tree": file_tree,
            "sampled_contents": sampled_contents,
            "detected_tech": sorted(list(detected_tech))
        }

    @staticmethod
    def ensure_app_assets_dir(app_obj) -> Optional[str]:
        """Ensure a local assets/ folder exists inside the application directory."""
        if not app_obj.local_path or not os.path.exists(app_obj.local_path):
            return None
        assets_dir = os.path.join(app_obj.local_path, "assets")
        os.makedirs(assets_dir, exist_ok=True)
        return assets_dir

    @staticmethod
    def sync_app_local_assets(app_obj, db: Session) -> List[Any]:
        """Discover image/document files inside app assets/ folder and sync them with SQLite MediaAsset table."""
        from gitbridge.db.models import MediaAssetModel
        from gitbridge.schemas.app_profile import AssetType

        assets_dir = WorkspaceService.ensure_app_assets_dir(app_obj)
        if not assets_dir:
            return []

        valid_exts = {".png", ".jpg", ".jpeg", ".webp", ".svg", ".gif", ".pdf", ".ico"}
        discovered = []

        for root, dirs, files in os.walk(assets_dir):
            for f in files:
                ext = os.path.splitext(f)[1].lower()
                if ext in valid_exts:
                    rel_file = os.path.relpath(os.path.join(root, f), app_obj.local_path).replace("\\", "/")
                    filename = os.path.basename(f)

                    f_lower = filename.lower()
                    if "logo" in f_lower:
                        asset_type = AssetType.LOGO
                    elif "icon" in f_lower or "fav" in f_lower:
                        asset_type = AssetType.ICON
                    elif "banner" in f_lower or "hero" in f_lower:
                        asset_type = AssetType.BANNER
                    elif "screen" in f_lower or "shot" in f_lower:
                        asset_type = AssetType.SCREENSHOT
                    elif "doc" in f_lower or ext == ".pdf":
                        asset_type = AssetType.DOC_IMAGE
                    else:
                        asset_type = AssetType.SCREENSHOT

                    existing = db.query(MediaAssetModel).filter(
                        MediaAssetModel.app_id == app_obj.slug,
                        MediaAssetModel.file_path == rel_file
                    ).first()

                    title = filename.replace("-", " ").replace("_", " ").rsplit(".", 1)[0].title()
                    file_url = f"/api/apps/{app_obj.slug}/assets/file/{filename}"

                    if not existing:
                        asset_obj = MediaAssetModel(
                            app_id=app_obj.slug,
                            title=title,
                            asset_type=asset_type,
                            file_path=rel_file,
                            url=file_url
                        )
                        db.add(asset_obj)
                        discovered.append(asset_obj)
                    else:
                        if not existing.url:
                            existing.url = file_url
                        discovered.append(existing)

        db.commit()
        return discovered

    @staticmethod
    def get_app_file_tree(app_obj) -> List[Dict[str, Any]]:
        """Get structured directory file tree of editable source/config files for an application project folder."""
        if not app_obj.local_path or not os.path.exists(app_obj.local_path):
            return []

        ignore_dirs = {
            ".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build",
            ".next", ".tmp.driveupload", ".geppy_baselines", ".geppy_latest", "sot_references"
        }
        binary_or_skip_exts = {
            ".png", ".jpg", ".jpeg", ".gif", ".webp", ".heic", ".ico", ".bmp", ".tiff",
            ".mp3", ".wav", ".ogg", ".mp4", ".webm", ".mov", ".avi",
            ".woff", ".woff2", ".ttf", ".eot", ".otf",
            ".pdf", ".zip", ".tar", ".gz", ".7z", ".rar",
            ".exe", ".dll", ".so", ".dylib", ".bin", ".lnk",
            ".db", ".sqlite", ".sqlite3", ".pyc", ".pyo", ".pyd", ".map"
        }
        skip_filenames = {"package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "uv.lock"}
        tree = []

        for root, dirs, files in os.walk(app_obj.local_path):
            dirs[:] = sorted([d for d in dirs if d not in ignore_dirs and not d.startswith(".")])
            rel_dir = os.path.relpath(root, app_obj.local_path).replace("\\", "/")
            if rel_dir == ".":
                rel_dir = ""

            # Skip generated image folders under assets/
            if rel_dir.startswith("assets/"):
                continue

            for f in sorted(files):
                if f in skip_filenames:
                    continue
                if f.startswith(".") and f not in [".env.example", ".gitignore", ".env"]:
                    continue
                ext = os.path.splitext(f)[1].lower()
                if ext in binary_or_skip_exts:
                    continue

                rel_path = f"{rel_dir}/{f}" if rel_dir else f
                file_size = 0
                try:
                    file_size = os.path.getsize(os.path.join(root, f))
                except Exception:
                    pass

                tree.append({
                    "path": rel_path,
                    "name": f,
                    "dir": rel_dir,
                    "extension": ext,
                    "size": file_size
                })

                if len(tree) >= 250:
                    break
            if len(tree) >= 250:
                break

        def _sort_key(item: Dict[str, Any]):
            p = item["path"].lower()
            ext = item["extension"]
            # Prioritize primary UI & code files over docs/configs
            is_primary_code = ext in {".html", ".tsx", ".jsx", ".js", ".ts", ".vue", ".svelte", ".css", ".scss", ".py"}
            return (0 if is_primary_code else 1, p)

        return sorted(tree, key=_sort_key)

    @staticmethod
    def read_app_file(app_obj, relative_path: str) -> Dict[str, Any]:
        """Read content of a specific file inside app's project folder, including original baseline and latest edited state."""
        if not app_obj.local_path or not os.path.exists(app_obj.local_path):
            return {"success": False, "message": "App local directory does not exist."}

        clean_rel = relative_path.replace("\\", "/").lstrip("/")
        abs_target = os.path.abspath(os.path.join(app_obj.local_path, clean_rel))
        abs_base = os.path.abspath(app_obj.local_path)

        if not abs_target.startswith(abs_base):
            return {"success": False, "message": "Access denied: Path outside project directory."}

        if not os.path.exists(abs_target) or not os.path.isfile(abs_target):
            return {"success": False, "message": f"File '{clean_rel}' not found."}

        try:
            with open(abs_target, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read(150000)

            baseline_path = os.path.join(abs_base, ".geppy_baselines", clean_rel.replace("/", os.sep))
            latest_path = os.path.join(abs_base, ".geppy_latest", clean_rel.replace("/", os.sep))

            original_baseline = content
            if os.path.exists(baseline_path) and os.path.isfile(baseline_path):
                try:
                    with open(baseline_path, "r", encoding="utf-8", errors="ignore") as bf:
                        original_baseline = bf.read(150000)
                except Exception:
                    pass

            latest_edited = content
            if os.path.exists(latest_path) and os.path.isfile(latest_path):
                try:
                    with open(latest_path, "r", encoding="utf-8", errors="ignore") as lf:
                        latest_edited = lf.read(150000)
                except Exception:
                    pass

            return {
                "success": True,
                "path": clean_rel,
                "abs_path": abs_target,
                "content": content,
                "original_baseline": original_baseline,
                "latest_edited": latest_edited,
                "has_baseline_diff": (original_baseline != latest_edited)
            }
        except Exception as e:
            return {"success": False, "message": f"Failed to read file: {e}"}

    @staticmethod
    def save_app_file(app_obj, relative_path: str, content: str, is_preview_revert: bool = False) -> Dict[str, Any]:
        """Save/write content to a file inside app's project folder while preserving original baseline for Preview ON/OFF."""
        if not app_obj.local_path or not os.path.exists(app_obj.local_path):
            return {"success": False, "message": "App local directory does not exist."}

        clean_rel = relative_path.replace("\\", "/").lstrip("/")
        abs_target = os.path.abspath(os.path.join(app_obj.local_path, clean_rel))
        abs_base = os.path.abspath(app_obj.local_path)

        if not abs_target.startswith(abs_base):
            return {"success": False, "message": "Access denied: Path outside project directory."}

        if clean_rel.lower().endswith(".py"):
            import ast
            try:
                ast.parse(content)
            except SyntaxError as syn_err:
                return {
                    "success": False,
                    "message": f"Refused to overwrite '{clean_rel}' with invalid/truncated Python syntax: {syn_err}"
                }

        try:
            baseline_path = os.path.join(abs_base, ".geppy_baselines", clean_rel.replace("/", os.sep))
            latest_path = os.path.join(abs_base, ".geppy_latest", clean_rel.replace("/", os.sep))

            # 1. Preserve original baseline before first edit if not already saved
            if not is_preview_revert and os.path.exists(abs_target) and not os.path.exists(baseline_path):
                try:
                    os.makedirs(os.path.dirname(baseline_path), exist_ok=True)
                    with open(abs_target, "r", encoding="utf-8", errors="ignore") as orig_f:
                        orig_text = orig_f.read()
                    with open(baseline_path, "w", encoding="utf-8") as bf:
                        bf.write(orig_text)
                except Exception:
                    pass

            # 2. Save latest edited content snapshot when not reverting to baseline
            if not is_preview_revert:
                try:
                    os.makedirs(os.path.dirname(latest_path), exist_ok=True)
                    with open(latest_path, "w", encoding="utf-8") as lf:
                        lf.write(content)
                except Exception:
                    pass

            # 3. Write requested content to actual file on disk
            os.makedirs(os.path.dirname(abs_target), exist_ok=True)
            with open(abs_target, "w", encoding="utf-8") as f:
                f.write(content)

            return {
                "success": True,
                "path": clean_rel,
                "abs_path": abs_target,
                "message": f"Successfully saved file '{clean_rel}'"
            }
        except Exception as e:
            return {"success": False, "message": f"Failed to save file: {e}"}

    @staticmethod
    def set_app_preview_mode(
        app_obj,
        enabled: bool,
        file_path: Optional[str] = None,
        edited_content: Optional[str] = None,
        baseline_content: Optional[str] = None
    ) -> Dict[str, Any]:
        """Swap all modified files (and any cached client/dist bundle) between Original Baseline (OFF) and Edited Preview (ON)."""
        import shutil
        if not app_obj.local_path or not os.path.exists(app_obj.local_path):
            return {"success": False, "message": "App local directory does not exist."}

        abs_base = os.path.abspath(app_obj.local_path)
        baselines_root = os.path.join(abs_base, ".geppy_baselines")
        latest_root = os.path.join(abs_base, ".geppy_latest")
        swapped_files = []

        # Ensure current file's baseline/latest are recorded if passed from extension
        if file_path:
            clean_rel = file_path.replace("\\", "/").lstrip("/")
            b_file = os.path.join(baselines_root, clean_rel.replace("/", os.sep))
            l_file = os.path.join(latest_root, clean_rel.replace("/", os.sep))
            if baseline_content is not None and not os.path.exists(b_file):
                try:
                    os.makedirs(os.path.dirname(b_file), exist_ok=True)
                    with open(b_file, "w", encoding="utf-8") as f:
                        f.write(baseline_content)
                except Exception:
                    pass
            if edited_content is not None:
                try:
                    os.makedirs(os.path.dirname(l_file), exist_ok=True)
                    with open(l_file, "w", encoding="utf-8") as f:
                        f.write(edited_content)
                except Exception:
                    pass

        source_root = latest_root if enabled else baselines_root
        if os.path.exists(source_root):
            for root, _, files in os.walk(source_root):
                for fname in files:
                    src_file = os.path.join(root, fname)
                    rel = os.path.relpath(src_file, source_root)
                    dst_file = os.path.join(abs_base, rel)
                    try:
                        os.makedirs(os.path.dirname(dst_file), exist_ok=True)
                        shutil.copy2(src_file, dst_file)
                        swapped_files.append(rel.replace("\\", "/"))
                    except Exception:
                        pass

        # If this app has pre-built dist snapshots (.geppy_baselines_dist / .geppy_latest_dist), swap client/dist or dist instantly!
        for dist_rel in [os.path.join("client", "dist"), "dist"]:
            target_dist = os.path.join(abs_base, dist_rel)
            snap_dist = os.path.join(abs_base, ".geppy_latest_dist" if enabled else ".geppy_baselines_dist")
            if os.path.exists(snap_dist) and os.path.isdir(snap_dist):
                try:
                    if os.path.exists(target_dist):
                        shutil.rmtree(target_dist, ignore_errors=True)
                    shutil.copytree(snap_dist, target_dist)
                    break
                except Exception:
                    pass

        return {
            "success": True,
            "enabled": enabled,
            "swapped_files": swapped_files
        }

    @staticmethod
    def launch_antigravity_cli(app_obj) -> Dict[str, Any]:
        """Launch Antigravity Desktop / IDE (or CLI terminal) in the application project folder."""
        local_path = app_obj.local_path
        if not local_path or not os.path.exists(local_path):
            return {"success": False, "message": f"Local folder for '{app_obj.name}' does not exist on disk."}

        try:
            from gitbridge.services.antigravity_service import ANTIGRAVITY_IDE_PATHS
            ide_exe = next((p for p in ANTIGRAVITY_IDE_PATHS if os.path.exists(p)), None)
            if ide_exe:
                subprocess.Popen([ide_exe, os.path.abspath(local_path)], cwd=local_path, shell=ide_exe.lower().endswith(".cmd"))
                return {
                    "success": True,
                    "local_path": local_path,
                    "ide_path": ide_exe,
                    "message": f"Opened '{app_obj.name}' in Antigravity ({os.path.basename(ide_exe)})!"
                }
            cmd = f'start cmd /k "cd /d "{local_path}" && title Antigravity Agent CLI - {app_obj.name} && echo Launching Antigravity CLI in {local_path}... & agy || echo Antigravity CLI started in {local_path}"'
            subprocess.Popen(cmd, shell=True)
            return {
                "success": True,
                "local_path": local_path,
                "message": f"Launched Antigravity CLI terminal for '{app_obj.name}' in directory: {local_path}"
            }
        except Exception as e:
            return {"success": False, "message": f"Failed to launch Antigravity: {e}"}
