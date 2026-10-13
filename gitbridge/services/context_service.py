import os
from datetime import datetime
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from gitbridge.db.models import AppProfileModel, MediaAssetModel, DocManualModel
from gitbridge.services.workspace_service import WorkspaceService
from gitbridge.services.launcher_service import ACTIVE_SERVERS

class GeminiContextService:

    @staticmethod
    def generate_universe_markdown(db: Session) -> str:
        """Generate comprehensive, structured Markdown context dump of Geppy's App Universe for Gemini AI."""
        apps = db.query(AppProfileModel).all()
        workspace_dir = WorkspaceService.get_workspace_dir()
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        status_counts = {}
        priority_tier_counts = {}
        all_tech = set()

        for a in apps:
            st = a.status.value if hasattr(a.status, 'value') else str(a.status)
            status_counts[st] = status_counts.get(st, 0) + 1

            tier = a.priority_tier or "Tier 2 (Core Infrastructure)"
            priority_tier_counts[tier] = priority_tier_counts.get(tier, 0) + 1

            for t in (a.tech_stack or []):
                all_tech.add(t)

        doc = f"""# 🌌 Geppy's App Universe - Master Catalog & Context Dump

> **Generated At**: {now_str}  
> **Workspace Directory**: `{workspace_dir}`  
> **Total Registered Apps**: {len(apps)}  

---

## 📊 1. Universe Overview & Executive Summary

### Status Distribution
"""
        for st, count in status_counts.items():
            doc += f"- **{st.replace('_', ' ').title()}**: {count} app(s)\n"

        doc += "\n### Priority Tier Breakdown\n"
        for tier, count in priority_tier_counts.items():
            doc += f"- **{tier}**: {count} app(s)\n"

        doc += f"\n### Global Tech Stack Inventory\n`{', '.join(sorted(list(all_tech))) if all_tech else 'Standard Web & Python'}`\n\n---\n\n"
        doc += "## 📱 2. Detailed Application Profiles\n\n"

        for idx, a in enumerate(apps, 1):
            sync_info = WorkspaceService.get_app_sync_status(a)
            is_live = a.slug in ACTIVE_SERVERS
            live_url = ACTIVE_SERVERS[a.slug]["url"] if is_live else a.live_url

            doc += f"### {idx}. {a.name} (`{a.slug}`)\n"
            doc += f"- **Status**: `{a.status.value if hasattr(a.status, 'value') else str(a.status)}`\n"
            doc += f"- **Priority Tier**: {a.priority_tier or 'Tier 2 (Core Infrastructure)'}\n"
            doc += f"- **Sync State**: `{sync_info['sync_label']}`\n"
            doc += f"- **Local Folder**: `{sync_info.get('local_path') or 'Not on PC'}`\n"
            doc += f"- **GitHub Repository**: {a.github_url or 'Unlinked'}\n"
            if is_live and live_url:
                doc += f"- **Live Server**: 🟢 [ACTIVE] `{live_url}`\n"
            doc += f"- **Version**: `{a.version or '0.1.0'}`\n"
            doc += f"- **Tech Stack**: {', '.join(a.tech_stack or []) if a.tech_stack else 'N/A'}\n"
            doc += f"- **Tags**: {', '.join(a.tags or []) if a.tags else 'None'}\n\n"

            doc += "#### Purpose & Description\n"
            doc += f"> {a.description or 'No description provided.'}\n\n"

            if a.system_instructions:
                doc += "#### System Prompt / Core Instructions\n"
                doc += f"```markdown\n{a.system_instructions}\n```\n\n"

            if a.health_report_md or a.feature_breakdown:
                breakdown = a.feature_breakdown or a.health_report_md
                doc += "#### Architectural Summary & Health Analysis\n"
                doc += f"```markdown\n{breakdown}\n```\n\n"

            # Deep file structure snippet if folder exists
            if sync_info.get('local_path') and os.path.exists(sync_info['local_path']):
                deep_info = WorkspaceService.inspect_deep_file_structure(sync_info['local_path'])
                file_tree = deep_info.get("file_tree", [])
                if file_tree:
                    doc += f"#### Directory Tree Preview ({len(file_tree)} files sampled)\n"
                    doc += "```text\n" + "\n".join(file_tree[:25]) + "\n```\n\n"

            # Logged Assets
            assets = a.assets or []
            if assets:
                doc += "#### Media & Marketing Assets\n"
                for asset in assets:
                    asset_type = asset.asset_type.value if hasattr(asset.asset_type, 'value') else str(asset.asset_type)
                    doc += f"- [{asset_type.upper()}] **{asset.title}**: `{asset.file_path}` ({asset.url or 'local'})\n"
                doc += "\n"

            # Instruction Manuals
            manuals = a.manuals or []
            if manuals:
                doc += "#### Documentation & User Manuals\n"
                for man in manuals:
                    doc += f"- **{man.title}**: `{man.file_path or 'Inline Markdown'}` - {man.summary or 'No summary'}\n"
                doc += "\n"

            doc += "---\n\n"

        return doc

    @staticmethod
    def generate_app_markdown(app_obj, db: Session) -> str:
        """Generate focused Markdown context dump for a single application profile."""
        sync_info = WorkspaceService.get_app_sync_status(app_obj)
        is_live = app_obj.slug in ACTIVE_SERVERS
        live_url = ACTIVE_SERVERS[app_obj.slug]["url"] if is_live else app_obj.live_url
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        doc = f"# Application Context: {app_obj.name} (`{app_obj.slug}`)\n\n"
        doc += f"> **Generated At**: {now_str}\n"
        doc += f"- **Status**: `{app_obj.status.value if hasattr(app_obj.status, 'value') else str(app_obj.status)}`  \n"
        doc += f"- **Priority Tier**: {app_obj.priority_tier or 'Tier 2'}  \n"
        doc += f"- **Sync State**: {sync_info['sync_label']}  \n"
        doc += f"- **Local Directory**: `{sync_info.get('local_path') or 'N/A'}`  \n"
        doc += f"- **GitHub URL**: {app_obj.github_url or 'Unlinked'}  \n"
        if is_live:
            doc += f"- **Live Localhost**: `{live_url}` (Active)  \n"
        doc += f"- **Tech Stack**: {', '.join(app_obj.tech_stack or [])}  \n"
        doc += f"- **Version**: `{app_obj.version or '0.1.0'}`  \n\n"

        doc += "## Description & Purpose\n"
        doc += f"{app_obj.description or 'No description provided.'}\n\n"

        if app_obj.system_instructions:
            doc += "## Core System Prompt / Instructions\n"
            doc += f"```markdown\n{app_obj.system_instructions}\n```\n\n"

        if app_obj.feature_breakdown or app_obj.health_report_md:
            doc += "## Architectural Breakdown & Health Card\n"
            doc += f"```markdown\n{app_obj.feature_breakdown or app_obj.health_report_md}\n```\n\n"

        if sync_info.get('local_path') and os.path.exists(sync_info['local_path']):
            deep_info = WorkspaceService.inspect_deep_file_structure(sync_info['local_path'])
            file_tree = deep_info.get("file_tree", [])
            sampled_contents = deep_info.get("sampled_contents", {})

            if file_tree:
                doc += "## File Tree Structure\n```text\n" + "\n".join(file_tree) + "\n```\n\n"

            if sampled_contents:
                doc += "## Key Code & Config Snippets\n"
                for fname, snippet in sampled_contents.items():
                    doc += f"### File: `{fname}`\n```\n{snippet}\n```\n\n"

        return doc

    @staticmethod
    def export_context_file(db: Session, filepath: Optional[str] = None) -> Dict[str, Any]:
        """Export master universe Markdown context file into local workspace directory for Gemini."""
        workspace_dir = WorkspaceService.get_workspace_dir()
        if not filepath:
            filepath = os.path.join(workspace_dir, "GEMINI_UNIVERSE_CONTEXT.md")

        content_md = GeminiContextService.generate_universe_markdown(db)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content_md)

        return {
            "success": True,
            "filepath": os.path.abspath(filepath),
            "file_size_bytes": os.path.getsize(filepath),
            "generated_at": datetime.now().isoformat()
        }
