from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text, Boolean
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    password = Column(String, nullable=False)
    role = Column(String, default="user", nullable=False)

    documents = relationship("Document", back_populates="user")


class Pharmacist(Base):
    __tablename__ = "pharmacists"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    phone = Column(String, default="")
    email = Column(String, default="")

    documents = relationship("Document", back_populates="pharmacist")


class Medicine(Base):
    __tablename__ = "medicines"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, index=True, nullable=True)   # รหัสยา
    name = Column(String, nullable=False)                           # ชื่อยา
    unit = Column(String, nullable=False, default="เม็ด")           # หน่วย
    price = Column(Float, default=0.0, nullable=False)              # ราคาต่อหน่วย
    created_at = Column(DateTime, default=datetime.now)

    items = relationship("DocumentItem", back_populates="medicine")


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    hn = Column(String, nullable=False)
    patient_name = Column(String, nullable=False)
    rights = Column(String, nullable=False)
    doctor = Column(String, nullable=False)
    note = Column(Text, default="")
    total_price = Column(Float, default=0.0, nullable=False)

    pharmacist_id = Column(Integer, ForeignKey("pharmacists.id"), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.now, nullable=False)

    is_finished = Column(Boolean, default=False, nullable=False)
    finished_at = Column(DateTime, nullable=True)

    step1_scanned_at = Column(DateTime, nullable=True)
    step1_name = Column(String, nullable=True)

    step2_scanned_at = Column(DateTime, nullable=True)
    step2_name = Column(String, nullable=True)

    step3_scanned_at = Column(DateTime, nullable=True)
    step3_name = Column(String, nullable=True)

    pharmacist = relationship("Pharmacist", back_populates="documents")
    user = relationship("User", back_populates="documents")
    items = relationship(
        "DocumentItem",
        back_populates="document",
        cascade="all, delete-orphan"
    )


class DocumentItem(Base):
    __tablename__ = "document_items"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    medicine_id = Column(Integer, ForeignKey("medicines.id"), nullable=False)
    dose = Column(String, default="")                    # วิธีใช้ยา
    quantity = Column(Integer, default=1, nullable=False)   # จำนวน
    unit_price = Column(Float, default=0.0, nullable=False) # ราคาต่อหน่วย ณ ตอนสร้าง
    total_price = Column(Float, default=0.0, nullable=False) # quantity × unit_price

    document = relationship("Document", back_populates="items")
    medicine = relationship("Medicine", back_populates="items")

    # 🛠️ [เพิ่มเพื่อรองรับ HTML] ทำ Alias ส่งค่าราคารวม
    @property
    def price(self):
        return self.total_price

    # 🛠️ [เพิ่มเพื่อรองรับ HTML] ถ้าหน้าบ้านเรียกใช้ price_per_unit ให้ดึงค่าจาก unit_price
    @property
    def price_per_unit(self):
        return self.unit_price

    # 🛠️ [เพิ่มเพื่อรองรับ HTML] ถ้าหน้าบ้านเรียกใช้ usage_instruction ให้ดึงค่าจาก dose
    @property
    def usage_instruction(self):
        return self.dose