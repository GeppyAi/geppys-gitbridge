import os
import json
import csv
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()

class GoogleDriveService:
    def __init__(self, folder_id: Optional[str] = None, credentials_path: Optional[str] = None):
        self.folder_id = folder_id or os.getenv("GOOGLE_DRIVE_FOLDER_ID")
        self.credentials_path = credentials_path or os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
        self.service = None
        self.local_reports_dir = os.path.abspath("reports")
        self.local_cards_dir = os.path.join(self.local_reports_dir, "health_cards")
        
        os.makedirs(self.local_cards_dir, exist_ok=True)
        self._init_client()

    def _init_client(self):
        """Initialize Google Drive API client if credentials exist."""
        if os.path.exists(self.credentials_path) and self.folder_id:
            try:
                from google.oauth2.service_account import Credentials
                from googleapiclient.discovery import build

                scopes = ["https://www.googleapis.com/auth/drive.file"]
                creds = Credentials.from_service_account_file(self.credentials_path, scopes=scopes)
                self.service = build("drive", "v3", credentials=creds)
                print("[DriveService] Google Drive API client initialized successfully.")
            except Exception as e:
                print(f"[DriveService] Could not initialize Google Drive client: {e}")

    def save_health_report(self, slug: str, app_name: str, health_card_md: str) -> str:
        """Save App Health Card (.md) locally and optionally sync to Google Drive."""
        safe_name = app_name.replace(" ", "-").replace("/", "-")
        filename = f"{safe_name}-Health.md"
        local_filepath = os.path.join(self.local_cards_dir, filename)

        with open(local_filepath, "w", encoding="utf-8") as f:
            f.write(health_card_md)

        if self.service and self.folder_id:
            try:
                from googleapiclient.http import MediaFileUpload
                
                # Check if file exists in folder
                query = f"'{self.folder_id}' in parents and name = '{filename}' and trashed = false"
                results = self.service.files().list(q=query, fields="files(id, name)").execute()
                files = results.get("files", [])

                media = MediaFileUpload(local_filepath, mimetype="text/markdown", resumable=True)

                if files:
                    file_id = files[0]["id"]
                    self.service.files().update(fileId=file_id, media_body=media).execute()
                    print(f"[DriveService] Updated '{filename}' in Google Drive.")
                else:
                    file_metadata = {
                        "name": filename,
                        "parents": [self.folder_id],
                        "mimeType": "text/markdown"
                    }
                    self.service.files().create(body=file_metadata, media_body=media, fields="id").execute()
                    print(f"[DriveService] Uploaded '{filename}' to Google Drive.")
            except Exception as e:
                print(f"[DriveService] Failed to sync '{filename}' to Google Drive: {e}")

        return local_filepath

    def sync_master_catalog_files(self, app_profiles: List[Dict[str, Any]]) -> Dict[str, str]:
        """Save Master CSV & Master JSON locally and sync to Google Drive."""
        json_path = os.path.join(self.local_reports_dir, "app_universe_master.json")
        csv_path = os.path.join(self.local_reports_dir, "app_universe_master.csv")

        # 1. Master JSON
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(app_profiles, f, indent=2, default=str)

        # 2. Master CSV
        headers = [
            "Slug", "Name", "Priority Tier", "Status", "Description", "GitHub URL",
            "Tech Stack", "Open Issues Count", "Last Commit At", "Tags", "Version"
        ]
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            for app in app_profiles:
                writer.writerow([
                    app.get("slug", ""),
                    app.get("name", ""),
                    app.get("priority_tier", "Tier 2 (Core Infrastructure)"),
                    app.get("status", ""),
                    app.get("description", ""),
                    app.get("github_url", ""),
                    ", ".join(app.get("tech_stack", []) if isinstance(app.get("tech_stack"), list) else []),
                    app.get("open_issues_count", 0),
                    str(app.get("last_commit_at", "") or ""),
                    ", ".join(app.get("tags", []) if isinstance(app.get("tags"), list) else []),
                    app.get("version", "")
                ])

        # 3. Google Drive Sync if active
        if self.service and self.folder_id:
            for file_path, mime in [(json_path, "application/json"), (csv_path, "text/csv")]:
                fname = os.path.basename(file_path)
                try:
                    from googleapiclient.http import MediaFileUpload
                    query = f"'{self.folder_id}' in parents and name = '{fname}' and trashed = false"
                    results = self.service.files().list(q=query, fields="files(id, name)").execute()
                    files = results.get("files", [])
                    media = MediaFileUpload(file_path, mimetype=mime, resumable=True)

                    if files:
                        self.service.files().update(fileId=files[0]["id"], media_body=media).execute()
                    else:
                        meta = {"name": fname, "parents": [self.folder_id], "mimeType": mime}
                        self.service.files().create(body=meta, media_body=media, fields="id").execute()
                    print(f"[DriveService] Synced master file '{fname}' to Google Drive.")
                except Exception as e:
                    print(f"[DriveService] Drive sync error for '{fname}': {e}")

        return {"json": json_path, "csv": csv_path}
