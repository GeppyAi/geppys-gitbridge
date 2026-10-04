import os
import sys
import json
import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from typing import Optional, List
from sqlalchemy.orm import Session

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from gitbridge.db.database import SessionLocal, init_db
from gitbridge.db.models import AppProfileModel, MediaAssetModel, DocManualModel
from gitbridge.schemas.app_profile import AppStatus, AssetType
from gitbridge.services.github_service import GitHubService
from gitbridge.services.sheets_service import GoogleSheetsService
from gitbridge.services.ai_studio_service import AIStudioParser

app = typer.Typer(help="Geppy's GitBridge CLI - App Universe Catalog & Context Bridge")
console = Console()

def get_db():
    init_db()
    return SessionLocal()

@app.command("init")
def init_cmd():
    """Initialize local GitBridge SQLite database and directory structure."""
    init_db()
    os.makedirs("./assets", exist_ok=True)
    os.makedirs("./docs", exist_ok=True)
    console.print("[bold green][OK] GitBridge Database & Asset directories initialized successfully![/bold green]")

@app.command("list")
def list_apps(status: Optional[str] = None):
    """List all applications in Geppy's App Universe."""
    db = get_db()
    query = db.query(AppProfileModel)
    if status:
        query = query.filter(AppProfileModel.status == status)
    apps = query.all()

    if not apps:
        console.print("[yellow]No applications found in GitBridge catalog. Run 'gitbridge sync github' or 'gitbridge app add' to register apps.[/yellow]")
        return

    table = Table(title="Geppy's App Universe Catalog", show_lines=True)
    table.add_column("Slug", style="cyan", no_wrap=True)
    table.add_column("Name", style="bold white")
    table.add_column("Status", style="magenta")
    table.add_column("Tech Stack", style="green")
    table.add_column("GitHub URL", style="blue")
    table.add_column("Version", style="dim")

    for a in apps:
        table.add_row(
            a.slug,
            a.name,
            a.status.value if hasattr(a.status, 'value') else str(a.status),
            ", ".join(a.tech_stack),
            a.github_url or "N/A",
            a.version
        )

    console.print(table)
    db.close()

@app.command("get")
def get_app(slug: str):
    """View full profile, system instructions, assets, and documentation for an app."""
    db = get_db()
    app_obj = db.query(AppProfileModel).filter(AppProfileModel.slug == slug).first()
    if not app_obj:
        console.print(f"[bold red]App with slug '{slug}' not found.[/bold red]")
        db.close()
        return

    details = (
        f"[bold]Name:[/bold] {app_obj.name}\n"
        f"[bold]Status:[/bold] {app_obj.status.value if hasattr(app_obj.status, 'value') else str(app_obj.status)}\n"
        f"[bold]GitHub:[/bold] {app_obj.github_url or 'N/A'}\n"
        f"[bold]AI Studio Link:[/bold] {app_obj.ai_studio_link or 'N/A'}\n"
        f"[bold]Tech Stack:[/bold] {', '.join(app_obj.tech_stack)}\n"
        f"[bold]Tags:[/bold] {', '.join(app_obj.tags)}\n"
        f"[bold]Version:[/bold] {app_obj.version}\n\n"
        f"[bold]Description:[/bold]\n{app_obj.description or 'No description provided.'}\n\n"
        f"[bold]System Instructions / Prompts:[/bold]\n"
        f"{app_obj.system_instructions or 'None stored.'}"
    )

    console.print(Panel(details, title=f"📱 App Profile: {app_obj.slug}", border_style="cyan"))
    
    if app_obj.assets:
        console.print("\n[bold yellow]📸 Media & Marketing Assets:[/bold yellow]")
        for asset in app_obj.assets:
            console.print(f" - [{asset.asset_type.value}] {asset.title}: {asset.file_path}")

    if app_obj.manuals:
        console.print("\n[bold yellow]📚 Instruction Manuals:[/bold yellow]")
        for doc in app_obj.manuals:
            console.print(f" - {doc.title} ({doc.file_path or 'Inline'})")

    db.close()

@app.command("add")
def add_app(
    slug: str = typer.Option(..., help="Unique slug identifier"),
    name: str = typer.Option(..., help="App name"),
    description: Optional[str] = typer.Option(None, help="App description"),
    github_url: Optional[str] = typer.Option(None, help="GitHub repository URL"),
    ai_studio_link: Optional[str] = typer.Option(None, help="AI Studio project link"),
    status: str = typer.Option("in_development", help="Status (idea, in_development, production, archived)"),
    tech_stack: Optional[str] = typer.Option(None, help="Comma-separated tech stack elements")
):
    """Add or register a new app profile manually."""
    db = get_db()
    existing = db.query(AppProfileModel).filter(AppProfileModel.slug == slug).first()
    if existing:
        console.print(f"[red]App with slug '{slug}' already exists. Use update instead.[/red]")
        db.close()
        return

    stack_list = [t.strip() for t in tech_stack.split(",")] if tech_stack else []
    app_obj = AppProfileModel(
        slug=slug,
        name=name,
        description=description,
        status=AppStatus(status),
        github_url=github_url,
        ai_studio_link=ai_studio_link,
        version="0.1.0"
    )
    app_obj.tech_stack = stack_list

    db.add(app_obj)
    db.commit()
    console.print(f"[bold green][OK] App '{name}' ({slug}) registered successfully![/bold green]")
    db.close()

@app.command("sync-github")
def sync_github(
    username: Optional[str] = typer.Option(None, help="GitHub username to sync repos from"),
    repo: Optional[str] = typer.Option(None, help="Specific GitHub repository URL or owner/repo (e.g. 'octocat/Hello-World')")
):
    """Sync repository or repositories from GitHub into GitBridge catalog."""
    gh_service = GitHubService()
    db = get_db()
    
    try:
        if repo:
            console.print(f"[cyan]Fetching repository '{repo}'...[/cyan]")
            repo_data = gh_service.fetch_repo_details(repo)
            repos = [repo_data] if repo_data else []
        else:
            console.print("[cyan]Fetching GitHub repositories...[/cyan]")
            repos = gh_service.fetch_user_repos(username)

        added_count = 0
        updated_count = 0

        for r in repos:
            parsed = gh_service.parse_repo_to_profile_dict(r)
            slug = parsed["slug"]
            existing = db.query(AppProfileModel).filter(AppProfileModel.slug == slug).first()

            if not existing:
                app_obj = AppProfileModel(
                    slug=slug,
                    name=parsed["name"],
                    description=parsed["description"],
                    status=AppStatus(parsed["status"]),
                    github_url=parsed["github_url"],
                    github_repo_name=parsed["github_repo_name"],
                    version=parsed["version"]
                )
                app_obj.tech_stack = parsed["tech_stack"]
                app_obj.tags = parsed["tags"]
                db.add(app_obj)
                added_count += 1
            else:
                existing.github_url = parsed["github_url"]
                existing.github_repo_name = parsed["github_repo_name"]
                if parsed["description"]:
                    existing.description = parsed["description"]
                existing.tech_stack = list(dict.fromkeys(existing.tech_stack + parsed["tech_stack"]))
                updated_count += 1

        db.commit()
        console.print(f"[bold green][OK] GitHub Sync Complete! Added {added_count} new apps, updated {updated_count} existing apps.[/bold green]")
    except Exception as e:
        console.print(f"[bold red]GitHub Sync failed: {e}[/bold red]")
    finally:
        db.close()

@app.command("sync-sheets")
def sync_sheets(export_csv: bool = typer.Option(False, help="Force export to local CSV file preview")):
    """Sync current GitBridge catalog with central Google Sheet (or CSV fallback)."""
    db = get_db()
    apps = db.query(AppProfileModel).all()
    
    app_dicts = []
    for a in apps:
        app_dicts.append({
            "slug": a.slug,
            "name": a.name,
            "description": a.description,
            "status": a.status.value if hasattr(a.status, 'value') else str(a.status),
            "github_url": a.github_url,
            "ai_studio_link": a.ai_studio_link,
            "tech_stack": a.tech_stack,
            "tags": a.tags,
            "version": a.version,
            "updated_at": a.updated_at
        })

    sheets_service = GoogleSheetsService()
    if export_csv:
        csv_path = sheets_service.export_to_csv_preview(app_dicts)
        console.print(f"[bold green][OK] Exported catalog preview to CSV: {csv_path}[/bold green]")
    else:
        success = sheets_service.sync_catalog_to_sheets(app_dicts)
        if success:
            console.print("[bold green][OK] Central Google Sheets catalog updated successfully![/bold green]")
        else:
            csv_path = sheets_service.export_to_csv_preview(app_dicts)
            console.print(f"[yellow]Google Sheets direct update skipped/unconfigured. Fallback exported to {csv_path}[/yellow]")
    db.close()

@app.command("import-ai-studio")
def import_ai_studio(file_path: str):
    """Import an AI Studio exported JSON file or Zip package into GitBridge."""
    if not os.path.exists(file_path):
        console.print(f"[bold red]File not found: {file_path}[/bold red]")
        return

    db = get_db()
    try:
        if file_path.endswith(".json"):
            parsed = AIStudioParser.parse_json_export(file_path)
        elif file_path.endswith(".zip"):
            parsed = AIStudioParser.parse_zip_export(file_path)
        else:
            console.print("[bold red]Unsupported file extension. Please provide a .json or .zip file from AI Studio.[/bold red]")
            return

        slug = parsed["slug"]
        existing = db.query(AppProfileModel).filter(AppProfileModel.slug == slug).first()

        if existing:
            existing.system_instructions = parsed.get("system_instructions") or existing.system_instructions
            if parsed.get("ai_studio_link"):
                existing.ai_studio_link = parsed.get("ai_studio_link")
            existing.tech_stack = list(dict.fromkeys(existing.tech_stack + parsed.get("tech_stack", [])))
            console.print(f"[bold green][OK] Updated existing app profile '{slug}' from AI Studio export.[/bold green]")
        else:
            app_obj = AppProfileModel(
                slug=slug,
                name=parsed["name"],
                description=parsed["description"],
                status=AppStatus(parsed["status"]),
                ai_studio_link=parsed.get("ai_studio_link"),
                system_instructions=parsed.get("system_instructions"),
                version=parsed["version"]
            )
            app_obj.tech_stack = parsed.get("tech_stack", [])
            app_obj.tags = parsed.get("tags", [])
            db.add(app_obj)
            console.print(f"[bold green][OK] Registered new app '{parsed['name']}' ({slug}) from AI Studio export![/bold green]")

        db.commit()
    except Exception as e:
        console.print(f"[bold red]Failed to import AI Studio file: {e}[/bold red]")
    finally:
        db.close()

@app.command("doc-generate")
def doc_generate(slug: str):
    """Generate a standard instruction manual markdown template for an app."""
    db = get_db()
    app_obj = db.query(AppProfileModel).filter(AppProfileModel.slug == slug).first()
    if not app_obj:
        console.print(f"[bold red]App '{slug}' not found.[/bold red]")
        db.close()
        return

    doc_dir = "./docs"
    os.makedirs(doc_dir, exist_ok=True)
    file_path = os.path.join(doc_dir, f"{slug}_USER_MANUAL.md")

    template = f"""# {app_obj.name} - User & Instruction Manual

> **App Status**: `{app_obj.status.value if hasattr(app_obj.status, 'value') else str(app_obj.status)}`  
> **Version**: `{app_obj.version}`  
> **GitHub**: {app_obj.github_url or 'N/A'}  
> **Tech Stack**: {', '.join(app_obj.tech_stack)}

---

## 📌 1. Overview
{app_obj.description or 'Add full overview and user purpose here.'}

---

## 🤖 2. Core AI Prompt / System Instructions
```markdown
{app_obj.system_instructions or 'Add or paste core system instructions here.'}
```

---

## 🛠️ 3. Quick Start & Setup Instructions
1. **Prerequisites**: Ensure {', '.join(app_obj.tech_stack) if app_obj.tech_stack else 'dependencies'} are installed.
2. **Installation**:
   ```bash
   git clone {app_obj.github_url or 'https://github.com/yourusername/' + app_obj.slug}
   cd {app_obj.slug}
   ```
3. **Running the App**:
   Follow instructions in standard setup guide.

---

## 🖼️ 4. Media & Marketing Assets
Refer to GitBridge Media Asset Library for high-res screenshots, banners, and logos.
"""
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(template)

    # Register manual in DB if not exists
    manual = db.query(DocManualModel).filter(DocManualModel.app_id == slug, DocManualModel.file_path == file_path).first()
    if not manual:
        manual = DocManualModel(
            app_id=slug,
            title=f"{app_obj.name} User Manual",
            summary=f"Standard instruction manual for {app_obj.name}",
            content_markdown=template,
            file_path=file_path
        )
        db.add(manual)
        db.commit()

    console.print(f"[bold green][OK] User Manual template generated and saved to: {file_path}[/bold green]")
    db.close()

if __name__ == "__main__":
    app()
