import os
import requests
from datetime import datetime
from typing import Dict, Any, Optional, List
from gitbridge.services.github_service import GitHubService

class AppAnalyzerService:
    def __init__(self):
        self.gh_service = GitHubService()

    def determine_priority_tier(self, name: str, status: str, tech_stack: List[str], tags: List[str], open_issues_count: int) -> str:
        """Determine priority tier based on status, tech stack complexity, and commercial relevance."""
        name_lower = name.lower()
        tags_lower = [t.lower() for t in tags]
        
        if "tier 1" in tags_lower or "commercial" in tags_lower or "geppyo" in name_lower or "geppybook" in name_lower:
            return "Tier 1 (Immediate Commercial Driver)"
        elif status == "archived" or "concept" in tags_lower or "idea" in status or "blank" in name_lower:
            return "Tier 3 (Top-of-Funnel / Experimental)"
        else:
            return "Tier 2 (Core Infrastructure & Utility)"

    def generate_health_card(self, app_obj) -> str:
        """Generate standardized Markdown Health Card ([App-Name]-Health.md) per Section 5 of Design Document."""
        name = app_obj.name
        slug = app_obj.slug
        github_repo = app_obj.github_repo_name or ""
        github_url = app_obj.github_url or (f"https://github.com/{github_repo}" if github_repo else "N/A")
        tech_stack = app_obj.tech_stack or []
        tags = app_obj.tags or []
        status = app_obj.status.value if hasattr(app_obj.status, 'value') else str(app_obj.status)
        today_str = datetime.now().strftime("%Y-%m-%d")

        # Ingest deep metadata from GitHub if repository linked
        issues = []
        commits = []
        readme = None
        if github_repo:
            try:
                meta = self.gh_service.fetch_comprehensive_repo_metadata(github_repo)
                issues = meta.get("issues", [])
                commits = meta.get("commits", [])
                readme = meta.get("readme")
                if meta.get("tech_stack"):
                    tech_stack = list(dict.fromkeys(tech_stack + meta["tech_stack"]))
            except Exception as e:
                print(f"[AnalyzerService] Metadata fetch notice for {github_repo}: {e}")

        priority_tier = self.determine_priority_tier(name, status, tech_stack, tags, len(issues))

        # Format open issues
        if issues:
            issues_md = ""
            for iss in issues:
                kind = "PR" if iss.get("is_pr") else "Issue"
                issues_md += f"  - #{iss['number']} ({kind}): {iss['title']}\n"
        else:
            issues_md = "  - None reported (0 open issues / PRs)\n"

        # Active maintenance summary
        maintenance_str = ""
        if commits:
            last = commits[0]
            maintenance_str = f"Last commit `{last.get('sha')}` on {last.get('date')} by **{last.get('author')}**: _{last.get('message')}_"
        else:
            maintenance_str = "No recent commit history retrieved."

        # AI Recommendations
        ai_recommendation = self._generate_ai_recommendations(name, app_obj.description or "", tech_stack, priority_tier, issues, readme)

        tech_stack_str = ", ".join(tech_stack) if tech_stack else "Standard App Tech Stack"

        health_card = f"""# App Name: {name}
- **Repository:** {github_url}
- **Last Synced:** {today_str}
- **Priority Tier:** {priority_tier}
- **Tech Stack:** {tech_stack_str}
- **Active Maintenance:** {maintenance_str}
- **Open Issues / Bugs:**
{issues_md}
- **AI Recommendations:** 
{ai_recommendation}
"""
        return health_card

    def _generate_ai_recommendations(self, name: str, description: str, tech_stack: List[str], priority_tier: str, issues: List[Dict[str, Any]], readme: Optional[str]) -> str:
        """Call Gemini API for automated code review & strategic recommendations, or fall back to rule-based engine."""
        api_key = os.getenv("GEMINI_API_KEY")
        if api_key:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
                prompt = f"""You are an AI CTO evaluating an app catalog entry for Geppy's App Universe.
Provide a concise, 2-3 sentence strategic recommendation focused on code quality, issue resolution, and commercial readiness.

App Name: {name}
Description: {description}
Priority Tier: {priority_tier}
Tech Stack: {', '.join(tech_stack)}
Open Issues Count: {len(issues)}
Open Issue Titles: {[i.get('title') for i in issues[:5]]}
README Excerpt: {readme[:500] if readme else 'None'}
"""
                payload = {"contents": [{"parts": [{"text": prompt}]}]}
                res = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=12)
                if res.status_code == 200:
                    text = res.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                    return f"  - {text}"
            except Exception as e:
                print(f"[AnalyzerService] Gemini call fallback: {e}")

        # Rule-based fallback recommendation
        rec = f"Focus next sprint on clearing open issues ({len(issues)}) and enhancing documentation."
        if "Tier 1" in priority_tier:
            rec = f"Prioritize immediate commercial beta testing readiness and resolve any critical bug reports."
        elif "Tier 3" in priority_tier:
            rec = f"Maintain light surveillance; archive or bundle into core features if feature adoption remains low."
        
        return f"  - {rec}"

    def analyze_app(self, app_obj) -> str:
        """Perform feature analysis & architectural breakdown for an app profile."""
        return self.generate_health_card(app_obj)

    def _synthesize_local_app_context(self, app_obj, deep_info: Dict[str, Any]) -> Dict[str, str]:
        """Synthesize app purpose description and system prompt from local source code inspection."""
        import os
        import re
        sampled_contents = deep_info.get("sampled_contents", {})
        file_tree = deep_info.get("file_tree", [])
        detected_tech = deep_info.get("detected_tech", [])
        
        modules = []
        app_title = None

        # Check index.html for title
        if "index.html" in sampled_contents:
            m = re.search(r'<title>(.*?)</title>', sampled_contents["index.html"], re.IGNORECASE)
            if m:
                t_val = m.group(1).strip()
                if t_val and "vite" not in t_val.lower() and "react" not in t_val.lower():
                    app_title = t_val

        # Scan App.tsx / App.jsx / components for module names
        entry_content = sampled_contents.get("src/App.tsx") or sampled_contents.get("src/App.jsx") or ""
        if entry_content:
            comp_matches = re.findall(r'import\s+.*?\{\s*([^}]+)\s*\}\s+from\s+[\'"]\.\/components', entry_content)
            ignore_comps = {"Navbar", "Header", "Footer", "Sidebar", "Navigation", "NavTab", "Layout"}
            for cm in comp_matches:
                for item in cm.split(','):
                    c_name = item.strip().split(' as ')[0].strip()
                    if c_name and c_name[0].isupper() and "Type" not in c_name and "Modal" not in c_name and c_name not in ignore_comps:
                        clean_name = re.sub(r'(View|Manager|Component|Container|Page)$', '', c_name)
                        clean_name = re.sub(r'([a-z])([A-Z])', r'\1 \2', clean_name).strip()
                        if clean_name and clean_name not in modules and clean_name not in ignore_comps:
                            modules.append(clean_name)

        # If no components extracted from App.tsx, check file tree for component files
        if not modules:
            ignore_comps = {"Navbar", "Header", "Footer", "Sidebar", "Navigation", "NavTab", "Layout"}
            for f in file_tree:
                if "components/" in f or "views/" in f or "pages/" in f:
                    base = os.path.basename(f).rsplit('.', 1)[0]
                    if base and base[0].isupper() and base not in ignore_comps:
                        clean_name = re.sub(r'(View|Manager|Component|Container|Page)$', '', base)
                        clean_name = re.sub(r'([a-z])([A-Z])', r'\1 \2', clean_name).strip()
                        if clean_name and clean_name not in modules and clean_name not in ignore_comps:
                            modules.append(clean_name)

        tech_str = ", ".join(detected_tech) if detected_tech else "React & TypeScript"
        display_name = app_title or app_obj.name

        if modules:
            capabilities_bullets = []
            for mod in modules[:10]:
                m_lower = mod.lower()
                if "account" in m_lower:
                    capabilities_bullets.append("- **Accounts & Balances Manager**: Track bank accounts, starting balances, and live net worth.")
                elif "calendar" in m_lower:
                    capabilities_bullets.append("- **Cashflow Calendar**: Interactive daily transaction calendar projecting future cash balances.")
                elif "debt" in m_lower or "payoff" in m_lower:
                    capabilities_bullets.append("- **Debt Payoff Planner**: Credit card and debt payoff strategies with interest acceleration modeling.")
                elif "consolidation" in m_lower:
                    capabilities_bullets.append("- **Debt Consolidation Calculator**: Analyze interest rate consolidation options and loan savings.")
                elif "budget" in m_lower:
                    capabilities_bullets.append("- **Budget Manager & Expense Tracking**: Organize recurring bills, income sources, and daily budgets.")
                elif "analytics" in m_lower:
                    capabilities_bullets.append("- **Financial Analytics Dashboard**: Visual trends, expense category breakdowns, and liquidity projections.")
                elif "ai" in m_lower or "assistant" in m_lower:
                    capabilities_bullets.append("- **AI Copilot & Budgeting Assistant**: Intelligent financial advice and automated transaction categorization.")
                elif "filing" in m_lower or "cabinet" in m_lower or "doc" in m_lower:
                    capabilities_bullets.append("- **Document Vault & Filing Cabinet**: Store and organize receipts, statements, and financial docs.")
                elif "mobile" in m_lower:
                    capabilities_bullets.append("- **Mobile Companion View**: Responsive mobile layout and local companion device sync.")
                elif "home" in m_lower:
                    capabilities_bullets.append("- **Overview Hub**: Executive dashboard summarizing overall financial health and active profiles.")
                else:
                    capabilities_bullets.append(f"- **{mod}**: Interactive feature module providing specialized user workflows.")

            caps_str = "\n".join(capabilities_bullets)
            desc = f"**{display_name}** is a comprehensive software platform built with {tech_str}.\n\n### App Purpose & Capabilities\n{caps_str}\n\n### Technical Overview\nFeatures client-side reactive state management, responsive UI design, multi-profile support, and real-time calculation engines."
        else:
            desc = f"**{display_name}** is a software application module built with {tech_str} in Geppy's App Universe.\n\n### Core Capabilities\n- Provides localized workflows, user interface components, and application data management."

        sys_prompt = f"You are the AI assistant for {display_name}. Help users interact with its capabilities including {', '.join(modules) if modules else 'application workflows'} and technical stack ({tech_str})."

        return {
            "description": desc,
            "system_instructions": sys_prompt
        }

    def analyze_and_autofill_app(self, app_obj, db) -> Dict[str, Any]:
        """Analyze local directory structure, code entrypoints, and GitHub repo to produce a deeply accurate purpose description, system prompt, and architectural breakdown."""
        import json
        from gitbridge.services.workspace_service import WorkspaceService
        
        # Filter boilerplate description if present
        if WorkspaceService.is_boilerplate_description(app_obj.description):
            app_obj.description = None

        # 1. Perform deep file structure & content inspection
        deep_info = {}
        if app_obj.local_path and os.path.exists(app_obj.local_path):
            deep_info = WorkspaceService.inspect_deep_file_structure(app_obj.local_path)

        # Merge detected tech stack
        detected_tech = deep_info.get("detected_tech", [])
        if detected_tech:
            combined_tech = list(dict.fromkeys((app_obj.tech_stack or []) + detected_tech))
            app_obj.tech_stack = combined_tech

        # 2. Ingest GitHub metadata if repository linked
        github_readme = None
        if app_obj.github_repo_name:
            try:
                meta = self.gh_service.fetch_comprehensive_repo_metadata(app_obj.github_repo_name)
                github_readme = meta.get("readme")
                if meta.get("tech_stack"):
                    combined_tech = list(dict.fromkeys((app_obj.tech_stack or []) + meta["tech_stack"]))
                    app_obj.tech_stack = combined_tech
            except Exception:
                pass

        # 3. Format file tree & code content samples for Gemini API
        file_tree_list = deep_info.get("file_tree", [])
        sampled_contents = deep_info.get("sampled_contents", {})

        sampled_text_block = ""
        for filepath, snippet in sampled_contents.items():
            sampled_text_block += f"\n--- File: {filepath} ---\n{snippet[:1200]}\n"

        file_tree_block = "\n".join(file_tree_list[:40]) if file_tree_list else "Directory tree not available."

        # Call Gemini API if available to produce deep accurate analysis
        api_key = os.getenv("GEMINI_API_KEY")
        if api_key:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
                prompt = f"""You are an expert AI Software Architect analyzing a software repository for Geppy's App Universe.
Perform a deep technical analysis of the file tree, code entrypoints, and configuration files provided below.

Generate a structured JSON response with these exact keys:
1. "description": A clear, highly detailed, 2-4 sentence explanation of the app's exact purpose, capabilities, user workflow, and technical role based on the code files.
2. "system_instructions": A comprehensive system prompt defining the AI persona, purpose, and operational instructions for this application.
3. "architectural_summary": A detailed Markdown architectural breakdown detailing the file structure, main code entrypoints, framework features, and data/API models.

App Name: {app_obj.name}
Directory Tree (Sample):
{file_tree_block}

Code Entrypoint & Config Content Samples:
{sampled_text_block}

GitHub README: {github_readme[:1000] if github_readme else 'None'}
"""
                payload = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"responseMimeType": "application/json"}}
                res = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=15)
                if res.status_code == 200:
                    resp_json = json.loads(res.json()["candidates"][0]["content"]["parts"][0]["text"])
                    if resp_json.get("description") and not WorkspaceService.is_boilerplate_description(resp_json["description"]):
                        app_obj.description = resp_json["description"].strip()
                    if resp_json.get("system_instructions"):
                        app_obj.system_instructions = resp_json["system_instructions"].strip()
                    if resp_json.get("architectural_summary"):
                        app_obj.feature_breakdown = resp_json["architectural_summary"].strip()
            except Exception as e:
                print(f"[AnalyzerService] Deep auto-fill Gemini call notice: {e}")

        # If description or system_instructions are missing or boilerplate, synthesize locally from source files
        if not app_obj.description or WorkspaceService.is_boilerplate_description(app_obj.description) or not app_obj.system_instructions:
            synth = self._synthesize_local_app_context(app_obj, deep_info)
            if not app_obj.description or WorkspaceService.is_boilerplate_description(app_obj.description):
                app_obj.description = synth["description"]
            if not app_obj.system_instructions:
                app_obj.system_instructions = synth["system_instructions"]

        # If breakdown wasn't set by Gemini, generate standard health card
        if not app_obj.feature_breakdown or len(app_obj.feature_breakdown) < 50:
            breakdown = self.generate_health_card(app_obj)
            app_obj.feature_breakdown = breakdown

        app_obj.health_report_md = app_obj.feature_breakdown

        db.commit()
        db.refresh(app_obj)

        return {
            "slug": app_obj.slug,
            "name": app_obj.name,
            "description": app_obj.description,
            "system_instructions": app_obj.system_instructions,
            "tech_stack": app_obj.tech_stack,
            "feature_breakdown": app_obj.feature_breakdown
        }

