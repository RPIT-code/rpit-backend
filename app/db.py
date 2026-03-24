from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os

from app.models import Base

DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def test_db():
    try:
        conn = engine.connect()
        print("DB Connected ✅")
        conn.close()
    except Exception as e:
        print("DB Failed ❌", e)
