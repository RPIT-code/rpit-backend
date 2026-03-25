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

    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )


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

    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )


# 🧩 PAYMENTS (FINAL 🔥)
class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    service_item_id = Column(Integer, ForeignKey("service_items.id"))

    amount = Column(Integer)

    # core status
    status = Column(String, default="created")

    # 🔥 event tracking (important)
    event_type = Column(String, default="created")

    # Razorpay mapping
    razorpay_order_id = Column(String, nullable=True)
    razorpay_payment_id = Column(String, nullable=True)

    payment_provider = Column(String, default="razorpay")

    # why status changed
    status_reason = Column(String, nullable=True)

    # 💸 refund support
    refund_amount = Column(Integer, nullable=True)
    refund_status = Column(String, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )


# 🧩 RATINGS
class Rating(Base):
    __tablename__ = "ratings"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("cases.id"))

    rating = Column(Integer)
    comment = Column(Text)

    created_at = Column(DateTime, default=datetime.utcnow)
