import os
import requests
from typing import Dict, Any, Optional
from gitbridge.services.github_service import GitHubService

class AppAnalyzerService:
    def __init__(self):
        self.gh_service = GitHubService()

    def analyze_app(self, app_obj) -> str:
        """Perform feature analysis & architectural breakdown for an app profile."""
        name = app_obj.name
        slug = app_obj.slug
        status = app_obj.status.value if hasattr(app_obj.status, 'value') else str(app_obj.status)
        description = app_obj.description or "No description provided."
        tech_stack = app_obj.tech_stack or []
        system_instructions = app_obj.system_instructions or ""

        # Attempt to fetch README from GitHub if repo is linked
        readme_content = None
        if app_obj.github_repo_name:
            try:
                readme_content = self.gh_service.fetch_repo_readme(app_obj.github_repo_name)
            except Exception:
                readme_content = None

        gemini_api_key = os.getenv("GEMINI_API_KEY")

        if gemini_api_key:
            try:
                analysis = self._analyze_with_gemini(name, description, tech_stack, system_instructions, readme_content, gemini_api_key)
                if analysis:
                    return analysis
            except Exception as e:
                print(f"[AnalyzerService] Gemini API call fallback: {e}")

        # Rule-based structured analyzer
        return self._generate_structured_breakdown(name, slug, status, description, tech_stack, system_instructions, readme_content)

    def _analyze_with_gemini(self, name: str, description: str, tech_stack: list, system_instructions: str, readme: Optional[str], api_key: str) -> Optional[str]:
        """Query Gemini API directly to produce a deep feature breakdown."""
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
        prompt = f"""You are an expert AI software architect analyzing an application in Geppy's App Universe.
Provide a comprehensive, clean, Markdown-formatted Feature Breakdown and Architectural Analysis for the app below.

App Name: {name}
Description: {description}
Tech Stack: {', '.join(tech_stack)}
System Prompts / Instructions: {system_instructions[:500]}
README Excerpt: {readme[:1500] if readme else 'None available'}

Format your response cleanly with these exact sections:
### 📌 1. Core Purpose & Value Proposition
### ⚡ 2. Key Feature Breakdown
### 🛠️ 3. Technical Architecture & Tech Stack
### 🤖 4. Gemini / AI Integration Points
### 💡 5. Next Steps & Recommended Enhancements
"""
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        res = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=15)
        if res.status_code == 200:
            data = res.json()
            try:
                return data["candidates"][0]["content"]["parts"][0]["text"]
            except Exception:
                return None
        return None

    def _generate_structured_breakdown(self, name: str, slug: str, status: str, description: str, tech_stack: list, system_instructions: str, readme: Optional[str]) -> str:
        """Generate structured feature breakdown report."""
        stack_str = ", ".join(tech_stack) if tech_stack else "Standard Web / AI Tech Stack"
        
        features = []
        if "React" in tech_stack or "TypeScript" in tech_stack or "JavaScript" in tech_stack:
            features.append("Interactive User Interface with responsive component architecture")
        if "FastAPI" in tech_stack or "Python" in tech_stack:
            features.append("RESTful API Backend with automated OpenAPI endpoints")
        if "AI Studio" in tech_stack or "Gemini API" in tech_stack or system_instructions:
            features.append("Gemini Model Integration for automated intelligence & prompts")
        if not features:
            features = [
                "Modular core application workflow",
                "Structured state & dataset management",
                "Integration interface for Geppy's App Universe"
            ]

        breakdown = f"""# 🔍 Feature Breakdown: {name}

> **Status**: `{status.upper()}` | **Slug**: `{slug}` | **Tech Stack**: `{stack_str}`

---

### 📌 1. Core Purpose & Value Proposition
{description}

---

### ⚡ 2. Primary Key Features
"""
        for feat in features:
            breakdown += f"- **{feat}**\n"

        breakdown += f"""
---

### 🛠️ 3. Technical Architecture
- **Language / Frameworks**: {stack_str}
- **Database / Storage**: Local state & GitHub repository sync
- **Documentation**: Markdown README & GitBridge Instruction Manuals

---

### 🤖 4. Gemini & AI Integration Points
"""
        if system_instructions:
            breakdown += f"```markdown\n{system_instructions}\n```\n"
        else:
            breakdown += "No specific AI system prompt recorded yet. Connect to AI Studio to import system instructions.\n"

        breakdown += f"""
---

### 💡 5. Recommended Enhancements & Next Steps
1. **Automated Testing**: Add automated pytest/jest unit testing suite.
2. **Media Assets**: Generate high-res logo and UI promo banners in GitBridge Media Store.
3. **Google Sheets Sync**: Verify bidirectional sync to central App Universe Google Sheet.
"""
        return breakdown
