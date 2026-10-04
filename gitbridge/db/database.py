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
    Base.metadata.create_all(bind=engine)
    # Ensure missing columns are migrated in SQLite
    if DATABASE_URL.startswith("sqlite"):
        with engine.connect() as conn:
            from sqlalchemy import text
            for col in ["feature_breakdown", "local_path", "launch_command", "live_url"]:
                try:
                    conn.execute(text(f"ALTER TABLE app_profiles ADD COLUMN {col} TEXT"))
                    conn.commit()
                except Exception:
                    pass
