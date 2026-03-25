import os
import razorpay
from fastapi import FastAPI, Depends, Request, Body
from sqlalchemy.orm import Session

from app.db import test_db, init_db, get_db
from app.models import Case, CaseStatusLog, Message, ServiceItem, Payment, Rating


client = razorpay.Client(auth=(
    os.getenv("RAZORPAY_KEY_ID"),
    os.getenv("RAZORPAY_SECRET")
))


app = FastAPI()


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

    new_case = Case(title=title, description=description, status="open")

    db.add(new_case)
    db.commit()
    db.refresh(new_case)

    db.add(CaseStatusLog(
        case_id=new_case.id,
        status_title="Issue Submitted",
        status_description=f"User reported: {title}"
    ))

    db.add(Message(
        case_id=new_case.id,
        sender_type="user",
        message=description
    ))

    db.commit()

    return {"case_id": new_case.id}


# 📂 Get Case
@app.get("/case/{case_id}")
def get_case(case_id: int, db: Session = Depends(get_db)):

    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        return {"error": "Case not found"}

    timeline = db.query(CaseStatusLog)\
        .filter(CaseStatusLog.case_id == case_id)\
        .order_by(CaseStatusLog.created_at).all()

    messages = db.query(Message)\
        .filter(Message.case_id == case_id)\
        .order_by(Message.created_at).all()

    service_items = db.query(ServiceItem)\
        .filter(ServiceItem.case_id == case_id).all()

    service_data = []

    for item in service_items:
        payments = db.query(Payment)\
            .filter(Payment.service_item_id == item.id).all()

        service_data.append({
            "id": item.id,
            "title": item.title,
            "price": item.price,
            "status": item.status,
            "payments": [
                {
                    "amount": p.amount,
                    "status": p.status
                } for p in payments
            ]
        })

    return {
        "case": case.id,
        "services": service_data
    }


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

    db.add(CaseStatusLog(
        case_id=case_id,
        status_title="Service Proposed",
        status_description=f"{title} → ₹{price}"
    ))

    db.commit()

    return {"service_id": service.id}


# 💳 Create Payment
@app.post("/create-payment")
def create_payment(service_item_id: int, db: Session = Depends(get_db)):

    service = db.query(ServiceItem).filter(ServiceItem.id == service_item_id).first()

    if not service or not service.price:
        return {"error": "Invalid service"}

    amount = service.price

    order = client.order.create({
        "amount": amount * 100,
        "currency": "INR",
        "payment_capture": 1
    })

    payment = Payment(
        service_item_id=service_item_id,
        amount=amount,
        status="created",
        razorpay_order_id=order["id"]
    )

    db.add(payment)
    db.commit()

    return {
        "razorpay_order_id": order["id"],
        "razorpay_key": os.getenv("RAZORPAY_KEY_ID"),
        "amount": amount
    }


# 🔥 WEBHOOK (CORE)
@app.post("/razorpay-webhook")
async def razorpay_webhook(request: Request, db: Session = Depends(get_db)):

    body = await request.body()
    signature = request.headers.get("X-Razorpay-Signature")

    webhook_secret = os.getenv("RAZORPAY_WEBHOOK_SECRET")

    try:
        razorpay.utility.verify_webhook_signature(
            body.decode(),
            signature,
            webhook_secret
        )
    except:
        return {"error": "Invalid signature"}

    payload = await request.json()
    event = payload.get("event")

    # ✅ PAYMENT SUCCESS
    if event == "payment.captured":

        entity = payload["payload"]["payment"]["entity"]

        razorpay_order_id = entity["order_id"]
        razorpay_payment_id = entity["id"]

        payment = db.query(Payment)\
            .filter(Payment.razorpay_order_id == razorpay_order_id)\
            .first()

        if not payment:
            return {"error": "Payment not found"}

        # 🛑 prevent duplicate updates
        if payment.status == "paid":
            return {"message": "Already processed"}

        payment.status = "paid"
        payment.razorpay_payment_id = razorpay_payment_id
        payment.status_reason = "Payment via webhook"

        service = db.query(ServiceItem)\
            .filter(ServiceItem.id == payment.service_item_id)\
            .first()

        service.status = "approved"

        db.add(CaseStatusLog(
            case_id=service.case_id,
            status_title="Payment Received",
            status_description=f"₹{payment.amount} received"
        ))

        db.commit()

    return {"status": "ok"}


# 🔁 Update Service (with reason)
@app.post("/update-service")
def update_service(service_id: int, new_price: int, reason: str, db: Session = Depends(get_db)):

    service = db.query(ServiceItem).filter(ServiceItem.id == service_id).first()

    if not service:
        return {"error": "Service not found"}

    old_payments = db.query(Payment)\
        .filter(Payment.service_item_id == service_id)\
        .filter(Payment.status == "created")\
        .all()

    for p in old_payments:
        p.status = "expired"
        p.status_reason = reason

    service.price = new_price

    db.add(CaseStatusLog(
        case_id=service.case_id,
        status_title="Service Updated",
        status_description=f"₹{new_price} - {reason}"
    ))

    db.commit()

    return {"message": "Service updated"}


# 💸 Refund
@app.post("/refund-payment")
def refund_payment(payment_id: int, refund_amount: int, reason: str, db: Session = Depends(get_db)):

    payment = db.query(Payment).filter(Payment.id == payment_id).first()

    if not payment or payment.status != "paid":
        return {"error": "Invalid payment"}

    payment.status = "refunded"
    payment.refund_amount = refund_amount
    payment.refund_status = "processed"
    payment.status_reason = reason

    service = db.query(ServiceItem).filter(ServiceItem.id == payment.service_item_id).first()

    db.add(CaseStatusLog(
        case_id=service.case_id,
        status_title="Refund Issued",
        status_description=f"₹{refund_amount} refunded - {reason}"
    ))

    db.commit()

    return {"message": "Refund processed"}




@app.post("/verify-payment")
def verify_payment(
    data: dict = Body(...),
    db: Session = Depends(get_db)
):
    razorpay_order_id = data.get("razorpay_order_id")
    razorpay_payment_id = data.get("razorpay_payment_id")

    if not razorpay_order_id:
        return {"error": "Missing order_id"}

    payment = db.query(Payment)\
        .filter(Payment.razorpay_order_id == razorpay_order_id)\
        .first()

    if not payment:
        return {"error": "Payment not found"}

    if payment.status == "paid":
        return {"message": "Already processed"}

    payment.status = "paid"
    payment.razorpay_payment_id = razorpay_payment_id
    payment.status_reason = "frontend success"

    service = db.query(ServiceItem)\
        .filter(ServiceItem.id == payment.service_item_id)\
        .first()

    if service:
        service.status = "approved"

        db.add(CaseStatusLog(
            case_id=service.case_id,
            status_title="Payment Received",
            status_description=f"₹{payment.amount} paid"
        ))

    db.commit()

    return {"message": "Payment verified"}  
    
    
@app.post("/payment-failed")
def payment_failed(
    data: dict = Body(...),
    db: Session = Depends(get_db)
):
    razorpay_order_id = data.get("razorpay_order_id")
    razorpay_payment_id = data.get("razorpay_payment_id")
    reason = data.get("reason")

    payment = db.query(Payment)\
        .filter(Payment.razorpay_order_id == razorpay_order_id)\
        .first()

    if not payment:
        return {"error": "Payment not found"}

    payment.status = "failed"
    payment.razorpay_payment_id = razorpay_payment_id
    payment.status_reason = reason

    db.commit()

    return {"message": "Payment failed recorded"}
