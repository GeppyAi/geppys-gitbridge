"""
Output Contextile & Finishing Service
Handles background removal, die-cut sticker contour rims,
high-DPI upscaling, print-ready layout generation with bleed and crop marks,
and 300 DPI print-ready PDF export.
"""

import os
import math
import time
import uuid
from typing import Dict, Any, Optional, Tuple, List
from PIL import Image, ImageDraw, ImageFont, ImageFilter

class OutputService:
    @staticmethod
    def _get_exports_dir() -> str:
        """Returns directory where exported PNGs and PDFs are stored."""
        from gitbridge.services.asset_lab_service import AssetLabService
        exports_dir = os.path.join(AssetLabService._get_lab_dir(), "exports")
        os.makedirs(exports_dir, exist_ok=True)
        return exports_dir

    @staticmethod
    def hex_to_rgb(hex_str: str) -> Tuple[int, int, int]:
        """Convert hex color string (#FFFFFF or FFFFFF) to RGB tuple."""
        clean = hex_str.lstrip("#")
        if len(clean) == 3:
            clean = "".join([c*2 for c in clean])
        if len(clean) >= 6:
            return (int(clean[0:2], 16), int(clean[2:4], 16), int(clean[4:6], 16))
        return (255, 255, 255)

    @classmethod
    def remove_background(
        cls,
        image: Image.Image,
        tolerance: int = 35,
        edge_feather: int = 2,
        sample_corners: bool = True,
        target_bg_color: Optional[Tuple[int, int, int]] = None,
        edge_margin_step: int = 20
    ) -> Image.Image:
        """
        Removes background from image using perimeter-connected flood fill & color distance thresholding,
        producing a clean alpha mask with antialiased edge feathering.
        """
        im = image.convert("RGB")
        w, h = im.size

        # Determine target background color if not explicitly provided
        if target_bg_color is None and sample_corners:
            # Sample four corners
            corners = [
                im.getpixel((0, 0)),
                im.getpixel((w - 1, 0)),
                im.getpixel((0, h - 1)),
                im.getpixel((w - 1, h - 1)),
                im.getpixel((w // 2, 0)),
                im.getpixel((w // 2, h - 1))
            ]
            # Average sample
            avg_r = sum(c[0] for c in corners) // len(corners)
            avg_g = sum(c[1] for c in corners) // len(corners)
            avg_b = sum(c[2] for c in corners) // len(corners)
            target_bg_color = (avg_r, avg_g, avg_b)
        elif target_bg_color is None:
            target_bg_color = (15, 23, 42) # Default dark slate

        # Create working copy to flood fill background markers
        work_im = im.copy()
        marker_color = (254, 0, 253) # Highly unique magenta marker

        # Flood fill from perimeter coordinates to only remove outer background
        step = max(10, edge_margin_step)
        for x in [0, w - 1]:
            for y in range(0, h, step):
                try:
                    ImageDraw.floodfill(work_im, (x, y), marker_color, thresh=tolerance)
                except Exception:
                    pass
        for y in [0, h - 1]:
            for x in range(0, w, step):
                try:
                    ImageDraw.floodfill(work_im, (x, y), marker_color, thresh=tolerance)
                except Exception:
                    pass

        # Build alpha mask based on marker color
        work_rgb = work_im.convert("RGB")
        alpha = Image.new("L", (w, h), 255)
        
        # Fast pixel comparison
        work_bytes = bytearray(work_rgb.tobytes())
        alpha_bytes = bytearray(w * h)
        m_r, m_g, m_b = marker_color

        for idx in range(w * h):
            r = work_bytes[idx * 3]
            g = work_bytes[idx * 3 + 1]
            b = work_bytes[idx * 3 + 2]
            if r == m_r and g == m_g and b == m_b:
                alpha_bytes[idx] = 0
            else:
                alpha_bytes[idx] = 255

        alpha = Image.frombytes("L", (w, h), bytes(alpha_bytes))

        # Apply feathering for silky edges
        if edge_feather > 0:
            alpha = alpha.filter(ImageFilter.GaussianBlur(edge_feather))

        result = im.convert("RGBA")
        result.putalpha(alpha)
        return result

    @classmethod
    def apply_diecut_stroke(
        cls,
        image: Image.Image,
        stroke_width: int = 16,
        stroke_color: Tuple[int, int, int, int] = (255, 255, 255, 255),
        add_shadow: bool = True
    ) -> Image.Image:
        """
        Adds a smooth, uniform vinyl sticker die-cut outer rim (contour) around transparent cutout.
        """
        rgba = image.convert("RGBA")
        w, h = rgba.size
        
        # Add padding so stroke does not clip at borders
        pad = stroke_width * 2 + 10
        canvas_w = w + pad * 2
        canvas_h = h + pad * 2

        alpha = rgba.getchannel("A")
        padded_alpha = Image.new("L", (canvas_w, canvas_h), 0)
        padded_alpha.paste(alpha, (pad, pad))

        # Binary threshold mask
        bin_mask = padded_alpha.point(lambda p: 255 if p > 40 else 0)

        # Dilate mask using MaxFilter
        filter_size = max(3, stroke_width * 2 + 1)
        dilated = bin_mask.filter(ImageFilter.MaxFilter(filter_size))
        
        # Smooth the contour corners with slight blur then threshold
        smooth_rim = dilated.filter(ImageFilter.GaussianBlur(2.0)).point(lambda p: 255 if p > 100 else 0)

        canvas = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))

        # Optional soft drop shadow for realistic sticker preview
        if add_shadow:
            shadow_mask = smooth_rim.filter(ImageFilter.GaussianBlur(6.0))
            shadow_layer = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 70))
            canvas.paste(shadow_layer, (4, 6), shadow_mask)

        # Die-cut white vinyl border layer
        rim_layer = Image.new("RGBA", (canvas_w, canvas_h), stroke_color)
        canvas.paste(rim_layer, (0, 0), smooth_rim)

        # Paste original artwork cleanly centered on top
        canvas.paste(rgba, (pad, pad), rgba)

        # Crop transparent margins back to snug bounding box with padding
        bbox = canvas.getbbox()
        if bbox:
            crop_pad = 8
            x0 = max(0, bbox[0] - crop_pad)
            y0 = max(0, bbox[1] - crop_pad)
            x1 = min(canvas_w, bbox[2] + crop_pad)
            y1 = min(canvas_h, bbox[3] + crop_pad)
            canvas = canvas.crop((x0, y0, x1, y1))

        return canvas

    @classmethod
    def apply_chat_sticker_format(
        cls,
        image: Image.Image,
        size: int = 512,
        add_white_rim: bool = True
    ) -> Image.Image:
        """
        Formats asset as a standard 512x512 transparent chat sticker (Discord / Slack / Telegram),
        optionally applying a clean 6px sticker rim so it pops on dark or light themes.
        """
        im = image.convert("RGBA")
        if add_white_rim:
            im = cls.apply_diecut_stroke(im, stroke_width=8, stroke_color=(255, 255, 255, 255), add_shadow=False)

        # Resize to fit within 512x512 while maintaining aspect ratio
        max_dim = size - 16
        im.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)

        canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        ox = (size - im.width) // 2
        oy = (size - im.height) // 2
        canvas.paste(im, (ox, oy), im)
        return canvas

    @classmethod
    def render_print_layout(
        cls,
        image: Image.Image,
        width_in: float = 3.0,
        height_in: float = 3.0,
        dpi: int = 300,
        bleed_in: float = 0.125,
        show_crop_marks: bool = True,
        show_cut_line: bool = False,
        fill_bleed: bool = False,
        bg_color: Optional[Tuple[int, int, int]] = (255, 255, 255),
        job_title: str = "Geppy's Galactic Print Asset"
    ) -> Image.Image:
        """
        Renders print-ready artboard with exact dimensions, 300 DPI resolution,
        0.125" bleed, printer's crop crosshairs, registration bullseyes, CMYK calibration boxes,
        and technical printer slug line.
        """
        trim_w = int(width_in * dpi)
        trim_h = int(height_in * dpi)
        bleed_px = int(bleed_in * dpi)
        slug_px = int(0.25 * dpi) if show_crop_marks else 0

        total_w = trim_w + 2 * (bleed_px + slug_px)
        total_h = trim_h + 2 * (bleed_px + slug_px)

        sheet = Image.new("RGB", (total_w, total_h), bg_color or (255, 255, 255))
        draw = ImageDraw.Draw(sheet)

        tx0 = slug_px + bleed_px
        ty0 = slug_px + bleed_px
        tx1 = tx0 + trim_w
        ty1 = ty0 + trim_h

        # Scale artwork to fit either full bleed or snug inside trim area
        target_w = trim_w + 2 * bleed_px if fill_bleed else trim_w
        target_h = trim_h + 2 * bleed_px if fill_bleed else trim_h

        art = image.copy()
        art.thumbnail((target_w, target_h), Image.Resampling.LANCZOS)

        ax = tx0 - (bleed_px if fill_bleed else 0) + (target_w - art.width) // 2
        ay = ty0 - (bleed_px if fill_bleed else 0) + (target_h - art.height) // 2

        if art.mode == "RGBA":
            sheet.paste(art, (ax, ay), art)
        else:
            sheet.paste(art, (ax, ay))

        # Show optional die-cut kiss-cut registration contour (dashed magenta line)
        if show_cut_line:
            # Draw subtle dashed cut guideline around trim
            c_magenta = (236, 72, 153)
            dash_len = 8
            for x in range(tx0, tx1, dash_len * 2):
                draw.line([(x, ty0), (min(x + dash_len, tx1), ty0)], fill=c_magenta, width=1)
                draw.line([(x, ty1), (min(x + dash_len, tx1), ty1)], fill=c_magenta, width=1)
            for y in range(ty0, ty1, dash_len * 2):
                draw.line([(tx0, y), (tx0, min(y + dash_len, ty1))], fill=c_magenta, width=1)
                draw.line([(tx1, y), (tx1, min(y + dash_len, ty1))], fill=c_magenta, width=1)

        # Draw Professional Printer Crop Marks & Slugs
        if show_crop_marks:
            c_len = int(0.14 * dpi)
            c_gap = int(0.04 * dpi)
            c_col = (20, 20, 20)

            # Top-left corner marks
            draw.line([(tx0 - c_gap - c_len, ty0), (tx0 - c_gap, ty0)], fill=c_col, width=2)
            draw.line([(tx0, ty0 - c_gap - c_len), (tx0, ty0 - c_gap)], fill=c_col, width=2)

            # Top-right corner marks
            draw.line([(tx1 + c_gap, ty0), (tx1 + c_gap + c_len, ty0)], fill=c_col, width=2)
            draw.line([(tx1, ty0 - c_gap - c_len), (tx1, ty0 - c_gap)], fill=c_col, width=2)

            # Bottom-left corner marks
            draw.line([(tx0 - c_gap - c_len, ty1), (tx0 - c_gap, ty1)], fill=c_col, width=2)
            draw.line([(tx0, ty1 + c_gap), (tx0, ty1 + c_gap + c_len)], fill=c_col, width=2)

            # Bottom-right corner marks
            draw.line([(tx1 + c_gap, ty1), (tx1 + c_gap + c_len, ty1)], fill=c_col, width=2)
            draw.line([(tx1, ty1 + c_gap), (tx1, ty1 + c_gap + c_len)], fill=c_col, width=2)

            # Center Registration Crosshairs / Target Bullseyes
            cx, cy_top = total_w // 2, slug_px // 2
            draw.ellipse([cx - 8, cy_top - 8, cx + 8, cy_top + 8], outline=c_col, width=1)
            draw.line([(cx - 12, cy_top), (cx + 12, cy_top)], fill=c_col, width=1)
            draw.line([(cx, cy_top - 12), (cx, cy_top + 12)], fill=c_col, width=1)

            # CMYK Color Density Swatches (Cyan, Magenta, Yellow, Key/Black, 50% Black)
            cmyk = [(6, 182, 212), (236, 72, 153), (234, 179, 8), (15, 23, 42), (148, 163, 184)]
            swatch_start_x = total_w - slug_px - (len(cmyk) * 16 + 20)
            swatch_y = slug_px // 3
            for i, col in enumerate(cmyk):
                sx = swatch_start_x + i * 16
                draw.rectangle([sx, swatch_y, sx + 12, swatch_y + 12], fill=col, outline=(200, 200, 200), width=1)

            # Technical Printer Slug Line
            font = ImageFont.load_default()
            date_str = time.strftime("%Y-%m-%d")
            slug_str = f"GEPPY'S GITBRIDGE PRINT STUDIO • {width_in:.2f}\" x {height_in:.2f}\" @ {dpi} DPI • BLEED {bleed_in:.3f}\" • [{job_title.upper()[:28]}] • {date_str}"
            draw.text((slug_px, total_h - slug_px + 8), slug_str, fill=(71, 85, 105), font=font)

        return sheet

    @classmethod
    def export_pdf(cls, image: Image.Image, output_path: str, dpi: int = 300) -> bool:
        """Saves image to high-resolution print-ready PDF."""
        try:
            im = image.convert("RGB")
            im.save(output_path, "PDF", resolution=float(dpi))
            return True
        except Exception as e:
            print(f"[OutputService] export_pdf failed: {e}")
            return False

    @classmethod
    def process_pipeline(
        cls,
        source_image_path: str,
        spec: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Executes complete finishing and output pipeline based on Output Contextile specification.
        Produces transparent PNG and 300 DPI Print-Ready PDF.
        """
        if not os.path.exists(source_image_path):
            raise FileNotFoundError(f"Source image not found: {source_image_path}")

        raw_im = Image.open(source_image_path)
        exports_dir = cls._get_exports_dir()
        export_id = f"export_{int(time.time())}_{uuid.uuid4().hex[:6]}"

        bg_mode = spec.get("background_mode", "preserve") # transparent, white_diecut, colored_border, solid, preserve
        bg_tolerance = int(spec.get("bg_tolerance", 35))
        edge_feather = int(spec.get("edge_feather", 2))
        diecut_stroke_width = int(spec.get("diecut_stroke_width", 16))
        stroke_color_hex = spec.get("diecut_stroke_color", "#FFFFFF")
        stroke_color = (*cls.hex_to_rgb(stroke_color_hex), 255)

        # 1. Background Treatment
        current_im = raw_im
        if bg_mode in ("transparent", "white_diecut", "colored_border"):
            # Remove background
            current_im = cls.remove_background(
                current_im,
                tolerance=bg_tolerance,
                edge_feather=edge_feather
            )

        if bg_mode in ("white_diecut", "colored_border"):
            # Add sticker outline
            current_im = cls.apply_diecut_stroke(
                current_im,
                stroke_width=diecut_stroke_width,
                stroke_color=stroke_color,
                add_shadow=True
            )
        elif bg_mode == "solid":
            solid_hex = spec.get("custom_bg_color", "#FFFFFF")
            solid_rgb = cls.hex_to_rgb(solid_hex)
            solid_bg = Image.new("RGBA", current_im.size, (*solid_rgb, 255))
            solid_bg.paste(current_im, (0, 0), current_im.convert("RGBA"))
            current_im = solid_bg

        # 2. Dimensions & Print Format Mapping
        preset = spec.get("print_size", "custom")
        preset_map = {
            "chat_sticker_512": {"w_in": 1.71, "h_in": 1.71, "dpi": 300, "bleed": 0.0, "chat": True},
            "diecut_sticker_2in": {"w_in": 2.0, "h_in": 2.0, "dpi": 300, "bleed": 0.125, "cut_line": True},
            "diecut_sticker_3in": {"w_in": 3.0, "h_in": 3.0, "dpi": 300, "bleed": 0.125, "cut_line": True},
            "diecut_sticker_4in": {"w_in": 4.0, "h_in": 4.0, "dpi": 300, "bleed": 0.125, "cut_line": True},
            "trading_card_print": {"w_in": 2.5, "h_in": 3.5, "dpi": 300, "bleed": 0.125, "fill_bleed": True},
            "art_print_5x7": {"w_in": 5.0, "h_in": 7.0, "dpi": 300, "bleed": 0.125},
            "art_print_8x10": {"w_in": 8.0, "h_in": 10.0, "dpi": 300, "bleed": 0.125},
            "poster_letter": {"w_in": 8.5, "h_in": 11.0, "dpi": 300, "bleed": 0.125}
        }

        cfg = preset_map.get(preset, {})
        w_in = float(spec.get("width_in") or cfg.get("w_in") or 3.0)
        h_in = float(spec.get("height_in") or cfg.get("h_in") or 3.0)
        dpi = int(spec.get("dpi") or cfg.get("dpi") or 300)
        bleed_in = float(spec.get("bleed_in") if "bleed_in" in spec else cfg.get("bleed", 0.125))
        show_crop = bool(spec.get("show_crop_marks", True))
        show_cut = bool(spec.get("show_cut_line", cfg.get("cut_line", False)))
        fill_bleed = bool(spec.get("fill_bleed", cfg.get("fill_bleed", False)))
        is_chat = cfg.get("chat", False)

        # 3. Render Formatted Output PNG
        if is_chat:
            final_png_im = cls.apply_chat_sticker_format(current_im, size=512, add_white_rim=(bg_mode != "white_diecut"))
        else:
            final_png_im = current_im

        png_filename = f"{export_id}.png"
        png_filepath = os.path.join(exports_dir, png_filename)
        final_png_im.save(png_filepath, "PNG", quality=95)
        png_url = f"/api/asset-lab/exports/{png_filename}"

        # 4. Generate Print-Ready PDF if requested or print preset selected
        generate_pdf = spec.get("export_pdf", True)
        pdf_url = None
        pdf_filename = None

        if generate_pdf:
            print_sheet = cls.render_print_layout(
                image=current_im,
                width_in=w_in,
                height_in=h_in,
                dpi=dpi,
                bleed_in=bleed_in,
                show_crop_marks=show_crop,
                show_cut_line=show_cut,
                fill_bleed=fill_bleed,
                job_title=spec.get("job_title", "Galactic Print Asset")
            )
            pdf_filename = f"{export_id}.pdf"
            pdf_filepath = os.path.join(exports_dir, pdf_filename)
            cls.export_pdf(print_sheet, pdf_filepath, dpi=dpi)
            pdf_url = f"/api/asset-lab/exports/{pdf_filename}"

        return {
            "id": export_id,
            "png_filename": png_filename,
            "png_url": png_url,
            "pdf_filename": pdf_filename,
            "pdf_url": pdf_url,
            "width_in": w_in,
            "height_in": h_in,
            "width_px": final_png_im.width,
            "height_px": final_png_im.height,
            "dpi": dpi,
            "bleed_in": bleed_in,
            "background_mode": bg_mode,
            "print_size_preset": preset,
            "file_size_png": os.path.getsize(png_filepath),
            "file_size_pdf": os.path.getsize(pdf_filepath) if pdf_filename and os.path.exists(pdf_filepath) else 0,
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
        }
