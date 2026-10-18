"""
Asset Laboratory Service
Allows mixing multiple Source of Truth (SOT) Contextiles, reference images,
and creative directives to synthesize fine-tuned app icons, marketing banners, and visual assets.
"""

import os
import json
import time
import uuid
import base64
import requests
from typing import Dict, List, Any, Optional
from PIL import Image, ImageDraw, ImageFont, ImageFilter

import re

# Default Gemini models for synthesis
GEMINI_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gemini-1.5-pro"
]

def call_gemini(messages: List[Dict[str, Any]], system_instruction: str, json_mode: bool = False, timeout: int = 25) -> Optional[str]:
    """Call Google Gemini Generative Language API via CentralKeyService."""
    from gitbridge.services.central_key_service import CentralKeyService
    return CentralKeyService.call_gemini(messages, system_instruction, timeout=timeout, json_mode=json_mode)

def _hex_to_rgb(hex_str: Optional[str], default: tuple = (15, 23, 42)) -> tuple:
    """Extract 6-digit hex color and return (R, G, B) tuple."""
    if not hex_str:
        return default
    m = re.search(r'#([0-9a-fA-F]{6})', str(hex_str))
    if m:
        h = m.group(1)
        return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))
    return default


class AssetLabService:
    @staticmethod
    def _get_lab_dir() -> str:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        lab_dir = os.path.join(base_dir, "assets", "lab_generated")
        os.makedirs(lab_dir, exist_ok=True)
        return lab_dir

    @staticmethod
    def _get_history_path() -> str:
        return os.path.join(AssetLabService._get_lab_dir(), "history.json")

    @classmethod
    def get_history(cls) -> List[Dict[str, Any]]:
        """Retrieve all synthesized assets from the lab history."""
        hist_path = cls._get_history_path()
        if not os.path.exists(hist_path):
            return []
        try:
            with open(hist_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[AssetLabService] Error reading history: {e}")
            return []

    @classmethod
    def save_history_item(cls, item: Dict[str, Any]) -> None:
        """Append an asset record to history."""
        hist = cls.get_history()
        hist.insert(0, item) # Newest first
        hist_path = cls._get_history_path()
        try:
            with open(hist_path, "w", encoding="utf-8") as f:
                json.dump(hist[:100], f, indent=2) # Keep last 100
        except Exception as e:
            print(f"[AssetLabService] Error saving history: {e}")

    @classmethod
    def delete_history_item(cls, asset_id: str) -> bool:
        """Remove a synthesized asset record and its image file."""
        hist = cls.get_history()
        new_hist = []
        found = False
        lab_dir = cls._get_lab_dir()

        for item in hist:
            if item.get("id") == asset_id:
                found = True
                # Remove file if exists
                fname = item.get("filename")
                if fname:
                    fpath = os.path.join(lab_dir, fname)
                    if os.path.exists(fpath):
                        try: os.remove(fpath)
                        except: pass
            else:
                new_hist.append(item)

        if found:
            with open(cls._get_history_path(), "w", encoding="utf-8") as f:
                json.dump(new_hist, f, indent=2)
        return found

    @classmethod
    def resolve_image_path(cls, ref_url: Optional[str]) -> Optional[str]:
        """
        Locate any reference image path across GitBridge repositories,
        sot_references directories, lab directories, and app assets folders.
        """
        if not ref_url:
            return None
        if os.path.isabs(ref_url) and os.path.exists(ref_url):
            return ref_url
        
        clean_url = str(ref_url).split("?")[0]
        fname = os.path.basename(clean_url)
        
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) # gitbridge
        root_dir = os.path.dirname(base_dir) # project root
        
        candidate_dirs = [
            os.path.join(base_dir, "assets", "sot_references"),
            os.path.join(root_dir, "assets", "sot_references"),
            os.path.join(base_dir, "assets", "lab_generated"),
            os.path.join(root_dir, "assets", "lab_generated"),
            os.path.join(base_dir, "assets"),
            os.path.join(root_dir, "assets"),
            os.path.join(base_dir, "static", "icons"),
            os.path.join(base_dir, "static"),
        ]

        if "/api/apps/" in clean_url and "/assets/file/" in clean_url:
            parts = clean_url.split("/assets/file/")
            if len(parts) == 2:
                sub_fname = parts[1]
                slug = parts[0].split("/api/apps/")[-1]
                candidate_dirs.insert(0, os.path.join("d:\\Geppy_Apps", slug, "assets"))
                candidate_dirs.insert(0, os.path.join(base_dir, "apps", slug, "assets"))
                fname = sub_fname

        for d in candidate_dirs:
            p = os.path.join(d, fname)
            if os.path.exists(p):
                return p

        # Fallback recursive search
        for search_dir in [os.path.join(base_dir, "assets"), os.path.join(root_dir, "assets")]:
            if os.path.exists(search_dir):
                for root, _, files in os.walk(search_dir):
                    if fname in files:
                        return os.path.join(root, fname)

        return None

    @staticmethod
    def _extract_image_style_palette(image_path: str) -> Dict[str, Any]:
        """
        Analyze an uploaded style reference icon image:
        Extracts dominant border/accent color, background fill color, and transparency.
        """
        try:
            with Image.open(image_path) as img:
                rgba = img.convert("RGBA")
                w, h = rgba.size
                bbox = rgba.getbbox()

                non_transparent = []
                border_samples = []
                step = max(1, w // 40)
                for x in range(0, w, step):
                    for y in range(0, h, step):
                        r, g, b, a = rgba.getpixel((x, y))
                        if a > 40:
                            non_transparent.append((r, g, b))
                            if (x < w * 0.22 or x > w * 0.78 or y < h * 0.22 or y > h * 0.78) and (r + g + b > 100):
                                border_samples.append((r, g, b))

                if not non_transparent:
                    return {"accent": (245, 158, 11), "base": (15, 23, 42), "has_transparent_bg": True, "bbox": bbox}

                vibrant = [c for c in (border_samples or non_transparent) if max(c) - min(c) > 40]
                if vibrant:
                    accent = max(vibrant, key=lambda c: (max(c) - min(c)))
                else:
                    accent = (245, 158, 11)

                dark_bg = [c for c in non_transparent if sum(c) < 200]
                base = dark_bg[0] if dark_bg else (15, 23, 42)

                corner_alphas = [rgba.getpixel((0, 0))[3], rgba.getpixel((w - 1, 0))[3], rgba.getpixel((0, h - 1))[3], rgba.getpixel((w - 1, h - 1))[3]]
                has_transparent = any(a == 0 for a in corner_alphas)

                return {
                    "accent": accent,
                    "base": base,
                    "has_transparent_bg": has_transparent,
                    "bbox": bbox
                }
        except Exception as e:
            print(f"[AssetLabService] Palette extraction notice: {e}")
            return {"accent": (245, 158, 11), "base": (15, 23, 42), "has_transparent_bg": True, "bbox": None}

    @classmethod
    def brainstorm_concepts(
        cls,
        purpose: str,
        style_directive: str,
        app_slug: Optional[str] = None,
        brand_contextile: Optional[str] = None,
        style_contextile: Optional[str] = None,
        output_contextile: Optional[str] = None,
        reference_images: Optional[List[str]] = None,
        db=None
    ) -> List[Dict[str, Any]]:
        """
        Brainstorm 3 distinct, high-impact creative visual concepts for an asset
        based on the user's purpose, style, brand characters, and icon style guides.
        """
        from gitbridge.services.central_key_service import CentralKeyService
        from gitbridge.db.database import SessionLocal
        from gitbridge.db.models import AppProfileModel, ContextileModel, MediaAssetModel

        should_close = False
        if db is None:
            db = SessionLocal()
            should_close = True

        app_info = ""
        app_icons = []
        character_info = ""
        icon_guide_info = ""
        style_ctx_info = ""
        output_spec_info = ""
        app_name = "Application"

        try:
            # 1. Fetch App & Existing Icon Context if app_slug provided
            if app_slug:
                app_obj = db.query(AppProfileModel).filter(AppProfileModel.slug == app_slug).first()
                if app_obj:
                    app_name = app_obj.name
                    app_info = f"Application: '{app_obj.name}' (Description: {app_obj.description[:220] if app_obj.description else 'None'})\nTech Stack: {', '.join(app_obj.tech_stack or [])}"
                    icons = db.query(MediaAssetModel).filter(
                        MediaAssetModel.app_id == app_slug,
                        MediaAssetModel.asset_type.in_(['icon', 'logo'])
                    ).all()
                    for ic in icons:
                        if ic.url and ic.url not in app_icons:
                            app_icons.append(ic.url)
                    if app_obj.icon_url and app_obj.icon_url not in app_icons:
                        app_icons.append(app_obj.icon_url)

            # 2. Fetch Brand Character Context (Source of Truth)
            is_gb = bool(app_slug and app_slug.lower() in ("geppys-gitbridge", "gitbridge")) or ("gitbridge" in (app_name or "").lower())
            char_ctx = None
            if brand_contextile:
                char_ctx = db.query(ContextileModel).filter(ContextileModel.name == brand_contextile).first()
            if not char_ctx:
                preferred_brand = "captain-geppy" if is_gb else "geppybrand"
                char_ctx = db.query(ContextileModel).filter(ContextileModel.name == preferred_brand).first()
            if not char_ctx:
                char_ctx = db.query(ContextileModel).filter(ContextileModel.name.in_(["geppybrand", "captain-geppy"])).first()

            if char_ctx:
                display_char_title = char_ctx.title if (is_gb or "captain" not in (char_ctx.title or "").lower()) else "Geppy"
                character_info = f"Character / Mascot Source of Truth: '@{char_ctx.name}' ({display_char_title})\nLikeness & Traits: {char_ctx.reference_text}\nArchetype: {char_ctx.archetype}"
                if char_ctx.primary_image_url or char_ctx.reference_image_url:
                    character_info += f"\nCharacter Image URL: {char_ctx.primary_image_url or char_ctx.reference_image_url}"

            # 3. Fetch Style Contextile Grounding
            style_ctx = None
            if style_contextile:
                style_ctx = db.query(ContextileModel).filter(ContextileModel.name == style_contextile.lstrip("@")).first()
            if not style_ctx and any(k in (style_directive or "").lower() for k in ["hex", "orange"]):
                style_ctx = db.query(ContextileModel).filter(ContextileModel.name == "geppy-hex-icon").first()

            if style_ctx:
                style_ctx_info = f"Style Contextile Source of Truth: '@{style_ctx.name}' ({style_ctx.title})\nStyle Directive: {style_ctx.reference_text}\nModifiers: {style_ctx.modifiers}\nCompiled Prompt: {style_ctx.assembled_prompt}"
            else:
                icon_sot = db.query(ContextileModel).filter(ContextileModel.name == "galactic-icons").first()
                if icon_sot:
                    icon_guide_info = f"SOT Icon Style Guide: {icon_sot.reference_text}"
                else:
                    icon_guide_info = "SOT Icon Style Guide: Centered glyphs, micro-radiance rim glow, volumetric lighting, frosted translucent glass, smooth bevels."

            # 4. Output Specification
            if output_contextile:
                if output_contextile in ["png-transparent", "transparent_png", "transparent"]:
                    output_spec_info = "Format: Isolated PNG on Transparent Background (no background, transparent alpha channel)."
                elif output_contextile in ["svg-vector", "svg"]:
                    output_spec_info = "Format: Pure Scalable Vector Graphics (SVG) with clean transparent background."
                else:
                    out_ctx = db.query(ContextileModel).filter(ContextileModel.name == output_contextile.lstrip("@")).first()
                    if out_ctx:
                        output_spec_info = f"Output Contextile Spec: '@{out_ctx.name}' ({out_ctx.title})\nModifiers: {out_ctx.modifiers}"
            elif any(k in (style_directive or "").lower() for k in ["no background", "transparent"]):
                output_spec_info = "Format: Isolated PNG on Transparent Background (no background, transparent alpha channel)."

            # 5. Gather and resolve visual references for multimodal analysis
            all_refs = list(reference_images or [])
            if style_ctx:
                for s_img in [style_ctx.primary_image_url, style_ctx.reference_image_url] + (style_ctx.gallery_images or []):
                    if s_img and s_img not in all_refs:
                        all_refs.append(s_img)
            if char_ctx:
                for c_img in [char_ctx.primary_image_url, char_ctx.reference_image_url] + (char_ctx.gallery_images or []):
                    if c_img and c_img not in all_refs:
                        all_refs.append(c_img)
            for ic in app_icons:
                if ic and ic not in all_refs:
                    all_refs.append(ic)

            resolved_ref_paths = []
            for r in all_refs:
                rp = cls.resolve_image_path(r)
                if rp and rp not in resolved_ref_paths:
                    resolved_ref_paths.append(rp)

        finally:
            if should_close:
                db.close()

        combined_text = f"{purpose} {style_directive} {style_ctx_info} {output_spec_info}".lower()
        is_hex_req = "hex" in combined_text or "hexagonal" in combined_text
        is_transparent_req = "transparent" in combined_text or "no background" in combined_text or "isolated" in combined_text
        is_orange_req = "orange" in combined_text or is_hex_req

        is_gb = bool(app_slug and app_slug.lower() in ("geppys-gitbridge", "gitbridge")) or ("gitbridge" in (app_name or "").lower())
        default_char_desc = (
            "Captain Geppy: Charismatic cosmic astronaut commander wearing an obsidian-and-gold flight suit with an illuminated translucent cyan visor."
            if is_gb
            else "Geppy: Friendly, upbeat IT & AI specialist with brown hair, beard, modern glasses, and his signature blue shirt with white 'Geppy' text."
        )
        char_name_hint = "Captain Geppy" if is_gb else "Geppy"

        ref_instruction = ""
        if resolved_ref_paths:
            ref_instruction = f"- VISUAL REFERENCE IMAGES: {len(resolved_ref_paths)} image(s) provided. Look at the attached image(s): analyze the silhouette shape, beveling, materials, glow, palette, and icon layout. Ensure your 3 concepts and SVGs explicitly adopt and harmonize with this style!"

        prompt = f"""You are the Master Creative Director and Lead Iconographer for Geppy's App Universe.
The creator needs 3 distinctly unique, high-production-value visual concepts for an asset.

USER REQUIREMENTS:
- WHAT IT'S FOR: {purpose or "Flagship application icon and visual brand asset"}
- GENERAL STYLE & MOOD: {style_directive or "Modern Hexagonal App Icon with Bold Orange Border and Metallic Accents"}
- TARGET APP: {app_info or f"App: {app_name}"}
- BRAND CHARACTER / MASCOT (Source of Truth):
{character_info or default_char_desc}
- STYLE CONTEXTILE (Source of Truth):
{style_ctx_info or icon_guide_info}
- PRODUCTION OUTPUT SPEC:
{output_spec_info or "Isolated transparent PNG / SVG output without background"}
- EXISTING ICON REFERENCES: {', '.join(app_icons) if app_icons else 'Standard Hexagonal & Squircle Iconography'}
{ref_instruction}

CRITICAL SHAPE & TRANSPARENCY RULES:
- Hexagonal Silhouette Requested: {is_hex_req} (If True: all concepts MUST feature a 6-sided hexagonal silhouette with bold orange border #F59E0B and metallic accents).
- Transparent Background (No Background) Requested: {is_transparent_req} (If True: all concepts and SVGs MUST be isolated on a transparent background with NO solid background rectangle).
- Primary Accent Color: {"Bold Orange (#F59E0B)" if is_orange_req else "Vibrant Cyan and Amber Gold"}.
{"" if is_gb else "- IDENTITY RULE: In this app, the character is strictly named 'Geppy' (NEVER 'Captain Geppy')."}

INSTRUCTIONS:
Generate exactly 3 DISTINCT creative concepts:
- Concept 1: "Hero Brand Integration" — Stars the brand character / mascot likeness ({char_name_hint}) seamlessly integrated into the requested silhouette (e.g. Hexagon or Squircle).
- Concept 2: "Signature Symbolic Glyph" — A stylized, powerful symbolic emblem or badge fusing the app's core utility with the brand's aesthetic language (e.g. glowing orbital ledger, hexagonal vault core, futuristic diamond emblem).
- Concept 3: "Dimensional Scene / Isometric Matrix" — A rich, isometric or deeply layered glassmorphic dimensional scene with floating elements, ambient cosmic depth, and tangible physical materials.

For EACH concept, generate clean, valid SVG preview code (viewBox="0 0 256 256", with {("hexagonal polygon points='128,18 228,73 228,183 128,238 28,183 28,73' stroke='#F59E0B' stroke-width='6' fill='#0F172A'" if is_hex_req else "squircle rect rx='56'")}, gradient defs, and custom foreground shapes without opaque background) so the user gets an immediate, stunning visual preview in their dashboard!

Return strictly valid JSON with this schema:
{{
  "concepts": [
    {{
      "id": "concept-1",
      "title": "Creative Title",
      "pitch": "1-2 sentence compelling summary of why this concept works.",
      "style_label": "e.g. Hexagonal App Icon (Orange Accent / No Background)",
      "color_palette": ["#F59E0B (Geppy Orange)", "#06B6D4 (Cyan Visor)", "#1E1B4B (Deep Obsidian)", "#0F172A (Glass Base)"],
      "composition_blueprint": "Detailed breakdown of background, midground, and foreground elements.",
      "master_prompt": "Hyper-detailed generation prompt ready for the synthesizer.",
      "character_role": "How character likeness is preserved.",
      "icon_style_role": "How icon style references are applied.",
      "target_format": "app_icon",
      "aspect_ratio": "1:1",
      "svg_preview_code": "<svg viewBox=\\"0 0 256 256\\" xmlns=\\"http://www.w3.org/2000/svg\\">...</svg>"
    }},
    ...
  ]
}}"""

        user_parts = [{"text": prompt}]
        for rpath in resolved_ref_paths[:2]:
            try:
                mime = "image/png" if rpath.lower().endswith(".png") else "image/jpeg"
                with open(rpath, "rb") as f_img:
                    b64_str = base64.b64encode(f_img.read()).decode("utf-8")
                user_parts.append({
                    "inlineData": {
                        "mimeType": mime,
                        "data": b64_str
                    }
                })
            except Exception as e:
                print(f"[AssetLabService] Attach image part notice: {e}")

        raw_res = CentralKeyService.call_gemini(
            [{"role": "user", "parts": user_parts}],
            "You are an expert AI Design Director. Output strictly valid JSON matching the requested schema.",
            timeout=30,
            json_mode=True,
            max_output_tokens=8192
        )

        concepts = []
        if raw_res:
            try:
                clean_json = raw_res.strip()
                if "```json" in clean_json:
                    clean_json = clean_json.split("```json")[1].split("```")[0].strip()
                elif "```" in clean_json:
                    clean_json = clean_json.split("```")[1].split("```")[0].strip()
                parsed = json.loads(clean_json)
                concepts = parsed.get("concepts", [])
            except Exception as e:
                print(f"[AssetLabService] Brainstorm JSON parse notice: {e}")

        # If model returned fewer than 3 concepts or failed, supply rich synthesized fallback concepts
        if not concepts or len(concepts) < 3:
            concepts = cls._generate_fallback_concepts(
                purpose=purpose,
                style_directive=style_directive,
                character_info=character_info,
                app_slug=app_slug,
                is_hex=is_hex_req,
                is_transparent=is_transparent_req,
                is_orange=is_orange_req,
                resolved_ref_paths=resolved_ref_paths,
                style_name=style_ctx.title if style_ctx else None
            )

        # Normalize keys across all concepts
        for c in concepts:
            svg = c.get("svg_preview") or c.get("svg_preview_code") or ""
            c["svg_preview"] = svg
            c["svg_preview_code"] = svg
            
            style_tag = c.get("style_tag") or c.get("style_label") or "3D SQUIRCLE"
            c["style_tag"] = style_tag
            c["style_label"] = style_tag

            blueprint = c.get("blueprint") or c.get("master_prompt") or ""
            c["blueprint"] = blueprint
            c["master_prompt"] = blueprint

            # Clean color palette
            raw_palette = c.get("color_palette") or []
            clean_palette = []
            for item in raw_palette:
                if isinstance(item, str):
                    m = re.search(r"#[0-9a-fA-F]{6}", item)
                    if m:
                        clean_palette.append(m.group(0))
                    elif item.startswith("#"):
                        clean_palette.append(item.split()[0])
            if clean_palette:
                c["color_palette"] = clean_palette

        return concepts

    @classmethod
    def _generate_fallback_concepts(
        cls,
        purpose: str,
        style_directive: str,
        character_info: str,
        app_slug: Optional[str],
        is_hex: bool = False,
        is_transparent: bool = False,
        is_orange: bool = False,
        resolved_ref_paths: Optional[List[str]] = None,
        style_name: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Fallback generator producing 3 distinct production-grade concepts with tailored SVG preview graphics."""
        target_name = purpose or "Galactic Application"
        p_lower = (purpose + " " + (app_slug or "") + " " + style_directive).lower()
        
        # Analyze reference image palette if available
        accent_hex = "#F59E0B"
        if resolved_ref_paths:
            pal = cls._extract_image_style_palette(resolved_ref_paths[0])
            c_rgb = pal.get("accent", (245, 158, 11))
            accent_hex = f"#{c_rgb[0]:02x}{c_rgb[1]:02x}{c_rgb[2]:02x}".upper()
            if pal.get("has_transparent_bg"):
                is_transparent = True

        style_label = style_name or ("Hexagonal App Icon (Orange Accent / No Background)" if (is_hex or is_orange) else "3D Glassmorphic Squircle")

        # 1. Developer / Git / Bridge / Code Application Suite
        if any(k in p_lower for k in ["git", "bridge", "branch", "commit", "repo", "version", "code", "dev"]):
            c1_svg = f"""<svg viewBox="0 0 256 256" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="g_bg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#0f172a"/>
      <stop offset="100%" stop-color="#1e1b4b"/>
    </linearGradient>
    <filter id="g_glow" x="-20%" y="-20%" width="140%" height="140%">
      <feDropShadow dx="0" dy="8" stdDeviation="12" flood-color="{accent_hex}" flood-opacity="0.5"/>
    </filter>
  </defs>
  <polygon points="128,16 230,75 230,181 128,240 26,181 26,75" fill="url(#g_bg)" stroke="{accent_hex}" stroke-width="7" filter="url(#g_glow)"/>
  <polygon points="128,26 220,79 220,177 128,230 36,177 36,79" fill="none" stroke="#fbbf24" stroke-width="2" stroke-opacity="0.6"/>
  <!-- Git Branching Graph -->
  <line x1="96" y1="64" x2="96" y2="192" stroke="{accent_hex}" stroke-width="6" stroke-linecap="round"/>
  <path d="M 96 150 Q 96 110 160 110 L 160 76" fill="none" stroke="#06b6d4" stroke-width="5" stroke-linecap="round"/>
  <!-- Commit Nodes -->
  <circle cx="96" cy="74" r="14" fill="#0f172a" stroke="{accent_hex}" stroke-width="4"/>
  <circle cx="96" cy="74" r="6" fill="{accent_hex}"/>
  <circle cx="96" cy="148" r="14" fill="#0f172a" stroke="#fbbf24" stroke-width="4"/>
  <circle cx="96" cy="148" r="6" fill="#fbbf24"/>
  <circle cx="96" cy="186" r="14" fill="#0f172a" stroke="{accent_hex}" stroke-width="4"/>
  <circle cx="96" cy="186" r="6" fill="{accent_hex}"/>
  <circle cx="160" cy="74" r="14" fill="#0f172a" stroke="#06b6d4" stroke-width="4"/>
  <circle cx="160" cy="74" r="6" fill="#06b6d4"/>
</svg>"""

            c2_svg = f"""<svg viewBox="0 0 256 256" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="c2_g" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#1c1917"/>
      <stop offset="100%" stop-color="#0c0a09"/>
    </linearGradient>
    <filter id="c2_gl">
      <feDropShadow dx="0" dy="6" stdDeviation="10" flood-color="{accent_hex}" flood-opacity="0.5"/>
    </filter>
  </defs>
  <polygon points="128,16 230,75 230,181 128,240 26,181 26,75" fill="url(#c2_g)" stroke="{accent_hex}" stroke-width="7" filter="url(#c2_gl)"/>
  <!-- Code Chevrons < / > -->
  <path d="M 88 100 L 64 128 L 88 156" fill="none" stroke="#06b6d4" stroke-width="6" stroke-linecap="round" stroke-linejoin="round"/>
  <path d="M 168 100 L 192 128 L 168 156" fill="none" stroke="{accent_hex}" stroke-width="6" stroke-linecap="round" stroke-linejoin="round"/>
  <line x1="140" y1="92" x2="116" y2="164" stroke="#fbbf24" stroke-width="6" stroke-linecap="round"/>
</svg>"""

            c3_svg = f"""<svg viewBox="0 0 256 256" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="c3_g" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#1e1b4b"/>
      <stop offset="100%" stop-color="#0f172a"/>
    </linearGradient>
    <filter id="c3_gl">
      <feDropShadow dx="0" dy="8" stdDeviation="14" flood-color="{accent_hex}" flood-opacity="0.45"/>
    </filter>
  </defs>
  <polygon points="128,16 230,75 230,181 128,240 26,181 26,75" fill="url(#c3_g)" stroke="{accent_hex}" stroke-width="7" filter="url(#c3_gl)"/>
  <!-- Bridge Connector Arcs -->
  <path d="M 60 160 Q 128 90 196 160" fill="none" stroke="#6366f1" stroke-width="4" stroke-dasharray="6 4"/>
  <circle cx="128" cy="120" r="28" fill="#0f172a" stroke="{accent_hex}" stroke-width="4"/>
  <polygon points="128,104 134,116 148,116 137,124 141,136 128,129 115,136 119,124 108,116 122,116" fill="{accent_hex}"/>
</svg>"""

            return [
                {
                    "id": "concept-1",
                    "title": f"GitBridge Quantum Conduit: {target_name}",
                    "pitch": f"An iconic multi-node branching git repository network with luminous amber commit nodes and high-contrast bridge arcs, framed inside a bold {accent_hex} hexagonal badge on pure transparent background.",
                    "style_label": f"{style_label} (Branching Git Tree)",
                    "color_palette": [accent_hex, "#06B6D4 (Cyan Branch)", "#FBBF24 (Gold Commit)", "#0F172A (Deep Obsidian)"],
                    "composition_blueprint": f"6-sided hexagonal silhouette ({accent_hex} border), dark obsidian core, branching git commit tree with glowing nodes, isolated on transparent background.",
                    "master_prompt": f"Flagship hexagonal app icon for {target_name}. Starring an illuminated multi-node git branching tree with amber ({accent_hex}) and cyan (#06B6D4) commit nodes, metallic bridge arcs, set inside a precision 6-sided hexagonal border with metallic bevels, isolated on clean transparent background, no background, 32-bit PNG.",
                    "character_role": "Brand heritage reflected through amber gold palette and metallic badge finish.",
                    "icon_style_role": f"Hexagonal silhouette with bold {accent_hex} border and metallic bevels.",
                    "target_format": "transparent_png",
                    "aspect_ratio": "1:1",
                    "svg_preview_code": c1_svg
                },
                {
                    "id": "concept-2",
                    "title": f"Terminal Code Chevron: {target_name}",
                    "pitch": "Futuristic code chevron < / > emblem illuminated with neon cyan and amber gold bevels, isolated inside the hexagonal badge.",
                    "style_label": f"{style_label} (Code Chevron Vanguard)",
                    "color_palette": [accent_hex, "#06B6D4 (Terminal Cyan)", "#FBBF24 (Gold Slash)", "#1C1917 (Deep Obsidian)"],
                    "composition_blueprint": "Precision code chevron brackets < / > inside a hexagonal container with dual metallic rim reflections and isolated alpha channel.",
                    "master_prompt": f"Flagship hexagonal app icon for {target_name}. Featuring glowing code chevron brackets (< / >) with polished orange ({accent_hex}) and cyan metallic bevels, centered on dark frosted obsidian glass inside a 6-sided hexagon, transparent background.",
                    "character_role": "Geometric precision echoing galactic engineering.",
                    "icon_style_role": "Modern developer terminal iconography.",
                    "target_format": "transparent_png",
                    "aspect_ratio": "1:1",
                    "svg_preview_code": c2_svg
                },
                {
                    "id": "concept-3",
                    "title": f"Galactic Commander Nexus: {target_name}",
                    "pitch": "Harmonizes Captain Geppy's commander crest with the branching version control nexus, honoring brand likeness and developer utility.",
                    "style_label": f"{style_label} (Commander Nexus)",
                    "color_palette": [accent_hex, "#6366F1 (Indigo Bridge)", "#FBBF24 (Commander Star)", "#1E1B4B (Space Navy)"],
                    "composition_blueprint": "Suspended galactic commander star over a curved version bridge with glowing telemetry conduit, transparent PNG output.",
                    "master_prompt": f"Flagship app icon for {target_name}. Central golden commander star crest seated above a curved digital bridge with glowing commit nodes, surrounded by a bold orange ({accent_hex}) hexagonal border, isolated on transparent background, 8K Octane render.",
                    "character_role": "Commander star insignia anchored at top node.",
                    "icon_style_role": "Multi-tier dimensional depth.",
                    "target_format": "transparent_png",
                    "aspect_ratio": "1:1",
                    "svg_preview_code": c3_svg
                }
            ]

        # 2. Finance / Cash / Vault Application Suite
        elif any(k in p_lower for k in ["cash", "money", "vault", "coin", "gold", "finance", "pay", "bank"]):
            c1_svg = f"""<svg viewBox="0 0 256 256" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="v_bg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#1c1917"/>
      <stop offset="100%" stop-color="#0c0a09"/>
    </linearGradient>
    <filter id="v_gl"><feDropShadow dx="0" dy="6" stdDeviation="10" flood-color="{accent_hex}" flood-opacity="0.5"/></filter>
  </defs>
  <polygon points="128,16 230,75 230,181 128,240 26,181 26,75" fill="url(#v_bg)" stroke="{accent_hex}" stroke-width="7" filter="url(#v_gl)"/>
  <circle cx="128" cy="128" r="54" fill="#292524" stroke="#fbbf24" stroke-width="4"/>
  <circle cx="128" cy="128" r="42" fill="#0c0a09" stroke="{accent_hex}" stroke-width="2"/>
  <text x="128" y="144" text-anchor="middle" font-size="44" font-weight="900" fill="#fbbf24" font-family="sans-serif">$</text>
</svg>"""
            c2_svg = f"""<svg viewBox="0 0 256 256" xmlns="http://www.w3.org/2000/svg">
  <polygon points="128,16 230,75 230,181 128,240 26,181 26,75" fill="#022c22" stroke="{accent_hex}" stroke-width="7"/>
  <polygon points="128,60 178,128 128,196 78,128" fill="#064e3b" stroke="#10b981" stroke-width="3"/>
  <circle cx="128" cy="128" r="18" fill="#fbbf24"/>
</svg>"""
            c3_svg = f"""<svg viewBox="0 0 256 256" xmlns="http://www.w3.org/2000/svg">
  <polygon points="128,16 230,75 230,181 128,240 26,181 26,75" fill="#1e1b4b" stroke="{accent_hex}" stroke-width="7"/>
  <rect x="78" y="88" width="100" height="80" rx="14" fill="#312e81" stroke="#818cf8" stroke-width="2"/>
  <circle cx="128" cy="128" r="16" fill="{accent_hex}"/>
</svg>"""
            return [
                {
                    "id": "concept-1",
                    "title": f"The Golden Vault: {target_name}",
                    "pitch": "A heavy hexagonal vault door with embossed gold coin and currency rune on transparent background.",
                    "style_label": f"{style_label} (Vault Door)",
                    "color_palette": [accent_hex, "#FBBF24 (Gold Core)", "#292524 (Bronze Rim)", "#0C0A09 (Obsidian)"],
                    "composition_blueprint": "Centered golden currency medallion inside reinforced hexagonal vault frame.",
                    "master_prompt": f"Flagship hexagonal app icon for {target_name}. Embossed golden coin with currency rune inside a heavy metallic vault door, bold orange ({accent_hex}) border, transparent background.",
                    "character_role": "Brand gold and obsidian palette.",
                    "icon_style_role": "Monolithic vault emblem.",
                    "target_format": "transparent_png",
                    "aspect_ratio": "1:1",
                    "svg_preview_code": c1_svg
                },
                {
                    "id": "concept-2",
                    "title": f"Emerald Wealth Ingot: {target_name}",
                    "pitch": "Precision metallic currency badge with radiant emerald shield and amber starlight node.",
                    "style_label": f"{style_label} (Emerald Ingot)",
                    "color_palette": ["#10B981 (Mint Emerald)", accent_hex, "#064E3B (Deep Vault)", "#022C22 (Obsidian)"],
                    "composition_blueprint": "Faceted emerald gemstone shield with golden star center inside hexagon.",
                    "master_prompt": f"Hexagonal app icon for {target_name}. Faceted emerald diamond badge with golden core, orange border ({accent_hex}), transparent background.",
                    "character_role": "Galactic wealth motif.",
                    "icon_style_role": "Precision gem shield.",
                    "target_format": "transparent_png",
                    "aspect_ratio": "1:1",
                    "svg_preview_code": c2_svg
                },
                {
                    "id": "concept-3",
                    "title": f"Dimensional Cash Matrix: {target_name}",
                    "pitch": "Layered isometric ledger shields with amber rim reflections and floating token.",
                    "style_label": f"{style_label} (Ledger Matrix)",
                    "color_palette": [accent_hex, "#818CF8 (Periwinkle)", "#312E81 (Cobalt)", "#1E1B4B (Space Navy)"],
                    "composition_blueprint": "Floating layered glass cash ledger plates with glowing amber core node.",
                    "master_prompt": f"App icon for {target_name}. Floating isometric frosted glass ledger plates with radiant orange core, transparent background, 8K Octane render.",
                    "character_role": "Cosmic ledger utility.",
                    "icon_style_role": "Isometric glass stack.",
                    "target_format": "transparent_png",
                    "aspect_ratio": "1:1",
                    "svg_preview_code": c3_svg
                }
            ]

        # 3. Default Suite (Hexagonal / Squircle Brand Mascot & Monogram)
        else:
            c1_svg = f"""<svg viewBox="0 0 256 256" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="def1_bg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#0f172a"/>
      <stop offset="100%" stop-color="#1e1b4b"/>
    </linearGradient>
    <filter id="def1_gl"><feDropShadow dx="0" dy="8" stdDeviation="12" flood-color="{accent_hex}" flood-opacity="0.45"/></filter>
  </defs>
  <polygon points="128,16 230,75 230,181 128,240 26,181 26,75" fill="url(#def1_bg)" stroke="{accent_hex}" stroke-width="7" filter="url(#def1_gl)"/>
  <polygon points="128,26 220,79 220,177 128,230 36,177 36,79" fill="none" stroke="#fbbf24" stroke-width="2" stroke-opacity="0.65"/>
  <circle cx="128" cy="116" r="46" fill="#1e293b" stroke="{accent_hex}" stroke-width="3"/>
  <ellipse cx="128" cy="114" rx="34" ry="17" fill="#06b6d4"/>
  <polygon points="128,140 131,148 140,148 133,153 136,161 128,156 120,161 123,153 116,148 125,148" fill="{accent_hex}"/>
</svg>"""
            c2_svg = f"""<svg viewBox="0 0 256 256" xmlns="http://www.w3.org/2000/svg">
  <polygon points="128,16 230,75 230,181 128,240 26,181 26,75" fill="#1c1917" stroke="{accent_hex}" stroke-width="7"/>
  <polygon points="128,80 168,128 128,176 88,128" fill="#292524" stroke="#fbbf24" stroke-width="3"/>
  <circle cx="128" cy="128" r="16" fill="{accent_hex}"/>
</svg>"""
            c3_svg = f"""<svg viewBox="0 0 256 256" xmlns="http://www.w3.org/2000/svg">
  <polygon points="128,16 230,75 230,181 128,240 26,181 26,75" fill="#1e1b4b" stroke="{accent_hex}" stroke-width="7"/>
  <path d="M 64 128 Q 128 64 192 128 Q 128 192 64 128" fill="none" stroke="#6366f1" stroke-width="3"/>
  <circle cx="128" cy="128" r="12" fill="#06b6d4"/>
</svg>"""
            return [
                {
                    "id": "concept-1",
                    "title": f"Commander Vanguard: {target_name}",
                    "pitch": "Anchors Captain Geppy and the flagship brand identity inside a sharp 6-sided hexagonal silhouette with bold orange borders and metallic bevels.",
                    "style_label": f"{style_label} (Commander Hero)",
                    "color_palette": [accent_hex, "#06B6D4 (Cyan Visor)", "#1E1B4B (Space Obsidian)", "#0F172A (Deep Slate)"],
                    "composition_blueprint": f"Centered hexagonal silhouette with bold {accent_hex} border, metallic gold inner bevel, illuminated cyan visor and commander star, transparent PNG.",
                    "master_prompt": f"Flagship hexagonal app icon for {target_name}. Starring Captain Geppy commander with illuminated translucent cyan visor, golden commander stars, and obsidian space suit, isolated in a 6-sided hexagonal badge with bold orange ({accent_hex}) metallic border, transparent background.",
                    "character_role": "Primary character likeness front and center inside hexagonal badge.",
                    "icon_style_role": f"Hexagonal silhouette with bold {accent_hex} rim and metallic bevels.",
                    "target_format": "transparent_png",
                    "aspect_ratio": "1:1",
                    "svg_preview_code": c1_svg
                },
                {
                    "id": "concept-2",
                    "title": f"Geometric Vault Shield: {target_name}",
                    "pitch": "A bold, memorable symbolic emblem that fuses the app's core utility into a precision golden orange hexagonal vault shield.",
                    "style_label": f"{style_label} (Symbolic Emblem)",
                    "color_palette": [accent_hex, "#FBBF24 (Gold Core)", "#292524 (Dark Bronze)", "#0C0A09 (Deep Obsidian)"],
                    "composition_blueprint": "Geometric hexagonal vault shield with centered glowing starlight core, bold orange metallic borders, volumetric bevel shadows.",
                    "master_prompt": f"Flagship hexagonal app icon for {target_name}. A glorious 3D hexagonal emblem glyph with polished orange ({accent_hex}) metallic bevels and glowing starlight core, isolated without background on transparent alpha channel.",
                    "character_role": "Insignia and orange palette inherit Geppy brand commander heritage.",
                    "icon_style_role": "Centered bold monolithic 3D hexagonal glyph.",
                    "target_format": "transparent_png",
                    "aspect_ratio": "1:1",
                    "svg_preview_code": c2_svg
                },
                {
                    "id": "concept-3",
                    "title": f"Hex-Matrix Dimensional Horizon: {target_name}",
                    "pitch": "An isometric, multi-layered glassmorphic hexagonal composition with floating cyan starlight core and deep orange rim reflection.",
                    "style_label": f"{style_label} (Isometric Matrix)",
                    "color_palette": [accent_hex, "#6366F1 (Indigo Glow)", "#06B6D4 (Cyan Pulse)", "#1E1B4B (Space Navy)"],
                    "composition_blueprint": "Layered isometric floating hexagonal glass plates with glowing cyan starlight node, orange rim reflection, transparent PNG alpha channel.",
                    "master_prompt": f"Flagship app icon for {target_name}. Modern isometric 3D composition with floating frosted translucent hexagonal glass plates, radiant cyan starlight node, bold orange border ({accent_hex}), isolated on transparent background, 8K Octane render.",
                    "character_role": "Cosmic aesthetic echoes brand universe.",
                    "icon_style_role": "Multi-tier hexagonal glassmorphic depth.",
                    "target_format": "transparent_png",
                    "aspect_ratio": "1:1",
                    "svg_preview_code": c3_svg
                }
            ]

    @staticmethod
    def _load_font(size: int = 18, bold: bool = False, serif: bool = False):
        """Load a scalable TrueType system font with clean fallback."""
        font_dir = os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts")
        if serif:
            candidates = ["georgiab.ttf", "timesbd.ttf", "georgia.ttf", "times.ttf"] if bold else ["georgia.ttf", "times.ttf"]
        else:
            candidates = ["segoeuib.ttf", "arialbd.ttf", "calibrib.ttf", "segoeui.ttf", "arial.ttf"] if bold else ["segoeui.ttf", "arial.ttf", "calibri.ttf"]
        for fname in candidates:
            fpath = os.path.join(font_dir, fname)
            if os.path.exists(fpath):
                try:
                    return ImageFont.truetype(fpath, size=size)
                except Exception:
                    pass
        try:
            return ImageFont.load_default(size=size)
        except TypeError:
            return ImageFont.load_default()

    @staticmethod
    def _merge_variables(variables: Optional[Dict[str, Any]], ingredients_summary: Optional[List[Dict[str, Any]]]) -> Dict[str, Any]:
        """Merge explicit variables dict with default/configured variables from SOT ingredients."""
        vars_dict: Dict[str, Any] = {}
        if ingredients_summary:
            for ing in ingredients_summary:
                if not isinstance(ing, dict):
                    continue
                for v in (ing.get("variables") or []):
                    if isinstance(v, dict):
                        k = v.get("key")
                        val = v.get("value") if v.get("value") not in (None, "") else v.get("default_value")
                        if k and val not in (None, "") and k not in vars_dict:
                            vars_dict[k] = val
        if isinstance(variables, dict):
            for k, val in variables.items():
                if k and val not in (None, ""):
                    vars_dict[k] = val
        return vars_dict

    @classmethod
    def _extract_option_toggles_summary(
        cls,
        ingredients: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Extract enabled and disabled option toggles from any attached Contextile templates.
        """
        enabled_list: List[Dict[str, Any]] = []
        disabled_list: List[Dict[str, Any]] = []
        for ing in (ingredients or []):
            if not isinstance(ing, dict):
                continue
            mods = ing.get("modifiers") if isinstance(ing.get("modifiers"), dict) else {}
            toggles = ing.get("option_toggles") if isinstance(ing.get("option_toggles"), list) else mods.get("option_toggles")
            if not isinstance(toggles, list):
                continue
            c_name = ing.get("name") or ing.get("title") or "contextile"
            for t in toggles:
                if not isinstance(t, dict):
                    continue
                entry = {
                    "contextile": c_name,
                    "id": str(t.get("id") or ""),
                    "label": str(t.get("label") or t.get("id") or ""),
                    "prompt": str(t.get("prompt") or t.get("label") or ""),
                    "enabled": bool(t.get("enabled", False))
                }
                if entry["enabled"]:
                    enabled_list.append(entry)
                else:
                    disabled_list.append(entry)
        return {"enabled": enabled_list, "disabled": disabled_list}

    @classmethod
    def _classify_and_resolve_references(
        cls,
        ingredients_summary: Optional[List[Dict[str, Any]]] = None,
        reference_images: Optional[List[str]] = None
    ) -> Dict[str, List[str]]:
        """
        Cleanly separate Subject Portrait Photos (real character/person Source of Truth photos to feature as the focal subject)
        from Contextile Sample Images / Style / Icon / Cover References (used only for layout & style inspiration, NEVER pasted as identity).
        """
        from gitbridge.services.sot_service import SOTService
        subject_urls: List[str] = []
        style_urls: List[str] = []
        all_urls: List[str] = []

        def _is_style_or_icon_filename(url_or_path: str) -> bool:
            base = os.path.basename(str(url_or_path).split("?")[0]).lower()
            if base.endswith(".ico") or base.endswith(".svg"):
                return True
            style_tokens = [
                "1970s-cover", "cover", "geppys_galactic_icon", "geppystechtoolbox",
                "preview_", "asset_", "cash", "badge", "hex", "template", "mockup"
            ]
            return any(t in base for t in style_tokens)

        if ingredients_summary:
            for ing in ingredients_summary:
                if not isinstance(ing, dict):
                    continue
                role = str(ing.get("role") or ing.get("sot_role") or "").lower()
                arch = str(ing.get("archetype") or "").lower()
                name = str(ing.get("name") or "").lower()
                mods = ing.get("modifiers") if isinstance(ing.get("modifiers"), dict) else {}
                entity_kind = str(ing.get("entity_kind") or SOTService.infer_entity_kind(arch, mods, name)).lower()

                p_img = ing.get("primary_image_url") or ing.get("reference_image_url")
                g_imgs = ing.get("gallery_images") or []
                ing_imgs = [u for u in ([p_img] + list(g_imgs)) if u]

                # Contextile templates contain SAMPLE images (never subject identity photos!)
                is_subject_ing = (
                    entity_kind == "sot" and (
                        role in ["subject", "mascot"] or
                        arch in ["character", "person", "mascot", "subject"] or
                        name in ["jon", "captain-geppy"]
                    ) and arch not in ["place", "environment", "style", "scene_template", "icon_set", "ui_component", "output"]
                )

                for u in ing_imgs:
                    if u not in all_urls:
                        all_urls.append(u)
                    if is_subject_ing and not _is_style_or_icon_filename(u):
                        if u not in subject_urls:
                            subject_urls.append(u)
                    else:
                        if u not in style_urls:
                            style_urls.append(u)

        for u in (reference_images or []):
            if not u:
                continue
            if u not in all_urls:
                all_urls.append(u)
            if u not in style_urls and u not in subject_urls:
                if _is_style_or_icon_filename(u):
                    style_urls.append(u)
                else:
                    subject_urls.append(u)

        subject_paths = []
        for u in subject_urls:
            p = cls.resolve_image_path(u)
            if p and os.path.exists(p) and p not in subject_paths:
                subject_paths.append(p)

        style_paths = []
        for u in style_urls:
            p = cls.resolve_image_path(u)
            if p and os.path.exists(p) and p not in style_paths and p not in subject_paths:
                style_paths.append(p)

        all_paths = list(dict.fromkeys(subject_paths + style_paths))
        return {
            "subject_paths": subject_paths,
            "style_paths": style_paths,
            "all_paths": all_paths
        }

    SOT_ROLE_LABELS = {
        "mascot": "SOURCE OF TRUTH: CHARACTER / PERSON (LOCK IDENTITY)",
        "subject": "SOURCE OF TRUTH: CHARACTER / PERSON (LOCK IDENTITY)",
        "logo": "SOURCE OF TRUTH: BRAND LOGO (LOCK GEOMETRY)",
        "icon": "CONTEXTILE TEMPLATE: ICON CONTAINER",
        "item": "SOURCE OF TRUTH: SPECIFIC PROP / ITEM",
        "blank_substrate": "CONTEXTILE OF TRUTH: PHYSICAL BLANK & SIZING TEMPLATE (FIT TO SAFE ZONE)",
        "style_only": "CONTEXTILE SAMPLE (MATCH LAYOUT/STYLE ONLY - NOT IDENTITY)",
        "style": "CONTEXTILE SAMPLE (MATCH LAYOUT/STYLE ONLY - NOT IDENTITY)",
        "stage": "SOURCE OF TRUTH: SPECIFIC PLACE / SETTING (LOCK LOCATION)",
        "lighting": "LIGHTING & ATMOSPHERE REFERENCE",
        "materials": "SURFACE MATERIAL REFERENCE",
        "base_image": "BASE IMAGE (COMPOSITE ONTO THIS)"
    }

    SOT_INTERACTION_PROMPTS = {
        "none": "",
        "holding": "The character MUST be actively holding, wielding, or operating the REFERENCE ITEM/PROP.",
        "wearing": "The character MUST be wearing or equipped with the REFERENCE ITEM/PROP as part of their outfit/gear.",
        "sitting_on": "The character MUST be sitting on, riding, or perched atop the REFERENCE ITEM/PROP.",
        "branded": "The item/scene MUST be branded with the REFERENCE CHARACTER/LOGO colors and aesthetic.",
        "mascot_printed": "The REFERENCE CHARACTER image MUST be printed, embossed, or emblazoned directly onto the surface of the REFERENCE ITEM/PROP.",
        "logo_printed": "The REFERENCE LOGO MUST be printed, stamped, or embossed directly onto the surface of the REFERENCE ITEM/PROP.",
        "emblem": "Use the REFERENCE PICTURE as the central 3D heroic emblem/crest inside the badge.",
        "themed_after": "Design the entire target item/concept so its shape, materials, and details are themed after the REFERENCE PICTURE.",
        "integrated": "Naturally blend and integrate the overlay picture into the base image matching lighting, perspective, and shadows.",
        "sticker": "Apply the reference picture as a crisp die-cut vinyl sticker overlay."
    }

    @classmethod
    def build_scene_elements_and_reference_sheet(
        cls,
        ingredients_summary: Optional[List[Dict[str, Any]]] = None,
        reference_images: Optional[List[Any]] = None,
        scene_elements: Optional[List[Dict[str, Any]]] = None,
        asset_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Port of geppy-s-asset-lab's `combineImagesToSingleReference` + `sceneElements` architecture.
        Cleanly distinguishes unchanging Source-of-Truth (SOT) entities (Characters/People, Specific Places,
        Brand Logos, Props), Contextiles of Truth (Physical Blanks & Sizing Templates), and Contextile Templates
        (whose images are labeled as CONTEXTILE SAMPLES and whose embedded SOT handles are automatically expanded).
        """
        from gitbridge.services.sot_service import SOTService
        from gitbridge.db.database import SessionLocal
        from gitbridge.db.models import ContextileModel as SOTContextileModel

        elements: List[Dict[str, Any]] = []
        seen_paths: set = set()

        def _add_element(
            url_or_path: str,
            role: str = "mascot",
            interaction: str = "none",
            action: str = "",
            name: str = ""
        ):
            if not url_or_path:
                return
            local_p = cls.resolve_image_path(url_or_path)
            if not local_p or not os.path.exists(local_p):
                return
            # Allow same image only if given a distinct role/action
            dedup_key = f"{local_p}::{role}::{interaction}::{action}"
            if dedup_key in seen_paths:
                return
            seen_paths.add(dedup_key)

            role_key = (role or "mascot").lower().strip()
            base_label = cls.SOT_ROLE_LABELS.get(role_key, "REFERENCE SOURCE OF TRUTH")
            label_parts = [base_label]
            if name:
                label_parts.append(f"[{name.upper()}]")
            if interaction and interaction != "none":
                label_parts.append(f"INTERACTION: {interaction.upper().replace('_', ' ')}")
            if action:
                label_parts.append(f"ACTION: {action.upper()}")
            full_label = " - ".join(label_parts)

            elements.append({
                "url": url_or_path,
                "path": local_p,
                "role": role_key,
                "interaction": (interaction or "none").lower().strip(),
                "action": (action or "").strip(),
                "name": name or os.path.basename(local_p),
                "label": full_label
            })

        def _role_for_sot_archetype(arch_str: str, explicit_role: str = "") -> str:
            er = (explicit_role or "").lower().strip()
            a = (arch_str or "").lower().strip()
            if a == "blank_substrate" or er == "blank_substrate":
                return "blank_substrate"
            if a in ["place", "environment"] or er in ["stage", "place", "environment"]:
                return "stage"
            if a == "brand_asset" or er == "logo":
                return "logo"
            if a == "prop" or er == "item":
                return "item"
            return "mascot"

        # 1. Explicit scene_elements (from UI Source-of-Truth Picture Deck)
        for el in (scene_elements or []):
            if isinstance(el, dict):
                img_u = el.get("image_url") or el.get("url") or el.get("primary_image_url")
                _add_element(
                    url_or_path=img_u,
                    role=el.get("role") or el.get("identity_focus") or "mascot",
                    interaction=el.get("interaction") or "none",
                    action=el.get("action") or "",
                    name=el.get("name") or el.get("title") or ""
                )

        # 2. Attached SOT items, Contextiles of Truth (Blanks), & Contextile templates
        embedded_handles_to_resolve: List[str] = []
        attached_names = set()

        for ing in (ingredients_summary or []):
            if not isinstance(ing, dict):
                continue
            raw_name = str(ing.get("name") or "").strip().lower()
            if raw_name:
                attached_names.add(raw_name)
            ing_role = str(ing.get("sot_role") or ing.get("identity_focus") or ing.get("role") or "").lower()
            arch = str(ing.get("archetype") or "").lower()
            mods = ing.get("modifiers") if isinstance(ing.get("modifiers"), dict) else {}
            entity_kind = str(ing.get("entity_kind") or SOTService.infer_entity_kind(arch, mods, raw_name)).lower()

            if entity_kind == "contextile_of_truth":
                ing_role = "blank_substrate"
            elif entity_kind == "contextile":
                # Contextile images are sample layouts/styles ONLY — never lock them as character/person identity!
                if arch in ["icon_set", "ui_component"] or ing_role == "icon":
                    ing_role = "icon"
                else:
                    ing_role = "style_only"

                # Collect any embedded Source-of-Truth handles locked inside this Contextile (e.g. @blackwood-manor inside @blackwood-horror-movie)
                emb = ing.get("embedded_sot_handles") if isinstance(ing.get("embedded_sot_handles"), list) else mods.get("embedded_sot_handles")
                if isinstance(emb, list):
                    for h in emb:
                        clean_h = str(h or "").strip().lstrip("@").lower()
                        if clean_h and clean_h not in embedded_handles_to_resolve:
                            embedded_handles_to_resolve.append(clean_h)
            else:
                # True Source of Truth entity (Person, Character, Place, Brand Logo, Prop)
                ing_role = _role_for_sot_archetype(arch, ing_role)

            ing_interaction = str(ing.get("interaction") or "none").lower()
            ing_action = str(ing.get("action") or "").strip()
            ing_name = str(ing.get("title") or ing.get("name") or "")
            p_img = ing.get("primary_image_url") or ing.get("reference_image_url")
            if p_img:
                _add_element(p_img, role=ing_role, interaction=ing_interaction, action=ing_action, name=ing_name)
            for g_img in (ing.get("gallery_images") or [])[:2]:
                if g_img and g_img != p_img:
                    _add_element(g_img, role=ing_role, interaction=ing_interaction, action=ing_action, name=ing_name)

        # 2b. Expand embedded Source-of-Truth items from any attached Contextile template
        if embedded_handles_to_resolve:
            db = SessionLocal()
            try:
                for emb_handle in embedded_handles_to_resolve:
                    if emb_handle in attached_names:
                        continue
                    emb_rec = db.query(SOTContextileModel).filter(SOTContextileModel.name == emb_handle).first()
                    if emb_rec and emb_rec.primary_image_url:
                        emb_role = _role_for_sot_archetype(emb_rec.archetype or "place")
                        _add_element(
                            emb_rec.primary_image_url,
                            role=emb_role,
                            interaction="none",
                            action=f"Embedded SOT from Contextile (@{emb_rec.name})",
                            name=f"{emb_rec.title} (@{emb_rec.name})"
                        )
            except Exception as e:
                print(f"[AssetLabService] Embedded SOT resolution notice: {e}")
            finally:
                db.close()

        # 3. Extra uploaded Reference Images (each can be a string URL or a dict {url, role, interaction, action, name})
        for ref_item in (reference_images or []):
            if isinstance(ref_item, dict):
                _add_element(
                    url_or_path=ref_item.get("url") or ref_item.get("image_url"),
                    role=ref_item.get("role") or "item",
                    interaction=ref_item.get("interaction") or "holding",
                    action=ref_item.get("action") or "",
                    name=ref_item.get("name") or "Reference Picture"
                )
            elif isinstance(ref_item, str) and ref_item.strip():
                # Default extra uploaded picture to Mascot if no mascot yet, otherwise Item/Prop to interact with
                has_mascot = any(e["role"] in ("mascot", "subject") for e in elements)
                default_r = "item" if has_mascot else "mascot"
                default_int = "holding" if has_mascot else "none"
                _add_element(ref_item.strip(), role=default_r, interaction=default_int, name="Uploaded Reference")

        # Build the side-by-side Labeled Combined Reference Sheet (port of combineImagesToSingleReference)
        ref_sheet_img: Optional[Image.Image] = None
        ref_sheet_url: Optional[str] = None
        ref_sheet_path: Optional[str] = None

        if elements:
            try:
                target_w = 512
                padding = 20
                text_h = 64
                loaded_panels = []

                for el in elements[:6]:
                    try:
                        with Image.open(el["path"]) as im_raw:
                            im_rgba = im_raw.convert("RGBA")
                            rw, rh = im_rgba.size
                            scale = target_w / max(1, rw)
                            nh = min(640, max(256, int(rh * scale)))
                            # Fit cleanly onto a 512 x nh studio panel
                            panel_im = Image.new("RGBA", (target_w, nh), (248, 250, 252, 255))
                            im_fit = im_rgba.copy()
                            im_fit.thumbnail((target_w - 16, nh - 16), Image.Resampling.LANCZOS)
                            ox = (target_w - im_fit.width) // 2
                            oy = (nh - im_fit.height) // 2
                            panel_im.paste(im_fit, (ox, oy), im_fit)
                            loaded_panels.append((panel_im, el))
                    except Exception as e:
                        print(f"[AssetLabService] Reference panel load notice: {e}")

                if loaded_panels:
                    max_img_h = max(p[0].height for p in loaded_panels)
                    total_w = len(loaded_panels) * target_w + (len(loaded_panels) + 1) * padding
                    total_h = max_img_h + text_h + padding * 2

                    sheet = Image.new("RGBA", (total_w, total_h), (255, 255, 255, 255))
                    s_draw = ImageDraw.Draw(sheet)
                    font_lbl = cls._load_font(size=15, bold=True)
                    font_sub = cls._load_font(size=12, bold=False)

                    role_badge_colors = {
                        "mascot": (245, 158, 11),
                        "subject": (245, 158, 11),
                        "logo": (6, 182, 212),
                        "icon": (168, 85, 247),
                        "item": (16, 185, 129),
                        "style_only": (236, 72, 153),
                        "style": (236, 72, 153),
                        "stage": (59, 130, 246),
                        "base_image": (99, 102, 241)
                    }

                    cur_x = padding
                    for panel_im, el in loaded_panels:
                        b_col = role_badge_colors.get(el["role"], (15, 23, 42))
                        # Header bar above picture
                        s_draw.rounded_rectangle(
                            [cur_x, padding, cur_x + target_w, padding + text_h - 6],
                            radius=8,
                            fill=(*b_col, 255)
                        )
                        lbl_main = cls.SOT_ROLE_LABELS.get(el["role"], "SOURCE OF TRUTH")
                        lbl_sub_parts = []
                        if el.get("name"):
                            lbl_sub_parts.append(str(el["name"]))
                        if el.get("interaction") and el["interaction"] != "none":
                            lbl_sub_parts.append(f"Mode: {el['interaction'].upper()}")
                        if el.get("action"):
                            lbl_sub_parts.append(f"Action: {el['action']}")
                        lbl_sub = " | ".join(lbl_sub_parts) or "LOCKED VISUAL SOURCE OF TRUTH"

                        s_draw.text((cur_x + 12, padding + 8), lbl_main[:48], fill=(255, 255, 255, 255), font=font_lbl)
                        s_draw.text((cur_x + 12, padding + 32), lbl_sub[:62], fill=(254, 249, 195, 255), font=font_sub)

                        # Paste actual picture below header
                        img_y = padding + text_h
                        sheet.paste(panel_im, (cur_x, img_y))
                        s_draw.rectangle(
                            [cur_x, img_y, cur_x + target_w, img_y + panel_im.height],
                            outline=(*b_col, 255),
                            width=3
                        )
                        cur_x += target_w + padding

                    ref_sheet_img = sheet
                    if asset_id:
                        lab_dir = cls._get_lab_dir()
                        sheet_fname = f"{asset_id}_ref_sheet.png"
                        ref_sheet_path = os.path.join(lab_dir, sheet_fname)
                        sheet.convert("RGB").save(ref_sheet_path, "PNG", quality=92)
                        ref_sheet_url = f"/api/asset-lab/file/{sheet_fname}"
            except Exception as e:
                print(f"[AssetLabService] build_scene_elements_and_reference_sheet notice: {e}")

        return {
            "elements": elements,
            "ref_sheet_img": ref_sheet_img,
            "ref_sheet_path": ref_sheet_path,
            "ref_sheet_url": ref_sheet_url
        }

    @classmethod
    def auto_fill_concepts(
        cls,
        count: int = 4,
        theme_prompt: str = "",
        asset_type: str = "app_icon",
        ingredients_summary: Optional[List[Dict[str, Any]]] = None,
        app_slug: Optional[str] = None
    ) -> List[Dict[str, str]]:
        """
        Port of geppy-s-asset-lab's `generateIconDefinitions`:
        Uses Gemini to generate `count` distinct, cohesive concepts (each with `label`, `prompt`, and `interaction`)
        so the user can generate multiple concepts as a whole (2x2 or 3x3 grid sheet + sliced individual assets).
        """
        from gitbridge.services.central_key_service import CentralKeyService
        count = max(2, min(12, int(count or 4)))

        ing_names = [str(i.get("title") or i.get("name")) for i in (ingredients_summary or []) if isinstance(i, dict)]
        ing_ctx = ", ".join(ing_names) if ing_names else "Geppy Source of Truth"

        sys_inst = (
            "You are an expert visual director for an AI Asset Lab. "
            "Return ONLY a JSON array of objects with keys: "
            "\"label\" (short 2-3 word title), \"prompt\" (concrete visual description of the item/pose/concept), "
            "and \"interaction\" (one of: 'none', 'holding', 'wearing', 'sitting_on', 'mascot_printed', 'logo_printed', 'emblem', 'themed_after')."
        )
        u_prompt = (
            f"Generate {count} distinct, high-impact visual asset concepts that work together as a cohesive set.\n"
            f"Theme / Direction: {theme_prompt or 'Cohesive app icon & mascot action set'}\n"
            f"Asset Format: {asset_type}\n"
            f"Source of Truth Anchors: {ing_ctx}\n"
            f"Target App: {app_slug or 'General'}\n"
            f"Return a JSON array of exactly {count} items."
        )
        raw = CentralKeyService.call_gemini(
            [{"role": "user", "parts": [{"text": u_prompt}]}],
            sys_inst,
            timeout=18,
            json_mode=True
        )
        if raw:
            try:
                clean = raw.strip()
                if clean.startswith("```json"): clean = clean[7:]
                elif clean.startswith("```"): clean = clean[3:]
                if clean.endswith("```"): clean = clean[:-3]
                arr = json.loads(clean.strip())
                if isinstance(arr, list) and len(arr) > 0:
                    out = []
                    for idx, item in enumerate(arr[:count], 1):
                        if isinstance(item, dict):
                            out.append({
                                "label": str(item.get("label") or f"Concept {idx}"),
                                "prompt": str(item.get("prompt") or f"Variation {idx} of {theme_prompt or ing_ctx}"),
                                "interaction": str(item.get("interaction") or "none")
                            })
                    if out:
                        return out
            except Exception as e:
                print(f"[AssetLabService] auto_fill_concepts parse notice: {e}")

        # Intelligent instant fallback concepts
        base_label = theme_prompt.strip()[:28] if theme_prompt else "SOT Concept"
        defaults = [
            {"label": f"{base_label} • Hero Pose", "prompt": f"Primary heroic front-facing pose of {ing_ctx} with signature lighting and emblem.", "interaction": "none"},
            {"label": f"{base_label} • Action Tool", "prompt": f"{ing_ctx} actively holding and operating a glowing high-tech tool/gadget.", "interaction": "holding"},
            {"label": f"{base_label} • Emblem Crest", "prompt": f"Precision 3D metallic badge crest emblazoned with the {ing_ctx} insignia.", "interaction": "emblem"},
            {"label": f"{base_label} • Victory Gesture", "prompt": f"{ing_ctx} giving a confident thumbs-up celebration with radiant energy rim glow.", "interaction": "none"},
            {"label": f"{base_label} • Command Gear", "prompt": f"{ing_ctx} wearing upgraded tactical holographic visor and shoulder armor.", "interaction": "wearing"},
            {"label": f"{base_label} • Hover Mount", "prompt": f"{ing_ctx} perched atop a sleek floating cosmic platform/cruiser.", "interaction": "sitting_on"},
            {"label": f"{base_label} • Branded Artifact", "prompt": f"Collectible 3D artifact with the {ing_ctx} graphic printed on its surface.", "interaction": "mascot_printed"},
            {"label": f"{base_label} • Power Surge", "prompt": f"{ing_ctx} surrounded by a swirling vortex of neon starlight particles.", "interaction": "none"},
            {"label": f"{base_label} • Master Seal", "prompt": f"Stamped golden vault seal themed after {ing_ctx}.", "interaction": "themed_after"},
        ]
        return defaults[:count]

    @staticmethod
    def _is_trading_card_request(
        target_format: str,
        title: str = "",
        master_prompt: str = "",
        ingredients: Optional[List[Dict[str, Any]]] = None
    ) -> bool:
        """
        Determine if the asset should be rendered as a 1970s Trading / Baseball Card.
        STRICTLY requires either:
        - `target_format` explicitly set to trading_card / baseball_card, OR
        - An attached Contextile ingredient that is explicitly `@70s-baseball-card` / `@vintage-sport-card-elite`, OR
        - When `target_format` is `auto`/empty and the user explicitly typed `baseball card` / `70s baseball card`.
        """
        fmt = (target_format or "").lower().strip()
        if fmt in ["trading_card", "baseball_card", "tradingcard"]:
            return True
        for ing in (ingredients or []):
            if isinstance(ing, dict):
                ing_handle = str(ing.get("name") or "").lower().strip()
                if ing_handle in ["70s-baseball-card", "vintage-sport-card-elite"]:
                    return True
        if fmt and fmt not in ["auto", ""]:
            # User explicitly chose another format (e.g. app_icon, transparent_png, banner_hero)
            return False
        combined = f"{title} {master_prompt}".lower()
        card_phrases = ["70s baseball card", "1970s baseball card", "baseball card", "topps card"]
        if any(phrase in combined for phrase in card_phrases):
            return True
        return False

    @classmethod
    def synthesize_blend(
        cls,
        ingredients: List[Dict[str, Any]],
        custom_prompt: str,
        target_format: str = "app_icon",
        fidelity_mode: str = "balanced",
        overrides: Dict[str, Any] = None,
        reference_images: List[Any] = None,
        app_context: Optional[str] = None,
        variables: Dict[str, Any] = None,
        scene_elements: Optional[List[Dict[str, Any]]] = None,
        grid_mode: str = "single",
        grid_rows: int = 1,
        grid_cols: int = 1,
        concepts_list: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Synthesize Source-of-Truth (SOT) entities (People, Characters, Specific Places, Logos, Props),
        Contextile Templates (with sample images, embedded SOTs, and option toggles),
        and multi-concept grid specs into a Master Asset Generation Blueprint.
        """
        from gitbridge.services.sot_service import SOTService
        overrides = overrides or {}
        reference_images = reference_images or []
        merged_vars = cls._merge_variables(variables, ingredients)
        is_card = cls._is_trading_card_request(target_format, custom_prompt, custom_prompt, ingredients)
        toggle_info = cls._extract_option_toggles_summary(ingredients)
        enabled_toggles = toggle_info["enabled"]
        disabled_toggles = toggle_info["disabled"]

        aspect_map = {
            "app_icon": "1:1",
            "transparent_png": "1:1",
            "avatar": "1:1",
            "trading_card": "2.5:3.5",
            "banner_hero": "16:9",
            "social_story": "9:16",
            "ui_component": "4:3"
        }
        default_aspect = "2.5:3.5" if is_card else aspect_map.get(target_format, "1:1")

        # Build the geppy-s-asset-lab Labeled Reference Sheet from all active pictures
        sot_bundle = cls.build_scene_elements_and_reference_sheet(
            ingredients_summary=ingredients,
            reference_images=reference_images,
            scene_elements=scene_elements
        )
        active_elements = sot_bundle["elements"]
        ref_sheet_img = sot_bundle["ref_sheet_img"]

        # System Instruction for the AI Style Synthesizer
        system_instruction = f"""You are the Chief Visual Synthesizer for Geppy's Asset Lab.
You MUST strictly distinguish between THREE different entity types:
1. SOURCE OF TRUTH (SOT) ENTITIES (`entity_kind = "sot"`):
   - Unchanging ground-truth pieces: a specific Person (`@jon`), Character/Mascot (`@captain-geppy`), Specific Place/Location (`@blackwood-manor`), Brand Logo (`@geppybrand`), or Prop.
   - Their photos are labeled `SOURCE OF TRUTH: CHARACTER / PERSON (LOCK IDENTITY)` or `SOURCE OF TRUTH: SPECIFIC PLACE / SETTING (LOCK LOCATION)`. You MUST preserve their exact identity, face, architecture, or geometry.
2. CONTEXTILES OF TRUTH (`entity_kind = "contextile_of_truth"`):
   - Physical Blank items & Sizing Templates (e.g., `@wood-plaque-blank`, `@slate-coaster-blank`, or an uploaded photo of a blank item to sublimate, laser engrave, stencil, or vinyl-cut).
   - They function as BOTH the Source of Truth for the physical blank substrate AND the calibrated sizing/output Contextile defining dimensions (`width_in` × `height_in`), safe margin, contour shape, and what can be output on it:
     * If Laser Engraver / Burn (`laser_bw`): Output MUST be strictly high-contrast 1-bit BLACK AND WHITE ONLY (#000000 = laser burn area, #FFFFFF = unburned blank; NO colors, NO gray background wash).
     * If Stencil with Edge Connections (`stencil_bridged`): Output MUST be a bold cuttable stencil where EVERY interior island is connected to the outer frame via structural stencil bridges / edge connections so no pieces fall out when cut.
     * If Vinyl Cutter (`vinyl_cut`): Solid weed-ready vector shapes with connected bridges.
3. CONTEXTILE TEMPLATES (`entity_kind = "contextile"`):
   - Reusable templatized settings, styles, fabrication rules, or scene templates (e.g., `@stencil-edge-connections`, `@laser-engrave-bw-burn`, `@blackwood-horror-movie`, `@70s-baseball-card`).
   - Their attached images are labeled `CONTEXTILE SAMPLE (MATCH LAYOUT/STYLE ONLY - NOT IDENTITY)`. Use them ONLY as a template for layout, framing, typography, texture, and mood — NEVER copy the sample person/subject inside a Contextile sample image!
   - A Contextile can include customizable OPTION TOGGLES and extensive VARIABLE DROPDOWNS. Strictly include all ENABLED option toggles and selected dropdown values.

CRITICAL FUSION RULES:
1. Honor the requested Target Format ('{target_format}') and Aspect Ratio ('{default_aspect}').
2. Look closely at the attached COMBINED REFERENCE SHEET image and follow each panel's header label (`SOURCE OF TRUTH`, `CONTEXTILE OF TRUTH`, vs `CONTEXTILE SAMPLE`).
3. If Grid / Multi-Concept Mode is active ('{grid_mode}', {grid_rows}x{grid_cols}), structure the blueprint for a cohesive {grid_rows}x{grid_cols} sprite sheet where every cell shares the locked Source-of-Truth character/style.

Respond ONLY with valid JSON in this exact structure:
{{
  "title": "Creative Asset Title reflecting the specific SOT entities, Contextile of Truth blank, Contextile template, and enabled options",
  "master_prompt": "Hyper-detailed visual generation prompt combining the unchanging Source-of-Truth character/place/prop with the Contextile of Truth blank sizing/fabrication constraints and Contextile template settings.",
  "negative_prompt": "blurry, low quality, generic primitive shapes, stacked icons, distorted anatomy, pixelated edges",
  "color_palette": ["#F59E0B (Primary Accent)", "#06B6D4 (Secondary Glow)", "#6366F1 (Energy Core)", "#0F172A (Deep Base)"],
  "composition_blueprint": "Detailed breakdown of how each Source-of-Truth entity is placed into the Contextile of Truth safe zone and Contextile template.",
  "style_fusion_notes": "Concise summary of how the Source-of-Truth entities, Contextile of Truth blank, Contextile template, and option toggles were fused.",
  "suggested_aspect_ratio": "{default_aspect}"
}}"""

        user_content = f"Target Format: {target_format}\nSuggested Aspect Ratio: {default_aspect}\nFidelity Mode: {fidelity_mode}\n"
        user_content += f"Generation Scope: {grid_mode} ({grid_rows}x{grid_cols})\n"
        if app_context:
            user_content += f"Target App: {app_context}\n"
        user_content += f"Creator Directives: {custom_prompt or 'Combine the attached Source-of-Truth entities into the active Contextile template.'}\n\n"
        if custom_prompt and "@" in str(custom_prompt):
            try:
                from gitbridge.db.database import SessionLocal
                _db = SessionLocal()
                try:
                    mention_res = SOTService.resolve_mentions(str(custom_prompt), _db)
                    if mention_res.get("grounding_prompt"):
                        user_content += f"{mention_res['grounding_prompt']}\n\n"
                finally:
                    _db.close()
            except Exception:
                pass

        if active_elements:
            user_content += "ACTIVE REFERENCE SHEET PANELS (SOT IDENTITIES, CONTEXTILES OF TRUTH BLANKS, vs CONTEXTILE SAMPLES):\n"
            for idx, el in enumerate(active_elements, 1):
                int_desc = cls.SOT_INTERACTION_PROMPTS.get(el["interaction"], "")
                user_content += (
                    f"[{idx}] Panel '{el['name']}' -> Role: {el['label']}\n"
                    f"    Rule: {int_desc or 'Follow panel header role strictly'}\n"
                )
                if el.get("action"):
                    user_content += f"    Specific Action/Pose: {el['action']}\n"

        sot_ings = []
        blank_ings = []
        ctx_ings = []
        for ing in (ingredients or []):
            if not isinstance(ing, dict):
                continue
            arch = str(ing.get("archetype") or "").lower()
            mods = ing.get("modifiers") if isinstance(ing.get("modifiers"), dict) else {}
            ek = str(ing.get("entity_kind") or SOTService.infer_entity_kind(arch, mods, ing.get("name"))).lower()
            if ek == "contextile_of_truth":
                blank_ings.append(ing)
            elif ek == "contextile":
                ctx_ings.append(ing)
            else:
                sot_ings.append(ing)

        if sot_ings:
            user_content += "\nATTACHED SOURCE OF TRUTH (SOT) ENTITIES (UNCHANGING SUBJECTS / PLACES / PROPS):\n"
            for idx, ing in enumerate(sot_ings, 1):
                name = ing.get("name", f"sot-{idx}")
                arch = ing.get("archetype", "character")
                title = ing.get("title", name)
                ref_text = ing.get("reference_text", "")
                user_content += f"[{idx}] @{name} (SOT Type: {str(arch).upper()}, Title: {title})\n"
                if ref_text:
                    user_content += f"    Unchanging Ground Truth: {ref_text}\n"

        active_fab_directive = ""
        if blank_ings:
            user_content += "\nATTACHED CONTEXTILES OF TRUTH (PHYSICAL BLANKS & SIZING TEMPLATES):\n"
            for idx, ing in enumerate(blank_ings, 1):
                name = ing.get("name", f"blank-{idx}")
                title = ing.get("title", name)
                ref_text = ing.get("reference_text", "")
                mods = ing.get("modifiers") if isinstance(ing.get("modifiers"), dict) else {}
                bspec = ing.get("blank_spec") if isinstance(ing.get("blank_spec"), dict) else (mods.get("blank_spec") if isinstance(mods.get("blank_spec"), dict) else {})
                w_in = bspec.get("width_in") or mods.get("width_in") or 4.0
                h_in = bspec.get("height_in") or mods.get("height_in") or 4.0
                safe_in = bspec.get("safe_margin_in", 0.25)
                shape = bspec.get("shape", "rounded_rect")
                material = bspec.get("material", "natural_wood")
                fab_mode = bspec.get("fabrication_mode") or mods.get("fabrication_mode") or "laser_bw"
                user_content += (
                    f"[{idx}] @{name} (Contextile of Truth Blank: {title})\n"
                    f"    Calibrated Blank Size: {w_in}\" W × {h_in}\" H (Safe Zone Margin: {safe_in}\") | Shape: {shape} | Substrate: {material} | Fabrication Mode: {fab_mode}\n"
                )
                if ref_text:
                    user_content += f"    Blank Specification: {ref_text}\n"
                if "laser" in str(fab_mode).lower():
                    active_fab_directive = "STRICTLY 1-BIT BLACK AND WHITE LASER ENGRAVING BURN ONLY (#000000 black burn lines on #FFFFFF pure white background, woodcut/pyrography line art, zero color gradients, zero gray wash)"
                elif "stencil" in str(fab_mode).lower() or bspec.get("edge_connections"):
                    active_fab_directive = "CUTTABLE STENCIL WITH EDGE CONNECTIONS (bold high-contrast black-and-white cutout shapes with sturdy structural stencil bridges connecting all interior islands to the outer frame so no pieces fall out)"

        if ctx_ings:
            user_content += "\nACTIVE CONTEXTILE TEMPLATES (TEMPLATIZED SETTINGS, SAMPLES & EMBEDDED SOTS):\n"
            for idx, ing in enumerate(ctx_ings, 1):
                name = ing.get("name", f"contextile-{idx}")
                title = ing.get("title", name)
                ref_text = ing.get("reference_text", "")
                mods = ing.get("modifiers") if isinstance(ing.get("modifiers"), dict) else {}
                emb = ing.get("embedded_sot_handles") or mods.get("embedded_sot_handles") or []
                user_content += f"[{idx}] @{name} (Contextile Template: {title})\n"
                if emb:
                    user_content += f"    Embedded Source of Truth Slot(s): {', '.join('@' + str(h).lstrip('@') for h in emb)}\n"
                if ref_text:
                    user_content += f"    Template Specification: {ref_text}\n"
                clean_mods = {k: v for k, v in mods.items() if k not in ("option_toggles", "entity_kind")}
                if clean_mods:
                    user_content += f"    Template Modifiers: {json.dumps(clean_mods)}\n"
                if "stencil" in name.lower():
                    active_fab_directive = "CUTTABLE STENCIL WITH EDGE CONNECTIONS (bold high-contrast black-and-white cutout shapes with sturdy structural stencil bridges connecting all interior islands to the outer frame so no pieces fall out)"
                elif "laser" in name.lower() and not active_fab_directive:
                    active_fab_directive = "STRICTLY 1-BIT BLACK AND WHITE LASER ENGRAVING BURN ONLY (#000000 black burn lines on #FFFFFF pure white background, woodcut/pyrography line art, zero color gradients, zero gray wash)"

        if enabled_toggles:
            user_content += "\nENABLED CONTEXTILE SPECIFICS / OPTION TOGGLES (MUST BE APPLIED):\n"
            for t in enabled_toggles:
                user_content += f"  - [ENABLED on @{t['contextile']}] {t['label']}: {t['prompt']}\n"
        if disabled_toggles:
            user_content += "\nDISABLED CONTEXTILE OPTION TOGGLES (DO NOT APPLY UNLESS REQUESTED IN DIRECTIVES):\n"
            for t in disabled_toggles:
                user_content += f"  - [OFF on @{t['contextile']}] {t['label']}\n"

        if concepts_list and grid_mode == "multi_concept_grid":
            user_content += f"\nMULTI-CONCEPT GRID CELLS ({grid_rows}x{grid_cols} AS A WHOLE):\n"
            for c_idx, c_item in enumerate(concepts_list[:grid_rows * grid_cols], 1):
                if isinstance(c_item, dict):
                    user_content += f"  - Cell {c_idx} ({c_item.get('label', f'Concept {c_idx}')}): {c_item.get('prompt', '')} [Interaction: {c_item.get('interaction', 'none')}]\n"

        # Extract active dropdown variables (Style, Medium, Lighting, Camera/Lens, Materials, Color Grading, Mood, Fabrication Mode, etc.)
        dropdown_directives = []
        for ing in (ingredients or []):
            if not isinstance(ing, dict):
                continue
            for v in (ing.get("variables") or []):
                if not isinstance(v, dict):
                    continue
                v_type = str(v.get("type") or "").lower()
                v_cat = str(v.get("category_preset") or "").lower()
                v_opts = v.get("options")
                if v_type == "dropdown" or v_cat or (isinstance(v_opts, list) and len(v_opts) > 0):
                    v_label = v.get("label") or v.get("key") or "Variable"
                    v_key = v.get("key") or ""
                    v_val = merged_vars.get(v_key) or v.get("value") or v.get("default_value") or ""
                    if v_val:
                        dropdown_directives.append(f"{v_label}: {v_val}")
                        if "stencil" in str(v_val).lower():
                            active_fab_directive = "CUTTABLE STENCIL WITH EDGE CONNECTIONS (bold high-contrast black-and-white cutout shapes with sturdy structural stencil bridges connecting all interior islands to the outer frame so no pieces fall out)"
                        elif "laser" in str(v_val).lower() and "1-bit" in str(v_val).lower():
                            active_fab_directive = "STRICTLY 1-BIT BLACK AND WHITE LASER ENGRAVING BURN ONLY (#000000 black burn lines on #FFFFFF pure white background, woodcut/pyrography line art, zero color gradients, zero gray wash)"

        if dropdown_directives:
            user_content += "\nSELECTED CONTEXTILE VARIABLE DROPDOWNS (STYLE / MEDIUM / LIGHTING / FABRICATION / ETC. - MUST BE APPLIED):\n"
            for dd in dropdown_directives:
                user_content += f"  - {dd}\n"

        if active_fab_directive:
            user_content += f"\nMANDATORY PHYSICAL FABRICATION CONSTRAINT:\n  - {active_fab_directive}\n"

        if merged_vars:
            user_content += f"\nDYNAMIC TEMPLATE VARIABLES & VALUES (MUST BE INTEGRATED):\n{json.dumps(merged_vars, indent=2)}\n"
        if overrides:
            user_content += f"\nOverrides & Nuances: {json.dumps(overrides)}\n"

        user_parts: List[Dict[str, Any]] = [{"text": user_content}]
        if ref_sheet_img is not None:
            try:
                import io
                sheet_copy = ref_sheet_img.copy()
                sheet_copy.thumbnail((1280, 720))
                buf = io.BytesIO()
                sheet_copy.convert("RGBA").save(buf, format="PNG")
                b64_str = base64.b64encode(buf.getvalue()).decode("utf-8")
                user_parts.append({
                    "inlineData": {
                        "mimeType": "image/png",
                        "data": b64_str
                    }
                })
            except Exception as e:
                print(f"[AssetLabService] synthesize_blend ref_sheet attach notice: {e}")

        messages = [{"role": "user", "parts": user_parts}]
        raw = call_gemini(messages, system_instruction, json_mode=True, timeout=25)

        enabled_prompts_str = "; ".join(t["prompt"] for t in enabled_toggles if t.get("prompt"))
        dropdown_prompts_str = " | ".join(dropdown_directives)

        if raw:
            try:
                clean = raw.strip()
                if clean.startswith("```json"): clean = clean[7:]
                elif clean.startswith("```"): clean = clean[3:]
                if clean.endswith("```"): clean = clean[:-3]
                clean = clean.strip()
                data = json.loads(clean)
                if isinstance(data, dict) and data.get("master_prompt"):
                    if active_fab_directive and active_fab_directive[:24].lower() not in data["master_prompt"].lower():
                        data["master_prompt"] = f"{active_fab_directive} | {data['master_prompt']}"
                    if dropdown_prompts_str and not any(dd.split(":")[-1].strip().lower() in data["master_prompt"].lower() for dd in dropdown_directives[:2]):
                        data["master_prompt"] = f"{data['master_prompt']} | Selected Contextile Dropdowns: {dropdown_prompts_str}"
                    if enabled_prompts_str and enabled_prompts_str.lower() not in data["master_prompt"].lower():
                        data["master_prompt"] = f"{data['master_prompt']} | Enabled Template Specifics: {enabled_prompts_str}"
                    if not data.get("suggested_aspect_ratio"):
                        data["suggested_aspect_ratio"] = default_aspect
                    return data
            except Exception as e:
                print(f"[AssetLabService] Parse synthesis JSON failed: {e}")

        # Intelligent Fallback Recipe Synthesis
        ing_names = [f"@{i.get('name')}" for i in (ingredients or []) if i.get('name')]
        ing_str = " + ".join(ing_names) if ing_names else "SOT + Contextile Fusion"

        subject_ing = next(
            (i for i in sot_ings if i.get("role") in ("subject", "mascot") or i.get("archetype") == "character"),
            sot_ings[0] if sot_ings else None
        )
        subject_name = (
            merged_vars.get("character_name")
            or merged_vars.get("player_name")
            or merged_vars.get("app_title")
            or (subject_ing.get("title") if subject_ing else None)
            or (active_elements[0]["name"] if active_elements else "Geppy")
        )

        if is_card:
            t_name = merged_vars.get("team_name") or "GEPPY'S GALACTIC ALL-STARS"
            p_pos = merged_vars.get("position") or merged_vars.get("role_title") or "CAPTAIN"
            s_text = merged_vars.get("stats") or "STARFLEET PILOT • .342 AVG • 48 HR • SOT ALL-GALAXY"
            c_num = merged_vars.get("card_number") or "#76"
            y_era = merged_vars.get("year_era") or "'76"
            extra_toggle_txt = f" Featured Specifics: {enabled_prompts_str}." if enabled_prompts_str else ""
            extra_dd_txt = f" Style & Medium Dropdowns: {dropdown_prompts_str}." if dropdown_prompts_str else ""

            return {
                "title": f"1970s Vintage Baseball Card: {subject_name}",
                "master_prompt": f"Authentic 1970s Topps-style vintage baseball card featuring {subject_name} of {t_name} ({p_pos}), printed on aged cardboard stock with arched team banner '{t_name}', round star position badge '{p_pos}', lower nameplate '{subject_name}', stats '{s_text}', card {c_num} ({y_era}).{extra_dd_txt}{extra_toggle_txt} {custom_prompt or ''}".strip(),
                "negative_prompt": "modern digital rendering, 3D glossy render, flat vector clipart, blurry, distorted anatomy",
                "color_palette": ["#F5EDE0 (Cardboard Buff)", "#DC2626 (Retro Red)", "#F59E0B (Topps Gold)", "#1E3A8A (Vintage Navy)"],
                "composition_blueprint": f"Authentic 1970s trading card layout: arched team banner '{t_name}', portrait window '{subject_name}', star position badge '{p_pos}', stats '{s_text}', card {c_num}.{extra_dd_txt}{extra_toggle_txt}",
                "style_fusion_notes": f"Applied @70s-baseball-card Contextile template to {subject_name} ({ing_str}).",
                "suggested_aspect_ratio": "2.5:3.5"
            }

        base_parts = []
        if active_fab_directive:
            base_parts.append(f"[{active_fab_directive}]")
        for el in active_elements:
            base_parts.append(f"[{el['label']}]")
        for ing in sot_ings:
            txt = ing.get("reference_text", "")
            if txt:
                base_parts.append(f"[SOT @{ing.get('name')}: {txt}]")
        for ing in blank_ings:
            txt = ing.get("reference_text", "")
            if txt:
                base_parts.append(f"[CONTEXTILE OF TRUTH BLANK @{ing.get('name')}: {txt}]")
        for ing in ctx_ings:
            txt = ing.get("reference_text", "")
            mods = ing.get("modifiers", {})
            if txt:
                base_parts.append(f"[CONTEXTILE TEMPLATE @{ing.get('name')}: {txt}]")
            if mods:
                clean_m = {k: v for k, v in mods.items() if k not in ("option_toggles", "entity_kind")}
                if clean_m:
                    base_parts.append(f"[TEMPLATE SETTINGS: {json.dumps(clean_m)}]")
        if enabled_prompts_str:
            base_parts.append(f"[ENABLED TEMPLATE SPECIFICS: {enabled_prompts_str}]")
        if merged_vars:
            var_summary = ", ".join(f"{k}='{v}'" for k, v in merged_vars.items())
            base_parts.append(f"[VARIABLES: {var_summary}]")
        if custom_prompt:
            base_parts.append(f"[DIRECTIVE: {custom_prompt}]")

        compiled_prompt = " | ".join(base_parts) if base_parts else f"Flagship fine-tuned 3D visual asset for {subject_name} ({ing_str})"
        if not active_fab_directive:
            compiled_prompt += " | Crisp vector & dimensional rendering, volumetric rim lighting, glassmorphic bevels, high-contrast focal emblem."

        return {
            "title": f"{subject_name} ({ing_str})",
            "master_prompt": compiled_prompt,
            "negative_prompt": "blurry, low resolution, artifacts, distorted geometry, stacked duplicate icons",
            "color_palette": ["#000000 (Laser Burn / Cut)", "#FFFFFF (Blank Surface)"] if active_fab_directive else ["#F59E0B (Amber Gold)", "#06B6D4 (Cyan Visor)", "#6366F1 (Indigo Nebula)", "#0F172A (Obsidian)"],
            "composition_blueprint": f"Optimized for {target_format} ({default_aspect}) featuring {subject_name} with {len(sot_ings)} Source-of-Truth item(s), {len(blank_ings)} Blank Contextile(s) of Truth, and {len(ctx_ings)} Contextile template(s).",
            "style_fusion_notes": f"Harmonized {len(sot_ings)} Source-of-Truth entities, {len(blank_ings)} Contextile(s) of Truth, {len(ctx_ings)} Contextiles, and {len(enabled_toggles)} enabled option toggle(s).",
            "suggested_aspect_ratio": default_aspect
        }

    @classmethod
    def _extract_reference_visual_traits(
        cls,
        ref_paths: List[str],
        ref_sheet_img: Optional[Image.Image] = None,
        scene_elements: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        """
        Uses Gemini Vision on the Combined Source-of-Truth Reference Sheet (or individual reference images)
        to extract a forensic, role-aware visual specification of the character, item/prop, logo, and style.
        """
        if not ref_paths and ref_sheet_img is None:
            return ""
        try:
            from gitbridge.services.central_key_service import CentralKeyService
            import io
            role_notes = []
            for el in (scene_elements or []):
                role_notes.append(f"- {el.get('label')}: interaction={el.get('interaction')}, action={el.get('action') or 'standard'}")
            role_str = "\n".join(role_notes)

            parts: List[Dict[str, Any]] = [{
                "text": (
                    "Analyze this Combined Source-of-Truth Reference Sheet (where each panel has a header label above it).\n"
                    f"{('Active Picture Roles:\n' + role_str + '\n') if role_str else ''}"
                    "Describe in 3 ultra-specific, concrete sentences:\n"
                    "1) The exact physical appearance of the REFERENCE CHARACTER / LOGO (species/type, face, helmet/glasses/hat, outfit/suit colors, proportions).\n"
                    "2) The exact appearance of any REFERENCE ITEM/PROP or STAGE and how the character should interact with it.\n"
                    "3) The exact art style, materials, lighting, and color palette from any STYLE/ICON reference (ignoring any unrelated object like a printer inside a style-only reference).\n"
                    "Output plain text only."
                )
            }]
            attached = 0
            if ref_sheet_img is not None:
                im_c = ref_sheet_img.copy()
                im_c.thumbnail((1024, 512))
                buf = io.BytesIO()
                im_c.convert("RGBA").save(buf, format="PNG")
                b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
                parts.append({"inlineData": {"mimeType": "image/png", "data": b64}})
                attached += 1
            else:
                for rpath in (ref_paths or [])[:3]:
                    if not rpath or not os.path.exists(rpath):
                        continue
                    with Image.open(rpath) as im:
                        im.thumbnail((384, 384))
                        buf = io.BytesIO()
                        im.convert("RGBA").save(buf, format="PNG")
                        b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
                    parts.append({"inlineData": {"mimeType": "image/png", "data": b64}})
                    attached += 1
            if attached == 0:
                return ""
            desc = CentralKeyService.call_gemini(
                [{"role": "user", "parts": parts}],
                "You are a forensic visual Source-of-Truth analyzer for AI image synthesis.",
                timeout=14,
                json_mode=False,
                max_output_tokens=320
            )
            return (desc or "").strip()
        except Exception as e:
            print(f"[AssetLabService] _extract_reference_visual_traits notice: {e}")
            return ""

    @classmethod
    def _compose_from_source_of_truth_pictures(
        cls,
        title: str,
        master_prompt: str,
        target_format: str,
        width: int,
        height: int,
        scene_elements: List[Dict[str, Any]],
        color_palette: List[str],
        vars_dict: Dict[str, Any],
        is_hex: bool = False,
        should_cutout: bool = True,
        ai_backdrop_or_prop: Optional[Image.Image] = None,
        grid_mode: str = "single",
        grid_rows: int = 1,
        grid_cols: int = 1,
        concepts_list: Optional[List[Dict[str, Any]]] = None
    ) -> Optional[Image.Image]:
        """
        True Picture-Preserving Source-of-Truth Compositor & Stylizer!
        Takes the ACTUAL Source-of-Truth picture pixels (Character SOT, Logo SOT, Item/Prop SOT,
        Stage/Background SOT, Base Image SOT, Style SOT) and composites them together so that:
        - The user's actual character/mascot/logo picture is preserved as the visual Source of Truth.
        - Multiple pictures (e.g. Character picture + Item/Prop picture + Stage picture, or Base Image + Overlay)
          are combined according to their interaction mode ('holding', 'wearing', 'sitting_on',
          'mascot_printed', 'logo_printed', 'emblem', 'integrated', 'sticker').
        - If a multi-variation or multi-concept grid (2x2 or 3x3) is requested, builds the complete
          cohesive grid sheet where each cell displays its distinct concept/variation!
        """
        from gitbridge.services.output_service import OutputService
        from PIL import ImageEnhance, ImageOps

        if not scene_elements:
            return None

        # Categorize elements by role
        mascot_els = [e for e in scene_elements if e["role"] in ("mascot", "subject")]
        logo_els = [e for e in scene_elements if e["role"] == "logo"]
        icon_els = [e for e in scene_elements if e["role"] == "icon"]
        item_els = [e for e in scene_elements if e["role"] == "item"]
        stage_els = [e for e in scene_elements if e["role"] == "stage"]
        base_els = [e for e in scene_elements if e["role"] == "base_image"]
        style_els = [e for e in scene_elements if e["role"] in ("style_only", "style", "lighting", "materials")]

        # Helper to load and cleanly cut out an element's background
        def _load_cutout(el_dict: Dict[str, Any], do_cut: bool = True) -> Optional[Image.Image]:
            p = el_dict.get("path")
            if not p or not os.path.exists(p):
                return None
            try:
                with Image.open(p) as im:
                    rgba = im.convert("RGBA")
                if not do_cut:
                    return rgba
                # Check if already has transparency
                alpha_extrema = rgba.getchannel("A").getextrema()
                if alpha_extrema and alpha_extrema[0] < 200:
                    return rgba
                return OutputService.remove_background(rgba, tolerance=44, edge_feather=1, sample_corners=True)
            except Exception as e:
                print(f"[AssetLabService] _load_cutout notice: {e}")
                return None

        pal = color_palette or []
        c_accent = _hex_to_rgb(pal[0] if len(pal) > 0 else None, (245, 158, 11))
        c_sec = _hex_to_rgb(pal[1] if len(pal) > 1 else None, (6, 182, 212))
        c_gold = _hex_to_rgb(pal[2] if len(pal) > 2 else None, (251, 191, 36))
        c_dark = _hex_to_rgb(pal[3] if len(pal) > 3 else None, (15, 23, 42))

        # Extract dominant color tint from style reference picture if present
        if style_els:
            try:
                with Image.open(style_els[0]["path"]) as sim:
                    s_small = sim.convert("RGB").resize((16, 16), Image.Resampling.BILINEAR)
                    pixels = list(s_small.getdata())
                    # Find most vibrant pixel in style reference
                    best_px = max(pixels, key=lambda rgb: (max(rgb) - min(rgb)) + (sum(rgb) // 6))
                    if max(best_px) > 60:
                        c_accent = best_px
            except Exception:
                pass

        def _render_single_cell(
            cell_w: int,
            cell_h: int,
            cell_label: str = "",
            cell_prompt: str = "",
            cell_interaction: str = "",
            variation_idx: int = 0
        ) -> Image.Image:
            canvas = Image.new("RGBA", (cell_w, cell_h), (0, 0, 0, 0) if should_cutout else (*c_dark, 255))
            draw = ImageDraw.Draw(canvas)
            cx, cy = cell_w // 2, cell_h // 2
            box_r = int(min(cell_w, cell_h) * 0.44)

            # 1. Base Image or Stage Background layer
            if base_els:
                base_im = _load_cutout(base_els[0], do_cut=False)
                if base_im:
                    base_fit = ImageOps.fit(base_im, (cell_w, cell_h), Image.Resampling.LANCZOS)
                    canvas.paste(base_fit, (0, 0))
            elif stage_els:
                stage_im = _load_cutout(stage_els[0], do_cut=False)
                if stage_im:
                    stage_fit = ImageOps.fit(stage_im, (cell_w, cell_h), Image.Resampling.LANCZOS)
                    canvas.paste(stage_fit, (0, 0))
            elif target_format in ("app_icon", "transparent_png", "avatar") or is_hex:
                # Draw 3D Hexagonal or Squircle Icon Container
                if is_hex:
                    dx = int(box_r * 0.866)
                    dy = box_r // 2
                    pts_outer = [
                        (cx, cy - box_r), (cx + dx, cy - dy), (cx + dx, cy + dy),
                        (cx, cy + box_r), (cx - dx, cy + dy), (cx - dx, cy - dy)
                    ]
                    draw.polygon(pts_outer, fill=(*c_dark, 248), outline=(*c_accent, 255), width=max(4, cell_w // 75))
                    ir = int(box_r * 0.91)
                    idx_h, idy_h = int(ir * 0.866), ir // 2
                    pts_inner = [
                        (cx, cy - ir), (cx + idx_h, cy - idy_h), (cx + idx_h, cy + idy_h),
                        (cx, cy + ir), (cx - idx_h, cy + idy_h), (cx - idx_h, cy - idy_h)
                    ]
                    draw.polygon(pts_inner, outline=(*c_gold, 195), width=max(2, cell_w // 180))
                else:
                    bx0, by0 = cx - box_r, cy - box_r
                    bsz = box_r * 2
                    rx = int(bsz * 0.22)
                    draw.rounded_rectangle(
                        [bx0, by0, bx0 + bsz, by0 + bsz],
                        radius=rx,
                        fill=(*c_dark, 248),
                        outline=(*c_accent, 255),
                        width=max(4, cell_w // 80)
                    )
                    draw.rounded_rectangle(
                        [bx0 + 10, by0 + 10, bx0 + bsz - 10, by0 + bsz - 10],
                        radius=max(6, rx - 8),
                        outline=(*c_gold, 180),
                        width=max(2, cell_w // 200)
                    )

                # Ambient radial glow inside container
                glow_layer = Image.new("RGBA", (cell_w, cell_h), (0, 0, 0, 0))
                g_draw = ImageDraw.Draw(glow_layer)
                glow_col = c_accent if variation_idx % 2 == 0 else c_sec
                for r_step in range(int(box_r * 0.75), 10, -12):
                    alpha = int(55 * (1.0 - r_step / max(1, box_r * 0.75)))
                    g_draw.ellipse([cx - r_step, cy - r_step, cx + r_step, cy + r_step], fill=(*glow_col, alpha))
                canvas = Image.alpha_composite(canvas, glow_layer)

            # 2. If AI generated a contextual prop/scene layer, blend it inside the container behind or alongside the SOT picture
            if ai_backdrop_or_prop is not None and variation_idx == 0:
                try:
                    ai_fit = ai_backdrop_or_prop.copy()
                    target_ai_sz = int(box_r * 1.45)
                    ai_fit.thumbnail((target_ai_sz, target_ai_sz), Image.Resampling.LANCZOS)
                    ax = cx - ai_fit.width // 2
                    ay = cy - ai_fit.height // 2
                    canvas.paste(ai_fit, (ax, ay), ai_fit)
                except Exception:
                    pass

            # 3. Primary Source-of-Truth Picture (Character / Mascot / Logo / Icon)
            primary_el = (
                mascot_els[variation_idx % len(mascot_els)] if mascot_els
                else (logo_els[0] if logo_els else (icon_els[0] if icon_els else None))
            )
            item_el = item_els[variation_idx % len(item_els)] if item_els else None

            eff_interaction = (
                cell_interaction
                or (item_el.get("interaction") if item_el else "")
                or (primary_el.get("interaction") if primary_el else "")
                or "none"
            ).lower()

            # Check if interaction prints Mascot/Logo onto the Item surface
            if item_el and primary_el and eff_interaction in ("mascot_printed", "logo_printed", "branded"):
                item_im = _load_cutout(item_el, do_cut=True)
                prim_im = _load_cutout(primary_el, do_cut=True)
                if item_im:
                    isz = int(box_r * 1.55)
                    item_im.thumbnail((isz, isz), Image.Resampling.LANCZOS)
                    ix = cx - item_im.width // 2
                    iy = cy - item_im.height // 2
                    canvas.paste(item_im, (ix, iy), item_im)
                    if prim_im:
                        psz = int(min(item_im.width, item_im.height) * 0.48)
                        prim_im.thumbnail((psz, psz), Image.Resampling.LANCZOS)
                        px = cx - prim_im.width // 2
                        py = cy - prim_im.height // 2
                        canvas.paste(prim_im, (px, py), prim_im)
            else:
                # Standard or interactive character + prop placement
                if primary_el:
                    prim_im = _load_cutout(primary_el, do_cut=True)
                    if prim_im:
                        # Subtle variation transforms when rendering a Variation Grid (2x2 or 3x3)
                        if grid_mode == "variations_grid" and variation_idx > 0:
                            if variation_idx % 4 == 1:
                                prim_im = ImageOps.mirror(prim_im)
                            elif variation_idx % 4 == 2:
                                prim_im = ImageEnhance.Color(prim_im).enhance(1.25)
                                prim_im = ImageEnhance.Contrast(prim_im).enhance(1.12)
                            elif variation_idx % 4 == 3:
                                prim_im = prim_im.rotate(-6, resample=Image.Resampling.BICUBIC, expand=True)

                        psz = int(box_r * (1.42 if item_el else 1.56))
                        prim_im.thumbnail((psz, psz), Image.Resampling.LANCZOS)
                        # Shift slightly if holding an item on the right
                        offset_x = -int(box_r * 0.14) if (item_el and eff_interaction in ("holding", "none")) else 0
                        offset_y = -int(box_r * 0.12) if (item_el and eff_interaction == "sitting_on") else -int(box_r * 0.04)

                        # If sitting_on, draw the item underneath first
                        if item_el and eff_interaction == "sitting_on":
                            it_im = _load_cutout(item_el, do_cut=True)
                            if it_im:
                                it_sz = int(box_r * 1.1)
                                it_im.thumbnail((it_sz, it_sz), Image.Resampling.LANCZOS)
                                canvas.paste(it_im, (cx - it_im.width // 2, cy + int(box_r * 0.18)), it_im)

                        px = cx - prim_im.width // 2 + offset_x
                        py = cy - prim_im.height // 2 + offset_y
                        canvas.paste(prim_im, (px, py), prim_im)

                # Paste Item/Prop picture if holding, wearing, or alongside
                if item_el and eff_interaction != "sitting_on":
                    it_im = _load_cutout(item_el, do_cut=True)
                    if it_im:
                        if eff_interaction == "wearing":
                            it_sz = int(box_r * 0.85)
                            it_im.thumbnail((it_sz, it_sz), Image.Resampling.LANCZOS)
                            ix = cx - it_im.width // 2
                            iy = cy - int(box_r * 0.55)
                        else:
                            # Holding / interacting on the foreground right
                            it_sz = int(box_r * 0.88)
                            it_im.thumbnail((it_sz, it_sz), Image.Resampling.LANCZOS)
                            ix = cx + int(box_r * 0.12)
                            iy = cy - it_im.height // 2 + int(box_r * 0.1)
                        canvas.paste(it_im, (ix, iy), it_im)

            # 4. If Logo element is also present alongside a Mascot, place a crisp corner/crest logo badge
            if logo_els and mascot_els:
                lg_im = _load_cutout(logo_els[0], do_cut=True)
                if lg_im:
                    lsz = int(box_r * 0.48)
                    lg_im.thumbnail((lsz, lsz), Image.Resampling.LANCZOS)
                    lx = cx + int(box_r * 0.42) - lg_im.width // 2
                    ly = cy - int(box_r * 0.48) - lg_im.height // 2
                    canvas.paste(lg_im, (lx, ly), lg_im)

            # 5. Dynamic Title / Cell Concept Ribbon
            draw = ImageDraw.Draw(canvas)
            ribbon_txt = (
                cell_label
                or str(vars_dict.get("app_title") or vars_dict.get("character_name") or "").strip()
            ).upper()[:24]
            if ribbon_txt:
                ry = cy + int(box_r * 0.62)
                rw_box = int(box_r * 1.48)
                rh_box = max(28, int(cell_h * 0.068))
                draw.rounded_rectangle(
                    [cx - rw_box // 2, ry, cx + rw_box // 2, ry + rh_box],
                    radius=12,
                    fill=(*c_dark, 235),
                    outline=(*c_accent, 255),
                    width=2
                )
                f_rib = cls._load_font(size=max(12, int(rh_box * 0.52)), bold=True)
                tb = draw.textbbox((0, 0), ribbon_txt, font=f_rib)
                tw, th = tb[2] - tb[0], tb[3] - tb[1]
                draw.text((cx - tw // 2, ry + (rh_box - th) // 2 - 2), ribbon_txt, fill=(255, 255, 255, 255), font=f_rib)

            return canvas

        # Check if rendering a Multi-Variation or Multi-Concept Grid Sheet (rows x cols)
        rows = max(1, int(grid_rows or 1))
        cols = max(1, int(grid_cols or 1))
        if grid_mode in ("variations_grid", "multi_concept_grid") and (rows > 1 or cols > 1):
            sheet_img = Image.new("RGBA", (width, height), (0, 0, 0, 0) if should_cutout else (*c_dark, 255))
            cell_w = width // cols
            cell_h = height // rows
            total_cells = rows * cols
            concepts = concepts_list or []

            for idx in range(total_cells):
                r_idx = idx // cols
                c_idx = idx % cols
                c_info = concepts[idx] if idx < len(concepts) and isinstance(concepts[idx], dict) else {}
                c_lbl = c_info.get("label") or (f"Variation {idx + 1}" if grid_mode == "variations_grid" else f"Concept {idx + 1}")
                c_prm = c_info.get("prompt") or master_prompt
                c_int = c_info.get("interaction") or ""
                cell_im = _render_single_cell(
                    cell_w=cell_w,
                    cell_h=cell_h,
                    cell_label=c_lbl,
                    cell_prompt=c_prm,
                    cell_interaction=c_int,
                    variation_idx=idx
                )
                sheet_img.paste(cell_im, (c_idx * cell_w, r_idx * cell_h), cell_im)
            return sheet_img

        return _render_single_cell(width, height, variation_idx=0)

    @classmethod
    def slice_grid_cells(
        cls,
        sheet_img: Image.Image,
        rows: int,
        cols: int,
        asset_id: str,
        concepts_list: Optional[List[Dict[str, Any]]] = None,
        should_cutout: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Slices a Multi-Variation or Multi-Concept Sprite Sheet (rows x cols) into individual
        ready-to-use PNG assets and returns their metadata (`sliced_assets`).
        """
        from gitbridge.services.output_service import OutputService
        rows = max(1, int(rows or 1))
        cols = max(1, int(cols or 1))
        if rows <= 1 and cols <= 1:
            return []

        lab_dir = cls._get_lab_dir()
        sw, sh = sheet_img.size
        cw, ch = sw // cols, sh // rows
        sliced: List[Dict[str, Any]] = []
        concepts = concepts_list or []

        for idx in range(rows * cols):
            r_i = idx // cols
            c_i = idx % cols
            x0, y0 = c_i * cw, r_i * ch
            cell = sheet_img.crop((x0, y0, x0 + cw, y0 + ch)).convert("RGBA")
            if should_cutout:
                try:
                    alpha_ext = cell.getchannel("A").getextrema()
                    if not alpha_ext or alpha_ext[0] > 240:
                        cell = OutputService.remove_background(cell, tolerance=45, edge_feather=1, sample_corners=True)
                except Exception:
                    pass
            cell_512 = cell.resize((512, 512), Image.Resampling.LANCZOS)
            c_fname = f"{asset_id}_cell_{idx + 1}.png"
            c_fpath = os.path.join(lab_dir, c_fname)
            cell_512.save(c_fpath, "PNG")
            c_meta = concepts[idx] if idx < len(concepts) and isinstance(concepts[idx], dict) else {}
            sliced.append({
                "index": idx + 1,
                "label": c_meta.get("label") or f"Asset #{idx + 1}",
                "prompt": c_meta.get("prompt") or "",
                "interaction": c_meta.get("interaction") or "none",
                "filename": c_fname,
                "file_url": f"/api/asset-lab/file/{c_fname}"
            })
        return sliced

    @classmethod
    def _generate_ai_raster_image(
        cls,
        title: str,
        master_prompt: str,
        target_format: str,
        width: int,
        height: int,
        color_palette: List[str],
        composition_blueprint: str,
        ingredients_summary: List[Dict[str, Any]],
        vars_dict: Dict[str, Any],
        ref_paths: List[str],
        use_chroma_cutout: bool = True,
        is_hex: bool = False,
        ref_sheet_img: Optional[Image.Image] = None,
        scene_elements: Optional[List[Dict[str, Any]]] = None,
        grid_mode: str = "single",
        grid_rows: int = 1,
        grid_cols: int = 1,
        concepts_list: Optional[List[Dict[str, Any]]] = None,
        preserve_source_picture: bool = False
    ) -> Tuple[Optional[Image.Image], Optional[Image.Image], Optional[Image.Image]]:
        """
        Generates a real AI raster image anchored to the Source-of-Truth pictures (Combined Reference Sheet)
        and also builds a Picture-Preserving SOT Composite when source pictures are provided.
        Returns (final_image, raw_uncut_image, picture_composite_image).
        """
        import io
        import urllib.parse
        from gitbridge.services.central_key_service import CentralKeyService
        from gitbridge.services.output_service import OutputService

        # 1. Build rich, geppy-s-asset-lab style prompt with explicit Source-of-Truth Picture Roles & Grid Specs
        ing_fragments = []
        for ing in (ingredients_summary or []):
            if isinstance(ing, dict):
                r_txt = (ing.get("reference_text") or "").strip()
                mods = ing.get("modifiers") or {}
                mod_str = ", ".join(f"{k}: {v}" for k, v in mods.items() if v not in (None, ""))
                frag = f"{ing.get('title') or ing.get('name')}: {r_txt}"
                if mod_str:
                    frag += f" ({mod_str})"
                ing_fragments.append(frag.strip())

        sot_element_instructions = []
        for el in (scene_elements or []):
            lbl = el.get("label", "SOURCE OF TRUTH")
            int_rule = cls.SOT_INTERACTION_PROMPTS.get(el.get("interaction", "none"), "")
            act_rule = f"Pose/Action: {el['action']}." if el.get("action") else ""
            sot_element_instructions.append(f"[{lbl} -> {int_rule} {act_rule}]".strip())

        grid_instruction = ""
        rows = max(1, int(grid_rows or 1))
        cols = max(1, int(grid_cols or 1))
        if grid_mode == "variations_grid" and (rows > 1 or cols > 1):
            grid_instruction = (
                f" SPRITE SHEET ({rows}x{cols} GRID OF {rows * cols} VARIATIONS): "
                f"Create a single image arranged in a clean {rows} rows by {cols} columns grid ({rows * cols} distinct variations in total). "
                f"Each cell must show a unique pose, angle, expression, or variation of the concept while strictly maintaining the exact Source-of-Truth character and style. "
                f"Leave clean spacing between cells with NO grid lines or borders."
            )
        elif grid_mode == "multi_concept_grid" and (rows > 1 or cols > 1):
            cell_descs = []
            for idx, c_it in enumerate((concepts_list or [])[:rows * cols], 1):
                if isinstance(c_it, dict):
                    cell_descs.append(f"Cell {idx} ({c_it.get('label', f'Item {idx}')}): {c_it.get('prompt', '')}")
            cells_str = " | ".join(cell_descs) if cell_descs else f"{rows * cols} distinct matching items"
            grid_instruction = (
                f" MULTI-CONCEPT SPRITE SHEET ({rows}x{cols} GRID AS A WHOLE): "
                f"Create a single cohesive image arranged in a {rows} rows by {cols} columns grid containing {rows * cols} distinct concepts: {cells_str}. "
                f"Every item in the grid must share the exact same Source-of-Truth character/logo/art style. Leave clean spacing between items."
            )

        var_fragments = []
        for k, v in (vars_dict or {}).items():
            if v not in (None, ""):
                var_fragments.append(f"{k.replace('_', ' ')}: '{v}'")

        brand_label = (
            vars_dict.get("app_title")
            or vars_dict.get("character_name")
            or vars_dict.get("player_name")
            or ""
        )
        badge_label = vars_dict.get("badge_count") or vars_dict.get("version_tag") or vars_dict.get("glyph_symbol") or ""

        fg_palette = []
        for c_item in (color_palette or []):
            c_low = str(c_item).lower()
            if use_chroma_cutout and any(dk in c_low for dk in ["#0f172a", "#1e293b", "#000000", "obsidian", "deep base", "dark slate"]):
                continue
            fg_palette.append(str(c_item))
        pal_str = ", ".join(fg_palette)

        chroma_name = "pure solid flat White (#FFFFFF) studio"
        chroma_hex = "#FFFFFF"

        container_hint = ""
        if is_hex:
            container_hint = "Framed on a solid dark obsidian and glowing metallic beveled 3D hexagonal badge plate. "
        elif target_format == "app_icon":
            container_hint = "Designed as a cohesive 3D die-cut icon/mascot emblem with dimensional depth and rim lighting. "

        text_hint = ""
        if brand_label or badge_label:
            parts_t = []
            if brand_label:
                parts_t.append(f'emblazoned with the text "{brand_label}"')
            if badge_label:
                parts_t.append(f'featuring badge mark "{badge_label}"')
            text_hint = "Integrate clean stylized typography " + " and ".join(parts_t) + ". "

        bg_lead = (
            f"Isolated centered 3D asset on a {chroma_name} background ({chroma_hex}) with clear margins on all sides: "
            if use_chroma_cutout else ""
        )
        bg_tail = (
            f" CRITICAL ISOLATION FOR CUTOUT: Isolate the entire subject/badge in the center on a clean, solid {chroma_name} background ({chroma_hex}) with no background clutter."
            if use_chroma_cutout else
            " Full-bleed cinematic composition with rich atmospheric lighting and depth."
        )

        combined_ref_lead = ""
        if ref_sheet_img is not None and scene_elements:
            combined_ref_lead = (
                "COMBINED SOURCE-OF-TRUTH REFERENCE SHEET: The attached reference image contains the exact Source-of-Truth picture(s) side-by-side with bold role headers above each panel. "
                "You MUST use the actual pictured CHARACTER/LOGO/ITEM as the strict visual Source of Truth and combine them as instructed: "
                + " ".join(sot_element_instructions) + ". "
            )

        full_ai_prompt = (
            f"{bg_lead}{combined_ref_lead}Masterpiece 3D digital render of {title}: {master_prompt}. "
            f"{grid_instruction} "
            f"{container_hint}"
            f"{('Style & Contextiles: ' + ' | '.join(ing_fragments) + '. ') if ing_fragments else ''}"
            f"{('Integrated Attributes: ' + ', '.join(var_fragments) + '. ') if var_fragments else ''}"
            f"{text_hint}"
            f"{('Subject Accent Colors: ' + pal_str + '. ') if pal_str else ''}"
            f"{bg_tail}"
        ).strip()

        raw_ai_img: Optional[Image.Image] = None

        # 2. Tier 1: Try Google Gemini Multimodal Image Models with the Combined Reference Sheet + individual SOT pictures!
        api_key = CentralKeyService.get_api_key()
        if api_key:
            valid_ratios = {"1:1": "1:1", "16:9": "16:9", "9:16": "9:16", "4:3": "4:3", "3:4": "3:4"}
            aspect_str = "16:9" if width > height * 1.2 else ("9:16" if height > width * 1.2 else "1:1")
            api_aspect = valid_ratios.get(aspect_str, "1:1")

            gem_parts: List[Dict[str, Any]] = []
            # Attach the Combined Labeled Reference Sheet first (exact geppy-s-asset-lab pattern!)
            if ref_sheet_img is not None:
                try:
                    sheet_c = ref_sheet_img.copy()
                    sheet_c.thumbnail((1280, 720))
                    buf = io.BytesIO()
                    sheet_c.convert("RGBA").save(buf, format="PNG")
                    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
                    gem_parts.append({"inlineData": {"mimeType": "image/png", "data": b64}})
                except Exception:
                    pass
            else:
                for rpath in (ref_paths or [])[:3]:
                    if rpath and os.path.exists(rpath):
                        try:
                            with Image.open(rpath) as rim:
                                rim.thumbnail((512, 512))
                                buf = io.BytesIO()
                                rim.convert("RGBA").save(buf, format="PNG")
                                b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
                            gem_parts.append({"inlineData": {"mimeType": "image/png", "data": b64}})
                        except Exception:
                            pass
            gem_parts.append({"text": full_ai_prompt})

            for img_model in ["gemini-2.5-flash-image", "gemini-3.1-flash-image-preview", "gemini-3-pro-image-preview"]:
                try:
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/{img_model}:generateContent?key={api_key}"
                    res = requests.post(
                        url,
                        headers={"Content-Type": "application/json", "User-Agent": "aistudio-build"},
                        json={
                            "contents": [{"parts": gem_parts}],
                            "generationConfig": {"imageConfig": {"aspectRatio": api_aspect}}
                        },
                        timeout=18
                    )
                    if res.status_code == 200:
                        cands = res.json().get("candidates", [])
                        if cands:
                            for p in cands[0].get("content", {}).get("parts", []):
                                inl = p.get("inlineData")
                                if inl and inl.get("data"):
                                    img_bytes = base64.b64decode(inl["data"])
                                    raw_ai_img = Image.open(io.BytesIO(img_bytes)).convert("RGBA")
                                    print(f"[AssetLabService] Generated Multimodal SOT image via {img_model}!")
                                    break
                    if raw_ai_img is not None:
                        break
                    elif res.status_code == 429:
                        break
                except Exception as e:
                    print(f"[AssetLabService] Gemini image model {img_model} notice: {e}")

        # 3. Tier 2: Multi-Space FLUX.1 / SD3.5 AI Image Generation (guided by Gemini Vision forensic analysis of the Combined Reference Sheet)
        if raw_ai_img is None:
            ref_traits = cls._extract_reference_visual_traits(
                ref_paths=ref_paths,
                ref_sheet_img=ref_sheet_img,
                scene_elements=scene_elements
            )
            flux_prompt = full_ai_prompt
            if ref_traits:
                flux_prompt = (
                    f"{bg_lead}{title}: {master_prompt}. "
                    f"Exact Source-of-Truth Visual Specification: {ref_traits}. "
                    f"{grid_instruction} {container_hint}{text_hint}{bg_tail}"
                )
            if len(flux_prompt) > 1350:
                flux_prompt = flux_prompt[:1150] + bg_tail

            flux_w = min(1024, max(512, (width // 64) * 64))
            flux_h = min(1024, max(512, (height // 64) * 64))
            seed_val = int(time.time() * 1000) % 2147483647

            gradio_providers = [
                (
                    "https://black-forest-labs-flux-1-schnell.hf.space",
                    "/gradio_api/call/infer",
                    [flux_prompt, seed_val, False, flux_w, flux_h, 4]
                ),
                (
                    "https://multimodalart-flux-1-merged.hf.space",
                    "/gradio_api/call/infer",
                    [flux_prompt, seed_val, False, flux_w, flux_h, 3.5, 4]
                ),
                (
                    "https://KingNish-Realtime-Flux.hf.space",
                    "/gradio_api/call/generate_image",
                    [flux_prompt, seed_val, flux_w, flux_h]
                ),
                (
                    "https://stabilityai-stable-diffusion-3-5-large-turbo.hf.space",
                    "/gradio_api/call/infer",
                    [flux_prompt, "floor shadow, gradient background, blurry, watermark", seed_val, False, flux_w, flux_h, 0.0, 4]
                )
            ]

            for space_host, endpoint_path, data_args in gradio_providers:
                try:
                    call_url = f"{space_host}{endpoint_path}"
                    c_res = requests.post(call_url, json={"data": data_args}, timeout=12)
                    if c_res.status_code == 200:
                        ev_id = c_res.json().get("event_id")
                        if ev_id:
                            s_res = requests.get(f"{call_url}/{ev_id}", timeout=32)
                            if s_res.status_code == 200 and "event: complete" in s_res.text:
                                for line in s_res.text.splitlines():
                                    if line.startswith("data: "):
                                        data_arr = json.loads(line[6:])
                                        if isinstance(data_arr, list) and len(data_arr) > 0:
                                            first_item = data_arr[0]
                                            file_url = None
                                            if isinstance(first_item, dict):
                                                file_url = first_item.get("url")
                                                if not file_url and first_item.get("path"):
                                                    file_url = f"{space_host}/gradio_api/file={first_item['path']}"
                                            if file_url:
                                                img_r = requests.get(file_url, timeout=15)
                                                if img_r.status_code == 200 and len(img_r.content) > 1000:
                                                    raw_ai_img = Image.open(io.BytesIO(img_r.content)).convert("RGBA")
                                                    print(f"[AssetLabService] Generated AI raster image via {space_host}!")
                                                    break
                    if raw_ai_img is not None:
                        break
                except Exception as e:
                    print(f"[AssetLabService] Flux space {space_host} notice: {e}")

        # 4. Tier 3: Pollinations AI Raster Fallback
        if raw_ai_img is None:
            try:
                short_core = f"{title}, {master_prompt}"[:340]
                short_prompt = (
                    f"Isolated centered 3D asset on a {chroma_name} chroma screen background ({chroma_hex}), no floor shadow: "
                    f"{short_core}. Solid flat {chroma_hex} background."
                    if use_chroma_cutout else short_core
                )
                encoded = urllib.parse.quote(short_prompt)
                p_url = f"https://image.pollinations.ai/prompt/{encoded}?width={min(1024, width)}&height={min(1024, height)}&nologo=true&seed={int(time.time()) % 100000}"
                p_res = requests.get(p_url, timeout=22, headers={"User-Agent": "Mozilla/5.0"})
                if p_res.status_code == 200 and len(p_res.content) > 4000:
                    im_p = Image.open(io.BytesIO(p_res.content)).convert("RGBA")
                    pw_i, ph_i = im_p.size
                    if ph_i >= 512:
                        im_p = im_p.crop((0, 0, pw_i, ph_i - 42)).resize((pw_i, ph_i), Image.Resampling.LANCZOS)
                    raw_ai_img = im_p
                    print("[AssetLabService] Generated AI raster image via Pollinations fallback!")
            except Exception as e:
                print(f"[AssetLabService] Pollinations AI raster fallback notice: {e}")

        cutout_ai_img: Optional[Image.Image] = None
        if raw_ai_img is not None:
            if raw_ai_img.size != (width, height):
                raw_ai_img = raw_ai_img.resize((width, height), Image.Resampling.LANCZOS)
            if use_chroma_cutout:
                try:
                    cutout_ai_img = OutputService.remove_background(
                        raw_ai_img,
                        tolerance=48,
                        edge_feather=1,
                        sample_corners=True
                    )
                except Exception as e:
                    print(f"[AssetLabService] Post-generation cutout notice: {e}")
                    cutout_ai_img = raw_ai_img
            else:
                cutout_ai_img = raw_ai_img

        # 5. Build the True Picture-Preserving SOT Composite whenever actual SOT Character/Logo/Item/Stage pictures are present!
        sot_picture_composite: Optional[Image.Image] = None
        has_identity_pictures = any(
            e.get("role") in ("mascot", "subject", "logo", "item", "base_image", "stage")
            for e in (scene_elements or [])
        )
        if has_identity_pictures:
            try:
                sot_picture_composite = cls._compose_from_source_of_truth_pictures(
                    title=title,
                    master_prompt=master_prompt,
                    target_format=target_format,
                    width=width,
                    height=height,
                    scene_elements=scene_elements,
                    color_palette=color_palette,
                    vars_dict=vars_dict,
                    is_hex=is_hex,
                    should_cutout=use_chroma_cutout,
                    ai_backdrop_or_prop=cutout_ai_img,
                    grid_mode=grid_mode,
                    grid_rows=grid_rows,
                    grid_cols=grid_cols,
                    concepts_list=concepts_list
                )
            except Exception as e:
                print(f"[AssetLabService] _compose_from_source_of_truth_pictures notice: {e}")

        # If preserve_source_picture is True (or if AI raster failed), promote the Picture-Preserving SOT Composite to primary!
        if preserve_source_picture and sot_picture_composite is not None:
            return sot_picture_composite, (raw_ai_img or sot_picture_composite), sot_picture_composite

        if cutout_ai_img is not None:
            return cutout_ai_img, raw_ai_img, sot_picture_composite

        if sot_picture_composite is not None:
            return sot_picture_composite, sot_picture_composite, sot_picture_composite

        return None, None, None

    @classmethod
    def _synthesize_ai_svg_artwork(
        cls,
        title: str,
        master_prompt: str,
        target_format: str,
        width: int,
        height: int,
        color_palette: List[str],
        composition_blueprint: str,
        ingredients_summary: List[Dict[str, Any]],
        vars_dict: Dict[str, Any],
        has_subject_photo: bool,
        is_transparent: bool,
        is_hex: bool,
        ref_paths: List[str]
    ) -> Optional[str]:
        """
        Ask Gemini to author a bespoke, richly detailed, multi-layered SVG illustration
        that integrates ALL user prompts, SOT contextiles, modifiers, color palettes,
        and dynamic variables.
        """
        from gitbridge.services.central_key_service import CentralKeyService

        ing_lines = []
        for ing in (ingredients_summary or []):
            if isinstance(ing, dict):
                ing_lines.append(
                    f"- @{ing.get('name', 'contextile')} (role={ing.get('role', 'style')}, archetype={ing.get('archetype', 'general')}): "
                    f"{ing.get('reference_text', '')} | modifiers={json.dumps(ing.get('modifiers', {}))}"
                )
        ing_block = "\n".join(ing_lines) if ing_lines else "None specified"
        vars_block = json.dumps(vars_dict, indent=2) if vars_dict else "{}"
        pal_block = ", ".join(color_palette or ["#F59E0B", "#06B6D4", "#6366F1", "#0F172A"])

        photo_instruction = ""
        if has_subject_photo:
            cx, cy = width // 2, int(height * 0.46)
            r_med = int(min(width, height) * 0.27)
            x0, y0 = cx - r_med, cy - r_med
            sz = r_med * 2
            photo_instruction = f"""
CRITICAL SUBJECT PORTRAIT PHOTO INTEGRATION:
A real photograph of the Subject is provided! You MUST embed it inside the SVG as the central focal portrait using the exact placeholder `{{{{SUBJECT_IMAGE_DATA_URI}}}}`:
1. In `<defs>`, define a `<clipPath id="subject_clip">` (either a circle `<circle cx="{cx}" cy="{cy}" r="{r_med}"/>` or a pointy-top hexagon centered at ({cx},{cy}) with radius {r_med}).
2. In the midground/subject layer, include:
   `<image href="{{{{SUBJECT_IMAGE_DATA_URI}}}}" x="{x0}" y="{y0}" width="{sz}" height="{sz}" preserveAspectRatio="xMidYMid slice" clip-path="url(#subject_clip)"/>`
3. Draw an illuminated metallic/neon rim border around the clip shape, plus thematic foreground elements (such as glowing visor HUD overlays, cosmic energy rings, shoulder pauldrons, or variable badges) framing the portrait without obscuring the face!
"""
        else:
            photo_instruction = """
CRITICAL BESPOKE ILLUSTRATION REQUIREMENT:
Draw a rich, custom, multi-layered vector illustration of the specific Subject, Character, Creature, Object, or Emblem described in the Master Prompt and Contextiles!
- Do NOT draw a generic circle-and-diamond placeholder.
- Use at least 15-30 detailed SVG elements (`<path>`, `<polygon>`, `<circle>`, `<rect>`, `<g>`, `<linearGradient>`, `<radialGradient>`, `<filter>`) to depict the exact subject, costume/armor/visor, tools/weapons/wings/circuits, lighting effects, and atmospheric details requested by the user.
"""

        system_instruction = """You are an elite SVG Vector Artist, Iconographer, and Visual Synthesizer.
Output ONLY raw, valid, self-contained `<svg ...>...</svg>` code. No markdown explanation, no prose.
Every `<svg>` tag MUST have `xmlns="http://www.w3.org/2000/svg"` and the exact requested `viewBox` and `width`/`height`.
Ensure all XML tags and attributes are properly closed and escaped (use `&amp;` instead of raw `&` in text)."""

        prompt = f"""Create a breathtaking, bespoke SVG visual asset with exact dimensions `viewBox="0 0 {width} {height}" width="{width}" height="{height}"`.

ASSET SPECIFICATIONS:
- Title: {title}
- Target Format: {target_format}
- Transparent Outer Background: {is_transparent} (If True: do NOT draw a full-bleed background `<rect>`; keep the outer canvas transparent outside the main icon/container silhouette!)
- Hexagonal Container Requested: {is_hex} (If True: use a bold 6-sided pointy-top hexagonal outer container centered at ({width//2}, {height//2}) with metallic bevels and glowing rim).
- Color Palette: {pal_block}
- Master Prompt / User Directive:
{master_prompt}
- Composition Blueprint:
{composition_blueprint}
- Active SOT Contextiles:
{ing_block}
- Dynamic Template Variables (render non-empty values as stylish integrated HUD/emblem badges, ribbons, or typography where appropriate):
{vars_block}
{photo_instruction}

DESIGN REQUIREMENTS:
1. Rich `<defs>` section with multiple `<linearGradient>`, `<radialGradient>`, and `<filter>` drop-shadow / glow definitions matching the Color Palette.
2. Container / Backdrop Layer:
   - If `target_format` is `app_icon` or `transparent_png` or `avatar`: frame the composition inside a masterwork 3D {("pointy-top Hexagon" if is_hex else "Apple-style Squircle (`rx='180'` on 1024x1024)")} with deep gradient fill, inner ambient nebula/grid texture, specular glass reflection, and double metallic/neon rim border.
   - If `target_format` is `banner_hero`, `social_story`, or `ui_component`: create a full-canvas layered scene with atmospheric lighting, depth grid/particles, and glassmorphic framing.
3. Central Subject & Thematic Details:
   - Depict the exact subject, action, props, and mood from `Master Prompt` and `Active SOT Contextiles`.
4. Dynamic Variable Badges / Typography:
   - If `Dynamic Template Variables` includes values like `app_title`, `character_name`, `role_title`, `glyph_symbol`, `badge_count`, `version_tag`, `power_level`, or `special_gear`, incorporate them cleanly into the artwork (e.g., a bottom nameplate ribbon, corner notification/version pill badge, or central monogram) using crisp `font-family="Segoe UI, Arial, sans-serif" font-weight="bold"`.

Return ONLY the `<svg viewBox="0 0 {width} {height}" width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">...</svg>` code."""

        user_parts: List[Dict[str, Any]] = [{"text": prompt}]
        for rpath in (ref_paths or [])[:2]:
            try:
                with Image.open(rpath) as r_im:
                    r_im.thumbnail((512, 512))
                    import io
                    buf = io.BytesIO()
                    r_im.convert("RGBA").save(buf, format="PNG")
                    b64_str = base64.b64encode(buf.getvalue()).decode("utf-8")
                user_parts.append({
                    "inlineData": {
                        "mimeType": "image/png",
                        "data": b64_str
                    }
                })
            except Exception as e:
                print(f"[AssetLabService] SVG synthesis attach ref notice: {e}")

        raw_svg = CentralKeyService.call_gemini(
            [{"role": "user", "parts": user_parts}],
            system_instruction,
            timeout=28,
            json_mode=False,
            max_output_tokens=8192
        )
        if not raw_svg:
            return None

        clean_svg = raw_svg.strip()
        if "```svg" in clean_svg:
            clean_svg = clean_svg.split("```svg", 1)[1].split("```", 1)[0].strip()
        elif "```xml" in clean_svg:
            clean_svg = clean_svg.split("```xml", 1)[1].split("```", 1)[0].strip()
        elif "```" in clean_svg:
            clean_svg = clean_svg.split("```", 1)[1].split("```", 1)[0].strip()

        start_idx = clean_svg.find("<svg")
        end_idx = clean_svg.rfind("</svg>")
        if start_idx != -1 and end_idx != -1:
            clean_svg = clean_svg[start_idx:end_idx + 6]
            return clean_svg
        return None

    @staticmethod
    def _prepare_subject_photo_data_uri(photo_path: str, size: int = 640) -> Optional[str]:
        """Crop and enhance a subject portrait photo into a clean square PNG data URI for SVG embedding."""
        try:
            import io
            with Image.open(photo_path) as im:
                rgba = im.convert("RGBA")
                rw, rh = rgba.size
                scale = max(size / rw, size / rh)
                nw, nh = max(1, int(rw * scale)), max(1, int(rh * scale))
                resized = rgba.resize((nw, nh), Image.Resampling.LANCZOS)
                cx = nw // 2
                # Slight upper bias for portrait photos so heads/faces are centered nicely
                cy = int(nh * 0.45) if nh > nw * 1.15 else nh // 2
                x0 = max(0, min(nw - size, cx - size // 2))
                y0 = max(0, min(nh - size, cy - size // 2))
                cropped = resized.crop((x0, y0, x0 + size, y0 + size))
                buf = io.BytesIO()
                cropped.save(buf, format="PNG")
                b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
                return f"data:image/png;base64,{b64}"
        except Exception as e:
            print(f"[AssetLabService] _prepare_subject_photo_data_uri error: {e}")
            return None

    @classmethod
    def _render_trading_card(
        cls,
        title: str,
        master_prompt: str,
        ingredients_summary: List[Dict[str, Any]] = None,
        reference_images: List[Any] = None,
        color_palette: List[str] = None,
        variables: Dict[str, Any] = None
    ) -> Image.Image:
        """
        Renders an authentic, ultra-crisp 1970s Topps-style vintage baseball trading card
        with scalable TrueType typography, dynamic variable slots, and proper subject portrait priority.
        """
        width, height = (750, 1050)
        img = Image.new("RGBA", (width, height), (245, 237, 224, 255))
        draw = ImageDraw.Draw(img)

        vars_dict = cls._merge_variables(variables, ingredients_summary)

        def _get_v(keys: List[str], default_val: str = "") -> str:
            for key in keys:
                for k, v in vars_dict.items():
                    if k.lower() == key.lower() and v not in (None, ""):
                        return str(v)
            return default_val

        team_text = _get_v(["team_name", "app_title", "brand_name"], "GEPPY'S GALACTIC ALL-STARS").upper()
        star_txt = _get_v(["position", "role_title", "badge_count"], "CAPTAIN").upper()
        if len(star_txt) > 10:
            star_txt = star_txt[:10]

        disp_name = _get_v(["player_name", "character_name"], "").upper()
        if not disp_name:
            subject_ing = next(
                (i for i in (ingredients_summary or []) if isinstance(i, dict) and (i.get("role") == "subject" or i.get("archetype") == "character")),
                None
            )
            if subject_ing and subject_ing.get("title"):
                disp_name = str(subject_ing.get("title")).upper()
            else:
                disp_name = title.upper()
                if ":" in disp_name:
                    disp_name = disp_name.split(":")[-1].strip()
        if len(disp_name) > 26:
            disp_name = disp_name[:24] + "..."

        # Build stats / subtitle line from any provided stats or character variables
        custom_stats = _get_v(["stats"], "").upper()
        if not custom_stats:
            stat_tokens = []
            if _get_v(["role_title"]): stat_tokens.append(_get_v(["role_title"]).upper())
            if _get_v(["power_level"]): stat_tokens.append(f"PWR {_get_v(['power_level']).upper()}")
            if _get_v(["special_gear"]): stat_tokens.append(_get_v(["special_gear"]).upper())
            if _get_v(["batting_avg"]): stat_tokens.append(f"{_get_v(['batting_avg'])} AVG")
            if _get_v(["home_runs"]): stat_tokens.append(f"{_get_v(['home_runs'])} HR")
            if _get_v(["rbi"]): stat_tokens.append(f"{_get_v(['rbi'])} RBI")
            if _get_v(["era"]): stat_tokens.append(f"{_get_v(['era'])} ERA")
            if _get_v(["strikeouts"]): stat_tokens.append(f"{_get_v(['strikeouts'])} SO")
            custom_stats = "  |  ".join(stat_tokens) if stat_tokens else "COMMANDER  |  STARFLEET PILOT  |  SOT ALL-GALAXY"
        else:
            custom_stats = custom_stats.replace("•", "|")

        pos_str = custom_stats[:48]
        num_str = _get_v(["card_number", "version_tag"], "#76")
        year_str = _get_v(["year_era"], "'76")
        foot_str = f"{year_str} VINTAGE SOT TRADING CARD  |  TOPPS HERITAGE SERIES"

        # Dynamic accent colors from palette if provided
        pal = color_palette or []
        c_banner = _hex_to_rgb(pal[1] if len(pal) > 1 else None, (185, 28, 28))
        c_gold = _hex_to_rgb(pal[2] if len(pal) > 2 else None, (245, 158, 11))
        c_navy = _hex_to_rgb(pal[3] if len(pal) > 3 else None, (30, 58, 138))

        # 1. Aged Cardboard Base & Paper Texture
        for y in range(height):
            ratio = y / height
            r = int(246 - 12 * ratio)
            g = int(238 - 14 * ratio)
            b = int(224 - 18 * ratio)
            draw.line([(0, y), (width, y)], fill=(r, g, b, 255))

        grain = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        g_draw = ImageDraw.Draw(grain)
        for i in range(0, width, 5):
            for j in range(0, height, 5):
                if (i * 17 + j * 31) % 23 == 0:
                    g_draw.point((i, j), fill=(100, 80, 50, 28))
        img = Image.alpha_composite(img, grain)
        draw = ImageDraw.Draw(img)

        # 2. Outer Card Margin & Double Border Lines
        pad = 26
        draw.rounded_rectangle([pad, pad, width - pad, height - pad], radius=18, outline=(30, 41, 59, 235), width=5)
        draw.rounded_rectangle([pad + 7, pad + 7, width - pad - 7, height - pad - 7], radius=13, outline=(*c_gold, 190), width=2)

        # 3. Top Team Banner (1970s Pennant Header)
        banner_y0 = pad + 18
        banner_y1 = banner_y0 + 82
        draw.rounded_rectangle([pad + 18, banner_y0, width - pad - 18, banner_y1], radius=16, fill=(*c_banner, 255), outline=(*c_gold, 255), width=4)
        draw.rounded_rectangle([pad + 23, banner_y0 + 5, width - pad - 23, banner_y1 - 5], radius=12, outline=(254, 240, 138, 210), width=1)

        team_font_size = 28 if len(team_text) <= 22 else (23 if len(team_text) <= 28 else 19)
        font_team = cls._load_font(size=team_font_size, bold=True)
        t_box = draw.textbbox((0, 0), team_text, font=font_team)
        tw, th = t_box[2] - t_box[0], t_box[3] - t_box[1]
        tx = (width - tw) // 2
        ty = banner_y0 + (82 - th) // 2 - 2
        draw.text((tx + 2, ty + 2), team_text, fill=(15, 23, 42, 190), font=font_team)
        draw.text((tx, ty), team_text, fill=(255, 255, 255, 255), font=font_team)

        # 4. Central Portrait Photo Window
        px0 = pad + 24
        py0 = banner_y1 + 16
        px1 = width - pad - 24
        py1 = height - pad - 144
        pw = px1 - px0
        ph = py1 - py0

        photo_box = Image.new("RGBA", (pw, ph), (15, 23, 42, 255))
        p_draw = ImageDraw.Draw(photo_box)

        # Twilight stadium / cosmic backdrop
        for py in range(ph):
            rat = py / ph
            pr = int(14 + (32 - 14) * rat)
            pg = int(20 + (28 - 20) * rat)
            pb = int(40 + (75 - 40) * rat)
            p_draw.line([(0, py), (pw, py)], fill=(pr, pg, pb, 255))

        for lx in [int(pw * 0.2), int(pw * 0.8)]:
            for lr in range(180, 0, -20):
                alpha = int(45 * (1.0 - lr / 180))
                p_draw.ellipse([lx - lr, -30 - lr, lx + lr, -30 + lr], fill=(253, 224, 71, alpha))

        # Check for a genuine Subject Portrait Photo (excluding Contextile sample covers like 1970s-cover.png!)
        raw_ref_urls = [r.get("url") if isinstance(r, dict) else r for r in (reference_images or []) if r]
        ref_info = cls._classify_and_resolve_references(ingredients_summary, raw_ref_urls)
        toggle_info = cls._extract_option_toggles_summary(ingredients_summary)
        enabled_toggles = toggle_info["enabled"]
        toggle_prompt_suffix = "; ".join(t["prompt"] for t in enabled_toggles if t.get("prompt"))
        has_mustache_toggle = any(
            "mustache" in (t.get("id", "") + " " + t.get("label", "") + " " + t.get("prompt", "")).lower()
            for t in enabled_toggles
        ) or ("mustache" in (master_prompt or "").lower())
        has_portrait_modifier_toggle = has_mustache_toggle or any(
            any(k in (t.get("id", "") + " " + t.get("label", "") + " " + t.get("prompt", "")).lower() for k in ["aviator", "sunglasses", "glasses", "hat", "helmet", "beard", "mullet"])
            for t in enabled_toggles
        )
        composited = False

        # If a portrait-modifying Contextile toggle (e.g. funny 1970s handlebar mustache) is active, try AI portrait synthesis first with the SOT subject photo as reference
        if has_portrait_modifier_toggle:
            ai_cutout, _, _ = cls._generate_ai_raster_image(
                title=disp_name,
                master_prompt=f"Heroic waist-up 1970s portrait of {disp_name} ({star_txt}) for {team_text}. REQUIRED SPECIFICS: {toggle_prompt_suffix}. {master_prompt}",
                target_format="card_portrait",
                width=pw,
                height=ph,
                color_palette=color_palette or ["#F59E0B", "#06B6D4", "#DC2626", "#0F172A"],
                composition_blueprint=f"Centered heroic character portrait of {disp_name} ({star_txt}) for {team_text}. {toggle_prompt_suffix}",
                ingredients_summary=ingredients_summary,
                vars_dict=vars_dict,
                ref_paths=ref_info["all_paths"],
                use_chroma_cutout=True,
                is_hex=False
            )
            if ai_cutout is not None:
                photo_box = Image.alpha_composite(photo_box, ai_cutout.convert("RGBA"))
                composited = True

        if not composited:
            for local_path in ref_info["subject_paths"]:
                if os.path.exists(local_path):
                    try:
                        ref_img = Image.open(local_path).convert("RGBA")
                        rw, rh = ref_img.size
                        scale = max(pw / rw, ph / rh)
                        nw, nh = max(1, int(rw * scale)), max(1, int(rh * scale))
                        ref_scaled = ref_img.resize((nw, nh), Image.Resampling.LANCZOS)
                        cx = nw // 2
                        cy = int(nh * 0.44) if nh > ph * 1.1 else nh // 2
                        x0 = max(0, min(nw - pw, cx - pw // 2))
                        y0 = max(0, min(nh - ph, cy - ph // 2))
                        ref_crop = ref_scaled.crop((x0, y0, x0 + pw, y0 + ph))

                        # Subtle warm 1970s Kodachrome film wash
                        tint = Image.new("RGBA", (pw, ph), (254, 240, 138, 18))
                        ref_crop = Image.alpha_composite(ref_crop, tint)
                        photo_box.paste(ref_crop, (0, 0), ref_crop)
                        composited = True
                        break
                    except Exception as e:
                        print(f"[_render_trading_card] composite subject image failed: {e}")

        if not composited:
            # Generate AI raster character portrait & cut out onto the trading card backdrop
            ai_cutout, _, _ = cls._generate_ai_raster_image(
                title=disp_name,
                master_prompt=f"Heroic waist-up portrait of {disp_name} ({star_txt}) for {team_text}: {master_prompt} {toggle_prompt_suffix}".strip(),
                target_format="card_portrait",
                width=pw,
                height=ph,
                color_palette=color_palette or ["#F59E0B", "#06B6D4", "#DC2626", "#0F172A"],
                composition_blueprint=f"Centered heroic character portrait of {disp_name} ({star_txt}) for {team_text}. {toggle_prompt_suffix}".strip(),
                ingredients_summary=ingredients_summary,
                vars_dict=vars_dict,
                ref_paths=ref_info["all_paths"],
                use_chroma_cutout=True,
                is_hex=False
            )
            if ai_cutout is not None:
                photo_box = Image.alpha_composite(photo_box, ai_cutout.convert("RGBA"))
                composited = True

        if not composited:
            # Synthesize bespoke AI SVG portrait illustration for the card window if offline
            svg_portrait = cls._synthesize_ai_svg_artwork(
                title=disp_name,
                master_prompt=f"Central character portrait for a 1970s trading card: {master_prompt}",
                target_format="card_portrait",
                width=pw,
                height=ph,
                color_palette=color_palette or ["#F59E0B", "#06B6D4", "#DC2626", "#0F172A"],
                composition_blueprint=f"Centered heroic character portrait of {disp_name} ({star_txt}) for {team_text}.",
                ingredients_summary=ingredients_summary,
                vars_dict=vars_dict,
                has_subject_photo=False,
                is_transparent=False,
                is_hex=False,
                ref_paths=ref_info["all_paths"]
            )
            if svg_portrait:
                try:
                    import resvg_py
                    import io
                    png_bytes = resvg_py.svg_to_bytes(svg_portrait, width=pw, height=ph)
                    svg_im = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
                    photo_box = Image.alpha_composite(photo_box, svg_im)
                    composited = True
                except Exception as e:
                    print(f"[_render_trading_card] resvg portrait render notice: {e}")

        if not composited:
            # High-detail fallback commander illustration
            p_draw = ImageDraw.Draw(photo_box)
            cx, cy = pw // 2, int(ph * 0.48)
            for r_step in range(160, 0, -16):
                p_draw.ellipse([cx - r_step, cy - r_step, cx + r_step, cy + r_step], fill=(99, 102, 241, int(48 * (1.0 - r_step / 160))))
            p_draw.polygon([(cx - 170, ph), (cx - 95, cy + 45), (cx + 95, cy + 45), (cx + 170, ph)], fill=(15, 23, 42, 255), outline=(*c_gold, 255), width=4)
            p_draw.ellipse([cx - 85, cy - 115, cx + 85, cy + 45], fill=(30, 41, 59, 255), outline=(*c_gold, 240), width=4)
            p_draw.rounded_rectangle([cx - 56, cy - 72, cx + 56, cy - 18], radius=16, fill=(6, 182, 212, 255), outline=(255, 255, 255, 240), width=3)

        img.paste(photo_box, (px0, py0))
        draw = ImageDraw.Draw(img)
        draw.rectangle([px0, py0, px1, py1], outline=(15, 23, 42, 255), width=4)
        draw.rectangle([px0 + 4, py0 + 4, px1 - 4, py1 - 4], outline=(*c_gold, 230), width=2)

        # Star Position Badge Overlapping Upper-Right Corner of Portrait Window
        star_r = 46
        scx = px1 - 54
        scy = py0 + 54
        draw.ellipse([scx - star_r + 3, scy - star_r + 4, scx + star_r + 3, scy + star_r + 4], fill=(0, 0, 0, 140))
        draw.ellipse([scx - star_r, scy - star_r, scx + star_r, scy + star_r], fill=(*c_gold, 255), outline=(*c_banner, 255), width=4)
        draw.ellipse([scx - star_r + 5, scy - star_r + 5, scx + star_r - 5, scy + star_r - 5], outline=(255, 255, 255, 200), width=1)
        pos_font_size = 17 if len(star_txt) <= 7 else 13
        font_pos = cls._load_font(size=pos_font_size, bold=True)
        st_box = draw.textbbox((0, 0), star_txt, font=font_pos)
        stw, sth = st_box[2] - st_box[0], st_box[3] - st_box[1]
        draw.text((scx - stw // 2, scy - sth // 2 - 1), star_txt, fill=(15, 23, 42, 255), font=font_pos)

        # 5. Lower Nameplate & Stats Banner
        np_y0 = py1 + 14
        np_y1 = np_y0 + 86
        draw.rounded_rectangle([pad + 18, np_y0, width - pad - 18, np_y1], radius=14, fill=(*c_navy, 255), outline=(*c_gold, 255), width=3)
        draw.rounded_rectangle([pad + 23, np_y0 + 4, width - pad - 23, np_y1 - 4], radius=10, outline=(254, 240, 138, 180), width=1)

        name_font_size = 30 if len(disp_name) <= 18 else (24 if len(disp_name) <= 24 else 20)
        font_name = cls._load_font(size=name_font_size, bold=True)
        nb_box = draw.textbbox((0, 0), disp_name, font=font_name)
        nw_txt = nb_box[2] - nb_box[0]
        nx = (width - nw_txt) // 2
        draw.text((nx + 2, np_y0 + 12), disp_name, fill=(0, 0, 0, 180), font=font_name)
        draw.text((nx, np_y0 + 10), disp_name, fill=(255, 255, 255, 255), font=font_name)

        stats_font_size = 16 if len(pos_str) <= 36 else 13
        font_stats = cls._load_font(size=stats_font_size, bold=True)
        pb_box = draw.textbbox((0, 0), pos_str, font=font_stats)
        pw_txt = pb_box[2] - pb_box[0]
        draw.text(((width - pw_txt) // 2, np_y0 + 52), pos_str, fill=(253, 224, 71, 255), font=font_stats)

        # 6. Vintage Bottom Card Footer Stamp & Card Number
        font_footer = cls._load_font(size=14, bold=True)
        font_num = cls._load_font(size=18, bold=True)
        fb_box = draw.textbbox((0, 0), foot_str, font=font_footer)
        fw_txt = fb_box[2] - fb_box[0]
        draw.text(((width - fw_txt) // 2, height - pad - 30), foot_str, fill=(71, 85, 105, 255), font=font_footer)
        draw.text((pad + 22, height - pad - 33), num_str, fill=(*c_banner, 255), font=font_num)

        return img

    @classmethod
    def _build_rich_fallback_svg(
        cls,
        title: str,
        master_prompt: str,
        target_format: str,
        width: int,
        height: int,
        c_accent: tuple,
        c_secondary: tuple,
        c_gold: tuple,
        c_dark: tuple,
        c_base: tuple,
        is_hex: bool,
        is_transparent: bool,
        vars_dict: Dict[str, Any],
        subject_data_uri: Optional[str] = None
    ) -> str:
        """
        Constructs a rich, variable-aware and prompt-aware SVG when the Gemini API is unreachable.
        Never stacks old icons or ignores variables.
        """
        import html
        hex_accent = f"#{c_accent[0]:02x}{c_accent[1]:02x}{c_accent[2]:02x}"
        hex_sec = f"#{c_secondary[0]:02x}{c_secondary[1]:02x}{c_secondary[2]:02x}"
        hex_gold = f"#{c_gold[0]:02x}{c_gold[1]:02x}{c_gold[2]:02x}"
        hex_dark = f"#{c_dark[0]:02x}{c_dark[1]:02x}{c_dark[2]:02x}"
        hex_base = f"#{c_base[0]:02x}{c_base[1]:02x}{c_base[2]:02x}"

        cx, cy = width // 2, height // 2
        box_r = int(min(width, height) * 0.42)

        bg_svg = "" if is_transparent else f'<rect width="{width}" height="{height}" fill="url(#bg_grad)"/>'

        if is_hex:
            dx = int(box_r * 0.866)
            dy = box_r // 2
            pts_outer = f"{cx},{cy - box_r} {cx + dx},{cy - dy} {cx + dx},{cy + dy} {cx},{cy + box_r} {cx - dx},{cy + dy} {cx - dx},{cy - dy}"
            ir = int(box_r * 0.92)
            idx, idy = int(ir * 0.866), ir // 2
            pts_inner = f"{cx},{cy - ir} {cx + idx},{cy - idy} {cx + idx},{cy + idy} {cx},{cy + ir} {cx - idx},{cy + idy} {cx - idx},{cy - idy}"
            container_svg = f"""
  <polygon points="{pts_outer}" fill="url(#core_grad)" stroke="url(#rim_grad)" stroke-width="14" filter="url(#drop_glow)"/>
  <polygon points="{pts_inner}" fill="none" stroke="{hex_gold}" stroke-width="3" stroke-opacity="0.7"/>"""
        else:
            bx0, by0 = cx - box_r, cy - box_r
            bsz = box_r * 2
            rx = int(bsz * 0.22)
            container_svg = f"""
  <rect x="{bx0}" y="{by0}" width="{bsz}" height="{bsz}" rx="{rx}" fill="url(#core_grad)" stroke="url(#rim_grad)" stroke-width="12" filter="url(#drop_glow)"/>
  <rect x="{bx0 + 14}" y="{by0 + 14}" width="{bsz - 28}" height="{bsz - 28}" rx="{max(8, rx - 10)}" fill="none" stroke="{hex_gold}" stroke-width="2.5" stroke-opacity="0.65"/>"""

        med_r = int(box_r * 0.58)
        if subject_data_uri:
            subject_svg = f"""
  <circle cx="{cx}" cy="{cy - 16}" r="{med_r + 8}" fill="none" stroke="{hex_accent}" stroke-width="6" filter="url(#drop_glow)"/>
  <image href="{subject_data_uri}" x="{cx - med_r}" y="{cy - 16 - med_r}" width="{med_r * 2}" height="{med_r * 2}" preserveAspectRatio="xMidYMid slice" clip-path="url(#subject_clip)"/>
  <circle cx="{cx}" cy="{cy - 16}" r="{med_r}" fill="none" stroke="{hex_gold}" stroke-width="4"/>"""
        else:
            glyph_txt = html.escape(str(vars_dict.get("glyph_symbol") or ""))
            if not glyph_txt:
                t_clean = (vars_dict.get("app_title") or vars_dict.get("character_name") or title or "G").strip()
                words = [w for w in re.split(r"[\s:_-]+", t_clean) if w]
                glyph_txt = (words[0][0] + (words[1][0] if len(words) > 1 else "")).upper()
            subject_svg = f"""
  <circle cx="{cx}" cy="{cy - 16}" r="{med_r}" fill="{hex_dark}" stroke="url(#rim_grad)" stroke-width="6" filter="url(#drop_glow)"/>
  <circle cx="{cx}" cy="{cy - 16}" r="{int(med_r * 0.78)}" fill="none" stroke="{hex_sec}" stroke-width="3" stroke-dasharray="12 8"/>
  <text x="{cx}" y="{cy + 14}" text-anchor="middle" font-family="Segoe UI, Arial, sans-serif" font-size="{int(med_r * 0.85)}" font-weight="900" fill="#FFFFFF" stroke="{hex_accent}" stroke-width="3">{glyph_txt[:3]}</text>"""

        label_main = html.escape(str(
            vars_dict.get("app_title")
            or vars_dict.get("character_name")
            or vars_dict.get("player_name")
            or (title.split(":")[-1].strip() if ":" in title else title)
        ).upper()[:24])
        label_sub = html.escape(str(
            vars_dict.get("role_title")
            or vars_dict.get("special_gear")
            or vars_dict.get("version_tag")
            or vars_dict.get("power_level")
            or ""
        ).upper()[:28])
        badge_val = html.escape(str(vars_dict.get("badge_count") or vars_dict.get("version_tag") or "")[:10])

        ribbon_y = cy + int(box_r * 0.56)
        ribbon_svg = ""
        if label_main:
            ribbon_svg += f"""
  <rect x="{cx - int(box_r * 0.72)}" y="{ribbon_y}" width="{int(box_r * 1.44)}" height="64" rx="18" fill="{hex_dark}" fill-opacity="0.92" stroke="{hex_accent}" stroke-width="3"/>
  <text x="{cx}" y="{ribbon_y + (36 if label_sub else 42)}" text-anchor="middle" font-family="Segoe UI, Arial, sans-serif" font-size="28" font-weight="900" fill="#FFFFFF">{label_main}</text>"""
            if label_sub:
                ribbon_svg += f"""
  <text x="{cx}" y="{ribbon_y + 56}" text-anchor="middle" font-family="Segoe UI, Arial, sans-serif" font-size="16" font-weight="700" fill="{hex_gold}">{label_sub}</text>"""

        badge_svg = ""
        if badge_val:
            bx_badge = cx + int(box_r * 0.62)
            by_badge = cy - int(box_r * 0.62)
            badge_svg = f"""
  <circle cx="{bx_badge}" cy="{by_badge}" r="38" fill="{hex_accent}" stroke="#FFFFFF" stroke-width="4" filter="url(#drop_glow)"/>
  <text x="{bx_badge}" y="{by_badge + 9}" text-anchor="middle" font-family="Segoe UI, Arial, sans-serif" font-size="24" font-weight="900" fill="{hex_dark}">{badge_val}</text>"""

        return f"""<svg viewBox="0 0 {width} {height}" width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="bg_grad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="{hex_base}"/>
      <stop offset="100%" stop-color="{hex_dark}"/>
    </linearGradient>
    <radialGradient id="core_grad" cx="50%" cy="42%" r="65%">
      <stop offset="0%" stop-color="{hex_sec}" stop-opacity="0.35"/>
      <stop offset="45%" stop-color="{hex_dark}" stop-opacity="0.96"/>
      <stop offset="100%" stop-color="{hex_base}" stop-opacity="1"/>
    </radialGradient>
    <linearGradient id="rim_grad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="{hex_accent}"/>
      <stop offset="50%" stop-color="{hex_gold}"/>
      <stop offset="100%" stop-color="{hex_sec}"/>
    </linearGradient>
    <filter id="drop_glow" x="-20%" y="-20%" width="140%" height="140%">
      <feDropShadow dx="0" dy="12" stdDeviation="18" flood-color="{hex_accent}" flood-opacity="0.45"/>
    </filter>
    <clipPath id="subject_clip">
      <circle cx="{cx}" cy="{cy - 16}" r="{med_r}"/>
    </clipPath>
  </defs>
  {bg_svg}
  {container_svg}
  {subject_svg}
  {ribbon_svg}
  {badge_svg}
</svg>"""

    @classmethod
    def generate_visual_asset(
        cls,
        title: str,
        master_prompt: str,
        target_format: str = "app_icon",
        aspect_ratio: str = "1:1",
        color_palette: List[str] = None,
        composition_blueprint: str = "",
        ingredients_summary: List[Dict[str, Any]] = None,
        reference_images: List[Any] = None,
        app_slug: Optional[str] = None,
        variables: Dict[str, Any] = None,
        scene_elements: Optional[List[Dict[str, Any]]] = None,
        grid_mode: str = "single",
        grid_rows: int = 1,
        grid_cols: int = 1,
        concepts_list: Optional[List[Dict[str, Any]]] = None,
        preserve_source_picture: bool = False,
        cutout_bg: Optional[bool] = None
    ) -> Dict[str, Any]:
        """
        Generate a bespoke, high-fidelity visual asset using the geppy-s-asset-lab Picture-as-Source-of-Truth architecture:
        1. Assembles all active SOT pictures (Character, Logo, Icon Template, Item/Prop, Style, Stage) into a
           side-by-side Labeled Combined Reference Sheet (`ref_sheet_url`).
        2. Generates both AI Raster synthesis (`file_url` / `raw_file_url`) AND a True Picture-Preserving SOT Composite (`sot_composite_url`)
           that literally cuts out and combines the user's actual Source-of-Truth pictures.
        3. Supports Single Assets (`1x1`), Variation Grids (`2x2`, `3x3`), and Multi-Concept Grids (`2x2`, `3x3`) with automatic cell slicing (`sliced_assets`).
        """
        lab_dir = cls._get_lab_dir()
        asset_id = f"asset_{int(time.time())}_{uuid.uuid4().hex[:6]}"
        filename = f"{asset_id}.png"
        filepath = os.path.join(lab_dir, filename)

        # Normalize ingredients_summary items into standard dicts
        normalized_ingredients = []
        for ing in (ingredients_summary or []):
            if isinstance(ing, dict):
                normalized_ingredients.append(ing)
            else:
                normalized_ingredients.append({
                    "name": getattr(ing, "name", ""),
                    "title": getattr(ing, "title", ""),
                    "role": getattr(ing, "role", "style"),
                    "sot_role": getattr(ing, "sot_role", None),
                    "interaction": getattr(ing, "interaction", "none"),
                    "action": getattr(ing, "action", ""),
                    "archetype": getattr(ing, "archetype", "general"),
                    "reference_text": getattr(ing, "reference_text", ""),
                    "primary_image_url": getattr(ing, "primary_image_url", None),
                    "reference_image_url": getattr(ing, "reference_image_url", None),
                    "gallery_images": getattr(ing, "gallery_images", []) or [],
                    "modifiers": getattr(ing, "modifiers", {}) or {},
                    "variables": getattr(ing, "variables", []) or []
                })
        ingredients_summary = normalized_ingredients

        # Merge variables from explicit dict + ingredient defaults
        vars_dict = cls._merge_variables(variables, ingredients_summary)

        # Build the Labeled Combined Reference Sheet from all active SOT pictures
        sot_bundle = cls.build_scene_elements_and_reference_sheet(
            ingredients_summary=ingredients_summary,
            reference_images=reference_images,
            scene_elements=scene_elements,
            asset_id=asset_id
        )
        active_scene_elements = sot_bundle["elements"]
        ref_sheet_img = sot_bundle["ref_sheet_img"]
        ref_sheet_url = sot_bundle["ref_sheet_url"]

        # Check if this is genuinely a Trading Card / Baseball Card request
        is_card = cls._is_trading_card_request(target_format, title, master_prompt, ingredients_summary)

        if is_card and grid_mode == "single":
            img = cls._render_trading_card(
                title=title,
                master_prompt=master_prompt,
                ingredients_summary=ingredients_summary,
                reference_images=reference_images,
                color_palette=color_palette,
                variables=vars_dict
            )
            img = img.convert("RGB")
            img.save(filepath, "PNG", quality=95)

            file_url = f"/api/asset-lab/file/{filename}"
            record = {
                "id": asset_id,
                "title": title,
                "filename": filename,
                "filepath": filepath,
                "file_path": filepath,
                "file_url": file_url,
                "ref_sheet_url": ref_sheet_url,
                "scene_elements": [
                    {"name": e["name"], "role": e["role"], "interaction": e["interaction"], "action": e["action"], "label": e["label"], "url": e["url"]}
                    for e in active_scene_elements
                ],
                "target_format": "trading_card",
                "aspect_ratio": "2.5:3.5",
                "master_prompt": master_prompt,
                "color_palette": color_palette or [],
                "composition_blueprint": composition_blueprint or "Authentic 1970s trading card layout",
                "ingredients_summary": ingredients_summary or [],
                "variables": vars_dict,
                "app_slug": app_slug,
                "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
            }
            cls.save_history_item(record)
            return record

        # Dimension mapping
        dim_map = {
            "1:1": (1024, 1024),
            "16:9": (1920, 1080),
            "9:16": (1080, 1920),
            "4:3": (1200, 900),
            "21:9": (2100, 900),
            "2.5:3.5": (750, 1050)
        }
        width, height = dim_map.get(aspect_ratio, (1024, 1024))
        if target_format in ["app_icon", "transparent_png", "avatar"] or grid_mode in ("variations_grid", "multi_concept_grid"):
            width, height = (1024, 1024)

        palette_list = color_palette or []
        combined_text = f"{title} {master_prompt} {composition_blueprint}".lower()
        is_hex = (
            "hex" in combined_text or
            "hexagonal" in combined_text or
            any("hex" in (i.get("name", "") + " " + i.get("title", "") + " " + str(i.get("modifiers", {}))).lower() for i in ingredients_summary)
        )
        if cutout_bg is not None:
            should_cutout = bool(cutout_bg)
        else:
            should_cutout = (
                target_format not in ["banner_hero", "social_story"] or
                "no background" in combined_text or
                "no_background" in combined_text or
                "transparent" in combined_text or
                "isolated" in combined_text or
                "cutout" in combined_text or
                any("transparent" in str(i.get("modifiers", {})).lower() or "no background" in str(i.get("modifiers", {})).lower() for i in ingredients_summary)
            )
        is_orange = "orange" in combined_text or is_hex or any("orange" in str(i.get("modifiers", {})).lower() for i in ingredients_summary)

        if is_orange and not palette_list:
            c_accent = (245, 158, 11)
            c_secondary = (6, 182, 212)
            c_gold = (251, 191, 36)
            c_dark = (15, 23, 42)
        else:
            c_accent = _hex_to_rgb(palette_list[0] if len(palette_list) > 0 else None, (245, 158, 11) if is_orange else (6, 182, 212))
            c_secondary = _hex_to_rgb(palette_list[1] if len(palette_list) > 1 else None, (99, 102, 241))
            c_gold = _hex_to_rgb(palette_list[2] if len(palette_list) > 2 else None, (245, 158, 11))
            c_dark = _hex_to_rgb(palette_list[3] if len(palette_list) > 3 else None, (15, 23, 42))
        c_base = (max(0, c_dark[0] - 10), max(0, c_dark[1] - 10), max(0, c_dark[2] - 10))

        raw_ref_urls = [r.get("url") if isinstance(r, dict) else r for r in (reference_images or []) if r]
        ref_info = cls._classify_and_resolve_references(ingredients_summary, raw_ref_urls)

        # 1. Generate AI Raster Image + SOT Picture Composite + Automatic Post-Generation Cutout
        ai_cutout_img, raw_ai_img, sot_picture_composite = cls._generate_ai_raster_image(
            title=title,
            master_prompt=master_prompt,
            target_format=target_format,
            width=width,
            height=height,
            color_palette=palette_list,
            composition_blueprint=composition_blueprint,
            ingredients_summary=ingredients_summary,
            vars_dict=vars_dict,
            ref_paths=[e["path"] for e in active_scene_elements] or ref_info["all_paths"],
            use_chroma_cutout=should_cutout,
            is_hex=is_hex,
            ref_sheet_img=ref_sheet_img,
            scene_elements=active_scene_elements,
            grid_mode=grid_mode,
            grid_rows=grid_rows,
            grid_cols=grid_cols,
            concepts_list=concepts_list,
            preserve_source_picture=preserve_source_picture
        )

        rendered_img: Optional[Image.Image] = ai_cutout_img or raw_ai_img or sot_picture_composite
        if rendered_img is None:
            rendered_img = Image.new("RGBA", (width, height), (0, 0, 0, 0) if should_cutout else (*c_dark, 255))

        # 1b. Apply Physical Fabrication Processing (Laser 1-Bit B&W Burn / Stencil Edge Connections) & Blank Contextile of Truth Composite
        try:
            fab_res = cls._apply_fabrication_and_blank_composite(
                rendered_img=raw_ai_img or rendered_img,
                ingredients_summary=ingredients_summary,
                vars_dict=vars_dict,
                master_prompt=master_prompt
            )
            if fab_res.get("production_img") is not None:
                rendered_img = fab_res["production_img"]
                should_cutout = False
            if fab_res.get("blank_mockup_img") is not None:
                sot_picture_composite = fab_res["blank_mockup_img"]
        except Exception as e:
            print(f"[AssetLabService] _apply_fabrication_and_blank_composite notice: {e}")

        # Save raw uncut AI image alongside if available
        raw_file_url = None
        if raw_ai_img is not None:
            raw_filename = f"{asset_id}_raw.png"
            raw_filepath = os.path.join(lab_dir, raw_filename)
            try:
                raw_ai_img.convert("RGB").save(raw_filepath, "PNG", quality=95)
                raw_file_url = f"/api/asset-lab/file/{raw_filename}"
            except Exception as e:
                print(f"[AssetLabService] Save raw AI image notice: {e}")

        # Save True Picture-Preserving SOT Composite (or Physical Blank Mockup Composite) alongside if available
        sot_composite_url = None
        if sot_picture_composite is not None:
            comp_filename = f"{asset_id}_sot_composite.png"
            comp_filepath = os.path.join(lab_dir, comp_filename)
            try:
                if should_cutout:
                    sot_picture_composite.convert("RGBA").save(comp_filepath, "PNG")
                else:
                    sot_picture_composite.convert("RGB").save(comp_filepath, "PNG", quality=95)
                sot_composite_url = f"/api/asset-lab/file/{comp_filename}"
            except Exception as e:
                print(f"[AssetLabService] Save SOT composite notice: {e}")

        # Save High-Resolution PNG
        if should_cutout:
            rendered_img.convert("RGBA").save(filepath, "PNG")
        else:
            rendered_img.convert("RGB").save(filepath, "PNG", quality=95)
        file_url = f"/api/asset-lab/file/{filename}"

        # If a Variation Grid or Multi-Concept Grid (2x2 or 3x3) was generated, automatically slice into individual assets!
        sliced_assets: List[Dict[str, Any]] = []
        rows = max(1, int(grid_rows or 1))
        cols = max(1, int(grid_cols or 1))
        if grid_mode in ("variations_grid", "multi_concept_grid") and (rows > 1 or cols > 1):
            try:
                sliced_assets = cls.slice_grid_cells(
                    sheet_img=rendered_img,
                    rows=rows,
                    cols=cols,
                    asset_id=asset_id,
                    concepts_list=concepts_list,
                    should_cutout=should_cutout
                )
            except Exception as e:
                print(f"[AssetLabService] slice_grid_cells notice: {e}")

        # Record in history (PNG only, no wasted SVG processing)
        record = {
            "id": asset_id,
            "title": title,
            "filename": filename,
            "filepath": filepath,
            "file_path": filepath,
            "file_url": file_url,
            "raw_file_url": raw_file_url,
            "sot_composite_url": sot_composite_url,
            "ref_sheet_url": ref_sheet_url,
            "scene_elements": [
                {"name": e["name"], "role": e["role"], "interaction": e["interaction"], "action": e["action"], "label": e["label"], "url": e["url"]}
                for e in active_scene_elements
            ],
            "grid_mode": grid_mode,
            "grid_rows": rows,
            "grid_cols": cols,
            "sliced_assets": sliced_assets,
            "cutout_applied": bool(should_cutout and rendered_img is not None),
            "target_format": target_format,
            "aspect_ratio": aspect_ratio,
            "master_prompt": master_prompt,
            "color_palette": color_palette or [],
            "composition_blueprint": composition_blueprint,
            "ingredients_summary": ingredients_summary or [],
            "variables": vars_dict,
            "app_slug": app_slug,
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        cls.save_history_item(record)
        return record

    @classmethod
    def _apply_fabrication_and_blank_composite(
        cls,
        rendered_img: Optional[Image.Image],
        ingredients_summary: Optional[List[Dict[str, Any]]] = None,
        vars_dict: Optional[Dict[str, Any]] = None,
        master_prompt: str = ""
    ) -> Dict[str, Optional[Image.Image]]:
        """
        If a Contextile of Truth (physical blank) or Fabrication Contextile (Laser 1-Bit B&W Burn,
        Cut Stencil with Edge Connections, Vinyl Cutter, or Sublimation) is active:
        1. Post-processes `production_img` into a true 1-bit high-contrast Black & White laser/stencil file
           (and adds structural outer frame + edge connection bridges when stencil mode is active).
        2. Renders `blank_mockup_img` showing the artwork burned, stenciled, or sublimated directly inside
           the physical blank's calibrated safe zone!
        """
        if rendered_img is None:
            return {"production_img": None, "blank_mockup_img": None}

        from gitbridge.services.sot_service import SOTService
        ings = ingredients_summary or []
        vdict = vars_dict or {}
        mp_low = (master_prompt or "").lower()

        blank_ing = None
        blank_spec: Dict[str, Any] = {}
        is_laser_bw = False
        is_stencil_bridged = False
        is_vinyl_cut = False

        for ing in ings:
            if not isinstance(ing, dict):
                continue
            name_low = str(ing.get("name") or "").lower()
            arch_low = str(ing.get("archetype") or "").lower()
            mods = ing.get("modifiers") if isinstance(ing.get("modifiers"), dict) else {}
            ek = str(ing.get("entity_kind") or SOTService.infer_entity_kind(arch_low, mods, name_low)).lower()
            if ek == "contextile_of_truth" or arch_low == "blank_substrate" or isinstance(ing.get("blank_spec"), dict) or isinstance(mods.get("blank_spec"), dict):
                blank_ing = ing
                blank_spec = (ing.get("blank_spec") if isinstance(ing.get("blank_spec"), dict) else mods.get("blank_spec")) or {}
            if "stencil" in name_low:
                is_stencil_bridged = True
            if "laser" in name_low:
                is_laser_bw = True
            for f_item in (mods.get("fabrication_mode") or []):
                fl = str(f_item).lower()
                if "stencil" in fl or "bridge" in fl:
                    is_stencil_bridged = True
                elif "laser" in fl and ("1-bit" in fl or "black & white" in fl or "dither" in fl):
                    is_laser_bw = True
                elif "vinyl" in fl:
                    is_vinyl_cut = True
            for tog in (ing.get("option_toggles") or mods.get("option_toggles") or []):
                if isinstance(tog, dict) and tog.get("enabled"):
                    tk = str(tog.get("key") or tog.get("label") or "").lower()
                    if "stencil" in tk or "bridge" in tk:
                        is_stencil_bridged = True
                    elif "laser" in tk or "1bit" in tk or "1-bit" in tk:
                        is_laser_bw = True

        # Check dropdown variable selections
        for vk, vv in vdict.items():
            v_str = f"{vk} {vv}".lower()
            if "stencil" in v_str and ("bridge" in v_str or "edge connection" in v_str):
                is_stencil_bridged = True
                is_laser_bw = False
            elif "laser engraver" in v_str and ("1-bit" in v_str or "black & white" in v_str):
                is_laser_bw = True
            elif "dye sublimation" in v_str or "uv direct" in v_str:
                is_laser_bw = False
                is_stencil_bridged = False

        if blank_spec:
            bfab = str(blank_spec.get("fabrication_mode") or "").lower()
            if not is_stencil_bridged and not is_vinyl_cut:
                if "stencil" in bfab or blank_spec.get("edge_connections"):
                    is_stencil_bridged = True
                elif "laser" in bfab or blank_spec.get("color_constraint") == "bw_1bit":
                    is_laser_bw = True

        if "cuttable stencil with edge connections" in mp_low:
            is_stencil_bridged = True
        elif "strictly 1-bit black and white laser" in mp_low:
            is_laser_bw = True

        production_img: Optional[Image.Image] = None
        bw_mask: Optional[Image.Image] = None

        if is_laser_bw or is_stencil_bridged:
            # Convert rendered_img into crisp 1-bit high-contrast Black (#000000) & White (#FFFFFF)
            src_rgba = rendered_img.convert("RGBA")
            w, h = src_rgba.size
            white_bg = Image.new("RGBA", (w, h), (255, 255, 255, 255))
            white_bg.alpha_composite(src_rgba)
            gray = white_bg.convert("L")

            # Compute adaptive threshold so artwork lines/shapes become pure #000000 and background is #FFFFFF
            hist = gray.histogram()
            total_px = max(1, sum(hist))
            mean_lum = sum(i * hist[i] for i in range(256)) / total_px
            # If the image has a dark background, invert so background becomes white (#FFFFFF)
            corners = [
                gray.getpixel((8, 8)),
                gray.getpixel((w - 9, 8)),
                gray.getpixel((8, h - 9)),
                gray.getpixel((w - 9, h - 9))
            ]
            if sum(corners) / 4.0 < 110:
                from PIL import ImageOps
                gray = ImageOps.invert(gray)
                hist = gray.histogram()
                mean_lum = sum(i * hist[i] for i in range(256)) / total_px

            thresh = int(max(95, min(185, mean_lum * 0.92)))
            bw_l = gray.point(lambda p: 0 if p < thresh else 255, mode="L")
            prod_rgba = Image.merge("RGBA", (bw_l, bw_l, bw_l, Image.new("L", (w, h), 255)))

            if is_stencil_bridged:
                # Add outer stencil sheet border + structural edge-connection bridges (white bridge bars tying interior islands to outer frame)
                sdraw = ImageDraw.Draw(prod_rgba)
                frame_pad = max(18, int(min(w, h) * 0.04))
                bridge_w = max(12, int(min(w, h) * 0.018))
                # White outer frame margin (material) + black stencil border guide
                sdraw.rectangle([0, 0, w, frame_pad], fill=(255, 255, 255, 255))
                sdraw.rectangle([0, h - frame_pad, w, h], fill=(255, 255, 255, 255))
                sdraw.rectangle([0, 0, frame_pad, h], fill=(255, 255, 255, 255))
                sdraw.rectangle([w - frame_pad, 0, w, h], fill=(255, 255, 255, 255))
                sdraw.rectangle([frame_pad, frame_pad, w - frame_pad, h - frame_pad], outline=(0, 0, 0, 255), width=4)
                # Structural stencil edge bridges (top, bottom, left, right, and mid-island tie-bars in pure white #FFFFFF material)
                cx, cy = w // 2, h // 2
                sdraw.rectangle([cx - bridge_w // 2, 0, cx + bridge_w // 2, h], fill=(255, 255, 255, 255))
                sdraw.rectangle([0, cy - bridge_w // 2, w, cy + bridge_w // 2], fill=(255, 255, 255, 255))
                # Secondary upper/lower island support bridges
                y_upper = int(h * 0.34)
                y_lower = int(h * 0.66)
                b_thin = max(8, bridge_w * 2 // 3)
                sdraw.rectangle([0, y_upper - b_thin // 2, w, y_upper + b_thin // 2], fill=(255, 255, 255, 255))
                sdraw.rectangle([0, y_lower - b_thin // 2, w, y_lower + b_thin // 2], fill=(255, 255, 255, 255))
                bw_l = prod_rgba.convert("L")

            production_img = prod_rgba
            bw_mask = bw_l

        # 2. If a Blank Contextile of Truth is active, render an On-Blank Mockup Composite showing the output on the physical blank!
        blank_mockup_img: Optional[Image.Image] = None
        if blank_ing is not None:
            raw_blank_url = (
                blank_spec.get("raw_blank_image_url")
                or (blank_ing.get("gallery_images")[-1] if (blank_ing.get("gallery_images") and len(blank_ing.get("gallery_images")) > 1) else None)
                or blank_ing.get("primary_image_url")
            )
            blank_path = cls.resolve_image_path(raw_blank_url) if raw_blank_url else None
            if blank_path and os.path.exists(blank_path):
                try:
                    with Image.open(blank_path) as b_im:
                        blank_canvas = b_im.convert("RGBA")
                except Exception:
                    blank_canvas = None
            else:
                blank_canvas = None

            if blank_canvas is not None:
                bw_c, bh_c = blank_canvas.size
                w_in = float(blank_spec.get("width_in") or 4.0)
                h_in = float(blank_spec.get("height_in") or 4.0)
                safe_in = float(blank_spec.get("safe_margin_in") or 0.25)
                mat_str = str(blank_spec.get("material") or "natural_wood").lower()

                # Compute safe zone box inside the blank image (accounting for 9% outer studio padding + safe_margin_in)
                margin_rx = min(0.28, 0.09 + (safe_in / max(1.0, w_in)) * 0.8)
                margin_ry = min(0.28, 0.09 + (safe_in / max(1.0, h_in)) * 0.8)
                sx0, sy0 = int(bw_c * margin_rx), int(bh_c * margin_ry)
                sx1, sy1 = bw_c - sx0, bh_c - sy0
                sw, sh = max(64, sx1 - sx0), max(64, sy1 - sy0)

                if bw_mask is not None:
                    # Burn or stencil the 1-bit mask onto the blank surface!
                    from PIL import ImageOps
                    mask_resized = ImageOps.invert(bw_mask).resize((sw, sh), Image.Resampling.LANCZOS)
                    if "slate" in mat_str or "black" in mat_str:
                        # Laser etching on dark slate turns burned areas light silver-stone
                        burn_color = (218, 224, 232, 235)
                    elif is_stencil_bridged:
                        # Stencil cutout sprayed onto blank
                        burn_color = (20, 28, 42, 240)
                    else:
                        # Deep pyrography woodburn on natural wood
                        burn_color = (52, 26, 10, 238)
                    burn_layer = Image.new("RGBA", (sw, sh), burn_color)
                    blank_canvas.paste(burn_layer, (sx0, sy0), mask_resized)
                else:
                    # Full-color sublimation / UV transfer inside the blank safe zone
                    art_fit = (production_img or rendered_img).convert("RGBA").resize((sw, sh), Image.Resampling.LANCZOS)
                    blank_canvas.alpha_composite(art_fit, (sx0, sy0))

                blank_mockup_img = blank_canvas

        return {
            "production_img": production_img,
            "blank_mockup_img": blank_mockup_img
        }



