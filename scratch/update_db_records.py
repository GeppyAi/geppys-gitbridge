from gitbridge.db.database import SessionLocal
from gitbridge.db.models import AppProfileModel, ContextileModel
import json

db = SessionLocal()
try:
    # 1. Update app_profile for Geppy's Apps Galaxtic
    app_profile = db.query(AppProfileModel).filter(
        (AppProfileModel.slug == "geppy-s-apps-galaxtic") | (AppProfileModel.slug == "geppys-galactic")
    ).first()
    if app_profile:
        app_profile.icon_url = "/static/assets/geppys_galactic_icon.png"
        print(f"Updated AppProfile '{app_profile.name}' icon_url to /static/assets/geppys_galactic_icon.png")

    sot_icon_url = "/api/sot/reference-file/geppys_galactic_icon.png"

    # 2. Update Captain Geppy contextile
    capt = db.query(ContextileModel).filter(ContextileModel.name == "captain-geppy").first()
    if capt:
        capt.primary_image_url = sot_icon_url
        capt.reference_image_url = sot_icon_url
        capt.reference_type = "hybrid"
        gal = capt.gallery_images or []
        if sot_icon_url not in gal:
            gal.append(sot_icon_url)
        capt.gallery_images = gal
        print("Updated 'captain-geppy' contextile with official Galactic icon!")

    # 3. Update Galactic Icons contextile
    gal_icons = db.query(ContextileModel).filter(ContextileModel.name == "galactic-icons").first()
    if gal_icons:
        gal_icons.primary_image_url = sot_icon_url
        gal_icons.reference_image_url = sot_icon_url
        gal_icons.reference_type = "hybrid"
        gal = gal_icons.gallery_images or []
        if sot_icon_url not in gal:
            gal.append(sot_icon_url)
        gal_icons.gallery_images = gal
        print("Updated 'galactic-icons' contextile with official Galactic icon!")

    # 4. Update geppybrand contextile
    brand = db.query(ContextileModel).filter(ContextileModel.name == "geppybrand").first()
    if brand:
        gal = brand.gallery_images or []
        if sot_icon_url not in gal:
            gal.append(sot_icon_url)
        brand.gallery_images = gal
        print("Appended Galactic icon to 'geppybrand' gallery!")

    # 5. Create or update geppys-galactic contextile
    galactic_ctx = db.query(ContextileModel).filter(ContextileModel.name == "geppys-galactic").first()
    if not galactic_ctx:
        galactic_ctx = ContextileModel(
            name="geppys-galactic",
            title="Geppy's Galactic Official Icon & Brand",
            description="Official hexagonal icon with bold orange border, cosmic spiral galaxy nebula background, and Captain Geppy smiling with glasses and beard.",
            archetype="brand_asset",
            reference_type="hybrid",
            reference_text="Hexagonal emblem featuring Captain Geppy with brown hair, beard, and modern glasses, framed by a cosmic swirling galaxy nebula, golden/orange beveled hex rim, and orange curved banner reading GEPPY'S GALACTIC. Transparent background outside hex.",
            reference_image_url=sot_icon_url,
            primary_image_url=sot_icon_url,
            assembled_prompt="Official Geppy's Galactic hexagonal emblem featuring Captain Geppy against a cosmic swirling galaxy nebula with orange hex border and banner.",
            app_slug="geppy-s-apps-galaxtic"
        )
        galactic_ctx.gallery_images = [sot_icon_url]
        galactic_ctx.modifiers = {
            "theme": ["Cosmic Galactic & Nebula"],
            "medium": ["3D Skeuomorphic Glass Squircle with Beveled Rim"]
        }
        galactic_ctx.tags = ["brand-asset", "galactic", "hex-icon", "official-icon"]
        db.add(galactic_ctx)
        print("Created new 'geppys-galactic' contextile!")
    else:
        galactic_ctx.primary_image_url = sot_icon_url
        galactic_ctx.reference_image_url = sot_icon_url
        print("Updated existing 'geppys-galactic' contextile!")

    db.commit()
    print("Database committed successfully!")
finally:
    db.close()
