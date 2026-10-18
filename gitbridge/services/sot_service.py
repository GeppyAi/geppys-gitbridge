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

EXTENSIVE_VARIABLE_DROPDOWNS = {
    "style": {
        "key": "style",
        "label": "Artistic & Visual Style",
        "icon": "🎨",
        "description": "Extensive library of artistic, cinematic, illustration, and design styles",
        "options": [
            "1980s John Carpenter Atmospheric Horror",
            "A24 Psychological Folk Thriller",
            "1970s Topps Vintage Baseball Trading Card",
            "1950s Classic Gum-Card Offset Lithograph",
            "Saturday-Morning Cartoon Adventure (DuckTales / 90s Toon)",
            "1930s Fleischer Rubber-Hose Vintage Animation",
            "Studio Ghibli Hand-Painted Lush Anime",
            "90s Cel-Shaded Sci-Fi OVA Anime",
            "Cyberpunk Edgerunners High-Contrast Neon Anime",
            "Spider-Verse Halftone Ben-Day Dot Comic Book",
            "Silver Age Jack Kirby Cosmic Comic Book",
            "Dark Horse Noir Graphic Novel Heavy Ink",
            "Pixar / Disney Feature 3D Character Animation",
            "Aardman Stop-Motion Sculpted Claymation",
            "Wes Anderson Symmetrical Pastel Panavision",
            "Classic 1940s High-Contrast Film Noir",
            "1970s Grindhouse Drive-In Exploitation Cinema",
            "Denis Villeneuve Brutalist Sci-Fi IMAX Epic",
            "Tim Burton Gothic German Expressionist Stop-Motion",
            "Apple VisionOS Glassmorphic Spatial UI",
            "Y2K Frutiger Aero Translucent Aqua Gloss",
            "1984 Synthwave Outrun Laser Grid",
            "Vaporwave Mallsoft Pastel Glitch",
            "Cyberpunk 2077 Night City Holographic",
            "Steampunk Victorian Brass & Clockwork",
            "Solarpunk Botanical Art Nouveau Utopia",
            "Dark Fantasy Elden Ring Baroque Gothic",
            "Ukiyo-e Japanese Woodblock Print",
            "Art Deco 1920s Metropolis Geometric Poster",
            "Bauhaus Constructivist Flat Vector",
            "Andy Warhol Pop Art Silkscreen Halftone",
            "Renaissance Chiaroscuro Oil Masterpiece",
            "Impressionist Thick Impasto Brushwork",
            "16-Bit SNES Pixel Art Sprite",
            "Low-Poly PS1 Retro 32-Bit 3D",
            "Isometric 3D Tech Diorama Cutaway",
            "Die-Cut Holographic Prism Vinyl Sticker",
            "Technical Cyanotype Blueprint Schematic"
        ]
    },
    "medium": {
        "key": "medium",
        "label": "Rendering Medium & Format",
        "icon": "🖌️",
        "description": "Physical print stocks, film gauges, 3D engines, and traditional media",
        "options": [
            "8K Octane / Redshift Ray-Traced 3D Render",
            "Unreal Engine 5.5 Lumen & Nanite Real-Time 3D",
            "Anamorphic 35mm Panavision Motion Picture Film",
            "Kodachrome 64 Vintage 35mm Slide Photography",
            "IMAX 70mm Large-Format Cinema Film",
            "Polaroid SX-70 Instant Film with Soft Chemical Bleed",
            "1880s Wet-Plate Collodion Silver Tintype",
            "1980s VHS Magnetic Tape with Tracking Scanlines",
            "Offset Lithography on Aged Matte Cardboard Stock",
            "Risograph Soy-Ink Duotone Grain Print",
            "Silkscreen Serigraph Hand-Pulled Poster Print",
            "Glossy Die-Cut Vinyl Sticker with 4mm White Rim",
            "Holographic Rainbow Diffraction Foil Stamping",
            "Hard Enamel Cloisonné Pin with Polished Gold Dividers",
            "Struck 24K Gold & Mint Emerald Medallion Coin Relief",
            "3D iOS Frosted Glass Squircle App Icon",
            "Clean Scalable Vector SVG Flat Illustration",
            "Macro Studio Product Packaging Photography",
            "ZBrush Digital Clay Sculpted Miniature",
            "Translucent Designer Vinyl Art Toy Figure",
            "Hand-Stitched Felt & Yarn Plushie Amigurumi",
            "Watercolor & Gouache on Cold-Press Cotton Paper",
            "Heavy Impasto Oil Paint on Stretched Linen",
            "1980s Airbrush Acrylic Sci-Fi Poster Art",
            "Pen, India Ink & Crosshatching on Bristol Board",
            "Charcoal & White Conte Crayon on Toned Paper",
            "Copic Marker Industrial Design Sketch",
            "Laser-Cut Multi-Layer Paper Shadowbox",
            "Leaded Stained-Glass Cathedral Window",
            "Bent-Glass Gas Neon Sign Tubing",
            "Intaglio Engraved Currency Banknote Print",
            "300 DPI CMYK Commercial Print-Ready Sheet"
        ]
    },
    "lighting": {
        "key": "lighting",
        "label": "Lighting Rig & Illumination",
        "icon": "💡",
        "description": "Studio setups, atmospheric natural light, neon rigs, and cinema lighting",
        "options": [
            "Volumetric Three-Point Studio Softbox",
            "Cyberpunk Dual-Tone Neon Rim (Electric Cyan & Magenta)",
            "Dramatic Chiaroscuro / Rembrandt Single Key Light",
            "Cold Cyan-Blue Full Moonlight & Volumetric Fog Shafts",
            "Flickering Warm Amber Lantern & Candlelight",
            "Golden Hour Low Sunbeam & Warm Rim Glow",
            "Twilight Blue-Hour Diffused Skylight",
            "High-Key Pure White Commercial Studio Softbox",
            "Moody Deep-Space Starlight & Nebula Backlight",
            "Cinematic Anamorphic Horizontal Streak Lens Flare",
            "Bioluminescent Alien Flora & Fauna Underglow",
            "Forked Lightning Strike High-Contrast Flash Silhouette",
            "Film Noir Venetian Blind Slatted Window Shadows",
            "Vintage 1970s On-Camera Direct Flashbulb",
            "Harsh Midday Sun with Crisp Cast Shadows",
            "Crimson Darkroom / Emergency Klaxon Red Alert Light",
            "Stage Concert Spotlight cutting through Haze",
            "Warm Campfire / Hearth Upward Flicker",
            "Rain-Slicked Asphalt Neon Street Reflections",
            "Subsurface Scattering Translucent Backlight",
            "Ray-Traced Global Illumination with Glass Caustics",
            "Ultraviolet Blacklight Fluorescent Glow",
            "Volumetric God-Rays Piercing Dusty Cathedral/Attic",
            "Ring-Light Portrait with Circular Eye Catchlights",
            "Total Solar Eclipse Corona Silhouette Rim",
            "CRT Monitor Green/Amber Phosphor Face Glow",
            "Prismatic Crystal Rainbow Light Dispersion",
            "Overcast North-Facing Soft Painterly Window Light"
        ]
    },
    "camera_lens": {
        "key": "camera_lens",
        "label": "Camera Angle, Framing & Lens",
        "icon": "📷",
        "description": "Focal lengths, camera angles, shot framing, and optical characteristics",
        "options": [
            "85mm f/1.2 Portrait Prime (Creamy Shallow Bokeh)",
            "35mm f/1.4 Anamorphic Cinema Wide",
            "50mm Standard Human-Eye Studio Framing",
            "24mm Dynamic Low-Angle Heroic Perspective",
            "14mm Ultra-Wide Dramatic Action Perspective",
            "100mm f/2.8 Macro Extreme Detail Close-Up",
            "200mm Telephoto Compressed Background",
            "Isometric 45° Orthographic 3D Diorama Angle",
            "Top-Down 90° Flat-Lay Knolling View",
            "Dutch-Angle Tilted Suspense Horror Framing",
            "Worm's-Eye Monumental Looking-Up Angle",
            "Bird's-Eye High Aerial Overhead View",
            "Extreme Close-Up (ECU) Eyes / Visor Reflection",
            "Medium Bust Portrait (Chest-Up Trading Card Framing)",
            "Medium Cowboy Shot (Waist-Up Action Stance)",
            "Full-Body Heroic Standing Character Shot",
            "Over-the-Shoulder Cinematic Narrative Framing",
            "Centered Symmetrical Wes Anderson Composition",
            "Tilt-Shift Miniature Toy-World Shallow Focus",
            "Split-Diopter Dual Foreground/Background Sharp Focus",
            "Vintage Helios 44-2 Swirly Bokeh Lens",
            "1860s Petzval Brass Lens Radial Edge Blur",
            "1:1 Centered App Icon Squircle Framing",
            "2.5:3.5 Vertical Collector Trading Card Framing",
            "16:9 Widescreen Cinema Scope Framing"
        ]
    },
    "materials": {
        "key": "materials",
        "label": "Materials, Surfaces & Textures",
        "icon": "💎",
        "description": "Physical surface properties, metals, fabrics, paper stocks, and shaders",
        "options": [
            "Frosted Translucent Glass (Glassmorphism)",
            "Brushed Anodized Titanium & Aerospace Aluminum",
            "Matte Dark Obsidian & Woven Carbon Fiber",
            "Iridescent Liquid Rainbow Hologram Foil",
            "Aged Matte Buff Cardboard with Worn Corners",
            "Glossy UV-Laminated Die-Cut Vinyl Sticker Stock",
            "Polished 24K Gold & Mirror Chrome",
            "Weathered 1890s Victorian Timber & Mansard Slate",
            "Glowing Neon Wireframe & Soldermask Circuit Traces",
            "Polished Ceramic White & Smooth Porcelain",
            "Distressed Vintage Saddle Leather & Brass Rivets",
            "Soft Cotton Jersey Fabric (Signature Blue Geppy Shirt)",
            "Ballistic Nylon & Hexagonal Kevlar Space Suit",
            "Hammered Antique Copper with Verdigris Patina",
            "Chiseled Gothic Gargoyle Limestone & Moss",
            "Translucent Subsurface Gummy / Resin Plastic",
            "Hard Enamel Cloisonné with Raised Metal Outlines",
            "Holographic Cracked-Ice Prismatic Foil",
            "Halftone CMYK Dot-Matrix Newsprint Paper",
            "Embossed Heavy Cotton Rag Archival Paper",
            "Velvet & Embroidered Gold Bullion Thread",
            "Iridescent Mother-of-Pearl & Abalone Inlay",
            "Cracked Volcanic Basalt with Molten Lava Veins",
            "Wet Cobblestone with Puddle Specular Reflections"
        ]
    },
    "color_grading": {
        "key": "color_grading",
        "label": "Color Palette & Film Grading",
        "icon": "🌈",
        "description": "Color harmonies, LUT film grades, and brand palettes",
        "options": [
            "Geppy Signature Palette (Electric Orange #F59E0B, Deep Navy #0F172A, Cyan #06B6D4)",
            "Geppy's Cash Mint Emerald, Bullion Gold & Obsidian",
            "Kodachrome 1970s Warm Nostalgic Vintage Grade",
            "Gothic Horror Cold Moonlight Cyan-Blue & Blood Crimson",
            "Cyberpunk Electric Magenta, Laser Cyan & Deep Violet",
            "Blockbuster Cinema Teal & Orange Complementary LUT",
            "3-Strip Technicolor Hyper-Saturated 1950s Palette",
            "Bleach-Bypass Gritty Desaturated Silver & High Contrast",
            "Sin City High-Contrast Black & White with Crimson Splash",
            "Wes Anderson Pastel Mint, Millennial Pink & Mustard Gold",
            "Synthwave Outrun Sunset Purple, Hot Pink & Chrome Gold",
            "Vaporwave Pastel Lavender, Bubblegum Pink & Poolside Aqua",
            "Minimalist Luxury Matte Black, Charcoal & Brushed Champagne Gold",
            "Solarpunk Lush Emerald, Warm Sunlight Gold & Cream Ivory",
            "Matrix Digital Phosphor Green & Pitch Black",
            "Sepia Antique Daguerreotype Warm Monochrome",
            "Cyanotype Prussian Blue & Crisp White Technical Print",
            "CMYK Four-Color Vintage Comic Halftone Palette",
            "Nordic Noir Desaturated Slate Grey & Glacial Blue",
            "Infrared Aerochrome Surreal Magenta & Turquoise",
            "Autumnal Halloween Pumpkin Orange, Deep Purple & Midnight Black",
            "GameBoy Classic 4-Shade Olive Pixel Palette"
        ]
    },
    "mood_atmosphere": {
        "key": "mood_atmosphere",
        "label": "Mood, Weather & Atmosphere",
        "icon": "🌫️",
        "description": "Emotional tone, environmental weather particles, and atmospheric effects",
        "options": [
            "Upbeat, Friendly & Heroic Saturday-Morning Energy",
            "Eerie 1980s Horror with Thick Rolling Ground Fog",
            "Stormy Midnight Downpour with Forked Lightning",
            "Nostalgic 1970s Summer Ballpark Sunshine",
            "Commanding Starship Bridge in Deep Nebula Orbit",
            "Cyberpunk Rain-Slicked Alley with Rising Steam Vents",
            "Cozy Candlelit Victorian Library during Rainstorm",
            "High-Stakes Championship Arena with Confetti & Sparks",
            "Mysterious Film Noir Foggy Docks at 2 AM",
            "Whimsical Enchanted Forest with Floating Fireflies",
            "Zero-Gravity Spacewalk with Drifting Stardust",
            "Crisp Ultra-Clean Apple Keynote Studio Minimalism",
            "Blizzard Whiteout with Swirling Snowflakes & Frost",
            "Volcanic Ash & Floating Glowing Cinder Embers",
            "Retro 1980s Neon Arcade Euphoria",
            "Post-Apocalyptic Golden Dust Storm",
            "Underwater Abyssal Calm with Rising Air Bubbles",
            "Triumphant Golden Victory Celebration"
        ]
    },
    "era": {
        "key": "era",
        "label": "Era & Time Period",
        "icon": "🕰️",
        "description": "Historical, retro, contemporary, or far-future era setting",
        "options": [
            "2026 Next-Gen AI Frontier",
            "3000 AD Deep-Space Galactic Starfleet Era",
            "1990s Saturday-Morning Cartoon & 16-Bit Golden Era",
            "1980s VHS Horror, Synthwave & Arcade Era",
            "1970s Topps Vintage Baseball & Kodachrome Era",
            "1960s Apollo Space Race & Mid-Century Atomic Age",
            "1950s Golden Age Americana & Chrome Diners",
            "1940s Wartime Aviation & Classic Film Noir",
            "1930s Art Deco & Golden Age Rubber-Hose Cartoons",
            "1920s Roaring Twenties Jazz & Speakeasy Era",
            "1890s Victorian Gothic & Gaslight Mansion Era",
            "1880s Wild West Frontier & Steam Locomotive Era",
            "Y2K Year 2000 Translucent Tech & Early Web",
            "Medieval Dark Fantasy & Castle Siege Era",
            "Feudal Japan Samurai & Edo Woodblock Era",
            "Retro-Futuristic Raygun Gothic 1950s Tomorrowland",
            "Timeless Modernist Studio"
        ]
    },
    "framing_border": {
        "key": "framing_border",
        "label": "Frame, Border & Container Layout",
        "icon": "🖼️",
        "description": "Card borders, icon squircles, sticker rims, and decorative frames",
        "options": [
            "Full-Bleed Edge-to-Edge Scene (No Border)",
            "1970s Topps Trading Card Border + Arched Team Banner + Star Badge",
            "1950s Vintage Gum Card Off-White Border + Bottom Nameplate",
            "Thick White Die-Cut Vinyl Sticker Contour Rim (Transparent BG)",
            "Geppy Official Hexagonal #F59E0B Orange Beveled Emblem Frame",
            "3D iOS Rounded Squircle App Icon Container with Beveled Rim",
            "Glassmorphic HUD Telemetry Card with Hairline Cyan Glow Border",
            "1980s VHS Horror Movie Cover Sleeve + Title Treatment",
            "Vintage Polaroid Instant Photo Frame with Bottom Caption Strip",
            "Comic Book Issue Cover with Corner Box & Halftone Title Banner",
            "Holographic Foil TCG Ultra-Rare Collector Card Frame",
            "Ornate Victorian Gilded Baroque Museum Picture Frame",
            "Circular Embroidered Mission Patch with Merrowed Thread Edge",
            "Arcade CRT Cabinet Bezel with Curved Glass Reflection",
            "Weathered Parchment Wanted Poster Border",
            "300 DPI Print Sheet with 0.125\" Bleed & Registration Crop Marks"
        ]
    },
    "fabrication_mode": {
        "key": "fabrication_mode",
        "label": "Physical Fabrication & Blank Output Constraint",
        "icon": "🔥",
        "description": "Laser engraving (1-bit black & white burn), stencil cutting with edge bridges, vinyl cutter paths, and dye sublimation specs",
        "options": [
            "Laser Engraver: High-Contrast 1-Bit Black & White Wood/Slate Burn (Black = Burn, White = Unburned Blank)",
            "Laser Engraver: Halftone Jarvis Dither Photo Burn (Monochrome Black & White Dots)",
            "Laser Engraver: Deep Relief 8-Bit Grayscale Depth Map Engraving",
            "Cut Stencil with Edge Connections: Bold Cutout Shapes + Structural Bridges Holding All Inner Islands",
            "Multi-Layer Spray Stencil with Registration Corner Marks & Connected Bridges",
            "Vinyl Cutter / Plotter (Cricut / Silhouette): Solid Single-Color Weed-Ready Vector Paths with Connected Bridges",
            "Layered Multi-Color Adhesive Vinyl Decal (2-4 Solid Spot Color Layers, No Gradients)",
            "Dye Sublimation Full-Color Transfer (300 DPI + 0.125\" Full Bleed Margin)",
            "Rotary Tumbler / Mug Wrap Sublimation (Full-Bleed Seamless Tapered Cylinder Wrap)",
            "UV Direct-to-Substrate Print with White Underbase Layer + Gloss Varnish",
            "Screen Print Spot-Color Separation (Halftone Mesh Ready, High-Contrast Solid Ink)",
            "CNC Router V-Carve Vector Linework (Closed Non-Overlapping Toolpaths)",
            "Leather Tooling & Hot Foil Brass Stamp Die (Bold High-Contrast Relief Line Art)",
            "DTF (Direct-to-Film) Apparel Heat Transfer with Transparent Alpha Background"
        ]
    }
}

MODIFIER_TAXONOMY = {
    "style": EXTENSIVE_VARIABLE_DROPDOWNS["style"]["options"],
    "medium": EXTENSIVE_VARIABLE_DROPDOWNS["medium"]["options"],
    "lighting": EXTENSIVE_VARIABLE_DROPDOWNS["lighting"]["options"],
    "camera_lens": EXTENSIVE_VARIABLE_DROPDOWNS["camera_lens"]["options"],
    "materials": EXTENSIVE_VARIABLE_DROPDOWNS["materials"]["options"],
    "color_grading": EXTENSIVE_VARIABLE_DROPDOWNS["color_grading"]["options"],
    "mood_atmosphere": EXTENSIVE_VARIABLE_DROPDOWNS["mood_atmosphere"]["options"],
    "era": EXTENSIVE_VARIABLE_DROPDOWNS["era"]["options"],
    "framing_border": EXTENSIVE_VARIABLE_DROPDOWNS["framing_border"]["options"],
    "fabrication_mode": EXTENSIVE_VARIABLE_DROPDOWNS["fabrication_mode"]["options"],
    "theme": [
        "Cosmic Galactic & Nebula",
        "Apple Glassmorphic Clean",
        "Cyber-SciFi Holographic",
        "Retro 80s Synthwave",
        "Minimalist Luxury Dark",
        "Hyper-Detailed Unreal Engine 5",
        "Solarpunk High-Tech",
        "Vector Isometric Clean",
        "Photorealistic 8K Commercial",
        "1980s Gothic Horror Cinema",
        "1970s Vintage Sports Memorabilia",
        "Saturday-Morning Cartoon Adventure",
        "Laser Engraving & Woodburn Pyography",
        "Cuttable Stencil & Vinyl Fabrication"
    ]
}

ARCHETYPES = {
    # --- 🔒 SOURCE OF TRUTH (SOT) ITEMS (Unchanging Ground-Truth Entities) ---
    "character": {
        "id": "character",
        "entity_kind": "sot",
        "label": "Person / Character SOT",
        "icon": "👤",
        "badge": "Unchanging Person/Character SOT",
        "description": "Unchanging ground-truth person, character, or mascot (facial likeness, hair, outfit). Use standalone or drop into any Contextile template."
    },
    "place": {
        "id": "place",
        "entity_kind": "sot",
        "label": "Specific Place / Location SOT",
        "icon": "🏛️",
        "badge": "Unchanging Place SOT",
        "description": "Unchanging specific real or fictional place, building, room, or landmark. Can be embedded inside a Contextile template or used directly."
    },
    "environment": {
        "id": "environment",
        "entity_kind": "sot",
        "label": "Specific Place / Environment SOT",
        "icon": "🌌",
        "badge": "Unchanging Place SOT",
        "description": "Specific location, architectural setting, flight deck, or landscape source of truth."
    },
    "brand_asset": {
        "id": "brand_asset",
        "entity_kind": "sot",
        "label": "Brand Logo / Emblem SOT",
        "icon": "🏷️",
        "badge": "Unchanging Brand SOT",
        "description": "Unchanging official brand logo, crest, emblem, or wordmark."
    },
    "prop": {
        "id": "prop",
        "entity_kind": "sot",
        "label": "Specific Item / Prop SOT",
        "icon": "🎸",
        "badge": "Unchanging Prop SOT",
        "description": "Unchanging specific object, vehicle, instrument, or wearable prop for characters to hold, wear, or interact with."
    },
    # --- 📐 CONTEXTILES OF TRUTH (Physical Blanks: Both Source of Truth for the Blank AND Calibrated Sizing/Output Contextile) ---
    "blank_substrate": {
        "id": "blank_substrate",
        "entity_kind": "contextile_of_truth",
        "label": "Contextile of Truth (Physical Blank & Sizing Template)",
        "icon": "📐",
        "badge": "Contextile of Truth (Blank)",
        "description": "Upload a photo of a physical blank item (wood plaque, slate coaster, tumbler, mug, ornament, acrylic blank, apparel) to create a calibrated sizing & boundary template. Functions as a Sizing/Output Contextile AND the Source of Truth for the physical blank."
    },
    # --- 🎛️ CONTEXTILES (Reusable Templatized Settings, Samples & SOT Slots) ---
    "style": {
        "id": "style",
        "entity_kind": "contextile",
        "label": "Style / Frame Contextile Template",
        "icon": "🎭",
        "badge": "Contextile Template",
        "description": "Templatized series of style settings, sample images, and toggleable specifics (e.g. '70s Baseball Card with optional funny mustache, Stencil with Edge Connections, Laser B&W Burn) to apply to any SOT, Blank, or uploaded photo."
    },
    "scene_template": {
        "id": "scene_template",
        "entity_kind": "contextile",
        "label": "Place + Mood Scene Contextile",
        "icon": "🎬",
        "badge": "Scene Contextile Template",
        "description": "A Contextile template that locks a Specific Place SOT in a specific genre/style (e.g. Horror Movie at a Specific Place) so you can drop in different Character SOTs while keeping the exact same place and feeling."
    },
    "icon_set": {
        "id": "icon_set",
        "entity_kind": "contextile",
        "label": "App Icon Suite Contextile",
        "icon": "🎨",
        "badge": "Icon Contextile Template",
        "description": "Templatized app icon container settings (squircle curvature, beveling, lighting, and sample icons) that any subject or SOT can be dropped into."
    },
    "ui_component": {
        "id": "ui_component",
        "entity_kind": "contextile",
        "label": "UI Component Contextile",
        "icon": "🧩",
        "badge": "UI Contextile Template",
        "description": "Templatized UI design tokens, HUD frames, glassmorphic cards, and layout rules."
    },
    "output": {
        "id": "output",
        "entity_kind": "contextile",
        "label": "Output & Print Spec Contextile",
        "icon": "🖨️",
        "badge": "Output Contextile Template",
        "description": "Templatized export & fabrication settings: laser black & white burn, stencil with edge connections, vinyl cut lines, transparent cutouts, die-cut sticker rims, and 300 DPI print-ready PDFs."
    },
    "general": {
        "id": "general",
        "entity_kind": "sot",
        "label": "General SOT Anchor",
        "icon": "✨",
        "badge": "General SOT",
        "description": "Custom Source of Truth reference item."
    }
}

def call_gemini(messages: List[Dict[str, Any]], system_instruction: str) -> Optional[str]:
    from gitbridge.services.central_key_service import CentralKeyService
    return CentralKeyService.call_gemini(messages, system_instruction)


class SOTService:

    SOT_ARCHETYPES = {"character", "place", "environment", "brand_asset", "prop", "general"}
    CONTEXTILE_OF_TRUTH_ARCHETYPES = {"blank_substrate"}
    CONTEXTILE_ARCHETYPES = {"style", "scene_template", "icon_set", "ui_component", "output"}

    @classmethod
    def infer_entity_kind(cls, archetype: Optional[str], modifiers: Optional[Dict[str, Any]] = None, name: str = "") -> str:
        """
        Determine whether a record is:
        - 'sot': Unchanging Source of Truth (person, character, place, brand, prop)
        - 'contextile_of_truth': Physical Blank & Sizing Template (acts as both sizing Contextile and Source of Truth for the physical blank)
        - 'contextile': Templatized Contextile settings/style/fabrication rule (e.g. Stencil with Edge Connections, 70s Baseball Card, Laser B&W Burn)
        """
        mods = modifiers if isinstance(modifiers, dict) else {}
        explicit_kind = str(mods.get("entity_kind") or "").lower().strip()
        if explicit_kind in ("sot", "contextile", "contextile_of_truth"):
            return explicit_kind
        arch = (archetype or "character").lower().strip()
        if arch in cls.CONTEXTILE_OF_TRUTH_ARCHETYPES or isinstance(mods.get("blank_spec"), dict):
            return "contextile_of_truth"
        if arch in cls.CONTEXTILE_ARCHETYPES:
            return "contextile"
        if mods.get("embedded_sot_handles") or mods.get("option_toggles"):
            return "contextile"
        n_low = (name or "").lower()
        if any(k in n_low for k in ["blank", "substrate", "plaque", "coaster", "tumbler", "mug-blank"]):
            return "contextile_of_truth"
        if any(k in n_low for k in ["baseball-card", "sport-card", "sticker", "icon", "card-ui", "template", "style", "print", "pdf", "stencil", "laser", "vinyl", "sublimation"]):
            return "contextile"
        return "sot"

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
    def get_variable_dropdown_catalog() -> Dict[str, Dict[str, Any]]:
        """Return the extensive variable dropdown catalog (style, medium, lighting, camera_lens, materials, color_grading, mood_atmosphere, era, framing_border, fabrication_mode)."""
        return EXTENSIVE_VARIABLE_DROPDOWNS

    @staticmethod
    def get_archetypes() -> Dict[str, Dict[str, Any]]:
        """Return supported SOT, Contextile of Truth, and Contextile Archetype definitions."""
        return ARCHETYPES

    EXTRACTION_STYLE_KEYWORDS: Dict[str, Dict[str, Any]] = {
        "vs": {
            "key": "vs",
            "aliases": ["vs", "vis", "visual", "style"],
            "prefix_example": "@vsGeppy",
            "alt_example": "@visGeppy",
            "label": "Visual Style Only",
            "short_label": "@vs / @vis",
            "icon": "🎨",
            "badge_color": "fuchsia",
            "role_override": "style_only",
            "description": "Extracts ONLY the visual rendering style, medium, tactile surface texture, and material feel (e.g., Geppy's claymation-ish sculpted designer vinyl toy aesthetic) without copying the character's literal face/identity.",
            "directive_template": (
                "🎨 VISUAL STYLE EXTRACTION ONLY ({raw_tag} -> extracting visual style from @{handle} '{title}'): "
                "Apply ONLY the visual rendering style, artistic medium, surface material feel, sculpt/brushwork texture, and studio lighting aesthetic of @{handle}. "
                "Extracted Visual Style Recipe: {style_summary}. "
                "CRITICAL: Do NOT copy @{handle}'s literal character identity, face, or name — render the user's target subject/concept IN @{handle}'s visual style!"
            )
        },
        "q": {
            "key": "q",
            "aliases": ["q", "chibi", "sd", "qstyle"],
            "prefix_example": "@qGeppy",
            "alt_example": "@chibiGeppy",
            "label": "Q-Style / Chibi Proportions",
            "short_label": "@q / @chibi",
            "icon": "🧸",
            "badge_color": "pink",
            "role_override": "style_only",
            "description": "Extracts Q-Style (SD / Chibi / Collectible Designer Vinyl Figure) 1:2.5 cute stylized proportions — oversized expressive head, compact rounded body, chunky tactile hands — combined with the target's aesthetic.",
            "directive_template": (
                "🧸 Q-STYLE / CHIBI COLLECTIBLE PROPORTIONS EXTRACTION ({raw_tag} -> from @{handle} '{title}'): "
                "Render with cute Q-Style (Super-Deformed / Chibi / Designer Vinyl Art Toy) 1:2.5 proportions — oversized expressive head/visor, compact rounded torso, chunky stubby limbs, and tactile sculpted vinyl/clay charm — blended with @{handle}'s visual aesthetic ({style_summary})."
            )
        },
        "mat": {
            "key": "mat",
            "aliases": ["mat", "tex", "material", "texture"],
            "prefix_example": "@matGeppy",
            "alt_example": "@texGeppy",
            "label": "Material & Texture Only",
            "short_label": "@mat / @tex",
            "icon": "🏺",
            "badge_color": "amber",
            "role_override": "materials",
            "description": "Extracts ONLY the physical surface materials and tactile shaders (e.g., sculpted matte stop-motion polymer clay with thumbprint micro-texture, soft-touch vinyl, brushed titanium, or frosted glass).",
            "directive_template": (
                "🏺 MATERIAL & SURFACE SHADER EXTRACTION ONLY ({raw_tag} -> from @{handle} '{title}'): "
                "Apply ONLY the physical surface materials, tactile textures, and shader finishes of @{handle} ({materials_summary}). "
                "Do NOT copy subject identity, pose, or layout."
            )
        },
        "pal": {
            "key": "pal",
            "aliases": ["pal", "col", "color", "palette", "lut"],
            "prefix_example": "@palGeppy",
            "alt_example": "@colGeppy",
            "label": "Color Palette & Grading Only",
            "short_label": "@pal / @col",
            "icon": "🌈",
            "badge_color": "cyan",
            "role_override": "style_only",
            "description": "Extracts ONLY the signature color palette, hex swatches, and tonal LUT harmony (e.g., Geppy's Amber Gold #F59E0B, Electric Cyan #06B6D4, Cosmic Indigo #6366F1 & Obsidian #0F172A).",
            "directive_template": (
                "🌈 COLOR PALETTE & TONAL GRADING EXTRACTION ONLY ({raw_tag} -> from @{handle} '{title}'): "
                "Apply ONLY the signature color palette and tonal LUT harmony of @{handle} ({palette_summary}). "
                "Do NOT copy subject identity or geometry."
            )
        },
        "lit": {
            "key": "lit",
            "aliases": ["lit", "light", "lighting"],
            "prefix_example": "@litGeppy",
            "alt_example": "@lightGeppy",
            "label": "Lighting & Rim Setup Only",
            "short_label": "@lit / @light",
            "icon": "💡",
            "badge_color": "yellow",
            "role_override": "lighting",
            "description": "Extracts ONLY the studio lighting rig, rim lights, key/fill ratios, and volumetric atmosphere from the referenced SOT.",
            "directive_template": (
                "💡 LIGHTING RIG & ATMOSPHERE EXTRACTION ONLY ({raw_tag} -> from @{handle} '{title}'): "
                "Apply ONLY the studio lighting setup, rim illumination, shadow contrast, and volumetric atmosphere of @{handle} ({lighting_summary})."
            )
        },
        "id": {
            "key": "id",
            "aliases": ["id", "char", "face", "identity"],
            "prefix_example": "@idGeppy",
            "alt_example": "@charGeppy",
            "label": "Pure Identity / Face Lock",
            "short_label": "@id / @char",
            "icon": "👤",
            "badge_color": "emerald",
            "role_override": "mascot",
            "description": "Locks ONLY the character's core facial/anatomical identity and design landmarks while stripping away their default rendering medium so they can be rendered in any new style.",
            "directive_template": (
                "👤 PURE IDENTITY & LIKENESS LOCK ({raw_tag} -> from @{handle} '{title}'): "
                "Preserve ONLY the core character/person identity, facial structure, and signature design landmarks of @{handle} ({reference_text}), while freely adapting the rendering medium and artistic style to the rest of the prompt."
            )
        },
        "fit": {
            "key": "fit",
            "aliases": ["fit", "gear", "outfit", "suit", "armor"],
            "prefix_example": "@fitGeppy",
            "alt_example": "@gearGeppy",
            "label": "Outfit, Suit & Gear Only",
            "short_label": "@fit / @gear",
            "icon": "🧥",
            "badge_color": "indigo",
            "role_override": "item",
            "description": "Extracts ONLY the costume, flight exosuit, armor, visor/helmet, and wearable accessories so another character or concept can wear or be themed around that gear.",
            "directive_template": (
                "🧥 OUTFIT, SUIT & GEAR EXTRACTION ONLY ({raw_tag} -> from @{handle} '{title}'): "
                "Extract ONLY the signature costume, flight suit, armor, visor, and wearable gear from @{handle} ({gear_summary}) and equip/theme the target character or subject with them — without copying @{handle}'s face/identity."
            )
        },
        "sil": {
            "key": "sil",
            "aliases": ["sil", "line", "contour", "silhouette"],
            "prefix_example": "@silGeppy",
            "alt_example": "@lineGeppy",
            "label": "Silhouette & Cutout Linework",
            "short_label": "@sil / @line",
            "icon": "✂️",
            "badge_color": "rose",
            "role_override": "style_only",
            "description": "Extracts ONLY the outer contour silhouette, bold line weights, and cutout geometry — ideal for stencils with edge connections, 1-bit laser engraving, and vinyl cutting.",
            "directive_template": (
                "✂️ SILHOUETTE, LINEWORK & CONTOUR EXTRACTION ({raw_tag} -> from @{handle} '{title}'): "
                "Extract ONLY the bold outer contour silhouette, clean line weight hierarchy, and recognizable graphic cutout geometry of @{handle} — optimized for laser engraving, bridged stencils, vinyl cutting, or emblems."
            )
        },
        "comp": {
            "key": "comp",
            "aliases": ["comp", "cam", "layout", "framing"],
            "prefix_example": "@compGeppy",
            "alt_example": "@camGeppy",
            "label": "Camera & Composition Only",
            "short_label": "@comp / @cam",
            "icon": "📐",
            "badge_color": "sky",
            "role_override": "style_only",
            "description": "Extracts ONLY the camera focal length, angle, framing geometry, and container/border layout without copying subject identity.",
            "directive_template": (
                "📐 CAMERA, COMPOSITION & FRAMING EXTRACTION ONLY ({raw_tag} -> from @{handle} '{title}'): "
                "Apply ONLY the camera focal length, shot angle, framing geometry, and border/container layout of @{handle} ({comp_summary})."
            )
        },
        "vibe": {
            "key": "vibe",
            "aliases": ["vibe", "mood", "era"],
            "prefix_example": "@vibeGeppy",
            "alt_example": "@moodGeppy",
            "label": "Mood, Vibe & Era Only",
            "short_label": "@vibe / @mood",
            "icon": "✨",
            "badge_color": "violet",
            "role_override": "style_only",
            "description": "Extracts ONLY the overarching emotional mood, era aesthetic, and genre vibe.",
            "directive_template": (
                "✨ MOOD, VIBE & ERA EXTRACTION ONLY ({raw_tag} -> from @{handle} '{title}'): "
                "Apply ONLY the overarching emotional mood, era nostalgia, and genre atmosphere of @{handle} ({vibe_summary})."
            )
        },
        "clay": {
            "key": "clay",
            "aliases": ["clay", "vinyl", "3d", "sculpt"],
            "prefix_example": "@clayGeppy",
            "alt_example": "@vinylGeppy",
            "label": "Claymation & Vinyl Sculpt",
            "short_label": "@clay / @vinyl / @3d",
            "icon": "🗿",
            "badge_color": "orange",
            "role_override": "style_only",
            "description": "Renders the subject as a tactile 3D stop-motion sculpted claymation & designer collectible vinyl figure with artisan clay thumbprint micro-texture and smooth vinyl joints.",
            "directive_template": (
                "🗿 CLAYMATION & DESIGNER VINYL TOY SCULPT EXTRACTION ({raw_tag} -> from @{handle} '{title}'): "
                "Render the subject as a tactile 3D stop-motion sculpted claymation and soft-touch designer collectible vinyl art toy figure (hand-sculpted polymer clay with subtle thumbprint micro-texture, smooth satin vinyl joints, rounded bevels, and miniature diorama studio lighting inspired by @{handle})."
            )
        },
        "flat": {
            "key": "flat",
            "aliases": ["flat", "vec", "vector", "2d"],
            "prefix_example": "@flatGeppy",
            "alt_example": "@vecGeppy",
            "label": "2D Vector / Cel Sticker",
            "short_label": "@flat / @vec",
            "icon": "✒️",
            "badge_color": "teal",
            "role_override": "style_only",
            "description": "Translates the referenced SOT's aesthetic into crisp 2D flat vector / cel-shaded illustration with bold outlines and spot-color clarity.",
            "directive_template": (
                "✒️ 2D FLAT VECTOR & CEL-SHADED EXTRACTION ({raw_tag} -> from @{handle} '{title}'): "
                "Translate @{handle}'s visual language into crisp 2D flat vector / cel-shaded graphic illustration with bold ink outlines, clean spot colors, and die-cut sticker clarity."
            )
        }
    }

    GEPPY_BUILTIN_PROFILE: Dict[str, Any] = {
        "name": "geppy",
        "title": "Geppy (Claymation & Vinyl Galactic Mascot)",
        "archetype": "character",
        "entity_kind": "sot",
        "reference_type": "text",
        "reference_text": (
            "Charismatic galactic commander mascot rendered in Geppy's signature claymation-ish sculpted designer vinyl toy style: "
            "hand-sculpted stop-motion polymer clay texture blended with smooth satin-matte collectible vinyl figure proportions, "
            "wearing an obsidian-and-amber-gold flight suit with a glowing translucent cyan visor reflecting swirling nebulae, "
            "chunky expressive sculpted hands, and warm miniature diorama studio rim lighting."
        ),
        "style_summary": (
            "Aardman stop-motion sculpted claymation meets tactile matte-and-gloss designer vinyl art toy figure "
            "(hand-sculpted polymer clay surface with subtle artisan thumbprint micro-textures, smooth satin soft-vinyl joints, "
            "chunky rounded collectible proportions, glossy translucent cyan visor refraction, warm amber-gold & electric cyan neon rim lighting)"
        ),
        "materials_summary": (
            "Soft Vinyl Designer Toy (Bearbrick / Funko), hand-sculpted matte stop-motion polymer clay with subtle thumbprint micro-texture, "
            "Frosted Translucent Cyan Acrylic Visor, Brushed Anodized Amber-Gold Trim"
        ),
        "palette_summary": (
            "Geppy Signature Palette — Amber Gold (#F59E0B), Electric Visor Cyan (#06B6D4), Cosmic Indigo (#6366F1), and Deep Flight-Suit Obsidian (#0F172A)"
        ),
        "lighting_summary": (
            "Miniature Stop-Motion Diorama Volumetric Studio Light, Cyberpunk Cyan & Warm Amber Rim Glow, Moody Starlight Backlight"
        ),
        "gear_summary": (
            "Obsidian-and-amber-gold sculpted vinyl flight exosuit with gold commander shoulder bars, galactic chest crest, and illuminated translucent cyan visor helmet"
        ),
        "color_palette": ["#F59E0B (Geppy Amber Gold)", "#06B6D4 (Visor Electric Cyan)", "#6366F1 (Cosmic Indigo)", "#0F172A (Flight-Suit Obsidian)"],
        "modifiers": {
            "entity_kind": "sot",
            "style": ["Aardman Stop-Motion Sculpted Claymation", "Pixar / Disney Feature 3D Character Animation"],
            "medium": ["8K Octane / Redshift Ray-Traced 3D Render", "ZBrush High-Poly Digital Clay Sculpt"],
            "materials": ["Soft Vinyl Designer Toy (Bearbrick / Funko)", "Frosted Translucent Acrylic & Glass", "Polished 24K Gold & Chrome Bevels"],
            "lighting": ["Volumetric God Rays & Atmospheric Rim Glow", "Dual-Tone Neon Cyan & Magenta Edge Lighting"],
            "color_grading": ["Geppy Signature (Amber Gold #F59E0B, Cyan #06B6D4 & Obsidian)"],
            "mood_atmosphere": ["Heroic, Confident & Larger-Than-Life", "Whimsical, Playful & Upbeat"],
            "theme": ["Cosmic Galactic & Nebula", "Claymation & Designer Vinyl Collectible"],
            "era": ["2026 Next-Gen Frontier"]
        }
    }

    @classmethod
    def get_extraction_keywords(cls) -> Dict[str, Dict[str, Any]]:
        """Return all supported @prefix extraction style keywords (e.g. @vs, @vis, @q, @mat, @pal, @lit, @id, @fit, @sil, @comp, @vibe, @clay, @flat)."""
        return cls.EXTRACTION_STYLE_KEYWORDS

    @staticmethod
    def compile_prompt(
        reference_text: str,
        modifiers: Dict[str, Any],
        custom_tags: List[str] = [],
        archetype: str = "character",
        primary_image_url: Optional[str] = None,
        gallery_images: List[str] = [],
        variables: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        """Assemble base reference text, archetype directives, blank sizing/fabrication specs, embedded SOTs, option toggles, variable dropdowns, and modifiers."""
        parts = []
        modifiers = modifiers if isinstance(modifiers, dict) else {}
        entity_kind = SOTService.infer_entity_kind(archetype, modifiers)

        # Archetype & Entity Kind directive
        if entity_kind == "contextile_of_truth":
            blank_spec = modifiers.get("blank_spec") if isinstance(modifiers.get("blank_spec"), dict) else {}
            w_in = blank_spec.get("width_in") or modifiers.get("width_in") or 4.0
            h_in = blank_spec.get("height_in") or modifiers.get("height_in") or 4.0
            safe_in = blank_spec.get("safe_margin_in", 0.25)
            shape = blank_spec.get("shape", "rectangle")
            material = blank_spec.get("material", "wood/slate/sublimation blank")
            fab_mode = blank_spec.get("fabrication_mode") or modifiers.get("fabrication_mode") or "laser_bw"
            parts.append(
                f"[📐 CONTEXTILE OF TRUTH (PHYSICAL BLANK & SIZING TEMPLATE) - Functions as BOTH the Unchanging Source of Truth for the physical blank ({material}, {shape} contour) AND the Calibrated Sizing Contextile ({w_in}\" × {h_in}\" physical size, {safe_in}\" safe margin, Fabrication Mode: {fab_mode})]"
            )
            if fab_mode == "laser_bw" or "laser" in str(fab_mode).lower() or blank_spec.get("color_constraint") == "bw_1bit":
                parts.append(
                    "[🔥 LASER ENGRAVER / BURN CONSTRAINT - STRICTLY BLACK AND WHITE ONLY: Pure high-contrast 1-bit monochrome black ink/line-art on pure white background (#000000 = laser burn area, #FFFFFF = unburned blank surface; NO color gradients, NO soft gray background wash)]"
                )
            elif fab_mode == "stencil_bridged" or "stencil" in str(fab_mode).lower() or blank_spec.get("edge_connections"):
                parts.append(
                    "[✂️ STENCIL WITH EDGE CONNECTIONS CONSTRAINT - Bold high-contrast cuttable stencil design where EVERY interior island and enclosed counter-space is structurally connected to the outer frame via sturdy stencil bridges/edge connections so no pieces fall out when laser-cut or knife-cut]"
                )
            elif fab_mode == "vinyl_cut" or "vinyl" in str(fab_mode).lower():
                parts.append(
                    "[🔪 VINYL CUTTER / PLOTTER CONSTRAINT - Crisp solid vector silhouettes with clean weedable minimum 2mm line thickness, united/welded paths, and zero tiny floating fragments]"
                )
            elif fab_mode in ("sublimation", "uv_print") or "sublimation" in str(fab_mode).lower():
                parts.append(
                    f"[🖨️ DYE SUBLIMATION / FULL-COLOR TRANSFER CONSTRAINT - Calibrated to {w_in}\" × {h_in}\" @ 300 DPI with +0.125\" full bleed margin and safe zone inside the {shape} blank contour]"
                )
        elif entity_kind == "sot":
            if archetype == "character":
                parts.append("[🔒 SOURCE OF TRUTH (PERSON / CHARACTER) - Unchanging identity: preserve exact facial likeness, hair, proportions, and signature attire]")
            elif archetype in ("place", "environment"):
                parts.append("[🔒 SOURCE OF TRUTH (SPECIFIC PLACE / LOCATION) - Unchanging location: preserve exact architecture, geography, layout, and spatial landmarks]")
            elif archetype == "brand_asset":
                parts.append("[🔒 SOURCE OF TRUTH (BRAND LOGO / EMBLEM) - Unchanging brand identity: preserve exact logo geometry and color scheme]")
            elif archetype == "prop":
                parts.append("[🔒 SOURCE OF TRUTH (SPECIFIC PROP / OBJECT) - Unchanging item: preserve exact object silhouette, design details, and surface colors]")
            else:
                parts.append("[🔒 SOURCE OF TRUTH ANCHOR - Preserve exact ground-truth identity]")
        else:
            if archetype == "scene_template":
                parts.append("[🎛️ CONTEXTILE SCENE TEMPLATE (PLACE SOT + MOOD/STYLE SETTINGS) - Maintain the embedded Place Source of Truth and genre atmosphere while inserting the selected Character/Subject SOT]")
            elif archetype == "style":
                parts.append("[🎛️ CONTEXTILE STYLE TEMPLATE - Apply these templatized style settings, framing, and enabled specifics onto the target Source of Truth, Blank Contextile of Truth, or uploaded image; sample images are for layout/style reference ONLY, not subject identity]")
            elif archetype == "icon_set":
                parts.append("[🎛️ CONTEXTILE APP ICON TEMPLATE - Cohesive 3D squircle silhouette, beveling, lighting, and icon grammar]")
            elif archetype == "ui_component":
                parts.append("[🎛️ CONTEXTILE UI COMPONENT TEMPLATE - Glassmorphic blur, rounded borders, and UI hierarchy]")
            elif archetype == "output":
                parts.append("[🎛️ CONTEXTILE OUTPUT & FABRICATION TEMPLATE - Physical output rules, laser black & white burn, stencil edge connections, die-cut contours, bleed margins, and 300 DPI layout]")
            else:
                parts.append("[🎛️ CONTEXTILE TEMPLATE - Apply templatized settings to target SOT subject]")

        ref = (reference_text or "").strip()
        if ref:
            parts.append(ref)

        # Embedded SOT items inside a Contextile (e.g., Specific Place SOT or Blank Contextile of Truth)
        embedded_sots = modifiers.get("embedded_sot_handles") or []
        if isinstance(embedded_sots, list) and embedded_sots:
            clean_handles = [f"@{str(h).lstrip('@').strip()}" for h in embedded_sots if str(h).strip()]
            if clean_handles:
                parts.append(f"Embedded Source of Truth Anchor(s): {', '.join(clean_handles)}")

        # Option Toggles / Specifics on a Contextile (e.g., 'Put a funny mustache on the person' or 'Add stencil edge bridges')
        option_toggles = modifiers.get("option_toggles") or []
        if isinstance(option_toggles, list) and option_toggles:
            enabled_Prompts = []
            for tog in option_toggles:
                if isinstance(tog, dict) and tog.get("enabled"):
                    p_snip = (tog.get("prompt") or tog.get("prompt_addition") or tog.get("label") or "").strip()
                    if p_snip:
                        enabled_Prompts.append(p_snip)
            if enabled_Prompts:
                parts.append(f"Active Template Specifics: {'; '.join(enabled_Prompts)}")

        # Variable Dropdowns & Template Slots
        vars_list = variables if isinstance(variables, list) else (modifiers.get("variables") if isinstance(modifiers.get("variables"), list) else [])
        if vars_list:
            dropdown_snips = []
            for v in vars_list:
                if isinstance(v, dict):
                    val = (v.get("value") if v.get("value") is not None else v.get("default_value") or "").strip()
                    lbl = (v.get("label") or v.get("key") or "").strip()
                    if val and lbl:
                        dropdown_snips.append(f"{lbl}: {val}")
            if dropdown_snips:
                parts.append(f"Contextile Variable Selections: {' | '.join(dropdown_snips)}")

        if archetype in ("output", "blank_substrate") or modifiers.get("background_mode") or modifiers.get("print_size") or modifiers.get("blank_spec"):
            bspec = modifiers.get("blank_spec") if isinstance(modifiers.get("blank_spec"), dict) else {}
            bg_mode = bspec.get("fabrication_mode") or modifiers.get("background_mode", "transparent")
            w_in = bspec.get("width_in") or modifiers.get("width_in")
            h_in = bspec.get("height_in") or modifiers.get("height_in")
            psize = f"{w_in}\"x{h_in}\"" if (w_in and h_in) else modifiers.get("print_size", "custom")
            dpi = bspec.get("dpi") or modifiers.get("dpi", 300)
            parts.append(f"Finishing/Blank Output: {bg_mode} | Calibrated Size: {psize} @ {dpi} DPI")

        category_label_map = [
            ("fabrication_mode", "Fabrication & Output Mode"),
            ("style", "Artistic Style"),
            ("theme", "Visual Theme"),
            ("medium", "Render Medium"),
            ("lighting", "Lighting Rig"),
            ("camera_lens", "Camera & Lens"),
            ("materials", "Materials & Textures"),
            ("color_grading", "Color Grading"),
            ("mood_atmosphere", "Mood & Atmosphere"),
            ("era", "Era/Period"),
            ("framing_border", "Framing & Border")
        ]
        for cat_key, cat_title in category_label_map:
            cat_val = modifiers.get(cat_key)
            if cat_val:
                val_str = ", ".join(cat_val) if isinstance(cat_val, list) else str(cat_val)
                if val_str.strip():
                    parts.append(f"{cat_title}: {val_str}")

        custom = modifiers.get("custom") or []
        all_custom = set(custom if isinstance(custom, list) else [custom])
        all_custom.update(custom_tags or [])
        if all_custom:
            parts.append(f"Custom Modifiers: {', '.join([c for c in all_custom if c])}")

        if primary_image_url:
            if entity_kind == "contextile_of_truth":
                parts.append(f"Contextile of Truth Blank Template Photo: {primary_image_url}")
            elif entity_kind == "sot":
                parts.append(f"Unchanging SOT Reference Photo: {primary_image_url}")
            else:
                parts.append(f"Contextile Style Sample Image (Layout/Style Only): {primary_image_url}")
        if gallery_images and len(gallery_images) > 1:
            if entity_kind == "contextile_of_truth":
                parts.append(f"Blank Reference & Sizing Template Gallery: {len(gallery_images)} images (raw blank + calibrated template)")
            elif entity_kind == "sot":
                parts.append(f"SOT Reference Gallery: {len(gallery_images)} ground-truth photos")
            else:
                parts.append(f"Contextile Sample Gallery: {len(gallery_images)} style/layout sample images")

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

    @classmethod
    def _contextile_to_dict(cls, ctx: Any) -> Dict[str, Any]:
        """Normalize a ContextileModel or dict into a rich dictionary, enriching @geppy / @captain-geppy with Geppy's claymation-vinyl profile."""
        if isinstance(ctx, dict):
            d = dict(ctx)
        else:
            d = {
                "id": getattr(ctx, "id", None),
                "name": getattr(ctx, "name", ""),
                "title": getattr(ctx, "title", ""),
                "description": getattr(ctx, "description", ""),
                "archetype": getattr(ctx, "archetype", "character") or "character",
                "entity_kind": cls.infer_entity_kind(getattr(ctx, "archetype", "character"), getattr(ctx, "modifiers", {}), getattr(ctx, "name", "")),
                "reference_type": getattr(ctx, "reference_type", "text"),
                "reference_text": getattr(ctx, "reference_text", "") or "",
                "reference_image_url": getattr(ctx, "reference_image_url", None),
                "primary_image_url": getattr(ctx, "primary_image_url", None),
                "gallery_images": list(getattr(ctx, "gallery_images", None) or []),
                "assembled_prompt": getattr(ctx, "assembled_prompt", "") or "",
                "modifiers": dict(getattr(ctx, "modifiers", None) or {}),
                "variables": list(getattr(ctx, "variables", None) or []),
                "tags": list(getattr(ctx, "tags", None) or [])
            }

        name_low = str(d.get("name") or "").lower()
        if name_low in ("geppy", "captain-geppy", "geppie"):
            prof = cls.GEPPY_BUILTIN_PROFILE
            mods = dict(d.get("modifiers") or {})
            for k, v in prof["modifiers"].items():
                if not mods.get(k):
                    mods[k] = list(v) if isinstance(v, list) else v
                elif k == "style" and isinstance(mods.get(k), list):
                    for st in v:
                        if st not in mods[k]:
                            mods[k].insert(0, st)
                elif k == "materials" and isinstance(mods.get(k), list):
                    for mt in v:
                        if mt not in mods[k]:
                            mods[k].insert(0, mt)
            d["modifiers"] = mods
            if "claymation" not in (d.get("reference_text") or "").lower() and "vinyl" not in (d.get("reference_text") or "").lower():
                d["reference_text"] = prof["reference_text"]
            d["style_summary"] = prof["style_summary"]
            d["materials_summary"] = prof["materials_summary"]
            d["palette_summary"] = prof["palette_summary"]
            d["lighting_summary"] = prof["lighting_summary"]
            d["gear_summary"] = prof["gear_summary"]
            d["color_palette"] = prof["color_palette"]
        return d

    @classmethod
    def _find_target_contextile(cls, candidate: str, db: Optional[Session] = None) -> Optional[Dict[str, Any]]:
        """Resolve a handle candidate (e.g. 'Geppy', 'captain-geppy', '70s-baseball-card') against the DB and built-in Geppy profile."""
        raw = (candidate or "").lstrip("@:").strip()
        if not raw:
            return None
        low = raw.lower()
        norm = re.sub(r"[^a-z0-9]", "", low)

        is_geppy_alias = norm in ("geppy", "geppie", "captgeppy", "captaingeppy")

        if db is not None:
            try:
                exact = db.query(ContextileModel).filter(ContextileModel.name == low).first()
                if exact:
                    return cls._contextile_to_dict(exact)
                if is_geppy_alias:
                    cg = db.query(ContextileModel).filter(ContextileModel.name.in_(["geppy", "captain-geppy"])).first()
                    if cg:
                        d = cls._contextile_to_dict(cg)
                        if low in ("geppy", "geppie"):
                            d["name"] = "geppy"
                        return d
                all_ctxs = db.query(ContextileModel).all()
                for c in all_ctxs:
                    c_norm = re.sub(r"[^a-z0-9]", "", (c.name or "").lower())
                    t_norm = re.sub(r"[^a-z0-9]", "", (c.title or "").lower())
                    if c_norm == norm or (len(norm) >= 3 and (c_norm.startswith(norm) or norm in c_norm or norm in t_norm)):
                        return cls._contextile_to_dict(c)
            except Exception as e:
                print(f"[SOTService._find_target_contextile] DB lookup notice: {e}")

        if is_geppy_alias:
            return cls._contextile_to_dict(cls.GEPPY_BUILTIN_PROFILE)
        return None

    @classmethod
    def parse_mention_token(cls, raw_token: str, db: Optional[Session] = None) -> Optional[Dict[str, Any]]:
        """
        Parse an @mention token into either:
        - An Extraction Style Mention (e.g. @vsGeppy, @visGeppy, @qGeppy, @matGeppy, @palGeppy, @litGeppy, @idGeppy, @fitGeppy, @silGeppy, @compGeppy, @vibeGeppy, @clayGeppy, @flatGeppy, or @vs:geppy / @vs-geppy)
        - Or a full SOT / Contextile Mention (e.g. @geppy, @captain-geppy, @70s-baseball-card).
        """
        token = (raw_token or "").lstrip("@").strip()
        if not token:
            return None

        # Build sorted alias -> canonical key map (longest alias first so 'visual' matches before 'vis' before 'vs')
        alias_pairs = []
        for mode_key, meta in cls.EXTRACTION_STYLE_KEYWORDS.items():
            for al in meta.get("aliases", [mode_key]):
                alias_pairs.append((al.lower(), mode_key))
        alias_pairs.sort(key=lambda x: len(x[0]), reverse=True)

        matched_mode: Optional[str] = None
        target_ctx: Optional[Dict[str, Any]] = None

        # 1. Check explicit delimiter syntax first: @vs:geppy, @vis-geppy, @q_geppy
        delim_match = re.match(r"^([a-zA-Z0-9]+)[:_\-](.+)$", token)
        if delim_match:
            prefix_cand = delim_match.group(1).lower()
            rem_cand = delim_match.group(2).strip()
            for al_str, canon_key in alias_pairs:
                if prefix_cand == al_str:
                    found = cls._find_target_contextile(rem_cand, db)
                    if found:
                        matched_mode = canon_key
                        target_ctx = found
                        break

        # 2. Check camelCase or concatenated extraction prefix: @vsGeppy, @visGeppy, @qGeppy, @palGeppy, @vsgeppy
        if not matched_mode:
            for al_str, canon_key in alias_pairs:
                if len(token) > len(al_str) and token.lower().startswith(al_str):
                    rem = token[len(al_str):].lstrip(":_-")
                    if not rem:
                        continue
                    # Don't accidentally split a plain word unless `rem` resolves to a known SOT/Geppy OR uses CamelCase like @vsGeppy / @qHero
                    found = cls._find_target_contextile(rem, db)
                    if found:
                        matched_mode = canon_key
                        target_ctx = found
                        break
                    elif token[len(al_str)].isupper():
                        # CamelCase extraction on an ad-hoc character/concept name (e.g. @qRobot -> Q-style Robot, or @vsGeppy fallback)
                        matched_mode = canon_key
                        target_ctx = {
                            "name": rem.lower(),
                            "title": rem,
                            "archetype": "character",
                            "entity_kind": "sot",
                            "reference_type": "text",
                            "reference_text": f"{rem} character/subject",
                            "modifiers": dict(cls.GEPPY_BUILTIN_PROFILE["modifiers"]),
                            "style_summary": cls.GEPPY_BUILTIN_PROFILE["style_summary"],
                            "materials_summary": cls.GEPPY_BUILTIN_PROFILE["materials_summary"],
                            "palette_summary": cls.GEPPY_BUILTIN_PROFILE["palette_summary"],
                            "lighting_summary": cls.GEPPY_BUILTIN_PROFILE["lighting_summary"],
                            "gear_summary": cls.GEPPY_BUILTIN_PROFILE["gear_summary"],
                            "color_palette": list(cls.GEPPY_BUILTIN_PROFILE["color_palette"])
                        }
                        break

        # 3. Otherwise check direct full SOT / Contextile handle (@geppy, @captain-geppy, @70s-baseball-card, etc.)
        if not target_ctx:
            exact_full = cls._find_target_contextile(token, db)
            if not exact_full:
                return None
            target_ctx = exact_full
            matched_mode = None

        mods = target_ctx.get("modifiers") if isinstance(target_ctx.get("modifiers"), dict) else {}
        style_list = mods.get("style") or ["Aardman Stop-Motion Sculpted Claymation", "Designer Collectible Vinyl Figure"]
        medium_list = mods.get("medium") or ["8K Octane / Redshift Ray-Traced 3D Render", "ZBrush High-Poly Digital Clay Sculpt"]
        mat_list = mods.get("materials") or ["Soft Vinyl Designer Toy (Bearbrick / Funko)", "Hand-Sculpted Matte Polymer Clay"]
        lit_list = mods.get("lighting") or ["Volumetric Studio Light", "Cyberpunk Neon Rim"]
        pal_list = mods.get("color_grading") or ["Geppy Signature (Amber Gold #F59E0B, Cyan #06B6D4 & Obsidian)"]
        cam_list = mods.get("camera_lens") or ["50mm Standard Eye-Level Heroic Framing"]
        frame_list = mods.get("framing_border") or []
        mood_list = mods.get("mood_atmosphere") or ["Heroic, Confident & Larger-Than-Life"]
        era_list = mods.get("era") or ["2026 Next-Gen Frontier"]
        theme_list = mods.get("theme") or ["Cosmic Galactic & Nebula"]

        style_summary = target_ctx.get("style_summary") or (
            f"Style: {', '.join(style_list)} | Medium: {', '.join(medium_list)} | "
            f"Materials: {', '.join(mat_list)} | Baseline: {target_ctx.get('reference_text', '')[:180]}"
        )
        materials_summary = target_ctx.get("materials_summary") or f"{', '.join(mat_list)} ({', '.join(medium_list)})"
        palette_summary = target_ctx.get("palette_summary") or f"{', '.join(pal_list)}"
        lighting_summary = target_ctx.get("lighting_summary") or f"{', '.join(lit_list)}"
        gear_summary = target_ctx.get("gear_summary") or target_ctx.get("reference_text") or target_ctx.get("title")
        comp_summary = f"Camera: {', '.join(cam_list)}" + (f" | Framing: {', '.join(frame_list)}" if frame_list else "")
        vibe_summary = f"Mood: {', '.join(mood_list)} | Era: {', '.join(era_list)} | Theme: {', '.join(theme_list)}"

        extracted_modifiers: Dict[str, List[str]] = {}
        directive = ""
        extraction_meta = None

        if matched_mode and matched_mode in cls.EXTRACTION_STYLE_KEYWORDS:
            extraction_meta = cls.EXTRACTION_STYLE_KEYWORDS[matched_mode]
            directive = extraction_meta["directive_template"].format(
                raw_tag=f"@{token}",
                handle=target_ctx.get("name", "geppy"),
                title=target_ctx.get("title", "Geppy"),
                style_summary=style_summary,
                materials_summary=materials_summary,
                palette_summary=palette_summary,
                lighting_summary=lighting_summary,
                gear_summary=gear_summary,
                comp_summary=comp_summary,
                vibe_summary=vibe_summary,
                reference_text=target_ctx.get("reference_text", "")
            )
            if matched_mode == "vs":
                extracted_modifiers = {
                    "style": list(style_list),
                    "medium": list(medium_list),
                    "materials": list(mat_list),
                    "lighting": list(lit_list),
                    "color_grading": list(pal_list),
                    "theme": list(theme_list)
                }
            elif matched_mode == "q":
                extracted_modifiers = {
                    "style": ["Q-Style / Chibi 1:2.5 Collectible Designer Vinyl Toy Proportions"] + list(style_list),
                    "medium": list(medium_list),
                    "materials": ["Soft Vinyl Designer Toy (Bearbrick / Funko)"] + [m for m in mat_list if "Vinyl" not in m],
                    "lighting": list(lit_list)
                }
            elif matched_mode == "mat":
                extracted_modifiers = {
                    "materials": list(mat_list),
                    "medium": list(medium_list)
                }
            elif matched_mode == "pal":
                extracted_modifiers = {
                    "color_grading": list(pal_list)
                }
            elif matched_mode == "lit":
                extracted_modifiers = {
                    "lighting": list(lit_list),
                    "mood_atmosphere": list(mood_list)
                }
            elif matched_mode == "comp":
                extracted_modifiers = {
                    "camera_lens": list(cam_list),
                    "framing_border": list(frame_list)
                }
            elif matched_mode == "vibe":
                extracted_modifiers = {
                    "mood_atmosphere": list(mood_list),
                    "era": list(era_list),
                    "theme": list(theme_list)
                }
            elif matched_mode == "sil":
                extracted_modifiers = {
                    "lighting": ["High-Contrast Rim Silhouette Only"],
                    "medium": ["Pure Flat Scalable Vector SVG Artwork"]
                }
            elif matched_mode == "clay":
                extracted_modifiers = {
                    "style": ["Aardman Stop-Motion Sculpted Claymation", "Claymation / Aardman Stop-Motion Puppet"],
                    "medium": ["ZBrush High-Poly Digital Clay Sculpt", "8K Octane / Redshift Ray-Traced 3D Render"],
                    "materials": ["Soft Vinyl Designer Toy (Bearbrick / Funko)", "Hand-Sculpted Matte Polymer Clay with Thumbprint Texture"]
                }
            elif matched_mode == "flat":
                extracted_modifiers = {
                    "style": ["Bauhaus Geometric Modernist Poster", "90s Cel-Shaded Retro Anime (Cowboy Bebop)"],
                    "medium": ["Pure Flat Scalable Vector SVG Artwork", "Glossy Die-Cut Vinyl Sticker with White Rim"]
                }
            elif matched_mode in ("id", "fit"):
                extracted_modifiers = {}
        else:
            extracted_modifiers = {k: list(v) for k, v in mods.items() if isinstance(v, list)}

        return {
            "raw_tag": f"@{token}",
            "token": token,
            "extraction_mode": matched_mode,
            "extraction_meta": extraction_meta,
            "target_handle": target_ctx.get("name"),
            "target_data": target_ctx,
            "directive": directive,
            "extracted_modifiers": extracted_modifiers,
            "style_summary": style_summary,
            "materials_summary": materials_summary,
            "palette_summary": palette_summary,
            "lighting_summary": lighting_summary,
            "color_palette": target_ctx.get("color_palette") or ["#F59E0B (Amber Gold)", "#06B6D4 (Electric Cyan)", "#6366F1 (Cosmic Indigo)", "#0F172A (Obsidian)"]
        }

    @classmethod
    def ai_autofill_contextile(
        cls,
        prompt: str,
        current_archetype: Optional[str] = None,
        app_name: Optional[str] = None,
        db: Optional[Session] = None
    ) -> Dict[str, Any]:
        """Intelligently autofill an entire Contextile (archetype, handle, title, base reference, modifiers, custom notes, creative options) from a seed idea or concept, resolving any @tags or @<prefix><Handle> extraction style tags (e.g. @vsGeppy, @qGeppy)."""
        concept = (prompt or "").strip()
        arch_hint = current_archetype if (current_archetype and current_archetype != "all") else ""

        mention_info = cls.resolve_mentions(concept, db)
        grounding_prompt = mention_info.get("grounding_prompt", "")
        extraction_mentions = mention_info.get("extraction_mentions", [])
        merged_ext_mods = mention_info.get("extracted_modifiers", {})
        clean_subject = re.sub(r"@[a-zA-Z0-9_:\-]+", "", concept).strip()

        system_instruction = """You are Captain Geppy's Master AI Architect & SOT (Source of Truth) Engine Director.
Your task is to take a creator's seed idea, theme, or concept (including any @SOT tags or @<prefix><Handle> Extraction Style tags like @vsGeppy, @visGeppy, @qGeppy, @matGeppy, @palGeppy, @litGeppy) and generate a COMPLETE, production-ready Ground Truth Contextile specification.

You must output valid JSON with these fields:
1. "archetype": one of ["character", "style", "scene_template", "icon_set", "ui_component", "brand_asset", "environment", "prop", "place", "general"]
2. "suggested_handle": clean lowercase kebab-case handle without @ (e.g. "captain-geppy-cyberpunk", "space-fox-clay-vinyl")
3. "recommended_title": punchy, high-impact display title
4. "reference_text": rich, vivid ground-truth subject/style description (2-4 descriptive sentences establishing baseline anatomy, materials, composition, colors, and extracted style)
5. "style": array of 1-2 artistic styles (e.g. ["Aardman Stop-Motion Sculpted Claymation", "Pixar / Disney 3D Feature Animation"])
6. "lighting": array of 1-2 lighting styles (e.g. ["Volumetric God Rays & Atmospheric Rim Glow", "Dual-Tone Neon Cyan & Magenta Edge Lighting"])
7. "theme": array of 1-2 theme styles (e.g. ["Cosmic Galactic & Nebula"])
8. "era": array of 1 era/mood style (e.g. ["Contemporary 2026 Next-Gen Flagship"])
9. "medium": array of 1-2 medium/render styles (e.g. ["Octane Render & Ray-Traced 3D", "ZBrush High-Poly Digital Clay Sculpt"])
10. "materials": array of 1-2 materials (e.g. ["Soft Vinyl Designer Toy (Bearbrick / Funko)", "Frosted Translucent Acrylic & Glass"])
11. "color_grading": array of 1 color palette / grading option
12. "custom_tags": array of 3-5 keywords
13. "custom_modifiers": comma-separated string of 3-5 technical modifiers
14. "creative_options": array of 4-6 creative modifier chips tailored to this concept
15. "rationale": 1-2 sentences explaining why this visual recipe creates unbreakable visual consistency.

CRITICAL RULES:
- Output ONLY valid JSON. Do not include markdown code fences or conversational text.
- If an Extraction Style Tag (such as @vsGeppy / @visGeppy for Visual Style, @qGeppy for Q-Style Chibi Proportions, @matGeppy for Materials, @palGeppy for Color Palette, etc.) is present in the grounding context, STRICTLY obey its extraction directive and populate the matching modifier arrays!"""

        user_content = f"Seed Concept: {concept or 'Next-gen Galactic App Asset'}"
        if clean_subject:
            user_content += f"\nCore Subject (without @tags): {clean_subject}"
        if arch_hint:
            user_content += f"\nPreferred Archetype: {arch_hint}"
        if app_name:
            user_content += f"\nApplication Context: {app_name}"
        if grounding_prompt:
            user_content += f"\n\n{grounding_prompt}"

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
                    for mod_k, mod_vals in merged_ext_mods.items():
                        if mod_vals:
                            existing = data.get(mod_k) if isinstance(data.get(mod_k), list) else []
                            for mv in mod_vals:
                                if mv not in existing:
                                    existing.insert(0, mv)
                            data[mod_k] = existing
                    data["resolved_mentions"] = extraction_mentions
                    return data
            except Exception as e:
                print(f"[SOTService] Parse AI autofill failed: {e}")

        # Intelligent fallbacks based on archetype / concept + any @extraction tags
        low = concept.lower()
        if extraction_mentions:
            ext_first = extraction_mentions[0]
            ext_dir = "; ".join(m.get("directive", "") for m in extraction_mentions if m.get("directive"))
            subj_title = clean_subject.title() if clean_subject else f"{ext_first.get('target_handle', 'Geppy').title()} {ext_first.get('extraction_meta', {}).get('label', 'Style')}"
            slug_base = re.sub(r"[^a-z0-9\-]", "", (clean_subject or f"{ext_first.get('extraction_mode', 'vs')}-{ext_first.get('target_handle', 'geppy')}").lower().replace(" ", "-")).strip("-") or "extracted-style-sot"
            return {
                "archetype": arch_hint or ("character" if clean_subject and not any(k in low for k in ["style", "icon", "ui"]) else "style"),
                "suggested_handle": slug_base[:36],
                "recommended_title": subj_title,
                "reference_text": (
                    f"{subj_title}: Rendered using {', '.join(m['raw_tag'] for m in extraction_mentions)}. "
                    f"{ext_first.get('style_summary', '')}. {ext_dir}"
                ),
                "style": merged_ext_mods.get("style") or ["Aardman Stop-Motion Sculpted Claymation", "Pixar / Disney 3D Feature Animation"],
                "lighting": merged_ext_mods.get("lighting") or ["Volumetric God Rays & Atmospheric Rim Glow", "Dual-Tone Neon Cyan & Magenta Edge Lighting"],
                "theme": merged_ext_mods.get("theme") or ["Cosmic Galactic & Nebula"],
                "era": merged_ext_mods.get("era") or ["Contemporary 2026 Next-Gen Flagship"],
                "medium": merged_ext_mods.get("medium") or ["Octane Render & Ray-Traced 3D", "ZBrush High-Poly Digital Clay Sculpt"],
                "materials": merged_ext_mods.get("materials") or ["Soft Vinyl Designer Toy (Bearbrick / Funko)", "Frosted Translucent Acrylic & Glass"],
                "color_grading": merged_ext_mods.get("color_grading") or ["Geppy Signature (Amber Gold #F59E0B, Cyan #06B6D4 & Obsidian)"],
                "custom_tags": [slug_base, "claymation-vinyl", *[m["raw_tag"].lstrip("@") for m in extraction_mentions]],
                "custom_modifiers": "claymation-sculpted-vinyl, tactile-thumbprint-clay, satin-vinyl-finish, miniature-studio-lighting",
                "creative_options": [
                    "Sculpted polymer clay thumbprint micro-texture",
                    "Smooth satin designer vinyl toy joints",
                    "Q-Style 1:2.5 oversized expressive head",
                    "Translucent glowing cyan acrylic visor",
                    "Warm amber-gold & cyan studio rim light"
                ],
                "rationale": f"Applies {', '.join(m['raw_tag'] for m in extraction_mentions)} extraction rules to lock in Geppy's claymation-ish sculpted designer vinyl visual aesthetic.",
                "resolved_mentions": extraction_mentions
            }
        elif "icon" in low or arch_hint == "icon_set":
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
                "reference_text": "Charismatic galactic captain sculpted in Geppy's claymation-ish designer vinyl style, wearing an obsidian-and-gold flight exosuit with an illuminated cyan visor reflecting distant spiral galaxies.",
                "style": ["Aardman Stop-Motion Sculpted Claymation", "Pixar / Disney 3D Feature Animation"],
                "lighting": ["Cyberpunk Neon Rim", "Volumetric Studio Light"],
                "theme": ["Cosmic Galactic & Nebula", "Cyber-SciFi Holographic"],
                "era": ["2026 Next-Gen Frontier"],
                "medium": ["8K Octane 3D Render", "ZBrush High-Poly Digital Clay Sculpt"],
                "materials": ["Soft Vinyl Designer Toy (Bearbrick / Funko)", "Brushed Titanium Metal"],
                "custom_tags": ["character", "hero-asset", "captain-geppy", "claymation-vinyl"],
                "custom_modifiers": "claymation-vinyl-sculpt, subsurface-scattering, cinematic-lighting, gold-inlays",
                "creative_options": [
                    "Sculpted polymer clay thumbprint texture",
                    "Smooth satin designer vinyl joints",
                    "Illuminated cyan visor telemetry",
                    "Gold-embossed shoulder insignia",
                    "Miniature diorama studio lighting"
                ],
                "rationale": "Claymation-ish sculpted vinyl materials paired with neon rim accents lock in Geppy's unmistakable tactile character aesthetic."
            }

    @classmethod
    def resolve_mentions(cls, text: str, db: Optional[Session] = None) -> Dict[str, Any]:
        """
        Detect @handle mentions AND @<prefix><Handle> Extraction Style mentions (e.g. @vsGeppy, @visGeppy, @qGeppy, @matGeppy, @palGeppy, @litGeppy, @idGeppy, @fitGeppy, @silGeppy, @compGeppy, @vibeGeppy, @clayGeppy, @flatGeppy) in user text,
        fetch SOT Items, Contextiles of Truth (Blanks), and Contextiles (plus any embedded SOTs), and compile grounding context + extracted modifiers.
        """
        if not text or "@" not in text:
            return {
                "has_mentions": False,
                "contextiles": [],
                "extraction_mentions": [],
                "extracted_modifiers": {},
                "grounding_prompt": ""
            }

        # Matches @handle-name or @prefix:handle (alphanumeric, underscore, hyphen, colon)
        raw_tokens = list(dict.fromkeys(re.findall(r"@([a-zA-Z0-9_:\-]+)", text)))
        if not raw_tokens:
            return {
                "has_mentions": False,
                "contextiles": [],
                "extraction_mentions": [],
                "extracted_modifiers": {},
                "grounding_prompt": ""
            }

        matched_contextiles: List[Dict[str, Any]] = []
        extraction_mentions: List[Dict[str, Any]] = []
        combined_extracted_mods: Dict[str, List[str]] = {}
        seen_keys = set()

        for token in raw_tokens:
            parsed = cls.parse_mention_token(token, db)
            if not parsed:
                continue

            t_data = dict(parsed["target_data"])
            ext_mode = parsed["extraction_mode"]
            ext_meta = parsed["extraction_meta"]
            dedup_key = f"{t_data.get('name')}::{ext_mode or 'full'}"
            if dedup_key in seen_keys:
                continue
            seen_keys.add(dedup_key)

            if ext_mode and ext_meta:
                t_data["extraction_mode"] = ext_mode
                t_data["extraction_label"] = ext_meta["label"]
                t_data["extraction_icon"] = ext_meta["icon"]
                t_data["extraction_raw_tag"] = parsed["raw_tag"]
                t_data["extraction_directive"] = parsed["directive"]
                t_data["sot_role"] = ext_meta.get("role_override", "style_only")
                # When extracting visual style/palette/materials/etc. (@vsGeppy, @qGeppy, @matGeppy, @palGeppy), treat as a style/aspect reference rather than locking literal character identity!
                if ext_mode != "id":
                    t_data["entity_kind"] = "contextile"
                extraction_mentions.append({
                    "raw_tag": parsed["raw_tag"],
                    "extraction_mode": ext_mode,
                    "extraction_meta": ext_meta,
                    "target_handle": t_data.get("name"),
                    "target_title": t_data.get("title"),
                    "directive": parsed["directive"],
                    "style_summary": parsed["style_summary"],
                    "extracted_modifiers": parsed["extracted_modifiers"],
                    "color_palette": parsed["color_palette"]
                })

            for mk, mvals in (parsed.get("extracted_modifiers") or {}).items():
                if not isinstance(mvals, list):
                    continue
                if mk not in combined_extracted_mods:
                    combined_extracted_mods[mk] = []
                for mv in mvals:
                    if mv and mv not in combined_extracted_mods[mk]:
                        combined_extracted_mods[mk].append(mv)

            matched_contextiles.append(t_data)

            # If this is a full Contextile template with embedded SOT handles, include those SOTs
            if not ext_mode and db is not None:
                mods = t_data.get("modifiers") if isinstance(t_data.get("modifiers"), dict) else {}
                for emb_h in (mods.get("embedded_sot_handles") or []):
                    clean_emb = str(emb_h).lstrip("@").strip()
                    emb_key = f"{clean_emb}::full"
                    if clean_emb and emb_key not in seen_keys:
                        emb_ctx = db.query(ContextileModel).filter(ContextileModel.name == clean_emb).first()
                        if emb_ctx:
                            matched_contextiles.append(cls._contextile_to_dict(emb_ctx))
                            seen_keys.add(emb_key)

        if not matched_contextiles and not extraction_mentions:
            return {
                "has_mentions": False,
                "contextiles": [],
                "extraction_mentions": [],
                "extracted_modifiers": {},
                "grounding_prompt": ""
            }

        grounding_lines = ["\n### 🛸 SOURCE OF TRUTH (SOT), EXTRACTION STYLE TAGS (@vs / @q / @mat / @pal), CONTEXTILES OF TRUTH (BLANKS) & CONTEXTILE GROUNDING:"]

        if extraction_mentions:
            grounding_lines.append("#### 🎯 ACTIVE ASPECT / STYLE EXTRACTION TAG DIRECTIVES (HIGHEST PRIORITY):")
            for em in extraction_mentions:
                grounding_lines.append(f"- **{em['raw_tag']}** [{em['extraction_meta']['icon']} *{em['extraction_meta']['label']}* from `@{em['target_handle']}`]: {em['directive']}")

        for c in matched_contextiles:
            c_name = c.get("name", "contextile")
            c_title = c.get("title", c_name)
            arch = c.get("archetype") or "general"
            arch_meta = ARCHETYPES.get(arch, ARCHETYPES["general"])
            mods = c.get("modifiers") if isinstance(c.get("modifiers"), dict) else {}
            ext_mode = c.get("extraction_mode")
            entity_kind = c.get("entity_kind") or cls.infer_entity_kind(arch, mods, c_name)

            if ext_mode:
                kind_badge = f"{c.get('extraction_icon', '🎨')} EXTRACTED {c.get('extraction_label', 'STYLE').upper()} ({c.get('extraction_raw_tag')})"
            elif entity_kind == "contextile_of_truth":
                kind_badge = "📐 CONTEXTILE OF TRUTH (PHYSICAL BLANK & SIZING TEMPLATE)"
            elif entity_kind == "sot":
                kind_badge = "🔒 UNCHANGING SOURCE OF TRUTH"
            else:
                kind_badge = "🎛️ CONTEXTILE TEMPLATE"

            grounding_lines.append(f"- **@{c_name}** [{kind_badge} | {arch_meta['icon']} *{arch_meta['label']}* | Title: *{c_title}*]")
            if c.get("extraction_directive"):
                grounding_lines.append(f"  - **Extraction Mode Rule**: {c['extraction_directive']}")
            elif c.get("reference_text"):
                if entity_kind == "contextile_of_truth":
                    lbl_ref = "Physical Blank & Sizing Template Specification"
                elif entity_kind == "sot":
                    lbl_ref = "Ground-Truth Identity/Place"
                else:
                    lbl_ref = "Template Settings & Style Baseline"
                grounding_lines.append(f"  - **{lbl_ref}**: {c['reference_text']}")

            blank_spec = mods.get("blank_spec") if isinstance(mods.get("blank_spec"), dict) else {}
            if (entity_kind == "contextile_of_truth" or blank_spec) and not ext_mode:
                w_in = blank_spec.get("width_in") or mods.get("width_in") or 4.0
                h_in = blank_spec.get("height_in") or mods.get("height_in") or 4.0
                safe_in = blank_spec.get("safe_margin_in", 0.25)
                shape = blank_spec.get("shape", "rectangle")
                material = blank_spec.get("material", "wood/slate/sublimation substrate")
                fab_mode = blank_spec.get("fabrication_mode") or mods.get("fabrication_mode") or "laser_bw"
                grounding_lines.append(
                    f"  - **📐 Calibrated Blank Dimensions & Substrate**: {w_in}\" W × {h_in}\" H (Safe Zone Margin: {safe_in}\") | Contour Shape: {shape} | Blank Material: {material} | Default Fabrication Mode: {fab_mode}"
                )
                if fab_mode == "laser_bw" or blank_spec.get("color_constraint") == "bw_1bit":
                    grounding_lines.append(
                        "  - **🔥 Laser Engraver Burn Constraint**: This blank is burned on a laser engraver — output MUST be pure high-contrast 1-bit BLACK AND WHITE ONLY (#000000 = laser burn, #FFFFFF = unburned blank). No color gradients."
                    )
                elif fab_mode == "stencil_bridged" or blank_spec.get("edge_connections"):
                    grounding_lines.append(
                        "  - **✂️ Stencil Edge Connections Constraint**: Output MUST be a cuttable stencil with sturdy structural bridges/edge connections tying every inner island to the outer frame so no pieces drop out when cut."
                    )

            emb_handles = mods.get("embedded_sot_handles") or []
            if emb_handles and not ext_mode:
                grounding_lines.append(f"  - **🔒 Embedded Source of Truth Inside This Contextile**: {', '.join(['@' + str(h).lstrip('@') for h in emb_handles])}")

            opt_toggles = mods.get("option_toggles") or []
            if opt_toggles and not ext_mode:
                active_opts = [f"{t.get('label')} ({t.get('prompt', '')})" for t in opt_toggles if isinstance(t, dict) and t.get("enabled")]
                inactive_opts = [f"{t.get('label')}" for t in opt_toggles if isinstance(t, dict) and not t.get("enabled")]
                if active_opts:
                    grounding_lines.append(f"  - **✅ Enabled Contextile Specifics**: {'; '.join(active_opts)}")
                if inactive_opts:
                    grounding_lines.append(f"  - **⬜ Disabled Contextile Specifics (Do NOT include unless asked)**: {'; '.join(inactive_opts)}")

            primary = c.get("primary_image_url") or c.get("reference_image_url")
            if primary:
                if ext_mode and ext_mode != "id":
                    grounding_lines.append(f"  - **🎨 Extracted Style Reference Image ({c.get('extraction_raw_tag')} — Match Extracted {c.get('extraction_label')} ONLY, Do NOT copy character identity)**: {primary}")
                elif entity_kind == "contextile_of_truth":
                    grounding_lines.append(f"  - **📐 Contextile of Truth Blank Template Photo (Lock Physical Blank Shape & Safe Zone)**: {primary}")
                elif entity_kind == "sot":
                    grounding_lines.append(f"  - **⭐ Unchanging SOT Reference Photo (Lock Identity/Place)**: {primary}")
                else:
                    grounding_lines.append(f"  - **🖼️ Contextile Sample Image (Match Layout/Vibe ONLY — Do NOT copy person/subject identity from sample)**: {primary}")

            gallery = c.get("gallery_images") or []
            additional = [img for img in gallery if img != primary]
            if additional:
                lbl = "Raw Blank & Sizing Gallery" if entity_kind == "contextile_of_truth" else ("Additional SOT Photos" if entity_kind == "sot" else "Additional Template Sample Images")
                grounding_lines.append(f"  - **🖼️ {lbl} ({len(additional)} items)**: {', '.join(additional)}")

            if not ext_mode:
                if entity_kind == "contextile_of_truth":
                    grounding_lines.append("  - **Contextile of Truth (Blank Substrate) Directive**: Treat this item as BOTH the unchanging Source of Truth for the physical blank substrate AND the sizing/boundary Contextile.")
                elif entity_kind == "sot":
                    if arch == "character":
                        grounding_lines.append("  - **SOT Person/Character Directive**: This is an UNCHANGING Source of Truth person/character. Preserve their exact facial structure, hair, proportions, and signature attire across any Contextile template or scene.")
                    elif arch in ("place", "environment"):
                        grounding_lines.append("  - **SOT Place/Location Directive**: This is an UNCHANGING Source of Truth specific place. Preserve its exact architecture, layout, and landmarks.")
                    elif arch == "brand_asset":
                        grounding_lines.append("  - **SOT Brand Directive**: Strictly preserve brand geometry, color balance, and typography.")
                    elif arch == "prop":
                        grounding_lines.append("  - **SOT Prop Directive**: Strictly preserve the exact object geometry, colors, and details.")

            if c.get("assembled_prompt") and not ext_mode:
                grounding_lines.append(f"  - **Compiled Prompt**: {c['assembled_prompt']}")

        grounding_prompt = "\n".join(grounding_lines) + "\n"

        return {
            "has_mentions": True,
            "contextiles": matched_contextiles,
            "extraction_mentions": extraction_mentions,
            "extracted_modifiers": combined_extracted_mods,
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
        """Create and persist a new SOT Item, Contextile of Truth (Blank), or Contextile Template with multi-image gallery, blank_spec, embedded SOTs, and option toggles."""
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
        modifiers = dict(data.get("modifiers") or {})
        # Persist explicit entity_kind ('sot', 'contextile_of_truth', 'contextile'), blank_spec, embedded_sot_handles, SOT variant metadata, and option_toggles inside modifiers
        entity_kind = data.get("entity_kind") or modifiers.get("entity_kind") or SOTService.infer_entity_kind(archetype, modifiers, name)
        modifiers["entity_kind"] = entity_kind
        if entity_kind == "contextile_of_truth" and archetype not in ("blank_substrate",):
            archetype = "blank_substrate"
        if isinstance(data.get("blank_spec"), dict):
            modifiers["blank_spec"] = data["blank_spec"]
        if "embedded_sot_handles" in data and isinstance(data["embedded_sot_handles"], list):
            modifiers["embedded_sot_handles"] = [str(h).lstrip("@").strip() for h in data["embedded_sot_handles"] if str(h).strip()]
        if "option_toggles" in data and isinstance(data["option_toggles"], list):
            modifiers["option_toggles"] = data["option_toggles"]
        if data.get("parent_sot_handle") or modifiers.get("parent_sot_handle"):
            parent_h = str(data.get("parent_sot_handle") or modifiers.get("parent_sot_handle")).lstrip("@").strip().lower()
            if parent_h and parent_h != name:
                modifiers["parent_sot_handle"] = parent_h
                modifiers["is_sot_variant"] = True
                if data.get("variant_label") or modifiers.get("variant_label"):
                    modifiers["variant_label"] = str(data.get("variant_label") or modifiers.get("variant_label")).strip()
                if data.get("parent_sot_title") or modifiers.get("parent_sot_title"):
                    modifiers["parent_sot_title"] = str(data.get("parent_sot_title") or modifiers.get("parent_sot_title")).strip()

        tags = data.get("tags", [])
        variables = list(data.get("variables") or [])
        assembled = data.get("assembled_prompt") or SOTService.compile_prompt(
            ref_text, modifiers, tags, archetype, primary_image_url, gallery_images, variables=variables
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
    def _resolve_local_image_path(cls, image_url: Optional[str]) -> Optional[str]:
        """Resolve a /sot-refs/... or /api/sot/reference-file/... URL to an existing local filesystem path."""
        if not image_url:
            return None
        ref_dir = cls._get_references_dir()
        clean = str(image_url).split("?")[0].strip()
        for prefix in ("/sot-refs/", "/api/sot/reference-file/"):
            if clean.startswith(prefix):
                fname = clean[len(prefix):]
                cand = os.path.join(ref_dir, fname)
                if os.path.exists(cand):
                    return cand
        if os.path.exists(clean):
            return clean
        return None

    @classmethod
    def render_blank_sizing_template_image(
        cls,
        handle: str,
        title: str,
        raw_blank_url: Optional[str],
        blank_spec: Dict[str, Any]
    ) -> Dict[str, str]:
        """
        Given a raw photo of a physical blank (or synthesizing one if none was uploaded yet),
        generate a calibrated Sizing & Safe-Zone Template overlay image (`template_<handle>.png`).
        Returns {"template_url": ..., "raw_blank_url": ...}.
        """
        ref_dir = cls._get_references_dir()
        width_in = float(blank_spec.get("width_in") or 4.0)
        height_in = float(blank_spec.get("height_in") or 4.0)
        safe_margin_in = float(blank_spec.get("safe_margin_in") or 0.25)
        shape = str(blank_spec.get("shape") or "rounded_rect").lower()
        material = str(blank_spec.get("material") or "natural_wood").lower()
        fab_mode = str(blank_spec.get("fabrication_mode") or "laser_bw").lower()

        raw_path = cls._resolve_local_image_path(raw_blank_url)
        raw_img = None
        if raw_path and os.path.exists(raw_path):
            try:
                raw_img = Image.open(raw_path).convert("RGBA")
            except Exception as e:
                print(f"[render_blank_sizing_template_image] Could not open raw blank {raw_path}: {e}")

        # If no uploaded blank image exists yet, synthesize a realistic physical blank substrate image
        if raw_img is None:
            aspect = max(0.4, min(2.4, width_in / max(0.1, height_in)))
            if aspect >= 1.0:
                rw, rh = 800, max(420, int(800 / aspect))
            else:
                rh, rw = 800, max(420, int(800 * aspect))
            raw_img = Image.new("RGBA", (rw, rh), (18, 24, 38, 255))
            rdraw = ImageDraw.Draw(raw_img)
            pad_x, pad_y = int(rw * 0.09), int(rh * 0.09)
            bx0, by0, bx1, by1 = pad_x, pad_y, rw - pad_x, rh - pad_y

            if "slate" in material or "stone" in material:
                base_col = (44, 50, 58, 255)
                rim_col = (75, 85, 99, 255)
            elif "ceramic" in material or "mug" in material or "sublimation" in material or "white" in material:
                base_col = (245, 247, 250, 255)
                rim_col = (203, 213, 225, 255)
            elif "metal" in material or "steel" in material or "aluminum" in material:
                base_col = (180, 190, 202, 255)
                rim_col = (226, 232, 240, 255)
            else:
                # Natural basswood / maple laser blank
                base_col = (218, 182, 132, 255)
                rim_col = (161, 114, 67, 255)

            if shape in ("circle", "round", "coaster_round"):
                rdraw.ellipse([bx0, by0, bx1, by1], fill=base_col, outline=rim_col, width=8)
            else:
                rad = 36 if "round" in shape else 14
                rdraw.rounded_rectangle([bx0, by0, bx1, by1], radius=rad, fill=base_col, outline=rim_col, width=8)

            # Subtle woodgrain or slate texture lines on the blank
            if "wood" in material or "plaque" in handle or "wood" in handle:
                for gy in range(by0 + 14, by1 - 14, 16):
                    grain_alpha = 26 if (gy // 16) % 2 == 0 else 14
                    rdraw.line([(bx0 + 18, gy), (bx1 - 18, gy)], fill=(120, 75, 35, grain_alpha), width=2)

            raw_fname = f"blank_raw_{handle}.png"
            raw_save_path = os.path.join(ref_dir, raw_fname)
            raw_img.save(raw_save_path, "PNG")
            raw_blank_url = f"/sot-refs/{raw_fname}"

        # Now build the Calibrated Sizing & Output Template Image (880 x 880 studio blueprint frame around the blank)
        canvas_w, canvas_h = 880, 880
        canvas = Image.new("RGBA", (canvas_w, canvas_h), (11, 17, 30, 255))
        draw = ImageDraw.Draw(canvas)

        # Blueprint engineering grid background
        for gx in range(0, canvas_w, 40):
            draw.line([(gx, 0), (gx, canvas_h)], fill=(30, 41, 59, 140), width=1)
        for gy in range(0, canvas_h, 40):
            draw.line([(0, gy), (canvas_w, gy)], fill=(30, 41, 59, 140), width=1)

        # Fit the raw blank photo into the central calibration stage (max 600x560)
        stage_x0, stage_y0, stage_x1, stage_y1 = 130, 130, 750, 690
        max_bw = stage_x1 - stage_x0
        max_bh = stage_y1 - stage_y0
        rw, rh = raw_img.size
        scale = min(max_bw / max(1, rw), max_bh / max(1, rh))
        disp_w = max(120, int(rw * scale))
        disp_h = max(120, int(rh * scale))
        bx0 = stage_x0 + (max_bw - disp_w) // 2
        by0 = stage_y0 + (max_bh - disp_h) // 2
        bx1 = bx0 + disp_w
        by1 = by0 + disp_h

        resized_blank = raw_img.resize((disp_w, disp_h), Image.Resampling.LANCZOS)
        canvas.alpha_composite(resized_blank, (bx0, by0))

        # Outer physical blank boundary frame (Cyan #06B6D4)
        cyan = (6, 182, 212, 255)
        amber = (245, 158, 11, 255)
        emerald = (16, 185, 129, 255)

        if shape in ("circle", "round", "coaster_round"):
            draw.ellipse([bx0, by0, bx1, by1], outline=cyan, width=3)
        else:
            draw.rounded_rectangle([bx0, by0, bx1, by1], radius=18, outline=cyan, width=3)

        # Safe Print / Laser Burn Zone inset boundary (Amber #F59E0B dashed guide)
        margin_ratio_x = min(0.28, max(0.05, safe_margin_in / max(0.5, width_in)))
        margin_ratio_y = min(0.28, max(0.05, safe_margin_in / max(0.5, height_in)))
        inset_x = int(disp_w * margin_ratio_x)
        inset_y = int(disp_h * margin_ratio_y)
        sx0, sy0, sx1, sy1 = bx0 + inset_x, by0 + inset_y, bx1 - inset_x, by1 - inset_y

        if shape in ("circle", "round", "coaster_round"):
            draw.ellipse([sx0, sy0, sx1, sy1], outline=amber, width=3)
        else:
            # Draw dashed safe zone rectangle
            dash_len = 14
            for x in range(sx0, sx1, dash_len * 2):
                draw.line([(x, sy0), (min(x + dash_len, sx1), sy0)], fill=amber, width=3)
                draw.line([(x, sy1), (min(x + dash_len, sx1), sy1)], fill=amber, width=3)
            for y in range(sy0, sy1, dash_len * 2):
                draw.line([(sx0, y), (sx0, min(y + dash_len, sy1))], fill=amber, width=3)
                draw.line([(sx1, y), (sx1, min(y + dash_len, sy1))], fill=amber, width=3)

        # Center alignment crosshairs
        cx, cy = (bx0 + bx1) // 2, (by0 + by1) // 2
        draw.line([(cx - 24, cy), (cx + 24, cy)], fill=(255, 255, 255, 190), width=2)
        draw.line([(cx, cy - 24), (cx, cy + 24)], fill=(255, 255, 255, 190), width=2)
        draw.ellipse([cx - 6, cy - 6, cx + 6, cy + 6], outline=cyan, width=2)

        font_def = ImageFont.load_default()

        # Top Dimension Ruler (Width in inches)
        ruler_y = by0 - 28
        draw.line([(bx0, ruler_y), (bx1, ruler_y)], fill=cyan, width=2)
        draw.line([(bx0, ruler_y - 8), (bx0, ruler_y + 8)], fill=cyan, width=2)
        draw.line([(bx1, ruler_y - 8), (bx1, ruler_y + 8)], fill=cyan, width=2)
        w_label = f"WIDTH: {width_in:.2f}\" ({int(width_in * 300)}px @ 300 DPI)"
        wb = draw.textbbox((0, 0), w_label, font=font_def)
        tw = wb[2] - wb[0]
        draw.rounded_rectangle([cx - tw // 2 - 10, ruler_y - 12, cx + tw // 2 + 10, ruler_y + 12], radius=6, fill=(15, 23, 42, 245), outline=cyan, width=1)
        draw.text((cx - tw // 2, ruler_y - 6), w_label, fill=(255, 255, 255, 255), font=font_def)

        # Right Dimension Ruler (Height in inches)
        ruler_x = bx1 + 28
        draw.line([(ruler_x, by0), (ruler_x, by1)], fill=cyan, width=2)
        draw.line([(ruler_x - 8, by0), (ruler_x + 8, by0)], fill=cyan, width=2)
        draw.line([(ruler_x - 8, by1), (ruler_x + 8, by1)], fill=cyan, width=2)
        h_label = f"H: {height_in:.2f}\""
        hb = draw.textbbox((0, 0), h_label, font=font_def)
        hw = hb[2] - hb[0]
        draw.rounded_rectangle([ruler_x - hw // 2 - 8, cy - 12, ruler_x + hw // 2 + 8, cy + 12], radius=6, fill=(15, 23, 42, 245), outline=cyan, width=1)
        draw.text((ruler_x - hw // 2, cy - 6), h_label, fill=(255, 255, 255, 255), font=font_def)

        # Safe Zone Label Pill inside top of safe area
        safe_w = max(0.5, width_in - 2 * safe_margin_in)
        safe_h = max(0.5, height_in - 2 * safe_margin_in)
        sz_text = f"SAFE OUTPUT ZONE: {safe_w:.2f}\" x {safe_h:.2f}\" (-{safe_margin_in:.2f}\" margin)"
        szb = draw.textbbox((0, 0), sz_text, font=font_def)
        szw = szb[2] - szb[0]
        draw.rounded_rectangle([cx - szw // 2 - 10, sy0 + 8, cx + szw // 2 + 10, sy0 + 30], radius=6, fill=(15, 23, 42, 230), outline=amber, width=1)
        draw.text((cx - szw // 2, sy0 + 13), sz_text, fill=amber, font=font_def)

        # Top Header Banner: CONTEXTILE OF TRUTH
        draw.rounded_rectangle([40, 24, canvas_w - 40, 82], radius=12, fill=(15, 23, 42, 245), outline=emerald, width=2)
        hdr_top = f"CONTEXTILE OF TRUTH  |  @{handle}  |  {title.upper()[:38]}"
        draw.text((62, 36), hdr_top, fill=(255, 255, 255, 255), font=font_def)
        hdr_sub = f"Physical Blank SOT + Calibrated Sizing Template  •  Shape: {shape.upper()}  •  Material: {material.upper()}"
        draw.text((62, 56), hdr_sub, fill=emerald, font=font_def)

        # Bottom Fabrication Spec Callout Bar
        if "laser" in fab_mode:
            fab_badge_text = "FABRICATION RULE: LASER ENGRAVER 1-BIT BLACK & WHITE BURN ONLY (BLACK = BURN, WHITE = UNBURNED BLANK)"
            fab_col = (245, 158, 11, 255)
        elif "stencil" in fab_mode:
            fab_badge_text = "FABRICATION RULE: CUT STENCIL WITH EDGE CONNECTIONS (STRUCTURAL BRIDGES HOLD ALL INNER ISLANDS)"
            fab_col = (236, 72, 153, 255)
        elif "vinyl" in fab_mode:
            fab_badge_text = "FABRICATION RULE: VINYL CUTTER PLOTTER VECTOR PATHS (WEED-READY SOLID SHAPES & BRIDGES)"
            fab_col = (6, 182, 212, 255)
        else:
            fab_badge_text = f"FABRICATION RULE: FULL-COLOR DYE SUBLIMATION / UV TRANSFER ({width_in:.2f}\"x{height_in:.2f}\" @ 300 DPI + BLEED)"
            fab_col = (56, 189, 248, 255)

        draw.rounded_rectangle([40, canvas_h - 110, canvas_w - 40, canvas_h - 30], radius=12, fill=(15, 23, 42, 245), outline=fab_col, width=2)
        draw.text((62, canvas_h - 94), fab_badge_text[:96], fill=fab_col, font=font_def)
        spec_line2 = f"Calibrated Blank Size: {width_in:.2f}\" W x {height_in:.2f}\" H  |  Safe Zone: {safe_w:.2f}\" x {safe_h:.2f}\"  |  Resolution: {int(width_in * 300)}x{int(height_in * 300)}px (300 DPI)"
        draw.text((62, canvas_h - 66), spec_line2[:100], fill=(226, 232, 240, 255), font=font_def)

        tpl_fname = f"template_{handle}.png"
        tpl_path = os.path.join(ref_dir, tpl_fname)
        canvas.save(tpl_path, "PNG")
        return {
            "template_url": f"/sot-refs/{tpl_fname}",
            "raw_blank_url": raw_blank_url or f"/sot-refs/{tpl_fname}"
        }

    @classmethod
    def analyze_blank_image_and_build_template(
        cls,
        image_url: Optional[str] = None,
        concept: str = "",
        width_in: Optional[float] = None,
        height_in: Optional[float] = None,
        safe_margin_in: Optional[float] = None,
        shape: Optional[str] = None,
        material: Optional[str] = None,
        fabrication_mode: Optional[str] = None,
        save_immediately: bool = False,
        db: Optional[Session] = None,
        handle_override: Optional[str] = None,
        unit: str = "in",
        color_mode: Optional[str] = None,
        safe_margin_pct: Optional[float] = None,
        requires_edge_bridges: Optional[bool] = None,
        paired_contextile_handles: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Analyze an uploaded physical blank photo (wood plaque, slate coaster, tumbler, mug, ornament, acrylic blank, etc.)
        to detect its physical dimensions, contour shape, substrate material, and what can be output on it
        (e.g., Laser Engraver 1-bit B&W burn, Stencil with Edge Connections, Vinyl Cutter, or Sublimation).
        Generates a calibrated sizing template image and returns/saves a 'Contextile of Truth' (`entity_kind = 'contextile_of_truth'`).
        """
        seed = (concept or "").strip()
        low = seed.lower()

        # Inspect uploaded image dimensions / aspect ratio if present
        local_path = cls._resolve_local_image_path(image_url)
        img_aspect = 1.0
        img_px_w, img_px_h = 800, 800
        if local_path and os.path.exists(local_path):
            try:
                with Image.open(local_path) as im:
                    img_px_w, img_px_h = im.size
                    img_aspect = round(img_px_w / max(1, img_px_h), 3)
            except Exception as e:
                print(f"[analyze_blank_image_and_build_template] Image open error: {e}")

        # Ask Gemini (with vision if image is available) to analyze the blank when explicit dimensions/handle aren't all pre-supplied
        ai_spec = None
        if not (handle_override and width_in is not None and height_in is not None and shape and material and fabrication_mode):
            try:
                sys_inst = """You are Captain Geppy's Physical Blank & Fabrication Engineer.
The user is uploading/describing a physical blank item (e.g., wood plaque, slate coaster, sublimation mug/tumbler, metal tag, acrylic ornament, stencil sheet) to create a 'Contextile of Truth' (which acts as BOTH the Source of Truth for the blank AND its calibrated sizing/output Contextile).

Respond STRICTLY with valid JSON:
{
  "suggested_handle": "kebab-case-blank-handle",
  "recommended_title": "Display Title for Blank Contextile of Truth",
  "description": "1-2 sentence overview of this physical blank, its dimensions, and what can be fabricated on it.",
  "reference_text": "Detailed description of the physical blank surface, contour shape, printable/burnable safe area, and output rules.",
  "width_in": 4.0,
  "height_in": 4.0,
  "safe_margin_in": 0.25,
  "shape": "rounded_rect" | "circle" | "rectangle" | "mug_wrap" | "arch_plaque" | "custom_contour",
  "material": "natural_wood" | "black_slate" | "white_sublimation_ceramic" | "brushed_metal" | "clear_acrylic" | "mylar_stencil_sheet",
  "fabrication_mode": "laser_bw" | "stencil_bridged" | "vinyl_cut" | "sublimation" | "uv_print",
  "color_constraint": "bw_1bit" | "monochrome_bridges" | "solid_spot_layers" | "full_color_cmyk",
  "edge_connections": true | false,
  "compatible_contextiles": ["@laser-engrave-bw-burn", "@stencil-edge-connections", "@sublimation-full-bleed"]
}"""
                user_parts: List[Dict[str, Any]] = [
                    {"text": f"User Blank Description: {seed or 'Physical Blank Substrate'}\nUploaded Image Pixel Aspect Ratio: {img_aspect} ({img_px_w}x{img_px_h})"}
                ]
                if local_path and os.path.exists(local_path):
                    import base64
                    with open(local_path, "rb") as bf:
                        b64 = base64.b64encode(bf.read()).decode("utf-8")
                    ext = os.path.splitext(local_path)[1].lower()
                    mime = "image/jpeg" if ext in (".jpg", ".jpeg") else ("image/webp" if ext == ".webp" else "image/png")
                    user_parts.append({"inline_data": {"mime_type": mime, "data": b64}})

                raw = call_gemini([{"role": "user", "parts": user_parts}], sys_inst)
                if raw:
                    clean = raw.strip()
                    if clean.startswith("```json"): clean = clean[7:]
                    elif clean.startswith("```"): clean = clean[3:]
                    if clean.endswith("```"): clean = clean[:-3]
                    ai_spec = json.loads(clean.strip())
            except Exception as e:
                print(f"[analyze_blank_image_and_build_template] Gemini vision fallback: {e}")

        # Deduce deterministic defaults merged with AI spec and explicit user overrides
        if not ai_spec or not isinstance(ai_spec, dict):
            if "coaster" in low or "slate" in low or "round" in low or "circle" in low:
                ai_spec = {
                    "suggested_handle": "slate-coaster-blank",
                    "recommended_title": "4\" Round Slate Coaster Blank (Contextile of Truth)",
                    "description": "4.0\" × 4.0\" chiseled dark slate coaster blank calibrated for 1-bit black & white laser engraving or bridged stencil etching.",
                    "reference_text": "Physical Blank Contextile of Truth: 4.0 inch diameter round natural black riven slate coaster with chiseled stone edge, 3.5 inch centered circular safe laser burn zone (0.25 inch margin). Supports high-contrast 1-bit black & white laser engraving or bridged stencil etching.",
                    "width_in": 4.0,
                    "height_in": 4.0,
                    "safe_margin_in": 0.25,
                    "shape": "circle" if ("round" in low or "circle" in low) else "rounded_rect",
                    "material": "black_slate",
                    "fabrication_mode": "laser_bw",
                    "color_constraint": "bw_1bit",
                    "edge_connections": False
                }
            elif "stencil" in low or "mylar" in low:
                ai_spec = {
                    "suggested_handle": "mylar-stencil-blank-6x6",
                    "recommended_title": "6\"×6\" Mylar Stencil Blank (Contextile of Truth)",
                    "description": "6.0\" × 6.0\" translucent 10mil Mylar stencil blank requiring structural edge connections/bridges for all interior islands.",
                    "reference_text": "Physical Blank Contextile of Truth: 6.0 x 6.0 inch square 10mil Mylar laser/craft cutter stencil blank with 0.375 inch outer frame margin (5.25 x 5.25 inch safe cut zone). Requires bold stencil cutout shapes with connected edge bridges so interior islands never drop out.",
                    "width_in": 6.0,
                    "height_in": 6.0,
                    "safe_margin_in": 0.375,
                    "shape": "rectangle",
                    "material": "mylar_stencil_sheet",
                    "fabrication_mode": "stencil_bridged",
                    "color_constraint": "bw_1bit",
                    "edge_connections": True
                }
            elif "mug" in low or "tumbler" in low or "sublimat" in low:
                ai_spec = {
                    "suggested_handle": "sublimation-tumbler-blank",
                    "recommended_title": "20oz Sublimation Tumbler / Mug Wrap Blank (Contextile of Truth)",
                    "description": "9.3\" × 8.2\" full-bleed white polymer-coated sublimation blank calibrated for 300 DPI vibrant dye-sublimation transfer.",
                    "reference_text": "Physical Blank Contextile of Truth: 9.3 inch wide by 8.2 inch high polymer-coated white sublimation wrap blank with 0.25 inch safe margin and +0.125 inch full bleed extension at 300 DPI.",
                    "width_in": 9.3,
                    "height_in": 8.2,
                    "safe_margin_in": 0.25,
                    "shape": "rectangle",
                    "material": "white_sublimation_ceramic",
                    "fabrication_mode": "sublimation",
                    "color_constraint": "full_color_cmyk",
                    "edge_connections": False
                }
            else:
                # Default to Wood Plaque Laser / Stencil Blank calibrated to uploaded image aspect ratio
                est_w = round(6.0 * img_aspect, 1) if img_aspect >= 1.0 else 5.0
                est_h = 6.0 if img_aspect >= 1.0 else round(5.0 / max(0.3, img_aspect), 1)
                est_w = max(2.5, min(12.0, est_w))
                est_h = max(2.5, min(12.0, est_h))
                slug_base = re.sub(r"[^a-z0-9\-]", "", seed.lower().replace(" ", "-")) if seed else "wood-plaque-blank"
                if not slug_base.endswith("blank"):
                    slug_base = f"{slug_base}-blank".strip("-")
                ai_spec = {
                    "suggested_handle": slug_base[:36],
                    "recommended_title": f"{seed.title() if seed else 'Natural Basswood Plaque'} ({est_w}\"×{est_h}\" Contextile of Truth)",
                    "description": f"Calibrated {est_w}\" × {est_h}\" physical blank Contextile of Truth for laser engraving (1-bit black & white burn), bridged stencil cutting, or sublimation.",
                    "reference_text": f"Physical Blank Contextile of Truth: {est_w}\" W × {est_h}\" H natural basswood/substrate blank with 0.25\" safe margin. Functions as both the Source of Truth for the physical blank and its sizing/output Contextile.",
                    "width_in": est_w,
                    "height_in": est_h,
                    "safe_margin_in": 0.25,
                    "shape": "rounded_rect",
                    "material": "natural_wood",
                    "fabrication_mode": "laser_bw",
                    "color_constraint": "bw_1bit",
                    "edge_connections": False
                }

        final_w = float(width_in if width_in is not None else (ai_spec.get("width_in") or 4.0))
        final_h = float(height_in if height_in is not None else (ai_spec.get("height_in") or 4.0))
        final_safe = float(safe_margin_in if safe_margin_in is not None else (ai_spec.get("safe_margin_in") or 0.25))
        final_shape = str(shape or ai_spec.get("shape") or "rounded_rect").strip()
        final_mat = str(material or ai_spec.get("material") or "natural_wood").strip()
        final_fab = str(fabrication_mode or ai_spec.get("fabrication_mode") or "laser_bw").strip()

        is_laser = "laser" in final_fab.lower() or final_fab == "laser_bw"
        is_stencil = "stencil" in final_fab.lower() or final_fab == "stencil_bridged"
        is_vinyl = "vinyl" in final_fab.lower() or final_fab == "vinyl_cut"

        fab_dropdown_default = EXTENSIVE_VARIABLE_DROPDOWNS["fabrication_mode"]["options"][0]
        if is_stencil:
            fab_dropdown_default = EXTENSIVE_VARIABLE_DROPDOWNS["fabrication_mode"]["options"][3]
        elif is_vinyl:
            fab_dropdown_default = EXTENSIVE_VARIABLE_DROPDOWNS["fabrication_mode"]["options"][5]
        elif not is_laser:
            fab_dropdown_default = EXTENSIVE_VARIABLE_DROPDOWNS["fabrication_mode"]["options"][7]

        final_color_mode = color_mode or ("1bit_bw" if (is_laser or is_stencil) else ("spot_vector" if is_vinyl else "full_color"))
        final_margin_pct = float(safe_margin_pct) if safe_margin_pct is not None else round((final_safe / max(0.5, min(final_w, final_h))) * 100.0, 1)
        final_edge_bridges = bool(requires_edge_bridges) if requires_edge_bridges is not None else bool(is_stencil or is_vinyl or ai_spec.get("edge_connections"))
        default_paired = ["stencil-edge-connections"] if final_edge_bridges else (["laser-engrave-bw-burn"] if is_laser else [])
        final_paired_handles = [str(h).lstrip("@").strip() for h in (paired_contextile_handles if paired_contextile_handles is not None else default_paired) if str(h).strip()]

        blank_spec = {
            "width_in": final_w,
            "height_in": final_h,
            "width_value": final_w,
            "height_value": final_h,
            "unit": unit or "in",
            "safe_margin_in": final_safe,
            "safe_margin_pct": final_margin_pct,
            "safe_width_in": round(max(0.5, final_w - 2 * final_safe), 2),
            "safe_height_in": round(max(0.5, final_h - 2 * final_safe), 2),
            "dpi": 300,
            "pixel_width": int(final_w * 300),
            "pixel_height": int(final_h * 300),
            "aspect_ratio": round(final_w / max(0.1, final_h), 3),
            "shape": final_shape,
            "material": final_mat,
            "fabrication_mode": fab_dropdown_default if len(final_fab) < 25 else final_fab,
            "color_mode": final_color_mode,
            "color_constraint": "bw_1bit" if (is_laser or is_stencil) else ("solid_spot_layers" if is_vinyl else "full_color_cmyk"),
            "edge_connections": final_edge_bridges,
            "requires_edge_bridges": final_edge_bridges,
            "paired_contextile_handles": final_paired_handles,
            "raw_blank_image_url": image_url
        }

        raw_handle = handle_override or ai_spec.get("suggested_handle") or "custom-blank"
        handle = re.sub(r"[^a-z0-9_\-]", "", str(raw_handle).lower()) or "custom-blank"
        title = str(ai_spec.get("recommended_title") or f"{handle.replace('-', ' ').title()} ({final_w}\"×{final_h}\")")

        rendered_imgs = cls.render_blank_sizing_template_image(
            handle=handle,
            title=title,
            raw_blank_url=image_url,
            blank_spec=blank_spec
        )
        template_url = rendered_imgs["template_url"]
        raw_blank_url_final = rendered_imgs["raw_blank_url"]
        blank_spec["raw_blank_image_url"] = raw_blank_url_final
        blank_spec["template_image_url"] = template_url

        gallery = [template_url]
        if raw_blank_url_final and raw_blank_url_final not in gallery:
            gallery.append(raw_blank_url_final)

        blank_variables = [
            {
                "key": "fabrication_output_mode",
                "label": "🔥 Physical Fabrication Output Mode",
                "type": "dropdown",
                "category_preset": "fabrication_mode",
                "default_value": fab_dropdown_default,
                "value": fab_dropdown_default,
                "options": EXTENSIVE_VARIABLE_DROPDOWNS["fabrication_mode"]["options"],
                "description": "Switch between Laser 1-Bit B&W Burn, Stencil with Edge Connections, Vinyl Plotter Cut, or Dye Sublimation"
            },
            {
                "key": "style_dropdown",
                "label": "🎨 Artwork Line / Render Style",
                "type": "dropdown",
                "category_preset": "style",
                "default_value": "Ukiyo-e Japanese Woodblock Print" if is_laser else EXTENSIVE_VARIABLE_DROPDOWNS["style"]["options"][0],
                "value": "Ukiyo-e Japanese Woodblock Print" if is_laser else EXTENSIVE_VARIABLE_DROPDOWNS["style"]["options"][0],
                "options": EXTENSIVE_VARIABLE_DROPDOWNS["style"]["options"],
                "description": "Choose artistic style applied inside the blank's safe zone"
            },
            {
                "key": "framing_border_dropdown",
                "label": "🖼️ Safe-Zone Border Treatment",
                "type": "dropdown",
                "category_preset": "framing_border",
                "default_value": EXTENSIVE_VARIABLE_DROPDOWNS["framing_border"]["options"][0],
                "value": EXTENSIVE_VARIABLE_DROPDOWNS["framing_border"]["options"][0],
                "options": EXTENSIVE_VARIABLE_DROPDOWNS["framing_border"]["options"],
                "description": "Choose border or framing inside the blank contour"
            }
        ]

        option_toggles = [
            {
                "key": "laser_bw_burn_only",
                "label": "Laser Engraver 1-Bit Black & White Burn Only (No Grays/Colors)",
                "prompt": "strictly 1-bit pure black and white high-contrast woodburn/laser engraving line art (#000000 burn on #FFFFFF white background, zero grayscale wash)",
                "enabled": bool(is_laser)
            },
            {
                "key": "stencil_edge_bridges",
                "label": "Stencil Edge Connections / Bridges (Connect All Inner Islands)",
                "prompt": "designed as a cuttable physical stencil with thick structural edge bridges connecting every interior island and counter-space to the outer frame so nothing falls out",
                "enabled": bool(final_edge_bridges)
            },
            {
                "key": "contour_safe_margin",
                "label": f"Enforce {final_safe}\" Safe Margin Inside {final_w}\"×{final_h}\" {final_shape.title()} Boundary",
                "prompt": f"centered cleanly inside a {final_w}\"x{final_h}\" {final_shape} boundary with a {final_safe}\" clear outer safe margin",
                "enabled": True
            }
        ]

        modifiers_dict = {
            "entity_kind": "contextile_of_truth",
            "blank_spec": blank_spec,
            "embedded_sot_handles": final_paired_handles,
            "fabrication_mode": [fab_dropdown_default],
            "width_in": final_w,
            "height_in": final_h,
            "dpi": 300,
            "option_toggles": option_toggles
        }

        ref_text = ai_spec.get("reference_text") or (
            f"Contextile of Truth (Physical Blank & Sizing Template): {title}. "
            f"Calibrated Size: {final_w}\" W × {final_h}\" H (Safe Zone: {blank_spec['safe_width_in']}\" × {blank_spec['safe_height_in']}\", {final_safe}\" margin). "
            f"Contour Shape: {final_shape}, Substrate Material: {final_mat}, Fabrication Mode: {blank_spec['fabrication_mode']}."
        )

        compiled = cls.compile_prompt(
            reference_text=ref_text,
            modifiers=modifiers_dict,
            custom_tags=["contextile-of-truth", "blank-substrate", final_shape, final_mat],
            archetype="blank_substrate",
            primary_image_url=template_url,
            gallery_images=gallery,
            variables=blank_variables
        )

        result = {
            "status": "ok",
            "name": handle,
            "suggested_handle": handle,
            "title": title,
            "description": ai_spec.get("description") or f"Contextile of Truth for {final_w}\"×{final_h}\" {final_mat} ({final_shape}) blank.",
            "archetype": "blank_substrate",
            "entity_kind": "contextile_of_truth",
            "reference_type": "hybrid",
            "reference_text": ref_text,
            "primary_image_url": template_url,
            "reference_image_url": template_url,
            "template_image_url": template_url,
            "gallery_images": gallery,
            "blank_spec": blank_spec,
            "embedded_sot_handles": final_paired_handles,
            "option_toggles": option_toggles,
            "modifiers": modifiers_dict,
            "variables": blank_variables,
            "tags": ["contextile-of-truth", "blank-substrate", final_shape, final_mat],
            "assembled_prompt": compiled
        }

        if save_immediately and db:
            ctx = cls.create_contextile(result, db)
            result["id"] = ctx.id
            result["saved"] = True
            result["message"] = f"Contextile of Truth '@{handle}' ({final_w}\"×{final_h}\" {final_mat}) calibrated and saved!"
        else:
            result["saved"] = False

        return result

    @classmethod
    def _detect_sot_variant_request(
        cls,
        seed: str,
        matched_ctxs: List[Dict[str, Any]],
        extraction_mentions: List[Dict[str, Any]],
        parent_sot_handle: Optional[str] = None,
        variant_label: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Detects when a user is creating a Source of Truth Variant (e.g. '@geppy in a civil war costume',
        '@geppy wearing a spacesuit', '@geppy as a pirate captain', or explicit parent_sot_handle).
        Returns metadata for linking the variant under the parent SOT so @autocomplete and the SOT gallery group them together.
        """
        raw = (seed or "").strip()
        explicit_parent = (parent_sot_handle or "").strip().lstrip("@").lower()

        parent_ctx = None
        if explicit_parent:
            for c in matched_ctxs:
                if (c.get("name") or "").lower() == explicit_parent:
                    parent_ctx = c
                    break
            if not parent_ctx and explicit_parent in ("geppy", "captain-geppy", "captaingeppy"):
                parent_ctx = dict(cls.GEPPY_BUILTIN_PROFILE)
            elif not parent_ctx:
                parent_ctx = {"name": explicit_parent, "title": explicit_parent.replace("-", " ").title(), "archetype": "character", "entity_kind": "sot"}

        # If no explicit parent_sot_handle was passed, check if the prompt starts with or contains an @SOT character/entity tag + a variant descriptor
        if not parent_ctx and matched_ctxs and not extraction_mentions:
            first_ctx = matched_ctxs[0]
            first_ek = (first_ctx.get("entity_kind") or cls.infer_entity_kind(first_ctx.get("archetype"), first_ctx.get("modifiers"), first_ctx.get("name"))).lower()
            if first_ek == "sot" or first_ctx.get("archetype") in cls.SOT_ARCHETYPES:
                remainder = re.sub(r"@[a-zA-Z0-9_:\-]+", "", raw).strip(" ,:;-—")
                if remainder and len(remainder) >= 3:
                    parent_ctx = first_ctx
                    explicit_parent = (first_ctx.get("name") or "geppy").lower()

        if not parent_ctx:
            return None

        p_handle = (parent_ctx.get("name") or explicit_parent or "geppy").lower()
        # Normalize captain-geppy variants under geppy if user tagged @geppy
        p_title_raw = parent_ctx.get("title") or p_handle.replace("-", " ").title()
        p_short_title = p_title_raw.split("(")[0].strip() or p_handle.replace("-", " ").title()

        remainder = re.sub(r"@[a-zA-Z0-9_:\-]+", "", raw).strip(" ,:;-—")
        cleaned_variant = (variant_label or remainder or "Custom Variant").strip()
        # Strip leading prepositions like "in a", "in an", "in", "wearing a", "wearing", "dressed as a", "dressed in", "as a", "as", "with a", "with"
        cleaned_variant_short = re.sub(
            r"^(?:dressed\s+in\s+(?:a|an|the)\s+|dressed\s+as\s+(?:a|an|the)\s+|wearing\s+(?:a|an|the)\s+|wearing\s+|in\s+(?:a|an|the)\s+|in\s+|as\s+(?:a|an|the)\s+|as\s+|with\s+(?:a|an|the)\s+|with\s+|variant\s*[:\-]?\s*)",
            "",
            cleaned_variant,
            flags=re.IGNORECASE
        ).strip(" .,:;-—") or cleaned_variant

        var_slug = re.sub(r"[^a-z0-9\-]", "", cleaned_variant_short.lower().replace(" ", "-")).strip("-")
        var_slug = re.sub(r"-+", "-", var_slug)[:32].strip("-") or "variant"

        if var_slug.startswith(f"{p_handle}-"):
            full_handle = var_slug
        else:
            full_handle = f"{p_handle}-{var_slug}"

        display_variant_label = cleaned_variant_short.title()
        return {
            "is_sot_variant": True,
            "parent_sot_handle": p_handle,
            "parent_sot_title": p_short_title,
            "parent_ctx": parent_ctx,
            "variant_label": display_variant_label,
            "variant_phrase": remainder or cleaned_variant,
            "suggested_handle": full_handle,
            "recommended_title": f"{p_short_title} — {display_variant_label}",
        }

    @classmethod
    def generate_ai_contextile(
        cls,
        concept: str,
        archetype: Optional[str] = None,
        save_immediately: bool = True,
        db: Optional[Session] = None,
        image_url: Optional[str] = None,
        entity_kind: Optional[str] = None,
        blank_spec: Optional[Dict[str, Any]] = None,
        parent_sot_handle: Optional[str] = None,
        variant_label: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        AI Generates a complete, production-ready Contextile, Source of Truth, SOT Variant (e.g. '@geppy in a civil war costume'),
        or Contextile of Truth (Blank) from any user concept (including @SOT tags and @<prefix><Handle> extraction style tags like @vsGeppy, @visGeppy, @qGeppy, @matGeppy, @palGeppy) and optional uploaded image.
        """
        seed = (concept or "").strip()
        low = seed.lower()
        arch = archetype if (archetype and archetype not in ("all", "auto")) else ""

        # Resolve any @mentions and @<prefix><Handle> extraction keywords (e.g. @vsGeppy, @visGeppy, @qGeppy, @palGeppy, @matGeppy)
        mention_info = cls.resolve_mentions(seed, db)
        grounding_prompt = mention_info.get("grounding_prompt", "")
        extraction_mentions = mention_info.get("extraction_mentions", [])
        matched_ctxs = mention_info.get("contextiles", [])
        merged_ext_mods = mention_info.get("extracted_modifiers", {})
        clean_subject = re.sub(r"@[a-zA-Z0-9_:\-]+", "", seed).strip()
        clean_low = clean_subject.lower()

        # Check if user is creating a Contextile of Truth (Physical Blank + Sizing Template)
        is_blank_request = (
            entity_kind == "contextile_of_truth"
            or arch == "blank_substrate"
            or isinstance(blank_spec, dict)
            or any(k in clean_low for k in ["blank", "coaster", "plaque", "tumbler", "sublimat", "laser engrav", "wood burn", "woodburn", "slate"])
        )
        if is_blank_request:
            bs = blank_spec if isinstance(blank_spec, dict) else {}
            return cls.analyze_blank_image_and_build_template(
                image_url=image_url,
                concept=seed,
                width_in=bs.get("width_in"),
                height_in=bs.get("height_in"),
                safe_margin_in=bs.get("safe_margin_in"),
                shape=bs.get("shape"),
                material=bs.get("material"),
                fabrication_mode=bs.get("fabrication_mode"),
                save_immediately=save_immediately,
                db=db
            )

        # Detect if this is a Source of Truth Variant (e.g., "@geppy in a civil war costume")
        variant_meta = cls._detect_sot_variant_request(
            seed=seed,
            matched_ctxs=matched_ctxs,
            extraction_mentions=extraction_mentions,
            parent_sot_handle=parent_sot_handle,
            variant_label=variant_label
        )
        if variant_meta:
            p_ctx = variant_meta["parent_ctx"]
            arch = p_ctx.get("archetype") or "character"
            entity_kind = "sot"
            p_mods = p_ctx.get("modifiers") if isinstance(p_ctx.get("modifiers"), dict) else {}
            for mk in ["style", "lighting", "theme", "era", "medium", "camera_lens", "materials", "color_grading", "mood_atmosphere"]:
                if p_mods.get(mk) and not merged_ext_mods.get(mk):
                    merged_ext_mods[mk] = list(p_mods.get(mk))

        # Deduce archetype if not specified (or if default 'style' was passed from top bar when user actually described a character/mascot with @vsGeppy)
        character_keywords = ["character", "mascot", "person", "pilot", "captain", "astronaut", "avatar", "companion", "sidekick", "hero", "villain", "robot", "creature", "pet", "dog", "cat", "fox", "owl", "alien", "knight", "wizard", "costume", "uniform", "outfit", "armor"]
        if not arch or (arch == "style" and entity_kind != "contextile" and clean_subject and any(k in clean_low for k in character_keywords)):
            if any(k in clean_low for k in ["stencil", "laser", "vinyl", "cut", "output", "diecut", "print", "pdf"]):
                arch = "output"
            elif variant_meta or any(k in clean_low for k in character_keywords):
                arch = "character"
                if not entity_kind:
                    entity_kind = "sot"
            elif any(k in clean_low for k in ["baseball", "card", "trading", "sticker", "comic", "style", "aesthetic", "medium", "retro", "vintage", "vaporwave", "anime"]):
                arch = "style"
            elif any(k in clean_low for k in ["icon", "squircle", "glyph", "app icon"]):
                arch = "icon_set"
            elif any(k in clean_low for k in ["ui", "hud", "button", "dashboard"]):
                arch = "ui_component"
            elif any(k in clean_low for k in ["logo", "brand", "emblem"]):
                arch = "brand_asset"
            elif any(k in clean_low for k in ["environment", "planet", "landscape", "cockpit", "place", "manor"]):
                arch = "place"
            elif not arch:
                arch = "character" if (clean_subject and (extraction_mentions or variant_meta) and "style" not in clean_low) else "style"

        system_instruction = """You are Captain Geppy's Master Style & Source of Truth (SOT) Architect aboard Geppy's GitBridge.
The user wants to generate a complete, production-grade SOT, SOT Variant, or Contextile from their concept or idea.
The user may include:
1. A Source of Truth Variant request such as "@geppy in a civil war costume" — where the character's core identity, facial likeness, and signature claymation-vinyl aesthetic from the parent SOT (@geppy) MUST be preserved 100%, while outfitting/adapting them into the requested variant costume, era, or role.
2. Aspect/Style Extraction Prefix Tags:
- @vs<Handle> / @vis<Handle> (e.g. @vsGeppy, @visGeppy): Extract ONLY the visual rendering style, medium, and tactile material feel (e.g. Geppy's claymation-ish sculpted designer vinyl toy aesthetic) and apply it to the new subject WITHOUT copying the referenced character's literal identity/face.
- @q<Handle> / @chibi<Handle> (e.g. @qGeppy): Extract Q-Style / Chibi 1:2.5 cute stylized collectible vinyl proportions + aesthetic.
- @mat<Handle> / @tex<Handle> (e.g. @matGeppy): Extract ONLY the physical surface materials and textures.
- @pal<Handle> / @col<Handle> (e.g. @palGeppy): Extract ONLY the signature color palette and tonal grading.
- @lit<Handle> / @light<Handle> (e.g. @litGeppy): Extract ONLY the studio lighting rig and rim illumination.
- @id<Handle> / @char<Handle> (e.g. @idGeppy): Lock ONLY the character's core facial/anatomical identity while adapting to a new artistic medium.
- @fit<Handle> / @gear<Handle> (e.g. @fitGeppy): Extract ONLY the outfit, suit, armor, and wearable gear.
- @sil<Handle> / @line<Handle> (e.g. @silGeppy): Extract ONLY the silhouette contour and cutout linework.
- @comp<Handle> / @cam<Handle> (e.g. @compGeppy): Extract ONLY the camera angle, lens, and framing composition.
- @vibe<Handle> / @mood<Handle> (e.g. @vibeGeppy): Extract ONLY the emotional mood, era, and genre vibe.
- @clay<Handle> / @vinyl<Handle> / @3d<Handle>: Render as a 3D stop-motion sculpted claymation & designer vinyl toy figure.
- @flat<Handle> / @vec<Handle>: Render as a crisp 2D flat vector / cel-shaded die-cut graphic.

Respond STRICTLY with valid JSON having these fields:
{
  "archetype": "style" | "character" | "icon_set" | "ui_component" | "brand_asset" | "environment" | "place" | "prop" | "output" | "general",
  "suggested_handle": "clean-kebab-case-handle",
  "recommended_title": "Punchy High-Impact Display Title",
  "description": "1-2 sentence overview of what this SOT/Contextile encapsulates.",
  "reference_text": "Vivid 2-4 sentence ground-truth reference baseline defining subject/style, materials, border geometry, color grading, lighting, and print/render techniques.",
  "master_style_prompt": "The definitive, hyper-detailed prompt capturing this exact visual grammar for image generation.",
  "prompt_template": "Template string with {subject} placeholder so any character or object can be rendered in this style.",
  "style": ["Artistic Style 1", "Artistic Style 2"],
  "lighting": ["Lighting Style 1", "Lighting Style 2"],
  "theme": ["Theme 1", "Theme 2"],
  "era": ["Era 1"],
  "medium": ["Medium 1"],
  "materials": ["Material 1", "Material 2"],
  "color_grading": ["Color Grading 1"],
  "custom_tags": ["tag1", "tag2", "tag3", "tag4"],
  "custom_modifiers": "comma-separated technical modifiers",
  "creative_options": ["Option 1", "Option 2", "Option 3", "Option 4"],
  "target_format_hint": "trading_card" | "app_icon" | "banner_hero" | "ui_component" | "avatar",
  "color_palette": ["#HEX1 (Label)", "#HEX2 (Label)", "#HEX3 (Label)", "#HEX4 (Label)"],
  "rationale": "Why this visual recipe creates authentic consistency."
}"""

        user_msg = f"Concept: {seed}\nClean Subject (without @tags): {clean_subject or seed}\nPreferred Archetype: {arch}"
        if variant_meta:
            user_msg += (
                f"\n\n[SOT VARIANT MODE ACTIVE]\n"
                f"Parent SOT Handle: @{variant_meta['parent_sot_handle']} ({variant_meta['parent_sot_title']})\n"
                f"Variant Label: {variant_meta['variant_label']}\n"
                f"Variant Phrase: {variant_meta['variant_phrase']}\n"
                f"Required Handle: {variant_meta['suggested_handle']}\n"
                f"Required Display Title: {variant_meta['recommended_title']}\n"
                f"IMPORTANT: Preserve 100% of @{variant_meta['parent_sot_handle']}'s core character identity, face, proportions, and claymation-vinyl aesthetic while dressing/adapting them in '{variant_meta['variant_phrase']}'!"
            )
        if grounding_prompt:
            user_msg += f"\n\n{grounding_prompt}"
        messages = [{"role": "user", "parts": [{"text": user_msg}]}]
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
            if variant_meta:
                p_ctx = variant_meta["parent_ctx"]
                p_ref = p_ctx.get("reference_text") or cls.GEPPY_BUILTIN_PROFILE["reference_text"]
                p_style_sum = p_ctx.get("style_summary") or cls.GEPPY_BUILTIN_PROFILE["style_summary"]
                v_label = variant_meta["variant_label"]
                v_phrase = variant_meta["variant_phrase"]
                v_handle = variant_meta["suggested_handle"]
                v_title = variant_meta["recommended_title"]
                p_handle = variant_meta["parent_sot_handle"]
                parsed_data = {
                    "archetype": p_ctx.get("archetype") or "character",
                    "suggested_handle": v_handle,
                    "recommended_title": v_title,
                    "description": f"Official '{v_label}' SOT Variant of @{p_handle} ({variant_meta['parent_sot_title']}). Preserves @{p_handle}'s exact character identity and claymation-vinyl style while dressed in {v_phrase}.",
                    "reference_text": (
                        f"[SOT Variant of @{p_handle}: {v_title}] "
                        f"{variant_meta['parent_sot_title']} {v_phrase} — preserving the exact character likeness, expressive eyes, proportions, and signature tactile stop-motion polymer claymation & designer vinyl figure aesthetic ({p_style_sum}), "
                        f"now outfitted in detailed {v_label.lower()} attire with sculpted clay fabric folds, brushed brass/gold buttons, and miniature diorama studio lighting. Base identity: {p_ref}"
                    ),
                    "master_style_prompt": (
                        f"{variant_meta['parent_sot_title']} ({v_phrase}), sculpted in tactile stop-motion polymer claymation and smooth satin designer collectible vinyl toy style, "
                        f"wearing detailed {v_label.lower()} attire with authentic period tailoring, sculpted clay textures, warm amber-gold and cyan rim lighting, 8K Octane miniature diorama render."
                    ),
                    "prompt_template": (
                        f"{variant_meta['parent_sot_title']} in {v_label} ({{subject}}), sculpted claymation-vinyl collectible figure style."
                    ),
                    "style": merged_ext_mods.get("style") or ["Aardman Stop-Motion Sculpted Claymation", "Pixar / Disney Feature 3D Character Animation"],
                    "lighting": merged_ext_mods.get("lighting") or ["Volumetric Studio Light", "Cyberpunk Neon Rim"],
                    "theme": merged_ext_mods.get("theme") or ["Cosmic Galactic & Nebula", "Claymation & Designer Vinyl Collectible"],
                    "era": merged_ext_mods.get("era") or ["2026 Next-Gen Frontier"],
                    "medium": merged_ext_mods.get("medium") or ["8K Octane / Redshift Ray-Traced 3D Render", "ZBrush High-Poly Digital Clay Sculpt"],
                    "materials": merged_ext_mods.get("materials") or ["Soft Vinyl Designer Toy (Bearbrick / Funko)", "Frosted Translucent Acrylic & Glass"],
                    "color_grading": merged_ext_mods.get("color_grading") or ["Geppy Signature (Amber Gold #F59E0B, Cyan #06B6D4 & Obsidian)"],
                    "custom_tags": [p_handle, v_handle, "sot-variant", v_label.lower().replace(" ", "-"), "claymation-vinyl"],
                    "custom_modifiers": f"sot-variant-of-{p_handle}, {v_label.lower().replace(' ', '-')}, claymation-sculpted-vinyl, character-identity-lock",
                    "creative_options": [
                        f"Full {v_label} regalia & tailored clay details",
                        f"Preserve @{p_handle} signature visor/accessories",
                        "Tactile polymer clay thumbprint micro-texture",
                        "Collectible designer vinyl figure articulation"
                    ],
                    "target_format_hint": "avatar",
                    "color_palette": cls.GEPPY_BUILTIN_PROFILE["color_palette"],
                    "rationale": f"Linked SOT Variant under @{p_handle} so typing @{p_handle} surfaces both the base character and '{v_title}'."
                }
            elif extraction_mentions or matched_ctxs:
                ext_first = extraction_mentions[0] if extraction_mentions else None
                base_ctx = (ext_first["target_data"] if (ext_first and "target_data" in ext_first) else None) or (matched_ctxs[0] if matched_ctxs else cls.GEPPY_BUILTIN_PROFILE)
                ext_tags_str = ", ".join(m["raw_tag"] for m in extraction_mentions) if extraction_mentions else ", ".join(f"@{c.get('name')}" for c in matched_ctxs)
                ext_directives_str = " ".join(m.get("directive", "") for m in extraction_mentions if m.get("directive"))
                style_sum = (ext_first.get("style_summary") if ext_first else None) or cls.GEPPY_BUILTIN_PROFILE["style_summary"]
                palette_out = (ext_first.get("color_palette") if ext_first else None) or cls.GEPPY_BUILTIN_PROFILE["color_palette"]

                if clean_subject:
                    handle_slug = re.sub(r"[^a-z0-9\-]", "", clean_subject.lower().replace(" ", "-")).strip("-") or "custom-sot"
                    rec_title = f"{clean_subject.title()} ({ext_tags_str})"
                else:
                    mode_prefix = ext_first["extraction_mode"] if ext_first else "style"
                    t_handle = ext_first["target_handle"] if ext_first else base_ctx.get("name", "geppy")
                    handle_slug = f"{mode_prefix}-{t_handle}-style"
                    lbl = ext_first["extraction_meta"]["label"] if (ext_first and ext_first.get("extraction_meta")) else "Visual Style"
                    rec_title = f"{t_handle.replace('-', ' ').title()} — {lbl} ({ext_tags_str})"

                is_q = any(m.get("extraction_mode") == "q" for m in extraction_mentions)
                q_clause = " with cute Q-Style / Chibi 1:2.5 oversized head and compact collectible vinyl figure proportions" if is_q else ""

                parsed_data = {
                    "archetype": arch or ("character" if clean_subject else "style"),
                    "suggested_handle": handle_slug[:40],
                    "recommended_title": rec_title,
                    "description": f"{'Character SOT' if arch == 'character' else 'Style Contextile'} grounded with {ext_tags_str}: {style_sum[:160]}.",
                    "reference_text": (
                        f"{clean_subject.title() if clean_subject else 'Reusable Extracted Visual Style'}{q_clause} rendered in the extracted aesthetic of {ext_tags_str}: "
                        f"{style_sum}. {ext_directives_str}"
                    ).strip(),
                    "master_style_prompt": (
                        f"{clean_subject if clean_subject else '{subject}'}{q_clause}, rendered in {style_sum}. {ext_directives_str}"
                    ).strip(),
                    "prompt_template": (
                        f"{{subject}}{q_clause} rendered in the {ext_tags_str} aesthetic: {style_sum}."
                    ),
                    "style": merged_ext_mods.get("style") or ["Aardman Stop-Motion Sculpted Claymation", "Pixar / Disney Feature 3D Character Animation"],
                    "lighting": merged_ext_mods.get("lighting") or ["Volumetric Studio Light", "Cyberpunk Neon Rim"],
                    "theme": merged_ext_mods.get("theme") or ["Cosmic Galactic & Nebula", "Claymation & Designer Vinyl Collectible"],
                    "era": merged_ext_mods.get("era") or ["2026 Next-Gen Frontier"],
                    "medium": merged_ext_mods.get("medium") or ["8K Octane / Redshift Ray-Traced 3D Render", "ZBrush High-Poly Digital Clay Sculpt"],
                    "materials": merged_ext_mods.get("materials") or ["Soft Vinyl Designer Toy (Bearbrick / Funko)", "Frosted Translucent Acrylic & Glass"],
                    "color_grading": merged_ext_mods.get("color_grading") or ["Geppy Signature (Amber Gold #F59E0B, Cyan #06B6D4 & Obsidian)"],
                    "custom_tags": [handle_slug[:24], "claymation-vinyl", *[m["raw_tag"].lstrip("@") for m in extraction_mentions]],
                    "custom_modifiers": "claymation-sculpted-vinyl, tactile-thumbprint-clay, satin-vinyl-finish, miniature-diorama-lighting" + (", q-style-chibi-proportions" if is_q else ""),
                    "creative_options": [
                        "Sculpted polymer clay thumbprint micro-texture",
                        "Smooth satin designer vinyl figure joints",
                        "Q-Style 1:2.5 oversized expressive head",
                        "Glossy translucent cyan visor refraction",
                        "Warm amber-gold & electric cyan rim lighting"
                    ],
                    "target_format_hint": "avatar" if arch == "character" else "app_icon",
                    "color_palette": palette_out,
                    "rationale": f"Automatically extracted via {ext_tags_str} so the new asset inherits Geppy's claymation-ish sculpted designer vinyl aesthetic."
                }
            elif "stencil" in low or "bridge" in low or "edge connection" in low:
                parsed_data = {
                    "archetype": "style",
                    "suggested_handle": "stencil-edge-connections",
                    "recommended_title": "Cut Stencil with Edge Connections (Bridged Islands)",
                    "description": "Reusable fabrication Contextile that converts any Character SOT, Logo, or Subject into a bold high-contrast cuttable stencil with structural bridges connecting all inner islands to the outer edge.",
                    "reference_text": "Cuttable Physical Stencil Contextile Template: Bold high-contrast black-and-white cutout silhouette where every enclosed interior island (eyes, letter counters, inner shapes) is tied to the outer border via sturdy structural stencil bridges / edge connections so no pieces fall out when laser-cut or knife-cut.",
                    "master_style_prompt": "High-contrast cuttable stencil art with sturdy structural edge connections and stencil bridges holding all interior islands connected to the outer frame, bold clean vector cutout paths, pure black and white stencil graphic.",
                    "prompt_template": "Bold cuttable stencil of {subject} with sturdy structural stencil bridges and edge connections holding all interior islands connected to the outer border, pure high-contrast black and white cutout vector art.",
                    "lighting": ["High-Contrast Rim Silhouette Only"],
                    "theme": ["Cuttable Stencil & Vinyl Fabrication"],
                    "era": ["2026 Next-Gen Frontier"],
                    "medium": ["Clean Scalable Vector SVG Flat Illustration"],
                    "materials": ["Laser-Cut Basswood & Birch Plywood"],
                    "custom_tags": ["stencil", "edge-connections", "stencil-bridges", "laser-cut", "vinyl-cutter"],
                    "custom_modifiers": "connected-stencil-bridges, no-floating-islands, bold-cutout-paths, high-contrast-monochrome",
                    "creative_options": ["Thick 3mm structural bridges", "Outer frame edge connection", "Single-layer spray stencil", "Weed-ready vinyl contour"],
                    "target_format_hint": "app_icon",
                    "color_palette": ["#000000 (Cutout Void)", "#FFFFFF (Stencil Bridge Material)"],
                    "rationale": "Structural edge connections ensure every internal island remains physically attached to the stencil sheet when cut on a laser or vinyl plotter."
                }
            elif " baseball" in low or "card" in low:
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

        # Enforce SOT Variant naming & parent linkage if variant_meta was detected
        if variant_meta:
            parsed_data["suggested_handle"] = variant_meta["suggested_handle"]
            parsed_data["recommended_title"] = variant_meta["recommended_title"]
            parsed_data["archetype"] = variant_meta["parent_ctx"].get("archetype") or "character"
            existing_tags = parsed_data.get("custom_tags") if isinstance(parsed_data.get("custom_tags"), list) else []
            for vt in [variant_meta["parent_sot_handle"], variant_meta["suggested_handle"], "sot-variant"]:
                if vt not in existing_tags:
                    existing_tags.insert(0, vt)
            parsed_data["custom_tags"] = existing_tags

        # Merge any extracted modifiers from @vsGeppy / @qGeppy / @matGeppy / @palGeppy / etc. into parsed_data
        for mod_k, mod_vals in merged_ext_mods.items():
            if mod_vals:
                existing_list = parsed_data.get(mod_k) if isinstance(parsed_data.get(mod_k), list) else []
                for mv in reversed(mod_vals):
                    if mv not in existing_list:
                        existing_list.insert(0, mv)
                parsed_data[mod_k] = existing_list

        if extraction_mentions:
            ext_directives = " | ".join(m["directive"] for m in extraction_mentions if m.get("directive"))
            if ext_directives:
                cur_master = parsed_data.get("master_style_prompt") or ""
                if ext_directives[:40].lower() not in cur_master.lower():
                    parsed_data["master_style_prompt"] = f"{cur_master} | {ext_directives}".strip(" |")
            if not parsed_data.get("color_palette") and extraction_mentions[0].get("color_palette"):
                parsed_data["color_palette"] = extraction_mentions[0]["color_palette"]

        handle = parsed_data.get("suggested_handle", "new-contextile")
        title = parsed_data.get("recommended_title", handle.replace("-", " ").title())
        archetype_out = parsed_data.get("archetype", arch or "style")
        color_palette = parsed_data.get("color_palette") or []

        # Use uploaded image if provided, otherwise generate preview thumbnail image
        if image_url:
            preview_url = image_url
        else:
            preview_url = generate_contextile_thumbnail(
                handle=handle,
                title=title,
                concept=seed,
                archetype=archetype_out,
                color_palette=color_palette,
                reference_text=parsed_data.get("reference_text"),
                master_style_prompt=parsed_data.get("master_style_prompt")
            )

        effective_ek = (
            "sot" if variant_meta else (
                entity_kind
                if (entity_kind and not (entity_kind == "contextile" and archetype_out in cls.SOT_ARCHETYPES))
                else cls.infer_entity_kind(archetype_out, {}, handle)
            )
        )
        modifiers_dict = {
            "entity_kind": effective_ek,
            "style": parsed_data.get("style") or merged_ext_mods.get("style") or [],
            "lighting": parsed_data.get("lighting") or merged_ext_mods.get("lighting") or [],
            "theme": parsed_data.get("theme") or merged_ext_mods.get("theme") or [],
            "era": parsed_data.get("era") or merged_ext_mods.get("era") or [],
            "medium": parsed_data.get("medium") or merged_ext_mods.get("medium") or [],
            "camera_lens": parsed_data.get("camera_lens") or merged_ext_mods.get("camera_lens") or [],
            "materials": parsed_data.get("materials") or merged_ext_mods.get("materials") or [],
            "color_grading": parsed_data.get("color_grading") or merged_ext_mods.get("color_grading") or [],
            "mood_atmosphere": parsed_data.get("mood_atmosphere") or merged_ext_mods.get("mood_atmosphere") or [],
            "framing_border": parsed_data.get("framing_border") or merged_ext_mods.get("framing_border") or [],
            "custom": [parsed_data.get("custom_modifiers", "")]
        }
        if variant_meta:
            modifiers_dict["is_sot_variant"] = True
            modifiers_dict["parent_sot_handle"] = variant_meta["parent_sot_handle"]
            modifiers_dict["parent_sot_title"] = variant_meta["parent_sot_title"]
            modifiers_dict["variant_label"] = variant_meta["variant_label"]
        if extraction_mentions:
            modifiers_dict["extraction_mentions"] = [
                {"raw_tag": m["raw_tag"], "mode": m["extraction_mode"], "target_handle": m["target_handle"], "label": m["extraction_meta"]["label"]}
                for m in extraction_mentions
            ]

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
            "entity_kind": modifiers_dict["entity_kind"],
            "is_sot_variant": bool(variant_meta),
            "parent_sot_handle": variant_meta["parent_sot_handle"] if variant_meta else None,
            "parent_sot_title": variant_meta["parent_sot_title"] if variant_meta else None,
            "variant_label": variant_meta["variant_label"] if variant_meta else None,
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
            "resolved_mentions": extraction_mentions,
            "assembled_prompt": compiled
        }

        # Save to database if requested
        if save_immediately and db:
            ctx = SOTService.create_contextile({
                "name": handle,
                "title": title,
                "description": result.get("description"),
                "archetype": archetype_out,
                "entity_kind": modifiers_dict["entity_kind"],
                "is_sot_variant": bool(variant_meta),
                "parent_sot_handle": variant_meta["parent_sot_handle"] if variant_meta else None,
                "parent_sot_title": variant_meta["parent_sot_title"] if variant_meta else None,
                "variant_label": variant_meta["variant_label"] if variant_meta else None,
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
            if variant_meta:
                result["message"] = f"SOT Variant '@{handle}' ({variant_meta['variant_label']}) created and nested under @{variant_meta['parent_sot_handle']}!"
            else:
                result["message"] = f"SOT / Contextile '@{handle}' created and saved to Vault!"
        else:
            result["saved"] = False

        return result

    @staticmethod
    def seed_default_contextiles(db: Session):
        """Seed default starter Contextiles for Geppy (@geppy & @captain-geppy with claymation-vinyl aesthetic, @geppy-civil-war-costume SOT Variant, @vs-geppy visual style), icon sets, galactic cards, Contextiles of Truth (Blanks), and Fabrication Contextiles."""
        geppy_prof = SOTService.GEPPY_BUILTIN_PROFILE
        geppy_ctx = db.query(ContextileModel).filter(ContextileModel.name == "geppy").first()
        if not geppy_ctx:
            geppy_ctx = SOTService.create_contextile({
                "name": "geppy",
                "title": geppy_prof["title"],
                "description": "Geppy's official Character SOT: charismatic galactic mascot sculpted in a tactile claymation-ish designer vinyl art toy aesthetic. Tag @geppy for full character, create variants like '@geppy in a civil war costume', or use @vsGeppy / @visGeppy / @qGeppy / @matGeppy / @palGeppy to extract specific style aspects!",
                "archetype": "character",
                "entity_kind": "sot",
                "reference_type": "text",
                "reference_text": geppy_prof["reference_text"],
                "modifiers": dict(geppy_prof["modifiers"]),
                "tags": ["sot", "geppy", "claymation", "vinyl-toy", "character", "mascot"],
                "assembled_prompt": (
                    "[🔒 SOURCE OF TRUTH (PERSON / CHARACTER) - Unchanging identity: preserve exact facial likeness, hair, proportions, and signature attire] | "
                    f"{geppy_prof['reference_text']} | "
                    "Artistic Style: Aardman Stop-Motion Sculpted Claymation, Pixar / Disney Feature 3D Character Animation | "
                    "Render Medium: 8K Octane / Redshift Ray-Traced 3D Render, ZBrush High-Poly Digital Clay Sculpt | "
                    "Materials & Textures: Soft Vinyl Designer Toy (Bearbrick / Funko), Hand-Sculpted Matte Polymer Clay with Thumbprint Texture, Frosted Translucent Acrylic & Glass | "
                    "Color Grading: Geppy Signature (Amber Gold #F59E0B, Cyan #06B6D4 & Obsidian)"
                )
            }, db)
        else:
            g_mods = dict(geppy_ctx.modifiers or {})
            if geppy_ctx.archetype != "character" or "Aardman Stop-Motion Sculpted Claymation" not in (g_mods.get("style") or []):
                geppy_ctx.archetype = "character"
                for k, v in geppy_prof["modifiers"].items():
                    if not g_mods.get(k):
                        g_mods[k] = list(v) if isinstance(v, list) else v
                    elif isinstance(v, list) and isinstance(g_mods.get(k), list):
                        for item in reversed(v):
                            if item not in g_mods[k]:
                                g_mods[k].insert(0, item)
                geppy_ctx.modifiers = g_mods
                if not geppy_ctx.reference_text or "claymation" not in geppy_ctx.reference_text.lower():
                    geppy_ctx.reference_text = geppy_prof["reference_text"]
                cur_tags = list(geppy_ctx.tags or [])
                for t in ["geppy", "claymation", "vinyl-toy", "character", "vsGeppy"]:
                    if t not in cur_tags:
                        cur_tags.append(t)
                geppy_ctx.tags = cur_tags
                db.commit()

        captain_ctx = db.query(ContextileModel).filter(ContextileModel.name == "captain-geppy").first()
        if not captain_ctx:
            SOTService.create_contextile({
                "name": "captain-geppy",
                "title": "Captain Geppy (Claymation-Vinyl Galactic Commander)",
                "description": "The cosmic captain navigating the Galaxy of AI-crafted applications, sculpted in a claymation-ish designer vinyl character style.",
                "archetype": "character",
                "entity_kind": "sot",
                "reference_type": "text",
                "reference_text": geppy_prof["reference_text"],
                "modifiers": dict(geppy_prof["modifiers"]),
                "tags": ["persona", "captain", "galaxy-commander", "claymation", "vinyl-toy"],
                "assembled_prompt": (
                    "[🔒 SOURCE OF TRUTH (PERSON / CHARACTER) - Preserve facial likeness, suit design, and character identity] | "
                    f"{geppy_prof['reference_text']} | "
                    "Artistic Style: Aardman Stop-Motion Sculpted Claymation, Pixar / Disney Feature 3D Character Animation | "
                    "Render Medium: 8K Octane / Redshift Ray-Traced 3D Render, ZBrush High-Poly Digital Clay Sculpt | "
                    "Materials & Textures: Soft Vinyl Designer Toy (Bearbrick / Funko), Brushed Titanium Metal, Frosted Translucent Acrylic & Glass"
                )
            }, db)
        else:
            c_mods = dict(captain_ctx.modifiers or {})
            if "Aardman Stop-Motion Sculpted Claymation" not in (c_mods.get("style") or []):
                c_mods["style"] = ["Aardman Stop-Motion Sculpted Claymation", "Pixar / Disney Feature 3D Character Animation"] + list(c_mods.get("style") or [])
                c_mods["materials"] = ["Soft Vinyl Designer Toy (Bearbrick / Funko)", "Frosted Translucent Acrylic & Glass"] + list(c_mods.get("materials") or [])
                captain_ctx.modifiers = c_mods
                if "claymation" not in (captain_ctx.reference_text or "").lower():
                    captain_ctx.reference_text = geppy_prof["reference_text"]
                db.commit()

        geppy_sample_img = getattr(geppy_ctx, "primary_image_url", None) or getattr(geppy_ctx, "reference_image_url", None)

        # Seed default SOT Variant: @geppy-civil-war-costume (nested under @geppy)
        cw_geppy_ctx = db.query(ContextileModel).filter(ContextileModel.name == "geppy-civil-war-costume").first()
        if not cw_geppy_ctx:
            cw_mods = dict(geppy_prof["modifiers"])
            cw_mods["entity_kind"] = "sot"
            cw_mods["is_sot_variant"] = True
            cw_mods["parent_sot_handle"] = "geppy"
            cw_mods["parent_sot_title"] = "Geppy"
            cw_mods["variant_label"] = "Civil War Costume"
            SOTService.create_contextile({
                "name": "geppy-civil-war-costume",
                "title": "Geppy — Civil War Costume",
                "description": "SOT Variant of @geppy: Captain Geppy outfitted in a tailored 1860s American Civil War Union officer coat with double-breasted brass buttons, gold braided shoulder epaulets, kepi cap with cyan holographic visor brim, and sculpted polymer claymation-vinyl texture.",
                "archetype": "character",
                "entity_kind": "sot",
                "is_sot_variant": True,
                "parent_sot_handle": "geppy",
                "parent_sot_title": "Geppy",
                "variant_label": "Civil War Costume",
                "reference_type": "hybrid" if geppy_sample_img else "text",
                "primary_image_url": geppy_sample_img,
                "reference_image_url": geppy_sample_img,
                "gallery_images": [geppy_sample_img] if geppy_sample_img else [],
                "reference_text": (
                    "[SOT Variant of @geppy: Geppy — Civil War Costume] "
                    "Geppy (Captain Geppy) in an authentic 1860s Civil War officer costume — preserving 100% of @geppy's expressive sculpted claymation face, friendly eyes, and tactile designer vinyl toy proportions, "
                    "now dressed in a navy-indigo wool double-breasted Union officer frock coat with sculpted polymer clay fabric folds, polished 24K brass buttons, gold bullion shoulder epaulets, crimson waist sash, and a classic Civil War kepi cap integrated with Geppy's signature glowing cyan visor."
                ),
                "modifiers": cw_mods,
                "tags": ["geppy", "geppy-civil-war-costume", "sot-variant", "civil-war-costume", "claymation", "vinyl-toy", "character"]
            }, db)
        else:
            cw_m = dict(cw_geppy_ctx.modifiers or {})
            if not cw_m.get("is_sot_variant") or cw_m.get("parent_sot_handle") != "geppy":
                cw_m["is_sot_variant"] = True
                cw_m["parent_sot_handle"] = "geppy"
                cw_m["parent_sot_title"] = "Geppy"
                cw_m["variant_label"] = cw_m.get("variant_label") or "Civil War Costume"
                cw_geppy_ctx.modifiers = cw_m
                db.commit()
        vs_geppy_ctx = db.query(ContextileModel).filter(ContextileModel.name == "vs-geppy").first()
        if not vs_geppy_ctx:
            SOTService.create_contextile({
                "name": "vs-geppy",
                "title": "Geppy Visual Style (@vsGeppy — Claymation & Designer Vinyl Aesthetic)",
                "description": "Extracted Visual Style Contextile for Geppy: applies Geppy's tactile stop-motion sculpted claymation & designer vinyl figure rendering style to ANY character, mascot, or object without copying Geppy's identity.",
                "archetype": "style",
                "entity_kind": "contextile",
                "reference_type": "hybrid" if geppy_sample_img else "text",
                "primary_image_url": geppy_sample_img,
                "reference_image_url": geppy_sample_img,
                "gallery_images": [geppy_sample_img] if geppy_sample_img else [],
                "reference_text": (
                    "Visual Style Extraction (@vsGeppy / @visGeppy): Hand-sculpted stop-motion polymer claymation blended with smooth satin-matte designer collectible vinyl art toy aesthetics — "
                    "featuring subtle artisan clay thumbprint micro-texture, rounded vinyl figure joints, glossy translucent acrylic visor/eye highlights, warm amber-gold (#F59E0B) and electric cyan (#06B6D4) rim lighting, and miniature diorama depth of field."
                ),
                "modifiers": {
                    "entity_kind": "contextile",
                    "style": ["Aardman Stop-Motion Sculpted Claymation", "Claymation / Aardman Stop-Motion Puppet"],
                    "medium": ["ZBrush High-Poly Digital Clay Sculpt", "8K Octane / Redshift Ray-Traced 3D Render"],
                    "materials": ["Soft Vinyl Designer Toy (Bearbrick / Funko)", "Frosted Translucent Acrylic & Glass", "Polished 24K Gold & Chrome Bevels"],
                    "lighting": ["Volumetric God Rays & Atmospheric Rim Glow", "Dual-Tone Neon Cyan & Magenta Edge Lighting"],
                    "color_grading": ["Geppy Signature (Amber Gold #F59E0B, Cyan #06B6D4 & Obsidian)"],
                    "camera_lens": ["Tilt-Shift Miniature Toy-World Focus", "85mm f/1.4 Prime Portrait Lens (Creamy Bokeh)"],
                    "option_toggles": [
                        {
                            "key": "clay_thumbprint_microtexture",
                            "label": "Tactile hand-sculpted polymer clay thumbprint micro-texture",
                            "prompt": "with authentic hand-sculpted stop-motion polymer clay surface showing subtle artisan thumbprint micro-textures",
                            "enabled": True
                        },
                        {
                            "key": "designer_vinyl_finish",
                            "label": "Smooth satin-matte designer vinyl collectible toy finish & joints",
                            "prompt": "crafted with smooth satin-matte designer collectible vinyl toy surfaces and rounded articulated figure bevels",
                            "enabled": True
                        },
                        {
                            "key": "q_style_chibi_mode",
                            "label": "Q-Style / Chibi 1:2.5 cute oversized head proportions (@qGeppy)",
                            "prompt": "proportioned in cute Q-Style 1:2.5 chibi collectible vinyl figure scale with an oversized expressive head and compact body",
                            "enabled": False
                        }
                    ]
                },
                "tags": ["contextile", "visual-style", "vsGeppy", "visGeppy", "claymation", "vinyl-toy", "extraction-style"]
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

        # Seed Dynamic Template Variables, Variable Dropdowns & Option Toggles for '70s Baseball Card Contextile Template
        baseball_card = db.query(ContextileModel).filter(ContextileModel.name == "70s-baseball-card").first()
        if baseball_card:
            changed = False
            cur_vars = list(baseball_card.variables or [])
            has_dropdown_vars = any(isinstance(v, dict) and v.get("type") == "dropdown" for v in cur_vars)
            if not cur_vars or not has_dropdown_vars:
                base_text_vars = [
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
                dropdown_vars = [
                    {
                        "key": "card_style_variant",
                        "label": "🎨 Card Style Variant",
                        "type": "dropdown",
                        "category_preset": "style",
                        "default_value": "1970s Topps Vintage Baseball Trading Card",
                        "value": "1970s Topps Vintage Baseball Trading Card",
                        "options": EXTENSIVE_VARIABLE_DROPDOWNS["style"]["options"],
                        "description": "Choose the artistic style or card era treatment"
                    },
                    {
                        "key": "print_medium",
                        "label": "🖌️ Print Stock & Medium",
                        "type": "dropdown",
                        "category_preset": "medium",
                        "default_value": "Offset Lithography on Aged Matte Cardboard Stock",
                        "value": "Offset Lithography on Aged Matte Cardboard Stock",
                        "options": EXTENSIVE_VARIABLE_DROPDOWNS["medium"]["options"],
                        "description": "Choose cardboard print stock, foil finish, or rendering medium"
                    },
                    {
                        "key": "lighting_setup",
                        "label": "💡 Photography Lighting",
                        "type": "dropdown",
                        "category_preset": "lighting",
                        "default_value": "Vintage 1970s On-Camera Direct Flashbulb",
                        "value": "Vintage 1970s On-Camera Direct Flashbulb",
                        "options": EXTENSIVE_VARIABLE_DROPDOWNS["lighting"]["options"],
                        "description": "Studio flash, golden hour stadium sun, or neon rim lighting"
                    },
                    {
                        "key": "color_grade",
                        "label": "🌈 Film Color Grading",
                        "type": "dropdown",
                        "category_preset": "color_grading",
                        "default_value": "Kodachrome 1970s Warm Nostalgic Vintage Grade",
                        "value": "Kodachrome 1970s Warm Nostalgic Vintage Grade",
                        "options": EXTENSIVE_VARIABLE_DROPDOWNS["color_grading"]["options"],
                        "description": "Color palette and film stock grading"
                    }
                ]
                baseball_card.variables = base_text_vars + dropdown_vars
                changed = True
            mods = dict(baseball_card.modifiers or {})
            if mods.get("entity_kind") != "contextile" or not mods.get("option_toggles"):
                mods["entity_kind"] = "contextile"
                mods["option_toggles"] = [
                    {
                        "key": "funny_mustache",
                        "label": "Put a funny 1970s handlebar mustache on the person",
                        "prompt": "wearing a hilarious oversized 1970s retro handlebar mustache on their face",
                        "enabled": False
                    },
                    {
                        "key": "retro_aviators",
                        "label": "Add 1970s tinted sports aviator sunglasses",
                        "prompt": "wearing vintage 1970s amber-tinted sports aviator sunglasses",
                        "enabled": False
                    },
                    {
                        "key": "arched_banner_star",
                        "label": "Classic arched team header & corner position star badge",
                        "prompt": "framed with an arched vintage team banner across the top and a round corner star position badge",
                        "enabled": True
                    },
                    {
                        "key": "aged_cardboard_gum",
                        "label": "Worn cardboard corners & subtle bubblegum wrapper crease",
                        "prompt": "printed on aged matte cardboard stock with worn corners, offset halftone print dots, and subtle vintage crease texture",
                        "enabled": True
                    }
                ]
                baseball_card.modifiers = mods
                changed = True
            if changed:
                db.commit()

        # Seed a Specific Place Source of Truth (@blackwood-manor) + a Scene Contextile Template (@blackwood-horror-movie) that embeds that Place SOT
        place_sot = db.query(ContextileModel).filter(ContextileModel.name == "blackwood-manor").first()
        if not place_sot:
            SOTService.create_contextile({
                "name": "blackwood-manor",
                "title": "Blackwood Victorian Manor (Specific Place SOT)",
                "description": "Unchanging Source of Truth for a specific place: the grand two-story Gothic Victorian manor house with wraparound porch, wrought-iron gates, turret tower, and stone gargoyle steps.",
                "archetype": "place",
                "entity_kind": "sot",
                "reference_type": "text",
                "reference_text": "Specific Unchanging Place: The Old Blackwood Victorian Manor — an unmistakable three-story 1890s Second-Empire Victorian mansion with an octagonal corner turret, weathered slate mansard roof, wraparound timber porch, twin stone gargoyles flanking the front staircase, and twisted oak trees along the wrought-iron fence.",
                "modifiers": {
                    "entity_kind": "sot",
                    "lighting": ["Moody Deep-Space Starlight & Nebula Backlight"],
                    "theme": ["Minimalist Luxury Dark"],
                    "era": ["1890s Victorian Gothic & Gaslight Mansion Era"],
                    "medium": ["Anamorphic 35mm Panavision Motion Picture Film"],
                    "materials": ["Weathered 1890s Victorian Timber & Mansard Slate"]
                },
                "tags": ["sot", "place", "location", "manor", "ground-truth"]
            }, db)

        horror_vars = [
            {
                "key": "style_genre",
                "label": "🎨 Cinema / Artistic Style",
                "type": "dropdown",
                "category_preset": "style",
                "default_value": "1980s John Carpenter Atmospheric Horror",
                "value": "1980s John Carpenter Atmospheric Horror",
                "options": EXTENSIVE_VARIABLE_DROPDOWNS["style"]["options"],
                "description": "Switch the directorial style while keeping @blackwood-manor locked"
            },
            {
                "key": "render_medium",
                "label": "🖌️ Film / Render Medium",
                "type": "dropdown",
                "category_preset": "medium",
                "default_value": "Anamorphic 35mm Panavision Motion Picture Film",
                "value": "Anamorphic 35mm Panavision Motion Picture Film",
                "options": EXTENSIVE_VARIABLE_DROPDOWNS["medium"]["options"],
                "description": "Choose film gauge, VHS tape, 3D engine, or illustration medium"
            },
            {
                "key": "lighting_rig",
                "label": "💡 Lighting & Illumination",
                "type": "dropdown",
                "category_preset": "lighting",
                "default_value": "Cold Cyan-Blue Full Moonlight & Volumetric Fog Shafts",
                "value": "Cold Cyan-Blue Full Moonlight & Volumetric Fog Shafts",
                "options": EXTENSIVE_VARIABLE_DROPDOWNS["lighting"]["options"],
                "description": "Choose moonlight, lantern glow, lightning silhouette, or studio rig"
            },
            {
                "key": "camera_framing",
                "label": "📷 Camera Angle & Lens",
                "type": "dropdown",
                "category_preset": "camera_lens",
                "default_value": "35mm f/1.4 Anamorphic Cinema Wide",
                "value": "35mm f/1.4 Anamorphic Cinema Wide",
                "options": EXTENSIVE_VARIABLE_DROPDOWNS["camera_lens"]["options"],
                "description": "Choose camera focal length and shot angle"
            },
            {
                "key": "mood_weather",
                "label": "🌫️ Mood & Weather Atmosphere",
                "type": "dropdown",
                "category_preset": "mood_atmosphere",
                "default_value": "Eerie 1980s Horror with Thick Rolling Ground Fog",
                "value": "Eerie 1980s Horror with Thick Rolling Ground Fog",
                "options": EXTENSIVE_VARIABLE_DROPDOWNS["mood_atmosphere"]["options"],
                "description": "Choose atmospheric weather and emotional tone"
            },
            {
                "key": "color_grading",
                "label": "🌈 Color Grading & Palette",
                "type": "dropdown",
                "category_preset": "color_grading",
                "default_value": "Gothic Horror Cold Moonlight Cyan-Blue & Blood Crimson",
                "value": "Gothic Horror Cold Moonlight Cyan-Blue & Blood Crimson",
                "options": EXTENSIVE_VARIABLE_DROPDOWNS["color_grading"]["options"],
                "description": "Choose film color LUT or palette harmony"
            },
            {
                "key": "movie_tagline",
                "label": "🎬 Scene Tagline / Cue",
                "default_value": "Don't go up the manor steps alone...",
                "value": "Don't go up the manor steps alone...",
                "type": "text",
                "description": "Optional atmospheric cue or poster tagline"
            }
        ]

        horror_ctx = db.query(ContextileModel).filter(ContextileModel.name == "blackwood-horror-movie").first()
        if not horror_ctx:
            SOTService.create_contextile({
                "name": "blackwood-horror-movie",
                "title": "Horror Movie at Blackwood Manor (Place + Style Contextile)",
                "description": "Contextile Template that embeds @blackwood-manor as the unchanging Place Source of Truth and provides extensive variable dropdowns for Style, Medium, Lighting, Camera, Mood, and Color Grading. Drop in any Character SOT (e.g. @jon or @captain-geppy).",
                "archetype": "scene_template",
                "entity_kind": "contextile",
                "reference_type": "text",
                "reference_text": "1980s John Carpenter / A24 atmospheric horror cinema template set at @blackwood-manor: eerie volumetric blue moonlight cutting through rolling ground fog, warm flickering amber lantern in the manor turret window, high-contrast chiaroscuro shadows, and 35mm Panavision anamorphic film grain.",
                "modifiers": {
                    "entity_kind": "contextile",
                    "embedded_sot_handles": ["blackwood-manor"],
                    "lighting": ["Dramatic Chiaroscuro / Rembrandt Single Key Light", "Cold Cyan-Blue Full Moonlight & Volumetric Fog Shafts"],
                    "theme": ["1980s Gothic Horror Cinema"],
                    "era": ["1980s VHS Horror, Synthwave & Arcade Era"],
                    "medium": ["Anamorphic 35mm Panavision Motion Picture Film"],
                    "materials": ["Weathered 1890s Victorian Timber & Mansard Slate"],
                    "option_toggles": [
                        {
                            "key": "rolling_ground_fog",
                            "label": "Thick eerie ground fog & blue moonlight beams",
                            "prompt": "surrounded by thick swirling ground fog illuminated by cold cyan-blue moonlight shafts",
                            "enabled": True
                        },
                        {
                            "key": "flashlight_beam",
                            "label": "Character holding a glowing vintage flashlight cutting through the dark",
                            "prompt": "holding a heavy vintage chrome flashlight casting a sharp volumetric cone of light into the darkness",
                            "enabled": True
                        },
                        {
                            "key": "lightning_strike",
                            "label": "Dramatic forked lightning strike behind the manor turret",
                            "prompt": "with a dramatic bolt of forked white-violet lightning illuminating the sky behind the manor turret",
                            "enabled": False
                        },
                        {
                            "key": "vhs_horror_grain",
                            "label": "1980s VHS tape tracking lines & retro horror title aesthetic",
                            "prompt": "with subtle 1980s analog VHS film grain, halation glow, and retro horror poster color grading",
                            "enabled": False
                        }
                    ]
                },
                "variables": horror_vars,
                "tags": ["contextile", "scene-template", "horror-movie", "blackwood-manor", "embedded-sot"]
            }, db)
        else:
            cur_h_vars = list(horror_ctx.variables or [])
            if not any(isinstance(v, dict) and v.get("type") == "dropdown" for v in cur_h_vars):
                horror_ctx.variables = horror_vars
                db.commit()

        # --- Seed Default CONTEXTILES OF TRUTH (Physical Blanks) & Paired Fabrication Contextiles ---
        wood_blank = db.query(ContextileModel).filter(ContextileModel.name == "wood-plaque-blank").first()
        if not wood_blank:
            SOTService.analyze_blank_image_and_build_template(
                image_url=None,
                concept="6x4 inch Natural Basswood Laser & Stencil Plaque Blank",
                width_in=6.0,
                height_in=4.0,
                safe_margin_in=0.25,
                shape="rounded_rect",
                material="natural_wood",
                fabrication_mode="laser_bw",
                save_immediately=True,
                db=db,
                handle_override="wood-plaque-blank",
                paired_contextile_handles=["laser-engrave-bw-burn", "stencil-edge-connections"]
            )

        slate_blank = db.query(ContextileModel).filter(ContextileModel.name == "slate-coaster-blank").first()
        if not slate_blank:
            SOTService.analyze_blank_image_and_build_template(
                image_url=None,
                concept="4x4 inch Round Black Slate Coaster Laser Blank",
                width_in=4.0,
                height_in=4.0,
                safe_margin_in=0.25,
                shape="circle",
                material="black_slate",
                fabrication_mode="laser_bw",
                save_immediately=True,
                db=db,
                handle_override="slate-coaster-blank",
                paired_contextile_handles=["laser-engrave-bw-burn"]
            )

        stencil_ctx = db.query(ContextileModel).filter(ContextileModel.name == "stencil-edge-connections").first()
        if not stencil_ctx:
            SOTService.create_contextile({
                "name": "stencil-edge-connections",
                "title": "Cut Stencil with Edge Connections (Bridged Islands)",
                "description": "Reusable Fabrication Contextile Template that converts any SOT Character, Logo, or Subject into a cuttable stencil or vinyl graphic with structural edge bridges connecting all inner islands so nothing falls out.",
                "archetype": "style",
                "entity_kind": "contextile",
                "reference_type": "text",
                "reference_text": "Cuttable Stencil with Edge Connections Contextile: Bold high-contrast monochrome cutout graphic where every enclosed interior island (eyes, letter loops, floating details) is structurally connected to the outer frame via sturdy stencil bridges / edge connections so no pieces fall out when laser-cut or vinyl-cut.",
                "modifiers": {
                    "entity_kind": "contextile",
                    "fabrication_mode": ["Cut Stencil with Edge Connections: Bold Cutout Shapes + Structural Bridges Holding All Inner Islands"],
                    "lighting": ["High-Contrast Rim Silhouette Only"],
                    "theme": ["Cuttable Stencil & Vinyl Fabrication"],
                    "medium": ["Clean Scalable Vector SVG Flat Illustration"],
                    "materials": ["Laser-Cut Basswood & Birch Plywood"],
                    "option_toggles": [
                        {
                            "key": "structural_edge_bridges",
                            "label": "Connect all interior islands to outer frame with sturdy stencil bridges",
                            "prompt": "with thick structural stencil bridges and edge connections tying every interior island and enclosed shape to the outer border so zero pieces fall out when cut",
                            "enabled": True
                        },
                        {
                            "key": "outer_frame_ring",
                            "label": "Include solid outer stencil frame ring around the design",
                            "prompt": "enclosed inside a solid cuttable outer stencil border frame that anchors all edge connection bridges",
                            "enabled": True
                        },
                        {
                            "key": "weed_ready_minimum_thickness",
                            "label": "Enforce minimum 2.5mm weed-ready bridge & line thickness for vinyl/laser",
                            "prompt": "with bold minimum 2.5mm line and bridge thickness eliminating fragile hairlines",
                            "enabled": True
                        }
                    ]
                },
                "variables": [
                    {
                        "key": "fabrication_mode_dropdown",
                        "label": "✂️ Stencil / Vinyl Cut Mode",
                        "type": "dropdown",
                        "category_preset": "fabrication_mode",
                        "default_value": EXTENSIVE_VARIABLE_DROPDOWNS["fabrication_mode"]["options"][3],
                        "value": EXTENSIVE_VARIABLE_DROPDOWNS["fabrication_mode"]["options"][3],
                        "options": EXTENSIVE_VARIABLE_DROPDOWNS["fabrication_mode"]["options"],
                        "description": "Select single-layer bridged stencil, multi-layer stencil, or vinyl plotter cut"
                    },
                    {
                        "key": "bridge_thickness",
                        "label": "🔗 Edge Connection Bridge Width",
                        "type": "dropdown",
                        "default_value": "3.0mm Heavy-Duty Laser & Craft Stencil Bridges",
                        "value": "3.0mm Heavy-Duty Laser & Craft Stencil Bridges",
                        "options": [
                            "2.0mm Fine Detail Vinyl Plotter Bridges",
                            "3.0mm Heavy-Duty Laser & Craft Stencil Bridges",
                            "4.5mm Industrial Spray-Paint Stencil Bridges",
                            "Radial Spoke Frame Edge Connections"
                        ],
                        "description": "Thickness of bridges connecting inner islands to the outer edge"
                    }
                ],
                "tags": ["contextile", "stencil", "edge-connections", "bridges", "vinyl-cut", "laser-cut"]
            }, db)

        laser_ctx = db.query(ContextileModel).filter(ContextileModel.name == "laser-engrave-bw-burn").first()
        if not laser_ctx:
            SOTService.create_contextile({
                "name": "laser-engrave-bw-burn",
                "title": "Laser Engraver Black & White Burn (1-Bit Pyrography)",
                "description": "Reusable Fabrication Contextile Template for CO2 & Diode Laser Engravers: forces pure high-contrast black and white output (#000000 = laser burn, #FFFFFF = unburned blank). Pair with any Blank Contextile of Truth!",
                "archetype": "style",
                "entity_kind": "contextile",
                "reference_type": "text",
                "reference_text": "Laser Engraver 1-Bit Black & White Burn Contextile: Pure monochrome black-and-white woodburn / engraving linework (#000000 = laser burned area, #FFFFFF = raw unburned blank). Zero color gradients, zero muddy gray wash; uses crisp woodblock linework and crosshatch shading optimized for laser burning.",
                "modifiers": {
                    "entity_kind": "contextile",
                    "fabrication_mode": ["Laser Engraver: High-Contrast 1-Bit Black & White Wood/Slate Burn (Black = Burn, White = Unburned Blank)"],
                    "lighting": ["High-Contrast Rim Silhouette Only"],
                    "theme": ["Laser Engraving & Woodburn Pyography"],
                    "medium": ["Pen, India Ink & Crosshatching on Bristol Board"],
                    "materials": ["Laser-Cut Basswood & Birch Plywood"],
                    "option_toggles": [
                        {
                            "key": "pure_1bit_bw",
                            "label": "Strict 1-Bit Black & White Only (Black = Laser Burn, White = Unburned)",
                            "prompt": "strictly 1-bit pure black (#000000) ink on pure white (#FFFFFF) background with zero color and zero gray wash",
                            "enabled": True
                        },
                        {
                            "key": "woodcut_crosshatch",
                            "label": "Engraver woodcut crosshatching for tonal depth without gray washes",
                            "prompt": "using crisp intaglio woodcut crosshatching and bold line weights to represent shading in pure black and white",
                            "enabled": True
                        },
                        {
                            "key": "invert_for_slate",
                            "label": "Invert for Dark Slate Coasters (Laser burns light onto dark stone)",
                            "prompt": "optimized with high-contrast inverted relief highlights for dark slate laser engraving",
                            "enabled": False
                        }
                    ]
                },
                "variables": [
                    {
                        "key": "fabrication_mode_dropdown",
                        "label": "🔥 Laser Burn Mode",
                        "type": "dropdown",
                        "category_preset": "fabrication_mode",
                        "default_value": EXTENSIVE_VARIABLE_DROPDOWNS["fabrication_mode"]["options"][0],
                        "value": EXTENSIVE_VARIABLE_DROPDOWNS["fabrication_mode"]["options"][0],
                        "options": EXTENSIVE_VARIABLE_DROPDOWNS["fabrication_mode"]["options"],
                        "description": "1-Bit B&W Line Burn, Halftone Dither Burn, or 8-Bit Grayscale Relief"
                    }
                ],
                "tags": ["contextile", "laser-engraver", "black-and-white", "woodburn", "1-bit-bw"]
            }, db)

    @classmethod
    def suggest_variables_for_concept(cls, concept: str = "", archetype: str = "character", reference_text: str = "") -> List[Dict[str, Any]]:
        """
        Suggest variable slots — including extensive dropdowns for Fabrication Mode, Style, Medium, Lighting, Camera/Lens, Materials, Color Grading, Mood, Era, and Framing — based on contextile concept, archetype, or reference text.
        """
        low = (concept + " " + archetype + " " + reference_text).lower()
        fab_dropdown = {
            "key": "fabrication_mode_dropdown",
            "label": "🔥 Physical Fabrication & Blank Output Mode",
            "type": "dropdown",
            "category_preset": "fabrication_mode",
            "default_value": EXTENSIVE_VARIABLE_DROPDOWNS["fabrication_mode"]["options"][0],
            "value": EXTENSIVE_VARIABLE_DROPDOWNS["fabrication_mode"]["options"][0],
            "options": EXTENSIVE_VARIABLE_DROPDOWNS["fabrication_mode"]["options"],
            "description": "Extensive physical fabrication constraint dropdown (Laser B&W Burn, Bridged Stencil, Vinyl Cut, Sublimation)"
        }
        core_dropdowns = [
            {
                "key": "style_dropdown",
                "label": "🎨 Artistic Style",
                "type": "dropdown",
                "category_preset": "style",
                "default_value": EXTENSIVE_VARIABLE_DROPDOWNS["style"]["options"][0],
                "value": EXTENSIVE_VARIABLE_DROPDOWNS["style"]["options"][0],
                "options": EXTENSIVE_VARIABLE_DROPDOWNS["style"]["options"],
                "description": "Extensive style dropdown (38 styles)"
            },
            {
                "key": "medium_dropdown",
                "label": "🖌️ Rendering Medium",
                "type": "dropdown",
                "category_preset": "medium",
                "default_value": EXTENSIVE_VARIABLE_DROPDOWNS["medium"]["options"][0],
                "value": EXTENSIVE_VARIABLE_DROPDOWNS["medium"]["options"][0],
                "options": EXTENSIVE_VARIABLE_DROPDOWNS["medium"]["options"],
                "description": "Extensive rendering medium & print stock dropdown (32 mediums)"
            },
            {
                "key": "lighting_dropdown",
                "label": "💡 Lighting Rig",
                "type": "dropdown",
                "category_preset": "lighting",
                "default_value": EXTENSIVE_VARIABLE_DROPDOWNS["lighting"]["options"][0],
                "value": EXTENSIVE_VARIABLE_DROPDOWNS["lighting"]["options"][0],
                "options": EXTENSIVE_VARIABLE_DROPDOWNS["lighting"]["options"],
                "description": "Extensive lighting & illumination dropdown (28 setups)"
            },
            {
                "key": "camera_lens_dropdown",
                "label": "📷 Camera Angle & Lens",
                "type": "dropdown",
                "category_preset": "camera_lens",
                "default_value": EXTENSIVE_VARIABLE_DROPDOWNS["camera_lens"]["options"][0],
                "value": EXTENSIVE_VARIABLE_DROPDOWNS["camera_lens"]["options"][0],
                "options": EXTENSIVE_VARIABLE_DROPDOWNS["camera_lens"]["options"],
                "description": "Extensive camera framing & lens focal length dropdown (25 options)"
            },
            {
                "key": "materials_dropdown",
                "label": "💎 Surface Materials",
                "type": "dropdown",
                "category_preset": "materials",
                "default_value": EXTENSIVE_VARIABLE_DROPDOWNS["materials"]["options"][0],
                "value": EXTENSIVE_VARIABLE_DROPDOWNS["materials"]["options"][0],
                "options": EXTENSIVE_VARIABLE_DROPDOWNS["materials"]["options"],
                "description": "Extensive physical materials & shaders dropdown (24 options)"
            },
            {
                "key": "color_grading_dropdown",
                "label": "🌈 Color Grading & Palette",
                "type": "dropdown",
                "category_preset": "color_grading",
                "default_value": EXTENSIVE_VARIABLE_DROPDOWNS["color_grading"]["options"][0],
                "value": EXTENSIVE_VARIABLE_DROPDOWNS["color_grading"]["options"][0],
                "options": EXTENSIVE_VARIABLE_DROPDOWNS["color_grading"]["options"],
                "description": "Extensive film color grading & palette harmony dropdown (22 options)"
            },
            {
                "key": "mood_atmosphere_dropdown",
                "label": "🌫️ Mood & Weather Atmosphere",
                "type": "dropdown",
                "category_preset": "mood_atmosphere",
                "default_value": EXTENSIVE_VARIABLE_DROPDOWNS["mood_atmosphere"]["options"][0],
                "value": EXTENSIVE_VARIABLE_DROPDOWNS["mood_atmosphere"]["options"][0],
                "options": EXTENSIVE_VARIABLE_DROPDOWNS["mood_atmosphere"]["options"],
                "description": "Extensive mood & weather effects dropdown (18 options)"
            },
            {
                "key": "framing_border_dropdown",
                "label": "🖼️ Frame & Container Border",
                "type": "dropdown",
                "category_preset": "framing_border",
                "default_value": EXTENSIVE_VARIABLE_DROPDOWNS["framing_border"]["options"][0],
                "value": EXTENSIVE_VARIABLE_DROPDOWNS["framing_border"]["options"][0],
                "options": EXTENSIVE_VARIABLE_DROPDOWNS["framing_border"]["options"],
                "description": "Extensive border & container framing dropdown (16 options)"
            },
            fab_dropdown
        ]

        if archetype == "blank_substrate" or any(k in low for k in ["blank", "laser", "stencil", "vinyl", "sublimat", "coaster", "plaque"]):
            return [fab_dropdown, core_dropdowns[0], core_dropdowns[1], core_dropdowns[7]]
        elif "baseball" in low or "card" in low or "trading" in low:
            return [
                {"key": "team_name", "label": "Team Name", "default_value": "GEPPY'S GALACTIC ALL-STARS", "value": "GEPPY'S GALACTIC ALL-STARS", "type": "text", "description": "Team banner text at top"},
                {"key": "player_name", "label": "Player Name", "default_value": "CAPTAIN GEPPY", "value": "CAPTAIN GEPPY", "type": "text", "description": "Player name banner at bottom"},
                {"key": "position", "label": "Player Position", "default_value": "CAPTAIN", "value": "CAPTAIN", "type": "text", "description": "Position star badge"},
                {"key": "stats", "label": "Stats Summary", "default_value": "STARFLEET PILOT • .342 AVG • 48 HR • SOT ALL-GALAXY", "value": "STARFLEET PILOT • .342 AVG • 48 HR • SOT ALL-GALAXY", "type": "text", "description": "Season or career stat line"},
                {"key": "card_number", "label": "Card Number", "default_value": "#76", "value": "#76", "type": "text", "description": "Collector series card number"},
                {"key": "year_era", "label": "Year / Era", "default_value": "'76", "value": "'76", "type": "text", "description": "Vintage year stamp"}
            ] + core_dropdowns[:4]
        elif archetype == "scene_template" or "horror" in low or "movie" in low or "scene" in low:
            return core_dropdowns[:8] + [
                {"key": "movie_tagline", "label": "🎬 Scene Tagline / Cue", "default_value": "Don't go up the manor steps alone...", "value": "Don't go up the manor steps alone...", "type": "text", "description": "Atmospheric cue or poster tagline"}
            ]
        elif archetype == "character" or "mascot" in low or "hero" in low:
            return [
                {"key": "character_name", "label": "Character Name", "default_value": "Captain Geppy", "value": "Captain Geppy", "type": "text", "description": "Primary identity name"},
                {"key": "role_title", "label": "Rank / Class", "default_value": "Galactic Commander", "value": "Galactic Commander", "type": "text", "description": "Official title or combat class"},
                {"key": "special_gear", "label": "Signature Gear", "default_value": "Translucent Cyan Visor & Obsidian Armor", "value": "Translucent Cyan Visor & Obsidian Armor", "type": "text", "description": "Key equipment slot"}
            ] + core_dropdowns[:4]
        elif archetype == "icon_set" or "icon" in low or "app" in low:
            return [
                {"key": "app_title", "label": "App Title", "default_value": "Geppy's Galactic", "value": "Geppy's Galactic", "type": "text", "description": "Application or module name"},
                {"key": "glyph_symbol", "label": "Glyph Motif", "default_value": "Orbital Warp Ring", "value": "Orbital Warp Ring", "type": "text", "description": "Central 3D icon element"}
            ] + core_dropdowns[:5]
        else:
            return core_dropdowns

