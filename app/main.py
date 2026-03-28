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
    allow_origins=["*"],   # testing only
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
    db.commit()
    db.refresh(service)

    return {"service_id": service.id}


# 💳 Create Payment
@app.post("/create-payment")
def create_payment(service_item_id: int, db: Session = Depends(get_db)):

    service = db.query(ServiceItem).filter(ServiceItem.id == service_item_id).first()

    order = client.order.create({
        "amount": service.price * 100,
        "currency": "INR",
        "payment_capture": 1
    })

    # expire old active payments
    db.query(Payment).filter(
        Payment.service_item_id == service_item_id,
        Payment.status == "created"
    ).update({
        "status": "expired",
        "event_type": "expired",
        "status_reason": "new attempt",
        "updated_at": datetime.utcnow()
    })

    payment = Payment(
        service_item_id=service_item_id,
        amount=service.price,
        razorpay_order_id=order["id"],
        event_type="created"
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

    items = payments.get("items", [])
    attempts = order.get("attempts", 0)
    last_payment = items[-1] if items else None

    updated = False  # track DB writes

    # ✅ SUCCESS
    if order.get("status") == "paid":
        captured = next((p for p in items if p["status"] == "captured"), None)

        if captured:
            if payment.status != "paid":
                payment.status = "paid"
                payment.event_type = "paid"
                payment.razorpay_payment_id = captured["id"]
                payment.status_reason = "verified via Razorpay"
                payment.updated_at = datetime.utcnow()

                payment.meta = {
                    "method": captured.get("method"),
                    "attempts": attempts,
                    "amount": captured.get("amount") / 100
                }

                updated = True

            if updated:
                db.commit()

            return {
                "state": "paid",
                "order_id": order_id,
                "amount": captured["amount"] / 100,
                "attempts": attempts,
                "method": captured.get("method"),
                "key": key
            }

    # ❌ FAILED
    if last_payment and last_payment["status"] == "failed":

        if payment.status != "failed":
            payment.status = "failed"
            payment.event_type = "failed"
            payment.status_reason = last_payment.get("error_description")
            payment.updated_at = datetime.utcnow()

            payment.meta = {
                "attempts": attempts,
                "error_code": last_payment.get("error_code"),
                "method": last_payment.get("method")
            }

            updated = True

        if updated:
            db.commit()

        return {
            "state": "failed",
            "order_id": order_id,
            "amount": order.get("amount") / 100,
            "attempts": attempts,
            "reason": last_payment.get("error_description"),
            "key": key
        }

    # ⏳ PENDING
    if payment.status == "created":
        payment.meta = {
            "attempts": attempts
        }
        payment.updated_at = datetime.utcnow()
        db.commit()

    return {
        "state": "pending",
        "order_id": order_id,
        "amount": order.get("amount") / 100,
        "attempts": attempts,
        "key": key
    }
