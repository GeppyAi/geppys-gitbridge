import asyncio
import json
import os
import re
import socket
import subprocess
import tempfile
import threading
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from gitbridge.services.central_key_service import CentralKeyService
from gitbridge.services.workspace_service import WorkspaceService

try:
    import websockets
    from google.antigravity import (
        Agent,
        AgentBehavior,
        BuiltinTools,
        CapabilitiesConfig,
        CustomSystemInstructions,
        GeminiAPIEndpoint,
        GeminiModelOptions,
        LocalAgentConfig,
        ModelTarget,
        ThinkingLevel,
    )
    from google.antigravity.connections.local import local_connection
    from google.antigravity.hooks import hooks, policy

    HookResult = hooks.HookResult
    HAS_ANTIGRAVITY_SDK = True

    # Speed Optimization #1: Connect to 127.0.0.1 BEFORE localhost when attaching to localharness.exe.
    # On Windows, 'localhost' attempts IPv6 (::1) first and stalls ~2.0s before falling back to 127.0.0.1.
    # Trying 127.0.0.1 first reduces localharness boot + WebSocket handshake from ~2.45s to ~0.35s!
    async def _fast_connect_websocket(
        self, port: int, api_key: str, process: subprocess.Popen
    ) -> Tuple[Any, str]:
        last_exception = None
        for attempt in range(6):
            # Prioritize 127.0.0.1 for local speed
            for host in ("127.0.0.1", "localhost"):
                ws_url = f"ws://{host}:{port}/"
                try:
                    ws = await websockets.connect(
                        ws_url,
                        additional_headers={"x-goog-api-key": api_key},
                        max_size=None,
                    )
                    return ws, ws_url
                except Exception as e:
                    last_exception = e
            # Exponential backoff with a fast start
            await asyncio.sleep(0.04 * (1.8 ** attempt))

        try:
            process.kill()
        except Exception:
            pass
        stderr = ""
        if process.stderr is not None:
            try:
                stderr = process.stderr.read().decode("utf-8", errors="replace")
            except Exception:
                pass
        raise RuntimeError(
            f"Failed to connect to Antigravity WebSocket on port {port}. Stderr: {stderr}"
        ) from last_exception

    local_connection.LocalConnectionStrategy._connect_websocket = _fast_connect_websocket

    # Silent Harness Patch: Prevent localharness.exe from opening visible cmd/conhost windows
    # when GitBridge runs under pythonw.exe (Windows GUI subsystem).
    async def _silent_spawn_harness_and_connect_ws(
        self, *, use_interactions_api: bool = False
    ) -> Tuple[subprocess.Popen, Any, str]:
        sdk_version = local_connection._get_sdk_version()
        client_info_proto = local_connection.localharness_pb2.ClientInfo(
            language="python",
            version=sdk_version,
            language_version=local_connection.platform.python_version(),
            os=local_connection.platform.system().lower(),
            os_version=local_connection.platform.release(),
        )
        env_map = (
            {str(k): str(v) for k, v in self._env.items()} if self._env else {}
        )
        input_config = local_connection.localharness_pb2.InputConfig(
            storage_directory=self._save_dir or "",
            client_info=client_info_proto,
            env=env_map,
        )
        if use_interactions_api:
            input_config.use_interactions_api = True

        merged_env = {**os.environ, **env_map} if self._env is not None else None

        popen_kwargs: Dict[str, Any] = {}
        if os.name == "nt":
            popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = getattr(subprocess, "SW_HIDE", 0)
            popen_kwargs["startupinfo"] = si

        process = subprocess.Popen(
            [self._binary_path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=merged_env,
            **popen_kwargs,
        )

        serialized = input_config.SerializeToString()
        assert process.stdin is not None
        assert process.stdout is not None
        assert process.stderr is not None
        process.stdin.write(local_connection.struct.pack("<I", len(serialized)) + serialized)
        process.stdin.flush()
        raw_len = process.stdout.read(4)
        if not raw_len:
            stderr_output = process.stderr.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"Failed to read length from stdout. Stderr: {stderr_output}"
            )
        length = local_connection.struct.unpack("<I", raw_len)[0]
        output_config = local_connection.localharness_pb2.OutputConfig()
        output_config.ParseFromString(process.stdout.read(length))
        ws, ws_url = await self._connect_websocket(
            output_config.port, output_config.api_key, process
        )
        return process, ws, ws_url

    local_connection.LocalConnectionStrategy._spawn_harness_and_connect_ws = (
        _silent_spawn_harness_and_connect_ws
    )

except Exception as _ag_err:
    print(f"[AntigravityService] Notice: google.antigravity SDK import failed: {_ag_err}")
    HAS_ANTIGRAVITY_SDK = False


ANTIGRAVITY_SERVICE_PORT = int(os.getenv("ANTIGRAVITY_SERVICE_PORT", "8001"))
ANTIGRAVITY_SERVICE_HOST = "127.0.0.1"
ANTIGRAVITY_SERVICE_URL = f"http://{ANTIGRAVITY_SERVICE_HOST}:{ANTIGRAVITY_SERVICE_PORT}"

ANTIGRAVITY_IDE_PATHS = [
    r"C:\Users\joneg\AppData\Local\Programs\Antigravity\Antigravity.exe",
    r"C:\Users\joneg\AppData\Local\Programs\Antigravity IDE\bin\antigravity-ide.cmd",
    r"C:\Users\joneg\AppData\Local\Programs\Antigravity IDE\Antigravity IDE.exe",
]

# Isolated lightweight app_data_dir so localharness.exe does not scan 40+ global plugins/skills on boot
_ISOLATED_APP_DATA_DIR = os.path.join(tempfile.gettempdir(), "geppy_antigravity_service_appdata")
os.makedirs(_ISOLATED_APP_DATA_DIR, exist_ok=True)

ANTIGRAVITY_MODELS = [
    "gemini-3-flash-preview",
    "gemini-2.5-pro",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
]


class WarmAgentSession:
    """
    Holds a live, warm `google.antigravity.Agent` (`localharness.exe` + open WebSocket)
    on the persistent Antigravity Service event loop so turns execute with zero cold-start delay.
    """

    def __init__(
        self,
        slug: str,
        app_name: str,
        local_root: str,
        mode: str,
        api_key: str,
        model_name: str = ANTIGRAVITY_MODELS[0],
    ):
        self.slug = slug
        self.app_name = app_name
        self.local_root = os.path.abspath(local_root)
        self.mode = mode  # "edit" or "brainstorm"
        self.api_key = api_key
        self.model_name = model_name
        self.agent: Optional[Agent] = None
        self.lock = asyncio.Lock()
        self.created_at = time.time()
        self.last_used_at = time.time()
        self.turn_count = 0
        self.is_alive = False
        self.ws_port: Optional[int] = None
        self.harness_pid: Optional[int] = None

        # Per-turn write tracking populated dynamically by the pre-tool hook
        self.active_tracker: Dict[str, Any] = {
            "pre_contents": {},
            "touched_files": [],
        }

    def reset_turn_tracker(self, seed_contents: Optional[Dict[str, str]] = None):
        self.active_tracker = {
            "pre_contents": dict(seed_contents or {}),
            "touched_files": [],
        }

    def _guard_write_call(self, tool_call) -> Any:
        t_name = str(getattr(tool_call.name, "value", tool_call.name))
        t_args = dict(getattr(tool_call, "args", None) or {})
        try:
            step_desc = AntigravityService._describe_tool_call(t_name, t_args, self.local_root)
            AntigravityDaemonPool.record_live_step(step_desc)
        except Exception:
            pass

        if t_name not in ("edit_file", "create_file"):
            return HookResult(allow=True)
        raw_p = (
            tool_call.args.get("file_path")
            or tool_call.args.get("TargetFile")
            or tool_call.args.get("path")
            or getattr(tool_call, "canonical_path", "")
            or ""
        )
        rel = AntigravityService._normalize_rel_path(self.local_root, raw_p)
        if rel and (
            rel.startswith(".geppy_")
            or rel.startswith(".git/")
            or rel.startswith("node_modules/")
        ):
            msg = f"Protected directory blocked (`{rel}`). Antigravity cannot directly overwrite `.geppy_`, `.git/`, or `node_modules/`."
            AntigravityDaemonPool.diagnose_and_record_error(
                raw_error=msg,
                slug=self.slug,
                app_name=self.app_name,
                mode=self.mode,
                target_file=rel,
                error_type_hint="protected_dir_blocked",
            )
            return HookResult(
                allow=False,
                message="Protected directory (.geppy_ / .git / node_modules).",
            )
        if rel:
            abs_target = os.path.join(self.local_root, rel.replace("/", os.sep))
            # Snapshot original content before the first write to this file in this turn
            if rel not in self.active_tracker["pre_contents"]:
                if os.path.exists(abs_target):
                    try:
                        with open(abs_target, "r", encoding="utf-8", errors="ignore") as src_f:
                            orig_txt = src_f.read()
                        self.active_tracker["pre_contents"][rel] = orig_txt
                    except Exception:
                        self.active_tracker["pre_contents"][rel] = ""
                else:
                    self.active_tracker["pre_contents"][rel] = None

            # Ensure .geppy_baselines copy exists before disk modification
            baseline_file = os.path.join(
                self.local_root, ".geppy_baselines", rel.replace("/", os.sep)
            )
            if os.path.exists(abs_target) and not os.path.exists(baseline_file):
                try:
                    os.makedirs(os.path.dirname(baseline_file), exist_ok=True)
                    orig_for_base = self.active_tracker["pre_contents"].get(rel)
                    if orig_for_base is None:
                        with open(abs_target, "r", encoding="utf-8", errors="ignore") as src_f:
                            orig_for_base = src_f.read()
                    with open(baseline_file, "w", encoding="utf-8") as bf:
                        bf.write(orig_for_base)
                except Exception:
                    pass

            if t_name == "create_file" and os.path.exists(abs_target):
                orig_txt = self.active_tracker["pre_contents"].get(rel) or ""
                new_txt = str(tool_call.args.get("content") or tool_call.args.get("CodeContent") or "")
                if len(orig_txt) > 4000 and len(new_txt) < len(orig_txt) * 0.75:
                    block_msg = (
                        f"Blocked create_file on existing file '{rel}' ({len(orig_txt)} chars) because "
                        f"new content ({len(new_txt)} chars) would truncate the file. "
                        f"You MUST use `edit_file` for surgical line edits on existing files!"
                    )
                    AntigravityDaemonPool.diagnose_and_record_error(
                        raw_error=block_msg,
                        slug=self.slug,
                        app_name=self.app_name,
                        mode=self.mode,
                        target_file=rel,
                        error_type_hint="hook_truncation_blocked",
                    )
                    return HookResult(
                        allow=False,
                        message=block_msg,
                    )

            if rel not in self.active_tracker["touched_files"]:
                self.active_tracker["touched_files"].append(rel)

        return HookResult(allow=True)

    async def start(self) -> bool:
        if self.is_alive and self.agent is not None:
            return True

        is_gb = bool(
            self.slug and self.slug.lower() in ("geppys-gitbridge", "gitbridge")
        ) or ("gitbridge" in (self.app_name or "").lower())
        persona_name = "Captain Geppy" if is_gb else "Geppy"
        identity_rule = (
            ""
            if is_gb
            else f'\n- IDENTITY RULE: This app is "{self.app_name}" (NOT GitBridge). Your persona name is strictly "Geppy" — NEVER "Captain Geppy" or "Galactic Commander".'
        )

        if self.mode == "edit":
            sys_text = f"""You are the Antigravity Surgical Coding Engine for "{self.app_name}".
Workspace Root: {self.local_root}

OPERATING RULES:
1. Apply requested code changes directly to files in `{self.local_root}` using `edit_file` or `create_file`.
2. FAST PATH: When the prompt already includes numbered lines of the target file, call `edit_file` (or `create_file` for a new file) immediately without redundant `view_file` calls!
3. COMPLETE DASHBOARD / UI BUILDS: When asked to build an HTML dashboard, web UI, gallery, or fix a directory listing / non-loading dashboard:
   - ALWAYS ensure `{self.local_root}\\index.html` exists and contains a COMPLETE, rich, modern, interactive, self-contained HTML5 dashboard (with clean dark-mode CSS, responsive gallery/cards, status indicators, and interactive controls) so the browser immediately loads `index.html` at `/` instead of a raw directory listing!
   - If the project also has a Python server (`dashboard.py`, `app.py`, `main.py`), ensure it serves `index.html` at `/`, includes all required imports (`import os`, `import json`, etc.), and uses `os.path.dirname(os.path.abspath(__file__))` (NEVER Linux `/home/...` paths).
4. Preserve all unrelated logic, imports, routes, and event listeners.
5. After editing, reply with a concise 2-3 sentence summary of what you updated.{identity_rule}"""
            enabled_tools = [
                BuiltinTools.VIEW_FILE,
                BuiltinTools.EDIT_FILE,
                BuiltinTools.CREATE_FILE,
                BuiltinTools.FIND_FILE,
                BuiltinTools.LIST_DIR,
                BuiltinTools.SEARCH_DIR,
            ]
            agent_hooks = [hooks.pre_tool_call_decide(self._guard_write_call)]
        else:
            sys_text = f"""You are {persona_name}, the upbeat, razor-sharp AI Architect co-building "{self.app_name}" in Geppy's Galactic Studio.
Workspace Root: {self.local_root}

OPERATING RULES:
1. FAST PATH: The prompt includes the project file list, runtime server diagnostics, and file excerpts. If that context is sufficient to answer or brainstorm, reply immediately WITHOUT calling any tools!
2. Only call `view_file` (with `start_line` and `end_line`) or `search_directory` (with `directory_path="{self.local_root}"`) if you specifically need to inspect unseen code to answer accurately.
3. ENTRYPOINT & DASHBOARD AWARENESS: If Runtime Diagnostics show that `index.html` is missing or the app is served by `http.server` showing a directory listing, clearly point this out and set `"target_file": "index.html"` for any dashboard/UI task! Prefer 1 comprehensive, complete build step over multiple fragmented micro-steps.
4. Whenever proposing actionable steps, features, UI upgrades, or fixes, ALWAYS append a valid JSON block wrapped in ```tasks ... ``` at the very end of your response:
```tasks
[
  {{
    "title": "Short step title",
    "category": "design" | "feature" | "ux" | "polish" | "fix",
    "target_file": "exact/relative/path/from/project.ext",
    "description": "1-sentence explanation",
    "suggested_prompt": "Specific coding instruction for target_file"
  }}
]
```{identity_rule}"""
            enabled_tools = [
                BuiltinTools.VIEW_FILE,
                BuiltinTools.FIND_FILE,
                BuiltinTools.LIST_DIR,
                BuiltinTools.SEARCH_DIR,
            ]
            agent_hooks = [hooks.pre_tool_call_decide(self._guard_write_call)]

        t_level = (
            getattr(ThinkingLevel, "HIGH", ThinkingLevel.LOW)
            if "pro" in (self.model_name or "").lower()
            else ThinkingLevel.LOW
        )
        cfg = LocalAgentConfig(
            workspaces=[self.local_root],
            app_data_dir=_ISOLATED_APP_DATA_DIR,
            model=ModelTarget(
                name=self.model_name,
                endpoint=GeminiAPIEndpoint(
                    api_key=self.api_key,
                    options=GeminiModelOptions(thinking_level=t_level),
                ),
            ),
            system_instructions=CustomSystemInstructions(text=sys_text),
            capabilities=CapabilitiesConfig(
                enabled_tools=enabled_tools,
                agent_behavior=AgentBehavior.MINIMAL,
                enable_subagents=False,
            ),
            policies=[policy.allow_all()],
            hooks=agent_hooks,
        )

        ag = Agent(cfg)
        await ag.__aenter__()
        self.agent = ag
        self.is_alive = True
        self.last_used_at = time.time()

        # Extract underlying localharness pid and WebSocket port for telemetry
        try:
            conn = ag.conversation._connection
            proc = getattr(conn, "_process", None)
            if proc:
                self.harness_pid = proc.pid
            ws = getattr(conn, "_ws", None)
            if ws and hasattr(ws, "remote_address") and ws.remote_address:
                self.ws_port = ws.remote_address[1]
        except Exception:
            pass

        return True

    async def close(self):
        self.is_alive = False
        ag = self.agent
        self.agent = None
        if ag is not None:
            try:
                await asyncio.wait_for(ag.__aexit__(None, None, None), timeout=3.0)
            except Exception:
                pass


class AntigravityDaemonPool:
    """
    Manages the persistent event loop, warm `localharness.exe` Agent pool, and dedicated
    FastAPI service on Port 8001 (`http://127.0.0.1:8001`).
    """

    _loop: Optional[asyncio.AbstractEventLoop] = None
    _thread: Optional[threading.Thread] = None
    _init_lock = threading.Lock()
    _sessions: Dict[Tuple[str, str], WarmAgentSession] = {}
    _started_at: float = 0.0
    _requests_served: int = 0
    _last_turn_ms: int = 0
    _active_model_idx: int = 0
    _error_log: List[Dict[str, Any]] = []
    _latest_error: Optional[Dict[str, Any]] = None
    _live_activity: Dict[str, Any] = {
        "is_busy": False,
        "job_id": None,
        "mode": None,
        "slug": None,
        "app_name": None,
        "title": None,
        "target_file": None,
        "phase": "idle",
        "started_at": 0.0,
        "live_steps": [],
        "last_completed": None,
    }

    @classmethod
    def diagnose_and_record_error(
        cls,
        raw_error: str,
        slug: str = "",
        app_name: str = "",
        mode: str = "edit",
        target_file: str = "",
        instruction: str = "",
        error_type_hint: str = "",
        source: str = "antigravity",
        file_path: str = "",
        model: str = "",
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Classify any Antigravity SDK, model, safety hook, or syntax error into a clear diagnostic
        with:
          - `what_is_the_error`: Plain-English explanation of what went wrong in Antigravity
          - `what_needs_done`: Concrete steps to fix or guide Antigravity
          - `suggested_replies`: 1-click or editable chat responses to send back to Antigravity
        """
        err_str = str(raw_error or "Unknown Antigravity error").strip()
        upper = err_str.upper()
        now_ms = int(time.time() * 1000)
        time_str = time.strftime("%H:%M:%S")
        current_model = model or cls.get_active_model()
        target_file = target_file or file_path or ""
        file_label = target_file or "the target file"

        if error_type_hint == "hook_truncation_blocked" or "TRUNCATE THE FILE" in upper or "BLOCKED CREATE_FILE" in upper:
            error_type = "hook_truncation_blocked"
            title = f"🛡️ Antigravity Safety Hook Blocked Full Overwrite on `{file_label}`"
            what_is_the_error = (
                f"Antigravity attempted to call `create_file` to overwrite the entire `{file_label}` with a shorter snippet, "
                f"which would have accidentally deleted existing code. GitBridge's pre-tool safety hook intercepted and blocked it to protect your file."
            )
            what_needs_done = (
                f"Tell Antigravity to use `edit_file` for a surgical line-range replacement in `{file_label}` instead of rewriting the whole file, "
                f"or specify the exact section/component you want updated."
            )
            suggested_replies = [
                {
                    "label": "🩹 Retry with Surgical Line Edit (`edit_file`)",
                    "action": "surgical_retry",
                    "reply": f"Use `edit_file` to surgically update only the target lines in `{file_label}` — do NOT call `create_file` or overwrite the whole file.",
                },
                {
                    "label": "🔍 Inspect Target Lines First",
                    "action": "inspect_and_propose",
                    "reply": f"First call `view_file` on `{file_label}` to find the exact line numbers, then apply a minimal `edit_file` patch.",
                },
            ]
        elif error_type_hint == "protected_dir_blocked" or "PROTECTED DIRECTORY" in upper:
            error_type = "protected_dir_blocked"
            title = f"🔒 Protected Directory Write Blocked (`{file_label}`)"
            what_is_the_error = (
                f"Antigravity attempted to modify `{file_label}`, which is inside a protected system directory (`.geppy_`, `.git/`, or `node_modules/`)."
            )
            what_needs_done = (
                "Direct Antigravity to edit your application's source files (e.g., `index.html`, `src/`, `static/`, or `main.py`) instead of protected folders."
            )
            suggested_replies = [
                {
                    "label": "🎯 Redirect to Main Source File",
                    "action": "surgical_retry",
                    "reply": "Apply this change to the application's primary source file instead of `.geppy_` or `.git`.",
                }
            ]
        elif error_type_hint == "syntax_revert" or "SYNTAXERROR" in upper or "INVALID PYTHON SYNTAX" in upper:
            error_type = "syntax_revert"
            title = f"🐍 Python Syntax Error Auto-Reverted in `{file_label}`"
            what_is_the_error = (
                f"Antigravity edited `{file_label}`, but the resulting Python code had a syntax error (`{err_str[:180]}`). "
                f"GitBridge automatically reverted `{file_label}` to its clean pre-edit state so your server wouldn't crash."
            )
            what_needs_done = (
                f"Reply to Antigravity below to have it inspect the indentation/brackets around the target lines in `{file_label}` and re-apply a clean, syntax-verified patch."
            )
            suggested_replies = [
                {
                    "label": "🔧 Fix Indentation & Re-Apply Patch",
                    "action": "surgical_retry",
                    "reply": f"Your previous edit to `{file_label}` caused `{err_str[:120]}`. View the surrounding lines carefully and re-apply the change with valid Python indentation and syntax.",
                },
                {
                    "label": "🔄 Rotate Model & Retry Cleanly",
                    "action": "rotate_and_retry",
                    "reply": f"Switch to the next Gemini model and apply this change to `{file_label}` with strict Python syntax validation.",
                },
            ]
        elif "429" in err_str or "RESOURCE_EXHAUSTED" in upper or "QUOTA" in upper or "RATE_LIMIT" in upper:
            error_type = "quota_429"
            title = f"⚡ Antigravity Model Quota / Rate Limit (`{current_model}`)"
            what_is_the_error = (
                f"Google Gemini returned HTTP 429 (`RESOURCE_EXHAUSTED`) on `{current_model}` while Antigravity was processing your request."
            )
            what_needs_done = (
                "Click **Rotate Model & Retry** below (or send a reply in chat) so Antigravity switches to the next available Gemini model in the pool and finishes your task."
            )
            suggested_replies = [
                {
                    "label": "🔄 Rotate Gemini Model & Retry Now",
                    "action": "rotate_and_retry",
                    "reply": "Rotate to the next available Gemini model in the pool and retry this task immediately.",
                },
                {
                    "label": "⚡ Execute via Fast Surgical Fallback",
                    "action": "fallback_retry",
                    "reply": "Complete this edit using the fast fallback model.",
                },
            ]
        elif "503" in err_str or "UNAVAILABLE" in upper or "OVERLOADED" in upper or "500" in err_str:
            error_type = "model_503"
            title = f"🌩️ Gemini Model Temporarily Overloaded (`{current_model}`)"
            what_is_the_error = (
                f"The upstream Gemini endpoint for `{current_model}` reported temporary high load (`{err_str[:160]}`)."
            )
            what_needs_done = (
                "Rotate to a lighter/faster model in the Antigravity pool and re-run the instruction."
            )
            suggested_replies = [
                {
                    "label": "🔄 Switch Model & Retry",
                    "action": "rotate_and_retry",
                    "reply": "Switch to the next available model and re-run this instruction.",
                }
            ]
        elif error_type_hint == "no_changes" or "NO FILE CHANGES DETECTED" in upper:
            error_type = "no_changes"
            title = f"🤔 Antigravity Finished Without Modifying `{file_label}`"
            what_is_the_error = (
                f"The Antigravity agent session completed its turn on `{file_label}` without writing any changes to disk "
                f"(it may have needed a clearer target selector, line range, or confirmation)."
            )
            what_needs_done = (
                f"Reply to Antigravity in chat with a more specific instruction or click **Force Surgical Edit on `{file_label}`** below."
            )
            suggested_replies = [
                {
                    "label": f"✏️ Force Surgical Edit on `{file_label}`",
                    "action": "surgical_retry",
                    "reply": f"Please apply the code changes directly to `{file_label}` now using `edit_file` — do not just describe them.",
                },
                {
                    "label": "💬 Ask Antigravity What It Needs",
                    "action": "brainstorm_clarify",
                    "reply": f"Why didn't you modify `{file_label}`? Tell me what you found in `{file_label}` and what needs to be changed.",
                },
            ]
        elif "TIMEOUT" in upper or "TIMED OUT" in upper or "WEBSOCKET" in upper or "HARNESS" in upper:
            error_type = "harness_timeout"
            title = "⏱️ Antigravity Harness Session Timed Out or Disconnected"
            what_is_the_error = (
                f"The local `localharness.exe` WebSocket session took too long or disconnected while working on `{file_label}` (`{err_str[:160]}`)."
            )
            what_needs_done = (
                "Recycle the warm Antigravity session and retry with a smaller, focused step."
            )
            suggested_replies = [
                {
                    "label": "♻️ Recycle Antigravity Session & Retry",
                    "action": "reset_and_retry",
                    "reply": "Reset the warm Antigravity session and retry this step with a focused surgical edit.",
                }
            ]
        elif (
            error_type_hint in ("watchdog_chat_healed", "watchdog_api_error", "json_parse_error")
            or "NOT VALID JSON" in upper
            or "UNEXPECTED TOKEN" in upper
            or "INTERNAL SERVER ERROR" in upper
            or "TYPEERROR" in upper
        ):
            error_type = error_type_hint or "watchdog_chat_healed"
            title = f"🛡️ Watchdog Intercepted & Auto-Corrected Runtime Error (`{file_label}`)"
            what_is_the_error = (
                f"The GitBridge Watchdog caught a runtime or non-JSON API response error (`{err_str[:220]}`) on `{file_label}` "
                f"and automatically engaged self-healing fallback so Captain Geppy's conversation continues without crashing."
            )
            what_needs_done = (
                f"Click **🔧 Apply Permanent Watchdog Fix** below to have Antigravity inspect `{file_label}` and patch the root cause, "
                f"or click **🛡️ Run Aegis Watchdog Audit** for a full defensive check."
            )
            suggested_replies = [
                {
                    "label": f"🔧 Apply Permanent Watchdog Fix on `{file_label}`",
                    "action": "surgical_retry",
                    "reply": f"Watchdog caught `{err_str[:160]}` in `{file_label}`. Inspect `{file_label}` and apply a surgical fix so this exception cannot recur.",
                },
                {
                    "label": "🛡️ Run Aegis Watchdog Audit (@qa)",
                    "action": "inspect_and_propose",
                    "reply": f"@qa Audit `{file_label}` for the runtime error `{err_str[:140]}`, ensure all API routes return valid JSON, and provide a permanent patch.",
                },
                {
                    "label": "🔄 Rotate Model & Retry Cleanly",
                    "action": "rotate_and_retry",
                    "reply": "Switch to the next Gemini model and retry the last request cleanly.",
                },
            ]
        else:
            error_type = error_type_hint or "execution_error"
            title = f"⚠️ Antigravity Encountered an Issue on `{file_label}`"
            what_is_the_error = f"Antigravity reported: `{err_str[:280]}`"
            what_needs_done = (
                f"Review the error details above and send a follow-up instruction to Antigravity in chat, or click one of the recovery actions below."
            )
            suggested_replies = [
                {
                    "label": "🔄 Rotate Model & Retry in Antigravity",
                    "action": "rotate_and_retry",
                    "reply": "Rotate to the next model and retry this instruction carefully.",
                },
                {
                    "label": "🔍 Ask Antigravity to Diagnose & Fix",
                    "action": "inspect_and_propose",
                    "reply": f"Diagnose why `{err_str[:120]}` happened on `{file_label}` and propose or apply a clean fix.",
                },
            ]

        # Deduplicate if the exact same error_type + target_file happened in the last 2 seconds
        if cls._error_log:
            last = cls._error_log[0]
            if (
                last.get("error_type") == error_type
                and last.get("target_file") == target_file
                and (now_ms - int(last.get("timestamp") or 0)) < 2000
            ):
                last["raw_error"] = err_str[:800]
                last["timestamp"] = now_ms
                cls._latest_error = last
                return last

        record = {
            "id": f"ag-err-{now_ms}-{len(cls._error_log) + 1}",
            "timestamp": now_ms,
            "time": time_str,
            "slug": slug or cls._live_activity.get("slug") or "",
            "app_name": app_name or cls._live_activity.get("app_name") or "App",
            "mode": mode or cls._live_activity.get("mode") or "edit",
            "target_file": target_file or cls._live_activity.get("target_file") or "",
            "instruction": (instruction or cls._live_activity.get("title") or "")[:500],
            "model": current_model,
            "source": source or "antigravity",
            "category": error_type,
            "error_type": error_type,
            "title": title,
            "raw_error": err_str[:800],
            "what_is_the_error": what_is_the_error,
            "what_needs_done": what_needs_done,
            "suggested_replies": suggested_replies,
            "status": "open",
            "user_response": None,
        }
        cls._error_log.insert(0, record)
        cls._error_log = cls._error_log[:50]
        cls._latest_error = record
        return record

    @classmethod
    def get_errors(
        cls,
        slug: Optional[str] = None,
        include_resolved: bool = True,
        unresolved_only: bool = False,
        limit: int = 25,
        **kwargs,
    ) -> List[Dict[str, Any]]:
        items = list(cls._error_log)
        if slug:
            items = [e for e in items if not e.get("slug") or e.get("slug") == slug]
        if unresolved_only or not include_resolved:
            items = [e for e in items if e.get("status") != "resolved"]
        if limit and limit > 0:
            items = items[:limit]
        return items

    @classmethod
    def clear_errors(cls, slug: Optional[str] = None, error_id: Optional[str] = None) -> int:
        before = len(cls._error_log)
        if error_id:
            cls._error_log = [e for e in cls._error_log if e.get("id") != error_id]
        elif slug:
            cls._error_log = [e for e in cls._error_log if e.get("slug") != slug]
        else:
            cls._error_log = []
        cls._latest_error = next((e for e in cls._error_log if e.get("status") == "open"), None)
        return before - len(cls._error_log)

    @classmethod
    def mark_error_status(cls, error_id: str, status: str = "resolved", user_response: str = "") -> Optional[Dict[str, Any]]:
        target = None
        for e in cls._error_log:
            if e.get("id") == error_id:
                e["status"] = status
                if user_response:
                    e["user_response"] = user_response
                e["updated_at"] = int(time.time() * 1000)
                target = e
                break
        cls._latest_error = next((e for e in cls._error_log if e.get("status") == "open"), None)
        return target

    @classmethod
    def begin_live_job(
        cls,
        mode: str,
        slug: str,
        app_name: str,
        title: str,
        target_file: Optional[str] = None,
    ) -> str:
        job_id = f"job-{int(time.time() * 1000)}"
        cls._live_activity = {
            "is_busy": True,
            "job_id": job_id,
            "mode": mode,
            "slug": slug,
            "app_name": app_name,
            "title": (title or "")[:140],
            "target_file": target_file or "",
            "phase": "Synthesizing with Antigravity AI...",
            "started_at": time.time(),
            "live_steps": [],
            "last_completed": cls._live_activity.get("last_completed"),
        }
        return job_id

    @classmethod
    def record_live_step(cls, step_info: Dict[str, Any]) -> None:
        if not cls._live_activity.get("is_busy"):
            return
        steps = list(cls._live_activity.get("live_steps") or [])
        step_entry = {
            **step_info,
            "ts": round(time.time() - float(cls._live_activity.get("started_at") or time.time()), 1),
        }
        steps.append(step_entry)
        cls._live_activity["live_steps"] = steps[-12:]
        cls._live_activity["phase"] = step_info.get("summary") or step_info.get("label") or "Working..."
        if step_info.get("file"):
            cls._live_activity["target_file"] = step_info.get("file")

    @classmethod
    def finish_live_job(
        cls,
        success: bool,
        elapsed_ms: int,
        summary: str = "",
        modified_files: Optional[List[str]] = None,
        antigravity_error: Optional[Dict[str, Any]] = None,
    ) -> None:
        completed_payload = {
            "job_id": cls._live_activity.get("job_id"),
            "mode": cls._live_activity.get("mode"),
            "slug": cls._live_activity.get("slug"),
            "app_name": cls._live_activity.get("app_name"),
            "title": cls._live_activity.get("title"),
            "target_file": cls._live_activity.get("target_file"),
            "success": bool(success),
            "elapsed_ms": elapsed_ms,
            "summary": (summary or "")[:240],
            "modified_files": list(modified_files or []),
            "steps_count": len(cls._live_activity.get("live_steps") or []),
            "finished_at": time.time(),
            "antigravity_error": antigravity_error,
        }
        cls._live_activity["is_busy"] = False
        cls._live_activity["phase"] = "completed" if success else "error"
        cls._live_activity["last_completed"] = completed_payload

    @classmethod
    def get_live_activity(cls) -> Dict[str, Any]:
        act = dict(cls._live_activity)
        if act.get("is_busy") and act.get("started_at"):
            act["elapsed_ms"] = int((time.time() - float(act["started_at"])) * 1000)
        else:
            act["elapsed_ms"] = 0
        open_errs = [e for e in cls._error_log if e.get("status") == "open"]
        act["latest_error"] = open_errs[0] if open_errs else cls._latest_error
        act["open_error_count"] = len(open_errs)
        return act

    @classmethod
    def get_active_model(cls, task_prompt: str = "", mode: str = "edit") -> str:
        try:
            st = CentralKeyService.get_model_state()
            if not st.get("is_auto"):
                locked = st.get("active_model")
                if locked in ANTIGRAVITY_MODELS:
                    return locked
            elif task_prompt:
                sel = CentralKeyService.select_model_for_need(
                    prompt=task_prompt,
                    task_type=mode,
                )
                chosen = sel.get("model")
                if chosen in ANTIGRAVITY_MODELS:
                    return chosen
        except Exception:
            pass
        return ANTIGRAVITY_MODELS[cls._active_model_idx % len(ANTIGRAVITY_MODELS)]

    @classmethod
    def sync_with_central_model(cls, mode_or_model: str) -> str:
        if mode_or_model in ANTIGRAVITY_MODELS:
            cls._active_model_idx = ANTIGRAVITY_MODELS.index(mode_or_model)
        return cls.get_active_model()

    @classmethod
    def rotate_model(cls) -> str:
        cls._active_model_idx = (cls._active_model_idx + 1) % len(ANTIGRAVITY_MODELS)
        next_m = ANTIGRAVITY_MODELS[cls._active_model_idx % len(ANTIGRAVITY_MODELS)]
        try:
            CentralKeyService._last_used_model = next_m
            CentralKeyService._last_selection_reason = f"Rotated to {next_m}"
        except Exception:
            pass
        return next_m

    @classmethod
    def ensure_running(cls) -> bool:
        """Start the dedicated Antigravity Service daemon & port 8001 listener if not already running."""
        if not HAS_ANTIGRAVITY_SDK:
            return False
        if cls._loop is not None and cls._thread is not None and cls._thread.is_alive():
            return True

        with cls._init_lock:
            if cls._loop is not None and cls._thread is not None and cls._thread.is_alive():
                return True

            ready_evt = threading.Event()

            def _daemon_main():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                cls._loop = loop
                cls._started_at = time.time()
                ready_evt.set()

                # Start the FastAPI / Uvicorn server on port 8001 inside this persistent event loop
                try:
                    import uvicorn
                    app = create_antigravity_port_app()
                    config = uvicorn.Config(
                        app=app,
                        host=ANTIGRAVITY_SERVICE_HOST,
                        port=ANTIGRAVITY_SERVICE_PORT,
                        log_level="error",
                        loop="asyncio",
                    )
                    server = uvicorn.Server(config)
                    server.install_signal_handlers = lambda: None
                    if not AntigravityService._is_port_listening(ANTIGRAVITY_SERVICE_PORT):
                        loop.run_until_complete(server.serve())
                    else:
                        loop.run_forever()
                except (Exception, SystemExit) as srv_err:
                    print(f"[AntigravityDaemonPool] Port {ANTIGRAVITY_SERVICE_PORT} server notice: {srv_err}")
                    # Keep the event loop running even if port 8001 was already bound by another instance
                    loop.run_forever()

            t = threading.Thread(
                target=_daemon_main,
                daemon=True,
                name="AntigravityPortServiceDaemon",
            )
            t.start()
            cls._thread = t
            ready_evt.wait(timeout=3.0)
            return cls._loop is not None

    @classmethod
    def run_sync(cls, coro, timeout: float = 95.0) -> Any:
        """Submit a coroutine to the persistent Antigravity event loop and wait for its result."""
        if not cls.ensure_running() or cls._loop is None:
            raise RuntimeError("Antigravity daemon event loop is not available.")
        future = asyncio.run_coroutine_threadsafe(coro, cls._loop)
        return future.result(timeout=timeout)

    @classmethod
    def submit_background(cls, coro) -> None:
        """Fire-and-forget a coroutine on the persistent Antigravity event loop (e.g. session pre-warming)."""
        if cls.ensure_running() and cls._loop is not None:
            asyncio.run_coroutine_threadsafe(coro, cls._loop)

    @classmethod
    async def get_or_create_session(
        cls,
        slug: str,
        app_name: str,
        local_root: str,
        mode: str,
        api_key: str,
        max_turns_before_recycle: int = 5,
        task_prompt: str = "",
    ) -> WarmAgentSession:
        norm_root = os.path.normcase(os.path.abspath(local_root))
        key = (norm_root, mode)
        existing = cls._sessions.get(key)
        active_model = cls.get_active_model(task_prompt=task_prompt, mode=mode)

        if existing is not None:
            if (
                not existing.is_alive
                or existing.api_key != api_key
                or existing.model_name != active_model
                or existing.turn_count >= max_turns_before_recycle
            ):
                await existing.close()
                cls._sessions.pop(key, None)
                existing = None

        if existing is None:
            session = WarmAgentSession(
                slug=slug,
                app_name=app_name,
                local_root=local_root,
                mode=mode,
                api_key=api_key,
                model_name=active_model,
            )
            await session.start()
            cls._sessions[key] = session
            return session

        return existing

    @classmethod
    async def prewarm_app_sessions(
        cls, slug: str, app_name: str, local_root: str, modes: Tuple[str, ...] = ("edit", "brainstorm")
    ) -> Dict[str, Any]:
        """Pre-warm persistent `localharness.exe` sessions for an app so the next user action has 0ms cold start."""
        if not HAS_ANTIGRAVITY_SDK or not local_root or not os.path.exists(local_root):
            return {"warmed": False, "reason": "SDK or local_root unavailable"}
        api_key = CentralKeyService.get_api_key()
        if not api_key:
            return {"warmed": False, "reason": "No Gemini API key configured"}

        t0 = time.perf_counter()
        warmed_modes = []
        ports = {}
        for m in modes:
            try:
                sess = await cls.get_or_create_session(
                    slug=slug,
                    app_name=app_name,
                    local_root=local_root,
                    mode=m,
                    api_key=api_key,
                )
                warmed_modes.append(m)
                ports[m] = sess.ws_port
            except Exception as e:
                print(f"[AntigravityDaemonPool] Pre-warm notice ({slug}, {m}): {e}")

        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        return {
            "warmed": len(warmed_modes) > 0,
            "slug": slug,
            "modes": warmed_modes,
            "ws_ports": ports,
            "elapsed_ms": elapsed_ms,
        }

    @classmethod
    async def recycle_session_background(
        cls, slug: str, app_name: str, local_root: str, mode: str, api_key: str
    ):
        """Close a used/stale session and immediately pre-warm a fresh replacement in the background."""
        norm_root = os.path.normcase(os.path.abspath(local_root))
        key = (norm_root, mode)
        old_sess = cls._sessions.pop(key, None)
        if old_sess is not None:
            await old_sess.close()
        try:
            new_sess = WarmAgentSession(
                slug=slug,
                app_name=app_name,
                local_root=local_root,
                mode=mode,
                api_key=api_key,
                model_name=cls.get_active_model(),
            )
            await new_sess.start()
            cls._sessions[key] = new_sess
        except Exception:
            pass

    @classmethod
    def get_pool_telemetry(cls) -> Dict[str, Any]:
        active_list = []
        for (_, mode), sess in list(cls._sessions.items()):
            if sess.is_alive:
                active_list.append({
                    "slug": sess.slug,
                    "app_name": sess.app_name,
                    "mode": mode,
                    "model": sess.model_name,
                    "ws_port": sess.ws_port,
                    "harness_pid": sess.harness_pid,
                    "turn_count": sess.turn_count,
                    "idle_seconds": int(time.time() - sess.last_used_at),
                })
        return {
            "service_port": ANTIGRAVITY_SERVICE_PORT,
            "service_url": ANTIGRAVITY_SERVICE_URL,
            "active_model": cls.get_active_model(),
            "daemon_running": bool(cls._loop and cls._thread and cls._thread.is_alive()),
            "uptime_seconds": int(time.time() - cls._started_at) if cls._started_at else 0,
            "warm_session_count": len(active_list),
            "warm_sessions": active_list,
            "requests_served": cls._requests_served,
            "last_turn_ms": cls._last_turn_ms,
        }


class AntigravityService:
    """
    High-Speed Google Antigravity Service & Port Bridge (`http://127.0.0.1:8001`).

    Communicates with persistent, pre-warmed `localharness.exe` WebSocket sessions
    and uses `CustomSystemInstructions` + `ThinkingLevel.LOW` + pre-seeded line windows
    for sub-3-second surgical edits and brainstorm turns.
    """

    @staticmethod
    def _is_port_listening(port: int = ANTIGRAVITY_SERVICE_PORT) -> bool:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.15)
                return s.connect_ex((ANTIGRAVITY_SERVICE_HOST, port)) == 0
        except Exception:
            return False

    @staticmethod
    def get_antigravity_status() -> Dict[str, Any]:
        """Return availability, dedicated port status, and warm session telemetry of the Antigravity Service."""
        AntigravityDaemonPool.ensure_running()
        ide_exe = next((p for p in ANTIGRAVITY_IDE_PATHS if os.path.exists(p)), None)
        sdk_version = None
        if HAS_ANTIGRAVITY_SDK:
            try:
                import importlib.metadata
                sdk_version = importlib.metadata.version("google-antigravity")
            except Exception:
                sdk_version = "0.1.22"

        pool_info = AntigravityDaemonPool.get_pool_telemetry()
        port_listening = AntigravityService._is_port_listening(ANTIGRAVITY_SERVICE_PORT)

        return {
            "sdk_available": HAS_ANTIGRAVITY_SDK,
            "sdk_version": sdk_version,
            "ide_available": bool(ide_exe),
            "ide_path": ide_exe,
            "engine": "google-antigravity-service" if HAS_ANTIGRAVITY_SDK else "fallback",
            "service_port": ANTIGRAVITY_SERVICE_PORT,
            "service_url": ANTIGRAVITY_SERVICE_URL,
            "port_listening": port_listening,
            **pool_info,
            "capabilities": [
                "Dedicated Port 8001 Warm Daemon",
                "view_file (line-range reading)",
                "edit_file (surgical multi-file patching)",
                "search_directory (workspace grep)",
                "find_file & list_directory",
                "create_file",
            ] if HAS_ANTIGRAVITY_SDK else [],
        }

    @staticmethod
    def prewarm_app(app_obj) -> Dict[str, Any]:
        """Trigger non-blocking background pre-warming of Antigravity sessions for the given app."""
        if not HAS_ANTIGRAVITY_SDK or not app_obj or not app_obj.local_path or not os.path.exists(app_obj.local_path):
            return {"warmed": False, "message": "App local path or SDK unavailable"}
        AntigravityDaemonPool.ensure_running()
        AntigravityDaemonPool.submit_background(
            AntigravityDaemonPool.prewarm_app_sessions(
                slug=app_obj.slug,
                app_name=app_obj.name or app_obj.slug,
                local_root=app_obj.local_path,
                modes=("edit", "brainstorm"),
            )
        )
        return {
            "warmed": True,
            "slug": app_obj.slug,
            "service_url": ANTIGRAVITY_SERVICE_URL,
            "message": f"Warming Antigravity sessions for '{app_obj.name}' on {ANTIGRAVITY_SERVICE_URL}",
        }

    @staticmethod
    def launch_antigravity_ide(app_obj, file_path: Optional[str] = None) -> Dict[str, Any]:
        """Open the application's workspace folder (and optional target file) in Antigravity Desktop / IDE."""
        if not app_obj or not app_obj.local_path or not os.path.exists(app_obj.local_path):
            return {
                "success": False,
                "message": f"Local workspace folder not found for '{getattr(app_obj, 'name', 'App')}'.",
            }

        local_path = os.path.abspath(app_obj.local_path)
        ide_exe = next((p for p in ANTIGRAVITY_IDE_PATHS if os.path.exists(p)), None)

        target_abs = None
        if file_path:
            clean_rel = file_path.replace("\\", "/").lstrip("/")
            cand = os.path.abspath(os.path.join(local_path, clean_rel))
            if cand.startswith(local_path) and os.path.exists(cand):
                target_abs = cand

        try:
            if ide_exe:
                args = [ide_exe, local_path]
                if target_abs:
                    args.append(target_abs)
                subprocess.Popen(args, cwd=local_path, shell=ide_exe.lower().endswith(".cmd"))
                return {
                    "success": True,
                    "ide_path": ide_exe,
                    "local_path": local_path,
                    "target_file": file_path,
                    "message": f"Opened '{app_obj.name}' in Antigravity ({os.path.basename(ide_exe)})!",
                }
            else:
                return WorkspaceService.launch_antigravity_cli(app_obj)
        except Exception as e:
            return {"success": False, "message": f"Failed to launch Antigravity IDE: {e}"}

    @staticmethod
    def _normalize_rel_path(local_root: str, raw_path: Optional[str]) -> Optional[str]:
        if not raw_path or not local_root:
            return None
        clean = str(raw_path).strip()
        if clean.startswith("file:///"):
            from urllib.parse import urlparse
            from urllib.request import url2pathname
            clean = url2pathname(urlparse(clean).path)
        abs_root = os.path.abspath(local_root)
        try:
            abs_cand = (
                os.path.abspath(clean)
                if os.path.isabs(clean)
                else os.path.abspath(os.path.join(abs_root, clean))
            )
            if abs_cand.lower().startswith(abs_root.lower()):
                rel = os.path.relpath(abs_cand, abs_root).replace("\\", "/")
                if rel and rel != "." and not rel.startswith(".."):
                    return rel
        except Exception:
            pass
        return None

    @staticmethod
    def _describe_tool_call(tc_name: str, tc_args: Dict[str, Any], local_root: str) -> Dict[str, Any]:
        """Format an Antigravity SDK ToolCall into a concise UI step badge for the Galactic chat."""
        raw_file = (
            tc_args.get("file_path")
            or tc_args.get("TargetFile")
            or tc_args.get("path")
            or tc_args.get("directory_path")
            or ""
        )
        rel_file = AntigravityService._normalize_rel_path(local_root, raw_file) or str(raw_file)

        if tc_name == "view_file":
            s_line = tc_args.get("start_line")
            e_line = tc_args.get("end_line")
            line_info = (
                f" (lines {int(s_line) + 1}–{int(e_line) + 1})"
                if (s_line is not None and e_line is not None)
                else ""
            )
            return {
                "tool": "view_file",
                "icon": "fa-book-open",
                "file": rel_file,
                "label": "📖 Read file",
                "detail": f"{rel_file}{line_info}",
                "summary": f"Read `{rel_file}`{line_info}",
            }
        elif tc_name == "edit_file":
            return {
                "tool": "edit_file",
                "icon": "fa-pen-to-square",
                "file": rel_file,
                "label": "✏️ Surgically edited",
                "detail": rel_file,
                "summary": f"Surgically edited `{rel_file}`",
            }
        elif tc_name == "create_file":
            return {
                "tool": "create_file",
                "icon": "fa-file-circle-plus",
                "file": rel_file,
                "label": "✨ Created file",
                "detail": rel_file,
                "summary": f"Created/wrote `{rel_file}`",
            }
        elif tc_name == "search_directory":
            query = tc_args.get("query") or tc_args.get("pattern") or tc_args.get("search_term") or ""
            return {
                "tool": "search_directory",
                "icon": "fa-magnifying-glass",
                "file": rel_file,
                "label": "🔍 Searched codebase",
                "detail": str(query)[:50] or rel_file or "workspace",
                "summary": (
                    f"Searched codebase for `{query[:45]}`"
                    if query
                    else f"Searched `{rel_file or 'workspace'}`"
                ),
            }
        elif tc_name == "find_file":
            pat = tc_args.get("pattern") or tc_args.get("name") or ""
            return {
                "tool": "find_file",
                "icon": "fa-folder-magnifying-glass",
                "file": rel_file,
                "label": "📁 Found file",
                "detail": str(pat) or rel_file,
                "summary": f"Located files matching `{pat}`",
            }
        elif tc_name == "list_directory":
            return {
                "tool": "list_directory",
                "icon": "fa-folder-tree",
                "file": rel_file or ".",
                "label": "📂 Listed directory",
                "detail": rel_file or "/",
                "summary": f"Listed directory `{rel_file or '/'}`",
            }
        else:
            return {
                "tool": tc_name,
                "icon": "fa-gears",
                "file": rel_file,
                "label": f"⚙️ {tc_name}",
                "detail": rel_file,
                "summary": f"Ran `{tc_name}`" + (f" on `{rel_file}`" if rel_file else ""),
            }

    @staticmethod
    def _build_numbered_file_preview(content: str, instruction: str, max_chars: int = 24000) -> str:
        """
        Build a 1-indexed line-numbered preview of the target file so the Antigravity agent
        can invoke `edit_file` immediately in a single step without extra discovery roundtrips.
        """
        if not content:
            return ""
        lines = content.splitlines()
        total = len(lines)
        if len(content) <= max_chars:
            return "\n".join(f"{i + 1}: {ln}" for i, ln in enumerate(lines))

        # For very large files, extract the top, bottom, and highest-scoring keyword windows with exact line numbers
        words = [
            w.lower()
            for w in re.findall(r"[A-Za-z_][A-Za-z0-9_\-]{2,}", instruction or "")
            if w.lower()
            not in {
                "the", "and", "for", "with", "that", "this", "from", "into", "when",
                "make", "add", "update", "change", "fix", "code", "file", "app", "use",
            }
        ]
        scored = []
        win_size = 80
        step = 40
        for s in range(0, total, step):
            e = min(total, s + win_size)
            chunk_lower = "\n".join(lines[s:e]).lower()
            sc = sum(3 if w in chunk_lower else 0 for w in set(words))
            if sc > 0:
                scored.append((sc, s, e))
        scored.sort(key=lambda x: (-x[0], x[1]))

        ranges = [(0, min(total, 75))]
        for _, s, e in scored[:4]:
            ranges.append((max(0, s - 10), min(total, e + 10)))
        ranges.append((max(0, total - 75), total))
        ranges.sort(key=lambda r: r[0])

        merged: List[List[int]] = []
        for rng in ranges:
            if not merged or rng[0] > merged[-1][1]:
                merged.append([rng[0], rng[1]])
            else:
                merged[-1][1] = max(merged[-1][1], rng[1])

        parts = []
        used = 0
        for s, e in merged:
            block = "\n".join(f"{idx + 1}: {lines[idx]}" for idx in range(s, e))
            if used + len(block) > max_chars:
                break
            parts.append(f"# --- Lines {s + 1} to {e} of {total} ---\n{block}")
            used += len(block)
        return "\n\n".join(parts)

    @staticmethod
    def run_agent_edit(
        app_obj,
        instruction: str,
        target_file_hint: Optional[str] = None,
        current_code_override: Optional[str] = None,
        sot_grounding: str = "",
        save_to_disk: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """
        Execute a fast, surgical code modification using the warm Antigravity Service session pool.
        """
        if (
            not HAS_ANTIGRAVITY_SDK
            or not app_obj
            or not app_obj.local_path
            or not os.path.exists(app_obj.local_path)
        ):
            return None

        api_key = CentralKeyService.get_api_key()
        if not api_key:
            return None

        t_start = time.perf_counter()
        local_root = os.path.abspath(app_obj.local_path)
        app_name = app_obj.name or app_obj.slug

        clean_hint = (target_file_hint or "").replace("\\", "/").lstrip("/")
        seed_pre_contents: Dict[str, str] = {}
        hint_preview = ""
        abs_hint_path = ""

        if clean_hint:
            abs_hint = os.path.abspath(os.path.join(local_root, clean_hint.replace("/", os.sep)))
            if abs_hint.lower().startswith(local_root.lower()) and os.path.exists(abs_hint):
                abs_hint_path = abs_hint
                try:
                    with open(abs_hint, "r", encoding="utf-8", errors="ignore") as f:
                        disk_txt = f.read()
                    seed_pre_contents[clean_hint] = disk_txt
                    # Sync unsaved frontend override to disk before agent runs
                    if current_code_override and current_code_override != disk_txt:
                        WorkspaceService.save_app_file(app_obj, clean_hint, current_code_override)
                        disk_txt = current_code_override
                        seed_pre_contents[clean_hint] = current_code_override
                    hint_preview = AntigravityService._build_numbered_file_preview(
                        disk_txt, instruction
                    )
                except Exception:
                    pass

        from gitbridge.services.extension_service import ExtensionService
        digest = ExtensionService.get_app_runtime_and_context_digest(
            app_obj, primary_file_path=clean_hint, max_total_chars=10000
        )

        sot_clause = (
            f"\nSource of Truth (SOT) Design Specifications:\n{sot_grounding}\n"
            if sot_grounding
            else ""
        )
        runtime_clause = ""
        if digest.get("project_files"):
            runtime_clause += f"\nProject Files in {app_name}: {', '.join(digest['project_files'][:40])}\n"
        if digest.get("runtime_diagnostic"):
            runtime_clause += f"Runtime & Server Architecture:\n{digest['runtime_diagnostic']}\n"

        if clean_hint and hint_preview:
            file_section = (
                f"{runtime_clause}\n"
                f"Target File Path: `{abs_hint_path}` (relative: `{clean_hint}`)\n"
                f"Pre-loaded File Content (1-indexed line numbers — call `edit_file` directly on `{abs_hint_path}` if the target lines are shown below!):\n"
                f"```\n{hint_preview}\n```\n"
            )
        elif clean_hint:
            abs_new_target = os.path.abspath(os.path.join(local_root, clean_hint.replace("/", os.sep)))
            companion_ctx = f"\nCompanion Project Files Context:\n{digest['multi_file_context']}\n" if digest.get("multi_file_context") else ""
            file_section = (
                f"{runtime_clause}\n"
                f"Target File to Create/Update: `{abs_new_target}` (relative: `{clean_hint}` inside `{local_root}`)\n"
                f"{companion_ctx}"
            )
        else:
            file_section = f"{runtime_clause}\nWorkspace Root: `{local_root}`\n"

        user_prompt = f"""Edit Task for "{app_name}":{sot_clause}{file_section}
Instruction:
{instruction}

Apply the surgical edit(s) now using `edit_file` (or `create_file` if creating a new file like `{clean_hint or 'index.html'}`) and summarize your change in 2-3 concise sentences."""

        AntigravityDaemonPool.begin_live_job(
            mode="edit",
            slug=app_obj.slug,
            app_name=app_name,
            title=instruction[:120],
            target_file=clean_hint,
        )

        async def _execute_warm_edit():
            for attempt in range(2):
                sess = await AntigravityDaemonPool.get_or_create_session(
                    slug=app_obj.slug,
                    app_name=app_name,
                    local_root=local_root,
                    mode="edit",
                    api_key=api_key,
                    task_prompt=instruction,
                )
                async with sess.lock:
                    sess.reset_turn_tracker(seed_contents=seed_pre_contents)
                    sess.turn_count += 1
                    sess.last_used_at = time.time()
                    try:
                        resp = await sess.agent.chat(user_prompt)
                        text = await resp.text()
                        tcs = [tc async for tc in resp.tool_calls]
                        tracker_snapshot = {
                            "pre_contents": dict(sess.active_tracker["pre_contents"]),
                            "touched_files": list(sess.active_tracker["touched_files"]),
                        }
                        # If session has accumulated 3+ edit turns, recycle it in the background after this turn so context stays ultra-lean
                        if sess.turn_count >= 3:
                            AntigravityDaemonPool.submit_background(
                                AntigravityDaemonPool.recycle_session_background(
                                    slug=app_obj.slug,
                                    app_name=app_name,
                                    local_root=local_root,
                                    mode="edit",
                                    api_key=api_key,
                                )
                            )
                        return text, tcs, tracker_snapshot
                    except Exception as turn_err:
                        err_str = str(turn_err)
                        if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "404" in err_str:
                            AntigravityDaemonPool.rotate_model()
                        await sess.close()
                        norm_root = os.path.normcase(os.path.abspath(local_root))
                        AntigravityDaemonPool._sessions.pop((norm_root, "edit"), None)
                        if attempt == 0:
                            continue
                        raise

        try:
            response_text, tool_calls, tracker = AntigravityDaemonPool.run_sync(
                _execute_warm_edit(), timeout=75.0
            )
        except Exception as e:
            print(f"[AntigravityService] Warm agent edit exception for {app_obj.slug}: {e}")
            err_rec = AntigravityDaemonPool.diagnose_and_record_error(
                raw_error=str(e),
                slug=app_obj.slug,
                app_name=app_name,
                mode="edit",
                target_file=clean_hint,
                instruction=instruction,
            )
            AntigravityDaemonPool.finish_live_job(
                success=False,
                elapsed_ms=int((time.perf_counter() - t_start) * 1000),
                summary=f"Edit fallback: {e}",
                antigravity_error=err_rec,
            )
            return None

        elapsed_ms = int((time.perf_counter() - t_start) * 1000)
        AntigravityDaemonPool._requests_served += 1
        AntigravityDaemonPool._last_turn_ms = elapsed_ms

        pre_turn_contents: Dict[str, Optional[str]] = tracker["pre_contents"]
        candidate_rels: List[str] = list(tracker["touched_files"])

        tool_steps: List[Dict[str, Any]] = []
        for tc in tool_calls or []:
            t_name = str(getattr(tc.name, "value", tc.name))
            t_args = dict(tc.args or {})
            step_info = AntigravityService._describe_tool_call(t_name, t_args, local_root)
            tool_steps.append(step_info)
            if t_name in ("edit_file", "create_file"):
                raw_p = (
                    t_args.get("file_path")
                    or t_args.get("TargetFile")
                    or t_args.get("path")
                    or getattr(tc, "canonical_path", None)
                )
                rel = AntigravityService._normalize_rel_path(local_root, raw_p)
                if rel and rel not in candidate_rels:
                    candidate_rels.append(rel)

        if clean_hint and clean_hint not in candidate_rels:
            candidate_rels.append(clean_hint)

        modified_files: List[str] = []
        post_turn_contents: Dict[str, str] = {}

        for rel_p in candidate_rels:
            abs_p = os.path.join(local_root, rel_p.replace("/", os.sep))
            if not os.path.exists(abs_p) or not os.path.isfile(abs_p):
                continue
            try:
                with open(abs_p, "r", encoding="utf-8", errors="ignore") as f:
                    new_txt = f.read()
                old_txt = pre_turn_contents.get(rel_p)
                if old_txt is None or new_txt != old_txt:
                    modified_files.append(rel_p)
                    post_turn_contents[rel_p] = new_txt
            except Exception:
                pass

        if not modified_files:
            err_rec = AntigravityDaemonPool.diagnose_and_record_error(
                raw_error=f"No file changes detected from warm Antigravity session on `{clean_hint or 'workspace'}`. Agent response: {(response_text or '')[:240]}",
                slug=app_obj.slug,
                app_name=app_name,
                mode="edit",
                target_file=clean_hint,
                instruction=instruction,
                error_type_hint="no_changes",
            )
            AntigravityDaemonPool.finish_live_job(
                success=False,
                elapsed_ms=elapsed_ms,
                summary="No file changes detected from warm session; falling back.",
                antigravity_error=err_rec,
            )
            return None

        # Validate Python syntax on any modified .py files; revert if broken
        syntax_errors_caught: List[str] = []
        for rel_p in list(modified_files):
            if rel_p.lower().endswith(".py"):
                import ast
                try:
                    ast.parse(post_turn_contents[rel_p])
                except SyntaxError as syn_err:
                    print(f"[AntigravityService] Reverting invalid Python syntax in {rel_p}: {syn_err}")
                    syntax_errors_caught.append(f"{rel_p}: {syn_err}")
                    old_code = pre_turn_contents.get(rel_p)
                    if old_code is not None:
                        with open(
                            os.path.join(local_root, rel_p.replace("/", os.sep)),
                            "w",
                            encoding="utf-8",
                        ) as rf:
                            rf.write(old_code)
                    modified_files.remove(rel_p)

        if not modified_files:
            err_rec = AntigravityDaemonPool.diagnose_and_record_error(
                raw_error="SyntaxError: " + "; ".join(syntax_errors_caught or ["Invalid Python syntax reverted"]),
                slug=app_obj.slug,
                app_name=app_name,
                mode="edit",
                target_file=clean_hint,
                instruction=instruction,
                error_type_hint="syntax_revert",
            )
            AntigravityDaemonPool.finish_live_job(
                success=False,
                elapsed_ms=elapsed_ms,
                summary="Reverted invalid syntax.",
                antigravity_error=err_rec,
            )
            return None

        from gitbridge.services.extension_service import ExtensionService
        rebuilt_any = False
        for rel_p in modified_files:
            old_txt = pre_turn_contents.get(rel_p) or ""
            new_txt = post_turn_contents[rel_p]

            baseline_file = os.path.join(local_root, ".geppy_baselines", rel_p.replace("/", os.sep))
            latest_file = os.path.join(local_root, ".geppy_latest", rel_p.replace("/", os.sep))
            try:
                if old_txt and not os.path.exists(baseline_file):
                    os.makedirs(os.path.dirname(baseline_file), exist_ok=True)
                    with open(baseline_file, "w", encoding="utf-8") as bf:
                        bf.write(old_txt)
                os.makedirs(os.path.dirname(latest_file), exist_ok=True)
                with open(latest_file, "w", encoding="utf-8") as lf:
                    lf.write(new_txt)
            except Exception:
                pass

            if not save_to_disk and old_txt:
                try:
                    with open(
                        os.path.join(local_root, rel_p.replace("/", os.sep)),
                        "w",
                        encoding="utf-8",
                    ) as rf:
                        rf.write(old_txt)
                except Exception:
                    pass
            else:
                if ExtensionService.maybe_rebuild_frontend_bundle(app_obj, rel_p):
                    rebuilt_any = True

        primary_file = modified_files[0]
        if clean_hint and clean_hint in modified_files:
            primary_file = clean_hint

        files_badge = ", ".join(f"`{p}`" for p in modified_files)
        clean_explanation = (response_text or "").strip()
        if not clean_explanation:
            clean_explanation = f"Antigravity surgically updated {files_badge} ({elapsed_ms}ms) for: {instruction}"
        elif len(modified_files) > 1 and not any(p in clean_explanation for p in modified_files):
            clean_explanation = f"**Edited {len(modified_files)} files ({files_badge}) via Antigravity ({elapsed_ms}ms):**\n\n{clean_explanation}"

        AntigravityDaemonPool.finish_live_job(
            success=True,
            elapsed_ms=elapsed_ms,
            summary=f"Edited {', '.join(modified_files)}",
            modified_files=modified_files,
        )

        return {
            "success": True,
            "engine": "google-antigravity-service",
            "service_port": ANTIGRAVITY_SERVICE_PORT,
            "elapsed_ms": elapsed_ms,
            "target_file": primary_file,
            "modified_files": modified_files,
            "baseline_code": pre_turn_contents.get(primary_file) or "",
            "modified_code": post_turn_contents.get(primary_file, ""),
            "explanation": clean_explanation,
            "tool_steps": tool_steps,
            "saved_to_disk": save_to_disk,
            "rebuilt_bundle": rebuilt_any,
        }

    @staticmethod
    def run_agent_brainstorm(
        app_obj,
        message: str,
        history: List[Dict[str, str]] = [],
        file_path: Optional[str] = None,
        sot_grounding: str = "",
        project_files_list: Optional[List[str]] = None,
        best_file: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Run fast conversational brainstorming & codebase exploration using the warm Antigravity Service session pool.
        """
        if (
            not HAS_ANTIGRAVITY_SDK
            or not app_obj
            or not app_obj.local_path
            or not os.path.exists(app_obj.local_path)
        ):
            return None

        api_key = CentralKeyService.get_api_key()
        if not api_key:
            return None

        t_start = time.perf_counter()
        local_root = os.path.abspath(app_obj.local_path)
        app_name = app_obj.name or app_obj.slug
        is_gb = bool(
            app_obj.slug and app_obj.slug.lower() in ("geppys-gitbridge", "gitbridge")
        ) or ("gitbridge" in app_name.lower())
        persona_name = "Captain Geppy" if is_gb else "Geppy"

        if project_files_list is None:
            tree = WorkspaceService.get_app_file_tree(app_obj)
            project_files_list = [f.get("path") for f in (tree or []) if f.get("path")]

        from gitbridge.services.extension_service import ExtensionService
        if best_file is None:
            best_file = ExtensionService.resolve_best_target_file(app_obj, message, file_path)
        digest = ExtensionService.get_app_runtime_and_context_digest(
            app_obj, primary_file_path=best_file, max_total_chars=12000
        )
        if not project_files_list:
            project_files_list = digest.get("project_files", [])

        preloaded_snippet = ""
        if digest.get("runtime_diagnostic"):
            preloaded_snippet += f"\nRuntime & Server Architecture Diagnostics:\n{digest['runtime_diagnostic']}\n"
        if digest.get("multi_file_context"):
            preloaded_snippet += f"\n{digest['multi_file_context']}\n"
        elif best_file:
            f_res = WorkspaceService.read_app_file(app_obj, best_file)
            if f_res.get("success") and f_res.get("content"):
                preloaded_snippet += (
                    f"\nPre-loaded Relevant File (`{best_file}`):\n"
                    f"```\n{f_res['content'][:5500]}\n```\n"
                )

        history_summary = ""
        if history:
            recent = history[-5:]
            lines = []
            for h in recent:
                who = "User" if h.get("sender") == "user" else persona_name
                txt = (h.get("text") or "").strip()
                if txt:
                    lines.append(f"{who}: {txt[:400]}")
            if lines:
                history_summary = "Recent Conversation History:\n" + "\n".join(lines) + "\n\n"

        files_header = f"Project Files in {app_name}: {', '.join(project_files_list[:45])}\n" if project_files_list else ""
        hint_info = f"Active File in Sidebar: `{file_path}`\n" if file_path else ""
        sot_info = f"{sot_grounding}\n" if sot_grounding else ""
        full_prompt = (
            f"{files_header}{hint_info}{sot_info}{preloaded_snippet}"
            f"{history_summary}User Message:\n{message}"
        )

        AntigravityDaemonPool.begin_live_job(
            mode="brainstorm",
            slug=app_obj.slug,
            app_name=app_name,
            title=message[:120],
            target_file=best_file or file_path or "",
        )

        async def _execute_warm_brainstorm():
            for attempt in range(2):
                sess = await AntigravityDaemonPool.get_or_create_session(
                    slug=app_obj.slug,
                    app_name=app_name,
                    local_root=local_root,
                    mode="brainstorm",
                    api_key=api_key,
                    task_prompt=message,
                )
                async with sess.lock:
                    sess.turn_count += 1
                    sess.last_used_at = time.time()
                    try:
                        resp = await sess.agent.chat(full_prompt)
                        text = await resp.text()
                        tcs = [tc async for tc in resp.tool_calls]
                        if sess.turn_count >= 5:
                            AntigravityDaemonPool.submit_background(
                                AntigravityDaemonPool.recycle_session_background(
                                    slug=app_obj.slug,
                                    app_name=app_name,
                                    local_root=local_root,
                                    mode="brainstorm",
                                    api_key=api_key,
                                )
                            )
                        return text, tcs
                    except Exception as turn_err:
                        err_str = str(turn_err)
                        if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "404" in err_str:
                            AntigravityDaemonPool.rotate_model()
                        await sess.close()
                        norm_root = os.path.normcase(os.path.abspath(local_root))
                        AntigravityDaemonPool._sessions.pop((norm_root, "brainstorm"), None)
                        if attempt == 0:
                            continue
                        raise

        try:
            raw_response, tool_calls = AntigravityDaemonPool.run_sync(
                _execute_warm_brainstorm(), timeout=65.0
            )
        except Exception as e:
            print(f"[AntigravityService] Warm agent brainstorm exception for {app_obj.slug}: {e}")
            err_rec = AntigravityDaemonPool.diagnose_and_record_error(
                raw_error=str(e),
                slug=app_obj.slug,
                app_name=app_name,
                mode="brainstorm",
                target_file=best_file or file_path or "",
                instruction=message,
            )
            AntigravityDaemonPool.finish_live_job(
                success=False,
                elapsed_ms=int((time.perf_counter() - t_start) * 1000),
                summary=f"Brainstorm fallback: {e}",
                antigravity_error=err_rec,
            )
            return None

        if not raw_response or not raw_response.strip():
            AntigravityDaemonPool.finish_live_job(
                success=False,
                elapsed_ms=int((time.perf_counter() - t_start) * 1000),
                summary="Empty response",
            )
            return None

        elapsed_ms = int((time.perf_counter() - t_start) * 1000)
        AntigravityDaemonPool._requests_served += 1
        AntigravityDaemonPool._last_turn_ms = elapsed_ms

        tool_steps = [
            AntigravityService._describe_tool_call(
                str(getattr(tc.name, "value", tc.name)),
                dict(tc.args or {}),
                local_root,
            )
            for tc in (tool_calls or [])
        ]

        AntigravityDaemonPool.finish_live_job(
            success=True,
            elapsed_ms=elapsed_ms,
            summary=f"Response ready ({len(tool_steps)} tool steps)",
        )

        return {
            "raw_response": raw_response,
            "tool_steps": tool_steps,
            "engine": "google-antigravity-service",
            "service_port": ANTIGRAVITY_SERVICE_PORT,
            "elapsed_ms": elapsed_ms,
        }

    @staticmethod
    def respond_to_antigravity(
        slug: str = "",
        response_text: str = "",
        error_id: Optional[str] = None,
        action: Optional[str] = None,
        file_path: Optional[str] = None,
        current_code: Optional[str] = None,
        db=None,
        user_response: Optional[str] = None,
        original_instruction: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Accept a user's response/instruction to Antigravity directly within Galactic chat (or GitBridge chat).
        Resolves the error context, optionally rotates the model or resets the warm session,
        and executes the user's guidance against Antigravity.
        """
        from gitbridge.services.extension_service import ExtensionService

        err_rec = None
        if error_id:
            for e in AntigravityDaemonPool._error_log:
                if e.get("id") == error_id:
                    err_rec = e
                    break
        if not err_rec:
            open_errs = AntigravityDaemonPool.get_errors(slug=slug, include_resolved=False)
            if open_errs:
                err_rec = open_errs[0]

        user_reply = (response_text or user_response or "").strip()
        if not user_reply and err_rec:
            suggested = err_rec.get("suggested_replies") or []
            if suggested:
                user_reply = suggested[0].get("reply") or "Retry this task cleanly."

        target_slug = slug or (err_rec.get("slug") if err_rec else "") or "geppys-gitbridge"
        target_file = file_path or (err_rec.get("target_file") if err_rec else "") or ""
        orig_instruction = original_instruction or (err_rec.get("instruction") if err_rec else "") or ""
        err_summary = (err_rec.get("what_is_the_error") if err_rec else "") or ""

        rotated_model = None
        if action in ("rotate_and_retry", "fallback_retry") or "rotate" in user_reply.lower() or "switch model" in user_reply.lower():
            rotated_model = AntigravityDaemonPool.rotate_model()

        if action in ("acknowledge", "dismiss"):
            if err_rec:
                AntigravityDaemonPool.mark_error_status(
                    err_rec["id"], status="resolved", user_response=user_reply
                )
            msg = f"Acknowledged and resolved Antigravity issue{f' (switched active model to `{rotated_model}`)' if rotated_model else ''}."
            return {
                "ok": True,
                "status": "success",
                "action_taken": "acknowledged",
                "mode": "acknowledge",
                "error_id": err_rec.get("id") if err_rec else error_id,
                "error_resolved": True,
                "rotated_to_model": rotated_model,
                "user_response": user_reply,
                "message": msg,
                "spoken_reply": msg,
            }

        if err_rec:
            AntigravityDaemonPool.mark_error_status(
                err_rec["id"], status="responded", user_response=user_reply
            )

        # Decide whether the user wants Antigravity to apply the edit or discuss/inspect in brainstorm mode
        is_edit_intent = (
            action in ("rotate_and_retry", "surgical_retry", "reset_and_retry", "fallback_retry")
            or (err_rec and err_rec.get("mode") == "edit" and action != "brainstorm_clarify")
            or any(
                kw in user_reply.lower()
                for kw in ("edit_file", "apply", "retry", "fix", "patch", "update", "re-apply")
            )
        )

        if is_edit_intent and target_slug:
            combined_instruction = (
                f"{orig_instruction}\n\n"
                f"[USER RESPONSE TO ANTIGRAVITY ERROR ({err_rec.get('error_type') if err_rec else 'session'})]:\n"
                f"Previous Issue: {err_summary}\n"
                f"User Instruction to Antigravity: {user_reply}\n"
                f"CRITICAL: Use surgical `edit_file` replacements on `{target_file or 'the target file'}` and preserve all unrelated code."
            ).strip()

            edit_res = ExtensionService.apply_design(
                slug=target_slug,
                file_path=target_file,
                current_code=current_code or "",
                instruction=combined_instruction,
                db=db,
                save_to_disk=True,
            )
            if err_rec and edit_res.get("success"):
                AntigravityDaemonPool.mark_error_status(
                    err_rec["id"], status="resolved", user_response=user_reply
                )
            msg = edit_res.get("message") or edit_res.get("summary") or "Antigravity processed your edit instruction."
            return {
                "ok": bool(edit_res.get("success")),
                "status": "success" if edit_res.get("success") else "error",
                "action_taken": action or "edit_retry",
                "mode": "edit",
                "error_id": err_rec.get("id") if err_rec else error_id,
                "error_resolved": bool(edit_res.get("success")),
                "rotated_to_model": rotated_model,
                "user_response": user_reply,
                "message": msg,
                "spoken_reply": msg,
                **edit_res,
            }
        else:
            combined_msg = (
                f"[USER RESPONSE TO ANTIGRAVITY ({err_rec.get('title') if err_rec else 'Session'})]:\n"
                f"{f'Original Task: {orig_instruction}' if orig_instruction else ''}\n"
                f"{f'Previous Antigravity Error: {err_summary}' if err_summary else ''}\n\n"
                f"User Response / Instruction to Antigravity:\n{user_reply}"
            ).strip()
            bs_res = ExtensionService.brainstorm(
                slug=target_slug,
                message=combined_msg,
                history=[],
                file_path=target_file,
                is_image=False,
                db=db,
            )
            if err_rec:
                AntigravityDaemonPool.mark_error_status(
                    err_rec["id"], status="resolved", user_response=user_reply
                )
            msg = bs_res.get("text") or "Antigravity responded to your instruction."
            return {
                "ok": True,
                "status": "success",
                "action_taken": action or "brainstorm_reply",
                "mode": "brainstorm",
                "error_id": err_rec.get("id") if err_rec else error_id,
                "error_resolved": True,
                "rotated_to_model": rotated_model,
                "user_response": user_reply,
                "message": msg,
                "spoken_reply": bs_res.get("spoken_reply") or msg[:450],
                **bs_res,
            }


def create_antigravity_port_app() -> FastAPI:
    """
    Create the dedicated FastAPI microservice bound to Port 8001 (`http://127.0.0.1:8001`).
    Allows Galactic (Chrome Extension) and GitBridge to communicate directly with the warm
    Antigravity Daemon Pool over its own dedicated local port.
    """
    ag_app = FastAPI(
        title="Geppy's Antigravity Port Service",
        description="Dedicated Warm Google Antigravity Agent Pool & Fast Communication Bridge",
        version="2.0.0",
    )

    ag_app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @ag_app.get("/")
    @ag_app.get("/health")
    @ag_app.get("/status")
    @ag_app.get("/api/extension/antigravity/status")
    async def get_service_status():
        return AntigravityService.get_antigravity_status()

    @ag_app.get("/live")
    @ag_app.get("/api/extension/antigravity/live")
    async def get_live_activity_endpoint():
        return AntigravityDaemonPool.get_live_activity()

    @ag_app.get("/errors")
    @ag_app.get("/api/extension/antigravity/errors")
    async def get_antigravity_errors_endpoint(
        slug: Optional[str] = None,
        include_resolved: bool = True,
        unresolved_only: bool = False,
        limit: int = 25,
    ):
        errors = AntigravityDaemonPool.get_errors(
            slug=slug,
            include_resolved=include_resolved,
            unresolved_only=unresolved_only,
            limit=limit,
        )
        open_errs = [e for e in errors if e.get("status") == "open"]
        latest_open = open_errs[0] if open_errs else None
        return {
            "errors": errors,
            "open_count": len(open_errs),
            "latest_error": latest_open or (errors[0] if errors else None),
            "latest_unresolved": latest_open,
            "active_model": AntigravityDaemonPool.get_active_model(),
        }

    @ag_app.post("/errors/clear")
    @ag_app.post("/api/extension/antigravity/errors/clear")
    async def clear_antigravity_errors_endpoint(payload: dict = {}):
        slug = (payload.get("slug") or "").strip() or None
        error_id = (payload.get("error_id") or "").strip() or None
        cleared = AntigravityDaemonPool.clear_errors(slug=slug, error_id=error_id)
        return {"success": True, "cleared": cleared}

    @ag_app.post("/report-error")
    @ag_app.post("/api/extension/antigravity/report-error")
    async def report_antigravity_error_endpoint(payload: dict = {}):
        """Allow reporting or diagnosing an external Antigravity error directly."""
        raw_error = (payload.get("raw_error") or payload.get("error") or payload.get("message") or "").strip()
        if not raw_error:
            raise HTTPException(status_code=400, detail="Error text is required")
        rec = AntigravityDaemonPool.diagnose_and_record_error(
            raw_error=raw_error,
            slug=(payload.get("slug") or payload.get("app_slug") or "").strip(),
            app_name=(payload.get("app_name") or "").strip(),
            mode=(payload.get("mode") or "edit").strip(),
            target_file=(payload.get("target_file") or payload.get("file_path") or "").strip(),
            instruction=(payload.get("instruction") or "").strip(),
            error_type_hint=(payload.get("error_type") or "").strip(),
            source=(payload.get("source") or "antigravity").strip(),
        )
        return {"success": True, "error": rec}

    @ag_app.post("/respond")
    @ag_app.post("/api/extension/antigravity/respond")
    def respond_to_antigravity_endpoint(payload: dict = {}):
        """Accept a user's response/instruction to Antigravity from Galactic chat."""
        from gitbridge.db.database import SessionLocal

        slug = (payload.get("slug") or payload.get("app_slug") or "").strip()
        response_text = (
            payload.get("response_text")
            or payload.get("user_response")
            or payload.get("message")
            or payload.get("reply")
            or ""
        ).strip()
        error_id = (payload.get("error_id") or "").strip() or None
        action = (payload.get("action") or "").strip() or None
        file_path = (payload.get("file_path") or payload.get("target_file") or "").strip() or None
        current_code = payload.get("current_code")
        original_instruction = payload.get("original_instruction")

        db = SessionLocal()
        try:
            return AntigravityService.respond_to_antigravity(
                slug=slug,
                response_text=response_text,
                error_id=error_id,
                action=action,
                file_path=file_path,
                current_code=current_code,
                original_instruction=original_instruction,
                db=db,
            )
        finally:
            db.close()

    @ag_app.post("/warm")
    @ag_app.post("/api/extension/antigravity/warm")
    async def warm_app_endpoint(payload: dict = {}):
        slug = (payload.get("slug") or "").strip()
        local_path = (payload.get("local_path") or "").strip()
        app_name = (payload.get("name") or slug or "App").strip()

        if not local_path and slug:
            from gitbridge.db.database import SessionLocal
            from gitbridge.db.models import AppProfileModel
            db = SessionLocal()
            try:
                app_obj = db.query(AppProfileModel).filter(AppProfileModel.slug == slug).first()
                if app_obj:
                    local_path = app_obj.local_path or ""
                    app_name = app_obj.name or slug
            finally:
                db.close()

        if not local_path or not os.path.exists(local_path):
            return {"warmed": False, "slug": slug, "message": "No valid local_path found"}

        # Trigger immediate async pre-warm on this event loop
        asyncio.create_task(
            AntigravityDaemonPool.prewarm_app_sessions(
                slug=slug or os.path.basename(local_path),
                app_name=app_name,
                local_root=local_path,
                modes=("edit", "brainstorm"),
            )
        )
        return {
            "warmed": True,
            "slug": slug,
            "service_port": ANTIGRAVITY_SERVICE_PORT,
            "service_url": ANTIGRAVITY_SERVICE_URL,
            "message": f"Warming Antigravity sessions for '{app_name}' on port {ANTIGRAVITY_SERVICE_PORT}",
        }

    @ag_app.post("/reset")
    @ag_app.post("/api/extension/antigravity/reset")
    async def reset_sessions_endpoint(payload: dict = {}):
        slug = (payload.get("slug") or "").strip()
        closed_count = 0
        for key, sess in list(AntigravityDaemonPool._sessions.items()):
            if not slug or sess.slug == slug:
                await sess.close()
                AntigravityDaemonPool._sessions.pop(key, None)
                closed_count += 1
        return {"reset": True, "closed_sessions": closed_count, "slug": slug or "all"}

    @ag_app.post("/brainstorm")
    @ag_app.post("/api/extension/brainstorm")
    def port_brainstorm_endpoint(payload: dict = {}):
        """Direct port 8001 pathway for Galactic Brainstorm requests."""
        from gitbridge.db.database import SessionLocal
        from gitbridge.services.extension_service import ExtensionService

        message = (payload.get("message") or payload.get("prompt") or "").strip()
        history = payload.get("history", [])
        if not message and isinstance(payload.get("messages"), list) and payload["messages"]:
            msgs = payload["messages"]
            last_msg = msgs[-1]
            message = str(last_msg.get("content") or last_msg.get("text") or "").strip() if isinstance(last_msg, dict) else str(last_msg).strip()
            if not history and len(msgs) > 1:
                history = msgs[:-1]
        if not message:
            raise HTTPException(status_code=400, detail="Message is required")
        slug = payload.get("slug")
        file_path = payload.get("file_path")
        is_image = bool(payload.get("is_image", False))
        agent_id = payload.get("agent_id")
        screen_frame_b64 = payload.get("screen_frame_b64")
        voice_mode = bool(payload.get("voice_mode", False))
        consult_crew = bool(payload.get("consult_crew", False))

        db = SessionLocal()
        try:
            return ExtensionService.brainstorm(
                slug=slug,
                message=message,
                history=history,
                file_path=file_path,
                is_image=is_image,
                db=db,
                agent_id=agent_id,
                screen_frame_b64=screen_frame_b64,
                voice_mode=voice_mode,
                consult_crew=consult_crew,
            )
        finally:
            db.close()

    @ag_app.post("/edit")
    @ag_app.post("/execute")
    @ag_app.post("/apply-design")
    @ag_app.post("/api/extension/execute")
    @ag_app.post("/api/extension/apply-design")
    def port_apply_design_endpoint(payload: dict = {}):
        """Direct port 8001 pathway for Galactic & Agent Crew surgical code edits."""
        from gitbridge.db.database import SessionLocal
        from gitbridge.services.extension_service import ExtensionService

        slug = (payload.get("slug") or payload.get("app_slug") or "").strip()
        file_path = (payload.get("file_path") or payload.get("target_file") or "").strip()
        current_code = payload.get("current_code", "")
        instruction = (
            payload.get("instruction")
            or payload.get("task_prompt")
            or payload.get("suggested_prompt")
            or payload.get("prompt")
            or payload.get("task_title")
            or ""
        ).strip()
        save_to_disk = bool(payload.get("save_to_disk", True))

        if not instruction:
            raise HTTPException(status_code=400, detail="Instruction is required")

        db = SessionLocal()
        try:
            res = ExtensionService.apply_design(
                slug=slug,
                file_path=file_path,
                current_code=current_code,
                instruction=instruction,
                db=db,
                save_to_disk=save_to_disk,
            )
            if isinstance(res, dict) and "summary" not in res:
                res["summary"] = res.get("explanation") or "Task executed via Antigravity Bridge."
            return res
        finally:
            db.close()

    return ag_app

