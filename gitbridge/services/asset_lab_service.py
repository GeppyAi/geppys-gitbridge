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

# Default Gemini models for synthesis
GEMINI_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gemini-1.5-pro"
]

def call_gemini(messages: List[Dict[str, Any]], system_instruction: str) -> Optional[str]:
    """Call Google Gemini Generative Language API with fallback sequence."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None

    for model in GEMINI_MODELS:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
            payload = {
                "contents": messages,
                "systemInstruction": {"parts": [{"text": system_instruction}]}
            }
            res = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=25)
            if res.status_code == 200:
                data = res.json()
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts:
                        return parts[0].get("text", "").strip()
        except Exception as e:
            print(f"[AssetLabService] Gemini call failed on {model}: {e}")
            continue
    return None

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
    def synthesize_blend(
        cls,
        ingredients: List[Dict[str, Any]],
        custom_prompt: str,
        target_format: str = "app_icon",
        fidelity_mode: str = "balanced",
        overrides: Dict[str, Any] = None,
        reference_images: List[str] = None,
        app_context: Optional[str] = None,
        variables: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Synthesize multiple SOT Contextiles, reference images, and directives
        into a unified, fine-tuned Master Asset Generation Blueprint.
        """
        overrides = overrides or {}
        reference_images = reference_images or []
        variables = variables or {}

        # System Instruction for the AI Style Synthesizer
        system_instruction = """You are Captain Geppy's Chief Holodeck & Style Synthesizer aboard Geppy's GitBridge.
Your duty is to fuse multiple disparate Sources of Truth (SOT) contextiles, visual references, and creator requirements into a cohesive Master Asset Blueprint.

ROLES of Contextiles:
- "subject": The primary character, mascot, or central object likeness to preserve.
- "style": The thematic frame, artistic medium, aesthetic genre, or format (e.g. 70s vintage baseball card, cyberpunk holographic sticker, 1930s rubber hose cartoon, iOS 3D squircle).
- "lighting": Volumetric lighting, rim glow, shadows, and atmospheric color temperature.
- "materials": Surface texture, cardboard paper stock, frosted glass, brushed metals, ceramic gloss, or neon.

CRITICAL INSTRUCTION FOR SUBJECT + STYLE FUSION:
When the user pairs a "subject" (e.g. Captain Geppy) with a "style" (e.g. 70s baseball card):
- The Master Prompt MUST depict the Subject as the star figure INSIDE that exact style and format! (e.g. "Authentic 1970s Topps-style vintage baseball card featuring Captain Geppy as the star galactic commander, rendered with 35mm Kodachrome film grain, printed on aged cardboard stock with arched team banner typography reading 'GALACTIC CAPTAIN', round star position badge, worn cardboard corners, and nostalgic offset litho print texture.")
- If dynamic variables/slots are provided (such as team name, player name, position, stats, card number, or year era), reflect these exact variable values within the typography and details of the Master Prompt and Composition Blueprint!
- Set suggested target format to "trading_card" if the style is a baseball card or trading card.
- Set suggested aspect ratio to "2.5:3.5" (or "1:1") for cards.
- Title should reflect the fusion, e.g. "1970s Vintage Baseball Card: Captain Geppy".

Respond ONLY with valid JSON in this exact structure:
{
  "title": "Creative Asset Title",
  "master_prompt": "Exquisite prompt describing the hybrid asset in hyper-fine detail. Seamlessly transpose the subject into the style/medium/format with all authentic textures, lighting, and framing.",
  "negative_prompt": "blurry, low quality, distorted anatomy, photoreal human skin, pixelated edges, out of frame",
  "color_palette": ["#F5EDE0 (Cardboard Buff)", "#DC2626 (Retro Red)", "#F59E0B (Commander Gold)", "#1E3A8A (Vintage Navy)"],
  "composition_blueprint": "Authentic 1970s trading card with arched team banner, player portrait photo window, star position badge, and aged cardboard margin.",
  "style_fusion_notes": "Transposed @captain-geppy character likeness into the @70s-baseball-card vintage lithograph cardboard medium.",
  "suggested_aspect_ratio": "2.5:3.5"
}"""

        user_content = f"Target Format: {target_format}\nFidelity Mode: {fidelity_mode}\n"
        if app_context:
            user_content += f"Target App: {app_context}\n"
        user_content += f"Creator Directives: {custom_prompt or 'Create a fine-tuned flagship asset combining our SOT references.'}\n\n"

        user_content += "ACTIVE SOT CONTEXTILE INGREDIENTS:\n"
        for idx, ing in enumerate(ingredients, 1):
            name = ing.get("name", f"item-{idx}")
            role = ing.get("role", "style")
            title = ing.get("title", name)
            ref_text = ing.get("reference_text", "")
            modifiers = ing.get("modifiers", {})
            user_content += f"[{idx}] @{name} (Role: {role.upper()}, Title: {title})\n"
            if ref_text:
                user_content += f"    Base Truth: {ref_text}\n"
            if modifiers:
                user_content += f"    Modifiers: {json.dumps(modifiers)}\n"

        if variables:
            user_content += f"\nDYNAMIC TEMPLATE VARIABLES & VALUES: {json.dumps(variables, indent=2)}\n"
        if overrides:
            user_content += f"\nOverrides & Nuances: {json.dumps(overrides)}\n"
        if reference_images:
            user_content += f"\nAdditional Reference Images: {len(reference_images)} visual anchors attached.\n"

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
                if isinstance(data, dict) and data.get("master_prompt"):
                    return data
            except Exception as e:
                print(f"[AssetLabService] Parse synthesis JSON failed: {e}")

        # Intelligent Fallback Recipe Synthesis
        ing_names = [f"@{i.get('name')}" for i in ingredients if i.get('name')]
        ing_str = " + ".join(ing_names) if ing_names else "SOT Galactic Fusion"
        
        has_card = (
            target_format == "trading_card" or
            any("baseball" in (i.get("name", "") + " " + i.get("title", "")).lower() or "card" in (i.get("name", "") + " " + i.get("title", "")).lower() for i in ingredients) or
            "baseball" in (custom_prompt or "").lower() or "card" in (custom_prompt or "").lower()
        )

        subject_ing = next((i for i in ingredients if i.get("role") == "subject"), None)
        subject_name = subject_ing.get("title") if subject_ing else "Captain Geppy"

        if has_card:
            aspect = "2.5:3.5"
            team_val = variables.get("team_name") if isinstance(variables, dict) else None
            player_val = variables.get("player_name") if isinstance(variables, dict) else None
            pos_val = variables.get("position") if isinstance(variables, dict) else None
            stats_val = variables.get("stats") if isinstance(variables, dict) else None
            num_val = variables.get("card_number") if isinstance(variables, dict) else None
            year_val = variables.get("year_era") if isinstance(variables, dict) else None

            p_name = player_val or subject_name
            t_name = team_val or "GEPPY'S GALACTIC ALL-STARS"
            p_pos = pos_val or "CAPTAIN"
            s_text = stats_val or "STARFLEET PILOT • .342 AVG • 48 HR • SOT ALL-GALAXY"
            c_num = num_val or "#76"
            y_era = year_val or "'76"

            return {
                "title": f"1970s Vintage Baseball Card: {p_name}",
                "master_prompt": f"Authentic 1970s Topps-style vintage baseball card featuring {p_name} of {t_name} ({p_pos}) as the star galactic commander, rendered with 35mm Kodachrome film grain, printed on aged cardboard stock with arched team banner typography reading '{t_name}', round star position badge '{p_pos}', lower player name banner '{p_name}', stats '{s_text}', card {c_num} ({y_era}), worn cardboard corners, and nostalgic offset litho print texture.",
                "negative_prompt": "modern digital rendering, 3D glossy render, flat vector clipart, oversaturated neon, blurry, distorted anatomy",
                "color_palette": ["#F5EDE0 (Cardboard Buff)", "#DC2626 (Retro Red)", "#F59E0B (Topps Gold)", "#1E3A8A (Vintage Navy)"],
                "composition_blueprint": f"Authentic 1970s trading card layout: arched team banner '{t_name}', player portrait window '{p_name}', star position badge '{p_pos}', stats '{s_text}', card {c_num}, aged cardboard borders.",
                "style_fusion_notes": f"Seamlessly transposed {p_name} into 1970s vintage baseball card aesthetic with team banner '{t_name}', position '{p_pos}', and authentic stats banner.",
                "suggested_aspect_ratio": "2.5:3.5"
            }

        aspect = "1:1"
        if target_format == "banner_hero": aspect = "16:9"
        elif target_format == "social_story": aspect = "9:16"
        elif target_format == "ui_component": aspect = "4:3"

        base_parts = []
        if ingredients:
            for ing in ingredients:
                r = ing.get("role", "style")
                txt = ing.get("reference_text", "")
                if txt: base_parts.append(f"[{r.upper()}: {txt}]")
        if custom_prompt:
            base_parts.append(custom_prompt)

        compiled_prompt = " | ".join(base_parts) if base_parts else f"Flagship fine-tuned 3D asset blending {ing_str}"
        compiled_prompt += " | 8K Octane Render, volumetric rim lighting, frosted translucent glass, smooth squircle curvature, masterwork design."

        return {
            "title": f"Fine-Tuned Asset ({ing_str})",
            "master_prompt": compiled_prompt,
            "negative_prompt": "blurry, low resolution, artifacts, distorted geometry, muted colors, flat 2d clipart",
            "color_palette": ["#06B6D4 (Cyan Visor)", "#6366F1 (Indigo Nebula)", "#F59E0B (Amber Gold)", "#0F172A (Obsidian)"],
            "composition_blueprint": f"Optimized for {target_format} ({aspect}) with centered focal subject, ambient depth lighting, and glassmorphic micro-bevels.",
            "style_fusion_notes": f"Harmonized {len(ingredients)} contextiles into a single unified asset profile.",
            "suggested_aspect_ratio": aspect
        }

    @classmethod
    def _render_trading_card(
        cls,
        title: str,
        master_prompt: str,
        ingredients_summary: List[Dict[str, Any]] = None,
        reference_images: List[str] = None,
        color_palette: List[str] = None,
        variables: Dict[str, Any] = None
    ) -> Image.Image:
        """
        Renders an authentic, ultra-crisp 1970s Topps-style vintage baseball trading card
        with dynamic variable slots (team name, player name, position, stats, card number, year).
        """
        width, height = (750, 1050)
        img = Image.new("RGBA", (width, height), (245, 237, 224, 255))
        draw = ImageDraw.Draw(img)

        # Merge variables from ingredients if present
        vars_dict = dict(variables or {})
        if ingredients_summary:
            for ing in ingredients_summary:
                for v in ing.get("variables", []):
                    k = v.get("key")
                    val = v.get("value", v.get("default_value"))
                    if k and val is not None and k not in vars_dict:
                        vars_dict[k] = val

        def _get_v(key: str, default_val: str) -> str:
            for k, v in vars_dict.items():
                if k.lower() == key.lower() and v:
                    return str(v)
            return default_val

        team_text = _get_v("team_name", "GEPPY'S GALACTIC ALL-STARS").upper()
        star_txt = _get_v("position", "CAPTAIN").upper()
        disp_name = _get_v("player_name", "").upper()
        if not disp_name:
            disp_name = title.upper()
            if ":" in disp_name: disp_name = disp_name.split(":")[-1].strip()
        if len(disp_name) > 28: disp_name = disp_name[:26] + "..."

        # Build stats line
        custom_stats = _get_v("stats", "").upper()
        if not custom_stats:
            stat_tokens = []
            if _get_v("batting_avg", ""): stat_tokens.append(f"{_get_v('batting_avg', '')} AVG")
            if _get_v("home_runs", ""): stat_tokens.append(f"{_get_v('home_runs', '')} HR")
            if _get_v("rbi", ""): stat_tokens.append(f"{_get_v('rbi', '')} RBI")
            if _get_v("era", ""): stat_tokens.append(f"{_get_v('era', '')} ERA")
            if _get_v("strikeouts", ""): stat_tokens.append(f"{_get_v('strikeouts', '')} SO")
            custom_stats = " • ".join(stat_tokens).upper() if stat_tokens else "COMMANDER • STARFLEET PILOT • SOT ALL-GALAXY"

        pos_str = custom_stats
        num_str = _get_v("card_number", "#76")
        year_str = _get_v("year_era", "'76")
        foot_str = f"{year_str} VINTAGE SOT TRADING CARD • TOPPS STYLE COLLECTIBLE"

        # 1. Aged Cardboard Base & Paper Texture
        for y in range(height):
            ratio = y / height
            r = int(246 - 12 * ratio)
            g = int(238 - 14 * ratio)
            b = int(224 - 18 * ratio)
            draw.line([(0, y), (width, y)], fill=(r, g, b, 255))

        # Cardboard fiber noise
        grain = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        g_draw = ImageDraw.Draw(grain)
        for i in range(0, width, 5):
            for j in range(0, height, 5):
                if (i * 17 + j * 31) % 23 == 0:
                    g_draw.point((i, j), fill=(100, 80, 50, 30))
        img = Image.alpha_composite(img, grain)
        draw = ImageDraw.Draw(img)

        # 2. Outer Card Margin & Double Border Lines
        pad = 26
        draw.rounded_rectangle([pad, pad, width - pad, height - pad], radius=16, outline=(30, 41, 59, 230), width=4)
        draw.rounded_rectangle([pad + 6, pad + 6, width - pad - 6, height - pad - 6], radius=12, outline=(217, 119, 6, 170), width=2)

        # 3. Top Arched Team Banner (1970s Pennant Style)
        banner_y0 = pad + 20
        banner_y1 = banner_y0 + 84
        draw.rounded_rectangle([pad + 18, banner_y0, width - pad - 18, banner_y1], radius=16, fill=(185, 28, 28, 255), outline=(245, 158, 11, 255), width=3)
        draw.rounded_rectangle([pad + 22, banner_y0 + 4, width - pad - 22, banner_y1 - 4], radius=12, outline=(254, 240, 138, 200), width=1)

        font_def = ImageFont.load_default()
        t_box = draw.textbbox((0, 0), team_text, font=font_def)
        tw = t_box[2] - t_box[0]
        draw.text(((width - tw) // 2, banner_y0 + 34), team_text, fill=(255, 255, 255, 255), font=font_def)

        # Star Position Badge in Upper Right Corner
        star_r = 38
        scx = width - pad - 50
        scy = banner_y1 + 44
        draw.ellipse([scx - star_r, scy - star_r, scx + star_r, scy + star_r], fill=(245, 158, 11, 255), outline=(185, 28, 28, 255), width=4)
        st_box = draw.textbbox((0, 0), star_txt, font=font_def)
        draw.text((scx - (st_box[2]-st_box[0])//2, scy - 7), star_txt, fill=(30, 27, 75, 255), font=font_def)

        # 4. Central Portrait Photo Frame
        px0 = pad + 24
        py0 = banner_y1 + 20
        px1 = width - pad - 24
        py1 = height - pad - 130
        draw.rectangle([px0, py0, px1, py1], fill=(15, 23, 42, 255), outline=(15, 23, 42, 255), width=3)
        draw.rectangle([px0 + 3, py0 + 3, px1 - 3, py1 - 3], outline=(245, 158, 11, 220), width=2)

        pw = px1 - px0
        ph = py1 - py0
        photo_box = Image.new("RGBA", (pw, ph), (15, 23, 42, 255))
        p_draw = ImageDraw.Draw(photo_box)

        # Photo stadium twilight background
        for py in range(ph):
            rat = py / ph
            pr = int(12 + (30 - 12) * rat)
            pg = int(18 + (24 - 18) * rat)
            pb = int(35 + (65 - 35) * rat)
            p_draw.line([(0, py), (pw, py)], fill=(pr, pg, pb, 255))

        # Stadium light beams
        for lx in [int(pw * 0.2), int(pw * 0.8)]:
            for lr in range(160, 0, -20):
                alpha = int(45 * (1.0 - lr / 160))
                p_draw.ellipse([lx - lr, -40 - lr, lx + lr, -40 + lr], fill=(253, 224, 71, alpha))

        # Check if subject image exists in reference_images
        composited = False
        all_refs = list(reference_images or [])
        if ingredients_summary:
            for ing in ingredients_summary:
                p_img = ing.get("primary_image_url") or ing.get("reference_image_url")
                if p_img and p_img not in all_refs:
                    all_refs.insert(0, p_img)

        for ref_url in all_refs:
            local_path = None
            if "/api/sot/reference-file/" in ref_url or "/api/sot/references/" in ref_url:
                fname_ref = ref_url.split("/")[-1]
                base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                local_path = os.path.join(base_dir, "assets", "sot_references", fname_ref)
            elif "/api/apps/" in ref_url and "/assets/file/" in ref_url:
                parts = ref_url.split("/assets/file/")
                if len(parts) == 2:
                    fname_ref = parts[1]
                    slug = parts[0].split("/api/apps/")[-1]
                    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                    local_path = os.path.join(base_dir, "apps", slug, "assets", fname_ref)

            if local_path and os.path.exists(local_path):
                try:
                    ref_img = Image.open(local_path).convert("RGBA")
                    rw, rh = ref_img.size
                    scale = max(pw / rw, ph / rh)
                    nw, nh = int(rw * scale), int(rh * scale)
                    ref_scaled = ref_img.resize((nw, nh), Image.Resampling.LANCZOS)
                    cx, cy = nw // 2, nh // 2
                    ref_crop = ref_scaled.crop((cx - pw // 2, cy - ph // 2, cx + pw // 2, cy + ph // 2))
                    
                    tint = Image.new("RGBA", (pw, ph), (254, 240, 138, 25))
                    ref_crop = Image.alpha_composite(ref_crop, tint)
                    photo_box.paste(ref_crop, (0, 0))
                    composited = True
                    break
                except Exception as e:
                    print(f"[_render_trading_card] composite ref image failed: {e}")

        if not composited:
            cx, cy = pw // 2, int(ph * 0.52)
            for r_step in range(120, 0, -15):
                p_draw.ellipse([cx - r_step, cy - r_step, cx + r_step, cy + r_step], fill=(99, 102, 241, int(40 * (1.0 - r_step / 120))))
            p_draw.ellipse([cx - 70, cy - 100, cx + 70, cy + 30], fill=(30, 41, 59, 255), outline=(245, 158, 11, 230), width=3)
            p_draw.rounded_rectangle([cx - 42, cy - 65, cx + 42, cy - 25], radius=10, fill=(6, 182, 212, 255), outline=(255, 255, 255, 240), width=2)
            p_draw.polygon([(cx - 140, ph), (cx - 75, cy + 35), (cx + 75, cy + 35), (cx + 140, ph)], fill=(15, 23, 42, 255), outline=(245, 158, 11, 240))
            p_draw.rectangle([cx - 24, cy + 50, cx + 24, cy + 58], fill=(245, 158, 11, 255))
            p_draw.rectangle([cx - 24, cy + 64, cx + 24, cy + 72], fill=(245, 158, 11, 255))

        img.paste(photo_box, (px0, py0))
        draw = ImageDraw.Draw(img)

        # 5. Lower Nameplate Banner
        np_y0 = py1 + 16
        np_y1 = np_y0 + 68
        draw.rounded_rectangle([pad + 18, np_y0, width - pad - 18, np_y1], radius=12, fill=(30, 58, 138, 255), outline=(245, 158, 11, 240), width=3)
        draw.rounded_rectangle([pad + 22, np_y0 + 3, width - pad - 22, np_y1 - 3], radius=9, outline=(254, 240, 138, 180), width=1)

        nb_box = draw.textbbox((0, 0), disp_name, font=font_def)
        draw.text(((width - (nb_box[2]-nb_box[0])) // 2, np_y0 + 16), disp_name, fill=(255, 255, 255, 255), font=font_def)

        pb_box = draw.textbbox((0, 0), pos_str, font=font_def)
        draw.text(((width - (pb_box[2]-pb_box[0])) // 2, np_y0 + 40), pos_str, fill=(253, 224, 71, 255), font=font_def)

        # 6. Vintage Bottom Card Footer Stamp
        fb_box = draw.textbbox((0, 0), foot_str, font=font_def)
        draw.text(((width - (fb_box[2]-fb_box[0])) // 2, height - pad - 22), foot_str, fill=(100, 116, 139, 255), font=font_def)

        draw.text((pad + 18, height - pad - 22), num_str, fill=(185, 28, 28, 255), font=font_def)

        return img

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
        reference_images: List[str] = None,
        app_slug: Optional[str] = None,
        variables: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Generate a high-fidelity visual asset PNG file with dynamic template variables and store it in the lab repository.
        """
        lab_dir = cls._get_lab_dir()
        asset_id = f"asset_{int(time.time())}_{uuid.uuid4().hex[:6]}"
        filename = f"{asset_id}.png"
        filepath = os.path.join(lab_dir, filename)

        # Check if this is a Trading Card / Baseball Card format
        is_card = (
            target_format == "trading_card" or
            "baseball" in (title + " " + master_prompt).lower() or
            "trading card" in (title + " " + master_prompt).lower() or
            any("baseball" in (i.get("name", "") + " " + i.get("title", "")).lower() or "card" in (i.get("name", "") + " " + i.get("title", "")).lower() for i in (ingredients_summary or []))
        )

        if is_card:
            img = cls._render_trading_card(
                title=title,
                master_prompt=master_prompt,
                ingredients_summary=ingredients_summary,
                reference_images=reference_images,
                color_palette=color_palette,
                variables=variables
            )
            img = img.convert("RGB")
            img.save(filepath, "PNG", quality=95)

            file_url = f"/api/asset-lab/file/{filename}"
            record = {
                "id": asset_id,
                "title": title,
                "filename": filename,
                "file_url": file_url,
                "target_format": "trading_card",
                "aspect_ratio": "2.5:3.5",
                "master_prompt": master_prompt,
                "color_palette": color_palette or [],
                "composition_blueprint": composition_blueprint or "Authentic 1970s trading card layout",
                "ingredients_summary": ingredients_summary or [],
                "variables": variables or {},
                "app_slug": app_slug,
                "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
            }
            cls.save_history_item(record)
            return record
            cls.save_history_item(record)
            return record

        # Dimension mapping
        dim_map = {
            "1:1": (1024, 1024),
            "16:9": (1920, 1080),
            "9:16": (1080, 1920),
            "4:3": (1200, 900),
            "21:9": (2100, 900)
        }
        width, height = dim_map.get(aspect_ratio, (1024, 1024))
        if target_format == "app_icon":
            width, height = (1024, 1024)

        # Generate procedural artwork with PIL
        img = Image.new("RGBA", (width, height), (15, 23, 42, 255)) # Dark slate base
        draw = ImageDraw.Draw(img)

        # 1. Cosmic Gradient Background
        for y in range(height):
            ratio = y / height
            # Interpolate from deep obsidian (#0a0f1d) to rich space navy (#1e1b4b)
            r = int(10 + (25 - 10) * ratio)
            g = int(15 + (27 - 15) * ratio)
            b = int(29 + (75 - 29) * ratio)
            draw.line([(0, y), (width, y)], fill=(r, g, b, 255))

        # 2. Ambient Nebula Radial Glow (Center or Upper Center)
        glow_center_x = width // 2
        glow_center_y = int(height * 0.45)
        glow_radius = int(min(width, height) * 0.55)

        # Radial glow buffer
        glow_overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        glow_draw = ImageDraw.Draw(glow_overlay)

        # Multi-layer cosmic glows
        for rad in range(glow_radius, 0, -20):
            alpha = int(45 * (1.0 - (rad / glow_radius)))
            # Cyan & Indigo blend
            glow_draw.ellipse(
                [glow_center_x - rad, glow_center_y - rad, glow_center_x + rad, glow_center_y + rad],
                fill=(6, 182, 212, alpha) # Cyan
            )
        glow_overlay = glow_overlay.filter(ImageFilter.GaussianBlur(radius=40))
        img = Image.alpha_composite(img, glow_overlay)
        draw = ImageDraw.Draw(img)

        # 3. Main Central 3D Squircle / Motif Container
        box_size = int(min(width, height) * 0.62)
        bx0 = (width - box_size) // 2
        by0 = (height - box_size) // 2 - int(height * 0.03)
        bx1 = bx0 + box_size
        by1 = by0 + box_size
        corner_rad = int(box_size * 0.22) # iOS-style squircle radius

        # Squircle Outer Drop Shadow
        shadow_overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        shadow_draw = ImageDraw.Draw(shadow_overlay)
        shadow_draw.rounded_rectangle([bx0 + 8, by0 + 20, bx1 + 8, by1 + 20], radius=corner_rad, fill=(0, 0, 0, 160))
        shadow_overlay = shadow_overlay.filter(ImageFilter.GaussianBlur(radius=30))
        img = Image.alpha_composite(img, shadow_overlay)
        draw = ImageDraw.Draw(img)

        # Squircle Frosted Glass Body
        glass_overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        glass_draw = ImageDraw.Draw(glass_overlay)
        glass_draw.rounded_rectangle([bx0, by0, bx1, by1], radius=corner_rad, fill=(15, 23, 42, 210))
        
        # Diagonal Glass Specular Sheen
        for i in range(bx0, bx1):
            rel = (i - bx0) / box_size
            if 0.15 < rel < 0.65:
                sheen_alpha = int(35 * (1.0 - abs(rel - 0.4) / 0.25))
                glass_draw.line([(i, by0 + 5), (i - int(box_size * 0.2), by1 - 5)], fill=(255, 255, 255, sheen_alpha), width=2)

        # Glowing Visor / Gold Border
        glass_draw.rounded_rectangle([bx0, by0, bx1, by1], radius=corner_rad, outline=(6, 182, 212, 200), width=4)
        glass_draw.rounded_rectangle([bx0 + 3, by0 + 3, bx1 - 3, by1 - 3], radius=corner_rad - 2, outline=(245, 158, 11, 140), width=2)
        
        img = Image.alpha_composite(img, glass_overlay)
        draw = ImageDraw.Draw(img)

        # 4. Check if any reference image exists to composite inside
        composited_ref = False
        if reference_images:
            for ref_url in reference_images:
                # If local file URL
                local_path = None
                if "/api/sot/references/" in ref_url:
                    fname_ref = ref_url.split("/api/sot/references/")[-1]
                    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                    local_path = os.path.join(base_dir, "assets", "sot_references", fname_ref)
                elif "/api/apps/" in ref_url and "/assets/file/" in ref_url:
                    parts = ref_url.split("/assets/file/")
                    if len(parts) == 2:
                        fname_ref = parts[1]
                        slug = parts[0].split("/api/apps/")[-1]
                        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                        local_path = os.path.join(base_dir, "apps", slug, "assets", fname_ref)

                if local_path and os.path.exists(local_path):
                    try:
                        ref_img = Image.open(local_path).convert("RGBA")
                        # Crop to square and resize
                        rw, rh = ref_img.size
                        min_dim = min(rw, rh)
                        cx, cy = rw // 2, rh // 2
                        ref_cropped = ref_img.crop((cx - min_dim // 2, cy - min_dim // 2, cx + min_dim // 2, cy + min_dim // 2))
                        
                        inner_size = int(box_size * 0.72)
                        ref_resized = ref_cropped.resize((inner_size, inner_size), Image.Resampling.LANCZOS)
                        
                        # Circular or squircle mask
                        mask = Image.new("L", (inner_size, inner_size), 0)
                        mask_draw = ImageDraw.Draw(mask)
                        mask_draw.rounded_rectangle([0, 0, inner_size, inner_size], radius=int(inner_size * 0.2), fill=255)
                        
                        ref_x = bx0 + (box_size - inner_size) // 2
                        ref_y = by0 + (box_size - inner_size) // 2
                        img.paste(ref_resized, (ref_x, ref_y), mask)
                        composited_ref = True
                        break
                    except Exception as e:
                        print(f"[AssetLabService] Failed to composite ref image: {e}")

        # If no reference image composited, draw a glorious 3D Galactic Emblem Glyph
        if not composited_ref:
            emblem_cx = (bx0 + bx1) // 2
            emblem_cy = (by0 + by1) // 2
            glyph_r = int(box_size * 0.28)

            # Central Glowing Core
            for r_step in range(glyph_r, 0, -10):
                g_alpha = int(120 * (1.0 - (r_step / glyph_r)))
                draw.ellipse(
                    [emblem_cx - r_step, emblem_cy - r_step, emblem_cx + r_step, emblem_cy + r_step],
                    fill=(99, 102, 241, g_alpha) # Indigo
                )

            # Golden Galactic Commander Rings
            draw.ellipse(
                [emblem_cx - glyph_r, emblem_cy - int(glyph_r * 0.4), emblem_cx + glyph_r, emblem_cy + int(glyph_r * 0.4)],
                outline=(245, 158, 11, 230), width=5
            )
            draw.ellipse(
                [emblem_cx - int(glyph_r * 0.4), emblem_cy - glyph_r, emblem_cx + int(glyph_r * 0.4), emblem_cy + glyph_r],
                outline=(6, 182, 212, 230), width=5
            )
            # Center Core Diamond
            d_size = int(glyph_r * 0.4)
            diamond_pts = [
                (emblem_cx, emblem_cy - d_size),
                (emblem_cx + d_size, emblem_cy),
                (emblem_cx, emblem_cy + d_size),
                (emblem_cx - d_size, emblem_cy)
            ]
            draw.polygon(diamond_pts, fill=(255, 255, 255, 240), outline=(245, 158, 11, 255))

        # 5. Header / Footer Badges & Title Overlay
        font_large = ImageFont.load_default()
        
        # Clean title text at bottom
        display_title = title if len(title) < 45 else title[:42] + "..."
        text_bbox = draw.textbbox((0, 0), display_title, font=font_large)
        tw = text_bbox[2] - text_bbox[0]
        tx = (width - tw) // 2
        ty = int(by1 + (height - by1) * 0.3)
        if ty < height - 50:
            draw.rectangle([tx - 16, ty - 8, tx + tw + 16, ty + 24], fill=(15, 23, 42, 220), outline=(51, 65, 85, 200), width=1)
            draw.text((tx, ty), display_title, fill=(241, 245, 249, 255), font=font_large)

        # Upper Tag Badge: "GEPPY'S GITBRIDGE • ASSET LAB"
        tag_str = f"GEPPY'S GITBRIDGE • SOT FUSION [{target_format.upper()}]"
        tb_box = draw.textbbox((0, 0), tag_str, font=font_large)
        tag_w = tb_box[2] - tb_box[0]
        tag_x = (width - tag_w) // 2
        tag_y = max(20, int(by0 * 0.35))
        draw.rectangle([tag_x - 12, tag_y - 6, tag_x + tag_w + 12, tag_y + 20], fill=(30, 27, 75, 200), outline=(99, 102, 241, 160), width=1)
        draw.text((tag_x, tag_y), tag_str, fill=(6, 182, 212, 255), font=font_large)

        # Save to disk
        img = img.convert("RGB")
        img.save(filepath, "PNG", quality=95)

        file_url = f"/api/asset-lab/file/{filename}"

        # Record in history
        record = {
            "id": asset_id,
            "title": title,
            "filename": filename,
            "file_url": file_url,
            "target_format": target_format,
            "aspect_ratio": aspect_ratio,
            "master_prompt": master_prompt,
            "color_palette": color_palette or [],
            "composition_blueprint": composition_blueprint,
            "ingredients_summary": ingredients_summary or [],
            "app_slug": app_slug,
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        cls.save_history_item(record)
        return record
