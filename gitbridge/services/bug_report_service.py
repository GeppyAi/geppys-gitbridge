import os
import json
import time
from datetime import datetime
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from gitbridge.db.models import AppProfileModel
from gitbridge.services.workspace_service import WorkspaceService
from gitbridge.services.antigravity_service import AntigravityDaemonPool, AntigravityService
from gitbridge.services.extension_service import ExtensionService
from gitbridge.services.central_key_service import CentralKeyService

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUG_STATE_PATH = os.path.join(BASE_DIR, "db", "bug_reports_state.json")


class BugReportService:
    """
    Universal Bug Reporting & App Update Service for Geppy's GitBridge.
    Powers the universal Report Bug badge (GeppyBug.png) and Update App widget across
    all applications in Geppy's App Universe, GitBridge Dashboard, and Geppy's Galactic.
    """

    @staticmethod
    def _load_state() -> Dict[str, Any]:
        if os.path.exists(BUG_STATE_PATH):
            try:
                with open(BUG_STATE_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        data.setdefault("reports", [])
                        return data
            except Exception as e:
                print(f"[BugReportService] Failed to read {BUG_STATE_PATH}: {e}")
        return {"reports": []}

    @staticmethod
    def _save_state(state: Dict[str, Any]) -> None:
        try:
            os.makedirs(os.path.dirname(BUG_STATE_PATH), exist_ok=True)
            with open(BUG_STATE_PATH, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            print(f"[BugReportService] Failed to write {BUG_STATE_PATH}: {e}")

    @classmethod
    def list_bug_reports(
        cls,
        slug: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        state = cls._load_state()
        reports = state.get("reports", [])
        if slug:
            clean_slug = slug.strip().lower()
            reports = [r for r in reports if (r.get("app_slug") or "").lower() == clean_slug]
        if status:
            clean_status = status.strip().lower()
            reports = [r for r in reports if (r.get("status") or "").lower() == clean_status]
        return reports[:limit]

    @classmethod
    def update_bug_status(cls, bug_id: str, status: str, resolution_note: Optional[str] = None, db: Optional[Session] = None) -> Optional[Dict[str, Any]]:
        state = cls._load_state()
        target = None
        for r in state.get("reports", []):
            if r.get("id") == bug_id:
                r["status"] = status
                r["updated_at"] = datetime.utcnow().isoformat()
                if resolution_note:
                    r["resolution_note"] = resolution_note
                target = r
                break
        if target:
            cls._save_state(state)
            if db and target.get("app_slug"):
                app_obj = db.query(AppProfileModel).filter(AppProfileModel.slug == target["app_slug"]).first()
                if app_obj:
                    open_bugs = [
                        b for b in state.get("reports", [])
                        if b.get("app_slug") == app_obj.slug and b.get("status") == "open"
                    ]
                    app_obj.open_issues_count = len(open_bugs)
                    db.commit()
        return target

    @classmethod
    def submit_bug_report(cls, payload: Dict[str, Any], db: Session) -> Dict[str, Any]:
        """
        Record a bug report from any app in Geppy's App Universe (or GitBridge / Galactic):
        1. Auto-detects or resolves the target AppProfileModel.
        2. Saves structured bug report to bug_reports_state.json & updates open_issues_count.
        3. Appends to the app's Health Card markdown and backlog tasks.
        4. Records diagnosis in AntigravityDaemonPool.
        5. Optionally creates a GitHub Issue or triggers an immediate AI / Antigravity code fix.
        """
        raw_slug = (payload.get("app_slug") or payload.get("slug") or "").strip()
        url = (payload.get("url") or payload.get("page_url") or "").strip()
        title = (payload.get("title") or "").strip()
        description = (payload.get("description") or payload.get("message") or "").strip()
        severity = (payload.get("severity") or "high").strip().lower()
        console_errors = payload.get("console_errors") or []
        if isinstance(console_errors, str):
            console_errors = [line.strip() for line in console_errors.splitlines() if line.strip()]
        target_file = (payload.get("file_path") or payload.get("target_file") or "").strip()
        auto_fix = bool(payload.get("auto_fix", False))
        send_to_crew = bool(payload.get("send_to_crew", True))
        log_to_health_card = bool(payload.get("log_to_health_card", True))
        create_github_issue = bool(payload.get("create_github_issue", False))

        # 1. Resolve App Profile
        app_obj = None
        if raw_slug:
            app_obj = db.query(AppProfileModel).filter(AppProfileModel.slug == raw_slug).first()

        if not app_obj and url:
            from gitbridge.services.launcher_service import ACTIVE_SERVERS
            detected = ExtensionService.detect_active_app(url, ACTIVE_SERVERS, db)
            if detected and detected.get("slug"):
                app_obj = db.query(AppProfileModel).filter(AppProfileModel.slug == detected["slug"]).first()

        if not app_obj:
            # Fallback to geppys-gitbridge if reported on port 8000 or unrecognized
            app_obj = db.query(AppProfileModel).filter(
                AppProfileModel.slug.in_(["geppys-gitbridge", "geppy-s-gitbridge"])
            ).first()

        resolved_slug = app_obj.slug if app_obj else (raw_slug or "geppys-gitbridge")
        resolved_name = app_obj.name if app_obj else (payload.get("app_name") or resolved_slug)

        if not title:
            if description:
                first_line = description.splitlines()[0][:72]
                title = first_line
            elif console_errors:
                title = f"Runtime Error: {str(console_errors[0])[:65]}"
            else:
                title = f"Bug Report in {resolved_name}"

        if not description:
            description = title

        # Resolve target file if not provided
        if not target_file and app_obj:
            try:
                target_file = ExtensionService.resolve_best_target_file(
                    app_obj,
                    f"{title} {description} {' '.join(console_errors[:3])}"
                )
            except Exception:
                target_file = "index.html"

        bug_id = f"bug_{int(time.time())}_{os.urandom(2).hex()}"
        now_iso = datetime.utcnow().isoformat()

        # 2. Diagnose via Antigravity Watchdog Pool
        combined_error_text = f"[{severity.upper()} BUG] {title}\nDetails: {description}"
        if console_errors:
            combined_error_text += "\nConsole/Runtime Errors:\n" + "\n".join(str(e) for e in console_errors[:8])

        ag_diagnosis = None
        try:
            ag_diagnosis = AntigravityDaemonPool.diagnose_and_record_error(
                raw_error=combined_error_text,
                source="geppy-bug-reporter",
                slug=resolved_slug,
                app_name=resolved_name,
                file_path=target_file or "index.html",
                instruction=f"Fix reported bug: {title} — {description}",
                error_type_hint="runtime_bug",
            )
        except Exception as e:
            print(f"[BugReportService] Antigravity diagnosis notice: {e}")

        # 3. Build Bug Record
        bug_record: Dict[str, Any] = {
            "id": bug_id,
            "app_slug": resolved_slug,
            "app_name": resolved_name,
            "title": title,
            "description": description,
            "severity": severity,
            "url": url,
            "target_file": target_file or "index.html",
            "console_errors": console_errors[:15],
            "user_agent": payload.get("user_agent") or "",
            "viewport": payload.get("viewport") or "",
            "status": "open",
            "created_at": now_iso,
            "updated_at": now_iso,
            "antigravity_error_id": ag_diagnosis.get("id") if isinstance(ag_diagnosis, dict) else None,
            "diagnosis_summary": (
                ag_diagnosis.get("what_needs_done")
                if isinstance(ag_diagnosis, dict)
                else f"Inspect `{target_file or 'index.html'}` to resolve: {title}"
            ),
            "suggested_fix_prompt": (
                f"Fix the following {severity} bug in `{target_file or 'index.html'}`: {title}. "
                f"Details: {description}"
                + (f" Console errors: {'; '.join(str(x) for x in console_errors[:3])}" if console_errors else "")
            ),
            "github_issue_url": None,
            "auto_fix_result": None,
        }

        # 4. Update AppProfileModel (backlog, health_report_md, open_issues_count, BUGS.md)
        if app_obj:
            try:
                # Add to backlog so Galactic & GitBridge show it as an actionable task
                backlog = list(app_obj.backlog or [])
                backlog_task = {
                    "id": bug_id,
                    "title": f"🐞 Fix Bug: {title[:65]}",
                    "category": f"Bug Fix ({severity.upper()})",
                    "priority": "high" if severity in ("critical", "high") else "medium",
                    "target_file": target_file or "index.html",
                    "description": description[:280],
                    "suggested_prompt": bug_record["suggested_fix_prompt"],
                    "status": "pending",
                    "source": "GeppyBug Reporter",
                    "created_at": now_iso,
                }
                backlog.insert(0, backlog_task)
                app_obj.backlog = backlog[:50]

                if log_to_health_card:
                    timestamp_human = datetime.now().strftime("%Y-%m-%d %H:%M")
                    bug_md_entry = (
                        f"\n\n### 🐞 Reported Bug [{timestamp_human}] — `{bug_id}` ({severity.upper()})\n"
                        f"- **Title:** {title}\n"
                        f"- **Target File:** `{target_file or 'index.html'}`\n"
                        f"- **Description:** {description}\n"
                    )
                    if console_errors:
                        bug_md_entry += f"- **Console Errors:** `{str(console_errors[0])[:200]}`\n"
                    bug_md_entry += f"- **Recommended Fix:** {bug_record['diagnosis_summary']}\n"

                    existing_health = app_obj.health_report_md or f"# {app_obj.name} — Health & Bug Card\n"
                    app_obj.health_report_md = existing_health + bug_md_entry

                    # Also append to local BUGS.md in the app directory if local_path exists
                    if app_obj.local_path and os.path.exists(app_obj.local_path):
                        bugs_file = os.path.join(app_obj.local_path, "BUGS.md")
                        header = f"# 🐞 Bug Reports — {app_obj.name}\n"
                        existing_bugs_md = ""
                        if os.path.exists(bugs_file):
                            try:
                                with open(bugs_file, "r", encoding="utf-8", errors="ignore") as bf:
                                    existing_bugs_md = bf.read()
                            except Exception:
                                pass
                        if not existing_bugs_md.strip():
                            existing_bugs_md = header
                        try:
                            with open(bugs_file, "w", encoding="utf-8") as bf:
                                bf.write(existing_bugs_md.rstrip() + bug_md_entry + "\n")
                        except Exception as e:
                            print(f"[BugReportService] Failed writing BUGS.md: {e}")

                db.commit()
            except Exception as e:
                print(f"[BugReportService] Error updating app_obj for bug report: {e}")

        # 5. Optional: Create GitHub Issue if requested and repo exists
        if create_github_issue and app_obj and app_obj.github_repo_name:
            try:
                import requests
                token = os.getenv("GITHUB_TOKEN", "").strip()
                if token:
                    gh_api_url = f"https://api.github.com/repos/{app_obj.github_repo_name}/issues"
                    issue_body = (
                        f"### 🐞 GeppyBug Report (`{bug_id}`)\n\n"
                        f"**Severity:** `{severity.upper()}`\n"
                        f"**Target File:** `{target_file or 'index.html'}`\n"
                        f"**Page URL:** {url or 'Localhost'}\n\n"
                        f"#### Description\n{description}\n"
                    )
                    if console_errors:
                        issue_body += "\n#### Console / Runtime Logs\n```\n" + "\n".join(str(x) for x in console_errors[:10]) + "\n```\n"
                    gh_res = requests.post(
                        gh_api_url,
                        headers={
                            "Authorization": f"token {token}",
                            "Accept": "application/vnd.github.v3+json"
                        },
                        json={"title": f"[GeppyBug] {title}", "body": issue_body, "labels": ["bug"]},
                        timeout=10
                    )
                    if gh_res.status_code in (200, 201):
                        bug_record["github_issue_url"] = gh_res.json().get("html_url")
            except Exception as e:
                print(f"[BugReportService] GitHub issue creation notice: {e}")

        # 6. Optional: Trigger Immediate AI / Antigravity Code Fix
        if auto_fix and app_obj:
            try:
                fix_res = ExtensionService.apply_design(
                    slug=resolved_slug,
                    file_path=target_file or "index.html",
                    current_code="",
                    instruction=bug_record["suggested_fix_prompt"],
                    db=db,
                    save_to_disk=True
                )
                bug_record["auto_fix_result"] = {
                    "applied": bool(fix_res.get("applied_to_disk") or fix_res.get("updated_code")),
                    "file_path": fix_res.get("file_path") or target_file,
                    "explanation": fix_res.get("explanation") or "AI patch generated and applied."
                }
                if bug_record["auto_fix_result"]["applied"]:
                    bug_record["status"] = "fixed"
            except Exception as e:
                bug_record["auto_fix_result"] = {"applied": False, "error": str(e)}

        # Save in state & update open_issues_count
        state = cls._load_state()
        state.setdefault("reports", []).insert(0, bug_record)
        state["reports"] = state["reports"][:200]
        cls._save_state(state)

        if app_obj:
            open_count = len([
                r for r in state["reports"]
                if r.get("app_slug") == app_obj.slug and r.get("status") == "open"
            ])
            app_obj.open_issues_count = open_count
            db.commit()

        return {
            "success": True,
            "message": (
                f"🐞 Bug '{title}' logged for {resolved_name}"
                + (" and auto-patched by Antigravity!" if (bug_record.get("auto_fix_result") or {}).get("applied") else " and queued in Backlog & Health Card!")
            ),
            "bug": bug_record,
            "antigravity_error": ag_diagnosis,
        }

    @classmethod
    def trigger_app_update(cls, slug: Optional[str], payload: Dict[str, Any], db: Session) -> Dict[str, Any]:
        """
        Universal "Update App" action for any app in Geppy's App Universe:
        Supports modes:
        - 'sync_all' (default): Syncs Central Gemini API Key + universal bridge widget, pulls/checks git status, and optionally pushes or applies an AI update instruction.
        - 'pull': Pulls latest changes from GitHub (`git pull --rebase` or clone).
        - 'push': Commits and pushes local changes to GitHub.
        - 'ai_update': Applies a natural-language AI update instruction via Antigravity/ExtensionService.
        - 'inject_bridge': Injects the universal `<script src="http://127.0.0.1:8000/static/geppy-key-bridge.js"></script>` into the app's HTML entrypoints.
        """
        url = (payload.get("url") or "").strip()
        mode = (payload.get("mode") or "sync_all").strip().lower()
        instruction = (payload.get("instruction") or payload.get("prompt") or "").strip()
        commit_message = (payload.get("commit_message") or "").strip()

        app_obj = None
        if slug:
            app_obj = db.query(AppProfileModel).filter(AppProfileModel.slug == slug).first()

        if not app_obj and url:
            from gitbridge.services.launcher_service import ACTIVE_SERVERS
            detected = ExtensionService.detect_active_app(url, ACTIVE_SERVERS, db)
            if detected and detected.get("slug"):
                app_obj = db.query(AppProfileModel).filter(AppProfileModel.slug == detected["slug"]).first()

        if not app_obj:
            app_obj = db.query(AppProfileModel).filter(
                AppProfileModel.slug.in_(["geppys-gitbridge", "geppy-s-gitbridge"])
            ).first()

        if not app_obj:
            return {"success": False, "message": f"App '{slug or url}' not found in GitBridge."}

        steps_completed = []
        details: Dict[str, Any] = {
            "slug": app_obj.slug,
            "name": app_obj.name,
            "mode": mode,
        }

        # 1. Always ensure Central Gemini Key is synced to this app's .env
        try:
            CentralKeyService.sync_all_apps()
            steps_completed.append("Synced Central Gemini API Key")
        except Exception as e:
            details["key_sync_notice"] = str(e)

        # 2. If 'inject_bridge' or 'sync_all', ensure geppy-key-bridge.js is linked in HTML entrypoints
        if mode in ("inject_bridge", "sync_all"):
            inj = cls.inject_bridge_into_app(app_obj)
            details["bridge_injection"] = inj
            if inj.get("injected_files"):
                steps_completed.append(f"Injected Geppy Bridge into {', '.join(inj['injected_files'])}")

        # 3. If 'pull' or 'sync_all', pull latest from GitHub if remote exists
        if mode in ("pull", "sync_all") and app_obj.local_path and os.path.exists(app_obj.local_path):
            git_dir = os.path.join(app_obj.local_path, ".git")
            if os.path.exists(git_dir):
                try:
                    pull_res = WorkspaceService._run_git_silent(
                        ["git", "pull", "--no-rebase"],
                        cwd=app_obj.local_path,
                        timeout=25
                    )
                    details["git_pull"] = {
                        "returncode": pull_res.returncode,
                        "stdout": (pull_res.stdout or "").strip()[:300],
                        "stderr": (pull_res.stderr or "").strip()[:300],
                    }
                    if pull_res.returncode == 0:
                        steps_completed.append("Pulled latest changes from GitHub")
                except Exception as e:
                    details["git_pull_error"] = str(e)

        # 4. If 'ai_update' or instruction is provided, execute AI code update
        if mode == "ai_update" or instruction:
            if not instruction:
                instruction = "Review and update the app UI for polish, responsiveness, and bug-free execution."
            target_file = payload.get("file_path") or ExtensionService.resolve_best_target_file(app_obj, instruction)
            ai_res = ExtensionService.apply_design(
                slug=app_obj.slug,
                file_path=target_file,
                current_code="",
                instruction=instruction,
                db=db,
                save_to_disk=True
            )
            details["ai_update"] = {
                "applied": bool(ai_res.get("applied_to_disk") or ai_res.get("updated_code")),
                "file_path": ai_res.get("file_path") or target_file,
                "explanation": ai_res.get("explanation") or "AI update completed."
            }
            if details["ai_update"]["applied"]:
                steps_completed.append(f"Applied AI Update to {details['ai_update']['file_path']}")

        # 5. If 'push' or commit_message is provided, commit & push to GitHub
        if mode == "push" or commit_message:
            push_res = WorkspaceService.push_app_to_github(
                app_obj,
                commit_message=commit_message or f"Update {app_obj.name} via Geppy Bridge",
                push_remote=True,
                db=db
            )
            details["git_push"] = push_res
            if push_res.get("success"):
                steps_completed.append(push_res.get("message") or "Pushed updates to GitHub")

        # 6. Refresh app git status & bump updated_at
        try:
            details["git_status"] = WorkspaceService.get_git_status(app_obj)
            app_obj.updated_at = datetime.utcnow()
            db.commit()
        except Exception:
            pass

        summary_msg = " • ".join(steps_completed) if steps_completed else f"{app_obj.name} is up to date!"
        return {
            "success": True,
            "message": summary_msg,
            "steps_completed": steps_completed,
            "details": details,
        }

    @classmethod
    def inject_bridge_into_app(cls, app_obj: AppProfileModel) -> Dict[str, Any]:
        """
        Ensure `<script src="http://127.0.0.1:8000/static/geppy-key-bridge.js"></script>`
        is present in the app's main HTML file(s) so the universal Report Bug (GeppyBug.png)
        & Update widget appears automatically inside the app.
        """
        if not app_obj or not app_obj.local_path or not os.path.exists(app_obj.local_path):
            return {"success": False, "injected_files": [], "message": "Local path not found"}

        script_tag = '<script src="http://127.0.0.1:8000/static/geppy-key-bridge.js" defer></script>'
        candidate_rel_paths = [
            "index.html",
            "public/index.html",
            "client/index.html",
            "static/index.html",
            "gitbridge/static/index.html",
            "gitbridge/static/geppy_chat.html",
            "src/index.html",
        ]

        injected = []
        already_present = []

        for rel in candidate_rel_paths:
            full_p = os.path.join(app_obj.local_path, rel.replace("/", os.sep))
            if os.path.exists(full_p) and os.path.isfile(full_p):
                try:
                    with open(full_p, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                    if "geppy-key-bridge.js" in content:
                        already_present.append(rel)
                        continue
                    if "</body>" in content:
                        new_content = content.replace("</body>", f"  {script_tag}\n</body>", 1)
                    elif "</head>" in content:
                        new_content = content.replace("</head>", f"  {script_tag}\n</head>", 1)
                    else:
                        new_content = content + f"\n{script_tag}\n"
                    with open(full_p, "w", encoding="utf-8") as f:
                        f.write(new_content)
                    injected.append(rel)
                except Exception as e:
                    print(f"[BugReportService] Could not inject into {full_p}: {e}")

        return {
            "success": True,
            "slug": app_obj.slug,
            "injected_files": injected,
            "already_present": already_present,
        }

    @classmethod
    def inject_bridge_into_all_apps(cls, db: Session) -> Dict[str, Any]:
        """Inject geppy-key-bridge.js into all registered local apps in Geppy's App Universe."""
        apps = db.query(AppProfileModel).all()
        updated_apps = []
        total_injected_files = 0
        for app_obj in apps:
            res = cls.inject_bridge_into_app(app_obj)
            if res.get("injected_files"):
                updated_apps.append({
                    "slug": app_obj.slug,
                    "name": app_obj.name,
                    "injected_files": res["injected_files"]
                })
                total_injected_files += len(res["injected_files"])
        return {
            "success": True,
            "apps_updated_count": len(updated_apps),
            "total_injected_files": total_injected_files,
            "updated_apps": updated_apps,
            "message": f"Injected Universal Update & GeppyBug Reporter Bridge into {len(updated_apps)} apps ({total_injected_files} HTML files)."
        }
