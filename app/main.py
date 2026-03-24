from fastapi import FastAPI
from app.db import test_db, init_db, SessionLocal
from app.models import Case, CaseStatusLog, Message

app = FastAPI()

@app.on_event("startup")
def startup():
    test_db()
    init_db()


@app.get("/")
def home():
    return {"message": "RPIT Backend Running 🚀"}


# 🚀 CREATE CASE API
@app.post("/create-case")
def create_case(title: str, description: str):

    db = SessionLocal()

    # 1. Create Case
    new_case = Case(
        title=title,
        description=description,
        status="open"
    )
    db.add(new_case)
    db.commit()
    db.refresh(new_case)

    # 2. Add Status Log
    status = CaseStatusLog(
        case_id=new_case.id,
        status_title="Issue Submitted",
        status_description=f"User reported: {title}"
    )
    db.add(status)

    # 3. Add First Message
    message = Message(
        case_id=new_case.id,
        sender_type="user",
        message=description
    )
    db.add(message)

    db.commit()
    db.close()

    return {
        "message": "Case created successfully",
        "case_id": new_case.id
    }