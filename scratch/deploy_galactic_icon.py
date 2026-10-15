import os
import shutil
from pathlib import Path
from PIL import Image

src_path = Path("D:/Downloads/Geppy's Galactic (1).png")
if not src_path.exists():
    raise FileNotFoundError(f"Source file not found: {src_path}")

print(f"Loading source icon: {src_path}")
im = Image.open(src_path)
print(f"Source size: {im.size}, mode: {im.mode}")

# 1. Extension icons
ext_icons_dir = Path("d:/Geppy_Apps/Geppy's GitBridge/extension/icons")
ext_icons_dir.mkdir(parents=True, exist_ok=True)
shutil.copy2(src_path, ext_icons_dir / "icon.png")

for sz in [512, 256, 128, 48, 16]:
    resized = im.resize((sz, sz), Image.Resampling.LANCZOS)
    target = ext_icons_dir / f"icon{sz}.png"
    resized.save(target, format="PNG")
    print(f"Saved: {target}")

# 2. GitBridge static assets
static_assets_dir = Path("d:/Geppy_Apps/Geppy's GitBridge/gitbridge/static/assets")
static_assets_dir.mkdir(parents=True, exist_ok=True)
shutil.copy2(src_path, static_assets_dir / "geppys_galactic_icon.png")
print(f"Saved static asset: {static_assets_dir / 'geppys_galactic_icon.png'}")

# 3. SOT references
sot_ref_dir = Path("d:/Geppy_Apps/Geppy's GitBridge/gitbridge/assets/sot_references")
sot_ref_dir.mkdir(parents=True, exist_ok=True)
shutil.copy2(src_path, sot_ref_dir / "geppys_galactic_icon.png")
print(f"Saved SOT reference: {sot_ref_dir / 'geppys_galactic_icon.png'}")

# 4. Geppy's Apps Galaxtic app directory
galaxtic_dir = Path("d:/Geppy_Apps/Geppy's Apps Galaxtic")
if galaxtic_dir.exists():
    app_icons = galaxtic_dir / "icons"
    app_icons.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src_path, app_icons / "icon.png")
    for sz in [128, 48, 16]:
        resized = im.resize((sz, sz), Image.Resampling.LANCZOS)
        target = app_icons / f"icon{sz}.png"
        resized.save(target, format="PNG")
        print(f"Saved Galaxtic app icon: {target}")

    app_assets = galaxtic_dir / "assets"
    app_assets.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src_path, app_assets / "geppys_galactic_icon.png")
    print(f"Saved Galaxtic app asset: {app_assets / 'geppys_galactic_icon.png'}")

print("All icon deployments completed successfully!")
