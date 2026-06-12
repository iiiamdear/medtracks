from contextlib import asynccontextmanager
from datetime import datetime
from typing import List, Optional
import base64
import hashlib
import io
import os

import qrcode
from fastapi import FastAPI, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, joinedload  # 🔥 เพิ่ม joinedload สำหรับดึงข้อมูลความสัมพันธ์ยา

import models
import database


# สร้างตารางในฐานข้อมูล (หากยังไม่มี)
models.Base.metadata.create_all(bind=database.engine)


# ===== HELPERS =====

def hash_password(p: str) -> str:
    return hashlib.sha256(p.encode()).hexdigest()


def verify_password(plain: str, hashed: str) -> bool:
    return hash_password(plain) == hashed


def get_current_user(request: Request, db: Session):
    username = request.cookies.get("username")
    if not username:
        return None
    return db.query(models.User).filter(models.User.username == username).first()


def check_auth(request: Request, db: Session, allowed_roles: List[str] = None):
    user = get_current_user(request, db)
    if not user:
        return None, RedirectResponse(url="/login", status_code=302)

    if allowed_roles and user.role not in allowed_roles:
        html_content = """
        <html>
            <head>
                <title>Access Denied</title>
                <meta charset="utf-8">
                <meta name="viewport" content="width=device-width, initial-scale=1">
                <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
            </head>
            <body class="bg-light d-flex align-items-center justify-content-center" style="height: 100vh;">
                <div class="text-center p-5 bg-white rounded shadow-sm border" style="max-width: 450px;">
                    <h1 class="text-danger mb-3 fw-bold">403 Access Denied</h1>
                    <p class="text-muted fs-5">บัญชีของคุณไม่มีสิทธิ์เข้าใช้งานระบบในส่วนนี้</p>
                    <a href="/" class="btn btn-primary px-4 mt-3">กลับหน้าหลัก</a>
                </div>
            </body>
        </html>
        """
        return None, HTMLResponse(content=html_content, status_code=403)

    return user, None


def make_qr_b64(url: str) -> str:
    qr = qrcode.QRCode(version=1, box_size=6, border=4)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def get_base_url(request: Request) -> str:
    return str(request.base_url).rstrip("/")


def get_step_status(doc) -> dict:
    # ปรับปรุงให้ตรวจเช็กไล่ลำดับย้อนกลับจาก 4 ลงไป 0 และป้องกันข้อผิดพลาดกรณีคอลัมน์ในฐานข้อมูลยังไม่อัปเดต
    if getattr(doc, 'step4_scanned_at', None):
        return {"current": 4, "label": "งานจัดซื้อรับแล้ว", "color": "success"}
    elif getattr(doc, 'step3_scanned_at', None):
        return {"current": 3, "label": "งานธุรการรับแล้ว", "color": "indigo"}
    elif doc.step2_scanned_at:
        return {"current": 2, "label": "งานประกันรับแล้ว", "color": "primary"}
    elif doc.step1_scanned_at:
        return {"current": 1, "label": "เภสัชกรจัดส่งแล้ว", "color": "warning"}
    else:
        return {"current": 0, "label": "รอดำเนินการ", "color": "secondary"}


# ===== LIFESPAN =====

@asynccontextmanager
async def lifespan(app: FastAPI):
    db = database.SessionLocal()
    try:
        if not db.query(models.User).filter(models.User.username == "admin").first():
            db.add(models.User(
                username="admin",
                password=hash_password("admin1234"),
                role="admin"
            ))
            print("✅ Created default admin: admin / admin1234")

        if not db.query(models.User).filter(models.User.username == "staff").first():
            db.add(models.User(
                username="staff",
                password=hash_password("staff1234"),
                role="user"
            ))
            print("✅ Created default staff: staff / staff1234")

        db.commit()
    finally:
        db.close()
    yield


app = FastAPI(lifespan=lifespan)
templates = Jinja2Templates(directory="templates")

# ----- เพิ่มระบบลงทะเบียน Custom Filter 'thdate' เพื่อแก้ปัญหา Jinja2 Error -----
def thdate_filter(value):
    if not value:
        return ""
    if isinstance(value, datetime):
        thai_year = value.year + 543
        return value.strftime(f"%d/%m/{thai_year} %H:%M")
    return str(value)

templates.env.filters["thdate"] = thdate_filter
# --------------------------------------------------------------------------

os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")


# ===== AUTH =====

@app.get("/login", response_class=HTMLResponse)
def login_get(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"error": None, "success_msg": None, "user": None}
    )


@app.post("/login")
def login_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(database.get_db)
):
    user = db.query(models.User).filter(models.User.username == username).first()

    if not user or not verify_password(password, user.password):
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "error": "ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง",
                "success_msg": None,
                "user": None
            }
        )

    response = RedirectResponse(url="/", status_code=302)
    response.set_cookie("username", username, httponly=True)
    return response


@app.post("/logout")
def logout():
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie("username")
    return response


# ===== USER MANAGEMENT =====

@app.get("/users", response_class=HTMLResponse)
def users_get(request: Request, db: Session = Depends(database.get_db)):
    user, response = check_auth(request, db, allowed_roles=["admin"])
    if response:
        return response

    users = db.query(models.User).all()
    return templates.TemplateResponse(
        request=request,
        name="users.html",
        context={"user": user, "users": users}
    )


@app.post("/users/add")
def user_add(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    role: str = Form(...),
    db: Session = Depends(database.get_db)
):
    user, response = check_auth(request, db, allowed_roles=["admin"])
    if response:
        return response

    clean_username = username.strip()
    exist_user = db.query(models.User).filter(models.User.username == clean_username).first()
    if exist_user:
        return RedirectResponse(url="/users?error=exists", status_code=302)

    db.add(models.User(
        username=clean_username,
        password=hash_password(password),
        role=role
    ))
    db.commit()
    return RedirectResponse(url="/users", status_code=302)


@app.post("/users/delete/{user_id}")
def user_delete(user_id: int, request: Request, db: Session = Depends(database.get_db)):
    user, response = check_auth(request, db, allowed_roles=["admin"])
    if response:
        return response

    if user.id == user_id:
        return RedirectResponse(url="/users?error=self_delete", status_code=302)

    u = db.query(models.User).filter(models.User.id == user_id).first()
    if u:
        db.delete(u)
        db.commit()
    return RedirectResponse(url="/users", status_code=302)


# ===== HOME =====

@app.get("/", response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(database.get_db)):
    user, response = check_auth(request, db, allowed_roles=["admin", "user"])
    if response:
        return response

    active_docs = db.query(models.Document).filter(
        models.Document.is_finished == False
    ).order_by(models.Document.created_at.desc()).all()

    for doc in active_docs:
        doc.step_status = get_step_status(doc)

    # 🛠️ แก้ไขเพิ่มคีย์ "step4" ให้ครบถ้วนเพื่อส่งไปนับสถิติบนหน้าเว็บ Template
    stats = {
        "total_active": len(active_docs),
        "step0": sum(1 for d in active_docs if d.step_status["current"] == 0),
        "step1": sum(1 for d in active_docs if d.step_status["current"] == 1),
        "step2": sum(1 for d in active_docs if d.step_status["current"] == 2),
        "step3": sum(1 for d in active_docs if d.step_status["current"] == 3),
        "step4": sum(1 for d in active_docs if d.step_status["current"] == 4),
        "total_meds": db.query(models.Medicine).count(),
        "total_users": db.query(models.User).count(),
    }

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"user": user, "docs": active_docs, "stats": stats}
    )


# ===== CREATE =====

@app.get("/create", response_class=HTMLResponse)
def create_get(request: Request, db: Session = Depends(database.get_db)):
    user, response = check_auth(request, db, allowed_roles=["admin", "user"])
    if response:
        return response

    medicines = db.query(models.Medicine).all()
    pharmacists = db.query(models.Pharmacist).all()
    med_list = [
        {"id": m.id, "name": m.name, "price": float(m.price), "unit": m.unit}
        for m in medicines
    ]

    return templates.TemplateResponse(
        request=request,
        name="create.html",
        context={"user": user, "medicines": med_list, "pharmacists": pharmacists}
    )


@app.post("/create")
async def create_post(
    request: Request,
    hn: str = Form(...),
    patient_name: str = Form(...),
    rights: str = Form(...),
    doctor: str = Form(...),
    pharmacist_id: Optional[str] = Form(None),
    note: str = Form(""),
    db: Session = Depends(database.get_db)
):
    user, response = check_auth(request, db, allowed_roles=["admin", "user"])
    if response:
        return response

    # 🛠️ แกะข้อมูล Form Data เพื่อดึงอาร์เรย์รายการยาจากหน้าฟอร์มตรง ๆ 
    form_data = await request.form()
    
    medicine_ids = form_data.getlist("medicine_ids") or form_data.getlist("medicine_ids[]") or form_data.getlist("medicine_id") or form_data.getlist("medicine_id[]")
    doses = form_data.getlist("doses") or form_data.getlist("doses[]") or form_data.getlist("dose") or form_data.getlist("dose[]")
    quantities = form_data.getlist("quantities") or form_data.getlist("quantities[]") or form_data.getlist("quantity") or form_data.getlist("quantity[]")
    unit_prices = form_data.getlist("unit_prices") or form_data.getlist("unit_prices[]") or form_data.getlist("unit_price") or form_data.getlist("unit_price[]")

    ph_id = int(pharmacist_id) if pharmacist_id and pharmacist_id.strip() else None

    # 1. สร้างหัวเอกสารใบติดตามหลัก
    doc = models.Document(
        hn=hn,
        patient_name=patient_name,
        rights=rights,
        doctor=doctor,
        note=note,
        pharmacist_id=ph_id,
        user_id=user.id,
        created_at=datetime.now()
    )
    db.add(doc)
    db.flush()

    # 2. วนลูปบันทึกรายการยาลงตารางความสัมพันธ์
    grand_total = 0.0
    for i, med_id in enumerate(medicine_ids):
        if not med_id or not med_id.strip():
            continue

        med = db.query(models.Medicine).filter(models.Medicine.id == int(med_id)).first()
        if not med:
            continue

        qty = int(quantities[i]) if i < len(quantities) and quantities[i] else 1
        unit_price = float(unit_prices[i]) if i < len(unit_prices) and unit_prices[i] else float(med.price)
        dose = doses[i] if i < len(doses) else ""
        row_total = qty * unit_price

        # บันทึก Item รายการยา (ความสัมพันธ์ระหว่างเอกสารและตัวยา)
        item = models.DocumentItem(
            document_id=doc.id,
            medicine_id=med.id,
            dose=dose,
            quantity=qty,
            unit_price=unit_price,
            total_price=row_total
        )
        db.add(item)
        grand_total += row_total

    doc.total_price = grand_total
    db.commit()
    return RedirectResponse(url=f"/document/{doc.id}", status_code=302)


# ===== FINISH =====

@app.post("/finish/{doc_id}")
def finish_document(doc_id: int, request: Request, db: Session = Depends(database.get_db)):
    user, response = check_auth(request, db, allowed_roles=["admin", "user"])
    if response:
        return response

    doc = db.query(models.Document).filter(models.Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="ไม่พบเอกสาร")

    doc.is_finished = True
    doc.finished_at = datetime.now()
    db.commit()
    return RedirectResponse(url="/", status_code=302)


# ===== DELETE DOCUMENT =====

@app.post("/delete/{doc_id}")
def delete_document(doc_id: int, request: Request, db: Session = Depends(database.get_db)):
    user, response = check_auth(request, db, allowed_roles=["admin"])
    if response:
        return response

    doc = db.query(models.Document).filter(models.Document.id == doc_id).first()
    if doc:
        db.delete(doc)
        db.commit()
    return RedirectResponse(url="/", status_code=302)


# ===== HISTORY =====

@app.get("/history", response_class=HTMLResponse)
def history(request: Request, search: str = "", db: Session = Depends(database.get_db)):
    user, response = check_auth(request, db, allowed_roles=["admin", "user"])
    if response:
        return response

    query = db.query(models.Document).filter(models.Document.is_finished == True)
    if search:
        query = query.filter(
            models.Document.patient_name.contains(search) |
            models.Document.hn.contains(search)
        )

    docs = query.order_by(models.Document.finished_at.desc()).all()
    for doc in docs:
        doc.step_status = get_step_status(doc)

    return templates.TemplateResponse(
        request=request,
        name="history.html",
        context={"user": user, "docs": docs, "search": search}
    )


# ===== DOCUMENT + QR (ดึงข้อมูลเอกสารและตารางยาร่วมอย่างสมบูรณ์) =====

@app.get("/document/{doc_id}", response_class=HTMLResponse)
def view_document(doc_id: int, request: Request, db: Session = Depends(database.get_db)):
    user, response = check_auth(request, db, allowed_roles=["admin", "user"])
    if response:
        return response

    doc = db.query(models.Document)\
            .options(joinedload(models.Document.pharmacist))\
            .filter(models.Document.id == doc_id).first()
            
    if not doc:
        raise HTTPException(status_code=404, detail="ไม่พบเอกสาร")

    items = db.query(models.DocumentItem)\
              .options(joinedload(models.DocumentItem.medicine))\
              .filter(models.DocumentItem.document_id == doc_id).all()
    
    for item in items:
        if not hasattr(item, 'price_per_unit') or item.price_per_unit is None:
            item.price_per_unit = item.unit_price
        if not hasattr(item, 'usage_instruction') or item.usage_instruction is None:
            item.usage_instruction = item.dose

    doc.items = items

    doc.step_status = get_step_status(doc)
    base_url = get_base_url(request)
    track_url = f"{base_url}/track/{doc_id}"
    qr_b64 = make_qr_b64(track_url)

    return templates.TemplateResponse(
        request=request,
        name="document.html",
        context={"doc": doc, "qr_b64": qr_b64, "track_url": track_url, "user": user}
    )


# ===== TRACKING =====

@app.get("/track/{doc_id}", response_class=HTMLResponse)
def track_get(doc_id: int, request: Request, db: Session = Depends(database.get_db)):
    doc = db.query(models.Document).filter(models.Document.id == doc_id).first()
    if not doc:
        return HTMLResponse("<h2>ไม่พบเอกสาร</h2>", status_code=404)

    doc.step_status = get_step_status(doc)
    return templates.TemplateResponse(
        request=request,
        name="track.html",
        context={"doc": doc, "success": False, "error": None, "user": None}
    )


@app.post("/track/{doc_id}")
def track_post(
    doc_id: int,
    request: Request,
    step: int = Form(...),
    scanner_name: str = Form(...),
    db: Session = Depends(database.get_db)
):
    doc = db.query(models.Document).filter(models.Document.id == doc_id).first()
    if not doc:
        return HTMLResponse("<h2>ไม่พบเอกสาร</h2>", status_code=404)

    now = datetime.now()
    error = None

    if doc.is_finished:
        error = "เอกสารนี้ปิดแล้ว ไม่สามารถสแกนได้"
    elif step == 1 and not doc.step1_scanned_at:
        doc.step1_scanned_at = now
        doc.step1_name = scanner_name
    elif step == 2 and doc.step1_scanned_at and not doc.step2_scanned_at:
        doc.step2_scanned_at = now
        doc.step2_name = scanner_name
    elif step == 3 and doc.step2_scanned_at and not getattr(doc, 'step3_scanned_at', None):
        # 💼 สเต็ปที่ 3: งานธุรการรับฝากเอกสาร
        doc.step3_scanned_at = now
        doc.step3_name = scanner_name
    elif step == 4 and getattr(doc, 'step3_scanned_at', None) and not getattr(doc, 'step4_scanned_at', None):
        # 🛒 สเต็ปที่ 4: งานจัดซื้อรับเอกสาร (ขั้นตอนสุดท้าย)
        doc.step4_scanned_at = now
        doc.step4_name = scanner_name
    else:
        error = "ไม่สามารถบันทึกได้ กรุณาตรวจสอบขั้นตอน (ห้ามสแกนข้ามขั้นตอนเด็ดขาด)"

    if not error:
        db.commit()
        db.refresh(doc)

    doc.step_status = get_step_status(doc)
    return templates.TemplateResponse(
        request=request,
        name="track.html",
        context={"doc": doc, "success": error is None, "error": error, "user": None}
    )


# ===== MEDICINES =====

@app.get("/medicines", response_class=HTMLResponse)
def medicines_get(request: Request, db: Session = Depends(database.get_db)):
    user, response = check_auth(request, db, allowed_roles=["admin", "user"])
    if response:
        return response

    meds = db.query(models.Medicine).order_by(models.Medicine.name).all()
    return templates.TemplateResponse(
        request=request,
        name="medicines.html",
        context={"user": user, "medicines": meds}
    )


@app.post("/medicines/add")
def medicine_add(
    request: Request,
    code: str = Form(""),
    name: str = Form(...),
    unit: str = Form(...),
    price: float = Form(...),
    db: Session = Depends(database.get_db)
):
    user, response = check_auth(request, db, allowed_roles=["admin"])
    if response:
        return response

    clean_code = code.strip() if code.strip() else None

    if clean_code:
        exists = db.query(models.Medicine).filter(models.Medicine.code == clean_code).first()
        if exists:
            return RedirectResponse(url="/medicines?error=duplicate_code", status_code=302)

    db.add(models.Medicine(
        code=clean_code,
        name=name,
        unit=unit,
        price=price
    ))
    db.commit()
    return RedirectResponse(url="/medicines", status_code=302)


@app.post("/medicines/edit/{med_id}")
def medicine_edit(
    med_id: int,
    request: Request,
    code: str = Form(""),
    name: str = Form(...),
    unit: str = Form(...),
    price: float = Form(...),
    db: Session = Depends(database.get_db)
):
    user, response = check_auth(request, db, allowed_roles=["admin"])
    if response:
        return response

    med = db.query(models.Medicine).filter(models.Medicine.id == med_id).first()
    if med:
        clean_code = code.strip() if code.strip() else None

        if clean_code:
            exists = db.query(models.Medicine).filter(
                models.Medicine.code == clean_code,
                models.Medicine.id != med_id
            ).first()
            if exists:
                return RedirectResponse(url="/medicines?error=duplicate_code", status_code=302)

        med.code = clean_code
        med.name = name
        med.unit = unit
        med.price = price
        db.commit()

    return RedirectResponse(url="/medicines", status_code=302)


@app.post("/medicines/delete/{med_id}")
def medicine_delete(med_id: int, request: Request, db: Session = Depends(database.get_db)):
    user, response = check_auth(request, db, allowed_roles=["admin"])
    if response:
        return response

    med = db.query(models.Medicine).filter(models.Medicine.id == med_id).first()
    if med:
        used = db.query(models.DocumentItem).filter(models.DocumentItem.medicine_id == med_id).first()
        if used:
            return RedirectResponse(url="/medicines?error=in_use", status_code=302)

        db.delete(med)
        db.commit()

    return RedirectResponse(url="/medicines", status_code=302)


# ===== PHARMACISTS =====

@app.get("/pharmacists", response_class=HTMLResponse)
def pharmacists_get(request: Request, db: Session = Depends(database.get_db)):
    user, response = check_auth(request, db, allowed_roles=["admin", "user"])
    if response:
        return response

    pharmacists = db.query(models.Pharmacist).all()
    return templates.TemplateResponse(
        request=request,
        name="pharmacists.html",
        context={"user": user, "pharmacists": pharmacists}
    )


@app.post("/pharmacists/add")
def pharmacist_add(
    request: Request,
    name: str = Form(...),
    phone: str = Form(""),
    email: str = Form(""),
    db: Session = Depends(database.get_db)
):
    user, response = check_auth(request, db, allowed_roles=["admin"])
    if response:
        return response

    db.add(models.Pharmacist(name=name, phone=phone, email=email))
    db.commit()
    return RedirectResponse(url="/pharmacists", status_code=302)


@app.post("/pharmacists/delete/{ph_id}")
def pharmacist_delete(ph_id: int, request: Request, db: Session = Depends(database.get_db)):
    user, response = check_auth(request, db, allowed_roles=["admin"])
    if response:
        return response

    ph = db.query(models.Pharmacist).filter(models.Pharmacist.id == ph_id).first()
    if ph:
        used = db.query(models.Document).filter(models.Document.pharmacist_id == ph_id).first()
        if used:
            return RedirectResponse(url="/pharmacists?error=in_use", status_code=302)

        db.delete(ph)
        db.commit()

    return RedirectResponse(url="/pharmacists", status_code=302)