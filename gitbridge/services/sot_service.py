import os
import re
import json
import requests
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from datetime import datetime

from gitbridge.db.models import ContextileModel
from PIL import Image, ImageDraw, ImageFont, ImageFilter

def generate_contextile_thumbnail(
    handle: str,
    title: str,
    concept: str,
    archetype: str = "style",
    color_palette: Optional[List[str]] = None,
    reference_text: Optional[str] = None,
    master_style_prompt: Optional[str] = None
) -> Optional[str]:
    """Generate an authentic AI example preview image for the SOT Contextile."""
    try:
        ref_dir = SOTService._get_references_dir()
        fname = f"preview_{handle}.png"
        filepath = os.path.join(ref_dir, fname)

        low = f"{concept} {title} {reference_text or ''} {master_style_prompt or ''}".lower()
        is_card = "baseball" in low or "trading card" in low or "topps" in low
        is_sticker = "sticker" in low or "die-cut" in low or "diecut" in low
        w, h = (600, 800) if is_card else (768, 768)

        # 1. Primary Path: Real AI Image Generation showcasing the style/subject
        if archetype != "output":
            try:
                from gitbridge.services.asset_lab_service import AssetLabService
                from gitbridge.services.output_service import OutputService

                style_desc = master_style_prompt or reference_text or concept or title
                if archetype == "style":
                    if is_sticker:
                        ai_prompt = (
                            f"Vibrant showcase example of '{title}' ({concept}): "
                            f"A charismatic cyberpunk anime character mascot die-cut sticker with bold cel-shaded linework, "
                            f"shimmering holographic prism foil highlights, neon cyan and magenta rim lighting, and a crisp white die-cut vinyl border. "
                            f"Style specification: {style_desc}"
                        )
                    elif is_card:
                        ai_prompt = (
                            f"Authentic showcase example of '{title}' ({concept}): "
                            f"Vintage portrait illustration in {style_desc} aesthetic, rich period color grading and texture."
                        )
                    else:
                        ai_prompt = (
                            f"Masterpiece visual showcase example demonstrating the '{title}' style ({concept}): "
                            f"{style_desc}. Iconic focal subject rendered with signature lighting, materials, and color palette."
                        )
                else:
                    ai_prompt = f"{title}: {style_desc}"

                should_cutout = is_sticker or archetype in ("character", "icon_set", "brand_asset")
                ai_img, _raw_uncut = AssetLabService._generate_ai_raster_image(
                    title=title,
                    master_prompt=ai_prompt,
                    target_format="trading_card" if is_card else "app_icon",
                    width=w,
                    height=h,
                    color_palette=color_palette or [],
                    composition_blueprint=reference_text or "",
                    ingredients_summary=[],
                    vars_dict={},
                    ref_paths=[],
                    use_chroma_cutout=should_cutout,
                    is_hex=False
                )
                if ai_img is not None:
                    ai_img.save(filepath, "PNG")
                    return f"/api/sot/reference-file/{fname}"
            except Exception as ai_err:
                print(f"[generate_contextile_thumbnail] AI generation fallback triggered: {ai_err}")

        # 2. Fallback Procedural Preview (only if AI generation is unavailable or archetype == 'output')
        img = Image.new("RGBA", (w, h), (15, 23, 42, 255))
        draw = ImageDraw.Draw(img)

        if is_card:
            # Authentic 1970s Baseball Trading Card Layout
            for y in range(h):
                ratio = y / h
                r = int(246 - 12 * ratio)
                g = int(238 - 14 * ratio)
                b = int(224 - 18 * ratio)
                draw.line([(0, y), (w, y)], fill=(r, g, b, 255))

            pad = 22
            draw.rectangle([pad, pad, w - pad, h - pad], outline=(30, 41, 59, 220), width=3)
            banner_y0 = pad + 18
            banner_y1 = banner_y0 + 72
            draw.rounded_rectangle([pad + 16, banner_y0, w - pad - 16, banner_y1], radius=14, fill=(220, 38, 38, 240), outline=(245, 158, 11, 255), width=3)
            font_def = ImageFont.load_default()
            header_text = title.upper()[:28]
            h_bbox = draw.textbbox((0, 0), header_text, font=font_def)
            draw.text(((w - (h_bbox[2] - h_bbox[0])) // 2, banner_y0 + 26), header_text, fill=(255, 255, 255, 255), font=font_def)

        elif archetype == "output":
            # Output & Print Spec Thumbnail (ONLY for explicit 'output' print-spec archetype)
            tile_sz = 24
            for ty in range(0, h, tile_sz):
                for tx in range(0, w, tile_sz):
                    is_dark = ((tx // tile_sz) + (ty // tile_sz)) % 2 == 0
                    c = (15, 23, 42, 255) if is_dark else (30, 41, 59, 255)
                    draw.rectangle([tx, ty, tx + tile_sz, ty + tile_sz], fill=c)

            st_cx, st_cy = w // 2, h // 2 - 20
            st_r = 130
            draw.ellipse([st_cx - st_r, st_cy - st_r, st_cx + st_r, st_cy + st_r], fill=(255, 255, 255, 255))
            draw.ellipse([st_cx - st_r + 14, st_cy - st_r + 14, st_cx + st_r - 14, st_cy + st_r - 14], fill=(6, 182, 212, 255))
            font_def = ImageFont.load_default()
            np_y0 = h - 90
            pad = 25
            draw.rounded_rectangle([pad + 10, np_y0, w - pad - 10, np_y0 + 55], radius=10, fill=(15, 23, 42, 240), outline=(6, 182, 212, 200), width=2)
            disp_title = title.upper()[:28]
            tb_box = draw.textbbox((0, 0), disp_title, font=font_def)
            draw.text(((w - (tb_box[2] - tb_box[0])) // 2, np_y0 + 12), disp_title, fill=(255, 255, 255, 255), font=font_def)

        else:
            # Vibrant Neon / Prism Style Swatch Card
            for y in range(h):
                ratio = y / h
                r = int(18 + 45 * ratio)
                g = int(12 + 25 * (1.0 - ratio))
                b = int(48 + 90 * ratio)
                draw.line([(0, y), (w, y)], fill=(r, g, b, 255))

            cx, cy = w // 2, h // 2
            pts_outer = []
            pts_inner = []
            import math
            for i in range(6):
                ang = math.radians(60 * i - 30)
                pts_outer.append((cx + int(190 * math.cos(ang)), cy + int(190 * math.sin(ang))))
                pts_inner.append((cx + int(168 * math.cos(ang)), cy + int(168 * math.sin(ang))))
            draw.polygon(pts_outer, fill=(255, 255, 255, 255))
            draw.polygon(pts_inner, fill=(15, 23, 42, 255), outline=(6, 182, 212, 255))
            draw.ellipse([cx - 110, cy - 110, cx + 110, cy + 110], outline=(236, 72, 153, 220), width=4)

            font_def = ImageFont.load_default()
            t_box = draw.textbbox((0, 0), title, font=font_def)
            draw.text(((w - (t_box[2] - t_box[0])) // 2, cy - 12), title, fill=(255, 255, 255, 255), font=font_def)
            arch_badge = f"SOT {archetype.upper()} STYLE"
            a_box = draw.textbbox((0, 0), arch_badge, font=font_def)
            draw.text(((w - (a_box[2] - a_box[0])) // 2, cy + 14), arch_badge, fill=(56, 189, 248, 255), font=font_def)

        img.save(filepath, "PNG")
        return f"/api/sot/reference-file/{fname}"
    except Exception as e:
        print(f"[generate_contextile_thumbnail] Error: {e}")
        return None

GEMINI_MODELS = ["gemini-2.5-flash", "gemini-1.5-flash", "gemini-3.8-flash"]

MODIFIER_TAXONOMY = {
    "lighting": [
        "Volumetric Studio Light",
        "Cyberpunk Neon Rim",
        "Golden Hour Sunbeam",
        "Dramatic Chiaroscuro",
        "Bioluminescent Ambient Glow",
        "High-Key Commercial Softbox",
        "Moody Starlight Backlight",
        "Cinematic Anamorphic Flare",
        "Atmospheric Cosmic Fog"
    ],
    "theme": [
        "Cosmic Galactic & Nebula",
        "Apple Glassmorphic Clean",
        "Cyber-SciFi Holographic",
        "Retro 80s Synthwave",
        "Minimalist Luxury Dark",
        "Hyper-Detailed Unreal Engine 5",
        "Solarpunk High-Tech",
        "Vector Isometric Clean",
        "Photorealistic 8K Commercial"
    ],
    "era": [
        "2026 Next-Gen Frontier",
        "Deep Space Far Future",
        "1980s Neon Retro",
        "1990s Cyberpunk Early Web",
        "Timeless Modernist",
        "Steampunk Brass & Clockwork",
        "Y2K Glossy Chrome"
    ],
    "medium": [
        "8K Octane 3D Render",
        "Macro Studio Photography",
        "Anamorphic 35mm Cinema",
        "Isometric 3D Diorama",
        "Vector SVG Flat Illustration",
        "Glossy Product Packaging Render",
        "Digital Matte Painting"
    ],
    "materials": [
        "Frosted Translucent Glass",
        "Brushed Titanium Metal",
        "Matte Dark Obsidian",
        "Glowing Neon Wireframe",
        "Iridescent Liquid Hologram",
        "Carbon Fiber Weave",
        "Polished Ceramic White"
    ]
}

ARCHETYPES = {
    "character": {
        "id": "character",
        "label": "Character / Persona",
        "icon": "👤",
        "badge": "Character Anchor",
        "description": "Character consistency anchor: facial likeness, hair, attire, and multi-angle turnarounds."
    },
    "icon_set": {
        "id": "icon_set",
        "label": "App Icon Set / Style Guide",
        "icon": "🎨",
        "badge": "App Icon Guide",
        "description": "Collection of reference app icons: maintains cohesive 3D squircle curvature, gradient depth, beveling, lighting, and glyph geometry for new icons."
    },
    "ui_component": {
        "id": "ui_component",
        "label": "UI Component / Design Token",
        "icon": "🧩",
        "badge": "UI Component",
        "description": "Design system reference: card containers, glassmorphic HUDs, button styles, borders, and spacing."
    },
    "brand_asset": {
        "id": "brand_asset",
        "label": "Brand Asset / Logo",
        "icon": "🏷️",
        "badge": "Brand Identity",
        "description": "Logos, badges, emblems, packaging, and brand typography."
    },
    "environment": {
        "id": "environment",
        "label": "Environment / Scene",
        "icon": "🌌",
        "badge": "Environment & Scene",
        "description": "Planetary landscapes, flight deck cockpits, space vistas, and lighting atmospheres."
    },
    "style": {
        "id": "style",
        "label": "Context Style / Frame / Medium",
        "icon": "🎭",
        "badge": "Style & Medium",
        "description": "Visual style, art medium, or thematic frame (e.g. 70s Baseball Card, Cyberpunk Hologram, 1930s Cartoon, Risograph) that can be fused onto any subject or character."
    },
    "output": {
        "id": "output",
        "label": "Output & Print Spec",
        "icon": "🖨️",
        "badge": "Output & Print",
        "description": "Output specification for export finishing: transparent backgrounds, die-cut sticker outlines, 300 DPI print-ready PDFs, custom borders, bleed, and trim margins."
    },
    "general": {
        "id": "general",
        "label": "General SOT / Custom",
        "icon": "✨",
        "badge": "General Anchor",
        "description": "Custom Source of Truth reference for marketing, assets, or code."
    }
}

def call_gemini(messages: List[Dict[str, Any]], system_instruction: str) -> Optional[str]:
    from gitbridge.services.central_key_service import CentralKeyService
    return CentralKeyService.call_gemini(messages, system_instruction)


class SOTService:

    @staticmethod
    def _get_references_dir() -> str:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        ref_dir = os.path.join(base_dir, "assets", "sot_references")
        os.makedirs(ref_dir, exist_ok=True)
        return ref_dir

    @staticmethod
    def get_modifiers_taxonomy() -> Dict[str, List[str]]:
        """Return categorized modifier taxonomy options."""
        return MODIFIER_TAXONOMY

    @staticmethod
    def get_archetypes() -> Dict[str, Dict[str, Any]]:
        """Return supported SOT Archetype definitions."""
        return ARCHETYPES

    @staticmethod
    def compile_prompt(
        reference_text: str,
        modifiers: Dict[str, Any],
        custom_tags: List[str] = [],
        archetype: str = "character",
        primary_image_url: Optional[str] = None,
        gallery_images: List[str] = []
    ) -> str:
        """Assemble base reference text, archetype directives, and modifiers into a unified Source-of-Truth prompt."""
        parts = []

        # Archetype directive
        if archetype == "character":
            parts.append("[SOT Character Anchor - Preserve facial likeness, suit design, and character identity]")
        elif archetype == "icon_set":
            parts.append("[SOT App Icon Style Guide - Cohesive 3D squircle silhouette, beveling, lighting, and icon grammar]")
        elif archetype == "ui_component":
            parts.append("[SOT UI Component System - Glassmorphic blur, rounded borders, and UI hierarchy]")
        elif archetype == "brand_asset":
            parts.append("[SOT Brand Identity - Strict brand color scheme and vector geometry]")
        elif archetype == "environment":
            parts.append("[SOT Environment - Volumetric atmosphere, perspective depth, and color temperature]")
        elif archetype == "style":
            parts.append("[SOT Context Style & Aesthetic Frame - Master visual grammar, materials, border framing, and rendering medium to fuse over subjects]")
        elif archetype == "output":
            parts.append("[SOT Output & Print Finishing Spec - Background treatment, die-cut contours, bleed margins, crop marks, and 300 DPI layout]")

        ref = (reference_text or "").strip()
        if ref:
            parts.append(ref)

        if archetype == "output" or modifiers.get("background_mode") or modifiers.get("print_size"):
            bg_mode = modifiers.get("background_mode", "transparent")
            psize = modifiers.get("print_size", "custom")
            dpi = modifiers.get("dpi", 300)
            parts.append(f"Finishing Output: {bg_mode} | Size: {psize} @ {dpi} DPI")

        theme = modifiers.get("theme")
        if theme:
            val = ", ".join(theme) if isinstance(theme, list) else str(theme)
            parts.append(f"Visual Theme: {val}")

        lighting = modifiers.get("lighting")
        if lighting:
            val = ", ".join(lighting) if isinstance(lighting, list) else str(lighting)
            parts.append(f"Lighting: {val}")

        era = modifiers.get("era")
        if era:
            val = ", ".join(era) if isinstance(era, list) else str(era)
            parts.append(f"Era/Mood: {val}")

        medium = modifiers.get("medium")
        if medium:
            val = ", ".join(medium) if isinstance(medium, list) else str(medium)
            parts.append(f"Render Style: {val}")

        materials = modifiers.get("materials")
        if materials:
            val = ", ".join(materials) if isinstance(materials, list) else str(materials)
            parts.append(f"Materials & Textures: {val}")

        custom = modifiers.get("custom") or []
        all_custom = set(custom if isinstance(custom, list) else [custom])
        all_custom.update(custom_tags or [])
        if all_custom:
            parts.append(f"Custom Modifiers: {', '.join([c for c in all_custom if c])}")

        if primary_image_url:
            parts.append(f"Primary Image Anchor: {primary_image_url}")
        if gallery_images and len(gallery_images) > 1:
            parts.append(f"Reference Gallery: {len(gallery_images)} contextual reference images")

        return " | ".join(parts)

    @staticmethod
    def suggest_modifiers_ai(reference_text: str, archetype: str = "character", app_name: Optional[str] = None) -> Dict[str, Any]:
        """Use Gemini to brainstorm an optimal modifier recipe based on reference concept and archetype."""
        system_instruction = f"""You are Captain Geppy's Master Aesthetic & SOT (Source of Truth) Engineer.
The user is building a Source of Truth Contextile of Archetype: '{archetype}'.
- If 'icon_set': Brainstorm modifiers suited for modern app icons (e.g. 3D squircle renders, glossy plastic/glass, isometric studio spotlight, vibrant contrast).
- If 'character': Focus on character rendering, facial fidelity, suit materials, and cinematic rim lighting.
- If 'ui_component': Focus on modern SaaS UI tokens, glassmorphism, micro-borders, clean elevation.
- If 'brand_asset': Focus on clean vector minimalism, geometric balance, metallic badges.
- If 'environment': Focus on atmospheric depth, starry nebulae, celestial lighting.

Select or create the most striking combination of:
- lighting
- theme
- era
- medium
- materials
- custom_tags (2-3 punchy tags)
Also provide a 1-sentence rationale.

Respond strictly with valid JSON:
{{
  "recommended_title": "Short title for this SOT Contextile",
  "suggested_handle": "kebab-case-handle",
  "lighting": ["Volumetric Studio Light", "Cyberpunk Neon Rim"],
  "theme": ["Cosmic Galactic & Nebula"],
  "era": ["2026 Next-Gen Frontier"],
  "medium": ["8K Octane 3D Render"],
  "materials": ["Frosted Translucent Glass", "Glowing Neon Wireframe"],
  "custom_tags": ["hero-asset", "captain-geppy-grade"],
  "rationale": "High-contrast cinematic look that makes the core subject pop with interstellar energy."
}}"""

        messages = [{
            "role": "user",
            "parts": [{"text": f"Reference subject for app '{app_name or 'Geppy Galactic'}':\n{reference_text}"}]
        }]

        raw = call_gemini(messages, system_instruction)
        if raw:
            try:
                clean = raw.strip()
                if clean.startswith("```json"): clean = clean[7:]
                elif clean.startswith("```"): clean = clean[3:]
                if clean.endswith("```"): clean = clean[:-3]
                clean = clean.strip()
                data = json.loads(clean)
                return data
            except Exception as e:
                print(f"[SOTService] Parse AI modifiers failed: {e}")

        # Fallback recipe
        return {
            "recommended_title": "Cosmic Neon Hero",
            "suggested_handle": "cosmic-neon-hero",
            "lighting": ["Cyberpunk Neon Rim", "Volumetric Studio Light"],
            "theme": ["Cosmic Galactic & Nebula"],
            "era": ["2026 Next-Gen Frontier"],
            "medium": ["8K Octane 3D Render"],
            "materials": ["Frosted Translucent Glass", "Glowing Neon Wireframe"],
            "custom_tags": ["hero-asset", "ground-truth"],
            "rationale": "Vibrant starlight illumination with deep slate and neon cyan glass elevation."
        }

    @staticmethod
    def ai_autofill_contextile(prompt: str, current_archetype: Optional[str] = None, app_name: Optional[str] = None) -> Dict[str, Any]:
        """Intelligently autofill an entire Contextile (archetype, handle, title, base reference, modifiers, custom notes, creative options) from a seed idea or concept."""
        concept = (prompt or "").strip()
        arch_hint = current_archetype if (current_archetype and current_archetype != "all") else ""

        system_instruction = """You are Captain Geppy's Master AI Architect & SOT (Source of Truth) Engine Director.
Your task is to take a creator's seed idea, theme, or concept and generate a COMPLETE, production-ready Ground Truth Contextile specification.

You must output valid JSON with these fields:
1. "archetype": one of ["character", "icon_set", "ui_component", "brand_asset", "environment", "general"]
2. "suggested_handle": clean lowercase kebab-case handle without @ (e.g. "captain-geppy-cyberpunk", "finance-3d-icons")
3. "recommended_title": punchy, high-impact display title (e.g. "Captain Geppy Cyberpunk Commander", "3D Glassmorphic Finance Icon Pack")
4. "reference_text": rich, vivid ground-truth subject description (2-4 descriptive sentences establishing baseline anatomy, composition, colors, and subject matter)
5. "lighting": array of 1-2 lighting styles (e.g. ["Volumetric Studio Light", "Cyberpunk Neon Rim"])
6. "theme": array of 1-2 theme styles (e.g. ["Cosmic Galactic & Nebula", "Apple Glassmorphic Clean"])
7. "era": array of 1 era/mood style (e.g. ["2026 Next-Gen Frontier"])
8. "medium": array of 1 medium/render style (e.g. ["8K Octane 3D Render"])
9. "materials": array of 1-2 materials (e.g. ["Frosted Translucent Glass", "Brushed Titanium Metal"])
10. "custom_tags": array of 3-5 keywords (e.g. ["character", "cyberpunk", "visor", "captain"])
11. "custom_modifiers": comma-separated string of 3-5 technical modifiers (e.g. "subsurface-scattering, octane-render, chromatic-aberration, 8k-resolution")
12. "creative_options": array of 4-6 creative modifier chips or prompt ideas tailored specifically to this archetype & concept that the creator can toggle (e.g. ["Dual visor HUD", "Nebula reflections", "Zero-gravity hair drift", "Golden hour solar flare"])
13. "rationale": 1-2 sentences explaining why this visual recipe creates unbreakable visual consistency.

CRITICAL RULES:
- Output ONLY valid JSON. Do not include markdown code fences or conversational text.
- If the user concept mentions icons, app icons, glyphs, set archetype to "icon_set".
- If the user concept mentions characters, mascots, avatars, people, set archetype to "character".
- If the user concept mentions UI, cards, buttons, dashboard, navigation, set archetype to "ui_component".
- If the user concept mentions logos, brand, emblems, set archetype to "brand_asset".
- If the user concept mentions landscapes, planets, cockpits, environments, set archetype to "environment"."""

        user_content = f"Seed Concept: {concept or 'Next-gen Galactic App Asset'}"
        if arch_hint:
            user_content += f"\nPreferred Archetype: {arch_hint}"
        if app_name:
            user_content += f"\nApplication Context: {app_name}"

        messages = [{"role": "user", "parts": [{"text": user_content}]}]

        raw = call_gemini(messages, system_instruction)
        if raw:
            try:
                clean = raw.strip()
                if clean.startswith("```json"): clean = clean[7:]
                elif clean.startswith("```"): clean = clean[3:]
                if clean.endswith("```"): clean = clean[:-3]
                clean = clean.strip()
                data = json.loads(clean)
                if isinstance(data, dict):
                    return data
            except Exception as e:
                print(f"[SOTService] Parse AI autofill failed: {e}")

        # Intelligent fallbacks based on archetype / concept
        low = concept.lower()
        if "icon" in low or arch_hint == "icon_set":
            return {
                "archetype": "icon_set",
                "suggested_handle": "app-icon-set",
                "recommended_title": "3D Glossy App Icon Set",
                "reference_text": "A cohesive set of modern 3D app icons set inside smooth iOS-style squircles with translucent glass surfaces, glowing core glyphs, and soft ambient drop shadows.",
                "lighting": ["Volumetric Studio Light", "Bioluminescent Ambient Glow"],
                "theme": ["Apple Glassmorphic Clean", "Minimalist Luxury Dark"],
                "era": ["2026 Next-Gen Frontier"],
                "medium": ["8K Octane 3D Render"],
                "materials": ["Frosted Translucent Glass", "Polished Ceramic White"],
                "custom_tags": ["app-icon", "squircle", "3d-render", "ui-asset"],
                "custom_modifiers": "smooth-squircle-curvature, soft-ambient-occlusion, glass-refraction, 8k-octane",
                "creative_options": [
                    "Frosted glass refraction",
                    "Isometric 45-degree perspective",
                    "Vibrant cyan & violet gradient core",
                    "Dual-layer floating glyph",
                    "Subtle specular highlights"
                ],
                "rationale": "High-fidelity squircle styling with frosted glass depth guarantees visual harmony across any app drawer or home screen."
            }
        elif "ui" in low or "card" in low or "hud" in low or arch_hint == "ui_component":
            return {
                "archetype": "ui_component",
                "suggested_handle": "galactic-glass-hud",
                "recommended_title": "Galactic Glassmorphic HUD System",
                "reference_text": "High-performance modular UI card containers and HUD panels with backdrop blur, hairline translucent borders, ambient glowing edge accents, and clean typography rhythm.",
                "lighting": ["Cyberpunk Neon Rim", "Bioluminescent Ambient Glow"],
                "theme": ["Apple Glassmorphic Clean", "Cosmic Galactic & Nebula"],
                "era": ["2026 Next-Gen Frontier"],
                "medium": ["Vector SVG Flat Illustration"],
                "materials": ["Frosted Translucent Glass", "Glowing Neon Wireframe"],
                "custom_tags": ["ui-tokens", "glassmorphism", "hud", "dashboard"],
                "custom_modifiers": "backdrop-filter-blur, hairline-border-0.5px, neon-glow-accents, rounded-2xl",
                "creative_options": [
                    "Ambient cyan edge glow",
                    "Frosted dark slate backdrop",
                    "Tactile micro-interaction focus rings",
                    "Floating status badges",
                    "Compact telemetry graphs"
                ],
                "rationale": "Clean glassmorphic tokens provide optimal contrast, sleek elevation, and responsive modularity."
            }
        else:
            return {
                "archetype": "character" if not arch_hint else arch_hint,
                "suggested_handle": "captain-geppy-sovereign",
                "recommended_title": "Captain Geppy Cosmic Sovereign",
                "reference_text": "Charismatic galactic captain in an obsidian-and-gold flight exosuit with an illuminated cyan visor reflecting distant spiral galaxies, standing proudly on an orbital flight deck.",
                "lighting": ["Cyberpunk Neon Rim", "Volumetric Studio Light"],
                "theme": ["Cosmic Galactic & Nebula", "Cyber-SciFi Holographic"],
                "era": ["2026 Next-Gen Frontier"],
                "medium": ["8K Octane 3D Render"],
                "materials": ["Brushed Titanium Metal", "Glowing Neon Wireframe"],
                "custom_tags": ["character", "hero-asset", "captain-geppy", "space-pilot"],
                "custom_modifiers": "heroic-portrait, subsurface-scattering, cinematic-lighting, gold-inlays",
                "creative_options": [
                    "Illuminated visor telemetry",
                    "Gold-embossed shoulder insignia",
                    "Floating stardust particles",
                    "Obsidian matte chestplate",
                    "Zero-G ambient hair flow"
                ],
                "rationale": "Cinematic volumetric lighting paired with neon rim accents locks in character likeness and futuristic hero presence."
            }

    @staticmethod
    def resolve_mentions(text: str, db: Session) -> Dict[str, Any]:
        """Detect @handle mentions in user text, fetch Contextiles, and compile grounding context."""
        if not text or "@" not in text:
            return {"has_mentions": False, "contextiles": [], "grounding_prompt": ""}

        # Matches @handle-name (alphanumeric, underscore, hyphen)
        handles = set(re.findall(r"@([a-zA-Z0-9_\-]+)", text))
        if not handles:
            return {"has_mentions": False, "contextiles": [], "grounding_prompt": ""}

        matched_contextiles = []
        for handle in handles:
            ctx = db.query(ContextileModel).filter(ContextileModel.name == handle).first()
            if ctx:
                matched_contextiles.append(ctx)

        if not matched_contextiles:
            return {"has_mentions": False, "contextiles": [], "grounding_prompt": ""}

        grounding_lines = ["\n### 🛸 SOURCE OF TRUTH (SOT) GROUNDING CONTEXT (Referenced Contextiles):"]
        for c in matched_contextiles:
            arch = c.archetype or "general"
            arch_meta = ARCHETYPES.get(arch, ARCHETYPES["general"])
            grounding_lines.append(f"- **@{c.name}** [{arch_meta['icon']} Archetype: *{arch_meta['label']}* | Title: *{c.title}*]")
            if c.reference_text:
                grounding_lines.append(f"  - **Reference Baseline**: {c.reference_text}")

            primary = c.primary_image_url or c.reference_image_url
            if primary:
                grounding_lines.append(f"  - **⭐ Primary Reference Image (Main Source of Truth)**: {primary}")

            gallery = c.gallery_images or []
            additional = [img for img in gallery if img != primary]
            if additional:
                grounding_lines.append(f"  - **🖼️ Additional Reference Gallery ({len(additional)} items)**: {', '.join(additional)}")
            elif len(gallery) > 1:
                grounding_lines.append(f"  - **🖼️ Reference Gallery ({len(gallery)} items)**: {', '.join(gallery)}")

            # Archetype-specific generation rules
            if arch == "character":
                grounding_lines.append("  - **Character Consistency Directive**: When generating new poses, scenes, or assets for this character, anchor strictly to the facial structure, hairstyle, armor/outfit colors, and visor styling from the primary reference image, referencing the gallery for context.")
            elif arch == "icon_set":
                grounding_lines.append("  - **App Icon Consistency Directive**: When generating a new app icon, emulate the exact squircle curvature, beveling, shadow depth, material texture, and vibrant lighting palette from the primary reference image and gallery examples so this new icon fits seamlessly into the app collection.")
            elif arch == "ui_component":
                grounding_lines.append("  - **UI Component Directive**: Maintain exact corner radius tokens, glassmorphic backdrop blurs, glow accents, and spacing rhythm.")
            elif arch == "brand_asset":
                grounding_lines.append("  - **Brand Directive**: Strictly preserve brand geometry, color balance, and typography.")
            elif arch == "style":
                grounding_lines.append("  - **Style & Medium Transformation Directive**: When applying this style to another subject, character, or scene, thoroughly transform the visual medium, lighting, color grading, border framing, paper/material texture, and typography into this exact style (e.g. 1970s vintage baseball card, authentic cardboard stock, offset litho print grain, retro team banners, and Kodachrome film saturation) while preserving the core subject likeness.")

            if c.assembled_prompt:
                grounding_lines.append(f"  - **Compiled SOT Prompt**: {c.assembled_prompt}")
            if c.modifiers:
                mods_summary = ", ".join([f"{k}: {v}" for k, v in c.modifiers.items() if v])
                grounding_lines.append(f"  - **Active Modifiers**: {mods_summary}")

        grounding_prompt = "\n".join(grounding_lines) + "\n"

        return {
            "has_mentions": True,
            "contextiles": [
                {
                    "name": c.name,
                    "title": c.title,
                    "archetype": c.archetype,
                    "reference_type": c.reference_type,
                    "reference_text": c.reference_text,
                    "reference_image_url": c.reference_image_url,
                    "primary_image_url": c.primary_image_url,
                    "gallery_images": c.gallery_images,
                    "assembled_prompt": c.assembled_prompt,
                    "modifiers": c.modifiers
                }
                for c in matched_contextiles
            ],
            "grounding_prompt": grounding_prompt
        }

    @staticmethod
    def list_contextiles(db: Session, app_slug: Optional[str] = None) -> List[ContextileModel]:
        """List all saved Contextiles, optionally filtered by app_slug."""
        query = db.query(ContextileModel)
        if app_slug:
            query = query.filter((ContextileModel.app_slug == app_slug) | (ContextileModel.app_slug.is_(None)))
        return query.order_by(ContextileModel.created_at.desc()).all()

    @staticmethod
    def get_contextile(name: str, db: Session) -> Optional[ContextileModel]:
        """Get Contextile by @name handle."""
        return db.query(ContextileModel).filter(ContextileModel.name == name).first()

    @staticmethod
    def create_contextile(data: Dict[str, Any], db: Session) -> ContextileModel:
        """Create and persist a new Contextile with multi-image gallery and archetype support."""
        name = re.sub(r"[^a-zA-Z0-9_\-]", "", data.get("name", "").lower().strip())
        if not name:
            name = f"contextile-{int(datetime.utcnow().timestamp())}"

        archetype = data.get("archetype", "character")
        gallery_images = list(data.get("gallery_images") or [])
        primary_image_url = data.get("primary_image_url")

        # Auto-designate primary image if not set but gallery has images
        if not primary_image_url and gallery_images:
            primary_image_url = gallery_images[0]
        if not primary_image_url and data.get("reference_image_url"):
            primary_image_url = data.get("reference_image_url")
        if primary_image_url and primary_image_url not in gallery_images:
            gallery_images.insert(0, primary_image_url)

        ref_text = data.get("reference_text", "")
        modifiers = data.get("modifiers", {})
        tags = data.get("tags", [])
        variables = list(data.get("variables") or [])
        assembled = data.get("assembled_prompt") or SOTService.compile_prompt(
            ref_text, modifiers, tags, archetype, primary_image_url, gallery_images
        )

        existing = db.query(ContextileModel).filter(ContextileModel.name == name).first()
        if existing:
            existing.title = data.get("title", existing.title)
            existing.description = data.get("description", existing.description)
            existing.archetype = archetype
            existing.reference_type = data.get("reference_type", existing.reference_type)
            existing.reference_text = ref_text
            existing.primary_image_url = primary_image_url
            existing.reference_image_url = primary_image_url or data.get("reference_image_url", existing.reference_image_url)
            existing.gallery_images = gallery_images
            existing.modifiers = modifiers
            existing.tags = tags
            if "variables" in data:
                existing.variables = variables
            existing.assembled_prompt = assembled
            existing.app_slug = data.get("app_slug", existing.app_slug)
            db.commit()
            db.refresh(existing)
            return existing

        ctx = ContextileModel(
            name=name,
            title=data.get("title") or name.replace("-", " ").title(),
            description=data.get("description"),
            archetype=archetype,
            reference_type=data.get("reference_type", "text"),
            reference_text=ref_text,
            reference_image_url=primary_image_url or data.get("reference_image_url"),
            primary_image_url=primary_image_url,
            assembled_prompt=assembled,
            app_slug=data.get("app_slug")
        )
        ctx.gallery_images = gallery_images
        ctx.modifiers = modifiers
        ctx.tags = tags
        ctx.variables = variables

        db.add(ctx)
        db.commit()
        db.refresh(ctx)
        return ctx

    @staticmethod
    def delete_contextile(name: str, db: Session) -> bool:
        """Delete Contextile by name."""
        ctx = db.query(ContextileModel).filter(ContextileModel.name == name).first()
        if not ctx:
            return False
        db.delete(ctx)
        db.commit()
        return True

    @classmethod
    def generate_ai_contextile(
        cls,
        concept: str,
        archetype: Optional[str] = None,
        save_immediately: bool = True,
        db: Optional[Session] = None
    ) -> Dict[str, Any]:
        """
        AI Generates a complete, production-ready Contextile from any user concept
        (e.g. '70s baseball card', 'cyberpunk hologram sticker', 'vintage rubber hose cartoon').
        Crafts the perfect master prompt, subject-replacement template, modifier recipe,
        and renders an authentic visual preview thumbnail.
        """
        seed = (concept or "").strip()
        low = seed.lower()

        # Deduce archetype if not specified
        arch = archetype if (archetype and archetype != "all") else ""
        if not arch:
            if any(k in low for k in ["baseball", "card", "trading", "sticker", "comic", "style", "aesthetic", "medium", "retro", "vintage", "vaporwave", "anime"]):
                arch = "style"
            elif any(k in low for k in ["character", "mascot", "person", "pilot", "captain", "astronaut", "avatar"]):
                arch = "character"
            elif any(k in low for k in ["icon", "squircle", "glyph", "app icon"]):
                arch = "icon_set"
            elif any(k in low for k in ["ui", "hud", "card", "button", "dashboard"]):
                arch = "ui_component"
            elif any(k in low for k in ["logo", "brand", "emblem"]):
                arch = "brand_asset"
            elif any(k in low for k in ["environment", "planet", "landscape", "cockpit"]):
                arch = "environment"
            else:
                arch = "style"

        system_instruction = """You are Captain Geppy's Master Style & Contextile Architect aboard Geppy's GitBridge.
The user wants to generate a complete, production-grade Contextile from their aesthetic concept or idea (e.g. '70s baseball card', 'cyberpunk holographic anime sticker', 'vintage 1930s rubber hose cartoon').

Respond STRICTLY with valid JSON having these fields:
{
  "archetype": "style" | "character" | "icon_set" | "ui_component" | "brand_asset" | "environment" | "general",
  "suggested_handle": "clean-kebab-case-handle",
  "recommended_title": "Punchy High-Impact Display Title",
  "description": "1-2 sentence overview of what this style/contextile encapsulates and how it transforms subjects.",
  "reference_text": "Vivid 2-4 sentence ground-truth reference baseline defining materials, border geometry, color grading, lighting, and print/render techniques.",
  "master_style_prompt": "The definitive, hyper-detailed prompt capturing this exact visual grammar for image generation.",
  "prompt_template": "Template string with {subject} placeholder so any character or object can be rendered in this style (e.g. 'Authentic 1970s vintage baseball card of {subject}, printed on textured cardboard with retro arched team banner, Kodachrome 35mm photography, aged corners, offset litho dots').",
  "lighting": ["Lighting Style 1", "Lighting Style 2"],
  "theme": ["Theme 1", "Theme 2"],
  "era": ["Era 1"],
  "medium": ["Medium 1"],
  "materials": ["Material 1", "Material 2"],
  "custom_tags": ["tag1", "tag2", "tag3", "tag4"],
  "custom_modifiers": "comma-separated technical modifiers",
  "creative_options": ["Option 1", "Option 2", "Option 3", "Option 4"],
  "target_format_hint": "trading_card" | "app_icon" | "banner_hero" | "ui_component" | "avatar",
  "color_palette": ["#HEX1 (Label)", "#HEX2 (Label)", "#HEX3 (Label)", "#HEX4 (Label)"],
  "rationale": "Why this visual recipe creates authentic consistency."
}"""

        messages = [{"role": "user", "parts": [{"text": f"Concept: {seed}\nPreferred Archetype: {arch}"}]}]
        raw = call_gemini(messages, system_instruction)

        parsed_data = None
        if raw:
            try:
                clean = raw.strip()
                if clean.startswith("```json"): clean = clean[7:]
                elif clean.startswith("```"): clean = clean[3:]
                if clean.endswith("```"): clean = clean[:-3]
                clean = clean.strip()
                data = json.loads(clean)
                if isinstance(data, dict) and data.get("suggested_handle"):
                    parsed_data = data
            except Exception as e:
                print(f"[generate_ai_contextile] Parse JSON failed: {e}")

        # Heuristic fallbacks if Gemini fails or is unreachable
        if not parsed_data:
            if "baseball" in low or "card" in low:
                parsed_data = {
                    "archetype": "style",
                    "suggested_handle": "70s-baseball-card",
                    "recommended_title": "1970s Vintage Baseball Card",
                    "description": "Authentic 1970s Topps-style sports trading card aesthetic with aged cardboard borders, bold arched team banners, Kodachrome film grain, and offset litho print texture.",
                    "reference_text": "Authentic 1970s vintage baseball card aesthetic: heavy aged matte cardboard paper stock with soft buff off-white borders, vibrant retro offset lithograph print grain, curved arched team banner typography across the top, round star position badge, Kodachrome 35mm sports photography saturation, and subtle corner aging.",
                    "master_style_prompt": "Authentic 1970s Topps-style vintage baseball card, printed on textured buff cardboard stock with retro arched header banner typography, circular star player position badge, Kodachrome 35mm film photography, aged card borders, subtle corner wear, and offset lithography dot matrix print texture.",
                    "prompt_template": "Authentic 1970s vintage baseball card of {subject}, printed on textured cardboard with retro arched team banner typography, Kodachrome 35mm photography, aged corners, offset litho print dots, high contrast vintage sports photography.",
                    "lighting": ["High-Key Commercial Softbox", "Golden Hour Sunbeam"],
                    "theme": ["Retro 70s Americana Sports & Vintage Print"],
                    "era": ["1970s Vintage Retro"],
                    "medium": ["Vintage Lithograph Cardboard Print / 35mm Kodachrome Film"],
                    "materials": ["Aged Matte Cardboard Stock / Textured Paper"],
                    "custom_tags": ["70s-baseball-card", "trading-card", "vintage-topps", "sports-card", "retro-print"],
                    "custom_modifiers": "vintage-cardboard-stock, arched-team-banner, kodachrome-saturation, 1970s-offset-print, aged-card-borders",
                    "creative_options": ["Arched team banner header", "Round position star badge", "Faded Kodachrome film grain", "Worn cardboard corner texture", "Dual-tone inner border"],
                    "target_format_hint": "trading_card",
                    "color_palette": ["#F5EDE0 (Cardboard Buff)", "#DC2626 (Retro Red)", "#F59E0B (Topps Gold)", "#1E3A8A (Vintage Navy)"],
                    "rationale": "1970s cardboard stock with arched team banners and Kodachrome color grading delivers instantaneous, nostalgic trading card authenticity."
                }
            elif "sticker" in low or "hologram" in low:
                parsed_data = {
                    "archetype": "style",
                    "suggested_handle": "cyberpunk-holographic-sticker",
                    "recommended_title": "Cyberpunk Holographic Die-Cut Sticker",
                    "description": "Iridescent prism foil sticker with thick die-cut white borders, reflective chrome sheen, and high-contrast cyberpunk neon graphics.",
                    "reference_text": "Die-cut glossy vinyl sticker with holographic prism foil underlay, thick white contour border, specular rainbow reflections across tilted angles, and ultra-saturated neon cyan and magenta palette.",
                    "master_style_prompt": "Die-cut holographic vinyl sticker, iridescent prism rainbow sheen, thick glossy white die-cut border, reflective specular chrome highlights, cyber neon vector aesthetic.",
                    "prompt_template": "Die-cut holographic cyberpunk sticker of {subject}, featuring iridescent rainbow sheen, glossy white die-cut outline, reflective prism foil, vibrant neon accents.",
                    "lighting": ["Cyberpunk Neon Rim", "Cinematic Anamorphic Flare"],
                    "theme": ["Cyber-SciFi Holographic"],
                    "era": ["2026 Next-Gen Frontier"],
                    "medium": ["Glossy Product Packaging Render"],
                    "materials": ["Iridescent Liquid Hologram"],
                    "custom_tags": ["hologram", "sticker", "die-cut", "cyberpunk", "prism-foil"],
                    "custom_modifiers": "die-cut-white-border, iridescent-prism-reflection, glossy-vinyl, high-gloss-sheen",
                    "creative_options": ["Rainbow diffraction grating", "Die-cut contour margin", "Chrome foil text", "Glossy reflection line"],
                    "target_format_hint": "app_icon",
                    "color_palette": ["#00F2FE (Holo Cyan)", "#F43F5E (Neon Pink)", "#A855F7 (Prism Violet)", "#FFFFFF (Die-Cut White)"],
                    "rationale": "Iridescent prism reflections combined with die-cut borders create a tangible, collectible sticker vibe."
                }
            elif arch == "output" or "output" in low or "diecut" in low or "print" in low or "pdf" in low:
                parsed_data = {
                    "archetype": "output",
                    "suggested_handle": "diecut-sticker-3in-pdf" if ("sticker" in low or "diecut" in low) else "print-spec-300dpi-pdf",
                    "recommended_title": "3\" Die-Cut Vinyl Sticker (300 DPI PDF)" if ("sticker" in low or "diecut" in low) else "Print-Ready 300 DPI PDF Spec",
                    "description": "Output specification for transparent die-cut vinyl stickers with 4mm white border, 0.125\" bleed, kiss-cut registration guidelines, and 300 DPI print-ready PDF.",
                    "reference_text": "Physical vinyl die-cut sticker output with transparent background, solid white contour edge (18px), 0.125\" bleed margin, corner crop marks, and 300 DPI print-ready PDF format.",
                    "master_style_prompt": "Output Finishing Spec: Transparent background removal, 4mm die-cut white vinyl contour border, 3x3 inch print sizing at 300 DPI, full bleed margins, and CMYK print-ready PDF with registration marks.",
                    "prompt_template": "Print-ready die-cut sticker finish for {subject}: 3x3 inches @ 300 DPI, transparent alpha background, 18px white vinyl contour stroke, crop marks, and PDF export.",
                    "background_mode": "white_diecut" if ("sticker" in low or "diecut" in low) else "transparent",
                    "print_size": "diecut_sticker_3in",
                    "bg_tolerance": 35,
                    "edge_feather": 2,
                    "diecut_stroke_width": 18,
                    "diecut_stroke_color": "#FFFFFF",
                    "bleed_in": 0.125,
                    "show_crop_marks": True,
                    "show_cut_line": True,
                    "export_pdf": True,
                    "dpi": 300,
                    "lighting": ["High-Key Commercial Softbox"],
                    "theme": ["Apple Glassmorphic Clean"],
                    "era": ["2026 Next-Gen Frontier"],
                    "medium": ["Glossy Product Packaging Render"],
                    "materials": ["Aged Matte Cardboard Stock / Textured Paper"],
                    "custom_tags": ["output", "diecut-sticker", "print-pdf", "300dpi", "transparent"],
                    "custom_modifiers": "transparent-alpha, die-cut-white-rim, 300dpi-print-pdf, crop-marks, bleed-margins",
                    "creative_options": ["4mm white vinyl contour", "0.125\" bleed margin", "Corner crop crosshairs", "300 DPI PDF export"],
                    "target_format_hint": "print_pdf",
                    "color_palette": ["#FFFFFF (Vinyl White)", "#06B6D4 (Cut Line Cyan)", "#EC4899 (Registration Magenta)", "#0F172A (Printer Black)"],
                    "rationale": "High-DPI die-cut sticker output spec standardizes background removal, white contour borders, and CMYK-ready print files."
                }
            else:
                handle_slug = re.sub(r"[^a-z0-9\-]", "", seed.lower().replace(" ", "-")) or "custom-style"
                parsed_data = {
                    "archetype": arch,
                    "suggested_handle": handle_slug,
                    "recommended_title": seed.title(),
                    "description": f"Custom visual style anchoring {seed} with distinct materials, lighting, and palette.",
                    "reference_text": f"High-fidelity aesthetic reference for {seed} with tailored lighting, detailed textures, and cohesive visual composition.",
                    "master_style_prompt": f"Master aesthetic rendering of {seed}, featuring rich atmospheric lighting, cohesive materials, high definition details.",
                    "prompt_template": f"{seed} aesthetic applied to {{subject}}, with signature lighting, authentic materials, and fine-tuned composition.",
                    "lighting": ["Volumetric Studio Light"],
                    "theme": ["Cosmic Galactic & Nebula"],
                    "era": ["2026 Next-Gen Frontier"],
                    "medium": ["8K Octane 3D Render"],
                    "materials": ["Frosted Translucent Glass"],
                    "custom_tags": [handle_slug, "context-style", "custom-sot"],
                    "custom_modifiers": "high-definition, fine-tuned-composition, authentic-materials",
                    "creative_options": ["Accent lighting", "High detail texture", "Atmospheric depth"],
                    "target_format_hint": "app_icon",
                    "color_palette": ["#6366F1 (Indigo)", "#06B6D4 (Cyan)", "#F59E0B (Gold)", "#0F172A (Obsidian)"],
                    "rationale": "Cohesive style anchors give prompt engines unbreakable visual consistency."
                }

        handle = parsed_data.get("suggested_handle", "new-contextile")
        title = parsed_data.get("recommended_title", handle.replace("-", " ").title())
        archetype_out = parsed_data.get("archetype", arch or "style")
        color_palette = parsed_data.get("color_palette") or []

        # Generate preview thumbnail image
        preview_url = generate_contextile_thumbnail(
            handle=handle,
            title=title,
            concept=seed,
            archetype=archetype_out,
            color_palette=color_palette,
            reference_text=parsed_data.get("reference_text"),
            master_style_prompt=parsed_data.get("master_style_prompt")
        )

        modifiers_dict = {
            "lighting": parsed_data.get("lighting") or [],
            "theme": parsed_data.get("theme") or [],
            "era": parsed_data.get("era") or [],
            "medium": parsed_data.get("medium") or [],
            "materials": parsed_data.get("materials") or [],
            "custom": [parsed_data.get("custom_modifiers", "")]
        }

        # Populate Output Finishing Specification if applicable
        if archetype_out == "output" or parsed_data.get("background_mode") or parsed_data.get("print_size"):
            modifiers_dict["background_mode"] = parsed_data.get("background_mode", "white_diecut")
            modifiers_dict["print_size"] = parsed_data.get("print_size", "diecut_sticker_3in")
            modifiers_dict["bg_tolerance"] = parsed_data.get("bg_tolerance", 35)
            modifiers_dict["edge_feather"] = parsed_data.get("edge_feather", 2)
            modifiers_dict["diecut_stroke_width"] = parsed_data.get("diecut_stroke_width", 18)
            modifiers_dict["diecut_stroke_color"] = parsed_data.get("diecut_stroke_color", "#FFFFFF")
            modifiers_dict["bleed_in"] = parsed_data.get("bleed_in", 0.125)
            modifiers_dict["show_crop_marks"] = parsed_data.get("show_crop_marks", True)
            modifiers_dict["show_cut_line"] = parsed_data.get("show_cut_line", True)
            modifiers_dict["export_pdf"] = parsed_data.get("export_pdf", True)
            modifiers_dict["dpi"] = parsed_data.get("dpi", 300)

        compiled = SOTService.compile_prompt(
            reference_text=parsed_data.get("reference_text", ""),
            modifiers=modifiers_dict,
            custom_tags=parsed_data.get("custom_tags") or [],
            archetype=archetype_out,
            primary_image_url=preview_url,
            gallery_images=[preview_url] if preview_url else []
        )

        result = {
            "name": handle,
            "title": title,
            "description": parsed_data.get("description"),
            "archetype": archetype_out,
            "reference_type": "hybrid" if preview_url else "text",
            "reference_text": parsed_data.get("reference_text"),
            "master_style_prompt": parsed_data.get("master_style_prompt"),
            "prompt_template": parsed_data.get("prompt_template"),
            "primary_image_url": preview_url,
            "reference_image_url": preview_url,
            "gallery_images": [preview_url] if preview_url else [],
            "modifiers": modifiers_dict,
            "tags": parsed_data.get("custom_tags") or [],
            "custom_modifiers": parsed_data.get("custom_modifiers", ""),
            "creative_options": parsed_data.get("creative_options") or [],
            "target_format_hint": parsed_data.get("target_format_hint", "app_icon"),
            "color_palette": color_palette,
            "rationale": parsed_data.get("rationale", ""),
            "assembled_prompt": compiled
        }

        # Save to database if requested
        if save_immediately and db:
            ctx = SOTService.create_contextile({
                "name": handle,
                "title": title,
                "description": result.get("description"),
                "archetype": archetype_out,
                "reference_type": result.get("reference_type"),
                "reference_text": result.get("reference_text"),
                "primary_image_url": preview_url,
                "reference_image_url": preview_url,
                "gallery_images": result.get("gallery_images"),
                "modifiers": modifiers_dict,
                "tags": result.get("tags"),
                "assembled_prompt": compiled
            }, db)
            result["id"] = ctx.id
            result["saved"] = True
            result["message"] = f"Contextile '@{handle}' created and saved to SOT Fleet!"
        else:
            result["saved"] = False

        return result

    @staticmethod
    def seed_default_contextiles(db: Session):
        """Seed default starter Contextiles for Captain Geppy, icon sets, and galactic cards."""
        captain_ctx = db.query(ContextileModel).filter(ContextileModel.name == "captain-geppy").first()
        if not captain_ctx:
            SOTService.create_contextile({
                "name": "captain-geppy",
                "title": "Captain Geppy (Galactic Commander)",
                "description": "The cosmic captain navigating the Galaxy of AI-crafted applications.",
                "archetype": "character",
                "reference_type": "text",
                "reference_text": "Charismatic cosmic astronaut commander wearing an obsidian-and-gold flight suit with an illuminated translucent cyan visor reflecting swirling nebula galaxies. Gold commander bars and galactic crest.",
                "modifiers": {
                    "lighting": ["Cyberpunk Neon Rim", "Moody Starlight Backlight"],
                    "theme": ["Cosmic Galactic & Nebula"],
                    "era": ["2026 Next-Gen Frontier"],
                    "medium": ["8K Octane 3D Render"],
                    "materials": ["Brushed Titanium Metal", "Glowing Neon Wireframe"]
                },
                "tags": ["persona", "captain", "galaxy-commander"],
                "assembled_prompt": "[SOT Character Anchor - Preserve facial likeness, suit design, and character identity] | Charismatic cosmic astronaut commander wearing an obsidian-and-gold flight suit with an illuminated translucent cyan visor reflecting swirling nebula galaxies | Visual Theme: Cosmic Galactic & Nebula | Lighting: Cyberpunk Neon Rim, Moody Starlight Backlight | Era/Mood: 2026 Next-Gen Frontier | Render Style: 8K Octane 3D Render | Materials & Textures: Brushed Titanium Metal, Glowing Neon Wireframe"
            }, db)

        icon_set = db.query(ContextileModel).filter(ContextileModel.name == "galactic-icons").first()
        if not icon_set:
            SOTService.create_contextile({
                "name": "galactic-icons",
                "title": "Galactic App Icons Style Guide",
                "description": "Source of Truth for creating cohesive app icons across the galaxy with 3D squircle depth, bevel shadows, and glowing glyphs.",
                "archetype": "icon_set",
                "reference_type": "text",
                "reference_text": "Uniform squircle app icon collection featuring centered 3D metallic or glass glyphs, gentle bevel shadows, micro-radiance rim glow, and subtle cosmic slate gradient backgrounds.",
                "modifiers": {
                    "lighting": ["Volumetric Studio Light", "Cyberpunk Neon Rim"],
                    "theme": ["Apple Glassmorphic Clean", "Cosmic Galactic & Nebula"],
                    "era": ["2026 Next-Gen Frontier"],
                    "medium": ["8K Octane 3D Render"],
                    "materials": ["Frosted Translucent Glass", "Brushed Titanium Metal"]
                },
                "tags": ["app-icon", "icon-set", "design-system", "squircle"],
                "assembled_prompt": "[SOT App Icon Style Guide - Cohesive 3D squircle silhouette, beveling, lighting, and icon grammar] | Uniform squircle app icon collection featuring centered 3D metallic or glass glyphs, gentle bevel shadows, micro-radiance rim glow, and subtle cosmic slate gradient backgrounds | Visual Theme: Apple Glassmorphic Clean, Cosmic Galactic & Nebula | Lighting: Volumetric Studio Light, Cyberpunk Neon Rim | Era/Mood: 2026 Next-Gen Frontier | Render Style: 8K Octane 3D Render | Materials & Textures: Frosted Translucent Glass, Brushed Titanium Metal"
            }, db)

        neon_card = db.query(ContextileModel).filter(ContextileModel.name == "galactic-card-ui").first()
        if not neon_card:
            SOTService.create_contextile({
                "name": "galactic-card-ui",
                "title": "Galactic Glassmorphic Card UI",
                "description": "Standard Source of Truth for cards, containers, and dashboard tiles across the galaxy.",
                "archetype": "ui_component",
                "reference_type": "text",
                "reference_text": "Modern SaaS UI card component with ultra-clean rounded corners, subtle translucent dark glass backdrop blur, and micro-thin illuminated cyan and violet border glow.",
                "modifiers": {
                    "lighting": ["Volumetric Studio Light"],
                    "theme": ["Apple Glassmorphic Clean", "Minimalist Luxury Dark"],
                    "era": ["2026 Next-Gen Frontier"],
                    "medium": ["Glossy Product Render"],
                    "materials": ["Frosted Translucent Glass"]
                },
                "tags": ["ui-component", "design-system", "glassmorphism"],
                "assembled_prompt": "[SOT UI Component System - Glassmorphic blur, rounded borders, and UI hierarchy] | Modern SaaS UI card component with ultra-clean rounded corners, subtle translucent dark glass backdrop blur, and micro-thin illuminated cyan and violet border glow | Visual Theme: Apple Glassmorphic Clean, Minimalist Luxury Dark | Lighting: Volumetric Studio Light | Era/Mood: 2026 Next-Gen Frontier | Render Style: Glossy Product Render | Materials & Textures: Frosted Translucent Glass"
            }, db)

        # Seed Output Contextiles for Chat Stickers & Print Merch
        chat_sticker = db.query(ContextileModel).filter(ContextileModel.name == "chat-sticker").first()
        if not chat_sticker:
            stk_thumb = generate_contextile_thumbnail(
                handle="chat-sticker",
                title="Transparent Chat Sticker",
                concept="512x512 transparent PNG chat sticker with subtle white contour",
                archetype="output",
                color_palette=["#06B6D4", "#FFFFFF", "#0F172A"]
            )
            SOTService.create_contextile({
                "name": "chat-sticker",
                "title": "Transparent Chat Sticker (512px)",
                "description": "Output specification for transparent 512x512 chat stickers with background removed and crisp white anti-bleed edge.",
                "archetype": "output",
                "reference_type": "hybrid" if stk_thumb else "text",
                "reference_text": "Standard 512x512 transparent PNG chat sticker with background removed and crisp 8px white contour edge for dark & light mode chat apps (Discord, Slack, Telegram).",
                "primary_image_url": stk_thumb,
                "reference_image_url": stk_thumb,
                "modifiers": {
                    "background_mode": "transparent",
                    "print_size": "chat_sticker_512",
                    "bg_tolerance": 35,
                    "edge_feather": 2,
                    "diecut_stroke_width": 8,
                    "diecut_stroke_color": "#FFFFFF",
                    "export_pdf": False,
                    "dpi": 300
                },
                "tags": ["output", "chat-sticker", "transparent", "discord", "slack"],
                "assembled_prompt": "[SOT Output & Print Finishing Spec - Background treatment, die-cut contours, bleed margins, crop marks, and 300 DPI layout] | Standard 512x512 transparent PNG chat sticker with background removed and crisp 8px white contour edge for dark & light mode chat apps (Discord, Slack, Telegram) | Finishing Output: transparent | Size: chat_sticker_512 @ 300 DPI"
            }, db)

        diecut_sticker = db.query(ContextileModel).filter(ContextileModel.name == "diecut-sticker-3in").first()
        if not diecut_sticker:
            dc_thumb = generate_contextile_thumbnail(
                handle="diecut-sticker-3in",
                title="3\" Die-Cut Vinyl Sticker",
                concept="3x3 inch vinyl physical sticker with 4mm solid white contour border, 0.125\" bleed, kiss-cut lines, and 300 DPI PDF",
                archetype="output",
                color_palette=["#FFFFFF", "#EC4899", "#06B6D4"]
            )
            SOTService.create_contextile({
                "name": "diecut-sticker-3in",
                "title": "3\" Physical Die-Cut Sticker (300 DPI + PDF)",
                "description": "3\"x3\" vinyl physical sticker with 4mm solid white die-cut contour border, transparent backdrop, 0.125\" bleed, kiss-cut registration lines, and 300 DPI print-ready PDF.",
                "archetype": "output",
                "reference_type": "hybrid" if dc_thumb else "text",
                "reference_text": "3x3 inch vinyl physical sticker with 4mm solid white die-cut contour border, transparent backdrop, 0.125\" bleed, kiss-cut registration lines, and 300 DPI print-ready PDF.",
                "primary_image_url": dc_thumb,
                "reference_image_url": dc_thumb,
                "modifiers": {
                    "background_mode": "white_diecut",
                    "print_size": "diecut_sticker_3in",
                    "width_in": 3.0,
                    "height_in": 3.0,
                    "bg_tolerance": 35,
                    "edge_feather": 2,
                    "diecut_stroke_width": 18,
                    "diecut_stroke_color": "#FFFFFF",
                    "bleed_in": 0.125,
                    "show_crop_marks": True,
                    "show_cut_line": True,
                    "export_pdf": True,
                    "dpi": 300
                },
                "tags": ["output", "diecut-sticker", "physical-merch", "print-pdf", "300dpi"],
                "assembled_prompt": "[SOT Output & Print Finishing Spec - Background treatment, die-cut contours, bleed margins, crop marks, and 300 DPI layout] | 3x3 inch vinyl physical sticker with 4mm solid white die-cut contour border, transparent backdrop, 0.125\" bleed, kiss-cut registration lines, and 300 DPI print-ready PDF | Finishing Output: white_diecut | Size: diecut_sticker_3in @ 300 DPI"
            }, db)

        tc_print = db.query(ContextileModel).filter(ContextileModel.name == "tradingcard-300dpi-pdf").first()
        if not tc_print:
            tc_thumb = generate_contextile_thumbnail(
                handle="tradingcard-300dpi-pdf",
                title="Trading Card 300 DPI PDF",
                concept="2.5x3.5 inch trading card print spec with 1/8\" bleed extension, crop crosshairs, and 300 DPI PDF",
                archetype="output",
                color_palette=["#DC2626", "#F59E0B", "#1E3A8A"]
            )
            SOTService.create_contextile({
                "name": "tradingcard-300dpi-pdf",
                "title": "Trading Card Print-Ready PDF (2.5\" x 3.5\" @ 300 DPI)",
                "description": "Commercial print specification for 2.5x3.5 inch trading cards with full 1/8\" bleed extension, corner crop crosshairs, CMYK calibration swatches, and 300 DPI PDF.",
                "archetype": "output",
                "reference_type": "hybrid" if tc_thumb else "text",
                "reference_text": "Commercial print specification for 2.5x3.5 inch trading cards with full 1/8\" bleed extension, corner crop crosshairs, CMYK calibration swatches, and 300 DPI PDF.",
                "primary_image_url": tc_thumb,
                "reference_image_url": tc_thumb,
                "modifiers": {
                    "background_mode": "preserve",
                    "print_size": "trading_card_print",
                    "width_in": 2.5,
                    "height_in": 3.5,
                    "bleed_in": 0.125,
                    "fill_bleed": True,
                    "show_crop_marks": True,
                    "show_cut_line": False,
                    "export_pdf": True,
                    "dpi": 300
                },
                "tags": ["output", "trading-card", "print-pdf", "300dpi", "bleed-marks"],
                "assembled_prompt": "[SOT Output & Print Finishing Spec - Background treatment, die-cut contours, bleed margins, crop marks, and 300 DPI layout] | Commercial print specification for 2.5x3.5 inch trading cards with full 1/8\" bleed extension, corner crop crosshairs, CMYK calibration swatches, and 300 DPI PDF | Finishing Output: preserve | Size: trading_card_print @ 300 DPI"
            }, db)

        art_print = db.query(ContextileModel).filter(ContextileModel.name == "art-print-8x10-pdf").first()
        if not art_print:
            ap_thumb = generate_contextile_thumbnail(
                handle="art-print-8x10-pdf",
                title="8\" x 10\" Art Print PDF",
                concept="8x10 inch art print with 0.125\" bleed, printer registration bullseyes, and 300 DPI PDF",
                archetype="output",
                color_palette=["#0F172A", "#6366F1", "#06B6D4"]
            )
            SOTService.create_contextile({
                "name": "art-print-8x10-pdf",
                "title": "8\" x 10\" Art Print (300 DPI + Frame Border)",
                "description": "Standard 8x10 inch high-resolution gallery art print with 0.125\" bleed, printer registration bullseyes, and 300 DPI output for framing.",
                "archetype": "output",
                "reference_type": "hybrid" if ap_thumb else "text",
                "reference_text": "Standard 8x10 inch high-resolution gallery art print with 0.125\" bleed, printer registration bullseyes, and 300 DPI output for framing.",
                "primary_image_url": ap_thumb,
                "reference_image_url": ap_thumb,
                "modifiers": {
                    "background_mode": "preserve",
                    "print_size": "art_print_8x10",
                    "width_in": 8.0,
                    "height_in": 10.0,
                    "bleed_in": 0.125,
                    "show_crop_marks": True,
                    "show_cut_line": False,
                    "export_pdf": True,
                    "dpi": 300
                },
                "tags": ["output", "art-print", "poster", "frame-ready", "print-pdf"],
                "assembled_prompt": "[SOT Output & Print Finishing Spec - Background treatment, die-cut contours, bleed margins, crop marks, and 300 DPI layout] | Standard 8x10 inch high-resolution gallery art print with 0.125\" bleed, printer registration bullseyes, and 300 DPI output for framing | Finishing Output: preserve | Size: art_print_8x10 @ 300 DPI"
            }, db)

        # Seed Dynamic Template Variables for Diamond Dreams '70s Baseball Card
        baseball_card = db.query(ContextileModel).filter(ContextileModel.name == "70s-baseball-card").first()
        if baseball_card and not baseball_card.variables:
            baseball_card.variables = [
                {
                    "key": "team_name",
                    "label": "Team Name",
                    "default_value": "GEPPY'S GALACTIC ALL-STARS",
                    "value": "GEPPY'S GALACTIC ALL-STARS",
                    "type": "text",
                    "description": "Team banner displayed across the top of the card"
                },
                {
                    "key": "player_name",
                    "label": "Player Name",
                    "default_value": "CAPTAIN GEPPY",
                    "value": "CAPTAIN GEPPY",
                    "type": "text",
                    "description": "Player name displayed on the bottom nameplate"
                },
                {
                    "key": "position",
                    "label": "Player Position",
                    "default_value": "CAPTAIN",
                    "value": "CAPTAIN",
                    "type": "text",
                    "description": "Position badge displayed inside upper right star"
                },
                {
                    "key": "stats",
                    "label": "Career / Season Stats",
                    "default_value": "STARFLEET PILOT • .342 AVG • 48 HR • SOT ALL-GALAXY",
                    "value": "STARFLEET PILOT • .342 AVG • 48 HR • SOT ALL-GALAXY",
                    "type": "text",
                    "description": "Stat summary line underneath the player name"
                },
                {
                    "key": "card_number",
                    "label": "Card Number",
                    "default_value": "#76",
                    "value": "#76",
                    "type": "text",
                    "description": "Collector card number in corner"
                },
                {
                    "key": "year_era",
                    "label": "Card Year / Era",
                    "default_value": "'76",
                    "value": "'76",
                    "type": "text",
                    "description": "Vintage release year in footer"
                }
            ]
            db.commit()

    @classmethod
    def suggest_variables_for_concept(cls, concept: str = "", archetype: str = "character", reference_text: str = "") -> List[Dict[str, Any]]:
        """
        Suggest variable slots (e.g. team_name, player_name, position, stats) based on contextile concept, archetype, or reference text.
        """
        low = (concept + " " + archetype + " " + reference_text).lower()
        if "baseball" in low or "card" in low or "trading" in low:
            return [
                {"key": "team_name", "label": "Team Name", "default_value": "GEPPY'S GALACTIC ALL-STARS", "value": "GEPPY'S GALACTIC ALL-STARS", "type": "text", "description": "Team banner text at top"},
                {"key": "player_name", "label": "Player Name", "default_value": "CAPTAIN GEPPY", "value": "CAPTAIN GEPPY", "type": "text", "description": "Player name banner at bottom"},
                {"key": "position", "label": "Player Position", "default_value": "CAPTAIN", "value": "CAPTAIN", "type": "text", "description": "Position star badge"},
                {"key": "stats", "label": "Stats Summary", "default_value": "STARFLEET PILOT • .342 AVG • 48 HR • SOT ALL-GALAXY", "value": "STARFLEET PILOT • .342 AVG • 48 HR • SOT ALL-GALAXY", "type": "text", "description": "Season or career stat line"},
                {"key": "card_number", "label": "Card Number", "default_value": "#76", "value": "#76", "type": "text", "description": "Collector series card number"},
                {"key": "year_era", "label": "Year / Era", "default_value": "'76", "value": "'76", "type": "text", "description": "Vintage year stamp"}
            ]
        elif archetype == "character" or "mascot" in low or "hero" in low:
            return [
                {"key": "character_name", "label": "Character Name", "default_value": "Captain Geppy", "value": "Captain Geppy", "type": "text", "description": "Primary identity name"},
                {"key": "role_title", "label": "Rank / Class", "default_value": "Galactic Commander", "value": "Galactic Commander", "type": "text", "description": "Official title or combat class"},
                {"key": "power_level", "label": "Power Rating", "default_value": "9,000+", "value": "9,000+", "type": "text", "description": "Power or energy metric"},
                {"key": "special_gear", "label": "Signature Gear", "default_value": "Translucent Cyan Visor & Obsidian Armor", "value": "Translucent Cyan Visor & Obsidian Armor", "type": "text", "description": "Key equipment slot"}
            ]
        elif archetype == "icon_set" or "icon" in low or "app" in low:
            return [
                {"key": "app_title", "label": "App Title", "default_value": "Geppy's Galactic", "value": "Geppy's Galactic", "type": "text", "description": "Application or module name"},
                {"key": "glyph_symbol", "label": "Glyph Motif", "default_value": "Orbital Warp Ring", "value": "Orbital Warp Ring", "type": "text", "description": "Central 3D icon element"},
                {"key": "badge_count", "label": "Badge Value", "default_value": "LIVE", "value": "LIVE", "type": "text", "description": "Notification or state pill"},
                {"key": "version_tag", "label": "Version Tag", "default_value": "v2.0", "value": "v2.0", "type": "text", "description": "Software release version"}
            ]
        elif archetype == "ui_component" or "dashboard" in low or "hud" in low:
            return [
                {"key": "component_title", "label": "Widget Title", "default_value": "Telemetry Radar", "value": "Telemetry Radar", "type": "text", "description": "Card header label"},
                {"key": "primary_metric", "label": "Key Metric", "default_value": "99.98% Orbit", "value": "99.98% Orbit", "type": "text", "description": "Primary display stat"},
                {"key": "status_badge", "label": "Status", "default_value": "OPERATIONAL", "value": "OPERATIONAL", "type": "text", "description": "Health status pill"}
            ]
        else:
            return [
                {"key": "label", "label": "Custom Label", "default_value": "Galactic Standard", "value": "Galactic Standard", "type": "text", "description": "Custom variable slot"},
                {"key": "stat", "label": "Key Stat", "default_value": "100%", "value": "100%", "type": "text", "description": "Metric or property slot"}
            ]
