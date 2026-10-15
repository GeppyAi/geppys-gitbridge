import os
import shutil
from pathlib import Path
from PIL import Image

src_path = Path("D:/Downloads/Gitbridge.png")
if not src_path.exists():
    raise FileNotFoundError(f"Source file not found: {src_path}")

print(f"Loading GitBridge icon: {src_path}")
im = Image.open(src_path)
print(f"Source size: {im.size}, mode: {im.mode}")

# 1. GitBridge static assets
static_assets_dir = Path("d:/Geppy_Apps/Geppy's GitBridge/gitbridge/static/assets")
static_assets_dir.mkdir(parents=True, exist_ok=True)
shutil.copy2(src_path, static_assets_dir / "gitbridge_icon.png")
shutil.copy2(src_path, static_assets_dir / "gitbridge_hero.png")

for sz in [512, 256, 128, 64, 32]:
    resized = im.resize((sz, sz), Image.Resampling.LANCZOS)
    target = static_assets_dir / f"gitbridge_icon_{sz}.png"
    resized.save(target, format="PNG")
    print(f"Saved: {target}")

# Favicon
fav_target = Path("d:/Geppy_Apps/Geppy's GitBridge/gitbridge/static/favicon.png")
im.resize((64, 64), Image.Resampling.LANCZOS).save(fav_target, format="PNG")
print(f"Saved favicon: {fav_target}")

# 2. SOT references
sot_ref_dir = Path("d:/Geppy_Apps/Geppy's GitBridge/gitbridge/assets/sot_references")
sot_ref_dir.mkdir(parents=True, exist_ok=True)
shutil.copy2(src_path, sot_ref_dir / "gitbridge_icon.png")
print(f"Saved SOT reference: {sot_ref_dir / 'gitbridge_icon.png'}")

# 3. Update database records (app_profiles & sot_contextiles)
import sqlite3
import json

db_path = "gitbridge.db"
conn = sqlite3.connect(db_path)
cur = conn.cursor()

icon_url = "/static/assets/gitbridge_icon.png"
sot_icon_url = "/api/sot/reference-file/gitbridge_icon.png"

# Update any gitbridge app_profile
cur.execute("UPDATE app_profiles SET icon_url = ? WHERE slug IN ('geppys-gitbridge', 'geppy-s-gitbridge') OR local_path LIKE '%GitBridge%'", (icon_url,))
print(f"Updated app_profiles rows: {cur.rowcount}")

# Check contextiles for gitbridge
exists = cur.execute("SELECT id FROM contextiles WHERE name IN ('gitbridge', 'geppys-gitbridge')").fetchone()
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
        'gitbridge',
        "Geppy's GitBridge Mission Control",
        "Official hexagonal mission control emblem with Captain Geppy at the starship bridge console navigating the cosmic nebula with circuit traces.",
        'brand_asset',
        'hybrid',
        "Hexagonal emblem featuring Captain Geppy wearing blue shirt at a high-tech starship control console, backdrop screen showing swirling cosmic nebula galaxy, glowing circuit traces on dark navy casing, beveled golden/orange hex rim, and orange curved banner reading GEPPY'S GIT BRIDGE. Transparent background outside hex.",
        sot_icon_url,
        sot_icon_url,
        json.dumps([sot_icon_url]),
        '{"theme":["Cosmic Galactic & Nebula","Cyberpunk Neon Rim"],"medium":["3D Skeuomorphic Glass Squircle with Beveled Rim"]}',
        '["brand-asset","mission-control","hex-icon","official-icon","gitbridge"]',
        '[]',
        "Official Geppy's GitBridge hexagonal mission control emblem featuring Captain Geppy at the starship flight deck console with cosmic nebula screen and orange banner.",
        'geppys-gitbridge'
    ))
    print("Created new 'gitbridge' Contextile!")
else:
    cur.execute("UPDATE contextiles SET primary_image_url = ?, reference_image_url = ? WHERE id = ?", (sot_icon_url, sot_icon_url, exists[0]))
    print("Updated existing 'gitbridge' Contextile!")

conn.commit()
conn.close()

print("All GitBridge icon deployments & DB updates complete!")
