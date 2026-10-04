import json
import zipfile
import os
from typing import Dict, Any, Optional

class AIStudioParser:
    """Parser for AI Studio exported JSON / Zip projects or prompt files."""

    @staticmethod
    def parse_json_export(file_path: str) -> Dict[str, Any]:
        """Parse a standalone AI Studio exported JSON configuration file."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Standard AI Studio JSON structure extraction
        name = data.get("name") or data.get("title") or os.path.basename(file_path).replace(".json", "")
        slug = name.lower().replace(" ", "-").replace("_", "-")
        system_instruction = ""
        
        # Check systemInstruction field formats
        if "systemInstruction" in data:
            si = data["systemInstruction"]
            if isinstance(si, dict) and "parts" in si:
                system_instruction = "\n".join([p.get("text", "") for p in si.get("parts", []) if isinstance(p, dict)])
            elif isinstance(si, str):
                system_instruction = si

        model = data.get("model", "gemini-2.0-flash")

        return {
            "slug": slug,
            "name": name,
            "description": data.get("description", f"AI Studio App: {name}"),
            "status": "in_development",
            "ai_studio_link": data.get("url") or data.get("shareLink"),
            "system_instructions": system_instruction,
            "tech_stack": ["Gemini API", "AI Studio", model],
            "tags": ["AI Studio", model],
            "version": "0.1.0"
        }

    @staticmethod
    def parse_zip_export(zip_path: str, extract_dir: Optional[str] = None) -> Dict[str, Any]:
        """Parse a zip archive exported from AI Studio codebase generators."""
        if not os.path.exists(zip_path):
            raise FileNotFoundError(f"Zip archive not found: {zip_path}")

        app_name = os.path.splitext(os.path.basename(zip_path))[0]
        slug = app_name.lower().replace(" ", "-").replace("_", "-")

        result = {
            "slug": slug,
            "name": app_name,
            "description": f"Imported AI Studio Zip project: {app_name}",
            "status": "in_development",
            "tech_stack": ["Python", "Gemini API"],
            "system_instructions": None,
            "tags": ["AI Studio Export"],
            "version": "0.1.0"
        }

        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            file_list = zip_ref.namelist()
            for filename in file_list:
                if filename.endswith(".json") and ("config" in filename or "prompt" in filename):
                    try:
                        content = zip_ref.read(filename).decode("utf-8")
                        json_data = json.loads(content)
                        parsed = AIStudioParser.parse_json_export_dict(json_data, app_name)
                        result.update(parsed)
                        break
                    except Exception:
                        pass
        return result

    @staticmethod
    def parse_json_export_dict(data: Dict[str, Any], default_name: str) -> Dict[str, Any]:
        name = data.get("name") or data.get("title") or default_name
        slug = name.lower().replace(" ", "-").replace("_", "-")
        system_instruction = ""
        if "systemInstruction" in data:
            si = data["systemInstruction"]
            if isinstance(si, dict) and "parts" in si:
                system_instruction = "\n".join([p.get("text", "") for p in si.get("parts", []) if isinstance(p, dict)])
            elif isinstance(si, str):
                system_instruction = si
        model = data.get("model", "gemini-2.0-flash")

        return {
            "slug": slug,
            "name": name,
            "description": data.get("description", f"AI Studio App: {name}"),
            "system_instructions": system_instruction,
            "tech_stack": ["Gemini API", "AI Studio", model],
            "tags": ["AI Studio", model]
        }
