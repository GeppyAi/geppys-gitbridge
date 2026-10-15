import os
import json
import time
import uuid
import zipfile
import requests
from typing import List, Dict, Any, Optional
from PIL import Image, ImageDraw, ImageFont, ImageFilter

class SeriesService:
    """
    Asset Series & Collection Generator.
    Takes a base/anchor asset and creates a cohesive series of multiple variations
    based on customizable difference directives (expressions, poses, app features, rarities, etc.).
    """

    PRESETS = {
        "emotes": {
            "title": "Emotes & Expressions Pack",
            "description": "6 emotional states with matching facial cues, particle sparkles, and energy glows.",
            "icon": "😃",
            "variations": [
                {
                    "title": "Happy & Cheering",
                    "difference": "Wide joyful beaming smile, thumbs-up gesture, golden star sparkles, radiant sunny warm aura",
                    "accent_color": "#F59E0B"
                },
                {
                    "title": "Pondering & Deep Thought",
                    "difference": "Hand resting under chin, focused curious expression, rotating cyan holographic question ring, analytical gaze",
                    "accent_color": "#06B6D4"
                },
                {
                    "title": "Hyperspace Focused",
                    "difference": "High-tech flight goggles lowered, wind-swept hair, intense determined gaze, warp-speed stars streaking in visor reflection",
                    "accent_color": "#6366F1"
                },
                {
                    "title": "Power-Down / Coffee Needed",
                    "difference": "Drowsy half-lidded eyes, slumped relaxed shoulders, holding a blinking low-battery indicator datapad",
                    "accent_color": "#64748B"
                },
                {
                    "title": "Mind Blown / Cosmic Discovery",
                    "difference": "Eyes wide in cosmic awe with vibrant swirling galaxy reflections, subtle electrical shockwave aura, hands raised in revelation",
                    "accent_color": "#EC4899"
                },
                {
                    "title": "Cool & Confident",
                    "difference": "Sleek mirrored sunglasses or dark aviator visor, charming confident smirk, golden glimmer sparkle on teeth/badge",
                    "accent_color": "#10B981"
                }
            ]
        },
        "actions": {
            "title": "Action & Quests Series",
            "description": "6 dynamic action poses and functional equipment sets.",
            "icon": "🚀",
            "variations": [
                {
                    "title": "Rocket Coffee Fuel",
                    "difference": "Sipping steaming space espresso from a chrome titanium rocket mug, cozy morning sunrise atmosphere",
                    "accent_color": "#D97706"
                },
                {
                    "title": "Holo-Keyboard Coder",
                    "difference": "Dual typing on floating translucent cyan code matrices, neon green binary code cascades, intense developer flow",
                    "accent_color": "#10B981"
                },
                {
                    "title": "Git Shield Barrier",
                    "difference": "Projecting a luminous hexagonal energy force-field shield deflecting bugs and server collisions",
                    "accent_color": "#3B82F6"
                },
                {
                    "title": "Deep Space Scanner",
                    "difference": "Holding an omni-directional tactical antenna scanner receiving radar blips and alien transmission waveforms",
                    "accent_color": "#8B5CF6"
                },
                {
                    "title": "Release Champion",
                    "difference": "Proudly hoisting a shining gold star trophy with floating celebratory victory ribbons and confetti",
                    "accent_color": "#F59E0B"
                },
                {
                    "title": "Reactor Technician",
                    "difference": "Equipped with plasma socket wrench and tool belt, grease smudge on cheek, sparks flying from manifold",
                    "accent_color": "#EF4444"
                }
            ]
        },
        "app_suite": {
            "title": "App Navigation & Feature Icons",
            "description": "6 matching 3D app navigation icons sharing identical materials, squircle framing, and lighting.",
            "icon": "📱",
            "variations": [
                {
                    "title": "Command Bridge (Home)",
                    "difference": "Main bridge command console with holographic orbital overview, helm star-map projector, welcoming amber glow",
                    "accent_color": "#6366F1"
                },
                {
                    "title": "Telemetry & Analytics",
                    "difference": "3D rising holographic bar charts, glowing circular radar sweep, floating data pulse metrics",
                    "accent_color": "#06B6D4"
                },
                {
                    "title": "Engine Core & Settings",
                    "difference": "Interlocking precision brass and obsidian clockwork gears revolving around an antimatter reactor chamber",
                    "accent_color": "#F59E0B"
                },
                {
                    "title": "Comms & Subspace Chat",
                    "difference": "Floating holographic speech beacon with undulating frequency soundwaves and glowing audio rings",
                    "accent_color": "#10B981"
                },
                {
                    "title": "Git Vault & Storage",
                    "difference": "Heavy orbital bank vault door with rotating combination wheel, glowing green security laser grids",
                    "accent_color": "#8B5CF6"
                },
                {
                    "title": "Launch Thruster (Deploy)",
                    "difference": "High-thrust rocket engine nozzle with roaring cyan plasma exhaust plume and particle trail",
                    "accent_color": "#EF4444"
                }
            ]
        },
        "seasons": {
            "title": "Four Seasons & Holidays",
            "description": "4 atmospheric seasonal variations with custom environmental palettes.",
            "icon": "🎃",
            "variations": [
                {
                    "title": "Cyber Halloween",
                    "difference": "Jack-o'-lantern visor hologram glow, ghostly violet mist, bats circling overhead, pumpkin orange neon rim light",
                    "accent_color": "#F97316"
                },
                {
                    "title": "Winter Solstice",
                    "difference": "Cozy knitted chunky interstellar scarf, gentle falling snow crystals, frosty cyan breath, icicle borders",
                    "accent_color": "#38BDF8"
                },
                {
                    "title": "Vernal Sakura",
                    "difference": "Swirling pink cherry blossom petals caught in solar wind, soft pastel green foliage, refreshing spring breeze",
                    "accent_color": "#F472B6"
                },
                {
                    "title": "Midsummer Solar Flare",
                    "difference": "Bright sunburst backdrop, tropical holographic palm silhouettes, warm golden sand hues, sunglasses",
                    "accent_color": "#EAB308"
                }
            ]
        },
        "card_rarities": {
            "title": "Collectible Card Rarity Tiers",
            "description": "4 tiers of collectible trading card finishes from Base to Cosmic 1-of-1.",
            "icon": "⚾",
            "variations": [
                {
                    "title": "Base Edition (Bronze)",
                    "difference": "Authentic matte cardboard stock, classic sepia-toned margins, standard team insignia, bronze stamped foil",
                    "accent_color": "#B45309"
                },
                {
                    "title": "Refractor (Silver Sheen)",
                    "difference": "Polished mirror chrome finish, prism rainbow light dispersion along borders, silver embossed star crest",
                    "accent_color": "#94A3B8"
                },
                {
                    "title": "Super-Foil (24K Gold)",
                    "difference": "Heavy 24-karat gilded gold leaf foil border, raised 3D metallic filigree, glowing champion laurel wreath",
                    "accent_color": "#F59E0B"
                },
                {
                    "title": "Cosmic Mythic (1-of-1)",
                    "difference": "Translucent dark obsidian holographic card, swirling nebula dust embedded inside, starlight constellation lines",
                    "accent_color": "#C084FC"
                }
            ]
        },
        "costumes": {
            "title": "Cosmic Wardrobe & Outfits",
            "description": "4 thematic character outfit overhauls maintaining face likeness.",
            "icon": "👔",
            "variations": [
                {
                    "title": "Starfleet Captain Dress Uniform",
                    "difference": "Crisp navy and gold braided officer dress tunic with high standing collar, ceremonial shoulder epaulettes, medal ribbon bar",
                    "accent_color": "#1D4ED8"
                },
                {
                    "title": "Cyberpunk Streetwear Hoodie",
                    "difference": "Oversized techwear matte black hoodie with luminous neon cyan circuit drawstrings, fingerless tactical gloves",
                    "accent_color": "#06B6D4"
                },
                {
                    "title": "Heavy Exosuit Armor",
                    "difference": "Bulky titanium hazard plates with hydraulic arm servos, reinforced chest reactor, danger hazard yellow stripes",
                    "accent_color": "#EAB308"
                },
                {
                    "title": "Retro 70s Tracksuit",
                    "difference": "Nostalgic retro velour athletic tracksuit with three red and white racing stripes, vintage athletic headband",
                    "accent_color": "#DC2626"
                }
            ]
        }
    }

    @classmethod
    def _get_series_dir(cls) -> str:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        target = os.path.join(base_dir, "assets", "lab_generated", "series")
        os.makedirs(target, exist_ok=True)
        return target

    @classmethod
    def _get_history_file(cls) -> str:
        return os.path.join(cls._get_series_dir(), "series_history.json")

    @classmethod
    def get_presets(cls) -> Dict[str, Any]:
        """Return available standard variation preset packs."""
        return cls.PRESETS

    @classmethod
    def get_history(cls) -> List[Dict[str, Any]]:
        """Retrieve list of all created series collections."""
        fpath = cls._get_history_file()
        if not os.path.exists(fpath):
            return []
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[SeriesService] Error reading history: {e}")
            return []

    @classmethod
    def save_history_item(cls, series_record: Dict[str, Any]):
        """Persist or update a series record in history."""
        hist = cls.get_history()
        # Filter out existing if any
        hist = [s for s in hist if s.get("id") != series_record.get("id")]
        hist.insert(0, series_record)
        try:
            with open(cls._get_history_file(), "w", encoding="utf-8") as f:
                json.dump(hist[:50], f, indent=2) # Keep last 50
        except Exception as e:
            print(f"[SeriesService] Error saving history item: {e}")

    @classmethod
    def get_series(cls, series_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a specific series by ID."""
        for s in cls.get_history():
            if s.get("id") == series_id:
                return s
        return None

    @classmethod
    def delete_series(cls, series_id: str) -> bool:
        """Delete a series and its generated folder assets."""
        series_dir = os.path.join(cls._get_series_dir(), series_id)
        if os.path.exists(series_dir):
            try:
                import shutil
                shutil.rmtree(series_dir)
            except Exception as e:
                print(f"[SeriesService] Error deleting folder {series_dir}: {e}")

        hist = [s for s in cls.get_history() if s.get("id") != series_id]
        try:
            with open(cls._get_history_file(), "w", encoding="utf-8") as f:
                json.dump(hist, f, indent=2)
            return True
        except Exception as e:
            print(f"[SeriesService] Error updating history file: {e}")
            return False

    @classmethod
    def expand_variations_ai(
        cls,
        theme_idea: str,
        anchor_title: str = "Captain Geppy",
        anchor_style: str = "3D Icon",
        count: int = 5
    ) -> List[Dict[str, str]]:
        """
        Use AI (or smart algorithmic fallback) to expand a series theme prompt
        into a structured list of distinct, cohesive variations.
        """
        count = max(2, min(count, 10))
        from gitbridge.services.central_key_service import CentralKeyService
        system_instruction = f"""You are the Series Director for Geppy's Galactic Asset Laboratory.
Given a Base Anchor Asset and a Series Theme Idea, generate exactly {count} distinct variations.
Every variation must retain the core character/subject likeness and artistic format, but introduce a unique action, emotion, prop, role, or environmental difference.
Respond ONLY with a JSON array of objects with keys: "title", "difference", "accent_color" (hex).
Example:
[
  {{"title": "Space Navigator", "difference": "Plotting star course on 3D celestial astrolabe, brass compass badge", "accent_color": "#06B6D4"}}
]"""
        prompt = f"Base Anchor Asset: {anchor_title} (Style: {anchor_style})\nSeries Theme Idea: {theme_idea}\nGenerate {count} variations in JSON format."

        raw = CentralKeyService.call_gemini([{"role": "user", "parts": [{"text": prompt}]}], system_instruction, timeout=15)
        if raw:
            try:
                clean_raw = raw.strip()
                if "```json" in clean_raw:
                    clean_raw = clean_raw.split("```json")[1].split("```")[0].strip()
                elif "```" in clean_raw:
                    clean_raw = clean_raw.split("```")[1].split("```")[0].strip()
                parsed = json.loads(clean_raw)
                if isinstance(parsed, list) and len(parsed) >= 2:
                    return parsed[:count]
            except Exception as e:
                print(f"[SeriesService] AI variation parsing failed: {e}")


        # Algorithmic fallback variations based on theme keywords
        lower_idea = theme_idea.lower()
        if "sport" in lower_idea or "game" in lower_idea:
            base_list = [
                {"title": "Batter at the Plate", "difference": "Stepping into batter's box, gripping ash-wood baseball bat, focused squint, pine-tar helmet", "accent_color": "#DC2626"},
                {"title": "Ace Pitcher Windup", "difference": "Mid-windup leg kick, arm cocked back ready to fire 100mph fastball, dust kicking from pitcher's mound", "accent_color": "#F59E0B"},
                {"title": "Golden Glove Fielder", "difference": "Diving horizontally across grass to snag line-drive into leather webbed mitt, turf flying", "accent_color": "#10B981"},
                {"title": "Home Run Trot", "difference": "Rounding third base with raised fist celebration, tipping cap to cheering crowd, helmet in hand", "accent_color": "#3B82F6"},
                {"title": "Bullpen Coach", "difference": "Leaning on dugout railing with clipboard and radar gun, chewing gum, vintage windbreaker jacket", "accent_color": "#8B5CF6"},
                {"title": "Championship Rings", "difference": "Showing off huge diamond championship ring with champagne shower goggles and trophy", "accent_color": "#FBBF24"}
            ]
        elif "cyber" in lower_idea or "tech" in lower_idea or "matrix" in lower_idea:
            base_list = [
                {"title": "Neural Hacker", "difference": "Jacking into glowing holographic terminal with cybernetic eye lens, neon green binary trails", "accent_color": "#10B981"},
                {"title": "Netrunner Scout", "difference": "Perched on rainy neon rooftop with wireframe visor, holographic drone hovering over shoulder", "accent_color": "#06B6D4"},
                {"title": "Black Market Tech", "difference": "Trench coat lined with glowing plasma drives and chrome cyberware components, shady back-alley", "accent_color": "#EC4899"},
                {"title": "Data Warden", "difference": "Guarding mainframe with dual glowing electric baton stunners and armored firewall cloak", "accent_color": "#3B82F6"},
                {"title": "Overclocked Glitch", "difference": "Body surrounded by chromatic aberration distortion waves and flickering purple lightning arcs", "accent_color": "#A855F7"}
            ]
        else:
            base_list = [
                {"title": f"{theme_idea.title()} Alpha", "difference": f"Primary flagship configuration showcasing {theme_idea} with confident stance and signature gear", "accent_color": "#6366F1"},
                {"title": f"{theme_idea.title()} Beta", "difference": f"High-energy dynamic action pose themed around {theme_idea} with particle energy aura", "accent_color": "#EC4899"},
                {"title": f"{theme_idea.title()} Tactical", "difference": f"Specialized technical variation with illuminated holographic instruments and upgraded suit", "accent_color": "#06B6D4"},
                {"title": f"{theme_idea.title()} Gold Edition", "difference": f"Prestige edition with gold leaf filigree accents, radiant ambient rim glow, and badge of honor", "accent_color": "#F59E0B"},
                {"title": f"{theme_idea.title()} Stealth Ops", "difference": f"Dark matte obsidian aesthetic with subtle glowing neon accents and suppressed equipment", "accent_color": "#64748B"}
            ]

        return base_list[:count]

    @classmethod
    def generate_series(
        cls,
        anchor_data: Dict[str, Any],
        variations: List[Dict[str, Any]],
        series_title: Optional[str] = None,
        output_contextile: Optional[str] = None,
        consistency_level: str = "high",
        app_slug: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Synthesize a complete multi-image series from an anchor asset and a list of variation directives.
        """
        from gitbridge.services.asset_lab_service import AssetLabService
        from gitbridge.services.output_service import OutputService

        series_id = f"series_{int(time.time())}_{uuid.uuid4().hex[:6]}"
        series_dir = os.path.join(cls._get_series_dir(), series_id)
        os.makedirs(series_dir, exist_ok=True)

        anchor_img_url = anchor_data.get("image_url") or anchor_data.get("file_url") or ""
        anchor_prompt = anchor_data.get("master_prompt") or anchor_data.get("prompt") or ""
        anchor_title = anchor_data.get("title") or "Base Asset"
        target_format = anchor_data.get("target_format") or "app_icon"
        aspect_ratio = anchor_data.get("aspect_ratio") or "1:1"

        if not series_title:
            series_title = f"{anchor_title} • Series Pack"

        generated_items = []
        pil_images_for_contact_sheet = []

        # Process each variation
        for idx, var in enumerate(variations):
            item_num = idx + 1
            v_title = var.get("title") or f"Variation #{item_num}"
            v_diff = var.get("difference") or "Variation details"
            v_color = var.get("accent_color") or "#06B6D4"

            # 1. Compile variation prompt
            compiled_prompt = (
                f"{anchor_prompt} | [SERIES VARIATION #{item_num} - {v_title.upper()}]: {v_diff}. "
                f"Accent tone: {v_color}. Maintain strict visual continuity with base asset likeness, style, and lighting."
            )

            # 2. Render variation asset via AssetLabService rendering logic
            item_filename = f"var_{item_num}_{uuid.uuid4().hex[:4]}.png"
            item_path = os.path.join(series_dir, item_filename)

            # Check if baseball / trading card format
            is_card = target_format == "trading_card" or "baseball" in anchor_prompt.lower() or "card" in anchor_prompt.lower()

            if is_card:
                card_img = AssetLabService._render_trading_card(
                    title=f"{anchor_title} - {v_title}",
                    master_prompt=compiled_prompt,
                    reference_images=[anchor_img_url] if anchor_img_url else []
                )
                # Apply custom accent badge overlay for variation
                draw = ImageDraw.Draw(card_img)
                font_def = ImageFont.load_default()
                # Variation pill in bottom left
                draw.rounded_rectangle([32, 900, 220, 930], radius=8, fill=(15, 23, 42, 230), outline=_hex_to_rgb(v_color), width=2)
                draw.text((42, 908), f"SERIES #{item_num}: {v_title[:16]}", fill=(255, 255, 255, 255), font=font_def)

                card_img = card_img.convert("RGB")
                card_img.save(item_path, "PNG", quality=95)
                pil_images_for_contact_sheet.append((card_img, v_title, item_num))
            else:
                # Icon / 1:1 or other aspect asset
                raw_rec = AssetLabService.generate_visual_asset(
                    title=f"{anchor_title} - {v_title}",
                    master_prompt=compiled_prompt,
                    target_format=target_format,
                    aspect_ratio=aspect_ratio,
                    color_palette=[v_color, "#0F172A", "#FFFFFF"],
                    reference_images=[anchor_img_url] if anchor_img_url else [],
                    app_slug=app_slug
                )
                # Copy or move generated image to series folder
                src_file = os.path.join(AssetLabService._get_lab_dir(), raw_rec["filename"])
                if os.path.exists(src_file):
                    from shutil import copyfile
                    copyfile(src_file, item_path)
                
                try:
                    img_loaded = Image.open(item_path).convert("RGBA")
                    # Decorate with variation stamp
                    draw = ImageDraw.Draw(img_loaded)
                    font_def = ImageFont.load_default()
                    draw.rounded_rectangle([20, 20, 240, 52], radius=10, fill=(15, 23, 42, 220), outline=_hex_to_rgb(v_color), width=2)
                    draw.text((32, 30), f"#{item_num} • {v_title.upper()[:22]}", fill=(255, 255, 255, 255), font=font_def)
                    img_loaded.save(item_path, "PNG")
                    pil_images_for_contact_sheet.append((img_loaded, v_title, item_num))
                except Exception as e:
                    print(f"[SeriesService] Error decorating variant: {e}")

            item_url = f"/api/asset-lab/series/{series_id}/file/{item_filename}"

            item_record = {
                "item_id": f"{series_id}_item_{item_num}",
                "item_num": item_num,
                "title": v_title,
                "difference": v_diff,
                "accent_color": v_color,
                "filename": item_filename,
                "image_url": item_url,
                "compiled_prompt": compiled_prompt,
                "finished_png_url": None,
                "finished_pdf_url": None
            }

            # 3. Optional: Auto-finish with Output Contextile if requested
            if output_contextile:
                try:
                    clean_ctx = output_contextile.lstrip("@").strip()
                    finish_res = OutputService.process_pipeline(item_path, {"contextile": clean_ctx})
                    if finish_res:
                        item_record["finished_png_url"] = finish_res.get("png_url")
                        item_record["finished_pdf_url"] = finish_res.get("pdf_url")
                except Exception as fe:
                    print(f"[SeriesService] Auto-finish failed for {v_title}: {fe}")

            generated_items.append(item_record)

        # 4. Generate Combined Series Contact Sheet / Montage Grid
        contact_filename = f"contact_sheet_{series_id}.png"
        contact_path = os.path.join(series_dir, contact_filename)
        contact_url = f"/api/asset-lab/series/{series_id}/file/{contact_filename}"

        cls._generate_contact_sheet(
            images_data=pil_images_for_contact_sheet,
            series_title=series_title,
            anchor_title=anchor_title,
            output_path=contact_path
        )

        # 5. Build Downloadable ZIP Archive containing all assets + contact sheet
        zip_filename = f"{series_id}_collection.zip"
        zip_path = os.path.join(series_dir, zip_filename)
        zip_url = f"/api/asset-lab/series/{series_id}/download-zip"

        cls._create_zip_package(series_dir, zip_path)

        # 6. Build Master Series Record
        series_record = {
            "id": series_id,
            "title": series_title,
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "anchor_title": anchor_title,
            "anchor_image_url": anchor_img_url,
            "anchor_prompt": anchor_prompt,
            "target_format": target_format,
            "aspect_ratio": aspect_ratio,
            "output_contextile": output_contextile,
            "consistency_level": consistency_level,
            "app_slug": app_slug,
            "item_count": len(generated_items),
            "items": generated_items,
            "contact_sheet_url": contact_url,
            "zip_url": zip_url,
            "zip_filename": zip_filename
        }

        # Save metadata.json inside the folder
        with open(os.path.join(series_dir, "metadata.json"), "w", encoding="utf-8") as f:
            json.dump(series_record, f, indent=2)

        # Save to global history
        cls.save_history_item(series_record)

        return series_record

    @classmethod
    def _generate_contact_sheet(
        cls,
        images_data: List[Any],
        series_title: str,
        anchor_title: str,
        output_path: str
    ):
        """
        Creates a high-resolution contact sheet / sticker sheet montage grid.
        """
        n = len(images_data)
        if n == 0:
            return

        # Determine grid dimensions
        if n <= 2: cols, rows = 2, 1
        elif n <= 4: cols, rows = 2, 2
        elif n <= 6: cols, rows = 3, 2
        elif n <= 8: cols, rows = 4, 2
        elif n <= 9: cols, rows = 3, 3
        else: cols, rows = 4, 3

        cell_w, cell_h = 480, 480
        # If portrait/card
        first_img = images_data[0][0]
        if first_img.height > first_img.width * 1.2:
            cell_w, cell_h = 360, 504 # 2.5:3.5 aspect

        pad = 24
        header_h = 130
        footer_h = 44

        total_w = pad * (cols + 1) + cols * cell_w
        total_h = header_h + pad * (rows + 1) + rows * cell_h + footer_h

        sheet = Image.new("RGBA", (total_w, total_h), (10, 15, 29, 255))
        draw = ImageDraw.Draw(sheet)
        font = ImageFont.load_default()

        # Header Banner
        draw.rectangle([0, 0, total_w, header_h], fill=(15, 23, 42, 255))
        draw.line([(0, header_h), (total_w, header_h)], fill=(99, 102, 241, 160), width=3)

        # Header Title & Meta
        main_hdr = "GEPPY'S GITBRIDGE • ASSET SERIES COLLECTION"
        draw.text((pad, 20), main_hdr, fill=(99, 102, 241, 255), font=font)
        draw.text((pad, 44), series_title.upper()[:50], fill=(255, 255, 255, 255), font=font)
        sub_hdr = f"Base Anchor: {anchor_title} • {n} Variations • SOT High Consistency"
        draw.text((pad, 74), sub_hdr, fill=(148, 163, 184, 255), font=font)

        # Place cells
        for idx, (img_obj, v_title, item_num) in enumerate(images_data):
            c = idx % cols
            r = idx // cols

            x = pad + c * (cell_w + pad)
            y = header_h + pad + r * (cell_h + pad)

            # Card container backdrop & border
            draw.rounded_rectangle([x - 4, y - 4, x + cell_w + 4, y + cell_h + 4], radius=14, fill=(15, 23, 42, 240), outline=(51, 65, 85, 200), width=2)

            # Resize image to fit cell
            fitted = img_obj.copy()
            fitted.thumbnail((cell_w, cell_h - 40), Image.Resampling.LANCZOS)
            fw, fh = fitted.size
            fx = x + (cell_w - fw) // 2
            fy = y + (cell_h - 40 - fh) // 2

            sheet.paste(fitted, (fx, fy))

            # Bottom cell title banner
            ty = y + cell_h - 32
            draw.rounded_rectangle([x + 8, ty, x + cell_w - 8, ty + 26], radius=6, fill=(30, 41, 59, 230), outline=(99, 102, 241, 140), width=1)
            label_txt = f"#{item_num} {v_title[:24]}"
            draw.text((x + 16, ty + 7), label_txt, fill=(241, 245, 249, 255), font=font)

        # Footer stamp
        foot_txt = f"Generated by Geppy's Galactic Series Studio • {time.strftime('%Y-%m-%d')} • Ready for Print & Stickers"
        draw.text((pad, total_h - 30), foot_txt, fill=(100, 116, 139, 255), font=font)

        sheet = sheet.convert("RGB")
        sheet.save(output_path, "PNG", quality=95)

    @classmethod
    def _create_zip_package(cls, series_dir: str, zip_path: str):
        """Bundle all assets in series directory into a neat ZIP archive."""
        try:
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for root, _, files in os.walk(series_dir):
                    for file in files:
                        if file.endswith(".zip"):
                            continue # Do not include the zip inside itself
                        full_p = os.path.join(root, file)
                        rel_p = os.path.relpath(full_p, series_dir)
                        zf.write(full_p, rel_p)
        except Exception as e:
            print(f"[SeriesService] Error building ZIP archive: {e}")

def _hex_to_rgb(hex_str: str) -> tuple:
    hex_str = hex_str.lstrip("#")
    if len(hex_str) == 3:
        hex_str = "".join([c*2 for c in hex_str])
    try:
        return (int(hex_str[0:2], 16), int(hex_str[2:4], 16), int(hex_str[4:6], 16), 255)
    except:
        return (6, 182, 212, 255)
