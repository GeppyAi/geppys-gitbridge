import os
import re
import time
import zipfile
import shutil
from typing import List, Dict, Any, Optional
from PIL import Image
from sqlalchemy.orm import Session
from gitbridge.db.models import AppProfileModel, MediaAssetModel

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".svg", ".webp", ".ico", ".gif", ".heic", ".heif"}
IGNORED_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", "dist", "build", ".next", ".nuxt", ".gitbridge_backups"}

class AppImageService:

    @staticmethod
    def get_app_images(slug: str, db: Session) -> Dict[str, Any]:
        """Scan app local_path for all image assets, returning structured metadata and preview URLs."""
        app_obj = db.query(AppProfileModel).filter(AppProfileModel.slug == slug).first()
        if not app_obj or not app_obj.local_path or not os.path.exists(app_obj.local_path):
            return {"slug": slug, "images": [], "folders": [], "total_size_bytes": 0}

        local_path = os.path.abspath(app_obj.local_path)
        images = []
        folders_set = set(["assets", "static", "public", "images", "img"])
        total_size = 0

        for root, dirs, files in os.walk(local_path):
            # Prune ignored directories in place
            dirs[:] = [d for d in dirs if d not in IGNORED_DIRS and not d.startswith(".")]
            rel_dir = os.path.relpath(root, local_path).replace("\\", "/")
            if rel_dir != ".":
                folders_set.add(rel_dir)

            for f in files:
                ext = os.path.splitext(f)[1].lower()
                if ext in IMAGE_EXTENSIONS:
                    abs_f = os.path.join(root, f)
                    rel_f = os.path.relpath(abs_f, local_path).replace("\\", "/")
                    f_size = os.path.getsize(abs_f)
                    total_size += f_size
                    
                    width = None
                    height = None
                    if ext in [".png", ".jpg", ".jpeg", ".webp"]:
                        try:
                            with Image.open(abs_f) as img:
                                width, height = img.size
                        except Exception:
                            pass

                    images.append({
                        "filename": f,
                        "rel_path": rel_f,
                        "folder": rel_dir if rel_dir != "." else "",
                        "extension": ext,
                        "size_bytes": f_size,
                        "size_formatted": f"{f_size / 1024:.1f} KB" if f_size < 1024 * 1024 else f"{f_size / (1024*1024):.1f} MB",
                        "width": width,
                        "height": height,
                        "url": f"/api/apps/{slug}/images/file?path={rel_f}",
                        "is_icon": bool(app_obj.icon_url and (f in app_obj.icon_url or rel_f in app_obj.icon_url))
                    })

        # Sort images: icons first, then folder/name
        images.sort(key=lambda x: (not x["is_icon"], x["rel_path"]))

        return {
            "slug": slug,
            "app_name": app_obj.name,
            "local_path": local_path,
            "images": images,
            "count": len(images),
            "folders": sorted(list(folders_set)),
            "total_size_bytes": total_size
        }

    @staticmethod
    def get_image_file_path(slug: str, rel_path: str, db: Session) -> Optional[str]:
        """Safely resolve an image file path within the app's local directory."""
        app_obj = db.query(AppProfileModel).filter(AppProfileModel.slug == slug).first()
        if not app_obj or not app_obj.local_path or not os.path.exists(app_obj.local_path):
            return None

        local_path = os.path.abspath(app_obj.local_path)
        # Prevent directory traversal
        clean_rel = rel_path.lstrip("/\\")
        abs_target = os.path.abspath(os.path.join(local_path, clean_rel))
        if not abs_target.startswith(local_path):
            return None
        if not os.path.exists(abs_target):
            return None
        return abs_target

    @staticmethod
    def backup_images_zip(slug: str, db: Session) -> Dict[str, Any]:
        """Create a zip archive of all images in the app and store in app's backups folder."""
        data = AppImageService.get_app_images(slug, db)
        images = data.get("images", [])
        app_obj = db.query(AppProfileModel).filter(AppProfileModel.slug == slug).first()
        if not app_obj or not app_obj.local_path:
            return {"success": False, "message": "App local path not found"}

        local_path = os.path.abspath(app_obj.local_path)
        backup_dir = os.path.join(local_path, ".gitbridge_backups")
        os.makedirs(backup_dir, exist_ok=True)

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        zip_filename = f"{slug}_images_backup_{timestamp}.zip"
        zip_path = os.path.join(backup_dir, zip_filename)

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for img in images:
                abs_img = os.path.join(local_path, img["rel_path"])
                if os.path.exists(abs_img):
                    zf.write(abs_img, arcname=img["rel_path"])

        zip_size = os.path.getsize(zip_path)
        return {
            "success": True,
            "zip_filename": zip_filename,
            "zip_path": zip_path,
            "size_bytes": zip_size,
            "image_count": len(images),
            "download_url": f"/api/apps/{slug}/images/file?path=.gitbridge_backups/{zip_filename}",
            "message": f"Successfully backed up {len(images)} images ({zip_size / 1024:.1f} KB) into {zip_filename}"
        }

    @staticmethod
    def drop_asset_to_app(
        slug: str,
        asset_url: Optional[str] = None,
        target_folder: str = "assets",
        target_filename: Optional[str] = None,
        set_as_app_icon: bool = False,
        update_code_references: bool = False,
        svg_content: Optional[str] = None,
        base64_data: Optional[str] = None,
        db: Session = None
    ) -> Dict[str, Any]:
        """Drop a synthesized asset file directly into the app's folder on disk, optionally updating icon and references."""
        import base64
        app_obj = db.query(AppProfileModel).filter(AppProfileModel.slug == slug).first()
        if not app_obj or not app_obj.local_path or not os.path.exists(app_obj.local_path):
            return {"success": False, "message": f"App '{slug}' directory not found on disk."}

        local_path = os.path.abspath(app_obj.local_path)
        clean_folder = target_folder.strip("/\\") if target_folder and target_folder != "." else ""
        dest_dir = os.path.abspath(os.path.join(local_path, clean_folder)) if clean_folder else local_path
        os.makedirs(dest_dir, exist_ok=True)

        dest_filepath = None

        if svg_content and svg_content.strip():
            ext = ".svg"
            if not target_filename:
                target_filename = f"icon{ext}" if set_as_app_icon else f"asset_{int(time.time())}{ext}"
            elif not target_filename.endswith(ext):
                target_filename = f"{target_filename}{ext}"
            dest_filepath = os.path.join(dest_dir, target_filename)
            with open(dest_filepath, "w", encoding="utf-8") as f:
                f.write(svg_content)
        elif base64_data and base64_data.strip():
            ext = ".png"
            if "data:image/svg+xml" in base64_data:
                ext = ".svg"
            elif "data:image/jpeg" in base64_data:
                ext = ".jpg"
            elif "data:image/webp" in base64_data:
                ext = ".webp"

            if not target_filename:
                target_filename = f"icon{ext}" if set_as_app_icon else f"asset_{int(time.time())}{ext}"
            elif not target_filename.endswith(ext):
                target_filename = f"{target_filename}{ext}"
            dest_filepath = os.path.join(dest_dir, target_filename)

            # Strip data url scheme if present
            raw_b64 = base64_data
            if "," in raw_b64:
                raw_b64 = raw_b64.split(",", 1)[1]
            binary_bytes = base64.b64decode(raw_b64)
            with open(dest_filepath, "wb") as f:
                f.write(binary_bytes)
        else:
            if not asset_url:
                return {"success": False, "message": "Either asset_url, svg_content, or base64_data is required."}

            # 1. Resolve source asset file
            src_path = None
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

            if "/api/asset-lab/file/" in asset_url:
                fname = asset_url.split("/")[-1].split("?")[0]
                src_path = os.path.join(base_dir, "assets", "lab_generated", fname)
            elif "/api/sot/reference-file/" in asset_url:
                fname = asset_url.split("/")[-1].split("?")[0]
                src_path = os.path.join(base_dir, "assets", "sot_references", fname)
            elif os.path.exists(asset_url):
                src_path = asset_url

            if not src_path or not os.path.exists(src_path):
                return {"success": False, "message": f"Source asset '{asset_url}' not found on disk."}

            ext = os.path.splitext(src_path)[1].lower()
            if not target_filename:
                target_filename = f"icon{ext}" if set_as_app_icon else os.path.basename(src_path)
            elif not target_filename.endswith(ext):
                target_filename = f"{target_filename}{ext}"

            dest_filepath = os.path.join(dest_dir, target_filename)
            shutil.copy2(src_path, dest_filepath)

        rel_dest = os.path.relpath(dest_filepath, local_path).replace("\\", "/")

        # 3. If set_as_app_icon, update AppProfileModel & MediaAssetModel
        icon_updated = False
        if set_as_app_icon:
            app_obj.icon_url = f"/api/apps/{slug}/images/file?path={rel_dest}"
            db.commit()
            db.refresh(app_obj)
            icon_updated = True

        # 4. If update_code_references, scan index.html or main code files for existing icon links
        refs_updated = []
        if update_code_references:
            for candidate in ["index.html", "public/index.html", "src/index.html"]:
                cand_path = os.path.join(local_path, candidate)
                if os.path.exists(cand_path):
                    try:
                        with open(cand_path, "r", encoding="utf-8") as f:
                            content = f.read()

                        # Determine relative path from HTML file to the dropped asset
                        cand_dir = os.path.dirname(cand_path)
                        rel_to_html = os.path.relpath(dest_filepath, cand_dir).replace("\\", "/") if cand_dir else rel_dest

                        # Check if an existing <link rel="icon"> or favicon tag exists
                        has_link = bool(re.search(r'<link[^>]*rel=["\'](?:icon|shortcut icon|apple-touch-icon)["\']', content, re.IGNORECASE))
                        if has_link:
                            new_content = re.sub(
                                r'(<link[^>]*rel=["\'](?:icon|shortcut icon|apple-touch-icon)["\'][^>]*href=["\'])[^"\']*(["\'])',
                                rf'\g<1>{rel_to_html}\g<2>',
                                content
                            )
                        else:
                            # Cleanly insert <link rel="icon"> into <head>
                            icon_tag = f'  <link rel="icon" type="image/png" href="{rel_to_html}" />\n'
                            if "</head>" in content:
                                new_content = content.replace("</head>", f"{icon_tag}</head>", 1)
                            elif "<head>" in content:
                                new_content = content.replace("<head>", f"<head>\n{icon_tag}", 1)
                            elif "<html" in content:
                                new_content = re.sub(r'(<html[^>]*>)', rf'\g<1>\n<head>\n{icon_tag}</head>', content, count=1)
                            else:
                                new_content = f"{icon_tag}{content}"

                        if new_content != content:
                            with open(cand_path, "w", encoding="utf-8") as f:
                                f.write(new_content)
                            refs_updated.append(candidate)
                    except Exception as e:
                        print(f"[DropAsset] Failed to update code reference in {candidate}: {e}")

            # Also check and update manifest.json if present
            for m_cand in ["manifest.json", "public/manifest.json", "src/manifest.json"]:
                m_path = os.path.join(local_path, m_cand)
                if os.path.exists(m_path):
                    try:
                        import json
                        with open(m_path, "r", encoding="utf-8") as f:
                            m_data = json.load(f)
                        if isinstance(m_data, dict):
                            cand_dir = os.path.dirname(m_path)
                            rel_to_m = os.path.relpath(dest_filepath, cand_dir).replace("\\", "/") if cand_dir else rel_dest
                            icons = m_data.get("icons", [])
                            # Remove duplicates or prepend
                            icons = [ic for ic in icons if ic.get("src") != rel_to_m]
                            icons.insert(0, {
                                "src": rel_to_m,
                                "sizes": "512x512",
                                "type": "image/png",
                                "purpose": "any maskable"
                            })
                            m_data["icons"] = icons
                            with open(m_path, "w", encoding="utf-8") as f:
                                json.dump(m_data, f, indent=2)
                            refs_updated.append(m_cand)
                    except Exception as e:
                        print(f"[DropAsset] Failed to update manifest {m_cand}: {e}")

        return {
            "success": True,
            "rel_path": rel_dest,
            "dest_filepath": dest_filepath,
            "filename": target_filename,
            "size_bytes": os.path.getsize(dest_filepath),
            "app_icon_updated": icon_updated,
            "refs_updated": refs_updated,
            "url": f"/api/apps/{slug}/images/file?path={rel_dest}",
            "message": f"Successfully dropped {target_filename} into '{clean_folder}/' ({rel_dest})!"
        }

    @staticmethod
    def upload_image_to_app(
        slug: str,
        file_bytes: bytes,
        original_filename: str,
        target_folder: str = "assets",
        set_as_app_icon: bool = False,
        update_code_references: bool = False,
        db: Session = None
    ) -> Dict[str, Any]:
        """Upload an image file from PC directly into the app's folder with automatic HEIC conversion and icon linking."""
        from gitbridge.services.image_converter_service import ImageConverterService
        app_obj = db.query(AppProfileModel).filter(AppProfileModel.slug == slug).first()
        if not app_obj or not app_obj.local_path or not os.path.exists(app_obj.local_path):
            return {"success": False, "message": f"App '{slug}' directory not found on disk."}

        local_path = os.path.abspath(app_obj.local_path)
        clean_folder = target_folder.strip("/\\") if target_folder and target_folder != "." else ""
        dest_dir = os.path.abspath(os.path.join(local_path, clean_folder)) if clean_folder else local_path
        os.makedirs(dest_dir, exist_ok=True)

        conv_res = ImageConverterService.save_and_convert_upload(
            file_bytes=file_bytes,
            original_filename=original_filename,
            target_dir=dest_dir,
            target_format="png" if original_filename.lower().endswith((".heic", ".heif")) else "original"
        )
        saved_filename = conv_res["filename"]
        dest_filepath = conv_res["file_path"]
        rel_dest = os.path.relpath(dest_filepath, local_path).replace("\\", "/")

        icon_updated = False
        if set_as_app_icon:
            app_obj.icon_url = f"/api/apps/{slug}/images/file?path={rel_dest}"
            db.commit()
            db.refresh(app_obj)
            icon_updated = True

        refs_updated = []
        if update_code_references:
            for candidate in ["index.html", "public/index.html", "src/index.html"]:
                cand_path = os.path.join(local_path, candidate)
                if os.path.exists(cand_path):
                    try:
                        with open(cand_path, "r", encoding="utf-8") as f:
                            content = f.read()

                        cand_dir = os.path.dirname(cand_path)
                        rel_to_html = os.path.relpath(dest_filepath, cand_dir).replace("\\", "/") if cand_dir else rel_dest

                        has_link = bool(re.search(r'<link[^>]*rel=["\'](?:icon|shortcut icon|apple-touch-icon)["\']', content, re.IGNORECASE))
                        if has_link:
                            new_content = re.sub(
                                r'(<link[^>]*rel=["\'](?:icon|shortcut icon|apple-touch-icon)["\'][^>]*href=["\'])[^"\']*(["\'])',
                                rf'\g<1>{rel_to_html}\g<2>',
                                content
                            )
                        else:
                            icon_tag = f'  <link rel="icon" type="image/png" href="{rel_to_html}" />\n'
                            if "</head>" in content:
                                new_content = content.replace("</head>", f"{icon_tag}</head>", 1)
                            elif "<head>" in content:
                                new_content = content.replace("<head>", f"<head>\n{icon_tag}", 1)
                            elif "<html" in content:
                                new_content = re.sub(r'(<html[^>]*>)', rf'\g<1>\n<head>\n{icon_tag}</head>', content, count=1)
                            else:
                                new_content = f"{icon_tag}{content}"

                        if new_content != content:
                            with open(cand_path, "w", encoding="utf-8") as f:
                                f.write(new_content)
                            refs_updated.append(candidate)
                    except Exception as e:
                        print(f"[UploadImage] Failed to update reference in {candidate}: {e}")

        return {
            "success": True,
            "rel_path": rel_dest,
            "dest_filepath": dest_filepath,
            "filename": saved_filename,
            "size_bytes": os.path.getsize(dest_filepath),
            "app_icon_updated": icon_updated,
            "refs_updated": refs_updated,
            "url": f"/api/apps/{slug}/images/file?path={rel_dest}",
            "message": f"Successfully uploaded {saved_filename} into '{clean_folder}/' ({rel_dest})!"
        }
