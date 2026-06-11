from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text, Boolean
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime, timezone, timedelta

# ===== TIMEZONE ไทย =====
TH_TZ = timezone(timedelta(hours=7))

def now_th():
    return datetime.now(TH_TZ)


class User(Base):
    __tablename__ = "users"

    id       = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    password = Column(String, nullable=False)
    role     = Column(String, default="user", nullable=False)

    documents = relationship("Document", back_populates="user")


class Pharmacist(Base):
    __tablename__ = "pharmacists"

    id    = Column(Integer, primary_key=True, index=True)
    name  = Column(String, nullable=False)
    phone = Column(String, default="")
    email = Column(String, default="")

    documents = relationship("Document", back_populates="pharmacist")


class Medicine(Base):
    __tablename__ = "medicines"

    id         = Column(Integer, primary_key=True, index=True)
    code       = Column(String, unique=True, index=True, nullable=True)
    name       = Column(String, nullable=False)
    unit       = Column(String, nullable=False, default="เม็ด")
    price      = Column(Float,  default=0.0, nullable=False)
    created_at = Column(DateTime(timezone=True), default=now_th)

    items = relationship("DocumentItem", back_populates="medicine")


class Document(Base):
    __tablename__ = "documents"

    id           = Column(Integer, primary_key=True, index=True)
    hn           = Column(String,  nullable=False)
    patient_name = Column(String,  nullable=False)
    rights       = Column(String,  nullable=False)
    doctor       = Column(String,  nullable=False)
    note         = Column(Text,    default="")
    total_price  = Column(Float,   default=0.0, nullable=False)

    pharmacist_id = Column(Integer, ForeignKey("pharmacists.id"), nullable=True)
    user_id       = Column(Integer, ForeignKey("users.id"),       nullable=True)

    created_at  = Column(DateTime(timezone=True), default=now_th, nullable=False)
    is_finished = Column(Boolean,  default=False, nullable=False)
    finished_at = Column(DateTime(timezone=True), nullable=True)

    # current_status: 'step1', 'step2', 'step3', 'step4'
    current_status = Column(String, default="step1", nullable=False)

    # Step 1 - เภสัชกรจัดส่งเอกสาร
    step1_scanned_at = Column(DateTime(timezone=True), nullable=True)
    step1_name       = Column(String, nullable=True)

    # Step 2 - งานประกันรับเอกสาร
    step2_scanned_at = Column(DateTime(timezone=True), nullable=True)
    step2_name       = Column(String, nullable=True)

    # Step 3 - งานธุรการ
    step3_scanned_at = Column(DateTime(timezone=True), nullable=True)
    step3_name       = Column(String, nullable=True)

    # Step 4 - งานจัดซื้อยา
    step4_scanned_at = Column(DateTime(timezone=True), nullable=True)
    step4_name       = Column(String, nullable=True)

    pharmacist = relationship("Pharmacist", back_populates="documents")
    user       = relationship("User",       back_populates="documents")
    items      = relationship(
        "DocumentItem",
        back_populates="document",
        cascade="all, delete-orphan"
    )

    # 💡 Helper Properties สำหรับนำไปแสดงผลหน้าเว็บได้ทันที
    @property
    def current_step_num(self):
        mapping = {"step1": 1, "step2": 2, "step3": 3, "step4": 4}
        return mapping.get(self.current_status, 1)

    @property
    def current_status_th(self):
        mapping = {
            "step1": "เภสัชกรจัดส่งเอกสาร",
            "step2": "งานประกันรับเอกสาร",
            "step3": "งานธุรการรับเอกสาร",
            "step4": "งานจัดซื้อรับเอกสาร"
        }
        return mapping.get(self.current_status, "ไม่ทราบสถานะ")


class DocumentItem(Base):
    __tablename__ = "document_items"

    id          = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    medicine_id = Column(Integer, ForeignKey("medicines.id"), nullable=False)
    dose        = Column(String,  default="")
    quantity    = Column(Integer, default=1,   nullable=False)
    unit_price  = Column(Float,   default=0.0, nullable=False)
    total_price = Column(Float,   default=0.0, nullable=False)

    document = relationship("Document", back_populates="items")
    medicine = relationship("Medicine", back_populates="items")

    @property
    def price(self):
        return self.quantity * self.unit_price