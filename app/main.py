from fastapi import Depends
from sqlalchemy.orm import Session
from app.db import get_db


@app.post("/create-case")
def create_case(title: str, description: str, db: Session = Depends(get_db)):

    # 1. Create Case
    new_case = Case(
        title=title,
        description=description,
        status="open"
    )
    db.add(new_case)
    db.commit()
    db.refresh(new_case)

    # 2. Status log
    status = CaseStatusLog(
        case_id=new_case.id,
        status_title="Issue Submitted",
        status_description=f"User reported: {title}"
    )
    db.add(status)

    # 3. First message
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
