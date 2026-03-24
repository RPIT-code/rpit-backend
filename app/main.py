from fastapi import FastAPI
from app.db import test_db

app = FastAPI()

@app.on_event("startup")
def startup():
    test_db()

@app.get("/")
def home():
    return {"message": "RPIT Backend Running 🚀"}

@app.get("/test-db")
def test_database():
    try:
        test_db()
        return {"status": "DB Connected ✅"}
    except:
        return {"status": "DB Failed ❌"}
