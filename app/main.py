from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session

from app.db import test_db, init_db, get_db
from app.models import Case, CaseStatusLog, Message


# ✅ FIRST define app
app = FastAPI()


# ✅ THEN startup
@app.on_event("startup")
def startup():
    test_db()
    init_db()


# ✅ THEN routes
@app.get("/")
def home():
    return {"message": "RPIT Backend Running 🚀"}


@app.post("/create-case")
def create_case(title: str, description: str, db: Session = Depends(get_db)):

    new_case = Case(
        title=title,
        description=description,
        status="open"
    )
    db.add(new_case)
    db.commit()
    db.refresh(new_case)

    status = CaseStatusLog(
        case_id=new_case.id,
        status_title="Issue Submitted",
        status_description=f"User reported: {title}"
    )
    db.add(status)

    message = Message(
        case_id=new_case.id,
        sender_type="user",
        message=description
    )
    db.add(message)

    db.commit()

    return {
        "message": "Case created successfully",
        "case_id": new_case.id
    }
