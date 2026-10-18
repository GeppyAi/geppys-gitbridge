import os
import shutil
import sqlite3
import json
from pathlib import Path
from PIL import Image

src_path = Path("D:/Downloads/GeppyBug.png")
if not src_path.exists():
    raise FileNotFoundError(f"Source file not found: {src_path}")

print(f"Loading GeppyBug icon: {src_path}")
im = Image.open(src_path)
print(f"Source size: {im.size}, mode: {im.mode}")

# 1. GitBridge static assets
static_assets_dir = Path("d:/Geppy_Apps/Geppy's GitBridge/gitbridge/static/assets")
static_assets_dir.mkdir(parents=True, exist_ok=True)
shutil.copy2(src_path, static_assets_dir / "geppy_bug.png")
shutil.copy2(src_path, static_assets_dir / "GeppyBug.png")

for sz in [512, 256, 128, 64, 48, 32]:
    resized = im.resize((sz, sz), Image.Resampling.LANCZOS)
    target = static_assets_dir / f"geppy_bug_{sz}.png"
    resized.save(target, format="PNG")
    print(f"Saved: {target}")

# 2. Extension icons
ext_icons_dir = Path("d:/Geppy_Apps/Geppy's GitBridge/extension/icons")
ext_icons_dir.mkdir(parents=True, exist_ok=True)
shutil.copy2(src_path, ext_icons_dir / "geppy_bug.png")
for sz in [128, 64, 48, 32]:
    resized = im.resize((sz, sz), Image.Resampling.LANCZOS)
    target = ext_icons_dir / f"geppy_bug_{sz}.png"
    resized.save(target, format="PNG")
    print(f"Saved extension icon: {target}")

# 3. SOT references
sot_ref_dir = Path("d:/Geppy_Apps/Geppy's GitBridge/gitbridge/assets/sot_references")
sot_ref_dir.mkdir(parents=True, exist_ok=True)
shutil.copy2(src_path, sot_ref_dir / "geppy_bug.png")
print(f"Saved SOT reference: {sot_ref_dir / 'geppy_bug.png'}")

# 4. Update database contextiles for GeppyBug
db_path = "gitbridge.db"
conn = sqlite3.connect(db_path)
cur = conn.cursor()

sot_icon_url = "/api/sot/reference-file/geppy_bug.png"

exists = cur.execute("SELECT id FROM contextiles WHERE name IN ('geppy-bug', 'report-bug', 'geppybug')").fetchone()
if not exists:
    cur.execute("""
        INSERT INTO contextiles (
            name, title, description, archetype, reference_type, reference_text,
            reference_image_url, primary_image_url, gallery_images, modifiers,
            tags, variables, assembled_prompt, app_slug, created_at, updated_at
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now')
        )
    """, (
        'geppy-bug',
        "Geppy's Bug Reporter Emblem",
        "Official hexagonal Report Bug badge featuring a cute 3D stylized orange-and-black spotted ladybug with googly eyes inside an orange hexagon with a golden ribbon reading REPORT BUG.",
        'brand_asset',
        'hybrid',
        "Hexagonal badge emblem featuring a cute 3D rendered orange ladybug with black spots, expressive wide googly eyes, antennae, and little legs, set against a warm orange hexagonal shield with a silver/charcoal border and a golden banner ribbon across the bottom reading REPORT BUG in bold dark lettering. Transparent background outside the hexagonal badge.",
        sot_icon_url,
        sot_icon_url,
        json.dumps([sot_icon_url, "/static/assets/geppy_bug.png"]),
        '{"theme":["3D Toy & Mascot","Hexagonal Badge Emblem"],"medium":["3D Skeuomorphic Emblem with Ribbon Banner"]}',
        '["brand-asset","bug-report","ladybug","hex-icon","official-icon","geppy-bug"]',
        '[]',
        "Official Geppy's GitBridge hexagonal Report Bug badge featuring a 3D orange spotted ladybug with wide eyes and a golden ribbon reading REPORT BUG.",
        'geppys-gitbridge'
    ))
    print("Created new 'geppy-bug' Contextile!")
else:
    cur.execute("UPDATE contextiles SET primary_image_url = ?, reference_image_url = ? WHERE id = ?", (sot_icon_url, sot_icon_url, exists[0]))
    print("Updated existing 'geppy-bug' Contextile!")

conn.commit()
conn.close()
print("All GeppyBug icon deployments & DB updates complete!")
