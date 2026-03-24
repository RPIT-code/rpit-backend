from fastapi import FastAPI
from app.db import test_db

app = FastAPI()

@app.on_event("startup")
def startup():
    test_db()

@app.get("/")
def home():
    return {"message": "RPIT Backend Running 🚀"}
