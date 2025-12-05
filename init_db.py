#!/usr/bin/env python
"""
Initialize database tables from SQLAlchemy models.
Run this once to create all tables.
"""

import asyncio
from pathlib import Path
from dotenv import load_dotenv

# Load .env file explicitly (override any existing env vars)
env_path = Path(__file__).parent / ".env"
load_dotenv(env_path, override=True)

from sqlalchemy import text

from app.core.config import settings
from app.core.db import async_engine
from app.models.base import Base


async def init_db():
    """Create all tables defined in models."""
    import os

    # Get DATABASE_URL from environment
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("❌ DATABASE_URL not set in .env file")
        return False

    # Convert async URL to sync for table creation
    sync_url = db_url.replace("postgresql+asyncpg://", "postgresql://")
    print(f"📝 Using database: {sync_url}")

    from sqlalchemy import create_engine

    # Create sync engine for initialization
    sync_engine = create_engine(sync_url, echo=True)

    try:
        # Create all tables
        Base.metadata.create_all(sync_engine)
        print("✅ Database tables created successfully!")
        return True
    except Exception as e:
        print(f"❌ Error creating tables: {e}")
        return False
    finally:
        sync_engine.dispose()


if __name__ == "__main__":
    print("Initializing database...")
    success = asyncio.run(init_db())
    exit(0 if success else 1)
