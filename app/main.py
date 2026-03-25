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
    
    from app.models import ServiceItem, Payment, Rating


@app.get("/case/{case_id}")
def get_case(case_id: int, db: Session = Depends(get_db)):

    # 🔹 Get case
    case = db.query(Case).filter(Case.id == case_id).first()

    # 🔹 Timeline
    timeline = db.query(CaseStatusLog)\
        .filter(CaseStatusLog.case_id == case_id)\
        .order_by(CaseStatusLog.created_at).all()

    # 🔹 Messages
    messages = db.query(Message)\
        .filter(Message.case_id == case_id)\
        .order_by(Message.created_at).all()

    # 🔹 Service Items
    service_items = db.query(ServiceItem)\
        .filter(ServiceItem.case_id == case_id).all()

    service_data = []

    for item in service_items:
        payments = db.query(Payment)\
            .filter(Payment.service_item_id == item.id).all()

        service_data.append({
            "id": item.id,
            "title": item.title,
            "description": item.description,
            "status": item.status,
            "price": item.price,
            "payments": [
                {
                    "amount": p.amount,
                    "status": p.status
                } for p in payments
            ]
        })

    # 🔹 Rating
    rating = db.query(Rating)\
        .filter(Rating.case_id == case_id).first()

    return {
        "case": {
            "id": case.id,
            "title": case.title,
            "description": case.description,
            "status": case.status
        },
        "timeline": [
            {
                "title": t.status_title,
                "description": t.status_description,
                "time": t.created_at
            } for t in timeline
        ],
        "messages": [
            {
                "sender": m.sender_type,
                "message": m.message,
                "time": m.created_at
            } for m in messages
        ],
        "service_items": service_data,
        "rating": {
            "rating": rating.rating,
            "comment": rating.comment
        } if rating else None
    }
