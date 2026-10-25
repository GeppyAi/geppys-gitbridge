# Change Log — Geppy's GitBridge

## [2026-10-25 07:46] — feat: update manifest.json, sidepanel.css (+25 more)
- **`gitbridge/static/index.html`**: [Batch] Implemented "UI Text Consistency Scrub" in gitbridge/static/index.html — I have updated the `index.html` file to replace all occurrences of "GitBridge" with "Git Bridge". This ensures consistent branding throughout the application's user interface.
- **`gitbridge/static/index.html`**: [Batch] Implemented "Update Mono-font Slug Display" in gitbridge/static/index.html — I have updated the `index.html` file. The mono-text paragraph under the main header now displays "git-bridge" instead of "geppys-git-bridge-api", aligning with the desired two-word branding for the API. This change improves consistency in t
- **`gitbridge/static/index.html`**: [Batch] Implemented "De-concatenate 'GitBridge' in UI" in gitbridge/static/index.html — Updated the hero section heading in index.html to display 'Geppy's Git Bridge' with a space, ensuring consistent branding across all visible text components.
- **`README.md`**: [Batch] Implemented "Project README Sync" in README.md — Successfully updated `README.md`: Scan the project README.md and replace all instances of 'GitBridge' with 'Git Bridge'.
- **`gitbridge/main.py`**: [Batch] Implemented "Swagger UI Title Update" in gitbridge/main.py — Updated the FastAPI application title and description to consistently use "Geppy's Git Bridge".
- **`gitbridge/main.py`**: [Batch] Implemented "Update FastAPI Metadata" in gitbridge/main.py — It looks like the `edit_file` tool is not available. I will try to achieve the same result by using `write_to_file` and overwriting the existing file.

## [2026-10-18 17:33] — Update Geppy's GitBridge
- Updated `README.md`
- Updated `extension/background.js`
- Updated `extension/manifest.json`
- Updated `extension/sidepanel.css`
- Updated `extension/sidepanel.html`
- Updated `extension/sidepanel.js`
- Updated `gitbridge/assets/lab_generated/history.json`
- Updated `gitbridge/assets/lab_generated/series/series_history.json`
- Updated `gitbridge/cli.py`
- Updated `gitbridge/main.py`
- Updated `gitbridge/services/asset_lab_service.py`
- Updated `gitbridge/services/central_key_service.py`
- Updated `gitbridge/services/chat_service.py`
- Updated `gitbridge/services/extension_service.py`
- Updated `gitbridge/services/launcher_service.py`

## [2026-10-16 19:26] — feat: update index.html, main.py (+11 more)
- **`gitbridge/main.py`**: [Batch] Implemented "Non-Blocking Async Port Radar Scanner" in gitbridge/main.py — Successfully applied: Add an async background helper function in FastAPI to scan common local development ports (e.g. 3000, 8000, 8080) and display active port badges in the GitBridge top navbar.
- **`gitbridge/main.py`**: Saved manual edits to gitbridge/main.py
- **`gitbridge/main.py`**: [Batch] Implemented "Add Self-Aware App Context Identifier to FastAPI" in gitbridge/main.py — Successfully applied: In gitbridge/main.py, create an async endpoint GET '/api/self-context' that returns JSON metadata identifying the current running instance (app_id='gitbridge', name="Geppy's GitBridge", port=8000, is_self=True, status=
- **`gitbridge/main.py`**: Fixed issue in gitbridge/main.py: "Fix runtime UI freeze / main-thread hang: 🚨 App Window ..." — Successfully applied: Fix runtime UI freeze / main-thread hang: 🚨 App Window Frozen (Main Thread Locked). Details: The running app tab stopped responding to heartbeats right after clicking <button#nav-app-dashboard> "App Dashboard". This i
- **`extension/sidepanel.css`**: Implemented "Add UI Loading State" in extension/sidepanel.css — Successfully applied: Add a CSS loading spinner to index.html that is visible until the JavaScript fetch function successfully populates the app list.
- **`gitbridge/main.py`**: Implemented "Fix Broken Layout & Add Scrollable Area" in gitbridge/main.py — Successfully applied: Fix the truncated index.html file. Ensure the main container is flexible and add a scrollable grid for the app catalog so it doesn't break the layout when many apps are loaded.
- **`gitbridge/main.py`**: Implemented "Implement the 'Sync' Trigger" in gitbridge/main.py — Successfully applied: In index.html, add a 'Sync Now' button with a loading state. When clicked, it should call the '/sync' endpoint and then refresh the app list.
- **`gitbridge/main.py`**: Implemented "Implement JS App Loader" in gitbridge/main.py — Successfully applied: In index.html, add a <script> block that calls fetch('/apps'), loops through the results, and creates HTML cards for each app inside a grid container.
- **`index.html`**: Implemented "Fix main.py Syntax & CORS" in index.html — Successfully applied: Update main.py to be a valid FastAPI application. Include CORSMiddleware and a GET /apps route that returns a list of dictionaries representing apps (id, name, status, icon).
- **`index.html`**: Saved manual edits to index.html
- **`index.html`**: Implemented "De-concatenate 'GitBridge' in UI" in index.html — Successfully applied: Update index.html to ensure all visible text uses 'Geppy's Git Bridge' instead of 'Geppy's GitBridge'. Check the <title> tag, the <h1> in the hero section, and the main description paragraph.
- **`index.html`**: Implemented "Sync FastAPI Branding" in index.html — Successfully applied: In main.py, update the FastAPI constructor title parameter to 'Geppy's Git Bridge API' so the spacing is consistent in the auto-generated docs.
- **`gitbridge/main.py`**: Applied AI edit to gitbridge/main.py: "Fix runtime UI freeze / main-thread hang: 🥶 UI Main-Thread Hang (2410ms). Details: App froze for 2410ms right after interacting with <button> "Set as Icon".. Ensure the click handler or async operation is non-blocking, has proper try/catch error handling, and never freezes the UI."
- **`index.html`**: Applied AI edit to index.html: "Update index.html to ensure all visible text uses 'Geppy's Git Bridge' instead of 'Geppy's GitBridge'. Check the <title> tag, the <h1> in the hero section, and the main description paragraph."
- **`index.html`**: Implemented "Fix FastAPI Metadata Spacing" into index.html
- **`index.html`**: Saved changes to index.html
- **`index.html`**: Implemented "Project README Sync" into index.html
- **`index.html`**: Implemented "Swagger UI Title Update" into index.html
- **`index.html`**: Implemented "Update FastAPI Metadata" into index.html
- **`gitbridge/main.py`**: [Batch] Implemented "Project README Sync" into gitbridge/main.py
- **`gitbridge/main.py`**: Saved changes to gitbridge/main.py
- **`gitbridge/main.py`**: [Batch] Implemented "Swagger UI Title Update" into gitbridge/main.py
- **`gitbridge/main.py`**: [Batch] Implemented "Update FastAPI Metadata" into gitbridge/main.py
- **`gitbridge/main.py`**: [Batch] Implemented "Add Spring Hover Animations" into gitbridge/main.py
- **`gitbridge/main.py`**: [Batch] Implemented "Add Glassmorphic Card Styling" into gitbridge/main.py
- **`gitbridge/main.py`**: [Batch] Implemented "Implement Smooth Page Transitions" into gitbridge/main.py
- **`gitbridge/main.py`**: [Batch] Implemented "Design Sleek, Glowing Icons" into gitbridge/main.py
- **`gitbridge/main.py`**: [Batch] Implemented "Add Neon Glow Accents" into gitbridge/main.py
- **`gitbridge/main.py`**: [Batch] Implemented "Apply Glassmorphism to UI Panels" into gitbridge/main.py

