"""
Image Converter & HEIC/HEIF Processing Service for Geppy's GitBridge & Geppy's Galactic.
Automatically detects and converts Apple iPhone/iPad HEIC/HEIF photos to web-ready PNG, JPEG, and WebP.
Preserves EXIF orientation, alpha channels, and color fidelity.
"""

import os
import io
from typing import Optional, Tuple, Dict, Any, List, Union
from PIL import Image, ImageOps

# Register HEIF opener with Pillow safely
_HEIF_INITIALIZED = False

def init_heif_support() -> bool:
    global _HEIF_INITIALIZED
    if _HEIF_INITIALIZED:
        return True
    try:
        import pillow_heif
        pillow_heif.register_heif_opener()
        _HEIF_INITIALIZED = True
        return True
    except Exception as e:
        print(f"[ImageConverterService] Warning: Failed to register pillow_heif: {e}")
        return False

# Initialize on module import
init_heif_support()


class ImageConverterService:
    """High-performance image conversion and format normalization service."""

    HEIC_EXTENSIONS = {".heic", ".heif", ".hif", ".heics", ".heifs"}
    HEIC_BRANDS = {b"heic", b"heix", b"hevc", b"heim", b"heis", b"mif1", b"msf1", b"heif"}

    @classmethod
    def init_heif_support(cls) -> bool:
        """Initialize pillow-heif support if not already initialized."""
        return init_heif_support()

    @classmethod
    def is_heic(cls, filename: str = "", file_bytes: bytes = b"") -> bool:
        """
        Check whether an image is HEIC/HEIF either by filename extension or ISOBMFF magic bytes.
        """
        if filename:
            ext = os.path.splitext(filename)[1].lower()
            if ext in cls.HEIC_EXTENSIONS:
                return True

        if file_bytes and len(file_bytes) >= 12:
            if file_bytes[4:8] == b"ftyp":
                brand = file_bytes[8:12].lower()
                if brand in cls.HEIC_BRANDS:
                    return True
        return False

    @classmethod
    def convert_image(
        cls,
        input_data: Union[str, bytes, io.BytesIO],
        target_format: str = "png",
        quality: int = 95
    ) -> Tuple[bytes, str, str, int, int]:
        """
        Convert an image (HEIC, PNG, JPEG, WebP, etc.) to target format.
        Automatically applies EXIF orientation transpose.

        Returns: (output_bytes, extension_with_dot, mime_type, width, height)
        """
        init_heif_support()

        if isinstance(input_data, str):
            with open(input_data, "rb") as f:
                img_stream = io.BytesIO(f.read())
        elif isinstance(input_data, bytes):
            img_stream = io.BytesIO(input_data)
        else:
            img_stream = input_data

        with Image.open(img_stream) as img:
            # Correct EXIF rotation (iPhone portraits / landscape orientation)
            try:
                img = ImageOps.exif_transpose(img)
            except Exception:
                pass

            width, height = img.size
            target_fmt = target_format.lower().strip()
            out_buf = io.BytesIO()

            if target_fmt in ["jpg", "jpeg"]:
                # Convert to RGB (remove alpha channel if present)
                if img.mode in ("RGBA", "LA", "P"):
                    bg = Image.new("RGB", img.size, (255, 255, 255))
                    if img.mode == "P":
                        img = img.convert("RGBA")
                    bg.paste(img, mask=img.split()[-1] if "A" in img.getbands() else None)
                    save_img = bg
                else:
                    save_img = img.convert("RGB")

                save_img.save(out_buf, format="JPEG", quality=quality, optimize=True)
                ext = ".jpg"
                mime = "image/jpeg"

            elif target_fmt == "webp":
                if img.mode not in ("RGB", "RGBA"):
                    img = img.convert("RGBA")
                img.save(out_buf, format="WEBP", quality=quality)
                ext = ".webp"
                mime = "image/webp"

            else:  # Default to PNG
                if img.mode not in ("RGB", "RGBA"):
                    img = img.convert("RGBA")
                img.save(out_buf, format="PNG", optimize=True)
                ext = ".png"
                mime = "image/png"

            return out_buf.getvalue(), ext, mime, width, height

    @classmethod
    def save_and_convert_upload(
        cls,
        file_bytes: bytes,
        original_filename: str,
        target_dir: str,
        target_format: str = "png",
        force_convert_all: bool = False
    ) -> Dict[str, Any]:
        """
        Save an uploaded image file into target_dir.
        If the file is HEIC/HEIF (or force_convert_all is True), converts it to target_format (default PNG).
        """
        os.makedirs(target_dir, exist_ok=True)
        is_heic_img = cls.is_heic(filename=original_filename, file_bytes=file_bytes)

        base_clean = os.path.basename(original_filename).replace(" ", "_")
        name_root, orig_ext = os.path.splitext(base_clean)

        if is_heic_img or force_convert_all:
            # Convert to target format
            converted_bytes, new_ext, mime, w, h = cls.convert_image(
                file_bytes, target_format=target_format
            )
            final_filename = f"{name_root}{new_ext}"
            target_path = os.path.join(target_dir, final_filename)

            with open(target_path, "wb") as f:
                f.write(converted_bytes)

            return {
                "was_converted": True,
                "original_filename": original_filename,
                "original_format": orig_ext.lstrip(".").lower() or "heic",
                "filename": final_filename,
                "file_path": target_path,
                "format": target_format.lower(),
                "mime_type": mime,
                "width": w,
                "height": h,
                "original_size": len(file_bytes),
                "converted_size": len(converted_bytes),
                "ratio_percent": round((len(converted_bytes) / len(file_bytes)) * 100, 1) if file_bytes else 100
            }
        else:
            # Save original file as is
            target_path = os.path.join(target_dir, base_clean)
            with open(target_path, "wb") as f:
                f.write(file_bytes)

            w, h = 0, 0
            try:
                with Image.open(io.BytesIO(file_bytes)) as img:
                    w, h = img.size
            except Exception:
                pass

            return {
                "was_converted": False,
                "original_filename": original_filename,
                "original_format": orig_ext.lstrip(".").lower(),
                "filename": base_clean,
                "file_path": target_path,
                "format": orig_ext.lstrip(".").lower(),
                "mime_type": f"image/{orig_ext.lstrip('.').lower()}",
                "width": w,
                "height": h,
                "original_size": len(file_bytes),
                "converted_size": len(file_bytes),
                "ratio_percent": 100.0
            }
