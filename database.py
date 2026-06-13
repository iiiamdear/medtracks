from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os

# ดึง DATABASE_URL จาก Environment Variable
# ถ้าไม่มีให้ใช้ SQLite สำหรับ local development
SQLALCHEMY_DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "sqlite:///./medtrack.db"
)

# Render PostgreSQL ใช้ postgres:// แต่ SQLAlchemy ต้องการ postgresql://
if SQLALCHEMY_DATABASE_URL.startswith("postgres://"):
    SQLALCHEMY_DATABASE_URL = SQLALCHEMY_DATABASE_URL.replace(
        "postgres://", "postgresql://", 1
    )

# สร้าง engine ให้ถูกต้องตามประเภทฐานข้อมูล
if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        connect_args={"check_same_thread": False}
    )
else:
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        pool_pre_ping=True,       # เช็ค connection ก่อนใช้งาน
        pool_recycle=300,         # recycle connection ทุก 5 นาที
        pool_size=5,              # จำนวน connection pool
        max_overflow=10           # connection เพิ่มเติมสูงสุด
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()