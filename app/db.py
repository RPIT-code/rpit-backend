from sqlalchemy import create_engine
import os

DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_engine(DATABASE_URL)

def test_db():
    try:
        conn = engine.connect()
        print("DB Connected ✅")
        conn.close()
    except Exception as e:
        print("DB Failed ❌", e)
