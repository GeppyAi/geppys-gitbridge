# 🌉 Geppy's GitBridge

> **The missing link for Geppy's App Universe**: Cataloging, database sync, asset management, and Gemini context bridge for AI Studio projects & GitHub repositories.

---

## 🌟 Features

- **📱 Central App Catalog**: Database for tracking every application created in AI Studio or hosted on GitHub.
- **🔄 GitHub Sync**: Automatically fetches and extracts repository metadata, tech stack tags, READMEs, and URLs.
- **📊 Google Sheets Sync**: Bidirectional/unidirectional sync to Google Sheets for clear viewing, filtering, and Gemini integration.
- **🤖 AI Studio Ingestor**: Parse AI Studio `.json` and `.zip` exports to automatically extract system prompts, project configurations, and metadata.
- **📸 Media & Asset Store**: Manage app logos, screenshots, promo banners, social graphics, and AI image prompts.
- **📚 Instruction Manuals Hub**: Generate, edit, and export standardized markdown user guides and developer instructions per app.
- **🧠 Gemini Context Bridge**: Dedicated CLI & API endpoint (`/api/context/universe`) formatted for Gemini models to query app specs and manage Geppy's App Universe.

---

## 🚀 Quick Start

### 1. Installation & Environment Setup
```bash
# Activate virtual environment
.\.venv\Scripts\activate

# Initialize GitBridge database and directories
python -m gitbridge.cli init
```

### 2. Basic CLI Commands

```bash
# List all apps in Geppy's App Universe
python -m gitbridge.cli list

# View detailed profile, prompts, assets & docs for an app
python -m gitbridge.cli get geppys-gitbridge

# Register a new app manually
python -m gitbridge.cli add --slug "prompt-gen" --name "Prompt Generator" --status "in_development" --tech-stack "Python, FastAPI"

# Sync with GitHub Repositories
python -m gitbridge.cli sync-github --username yourgithubusername

# Sync Catalog to Google Sheets (or CSV preview)
python -m gitbridge.cli sync-sheets --export-csv

# Import an AI Studio JSON/Zip Export
python -m gitbridge.cli import-ai-studio path/to/ai_studio_export.json

# Generate an Instruction Manual Template
python -m gitbridge.cli doc-generate geppys-gitbridge
```

### 3. Launching the API Server & Web UI Backend

```bash
# Start FastAPI server on port 8000
python -m uvicorn gitbridge.main:app --reload --port 8000
```
- Interactive API Docs: `http://localhost:8000/docs`
- Gemini Universe Context API: `http://localhost:8000/api/context/universe`

---

## 🏗️ Project Architecture

```
Geppy's GitBridge/
├── gitbridge/
│   ├── main.py                # FastAPI App & REST API Endpoints
│   ├── cli.py                 # Typer & Rich Command Line Interface
│   ├── db/
│   │   ├── database.py        # SQLite / SQLAlchemy Engine & Session
│   │   └── models.py          # AppProfile, MediaAsset, DocManual Models
│   ├── services/
│   │   ├── github_service.py  # GitHub API client & metadata extractor
│   │   ├── sheets_service.py  # Google Sheets API & CSV Exporter
│   │   └── ai_studio_service.py # AI Studio JSON/Zip Export Parser
│   └── schemas/
│       └── app_profile.py     # Pydantic Schemas & Data Enums
├── assets/                    # Media & Marketing Image Library
├── docs/                      # Instruction Manuals & Guides (.md)
├── gitbridge.db               # Local SQLite Database
├── .env.example               # Environment Configuration Template
└── requirements.txt           # Python Dependencies
```
