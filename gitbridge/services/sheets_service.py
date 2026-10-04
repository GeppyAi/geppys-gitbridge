import os
import json
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()

class GoogleSheetsService:
    def __init__(self, spreadsheet_id: Optional[str] = None, credentials_path: Optional[str] = None):
        self.spreadsheet_id = spreadsheet_id or os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID")
        self.credentials_path = credentials_path or os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
        self.service = None
        self._init_client()

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
                print(f"[SheetsService] Could not initialize Google Sheets client: {e}")

    def export_to_csv_preview(self, app_profiles: List[Dict[str, Any]], output_path: str = "app_universe_export.csv") -> str:
        """Export catalog profiles to a local CSV file (fallback / preview format)."""
        import csv
        headers = [
            "Slug", "Name", "Status", "Description", "GitHub URL",
            "AI Studio Link", "Tech Stack", "Tags", "Version", "Updated At"
        ]
        with open(output_path, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            for app in app_profiles:
                writer.writerow([
                    app.get("slug"),
                    app.get("name"),
                    app.get("status"),
                    app.get("description"),
                    app.get("github_url"),
                    app.get("ai_studio_link"),
                    ", ".join(app.get("tech_stack", [])),
                    ", ".join(app.get("tags", [])),
                    app.get("version"),
                    str(app.get("updated_at", ""))
                ])
        return output_path

    def sync_catalog_to_sheets(self, app_profiles: List[Dict[str, Any]]) -> bool:
        """Sync app profiles array directly to configured Google Sheets spreadsheet."""
        if not self.service or not self.spreadsheet_id:
            print("[SheetsService] Warning: Google Sheets credentials or SPREADSHEET_ID missing. Fallback to local CSV/JSON export.")
            self.export_to_csv_preview(app_profiles)
            return False

        headers = [
            "Slug", "Name", "Status", "Description", "GitHub URL",
            "AI Studio Link", "Tech Stack", "Tags", "Version", "Updated At"
        ]
        rows = [headers]
        for app in app_profiles:
            rows.append([
                app.get("slug", ""),
                app.get("name", ""),
                app.get("status", ""),
                app.get("description", ""),
                app.get("github_url", ""),
                app.get("ai_studio_link", ""),
                ", ".join(app.get("tech_stack", [])),
                ", ".join(app.get("tags", [])),
                app.get("version", ""),
                str(app.get("updated_at", ""))
            ])

        try:
            body = {"values": rows}
            self.service.spreadsheets().values().update(
                spreadsheetId=self.spreadsheet_id,
                range="AppCatalog!A1",
                valueInputOption="USER_ENTERED",
                body=body
            ).execute()
            return True
        except Exception as e:
            print(f"[SheetsService] Failed to sync to Google Sheets: {e}")
            return False
