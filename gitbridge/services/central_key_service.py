import os
import re
import json
import time
import requests
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv

# Base directory of Geppy's GitBridge
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT_ENV_PATH = os.path.join(BASE_DIR, ".env")

# Ensure root .env is loaded on import
if os.path.exists(ROOT_ENV_PATH):
    load_dotenv(ROOT_ENV_PATH, override=False)

SUPPORTED_GEMINI_MODELS = [
    "gemini-3-flash-preview",
    "gemini-3.5-flash",
    "gemini-3.1-flash-lite",
    "gemini-2.5-flash",
    "gemini-flash-lite-latest",
    "gemini-2.5-flash-lite",
    "gemini-3.8-flash"
]


class CentralKeyService:
    """
    Centralized API Key Vault & Gemini AI Bridge for Geppy's GitBridge.
    Provides single source of truth for GEMINI_API_KEY across all Geppy apps,
    Galactic Chrome Extension, and background microservices.
    """

    @staticmethod
    def get_root_env_path() -> str:
        """Return the absolute path to GitBridge's master .env file."""
        if os.path.exists(ROOT_ENV_PATH):
            return ROOT_ENV_PATH
        # Fallback to local .env in current working dir
        return os.path.abspath(".env")

    @staticmethod
    def get_api_key() -> Optional[str]:
        """
        Retrieve the central Gemini API key.
        Checks environment variables first, falls back to direct reading of master .env file.
        """
        key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if key and key.strip():
            return key.strip()

        # Fallback: Parse master .env directly
        env_file = CentralKeyService.get_root_env_path()
        if os.path.exists(env_file):
            try:
                with open(env_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        if "=" in line:
                            k, v = line.split("=", 1)
                            k = k.strip()
                            v = v.strip().strip('"').strip("'")
                            if k in ("GEMINI_API_KEY", "GOOGLE_API_KEY") and v:
                                os.environ["GEMINI_API_KEY"] = v
                                os.environ["GOOGLE_API_KEY"] = v
                                return v
            except Exception as e:
                print(f"[CentralKeyService] Error reading {env_file}: {e}")

        return None

    @staticmethod
    def get_masked_key(key: Optional[str] = None) -> str:
        """Return masked key for safe UI display (e.g. AIza...7890)."""
        key = key or CentralKeyService.get_api_key()
        if not key:
            return ""
        if len(key) > 8:
            return f"{key[:4]}...{key[-4:]}"
        return "configured"

    @staticmethod
    def get_key_status() -> Dict[str, Any]:
        """Get current central key configuration status and model info."""
        key = CentralKeyService.get_api_key()
        return {
            "configured": bool(key),
            "masked_key": CentralKeyService.get_masked_key(),
            "source": "GitBridge Central Vault",
            "active_model": SUPPORTED_GEMINI_MODELS[0],
            "supported_models": SUPPORTED_GEMINI_MODELS,
            "env_path": CentralKeyService.get_root_env_path()
        }

    @staticmethod
    def test_connection() -> Dict[str, Any]:
        """
        Perform a live lightweight ping to the Gemini API using the central key.
        Returns latency and status without leaking the key.
        """
        key = CentralKeyService.get_api_key()
        if not key:
            return {
                "success": False,
                "status_code": 401,
                "message": "No Gemini API Key found in GitBridge Central Vault.",
                "latency_ms": 0,
                "model": SUPPORTED_GEMINI_MODELS[0]
            }

        start_time = time.time()
        for model in SUPPORTED_GEMINI_MODELS:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
                payload = {
                    "contents": [{"parts": [{"text": "ping"}]}]
                }
                res = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=12)
                latency_ms = int((time.time() - start_time) * 1000)

                if res.status_code == 200:
                    return {
                        "success": True,
                        "status_code": 200,
                        "message": f"Successfully connected to Google Gemini via {model}!",
                        "latency_ms": latency_ms,
                        "model": model,
                        "timestamp": time.time()
                    }
                else:
                    err_msg = res.json().get("error", {}).get("message", f"HTTP {res.status_code}")
                    # If this model failed, try the next one in sequence
                    print(f"[CentralKeyService] Model {model} test failed ({res.status_code}): {err_msg}")
                    continue
            except Exception as e:
                print(f"[CentralKeyService] Connection test exception on {model}: {e}")
                continue

        return {
            "success": False,
            "status_code": 500,
            "message": "Failed to reach Google Gemini API with configured models.",
            "latency_ms": int((time.time() - start_time) * 1000),
            "model": SUPPORTED_GEMINI_MODELS[0]
        }

    @staticmethod
    def call_gemini(
        messages: List[Dict[str, Any]],
        system_instruction: str,
        timeout: int = 25,
        model_preference: Optional[str] = None,
        json_mode: bool = False,
        max_output_tokens: int = 8192
    ) -> Optional[str]:
        """
        Execute a Gemini generation call using the central key with automatic model fallback.
        Supports structured JSON mode and configurable token limits.
        """
        api_key = CentralKeyService.get_api_key()
        if not api_key:
            print("[CentralKeyService] call_gemini aborted: No central API key available.")
            return None

        models_to_try = [model_preference] if model_preference and model_preference in SUPPORTED_GEMINI_MODELS else []
        for m in SUPPORTED_GEMINI_MODELS:
            if m not in models_to_try:
                models_to_try.append(m)

        for model in models_to_try:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
                generation_config: Dict[str, Any] = {
                    "maxOutputTokens": max_output_tokens
                }
                if json_mode:
                    generation_config["responseMimeType"] = "application/json"

                payload = {
                    "contents": messages,
                    "systemInstruction": {"parts": [{"text": system_instruction}]},
                    "generationConfig": generation_config
                }
                res = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=timeout)
                if res.status_code == 200:
                    data = res.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        if parts:
                            return parts[0].get("text", "").strip()
                else:
                    print(f"[CentralKeyService] Gemini API returned {res.status_code} on {model}: {res.text[:200]}")
            except Exception as e:
                print(f"[CentralKeyService] Gemini call failed on {model}: {e}")
                continue

        return None

    @staticmethod
    def sync_all_apps(api_key: Optional[str] = None) -> Dict[str, Any]:
        r"""
        Propagate the central Gemini API key into the .env files of all application
        directories inside Geppy's workspace (d:\Geppy_Apps).
        Safely updates existing .env files without erasing other environment variables.
        """
        from gitbridge.services.workspace_service import WorkspaceService

        key_to_sync = (api_key or CentralKeyService.get_api_key() or "").strip()
        if not key_to_sync:
            return {
                "success": False,
                "message": "Cannot sync apps: No central Gemini API key found in vault.",
                "apps_updated": 0,
                "app_list": []
            }

        workspace_dirs = WorkspaceService.get_workspace_dirs()
        updated_apps = []
        ignored_names = {".git", ".venv", "venv", "node_modules", "__pycache__", "dist", "build", ".next", ".turbo"}

        for base_dir in workspace_dirs:
            if not os.path.exists(base_dir):
                continue

            try:
                entries = os.listdir(base_dir)
            except Exception as e:
                print(f"[CentralKeyService] Could not list directory {base_dir}: {e}")
                continue

            for entry in entries:
                if entry.startswith(".") or entry in ignored_names:
                    continue

                full_app_path = os.path.join(base_dir, entry)
                if not os.path.isdir(full_app_path):
                    continue

                env_file_path = os.path.join(full_app_path, ".env")
                env_lines: List[str] = []
                existing_keys = set()

                if os.path.exists(env_file_path):
                    try:
                        with open(env_file_path, "r", encoding="utf-8", errors="ignore") as f:
                            for raw_line in f:
                                stripped = raw_line.strip()
                                if stripped and not stripped.startswith("#") and "=" in stripped:
                                    k = stripped.split("=", 1)[0].strip()
                                    existing_keys.add(k)
                                    # If it's one of our target keys, replace with new value
                                    if k in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "VITE_GEMINI_API_KEY", "NEXT_PUBLIC_GEMINI_API_KEY", "REACT_APP_GEMINI_API_KEY"):
                                        env_lines.append(f"{k}={key_to_sync}\n")
                                        continue
                                env_lines.append(raw_line)
                    except Exception as e:
                        print(f"[CentralKeyService] Error reading existing .env in {entry}: {e}")

                # Append any target keys that were not present
                target_keys = [
                    ("GEMINI_API_KEY", key_to_sync),
                    ("GOOGLE_API_KEY", key_to_sync),
                    ("VITE_GEMINI_API_KEY", key_to_sync),
                    ("NEXT_PUBLIC_GEMINI_API_KEY", key_to_sync),
                    ("REACT_APP_GEMINI_API_KEY", key_to_sync)
                ]

                added_any = False
                for k, v in target_keys:
                    if k not in existing_keys:
                        env_lines.append(f"{k}={v}\n")
                        added_any = True

                try:
                    with open(env_file_path, "w", encoding="utf-8") as f:
                        f.writelines(env_lines)
                    updated_apps.append(entry)
                except Exception as e:
                    print(f"[CentralKeyService] Failed to write .env in {entry}: {e}")

        return {
            "success": True,
            "message": f"Successfully synchronized Central Gemini API key to {len(updated_apps)} apps across Geppy's App Universe.",
            "apps_updated": len(updated_apps),
            "app_list": updated_apps
        }

    @staticmethod
    def set_central_key(new_key: str, sync_apps: bool = True) -> Dict[str, Any]:
        """
        Store a new central API key in master GitBridge .env, update process environment,
        and optionally sync to all app directories.
        """
        clean_key = new_key.strip()
        if not clean_key:
            return {"success": False, "message": "API key cannot be empty."}

        # 1. Update live process environment
        os.environ["GEMINI_API_KEY"] = clean_key
        os.environ["GOOGLE_API_KEY"] = clean_key

        # 2. Update master .env file
        env_path = CentralKeyService.get_root_env_path()
        env_lines = []
        found_gemini = False
        found_google = False

        if os.path.exists(env_path):
            try:
                with open(env_path, "r", encoding="utf-8", errors="ignore") as f:
                    for raw_line in f:
                        line = raw_line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k = line.split("=", 1)[0].strip()
                            if k == "GEMINI_API_KEY":
                                env_lines.append(f"GEMINI_API_KEY={clean_key}\n")
                                found_gemini = True
                                continue
                            if k == "GOOGLE_API_KEY":
                                env_lines.append(f"GOOGLE_API_KEY={clean_key}\n")
                                found_google = True
                                continue
                        env_lines.append(raw_line)
            except Exception as e:
                print(f"[CentralKeyService] Failed to read {env_path}: {e}")

        if not found_gemini:
            env_lines.append(f"GEMINI_API_KEY={clean_key}\n")
        if not found_google:
            env_lines.append(f"GOOGLE_API_KEY={clean_key}\n")

        try:
            with open(env_path, "w", encoding="utf-8") as f:
                f.writelines(env_lines)
        except Exception as e:
            return {"success": False, "message": f"Failed to write master .env: {e}"}

        # 3. Propagate to all apps if requested
        sync_result = {}
        if sync_apps:
            sync_result = CentralKeyService.sync_all_apps(clean_key)

        return {
            "success": True,
            "message": "Central Gemini API Key saved successfully.",
            "masked_key": CentralKeyService.get_masked_key(),
            "sync": sync_result
        }
