import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./gitbridge.db")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    import gitbridge.db.models  # Ensure all model tables are registered with Base
    Base.metadata.create_all(bind=engine)
    # Ensure missing columns are migrated in SQLite
    if DATABASE_URL.startswith("sqlite"):
        with engine.connect() as conn:
            from sqlalchemy import text
            for col in ["feature_breakdown", "local_path", "launch_command", "live_url", "icon_url", "priority_tier", "health_report_md", "last_commit_at", "open_issues_count", "backlog"]:
                try:
                    conn.execute(text(f"ALTER TABLE app_profiles ADD COLUMN {col} TEXT"))
                    conn.commit()
                except Exception:
                    pass
            try:
                conn.execute(text("ALTER TABLE app_profiles ADD COLUMN is_hidden BOOLEAN DEFAULT 0"))
                conn.commit()
            except Exception:
                pass
            for col, col_def in [
                ("archetype", "VARCHAR DEFAULT 'character'"),
                ("primary_image_url", "VARCHAR"),
                ("gallery_images", "TEXT DEFAULT '[]'"),
                ("variables", "TEXT DEFAULT '[]'")
            ]:
                try:
                    conn.execute(text(f"ALTER TABLE contextiles ADD COLUMN {col} {col_def}"))
                    conn.commit()
                except Exception:
                    pass
