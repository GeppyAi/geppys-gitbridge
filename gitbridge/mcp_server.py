import sys
import os
import json
import traceback
from typing import Dict, Any, List

# Ensure python path includes project root
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from gitbridge.db.database import SessionLocal, init_db
from gitbridge.db.models import AppProfileModel
from gitbridge.services.workspace_service import WorkspaceService
from gitbridge.services.context_service import GeminiContextService
from gitbridge.services.analyzer_service import AppAnalyzerService
from gitbridge.services.launcher_service import AppLauncherService

TOOLS_MANIFEST = [
    {
        "name": "list_universe_apps",
        "description": "List all applications registered in Geppy's App Universe catalog along with status, tech stack, and sync state.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "description": "Optional filter by status: idea, in_development, production, archived"}
            }
        }
    },
    {
        "name": "get_universe_context",
        "description": "Retrieve complete, structured Markdown context dump of all applications in Geppy's App Universe for planning and architecture design.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "get_app_context",
        "description": "Retrieve deep technical context, directory structure, system prompt, health status, and code samples for a specific app.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "slug": {"type": "string", "description": "Unique app slug identifier (e.g., 'geppys-gitbridge')"}
            },
            "required": ["slug"]
        }
    },
    {
        "name": "analyze_app",
        "description": "Run AI architectural code analysis & purpose auto-fill on an application repository.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "slug": {"type": "string", "description": "App slug identifier to analyze"}
            },
            "required": ["slug"]
        }
    },
    {
        "name": "launch_app",
        "description": "Launch an application on localhost server or open its local entrypoint.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "slug": {"type": "string", "description": "App slug identifier to launch"}
            },
            "required": ["slug"]
        }
    },
    {
        "name": "push_app_to_github",
        "description": "Stage, commit, and push local application code changes to GitHub repository.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "slug": {"type": "string", "description": "App slug identifier"},
                "commit_message": {"type": "string", "description": "Git commit message (optional)"}
            },
            "required": ["slug"]
        }
    },
    {
        "name": "read_app_file",
        "description": "Read the text contents of a file inside an application's local workspace folder.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "slug": {"type": "string", "description": "App slug identifier"},
                "file_path": {"type": "string", "description": "Relative file path inside app folder (e.g. 'package.json', 'README.md', 'src/App.tsx')"}
            },
            "required": ["slug", "file_path"]
        }
    },
    {
        "name": "export_gemini_context",
        "description": "Export the master GEMINI_UNIVERSE_CONTEXT.md file into the local workspace folder.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    }
]

def handle_tool_call(name: str, args: Dict[str, Any]) -> str:
    init_db()
    db = SessionLocal()

    try:
        if name == "list_universe_apps":
            status_filter = args.get("status")
            query = db.query(AppProfileModel)
            if status_filter:
                query = query.filter(AppProfileModel.status == status_filter)
            apps = query.all()
            res = []
            for a in apps:
                sync_info = WorkspaceService.get_app_sync_status(a)
                res.append({
                    "slug": a.slug,
                    "name": a.name,
                    "status": a.status.value if hasattr(a.status, 'value') else str(a.status),
                    "local_path": sync_info.get("local_path"),
                    "github_url": a.github_url,
                    "sync_state": sync_info["sync_label"],
                    "tech_stack": a.tech_stack,
                    "version": a.version
                })
            return json.dumps({"app_count": len(res), "apps": res}, indent=2)

        elif name == "get_universe_context":
            return GeminiContextService.generate_universe_markdown(db)

        elif name == "get_app_context":
            slug = args.get("slug")
            app_obj = db.query(AppProfileModel).filter(AppProfileModel.slug == slug).first()
            if not app_obj:
                return f"Error: App with slug '{slug}' not found in catalog."
            return GeminiContextService.generate_app_markdown(app_obj, db)

        elif name == "analyze_app":
            slug = args.get("slug")
            app_obj = db.query(AppProfileModel).filter(AppProfileModel.slug == slug).first()
            if not app_obj:
                return f"Error: App with slug '{slug}' not found."
            analyzer = AppAnalyzerService()
            result = analyzer.analyze_and_autofill_app(app_obj, db)
            return json.dumps(result, indent=2)

        elif name == "launch_app":
            slug = args.get("slug")
            app_obj = db.query(AppProfileModel).filter(AppProfileModel.slug == slug).first()
            if not app_obj:
                return f"Error: App with slug '{slug}' not found."
            result = AppLauncherService.launch_localhost(app_obj)
            return json.dumps(result, indent=2)

        elif name == "push_app_to_github":
            slug = args.get("slug")
            msg = args.get("commit_message")
            app_obj = db.query(AppProfileModel).filter(AppProfileModel.slug == slug).first()
            if not app_obj:
                return f"Error: App with slug '{slug}' not found."
            res = WorkspaceService.push_app_to_github(app_obj, commit_message=msg, db=db)
            return json.dumps(res, indent=2)

        elif name == "read_app_file":
            slug = args.get("slug")
            file_path = args.get("file_path")
            app_obj = db.query(AppProfileModel).filter(AppProfileModel.slug == slug).first()
            if not app_obj:
                return f"Error: App with slug '{slug}' not found."

            local_path = AppLauncherService.detect_local_path(app_obj)
            if not local_path or not os.path.exists(local_path):
                return f"Error: Local directory for '{slug}' does not exist on disk."

            clean_rel = file_path.replace("\\", "/").lstrip("/")
            target_abs = os.path.abspath(os.path.join(local_path, clean_rel))

            if not target_abs.startswith(os.path.abspath(local_path)):
                return "Error: Path traversal outside app directory prohibited."

            if not os.path.exists(target_abs) or not os.path.isfile(target_abs):
                return f"Error: File '{file_path}' does not exist in app folder."

            with open(target_abs, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read(50000)

            return f"--- File: {clean_rel} (Path: {target_abs}) ---\n\n{content}"

        elif name == "export_gemini_context":
            res = GeminiContextService.export_context_file(db)
            return json.dumps(res, indent=2)

        else:
            return f"Error: Unknown tool name '{name}'"

    except Exception as e:
        return f"Error executing tool '{name}': {e}\n{traceback.format_exc()}"
    finally:
        db.close()

def run_stdio_mcp_server():
    """Run Model Context Protocol (MCP) server over standard input/output."""
    sys.stderr.write("[GitBridge MCP Server] Starting stdio MCP server for Gemini...\n")
    sys.stderr.flush()

    while True:
        line = sys.stdin.readline()
        if not line:
            break
        line = line.strip()
        if not line:
            continue

        try:
            req = json.loads(line)
            req_id = req.get("id")
            method = req.get("method")
            params = req.get("params", {})

            if method == "initialize":
                resp = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {
                            "tools": {}
                        },
                        "serverInfo": {
                            "name": "gitbridge-mcp",
                            "version": "0.1.0"
                        }
                    }
                }
            elif method == "notifications/initialized":
                continue
            elif method == "tools/list":
                resp = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "tools": TOOLS_MANIFEST
                    }
                }
            elif method == "tools/call":
                tool_name = params.get("name")
                tool_args = params.get("arguments", {})
                result_text = handle_tool_call(tool_name, tool_args)
                resp = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": result_text
                            }
                        ]
                    }
                }
            elif method == "ping":
                resp = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {}
                }
            else:
                resp = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {
                        "code": -32601,
                        "message": f"Method '{method}' not found"
                    }
                }

            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()

        except Exception as e:
            err_resp = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {
                    "code": -32603,
                    "message": f"Internal RPC error: {e}"
                }
            }
            sys.stdout.write(json.dumps(err_resp) + "\n")
            sys.stdout.flush()

if __name__ == "__main__":
    run_stdio_mcp_server()
