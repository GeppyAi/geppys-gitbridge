import os
import re
import csv
import io
import json
import requests
from datetime import datetime
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv, set_key

load_dotenv()


class GoogleSheetsService:
    def __init__(self, spreadsheet_id: Optional[str] = None, credentials_path: Optional[str] = None):
        state = self.get_state()
        raw_sheet = spreadsheet_id or state.get("sheet_url") or state.get("spreadsheet_id") or os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID", "")
        self.sheet_url = raw_sheet if raw_sheet.startswith("http") else state.get("sheet_url", "")
        self.spreadsheet_id = self.extract_spreadsheet_id(raw_sheet)
        if not self.sheet_url and self.spreadsheet_id:
            self.sheet_url = f"https://docs.google.com/spreadsheets/d/{self.spreadsheet_id}/edit"
        self.webhook_url = state.get("webhook_url", "") or os.getenv("GOOGLE_SHEETS_WEBHOOK_URL", "")
        self.sheet_tab = state.get("sheet_tab", "") or "Sheet1"
        self.credentials_path = credentials_path or state.get("credentials_path") or os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
        self.service = None
        self.init_error: Optional[str] = None
        self._init_client()

    @staticmethod
    def _get_state_path() -> str:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        data_dir = os.path.join(base_dir, "db")
        os.makedirs(data_dir, exist_ok=True)
        return os.path.join(data_dir, "sheets_sync_state.json")

    @staticmethod
    def extract_spreadsheet_id(value: str) -> str:
        clean = (value or "").strip()
        if not clean:
            return ""
        m = re.search(r"spreadsheets/d/([a-zA-Z0-9_-]+)", clean)
        if m:
            return m.group(1)
        if re.match(r"^[a-zA-Z0-9_-]{15,}$", clean):
            return clean
        return ""

    @classmethod
    def get_state(cls) -> Dict[str, Any]:
        path = cls._get_state_path()
        env_id = os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID", "").strip()
        default_state = {
            "sheet_url": f"https://docs.google.com/spreadsheets/d/{env_id}/edit" if env_id and not env_id.startswith("http") else env_id,
            "spreadsheet_id": cls.extract_spreadsheet_id(env_id),
            "webhook_url": os.getenv("GOOGLE_SHEETS_WEBHOOK_URL", "").strip(),
            "sheet_tab": "Sheet1",
            "credentials_path": os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json"),
            "last_synced_at": None,
            "last_sync_mode": None,
            "last_row_count": 0,
            "last_status_message": "Ready to sync"
        }
        if not os.path.exists(path):
            return default_state
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for k, v in default_state.items():
                if k not in data:
                    data[k] = v
            if data.get("sheet_url") and not data.get("spreadsheet_id"):
                data["spreadsheet_id"] = cls.extract_spreadsheet_id(data["sheet_url"])
            return data
        except Exception:
            return default_state

    @classmethod
    def save_state(cls, state: Dict[str, Any]) -> Dict[str, Any]:
        path = cls._get_state_path()
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2, default=str)
        except Exception as e:
            print(f"[SheetsService] Could not save state: {e}")
        return state

    @classmethod
    def update_config(cls, payload: Dict[str, Any]) -> Dict[str, Any]:
        state = cls.get_state()
        if "sheet_url" in payload or "spreadsheet_id" in payload:
            raw = str(payload.get("sheet_url") or payload.get("spreadsheet_id") or "").strip()
            extracted_id = cls.extract_spreadsheet_id(raw)
            state["spreadsheet_id"] = extracted_id
            if raw.startswith("http"):
                state["sheet_url"] = raw
            elif extracted_id:
                state["sheet_url"] = f"https://docs.google.com/spreadsheets/d/{extracted_id}/edit"
            else:
                state["sheet_url"] = ""

            env_file = os.path.abspath(".env")
            if os.path.exists(env_file):
                try:
                    set_key(env_file, "GOOGLE_SHEETS_SPREADSHEET_ID", extracted_id)
                except Exception:
                    pass
            os.environ["GOOGLE_SHEETS_SPREADSHEET_ID"] = extracted_id

        if "webhook_url" in payload:
            wh = str(payload.get("webhook_url") or "").strip()
            state["webhook_url"] = wh
            env_file = os.path.abspath(".env")
            if os.path.exists(env_file):
                try:
                    set_key(env_file, "GOOGLE_SHEETS_WEBHOOK_URL", wh)
                except Exception:
                    pass
            os.environ["GOOGLE_SHEETS_WEBHOOK_URL"] = wh

        if "sheet_tab" in payload and str(payload.get("sheet_tab") or "").strip():
            state["sheet_tab"] = str(payload["sheet_tab"]).strip()

        return cls.save_state(state)

    def _init_client(self):
        """Initialize Google Sheets API client if credentials exist."""
        if os.path.exists(self.credentials_path) and self.spreadsheet_id:
            try:
                from google.oauth2.service_account import Credentials
                from googleapiclient.discovery import build

                scopes = ["https://www.googleapis.com/auth/spreadsheets"]
                creds = Credentials.from_service_account_file(self.credentials_path, scopes=scopes)
                self.service = build("sheets", "v4", credentials=creds)
            except Exception as e:
                self.init_error = str(e)
                print(f"[SheetsService] Could not initialize Google Sheets client: {e}")

    @staticmethod
    def build_headers() -> List[str]:
        return [
            "Slug", "Name", "Status", "Priority Tier", "Description", "GitHub URL",
            "Live URL", "AI Studio Link", "Tech Stack", "Tags", "Active Tasks",
            "Completed Tasks", "Version", "Updated At"
        ]

    @classmethod
    def build_rows(cls, app_profiles: List[Dict[str, Any]]) -> List[List[str]]:
        headers = cls.build_headers()
        rows = [headers]
        for app in app_profiles:
            backlog = app.get("backlog") or []
            if isinstance(backlog, str):
                try:
                    backlog = json.loads(backlog)
                except Exception:
                    backlog = []
            active_tasks = [t.get("title", "") for t in backlog if isinstance(t, dict) and not t.get("completed")]
            done_tasks = [t.get("title", "") for t in backlog if isinstance(t, dict) and t.get("completed")]
            rows.append([
                str(app.get("slug") or ""),
                str(app.get("name") or ""),
                str(app.get("status") or ""),
                str(app.get("priority_tier") or "Tier 2"),
                str(app.get("description") or ""),
                str(app.get("github_url") or ""),
                str(app.get("live_url") or ""),
                str(app.get("ai_studio_link") or ""),
                ", ".join(app.get("tech_stack") or []),
                ", ".join(app.get("tags") or []),
                f"{len(active_tasks)} active" + (f": {'; '.join(active_tasks[:5])}" if active_tasks else ""),
                f"{len(done_tasks)} done",
                str(app.get("version") or "0.1.0"),
                str(app.get("updated_at") or "")
            ])
        return rows

    def export_to_csv_preview(self, app_profiles: List[Dict[str, Any]], output_path: str = "app_universe_export.csv") -> str:
        """Export catalog profiles to a local CSV file AND the _Gemini_Bridge synced folder."""
        rows = self.build_rows(app_profiles)
        with open(output_path, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerows(rows)

        # Also mirror to _Gemini_Bridge folder so Google Drive for Desktop syncs it automatically
        try:
            from gitbridge.services.workspace_service import WorkspaceService
            ws_dirs = WorkspaceService.get_workspace_dirs()
            primary = ws_dirs[0] if ws_dirs else "d:\\Geppy_Apps"
            bridge_dir = os.path.join(primary, "_Gemini_Bridge")
            os.makedirs(bridge_dir, exist_ok=True)
            bridge_csv = os.path.join(bridge_dir, "app_universe_export.csv")
            with open(bridge_csv, mode="w", newline="", encoding="utf-8") as bf:
                writer = csv.writer(bf)
                writer.writerows(rows)
        except Exception:
            pass

        return os.path.abspath(output_path)

    def build_tsv(self, app_profiles: List[Dict[str, Any]]) -> str:
        """Build Tab-Separated Values string ready for direct Ctrl+V paste into Google Sheets."""
        rows = self.build_rows(app_profiles)
        output = io.StringIO()
        writer = csv.writer(output, delimiter="\t", lineterminator="\n")
        for r in rows:
            clean_row = [str(cell).replace("\r", " ").replace("\n", " ").replace("\t", " ") for cell in r]
            writer.writerow(clean_row)
        return output.getvalue()

    def sync_catalog_to_sheets(self, app_profiles: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Sync app profiles array to Google Sheets via:
        1. Google Sheets API v4 (if Service Account credentials.json + spreadsheet_id are present)
        2. Google Apps Script Webhook URL (if webhook_url is configured)
        3. Always exports app_universe_export.csv + _Gemini_Bridge/app_universe_export.csv + TSV clipboard data
        """
        rows = self.build_rows(app_profiles)
        csv_path = self.export_to_csv_preview(app_profiles)
        tsv_data = self.build_tsv(app_profiles)

        cloud_updated = False
        mode_used = "local_csv_and_tsv"
        detail_msg = f"Exported {len(app_profiles)} apps to {os.path.basename(csv_path)} & _Gemini_Bridge."
        api_error = None

        # 1. Try Google Apps Script Webhook if configured
        if self.webhook_url and self.webhook_url.startswith("http"):
            try:
                res = requests.post(
                    self.webhook_url,
                    json={
                        "spreadsheet_id": self.spreadsheet_id,
                        "sheet_tab": self.sheet_tab or "Sheet1",
                        "headers": rows[0],
                        "rows": rows[1:],
                        "values": rows,
                        "updated_at": datetime.utcnow().isoformat()
                    },
                    timeout=15
                )
                if res.status_code in (200, 201, 302):
                    cloud_updated = True
                    mode_used = "apps_script_webhook"
                    detail_msg = f"Pushed {len(app_profiles)} apps directly to Google Sheets via Apps Script Webhook!"
                else:
                    api_error = f"Webhook returned HTTP {res.status_code}: {res.text[:160]}"
            except Exception as e:
                api_error = f"Webhook error: {e}"

        # 2. Try Google Sheets Service Account API v4 if configured
        if not cloud_updated and self.service and self.spreadsheet_id:
            try:
                body = {"values": rows}
                target_range = f"{self.sheet_tab}!A1" if self.sheet_tab else "A1"
                try:
                    self.service.spreadsheets().values().update(
                        spreadsheetId=self.spreadsheet_id,
                        range=target_range,
                        valueInputOption="USER_ENTERED",
                        body=body
                    ).execute()
                except Exception:
                    # Fallback to first sheet A1 if named tab doesn't exist
                    self.service.spreadsheets().values().update(
                        spreadsheetId=self.spreadsheet_id,
                        range="A1",
                        valueInputOption="USER_ENTERED",
                        body=body
                    ).execute()
                cloud_updated = True
                mode_used = "google_sheets_api_v4"
                detail_msg = f"Synced {len(app_profiles)} apps directly to Google Sheet ({self.spreadsheet_id[:12]}...)!"
            except Exception as e:
                api_error = str(e)
                print(f"[SheetsService] Failed to sync to Google Sheets API: {e}")

        state = self.get_state()
        state["last_synced_at"] = datetime.now().isoformat()
        state["last_sync_mode"] = mode_used
        state["last_row_count"] = len(app_profiles)
        state["last_status_message"] = detail_msg if not api_error else f"{detail_msg} (Cloud note: {api_error})"
        self.save_state(state)

        return {
            "success": True,
            "google_sheets_updated": cloud_updated,
            "mode_used": mode_used,
            "rows_exported": len(app_profiles),
            "csv_path": csv_path,
            "sheet_url": self.sheet_url,
            "spreadsheet_id": self.spreadsheet_id,
            "has_service_account": os.path.exists(self.credentials_path),
            "has_webhook": bool(self.webhook_url),
            "api_error": api_error,
            "message": detail_msg,
            "tsv": tsv_data,
            "preview_headers": rows[0],
            "preview_rows": rows[1:35]
        }

    def pull_catalog_from_sheet(self, db) -> Dict[str, Any]:
        """
        Pull app updates from the linked Google Sheet URL (via /export?format=csv)
        and update matching AppProfileModel records in GitBridge.
        """
        from gitbridge.db.models import AppProfileModel, AppStatus

        if not self.spreadsheet_id:
            return {
                "success": False,
                "message": "No Google Sheet URL or Spreadsheet ID configured yet. Paste your Google Sheet link above first."
            }

        export_url = f"https://docs.google.com/spreadsheets/d/{self.spreadsheet_id}/export?format=csv"
        try:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) GitBridge/1.0"}
            res = requests.get(export_url, headers=headers, timeout=15)
            if res.status_code != 200 or not res.text:
                return {
                    "success": False,
                    "message": f"Could not fetch Google Sheet CSV (HTTP {res.status_code}). Ensure the sheet is shared as 'Anyone with the link can view'."
                }
            if "<!DOCTYPE html>" in res.text[:300] and "accounts.google.com" in res.text[:2000]:
                return {
                    "success": False,
                    "message": "Google Sheet requires sign-in. In Google Sheets, click Share -> 'Anyone with the link' (Viewer) so GitBridge can pull from it."
                }

            reader = csv.DictReader(io.StringIO(res.text))
            updated_count = 0
            checked_count = 0
            for row in reader:
                norm_row = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
                slug = norm_row.get("slug") or norm_row.get("app slug")
                if not slug:
                    continue
                checked_count += 1
                app_obj = db.query(AppProfileModel).filter(AppProfileModel.slug == slug).first()
                if not app_obj:
                    continue
                changed = False
                if norm_row.get("name") and norm_row["name"] != app_obj.name:
                    app_obj.name = norm_row["name"]
                    changed = True
                if norm_row.get("description") and norm_row["description"] != (app_obj.description or ""):
                    app_obj.description = norm_row["description"]
                    changed = True
                if norm_row.get("github url") and norm_row["github url"] != (app_obj.github_url or ""):
                    app_obj.github_url = norm_row["github url"]
                    changed = True
                if norm_row.get("ai studio link") and norm_row["ai studio link"] != (app_obj.ai_studio_link or ""):
                    app_obj.ai_studio_link = norm_row["ai studio link"]
                    changed = True
                if norm_row.get("version") and norm_row["version"] != (app_obj.version or ""):
                    app_obj.version = norm_row["version"]
                    changed = True
                if norm_row.get("status"):
                    st_val = norm_row["status"].lower().strip()
                    for st_enum in AppStatus:
                        if st_enum.value == st_val:
                            if app_obj.status != st_enum:
                                app_obj.status = st_enum
                                changed = True
                            break
                if changed:
                    updated_count += 1

            if updated_count > 0:
                db.commit()

            state = self.get_state()
            state["last_synced_at"] = datetime.now().isoformat()
            state["last_sync_mode"] = "pull_from_google_sheet"
            state["last_status_message"] = f"Pulled {checked_count} rows from Google Sheet ({updated_count} app profiles updated)."
            self.save_state(state)

            return {
                "success": True,
                "rows_checked": checked_count,
                "apps_updated": updated_count,
                "message": f"Pulled {checked_count} rows from Google Sheet ({updated_count} app profiles updated)."
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to pull from Google Sheet: {e}"
            }
