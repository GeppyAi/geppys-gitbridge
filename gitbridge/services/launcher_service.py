import os
import subprocess
import webbrowser
from typing import Dict, Any, Optional

class AppLauncherService:
    @staticmethod
    def detect_local_path(app_obj) -> Optional[str]:
        """Auto-detect if application exists in Geppy's App Universe directory."""
        if app_obj.local_path and os.path.exists(app_obj.local_path):
            return app_obj.local_path

        candidates = [
            os.path.join("d:\\Geppy_Apps", app_obj.slug),
            os.path.join("d:\\Geppy_Apps", app_obj.name),
            os.path.join("d:\\Geppy_Apps", app_obj.name.replace(" ", "-")),
            os.path.join("d:\\Geppy_Apps", app_obj.name.replace(" ", "_")),
        ]
        if app_obj.github_repo_name and "/" in app_obj.github_repo_name:
            repo_basename = app_obj.github_repo_name.split("/")[-1]
            candidates.append(os.path.join("d:\\Geppy_Apps", repo_basename))

        for path in candidates:
            if os.path.exists(path):
                return path
        return None

    @staticmethod
    def open_in_browser(url: str) -> bool:
        """Open web URL in default browser."""
        if not url:
            return False
        if not url.startswith("http://") and not url.startswith("https://"):
            url = "https://" + url
        webbrowser.open(url)
        return True

    @staticmethod
    def open_local_folder(folder_path: str) -> bool:
        """Open directory in Windows File Explorer."""
        if not folder_path or not os.path.exists(folder_path):
            return False
        try:
            os.startfile(folder_path)
            return True
        except Exception:
            subprocess.Popen(["explorer", folder_path])
            return True

    @staticmethod
    def launch_app(app_obj) -> Dict[str, Any]:
        """Launch application using live URL, local command, AI Studio link, or GitHub repo."""
        local_path = AppLauncherService.detect_local_path(app_obj)

        # 1. If Live URL exists, open in browser
        if app_obj.live_url:
            AppLauncherService.open_in_browser(app_obj.live_url)
            return {
                "launched": True,
                "action": "opened_live_url",
                "target": app_obj.live_url,
                "message": f"Opened live app URL in browser: {app_obj.live_url}"
            }

        # 2. If Local Command exists and local directory exists, execute local process
        if app_obj.launch_command and local_path:
            try:
                subprocess.Popen(app_obj.launch_command, cwd=local_path, shell=True)
                return {
                    "launched": True,
                    "action": "executed_local_command",
                    "target": app_obj.launch_command,
                    "message": f"Started local process '{app_obj.launch_command}' in {local_path}"
                }
            except Exception as e:
                pass

        # 3. If AI Studio link exists, open in browser
        if app_obj.ai_studio_link:
            AppLauncherService.open_in_browser(app_obj.ai_studio_link)
            return {
                "launched": True,
                "action": "opened_ai_studio_link",
                "target": app_obj.ai_studio_link,
                "message": f"Opened AI Studio project in browser: {app_obj.ai_studio_link}"
            }

        # 4. If GitHub URL exists, open in browser
        if app_obj.github_url:
            AppLauncherService.open_in_browser(app_obj.github_url)
            return {
                "launched": True,
                "action": "opened_github_url",
                "target": app_obj.github_url,
                "message": f"Opened GitHub repository in browser: {app_obj.github_url}"
            }

        # 5. Fallback: If local directory detected, open local folder
        if local_path:
            AppLauncherService.open_local_folder(local_path)
            return {
                "launched": True,
                "action": "opened_local_folder",
                "target": local_path,
                "message": f"Opened local project folder in Explorer: {local_path}"
            }

        return {
            "launched": False,
            "action": "none",
            "target": None,
            "message": "No live URL, GitHub repo, AI Studio link, or local path configured for this app."
        }
