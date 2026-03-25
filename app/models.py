from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, JSON
from sqlalchemy.orm import declarative_base
from datetime import datetime

Base = declarative_base()


# 🧩 CASES
class Case(Base):
    __tablename__ = "cases"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String)
    description = Column(Text)
    status = Column(String, default="open")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)


# 🧩 STATUS LOGS (Timeline)
class CaseStatusLog(Base):
    __tablename__ = "case_status_logs"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id"))
    status_title = Column(String)
    status_description = Column(Text)
    meta_data = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


# 🧩 CHAT MESSAGES
class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id"))
    sender_type = Column(String)  # user / agent
    message = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


# 🧩 SERVICE ITEMS
class ServiceItem(Base):
    __tablename__ = "service_items"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id"))
    title = Column(String)
    description = Column(Text)
    status = Column(String, default="pending")
    price = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)


# 🧩 PAYMENTS (UPDATED ✅)
# 🧩 PAYMENTS
class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    service_item_id = Column(Integer, ForeignKey("service_items.id"))

    amount = Column(Integer)
    status = Column(String, default="created")

    # 🔥 Razorpay fields
    razorpay_order_id = Column(String, nullable=True)
    razorpay_payment_id = Column(String, nullable=True)

    payment_provider = Column(String, default="razorpay")

    # ✅ ADD THIS HERE
    status_reason = Column(String, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)


# 🧩 RATINGS
class Rating(Base):
    __tablename__ = "ratings"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id"))
    rating = Column(Integer)
    comment = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
