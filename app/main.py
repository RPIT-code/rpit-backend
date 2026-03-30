import os
import razorpay
import requests
from requests.auth import HTTPBasicAuth
from datetime import datetime

from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session

from app.db import test_db, init_db, get_db
from app.models import Case, CaseStatusLog, Message, ServiceItem, Payment
from fastapi.middleware.cors import CORSMiddleware


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # testing only
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

client = razorpay.Client(auth=(
    os.getenv("RAZORPAY_KEY_ID"),
    os.getenv("RAZORPAY_SECRET")
))


@app.on_event("startup")
def startup():
    test_db()
    init_db()


@app.get("/")
def home():
    return {"message": "RPIT Backend Running 🚀"}


# 🧾 Create Case
@app.post("/create-case")
def create_case(title: str, description: str, db: Session = Depends(get_db)):
    case = Case(title=title, description=description)
    db.add(case)
    db.commit()
    db.refresh(case)

    db.add(CaseStatusLog(
        case_id=case.id,
        status_title="Issue Submitted",
        status_description=title
    ))

    db.add(Message(
        case_id=case.id,
        sender_type="user",
        message=description
    ))

    db.commit()
    return {"case_id": case.id}


# 🧩 Add Service
@app.post("/add-service")
def add_service(case_id: int, title: str, description: str, price: int, db: Session = Depends(get_db)):
    service = ServiceItem(
        case_id=case_id,
        title=title,
        description=description,
        price=price,
        status="quoted"
    )

    db.add(service)
    
    

    db.add(CaseStatusLog(
    case_id=case_id,
    status_title="Service Proposed",
    status_description=f"{title} → ₹{price}"
    ))
    db.commit()
    db.refresh(service)
    return {"service_id": service.id}


# 🔁 UPDATE SERVICE (ADD ONLY - NO CHANGE ABOVE)

from fastapi import Depends
from sqlalchemy.orm import Session

@app.post("/update-service")
def update_service(service_id: int, new_price: int, reason: str, db: Session = Depends(get_db)):

    service = db.query(ServiceItem).filter(ServiceItem.id == service_id).first()

    if not service:
        return {"error": "Service not found"}

    # 🔥 expire pending payments (ROW LEVEL — IMPORTANT)
    old_payments = db.query(Payment).filter(
        Payment.service_item_id == service_id,
        Payment.status == "created"
    ).all()

    for p in old_payments:
        p.status = "expired"
        p.event_type = "expired"

        # ✅ preserve old reason if new one not provided
        p.status_reason = reason if reason else p.status_reason

        p.updated_at = datetime.utcnow()

    # 🔥 update service price
    old_price = service.price
    service.price = new_price
    service.updated_at = datetime.utcnow()

    # 🧾 timeline entry
    db.add(CaseStatusLog(
        case_id=service.case_id,
        status_title="Service Updated",
        status_description=f"₹{old_price} → ₹{new_price} | {reason}"
    ))

    db.commit()

    return {"message": "Service updated"}

# 💳 Create Payment
@app.post("/create-payment")
def create_payment(service_item_id: int, db: Session = Depends(get_db)):


    service = db.query(ServiceItem).filter(ServiceItem.id == service_item_id).first()
    if not service:
        return {"error": "Service not found"}

    if service.status == "approved":
        return {"error": "Already paid"}
    
    
    if not service or not service.price:
        return {"error": "Invalid service"}

    order = client.order.create({
        "amount": service.price * 100,
        "currency": "INR",
        "payment_capture": 1
    })

    # expire old payments
    old_payments = db.query(Payment).filter(
    Payment.service_item_id == service_item_id,
    Payment.status == "created"
    ).all()

    for p in old_payments:
        p.status = "expired"
        p.event_type = "expired"
        p.status_reason = p.status_reason or "new attempt"
        p.updated_at = datetime.utcnow()

    # 🔥 get last meaningful reason (for propagation)
    last_reason_payment = db.query(Payment)\
        .filter(
            Payment.service_item_id == service_item_id,
            Payment.status_reason.isnot(None)
        )\
        .order_by(Payment.created_at.desc())\
        .first()

    propagated_reason = last_reason_payment.status_reason if last_reason_payment else None

    payment = Payment(
    service_item_id=service_item_id,
    amount=service.price,
    razorpay_order_id=order["id"],
    event_type="created",
    status_reason=propagated_reason   # 🔥 THIS LINE
)

    db.add(payment)
    db.commit()

    return {
        "order_id": order["id"],
        "amount": service.price,
        "key": os.getenv("RAZORPAY_KEY_ID")
    }


# 🔥 VALIDATE + SYNC (CORE ENGINE)
@app.get("/validate-payment/{service_id}")
def validate_payment(service_id: int, db: Session = Depends(get_db)):

    try:
        payment = db.query(Payment)\
            .filter(Payment.service_item_id == service_id)\
            .order_by(Payment.created_at.desc())\
            .first()

        if not payment:
            return {"error": "No payment"}

        order_id = payment.razorpay_order_id

        key = os.getenv("RAZORPAY_KEY_ID")
        secret = os.getenv("RAZORPAY_SECRET")

        order = requests.get(
            f"https://api.razorpay.com/v1/orders/{order_id}",
            auth=HTTPBasicAuth(key, secret)
        ).json()

        payments = requests.get(
            f"https://api.razorpay.com/v1/orders/{order_id}/payments",
            auth=HTTPBasicAuth(key, secret)
        ).json()


        # safety
        if "error" in order:
            return {"error": "Razorpay order fetch failed"}

        if "error" in payments:
            return {"error": "Razorpay payment fetch failed"}

        items = payments.get("items", [])
        attempts = order.get("attempts", 0)
        last_payment = items[-1] if items else None

        # =========================
        # ✅ SUCCESS
        # =========================
        if order.get("status") == "paid":
            captured = next((p for p in items if p["status"] == "captured"), None)

            if captured:
                existing_meta = payment.meta if payment.meta else {}

                # ❌ AMOUNT MISMATCH
                if captured["amount"] != payment.amount * 100:

                    payment.status = "failed"
                    payment.event_type = "failed"
                    payment.status_reason = "amount mismatch"
                    payment.updated_at = datetime.utcnow()

                    existing_meta.update({
                        "razorpay_amount": captured["amount"] / 100,
                        "expected_amount": payment.amount
                    })

                    payment.meta = existing_meta

                    db.commit()

                    return {"error": "Amount mismatch"}

                # ✅ SUCCESS / UPDATE
                should_update = (
                    payment.status != "paid"
                    or existing_meta.get("attempts") != attempts
                )

                if should_update:

                    is_first_success = payment.status != "paid"

                    payment.status = "paid"
                    payment.event_type = "paid"
                    payment.razorpay_payment_id = captured["id"]
                    payment.status_reason = "verified via Razorpay"
                    payment.updated_at = datetime.utcnow()

                    existing_meta.update({
                        "method": captured.get("method"),
                        "attempts": attempts,
                        "amount": captured.get("amount") / 100
                    })

                    payment.meta = existing_meta

                    # 🔥 ONLY FIRST TIME → timeline
                    if is_first_success:
                        service = db.query(ServiceItem)\
                            .filter(ServiceItem.id == payment.service_item_id)\
                            .first()

                        if service:
                            service.status = "approved"

                            db.add(CaseStatusLog(
                                case_id=service.case_id,
                                status_title="Payment Received",
                                status_description=f"₹{payment.amount} received via {captured.get('method')}"
                            ))

                    db.commit()

                return {
                    "state": "paid",
                    "order_id": order_id,
                    "amount": captured["amount"] / 100,
                    "attempts": attempts,
                    "method": captured.get("method"),
                    "key": key
                }
        # =========================
        # ❌ FAILED
        # =========================
        if last_payment and last_payment["status"] == "failed":

            existing_meta = payment.meta if payment.meta else {}

            if payment.status != "failed" or existing_meta.get("attempts") != attempts:
                payment.status = "failed"
                payment.event_type = "failed"
                payment.status_reason = last_payment.get("error_description")
                payment.updated_at = datetime.utcnow()

                existing_meta.update({
                    "attempts": attempts,
                    "method": last_payment.get("method"),
                    "error_code": last_payment.get("error_code")
                })

                payment.meta = existing_meta
                db.commit()

            return {
                "state": "failed",
                "order_id": order_id,
                "amount": order.get("amount") / 100,
                "attempts": attempts,
                "reason": last_payment.get("error_description"),
                "key": key
            }

        # =========================
        # ⏳ PENDING
        # =========================
        existing_meta = payment.meta if payment.meta else {}

        if existing_meta.get("attempts") != attempts:
            existing_meta.update({
                "attempts": attempts
            })

            payment.meta = existing_meta
            payment.updated_at = datetime.utcnow()
            db.commit()

        return {
            "state": "pending",
            "order_id": order_id,
            "amount": order.get("amount") / 100,
            "attempts": attempts,
            "key": key
        }

    except Exception as e:
        print("VALIDATION ERROR:", str(e))
        return {"error": "internal error"}
    

# 📂 GET FULL CASE (UI BACKBONE)
@app.get("/case/{case_id}")
def get_case(case_id: int, db: Session = Depends(get_db)):

    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        return {"error": "Case not found"}

    # timeline
    timeline = db.query(CaseStatusLog)\
        .filter(CaseStatusLog.case_id == case_id)\
        .order_by(CaseStatusLog.created_at).all()

    # messages
    messages = db.query(Message)\
        .filter(Message.case_id == case_id)\
        .order_by(Message.created_at).all()

    # services
    services = db.query(ServiceItem)\
        .filter(ServiceItem.case_id == case_id).all()

    service_data = []

    for s in services:
        payments = db.query(Payment)\
            .filter(Payment.service_item_id == s.id)\
            .order_by(Payment.created_at.desc()).all()

        service_data.append({
            "id": s.id,
            "title": s.title,
            "description": s.description,
            "price": s.price,
            "status": s.status,
            "payments": [
                {
                    "id": p.id,
                    "amount": p.amount,
                    "status": p.status,
                    "event_type": p.event_type,
                    "reason": p.status_reason,
                    "created_at": p.created_at,
                    "updated_at": p.updated_at,
                    "meta": p.meta
                } for p in payments
            ]
        })

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
        "services": service_data
    }


# 💬 SEND MESSAGE
@app.post("/send-message")
def send_message(case_id: int, sender: str, message: str, db: Session = Depends(get_db)):

    msg = Message(
        case_id=case_id,
        sender_type=sender,
        message=message
    )

    db.add(msg)
    db.commit()

    return {"message": "sent"}


# 🔒 CLOSE CASE
@app.post("/close-case")
def close_case(case_id: int, db: Session = Depends(get_db)):

    case = db.query(Case).filter(Case.id == case_id).first()

    if not case:
        return {"error": "Case not found"}

    case.status = "closed"
    case.updated_at = datetime.utcnow()
    db.add(CaseStatusLog(
        case_id=case_id,
        status_title="Case Closed",
        status_description="Resolved"
    ))

    db.commit()

    return {"message": "Case closed"}


# 🔁 REOPEN CASE
@app.post("/reopen-case")
def reopen_case(case_id: int, reason: str, db: Session = Depends(get_db)):

    case = db.query(Case).filter(Case.id == case_id).first()

    if not case:
        return {"error": "Case not found"}

    case.status = "reopened"
    case.updated_at = datetime.utcnow()
    db.add(CaseStatusLog(
        case_id=case_id,
        status_title="Case Reopened",
        status_description=reason
    ))

    db.commit()

    return {"message": "Case reopened"}


# 💸 REFUND PAYMENT (ADD ONLY - NO CHANGE ABOVE)
@app.post("/refund-payment")
def refund_payment(payment_id: int, refund_amount: int, reason: str, db: Session = Depends(get_db)):

    payment = db.query(Payment).filter(Payment.id == payment_id).first()

    if not payment:
        return {"error": "Payment not found"}

    if payment.status != "paid":
        return {"error": "Only paid payments can be refunded"}

    payment.status = "refunded"
    payment.event_type = "refunded"
    payment.refund_amount = refund_amount
    payment.refund_status = "processed"
    payment.status_reason = reason
    payment.updated_at = datetime.utcnow()

    service = db.query(ServiceItem).filter(ServiceItem.id == payment.service_item_id).first()

    if service:
        db.add(CaseStatusLog(
            case_id=service.case_id,
            status_title="Refund Issued",
            status_description=f"₹{refund_amount} refunded - {reason}"
        ))

    db.commit()

    return {"message": "Refund processed"}


@app.get("/cases")
def get_cases(db: Session = Depends(get_db)):

    cases = db.query(Case).order_by(Case.created_at.desc()).all()

    case_ids = [c.id for c in cases]

    # 🔥 batch fetch
    services = db.query(ServiceItem)\
        .filter(ServiceItem.case_id.in_(case_ids)).all()

    timelines = db.query(CaseStatusLog)\
        .filter(CaseStatusLog.case_id.in_(case_ids))\
        .order_by(CaseStatusLog.created_at.asc()).all()

    # 🔥 group them
    service_map = {}
    for s in services:
        service_map.setdefault(s.case_id, []).append(s)

    timeline_map = {}
    for t in timelines:
        timeline_map.setdefault(t.case_id, []).append(t)

    result = []

    for c in cases:

        case_services = service_map.get(c.id, [])
        case_timeline = timeline_map.get(c.id, [])

        last_status = case_timeline[-1].status_title if case_timeline else None

        result.append({
            "id": c.id,
            "title": c.title,
            "status": c.status,
            "last_status": last_status,
            "service_count": len(case_services),
            "created_at": c.created_at
        })

    return result