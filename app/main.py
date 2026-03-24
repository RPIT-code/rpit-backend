from fastapi import FastAPI
from app.db import test_db, init_db

app = FastAPI()

@app.on_event("startup")
def startup():
    test_db()
    init_db()  # 👈 creates tables automatically

@app.get("/")
def home():
    return {"message": "RPIT Backend Running 🚀"}