"""
Sets up the connection between FastAPI and the database.
main.py uses this to actually talk to timetable.db.
"""

from sqlalchemy.orm import sessionmaker
from models import engine

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """
    Gives each API request its own database connection, and makes
    sure it's properly closed afterward. FastAPI calls this
    automatically for any endpoint that asks for it.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()