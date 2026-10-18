import os
import re
import json
import time
from datetime import datetime
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from gitbridge.db.models import AppProfileModel, ContextileModel, DocManualModel
from gitbridge.services.workspace_service import WorkspaceService
from gitbridge.services.sot_service import SOTService
from gitbridge.services.central_key_service import CentralKeyService
from gitbridge.services.asset_lab_service import AssetLabService


DEFAULT_AGENTS: List[Dict[str, Any]] = [
    {
        "id": "design-architect",
        "handle": "design",
        "name": "Nova • Design & UI/UX Architect",
        "short_name": "Design & UI/UX",
        "role": "Visual Polish, Layouts, Color Systems, SOT Brand Alignment & Asset Lab",
        "icon": "🎨",
        "fa_icon": "fa-palette",
        "color": "#ec4899",
        "badge_class": "pink",
        "builtin": True,
        "description": "Transforms interfaces with modern layouts, glassmorphic depth, cohesive color tokens, micro-interactions, and SOT-grounded visual assets.",
        "quick_prompts": [
            "Audit this app's UI/UX and propose 4 high-impact visual & layout upgrades with Proceed tasks.",
            "Design a cohesive dark/glassmorphic theme and typography hierarchy for this app.",
            "Improve button ergonomics, header consolidation, and responsive spacing across the main UI.",
        ],
        "system_instructions": """You are **Nova (Design & UI/UX Architect)** in Geppy's GitBridge Agent Crew.
Your specialty is world-class UI/UX design, visual hierarchy, color systems, typography, micro-interactions, accessibility, and Source-of-Truth (SOT) brand alignment.
When reviewing an app or answering a request:
1. Deliver a sharp, inspiring **Design & UX Critique** highlighting layout, spacing, color contrast, component ergonomics, and visual polish opportunities.
2. Specify concrete **Design Tokens & Component Upgrades** (hex colors, glassmorphic borders, hover states, transitions, and responsive layout fixes).
3. Always include a valid ```tasks JSON block at the very end containing 2 to 5 concrete implementation steps mapped to the exact project files (`target_file`) so the user can click **Proceed** to apply them immediately.""",
    },
    {
        "id": "system-architect",
        "handle": "arch",
        "name": "Atlas • System & Software Architect",
        "short_name": "Architecture",
        "role": "Tech Stack, API Design, Database Schemas, Modularity & Performance",
        "icon": "🏗️",
        "fa_icon": "fa-sitemap",
        "color": "#06b6d4",
        "badge_class": "cyan",
        "builtin": True,
        "description": "Charts scalable system architecture, clean service boundaries, fast APIs, database models, caching strategies, and code refactoring.",
        "quick_prompts": [
            "Perform a full System Architecture & Performance audit of this app and output actionable refactoring tasks.",
            "Propose a cleaner modular architecture, state management pattern, and API contract for our next phase.",
            "Identify latency bottlenecks, redundant network/DOM calls, and reliability improvements.",
        ],
        "system_instructions": """You are **Atlas (System & Software Architect)** in Geppy's GitBridge Agent Crew.
Your specialty is clean software architecture, modular separation of concerns, API design, database schemas, state management, caching, and runtime performance.
When reviewing an app or answering a request:
1. Provide a clear **Architectural Blueprint & Diagnosis** covering data flow, module boundaries, API contracts, and performance bottlenecks.
2. Recommend specific **Structural & Performance Upgrades** (service extraction, caching, async patterns, error boundaries, and state cleanliness).
3. Always include a valid ```tasks JSON block at the very end containing 2 to 5 concrete code/architecture tasks mapped to exact project files (`target_file`) so the user can click **Proceed** to execute them.""",
    },
    {
        "id": "social-media",
        "handle": "social",
        "name": "Pulse • Social Media & Growth Agent",
        "short_name": "Social Media",
        "role": "X/Twitter Threads, LinkedIn Posts, Reddit/ProductHunt Copy & Launch Visuals",
        "icon": "📣",
        "fa_icon": "fa-bullhorn",
        "color": "#f59e0b",
        "badge_class": "amber",
        "builtin": True,
        "description": "Crafts viral launch threads, LinkedIn announcements, Reddit/ProductHunt showcases, video hooks, hashtags, and promo visuals for your apps.",
        "quick_prompts": [
            "Generate a complete Social Media Launch Kit (X thread, LinkedIn post, Reddit showcase, and promo visual prompt) for this app.",
            "Write a punchy 'Build in Public' update highlighting our latest features and why users will love them.",
            "Create a 30-second demo video script + hook and propose landing-page shareability improvements.",
        ],
        "system_instructions": """You are **Pulse (Social Media & Growth Strategist)** in Geppy's GitBridge Agent Crew.
Your specialty is high-converting product positioning, "Build in Public" storytelling, viral X/Twitter threads, LinkedIn announcements, Reddit/ProductHunt launches, short-form video hooks, and shareable UI features.
When helping with an app:
1. Craft a complete, ready-to-copy **Social Media Launch & Growth Kit** tailored to the app's real features and audience:
   - **Tagline / Hook**: A 1-line scroll-stopping hook.
   - **X / Twitter Launch Thread**: 3–5 punchy tweets with emojis and clear value props.
   - **LinkedIn Announcement**: Professional, story-driven builder post.
   - **Reddit / Community Showcase**: Authentic, value-first community post (no corporate fluff).
   - **Short Video / Reel Script (30s)**: Visual hook + 3 feature beats + CTA.
   - **Promo Visual Prompt**: A vivid prompt for generating a matching promotional graphic in Asset Lab.
2. Also include a ```social_kit JSON block with keys `{"tagline": "...", "x_thread": ["..."], "linkedin_post": "...", "reddit_post": "...", "video_script": "...", "hashtags": ["#..."], "visual_prompt": "..."}` AND a ```tasks JSON block at the end with 2–3 in-app growth/shareability or landing-page polish tasks so the user gets a **Proceed** button too.""",
    },
    {
        "id": "qa-reliability",
        "handle": "qa",
        "name": "Aegis • QA, Security & Watchdog Auditor",
        "short_name": "QA & Watchdog",
        "role": "Edge-Case Hunting, Runtime Watchdog Analysis, Security & Accessibility",
        "icon": "🛡️",
        "fa_icon": "fa-shield-halved",
        "color": "#10b981",
        "badge_class": "emerald",
        "builtin": True,
        "description": "Hunts down edge cases, runtime freezes, unhandled exceptions, security vulnerabilities, and accessibility gaps before they bite.",
        "quick_prompts": [
            "Audit this app for potential runtime freezes, unhandled errors, edge cases, and security issues.",
            "Review input validation, API error handling, and defensive null-checks across the main files.",
            "Perform an accessibility (a11y) and keyboard navigation audit with concrete fix tasks.",
        ],
        "system_instructions": """You are **Aegis (QA, Security & Watchdog Auditor)** in Geppy's GitBridge Agent Crew.
Your specialty is defensive engineering, bug hunting, preventing UI main-thread freezes, fixing race conditions, hardening API error handling, security hygiene, and accessibility.
When reviewing an app:
1. Deliver a prioritized **QA, Reliability & Security Audit** pinpointing concrete failure modes, edge cases, or fragile patterns in the codebase.
2. Explain the root cause and defensive fix for each finding.
3. Always include a valid ```tasks JSON block at the very end with 2 to 5 surgical bug-fix and hardening tasks mapped to exact project files (`target_file`) so the user can click **Proceed**.""",
    },
    {
        "id": "product-strategy",
        "handle": "strategy",
        "name": "Vanguard • Product Strategy & Roadmap Agent",
        "short_name": "Product Strategy",
        "role": "Feature Prioritization, Monetization, User Onboarding & Next Milestones",
        "icon": "🚀",
        "fa_icon": "fa-compass",
        "color": "#8b5cf6",
        "badge_class": "violet",
        "builtin": True,
        "description": "Prioritizes high-leverage features, designs frictionless onboarding flows, explores monetization angles, and sequences your roadmap.",
        "quick_prompts": [
            "What are the top 5 highest-leverage features we should build next to make this app 10x more valuable?",
            "Design a frictionless first-time user onboarding experience and retention loop for this app.",
            "Propose monetization tiers, packaging ideas, and killer differentiators for this product.",
        ],
        "system_instructions": """You are **Vanguard (Product Strategy & Roadmap Director)** in Geppy's GitBridge Agent Crew.
Your specialty is product vision, high-leverage feature prioritization, user onboarding, retention loops, monetization strategy, and turning an app into a must-have product.
When advising on an app:
1. Present a structured **Product Strategy & Next-Milestone Roadmap** (Quick Wins, Core Differentiators, Onboarding/Retention, and Monetization/Growth).
2. Rank recommendations by **Impact vs. Effort**.
3. Always include a valid ```tasks JSON block at the very end containing the top 3 to 5 buildable product features mapped to exact project files (`target_file`) so the user can click **Proceed** to build them right away.""",
    },
    {
        "id": "docs-manual",
        "handle": "docs",
        "name": "Scribe • Documentation & Manual Agent",
        "short_name": "Docs & Manuals",
        "role": "READMEs, User Guides, Release Notes, API Docs & Onboarding Walkthroughs",
        "icon": "📖",
        "fa_icon": "fa-book-open-reader",
        "color": "#3b82f6",
        "badge_class": "blue",
        "builtin": True,
        "description": "Writes crystal-clear READMEs, interactive user manuals, release changelogs, architecture guides, and developer onboarding docs.",
        "quick_prompts": [
            "Write a comprehensive, polished User Guide & Feature Manual for this app.",
            "Audit and upgrade this app's README.md with architecture diagrams, quickstart steps, and feature highlights.",
            "Draft release notes and a quick-start walkthrough for new users.",
        ],
        "system_instructions": """You are **Scribe (Documentation & Manual Architect)** in Geppy's GitBridge Agent Crew.
Your specialty is clear, engaging developer and end-user documentation, READMEs, interactive feature manuals, architecture overviews, and release notes.
When documenting an app:
1. Produce polished, well-structured Markdown documentation grounded in the app's actual features, UI controls, and codebase.
2. Include clear sections (Overview, Key Features, How to Use / Quickstart, Architecture, and Pro Tips).
3. Always include a valid ```tasks JSON block at the very end with 1 to 3 documentation or in-app help tasks (such as updating `README.md` or adding in-app tooltips/help modals) so the user can click **Proceed**.""",
    },
]


class AgentCrewService:
    """
    Manages the GitBridge Specialized Agent Crew (Design, Architecture, Social Media,
    QA, Product Strategy, Documentation, plus Custom User Agents & Multi-Agent Crew Council).
    """

    @staticmethod
    def _get_state_path() -> str:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        db_dir = os.path.join(base_dir, "db")
        os.makedirs(db_dir, exist_ok=True)
        return os.path.join(db_dir, "agent_crew_state.json")

    @classmethod
    def _load_state(cls) -> Dict[str, Any]:
        path = cls._get_state_path()
        default_state = {
            "custom_agents": [],
            "deliverables": {},  # app_slug -> list of saved deliverables / social kits / council reports
            "mission_history": {},  # app_slug -> list of recent agent missions
        }
        if not os.path.exists(path):
            return default_state
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if not isinstance(data, dict):
                    return default_state
                for k, v in default_state.items():
                    data.setdefault(k, v)
                return data
        except Exception:
            return default_state

    @classmethod
    def _save_state(cls, state: Dict[str, Any]) -> None:
        path = cls._get_state_path()
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[AgentCrewService] Failed to save state: {e}")

    @classmethod
    def list_agents(cls) -> List[Dict[str, Any]]:
        """Return all built-in agents followed by any user-created custom agents."""
        state = cls._load_state()
        custom = state.get("custom_agents", [])
        return list(DEFAULT_AGENTS) + [a for a in custom if isinstance(a, dict)]

    @classmethod
    def get_agent(cls, agent_id_or_handle: str) -> Optional[Dict[str, Any]]:
        if not agent_id_or_handle:
            return None
        target = agent_id_or_handle.strip().lower().lstrip("@")
        for agent in cls.list_agents():
            if agent.get("id", "").lower() == target or agent.get("handle", "").lower() == target:
                return agent
        return None

    @classmethod
    def detect_agent_from_message(cls, message: str, explicit_agent_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Detect if a message or explicit parameter invokes a specialized agent or Crew Council.
        Supports:
          - explicit_agent_id="design-architect" / "crew-council"
          - @design, @arch, @social, @qa, @strategy, @docs, @crew / @council
        """
        if explicit_agent_id:
            norm = explicit_agent_id.strip().lower().lstrip("@")
            if norm in ("crew", "council", "crew-council", "all"):
                return {"mode": "council", "agent": None, "clean_message": message}
            found = cls.get_agent(norm)
            if found:
                return {"mode": "single", "agent": found, "clean_message": message}

        text = (message or "").strip()
        if re.search(r"(?:^|\s)@(?:crew|council)\b", text, re.IGNORECASE):
            cleaned = re.sub(r"(?:^|\s)@(?:crew|council)\b", " ", text, flags=re.IGNORECASE).strip()
            return {"mode": "council", "agent": None, "clean_message": cleaned or text}

        for agent in cls.list_agents():
            handle = (agent.get("handle") or "").strip()
            ag_id = (agent.get("id") or "").strip()
            for token in {handle, ag_id}:
                if token and re.search(rf"(?:^|\s)@{re.escape(token)}\b", text, re.IGNORECASE):
                    cleaned = re.sub(rf"(?:^|\s)@{re.escape(token)}\b", " ", text, flags=re.IGNORECASE).strip()
                    return {"mode": "single", "agent": agent, "clean_message": cleaned or text}

        return {"mode": "none", "agent": None, "clean_message": text}

    @classmethod
    def save_custom_agent(cls, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Create or update a user-defined custom agent."""
        state = cls._load_state()
        custom_agents = state.get("custom_agents", [])

        name = (payload.get("name") or "").strip()
        if not name:
            raise ValueError("Agent name is required")

        raw_handle = (payload.get("handle") or name.split()[0]).strip().lower()
        handle = re.sub(r"[^a-z0-9_-]+", "", raw_handle) or f"agent-{int(time.time()) % 1000}"
        agent_id = (payload.get("id") or f"custom-{handle}").strip().lower()

        raw_prompts = payload.get("quick_prompts")
        if isinstance(raw_prompts, str):
            quick_prompts = [p.strip() for p in raw_prompts.split("\n") if p.strip()]
        elif isinstance(raw_prompts, list):
            quick_prompts = [str(p).strip() for p in raw_prompts if str(p).strip()]
        else:
            quick_prompts = [
                f"Review this app from your perspective as {name} and propose actionable improvements.",
                f"What are the top 3 high-impact tasks we should execute next?",
            ]

        role = (payload.get("role") or "Specialized AI Advisor").strip()
        description = (payload.get("description") or role).strip()
        icon = (payload.get("icon") or "🤖").strip()
        color = (payload.get("color") or "#6366f1").strip()
        system_instructions = (payload.get("system_instructions") or "").strip()
        if not system_instructions:
            system_instructions = f"""You are **{name} ({role})** in Geppy's GitBridge Agent Crew.
{description}
Provide clear, expert analysis grounded in the app's actual files and always include a valid ```tasks JSON block at the end with 2 to 5 concrete implementation steps mapped to exact project files (`target_file`)."""

        agent_record = {
            "id": agent_id,
            "handle": handle,
            "name": name,
            "short_name": (payload.get("short_name") or name.split("•")[0].strip()[:22]),
            "role": role,
            "icon": icon,
            "fa_icon": payload.get("fa_icon") or "fa-robot",
            "color": color,
            "badge_class": payload.get("badge_class") or "indigo",
            "builtin": False,
            "description": description,
            "quick_prompts": quick_prompts[:5],
            "system_instructions": system_instructions,
            "updated_at": datetime.now().isoformat(),
        }

        updated = False
        for idx, existing in enumerate(custom_agents):
            if existing.get("id") == agent_id or existing.get("handle") == handle:
                custom_agents[idx] = agent_record
                updated = True
                break
        if not updated:
            custom_agents.append(agent_record)

        state["custom_agents"] = custom_agents
        cls._save_state(state)
        return agent_record

    @classmethod
    def delete_custom_agent(cls, agent_id: str) -> bool:
        state = cls._load_state()
        before = len(state.get("custom_agents", []))
        state["custom_agents"] = [
            a for a in state.get("custom_agents", [])
            if a.get("id") != agent_id and a.get("handle") != agent_id
        ]
        cls._save_state(state)
        return len(state["custom_agents"]) < before

    @classmethod
    def get_app_deliverables(cls, app_slug: str) -> List[Dict[str, Any]]:
        state = cls._load_state()
        deliverables = state.get("deliverables", {}).get(app_slug or "global", [])
        return deliverables if isinstance(deliverables, list) else []

    @classmethod
    def save_deliverable(cls, app_slug: str, deliverable: Dict[str, Any], db: Optional[Session] = None) -> Dict[str, Any]:
        state = cls._load_state()
        slug_key = app_slug or "global"
        state.setdefault("deliverables", {})
        items = state["deliverables"].get(slug_key, [])
        if not isinstance(items, list):
            items = []

        record = {
            "id": deliverable.get("id") or f"deliv-{int(time.time() * 1000)}",
            "app_slug": slug_key,
            "agent_id": deliverable.get("agent_id") or "social-media",
            "agent_name": deliverable.get("agent_name") or "Agent Crew",
            "agent_icon": deliverable.get("agent_icon") or "✨",
            "type": deliverable.get("type") or "report",  # social_kit | report | council | manual
            "title": deliverable.get("title") or "Agent Deliverable",
            "content_md": deliverable.get("content_md") or "",
            "social_kit": deliverable.get("social_kit"),
            "extracted_tasks": deliverable.get("extracted_tasks") or [],
            "asset_url": deliverable.get("asset_url"),
            "created_at": datetime.now().isoformat(),
        }
        items.insert(0, record)
        state["deliverables"][slug_key] = items[:40]
        cls._save_state(state)

        # If save_as_manual is requested and db is available, also persist as a DocManualModel
        if deliverable.get("save_as_manual") and db and app_slug:
            app_obj = db.query(AppProfileModel).filter(AppProfileModel.slug == app_slug).first()
            if app_obj and record["content_md"]:
                manual = DocManualModel(
                    app_id=app_obj.id,
                    title=record["title"],
                    doc_type="agent_deliverable",
                    content_md=record["content_md"],
                )
                db.add(manual)
                db.commit()
                record["saved_to_manuals"] = True

        return record

    @classmethod
    def delete_deliverable(cls, app_slug: str, deliverable_id: str) -> bool:
        state = cls._load_state()
        slug_key = app_slug or "global"
        items = state.get("deliverables", {}).get(slug_key, [])
        before = len(items)
        state.setdefault("deliverables", {})[slug_key] = [
            d for d in items if d.get("id") != deliverable_id
        ]
        cls._save_state(state)
        return len(state["deliverables"][slug_key]) < before

    @classmethod
    def _build_app_context(cls, app_obj: Optional[AppProfileModel], file_path: Optional[str], prompt: str, db: Optional[Session]) -> Dict[str, Any]:
        """Gather rich app context, file tree, key code snippets, and SOT grounding."""
        app_name = app_obj.name if app_obj else "Geppy's GitBridge"
        tech_stack = ", ".join(app_obj.tech_stack) if (app_obj and app_obj.tech_stack) else "HTML5, TailwindCSS, JavaScript, Python FastAPI"
        description = (app_obj.description if app_obj and app_obj.description else "Application in Geppy's App Universe")
        project_files_list: List[str] = []
        file_context = ""

        if app_obj:
            try:
                tree = WorkspaceService.get_app_file_tree(app_obj)
                project_files_list = [f["path"] for f in tree if isinstance(f, dict) and f.get("path")]
            except Exception:
                project_files_list = []

            if project_files_list:
                file_context += f"\n--- PROJECT FILES ({len(project_files_list)} files) ---\n" + ", ".join(project_files_list[:60]) + "\n"

            target_to_read = file_path
            if not target_to_read and project_files_list:
                from gitbridge.services.extension_service import ExtensionService
                target_to_read = ExtensionService.resolve_best_target_file(app_obj, prompt, None)

            if target_to_read:
                f_res = WorkspaceService.read_app_file(app_obj, target_to_read)
                if f_res.get("success") and f_res.get("content"):
                    file_context += f"\n--- KEY FILE ({target_to_read}) ---\n{f_res['content'][:5000]}\n"

            if "README.md" in project_files_list and target_to_read != "README.md":
                r_res = WorkspaceService.read_app_file(app_obj, "README.md")
                if r_res.get("success") and r_res.get("content"):
                    file_context += f"\n--- README.md ---\n{r_res['content'][:2500]}\n"

        sot_grounding = ""
        if db:
            try:
                sot_grounding = SOTService.build_sot_system_grounding(prompt, db)
            except Exception:
                pass

        return {
            "app_name": app_name,
            "tech_stack": tech_stack,
            "description": description,
            "project_files_list": project_files_list,
            "file_context": file_context,
            "sot_grounding": sot_grounding,
        }

    @classmethod
    def _extract_tasks_and_social_kit(
        cls,
        raw_response: str,
        app_obj: Optional[AppProfileModel],
        project_files_list: List[str],
        prompt: str,
        default_category: str = "feature",
    ) -> Dict[str, Any]:
        """Extract ```tasks / ```json task arrays and ```social_kit JSON blocks from an agent response."""
        clean_text = raw_response or ""
        extracted_tasks: List[Dict[str, Any]] = []
        social_kit: Optional[Dict[str, Any]] = None

        if not raw_response:
            return {"clean_text": "", "extracted_tasks": [], "social_kit": None}

        # 1. Extract ```social_kit { ... } ``` block if present
        sk_pattern = re.compile(r"```social_kit\s*(\{[\s\S]*?\})\s*```", re.IGNORECASE)
        sk_match = sk_pattern.search(clean_text)
        if sk_match:
            try:
                parsed_sk = json.loads(sk_match.group(1))
                if isinstance(parsed_sk, dict):
                    social_kit = parsed_sk
                    clean_text = (clean_text[:sk_match.start()] + clean_text[sk_match.end():]).strip()
            except Exception:
                pass

        # 2. Extract ```tasks [ ... ] ``` or ```json [ ... ] ``` block
        fence_pattern = re.compile(r"```(?:tasks|json)?\s*(\[\s*\{[\s\S]*?\}\s*\])\s*```", re.IGNORECASE)
        fence_match = fence_pattern.search(clean_text)
        if fence_match:
            try:
                candidate_list = json.loads(fence_match.group(1))
                if isinstance(candidate_list, list) and any(
                    isinstance(item, dict) and (item.get("title") or item.get("suggested_prompt"))
                    for item in candidate_list
                ):
                    extracted_tasks = candidate_list
                    clean_text = (clean_text[:fence_match.start()] + clean_text[fence_match.end():]).strip()
            except Exception:
                pass

        # 3. Fallback bullet extraction if no fenced task array was found
        if not extracted_tasks and clean_text:
            fallback_items = []
            for m in re.finditer(
                r"(?:^|\n)\s*(?:\d+[\.\)]|[-*•])\s*\*\*([^*:\n]{3,80}):?\*\*[:\s—–-]*(.+?)(?=\n\s*(?:\d+[\.\)]|[-*•]|\n|#|$))",
                clean_text,
                re.DOTALL,
            ):
                t_title = m.group(1).strip().rstrip(":")
                t_desc = re.sub(r"\s+", " ", m.group(2).strip())
                if t_title and len(t_desc) > 8:
                    fallback_items.append({
                        "title": t_title[:75],
                        "category": default_category,
                        "description": t_desc[:200],
                        "suggested_prompt": f"{t_title}: {t_desc[:300]}",
                    })
            if len(fallback_items) >= 2:
                extracted_tasks = fallback_items[:8]

        # 4. Resolve target_file for every task against the app's real file tree
        if app_obj and extracted_tasks:
            from gitbridge.services.extension_service import ExtensionService
            for t in extracted_tasks:
                if isinstance(t, dict):
                    t.setdefault("category", default_category)
                    req_tf = t.get("target_file")
                    if req_tf and req_tf in project_files_list and not req_tf.lower().endswith("index.html"):
                        t["target_file"] = req_tf
                    else:
                        combined = f"{t.get('title', '')} {t.get('description', '')} {t.get('suggested_prompt', '')} {prompt}"
                        best_tf = ExtensionService.resolve_best_target_file(app_obj, combined, req_tf)
                        if best_tf:
                            t["target_file"] = best_tf

        return {
            "clean_text": clean_text,
            "extracted_tasks": extracted_tasks,
            "social_kit": social_kit,
        }

    @classmethod
    def run_agent_mission(
        cls,
        agent_id: str,
        prompt: str,
        app_slug: Optional[str] = None,
        file_path: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
        generate_promo_visual: bool = False,
        save_deliverable_flag: bool = True,
        screen_frame_b64: Optional[str] = None,
        images_b64: Optional[List[str]] = None,
        db: Optional[Session] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Execute a specialized agent mission for the target app, returning markdown, Proceed tasks, and optional Social Kit."""
        agent = cls.get_agent(agent_id) or DEFAULT_AGENTS[0]
        app_obj = None
        if app_slug and db:
            app_obj = db.query(AppProfileModel).filter(AppProfileModel.slug == app_slug).first()

        ctx = cls._build_app_context(app_obj, file_path, prompt, db)
        app_name = ctx["app_name"]
        project_files_list = ctx["project_files_list"]

        default_prompt = (
            agent["quick_prompts"][0]
            if agent.get("quick_prompts")
            else f"Review {app_name} and provide actionable recommendations and Proceed tasks."
        )
        mission_prompt = (prompt or "").strip() or default_prompt

        category_map = {
            "design-architect": "design",
            "system-architect": "architecture",
            "social-media": "growth",
            "qa-reliability": "fix",
            "product-strategy": "feature",
            "docs-manual": "docs",
        }
        default_cat = category_map.get(agent["id"], "feature")

        system_prompt = f"""{agent['system_instructions']}

Target Application: "{app_name}"
Tech Stack: {ctx['tech_stack']}
App Summary: {ctx['description']}
{ctx['sot_grounding']}

IMPORTANT TASK EXTRACTION REQUIREMENT:
At the very end of your response, ALWAYS output a valid JSON array wrapped in ```tasks ... ``` fences containing 2 to 5 concrete, actionable steps that can be executed on this project:
```tasks
[
  {{
    "title": "Short punchy task title",
    "category": "{default_cat}",
    "target_file": "exact/relative/path/from/project.ext",
    "description": "1-sentence summary of what this task accomplishes",
    "suggested_prompt": "Detailed instruction for the AI code engine to implement this step in target_file"
  }}
]
```"""

        user_payload = f"""Application: {app_name}
{ctx['file_context']}

Mission Request for {agent['name']}:
{mission_prompt}"""

        raw_response = None
        engine_used = "gemini-central"
        elapsed_ms = 0
        t0 = time.perf_counter()

        from gitbridge.services.antigravity_service import AntigravityDaemonPool
        AntigravityDaemonPool.begin_live_job(
            mode="agent_mission",
            slug=app_slug or "global",
            app_name=app_name,
            title=f"{agent['icon']} {agent['short_name']}: {mission_prompt[:90]}",
            target_file=file_path or "",
        )

        # Use warm Antigravity Service on Port 8001 when app has a local workspace and agent needs deep code inspection
        if app_obj and app_obj.local_path and os.path.exists(app_obj.local_path):
            try:
                from gitbridge.services.antigravity_service import AntigravityService
                ag_prompt = (
                    f"[SPECIALIZED AGENT ROLE: {agent['name']} — {agent['role']}]\n"
                    f"{agent['system_instructions']}\n\n"
                    f"Mission Request:\n{mission_prompt}"
                )
                ag_res = AntigravityService.run_agent_brainstorm(
                    app_obj=app_obj,
                    message=ag_prompt,
                    history=history or [],
                    file_path=file_path,
                    sot_grounding=ctx["sot_grounding"],
                    project_files_list=project_files_list,
                    best_file=file_path,
                )
                if ag_res and ag_res.get("raw_response"):
                    raw_response = ag_res["raw_response"]
                    engine_used = ag_res.get("engine", "google-antigravity-service")
            except Exception as e:
                print(f"[AgentCrewService] Antigravity port fallback notice: {e}")

        extra_f = list(images_b64 or [])
        if screen_frame_b64:
            extra_f.append(screen_frame_b64)
        from gitbridge.services.chat_service import LiveScreenStreamHub
        active_frames, stream_note = LiveScreenStreamHub.get_active_vision_frames(extra_frames=extra_f or None)

        if not raw_response:
            messages = []
            for h in (history or [])[-6:]:
                role = "user" if h.get("sender") == "user" else "model"
                messages.append({"role": role, "parts": [{"text": h.get("text", "")}]})
            messages.append({"role": "user", "parts": [{"text": user_payload}]})
            if stream_note:
                messages[-1]["parts"][0]["text"] = f"{stream_note}\n\n" + messages[-1]["parts"][0]["text"]
            raw_response = CentralKeyService.call_gemini(messages, system_prompt, images_b64=active_frames or None)

        elapsed_ms = int((time.perf_counter() - t0) * 1000)

        if not raw_response:
            raw_response = (
                f"### {agent['icon']} {agent['name']}\n\n"
                f"I analyzed **{app_name}** ({ctx['tech_stack']}). Here are my recommended next steps:\n\n"
                f"1. **Core {agent['short_name']} Enhancement:** Upgrade the primary workflow in `{project_files_list[0] if project_files_list else 'index.html'}`.\n"
                f"2. **Polish & Verification:** Validate responsiveness, edge cases, and visual consistency across the app."
            )

        parsed = cls._extract_tasks_and_social_kit(
            raw_response=raw_response,
            app_obj=app_obj,
            project_files_list=project_files_list,
            prompt=mission_prompt,
            default_category=default_cat,
        )
        clean_text = parsed["clean_text"]
        extracted_tasks = parsed["extracted_tasks"]
        social_kit = parsed["social_kit"]

        # If this is the Social Media agent and no structured social_kit JSON was fenced, synthesize a structured kit from the markdown
        if agent["id"] == "social-media" and not social_kit:
            social_kit = cls._build_fallback_social_kit(app_name, ctx["description"], clean_text)

        # Optional: generate a promotional visual via Asset Lab if requested
        asset_record = None
        if generate_promo_visual:
            visual_prompt = (
                (social_kit or {}).get("visual_prompt")
                or f" sleek promotional showcase graphic and emblem for {app_name}: {ctx['description'][:120]}"
            )
            try:
                asset_record = AssetLabService.generate_visual_asset(
                    title=f"{app_name} • Promo Visual",
                    master_prompt=visual_prompt,
                    target_format="promo_banner",
                    aspect_ratio="16:9",
                    color_palette=["#F59E0B", "#6366F1", "#06B6D4", "#0F172A"],
                    composition_blueprint=f"Social Media Promo Visual for {app_name}",
                    app_slug=app_slug,
                )
            except Exception as e:
                print(f"[AgentCrewService] Promo visual generation notice: {e}")

        deliverable_record = None
        if save_deliverable_flag:
            deliv_type = "social_kit" if agent["id"] == "social-media" else ("manual" if agent["id"] == "docs-manual" else "report")
            deliverable_record = cls.save_deliverable(
                app_slug=app_slug or "global",
                deliverable={
                    "agent_id": agent["id"],
                    "agent_name": agent["name"],
                    "agent_icon": agent["icon"],
                    "type": deliv_type,
                    "title": f"{agent['short_name']}: {mission_prompt[:60]}",
                    "content_md": clean_text,
                    "markdown": clean_text,
                    "social_kit": social_kit,
                    "extracted_tasks": extracted_tasks,
                    "asset_url": asset_record.get("image_url") if isinstance(asset_record, dict) else None,
                },
                db=db,
            )

        AntigravityDaemonPool.finish_live_job(
            success=True,
            elapsed_ms=elapsed_ms,
            summary=f"{agent['icon']} {agent['short_name']} mission complete ({len(extracted_tasks)} Proceed tasks)",
        )

        return {
            "status": "success",
            "agent": agent,
            "app_slug": app_slug,
            "app_name": app_name,
            "text": clean_text,
            "reply": clean_text,
            "spoken_reply": cls.build_spoken_summary(clean_text, speaker_name=agent["short_name"]),
            "extracted_tasks": extracted_tasks,
            "social_kit": social_kit,
            "image_data": asset_record,
            "asset": asset_record,
            "deliverable": deliverable_record,
            "engine": engine_used,
            "elapsed_ms": elapsed_ms,
        }

    @classmethod
    def run_crew_council(
        cls,
        prompt: str,
        app_slug: Optional[str] = None,
        agent_ids: Optional[List[str]] = None,
        file_path: Optional[str] = None,
        screen_frame_b64: Optional[str] = None,
        db: Optional[Session] = None,
        images_b64: Optional[List[str]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Summon multiple specialized agents together ("Crew Council Mode") to evaluate an app
        from Design, Architecture, Social Media, QA, and Strategy perspectives in one unified mission.
        """
        from gitbridge.services.antigravity_service import AntigravityDaemonPool
        selected_ids = agent_ids or ["design-architect", "system-architect", "social-media", "product-strategy"]
        selected_agents = [cls.get_agent(aid) for aid in selected_ids]
        selected_agents = [a for a in selected_agents if a is not None]
        if not selected_agents:
            selected_agents = DEFAULT_AGENTS[:4]

        app_obj = None
        if app_slug and db:
            app_obj = db.query(AppProfileModel).filter(AppProfileModel.slug == app_slug).first()

        ctx = cls._build_app_context(app_obj, file_path, prompt, db)
        app_name = ctx["app_name"]
        project_files_list = ctx["project_files_list"]
        mission_goal = (prompt or "").strip() or f"Conduct a full multi-agent Crew Council review of {app_name} covering UI/UX Design, System Architecture, Growth/Social Media, and Product Roadmap."

        AntigravityDaemonPool.begin_live_job(
            mode="council",
            slug=app_slug or "global",
            app_name=app_name,
            title=f"⚡ Crew Council ({len(selected_agents)} Officers): {mission_goal[:80]}",
            target_file=file_path or "",
        )

        roster_desc = "\n".join(
            [f"- **{a['icon']} {a['name']}** ({a['role']}): {a['description']}" for a in selected_agents]
        )

        extra_f = list(images_b64 or [])
        if screen_frame_b64:
            extra_f.append(screen_frame_b64)
        from gitbridge.services.chat_service import LiveScreenStreamHub
        active_frames, stream_note = LiveScreenStreamHub.get_active_vision_frames(extra_frames=extra_f or None)

        system_prompt = f"""You are the **GitBridge Agent Crew Council** conducting a coordinated multi-agent review for "{app_name}".
Participating Crew Members:
{roster_desc}

Target Application: "{app_name}"
Tech Stack: {ctx['tech_stack']}
App Summary: {ctx['description']}
{ctx['sot_grounding']}
{stream_note}

Structure your response clearly with a dedicated section for EACH participating agent (using their icon and name as a `###` heading), followed by a `### ⚡ Crew Council Master Action Plan` summary.
If **Pulse (Social Media & Growth Agent)** is in the council, include a ready-to-post X/Twitter launch post and LinkedIn blurb in Pulse's section, plus a ```social_kit JSON block.
At the very end of your response, ALWAYS output a consolidated ```tasks JSON block containing 4 to 7 high-impact tasks across the participating agents, with each task mapped to an exact `"target_file"` from the project file tree so the user can click **Proceed** to execute them!"""

        user_payload = f"""Application: {app_name}
{ctx['file_context']}

Crew Council Mission:
{mission_goal}"""

        t0 = time.perf_counter()
        raw_response = CentralKeyService.call_gemini(
            [{"role": "user", "parts": [{"text": user_payload}]}],
            system_prompt,
            images_b64=active_frames or None,
        )
        elapsed_ms = int((time.perf_counter() - t0) * 1000)

        if not raw_response:
            sections = [f"## ⚡ Crew Council Briefing for **{app_name}**\n"]
            for a in selected_agents:
                sections.append(f"### {a['icon']} {a['name']}\n- Focused review on **{a['role']}** for `{app_name}`.")
            raw_response = "\n\n".join(sections)

        parsed = cls._extract_tasks_and_social_kit(
            raw_response=raw_response,
            app_obj=app_obj,
            project_files_list=project_files_list,
            prompt=mission_goal,
            default_category="feature",
        )

        deliverable = cls.save_deliverable(
            app_slug=app_slug or "global",
            deliverable={
                "agent_id": "crew-council",
                "agent_name": "⚡ Agent Crew Council",
                "agent_icon": "⚡",
                "type": "council",
                "title": f"Crew Council ({len(selected_agents)} Agents): {mission_goal[:50]}",
                "content_md": parsed["clean_text"],
                "markdown": parsed["clean_text"],
                "social_kit": parsed["social_kit"],
                "extracted_tasks": parsed["extracted_tasks"],
            },
            db=db,
        )

        AntigravityDaemonPool.finish_live_job(
            success=True,
            elapsed_ms=elapsed_ms,
            summary=f"⚡ Crew Council complete ({len(parsed['extracted_tasks'])} Proceed tasks)",
        )

        return {
            "status": "success",
            "mode": "council",
            "agent": {"id": "crew-council", "name": "⚡ Agent Crew Council", "icon": "⚡", "role": "Multi-Agent Council"},
            "agents": selected_agents,
            "app_slug": app_slug,
            "app_name": app_name,
            "text": parsed["clean_text"],
            "reply": parsed["clean_text"],
            "spoken_reply": cls.build_spoken_summary(parsed["clean_text"], speaker_name="Geppy & Crew Council"),
            "extracted_tasks": parsed["extracted_tasks"],
            "social_kit": parsed["social_kit"],
            "deliverable": deliverable,
            "elapsed_ms": elapsed_ms,
        }

    @classmethod
    def select_relevant_agents_for_consultation(cls, prompt: str, has_error: bool = False) -> List[Dict[str, Any]]:
        """Automatically pick the best 2-3 specialized agents for Geppy to consult based on the user's topic."""
        p_low = (prompt or "").lower()
        all_agents = cls.list_agents()
        picked_ids: List[str] = []

        if has_error or any(k in p_low for k in ("error", "bug", "crash", "freeze", "fix", "broken", "antigravity", "fail", "issue")):
            picked_ids.append("qa-reliability")
            picked_ids.append("system-architect")
        if any(k in p_low for k in ("design", "ui", "ux", "color", "layout", "button", "style", "look", "screen", "icon", "blank", "contextile", "card", "visual")):
            if "design-architect" not in picked_ids:
                picked_ids.append("design-architect")
        if any(k in p_low for k in ("code", "api", "backend", "database", "route", "fast", "performance", "architecture", "structure", "function")):
            if "system-architect" not in picked_ids:
                picked_ids.append("system-architect")
        if any(k in p_low for k in ("feature", "idea", "next", "roadmap", "build", "what should", "plan", "monetiz")):
            if "product-strategy" not in picked_ids:
                picked_ids.append("product-strategy")
        if any(k in p_low for k in ("social", "launch", "tweet", "linkedin", "reddit", "promo", "share", "market")):
            if "social-media" not in picked_ids:
                picked_ids.append("social-media")
        if any(k in p_low for k in ("doc", "readme", "manual", "guide", "explain")):
            if "docs-manual" not in picked_ids:
                picked_ids.append("docs-manual")

        # Default live co-design consultation trio: Design (Nova) + Architecture (Atlas) + Strategy/QA
        if not picked_ids:
            picked_ids = ["design-architect", "system-architect", "product-strategy"]
        elif len(picked_ids) == 1:
            fallback_second = "system-architect" if picked_ids[0] != "system-architect" else "design-architect"
            picked_ids.append(fallback_second)

        result = []
        for aid in picked_ids[:3]:
            ag = cls.get_agent(aid)
            if ag:
                result.append(ag)
        return result or all_agents[:3]

    @classmethod
    def build_spoken_summary(cls, markdown_text: str, speaker_name: str = "Geppy") -> str:
        """
        Convert a Markdown AI response into a clean, natural, upbeat spoken voice summary
        suitable for Web Speech API Text-to-Speech (TTS).
        """
        if not markdown_text:
            return f"{speaker_name} here! Ready for your next command."

        # Check if there is an explicit ```spoken ... ``` block first
        sp_match = re.search(r"```spoken\s*([\s\S]*?)\s*```", markdown_text, re.IGNORECASE)
        if sp_match and sp_match.group(1).strip():
            return re.sub(r"\s+", " ", sp_match.group(1).strip())[:520]

        text = markdown_text
        # Strip code blocks
        text = re.sub(r"```[\s\S]*?```", " ", text)
        # Strip inline code backticks but keep the word
        text = re.sub(r"`([^`]+)`", r"\1", text)
        # Strip markdown links [label](url) -> label
        text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
        # Strip headings, bold/italic markers, blockquotes, and bullet symbols
        text = re.sub(r"(?m)^\s*#{1,6}\s*", "", text)
        text = re.sub(r"[\*_~]{1,3}", "", text)
        text = re.sub(r"(?m)^\s*[-*•>]\s*", "", text)
        # Strip most decorative emojis so TTS doesn't read "high voltage sign" repeatedly
        text = re.sub(r"[\U00010000-\U0010ffff]", "", text)
        text = re.sub(r"[\u2600-\u27BF]", "", text)
        text = re.sub(r"\s+", " ", text).strip()

        # Take the first 3-4 sentences (up to ~460 chars) for crisp spoken voice pacing
        sentences = re.split(r"(?<=[.!?])\s+", text)
        spoken_parts = []
        total_len = 0
        for s in sentences:
            s_clean = s.strip()
            if not s_clean:
                continue
            spoken_parts.append(s_clean)
            total_len += len(s_clean)
            if total_len >= 360 or len(spoken_parts) >= 4:
                break
        result = " ".join(spoken_parts).strip()
        return result[:500] if result else f"{speaker_name} here! I've posted the full breakdown and action steps in the chat."

    @classmethod
    def consult_crew_with_geppy(
        cls,
        prompt: str,
        app_slug: Optional[str] = None,
        file_path: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
        images_b64: Optional[List[str]] = None,
        screen_frame_b64: Optional[str] = None,
        requested_agents: Optional[List[str]] = None,
        agent_ids: Optional[List[str]] = None,
        voice_mode: bool = False,
        db: Optional[Session] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Geppy Live Voice & Co-Design Consultation with the Specialized Agent Crew!
        Geppy inspects the live screen stream (of both GitBridge and Galactic), checks any active Antigravity errors,
        consults the relevant Agent Crew specialists (@design, @arch, @qa, @strategy, etc.), and returns:
          - `text` / `reply`: Coordinated markdown response from Geppy + the consulted agents
          - `spoken_reply`: Conversational voice summary for Geppy to speak aloud via TTS
          - `consulted_agents`: Structured list of the agents Geppy consulted and their key takeaways
          - `extracted_tasks`: Actionable Proceed tasks
        """
        from gitbridge.services.antigravity_service import AntigravityDaemonPool
        from gitbridge.services.chat_service import LiveScreenStreamHub

        app_obj = None
        if app_slug and db:
            app_obj = db.query(AppProfileModel).filter(AppProfileModel.slug == app_slug).first()

        is_gb = (not app_slug) or (app_slug.lower() in ("geppys-gitbridge", "gitbridge")) or (app_obj and "gitbridge" in app_obj.name.lower())
        geppy_name = "Captain Geppy" if is_gb else "Geppy"

        ctx = cls._build_app_context(app_obj, file_path, prompt, db)
        app_name = ctx["app_name"]
        project_files_list = ctx["project_files_list"]

        open_ag_errors = AntigravityDaemonPool.get_errors(slug=app_slug, include_resolved=False)
        latest_ag_err = open_ag_errors[0] if open_ag_errors else None

        req_ids = requested_agents or agent_ids
        if req_ids:
            consulted = [cls.get_agent(a) for a in req_ids]
            consulted = [a for a in consulted if a is not None]
        else:
            consulted = []
        if not consulted:
            consulted = cls.select_relevant_agents_for_consultation(prompt, has_error=bool(latest_ag_err))

        extra_f = list(images_b64 or [])
        if screen_frame_b64:
            extra_f.append(screen_frame_b64)
        active_frames, stream_note = LiveScreenStreamHub.get_active_vision_frames(extra_frames=extra_f or None)

        ag_err_context = ""
        if latest_ag_err:
            ag_err_context = (
                f"\nACTIVE ANTIGRAVITY ERROR CONTEXT:\n"
                f"- Title: {latest_ag_err.get('title')}\n"
                f"- What the Error Is: {latest_ag_err.get('what_is_the_error')}\n"
                f"- What Needs Done: {latest_ag_err.get('what_needs_done')}\n"
                f"- Target File: {latest_ag_err.get('target_file')}\n"
            )

        roster_lines = "\n".join(
            [f"- **{a['icon']} {a['name']} (@{a['handle']})** — {a['role']}" for a in consulted]
        )

        system_prompt = f"""You are **{geppy_name}** co-designing "{app_name}" live with the user via Voice & Screen Stream, and consulting with your Specialized Agent Crew!
{"CRITICAL IDENTITY RULE: Your name is strictly 'Geppy' (NEVER 'Captain Geppy' outside GitBridge)." if not is_gb else "You are Captain Geppy, Commander of Geppy's GitBridge."}

Specialists You Are Consulting Right Now:
{roster_lines}

{ctx['sot_grounding']}
{stream_note}
{ag_err_context}

HOW TO FORMAT YOUR RESPONSE:
1. First, output a ```spoken ... ``` block containing a warm, natural, conversational 2 to 4 sentence spoken response from {geppy_name} to read aloud via voice chat (mentioning what you see on the live screen if streaming is active, and summarizing what you and the consulted specialists recommend — no markdown symbols or code in the spoken block).
2. Next, write your visible Markdown response:
   - Start with **{geppy_name}'s Live Synthesis** (referencing what is visible on the live screen stream and any active Antigravity status/errors).
   - Include a concise **🤝 Agent Crew Consultation** section with a bullet or mini-section for each consulted specialist ({', '.join(a['icon'] + ' ' + a['short_name'] for a in consulted)}).
3. At the very end, output a valid ```tasks JSON array with 2 to 4 concrete **Proceed** implementation tasks mapped to exact project files (`target_file`)."""

        user_payload = f"""Target App: {app_name} ({ctx['tech_stack']})
{ctx['file_context']}

User Live Voice / Chat Request:
{prompt}"""

        messages = []
        for h in (history or [])[-5:]:
            role = "user" if h.get("sender") == "user" else "model"
            messages.append({"role": role, "parts": [{"text": h.get("text", "")}]})
        messages.append({"role": "user", "parts": [{"text": user_payload}]})

        t0 = time.perf_counter()
        raw_response = CentralKeyService.call_gemini(
            messages,
            system_prompt,
            timeout=25,
            images_b64=active_frames or None,
        )
        elapsed_ms = int((time.perf_counter() - t0) * 1000)

        spoken_reply = ""
        if raw_response:
            sp_match = re.search(r"```spoken\s*([\s\S]*?)\s*```", raw_response, re.IGNORECASE)
            if sp_match:
                spoken_reply = re.sub(r"\s+", " ", sp_match.group(1).strip())
                raw_response = (raw_response[:sp_match.start()] + raw_response[sp_match.end():]).strip()

        if not raw_response:
            crew_names = ", ".join(f"{a['icon']} {a['short_name']}" for a in consulted)
            raw_response = (
                f"### 🎙️ {geppy_name} + Crew Consultation ({crew_names})\n\n"
                f"I consulted with **{crew_names}** regarding **{app_name}**:\n\n"
                + "\n".join([f"- **{a['icon']} {a['name']}**: Recommends focusing on {a['role'].lower()} for your current workflow." for a in consulted])
            )

        parsed = cls._extract_tasks_and_social_kit(
            raw_response=raw_response,
            app_obj=app_obj,
            project_files_list=project_files_list,
            prompt=prompt,
            default_category="feature",
        )
        clean_text = parsed["clean_text"]
        if not spoken_reply:
            spoken_reply = cls.build_spoken_summary(clean_text, speaker_name=geppy_name)

        consulted_badges = [
            {
                "id": a["id"],
                "handle": a["handle"],
                "name": a["name"],
                "short_name": a["short_name"],
                "icon": a["icon"],
                "role": a["role"],
                "color": a.get("color", "#8b5cf6"),
            }
            for a in consulted
        ]

        return {
            "status": "success",
            "sender": "ai",
            "text": clean_text,
            "reply": clean_text,
            "spoken_reply": spoken_reply,
            "consulted_agents": consulted_badges,
            "extracted_tasks": parsed["extracted_tasks"],
            "social_kit": parsed["social_kit"],
            "live_stream_seen": len(active_frames) > 0,
            "live_stream_count": len(active_frames),
            "antigravity_error": latest_ag_err,
            "elapsed_ms": elapsed_ms,
        }

    @staticmethod
    def _build_fallback_social_kit(app_name: str, description: str, markdown_text: str) -> Dict[str, Any]:
        """Provide a structured Social Media Kit dictionary even if the model wrote prose without a ```social_kit fence."""
        return {
            "tagline": f"Meet {app_name} — {description[:110]}",
            "x_thread": [
                f"🚀 Just shipped a major upgrade to {app_name}!\n\n{description[:180]}\n\nHere's what's new inside 🧵👇",
                f"✨ Built for speed, visual clarity, and real-world workflows. Every detail in {app_name} is designed to save time and level up your daily toolkit.",
                f"🔥 Check out {app_name} in Geppy's App Universe and let me know what feature we should ship next! #BuildInPublic #AI #DevTools",
            ],
            "linkedin_post": (
                f"Excited to share the latest evolution of {app_name}!\n\n"
                f"{description}\n\n"
                f"See the full breakdown in the report above — feedback and ideas are always welcome!"
            ),
            "reddit_post": f"I've been building {app_name} ({description[:140]}) — would love your feedback on the architecture and UX!",
            "video_script": f"[0-5s Hook] Stop wrestling with clunky workflows — look at how {app_name} handles this in one click.\n[5-20s Demo] Show live workspace + AI actions.\n[20-30s CTA] Try it out and drop feature ideas below!",
            "hashtags": ["#BuildInPublic", "#AIApps", "#SoftwareArchitecture", "#UXDesign", "#GeppysUniverse"],
            "visual_prompt": f"Sleek futuristic app showcase banner for {app_name}, glowing glassmorphic UI cards, obsidian and cyan/amber accents, studio lighting",
        }
