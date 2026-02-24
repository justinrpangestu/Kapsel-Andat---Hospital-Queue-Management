# main.py - FINAL CLEAN VERSION (ENGLISH)

from pydoc import doc

from annotated_types import doc
from fastapi import FastAPI, Depends, HTTPException, status, APIRouter
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from sqlalchemy import text, func
from typing import List, Optional
from datetime import datetime, date, time, timedelta
import random
import pandas as pd
from contextlib import asynccontextmanager
from faker import Faker
import re

# --- INTERNAL MODULES ---
import storage
import schemas
import security
import csv_utils

# =================================================================
# 1. SETUP & LIFESPAN
# =================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Create tables if they don't exist
    print("🏥 Smart Hospital System Starting...")
    storage.Base.metadata.create_all(bind=storage.engine)
    yield
    # Shutdown
    print("🛑 Smart Hospital System Shutting Down...")

app = FastAPI(
    title="Smart Hospital System",
    description="Hospital Management API (English Version)",
    version="4.0.0",
    lifespan=lifespan
)

# Database Dependency
def get_db():
    db = storage.SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- HELPER FUNCTIONS ---
def clean_simple_name(full_name: str) -> str:
    """Removes titles and returns cleaned name."""
    if not full_name: return "NoName"
    name_no_suffix = full_name.split(',')[0]
    name_clean = re.sub(r'^(dr\.|drs\.|dra\.|ir\.|prof\.|h\.|hj\.|ns\.|mr\.|mrs\.)\s*', '', name_no_suffix, flags=re.IGNORECASE)
    parts = name_clean.replace('.', ' ').split()
    return parts[-1].title() if parts else "User"

def get_estimated_wait_time(db: Session, doctor_id: int, current_queue_seq: int, v_date: date):
    # 1. Calculate average service duration for this doctor from past data (Finished status)
    avg_service_query = db.query(
        func.avg(func.timestampdiff(text("MINUTE"), storage.TabelPelayanan.clinic_entry_time, storage.TabelPelayanan.completion_time))
    ).filter(
        storage.TabelPelayanan.doctor_id_ref == doctor_id,
        storage.TabelPelayanan.status_pelayanan == "Finished"
    ).scalar()

    # Default to 15 minutes if no historical data exists
    avg_service_time = float(avg_service_query) if avg_service_query else 15.0

    # 2. Count people still ahead in the queue for the same doctor today
    people_ahead = db.query(storage.TabelPelayanan).filter(
        storage.TabelPelayanan.doctor_id_ref == doctor_id,
        storage.TabelPelayanan.visit_date == v_date,
        storage.TabelPelayanan.queue_sequence < current_queue_seq,
        storage.TabelPelayanan.status_pelayanan.in_(["Registered", "Waiting", "Serving"])
    ).count()

    return round(people_ahead * avg_service_time)

# --- SECURITY GUARD (RBAC) ---
def require_role(allowed_roles: list):
    def role_checker(current_user: dict = Depends(security.get_current_user_token)):
        if current_user['role'] not in allowed_roles:
            raise HTTPException(
                status_code=403, 
                detail=f"Access Denied! Role '{current_user['role']}' is not authorized."
            )
        return current_user
    return role_checker

# =================================================================
# 2. ROUTER DEFINITIONS
# =================================================================

router_auth = APIRouter(tags=["Authentication"])
router_public = APIRouter(tags=["Public Services"])
router_ops = APIRouter(tags=["Operational"])
router_monitor = APIRouter(tags=["Monitor Display"])
router_admin = APIRouter(tags=["Administrator"])
router_analytics = APIRouter(tags=["Analytics"])

# =================================================================
# 3. AUTHENTICATION ROUTER
# =================================================================

@router_auth.post("/login", response_model=schemas.Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    # Normalize input
    clean_username = form_data.username.lower().strip()
    
    user = db.query(storage.TabelUser).filter(storage.TabelUser.username == clean_username).first()
    
    if not user or not security.verify_password(form_data.password, user.password):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    
    # DETERMINE MEMBER STATUS
    status_label = "User"
    if user.role == "admin":
        status_label = "Admin"
    elif user.role in ["perawat", "administrasi"]:
        status_label = "Staff"
    elif user.role == "pasien":
        # Check historical visits
        cnt = db.query(storage.TabelPelayanan).filter(
            storage.TabelPelayanan.username == user.username,
            storage.TabelPelayanan.status_pelayanan == "Finished"
        ).count()
        status_label = "Existing Patient" if cnt > 0 else "New Patient"
    
    token = security.create_access_token(data={"sub": user.username, "role": user.role})
    
    return {
        "access_token": token, 
        "token_type": "bearer", 
        "role": user.role, 
        "nama": user.nama_lengkap, 
        "status_member": status_label 
    }

@router_auth.post("/register", response_model=schemas.Token)
def register(user: schemas.UserCreate, db: Session = Depends(get_db)):
    clean_username = user.username.lower().strip()

    if db.query(storage.TabelUser).filter(storage.TabelUser.username == clean_username).first():
        raise HTTPException(400, "Username already exists.")
    
    new_user = storage.TabelUser(
        username=clean_username, 
        password=security.get_password_hash(user.password),
        role="pasien", 
        nama_lengkap=user.nama_lengkap
    )
    db.add(new_user); db.commit(); db.refresh(new_user)
    
    token = security.create_access_token(data={"sub": new_user.username, "role": new_user.role})
    return {
        "access_token": token, "token_type": "bearer", 
        "role": new_user.role, "nama": new_user.nama_lengkap, "status_member": "New Patient"
    }

# =================================================================
# 4. ADMIN ROUTER
# =================================================================

@router_admin.get("/doctors")
def get_doctors(db: Session = Depends(get_db)):
    return db.query(storage.TabelDokter).all()

@router_admin.post("/doctors")
def add_doctor(p: schemas.DoctorCreate, db: Session = Depends(get_db)):
    if not db.query(storage.TabelPoli).filter(storage.TabelPoli.poli == p.poli).first():
        raise HTTPException(404, "Clinic/Poli not found")
    
    clean_name = f"dr. {clean_simple_name(p.dokter)}"
    max_id = db.query(func.max(storage.TabelDokter.doctor_id)).scalar()
    next_id = 1 if max_id is None else max_id + 1
    
    # Generate Code
    last = db.query(storage.TabelDokter).filter(storage.TabelDokter.poli == p.poli).order_by(storage.TabelDokter.doctor_id.desc()).first()
    try: nxt_num = int(last.doctor_code.split('-')[-1]) + 1 if last else 1
    except: nxt_num = 1
    prefix = db.query(storage.TabelPoli).filter(storage.TabelPoli.poli == p.poli).first().prefix
    code = f"{prefix}-{nxt_num:03d}"
    
    new = storage.TabelDokter(
        doctor_id=next_id, dokter=clean_name, poli=p.poli,
        practice_start_time=datetime.strptime(p.practice_start_time, "%H:%M").time(),
        practice_end_time=datetime.strptime(p.practice_end_time, "%H:%M").time(),
        doctor_code=code, max_patients=p.max_patients
    )
    db.add(new); db.commit(); db.refresh(new)
    return new

@router_admin.delete("/doctors/{id}")
def delete_doctor(id: int, db: Session = Depends(get_db)):
    d = db.query(storage.TabelDokter).filter(storage.TabelDokter.doctor_id == id).first()
    if not d: raise HTTPException(404, "Doctor not found")
    
    patient_count = db.query(storage.TabelPelayanan).filter(storage.TabelPelayanan.doctor_id_ref == id).count()
    if patient_count > 0:
        raise HTTPException(400, detail=f"CANNOT DELETE! This doctor has {patient_count} patient records.")
    
    db.delete(d); db.commit()
    return {"message": "Doctor deleted successfully."}

@router_admin.post("/polis")
def add_poli(p: schemas.PoliCreate, db: Session = Depends(get_db)):
    if db.query(storage.TabelPoli).filter(storage.TabelPoli.poli == p.poli).first():
        raise HTTPException(status_code=400, detail=f"Poli '{p.poli}' already exists.")
        
    if db.query(storage.TabelPoli).filter(storage.TabelPoli.prefix == p.prefix).first():
        raise HTTPException(status_code=400, detail=f"Prefix '{p.prefix}' is already used.")

    new_poli = storage.TabelPoli(poli=p.poli, prefix=p.prefix)
    db.add(new_poli); db.commit()
    return {"message": "Poli added successfully"}

@router_admin.get("/import-random-data")
def import_random_data(count: int = 10, db: Session = Depends(get_db)):
    try:
        fake = Faker('id_ID')
        df_doc, df_pas = csv_utils.get_merged_random_data(count)
        
        c = 0
        for i in range(count):
            # Setup Doctor/Poli from CSV
            if not df_doc.empty:
                row = df_doc.sample(n=1).iloc[0]
                r_poli = schemas.format_poli_name(str(row['poli']))
                r_doc_name = f"dr. {clean_simple_name(str(row['dokter']))}"
                r_prefix = str(row.get('prefix', r_poli[:4].upper())).strip()
                
                if not db.query(storage.TabelPoli).filter(storage.TabelPoli.poli == r_poli).first():
                    db.add(storage.TabelPoli(poli=r_poli, prefix=r_prefix)); db.commit()
                
                doc = db.query(storage.TabelDokter).filter(storage.TabelDokter.dokter == r_doc_name).first()
                if not doc:
                    try: 
                        ts = datetime.strptime(str(row['practice_start_time']), "%H:%M:%S").time()
                        te = datetime.strptime(str(row['practice_end_time']), "%H:%M:%S").time()
                    except: ts=time(8,0); te=time(16,0)
                    mid = db.query(func.max(storage.TabelDokter.doctor_id)).scalar() or 0
                    doc = storage.TabelDokter(doctor_id=mid+1, dokter=r_doc_name, poli=r_poli, 
                                              practice_start_time=ts, practice_end_time=te, 
                                              doctor_code=f"{r_prefix}-001", max_patients=20)
                    db.add(doc); db.commit()
            
            # Setup Patient
            r_nama = clean_simple_name(fake.name())
            uname = r_nama.lower() + str(random.randint(1,999))
            if not db.query(storage.TabelUser).filter(storage.TabelUser.username == uname).first():
                db.add(storage.TabelUser(username=uname, password=security.get_password_hash("123"), role="pasien", nama_lengkap=r_nama))
                db.commit()

            # Logic for Varied Dates
            is_today = random.random() < 0.4 
            r_date = date.today() if is_today else fake.date_between(start_date='-30d', end_date='-1d')
            r_stat = random.choice(["Waiting", "Serving", "Finished"]) if is_today else "Finished"

            # Save Transaction
            new_t = storage.TabelPelayanan(
                username=uname, status_member="Member", nama_pasien=r_nama, poli=r_poli, 
                dokter=doc.dokter, doctor_id_ref=doc.doctor_id, visit_date=r_date, 
                status_pelayanan=r_stat, queue_number=f"{r_prefix}-001-{i:03d}", queue_sequence=i+1
            )
            db.add(new_t); db.commit()
            c += 1
            
        return {"message": f"Successfully imported {c} records."}
    except Exception as e:
        db.rollback()
        raise HTTPException(500, str(e))

# =================================================================
# 5. OPS ROUTER (Scanner & Notes)
# =================================================================

@router_ops.post("/scan-barcode")
def scan_barcode(p: schemas.ScanRequest, db: Session = Depends(get_db)):
    val = p.barcode_data.strip()
    
    # 1. FIND TICKET (Prioritize newest)
    if val.isdigit():
        s = db.query(storage.TabelPelayanan).filter(storage.TabelPelayanan.id == int(val)).first()
    else:
        s = db.query(storage.TabelPelayanan)\
            .filter(storage.TabelPelayanan.queue_number == val)\
            .order_by(storage.TabelPelayanan.id.desc())\
            .first()
    
    if not s: 
        raise HTTPException(404, detail="Ticket not found")

    # 2. STATE MACHINE
    STATE_LVL = {"Registered": 0, "Waiting": 1, "Serving": 2, "Finished": 3}
    LOC_MAP = {"arrival": ("Waiting", 1), "clinic": ("Serving", 2), "finish": ("Finished", 3)}
    
    current_status = s.status_pelayanan if s.status_pelayanan in STATE_LVL else "Registered"
    curr_lvl = STATE_LVL.get(current_status, 0)
    tgt_stat, tgt_lvl = LOC_MAP.get(p.location)

    # A. Validation (No backwards, no skipping)
    if curr_lvl == tgt_lvl:
        return {"status": "Warning", "message": f"Patient is already '{s.status_pelayanan}'."}
    
    if tgt_lvl < curr_lvl:
        return {"status": "Error", "message": f"Backward flow denied! Status is '{s.status_pelayanan}'."}
    
    if tgt_lvl > curr_lvl + 1:
        return {"status": "Error", "message": "Step skipped! Please follow the sequential queue process."}

    if tgt_stat == "Finished" and not s.catatan_medis:
        return {"status": "Error", "message": "Medical notes are required before finishing."}

    # 3. UPDATE DATA (Using a Transaction)
    try:
        now = datetime.now()
        if p.location == "arrival": s.checkin_time = now
        elif p.location == "clinic": s.clinic_entry_time = now
        elif p.location == "finish": s.completion_time = now
        
        s.status_pelayanan = tgt_stat
        
        # Sync to Combined Table
        db.query(storage.TabelGabungan).filter(
            storage.TabelGabungan.queue_number == s.queue_number,
            storage.TabelGabungan.visit_date == s.visit_date
        ).update({
            "status_pelayanan": tgt_stat,
            "checkin_time": s.checkin_time,
            "clinic_entry_time": s.clinic_entry_time,
            "completion_time": s.completion_time
        })
        
        db.commit()
        return {"status": "Success", "message": f"Status updated to: {tgt_stat}"}
    except Exception as e:
        db.rollback()
        raise HTTPException(500, detail=f"Database Sync Error: {str(e)}")

@router_ops.put("/medical-notes/{q_num}")
def update_notes(q_num: str, body: schemas.MedicalNoteUpdate, db: Session = Depends(get_db)):
    s = db.query(storage.TabelPelayanan).filter(storage.TabelPelayanan.queue_number == q_num).first()
    if not s:
        raise HTTPException(404, detail="Queue number not found")

    try:
        s.catatan_medis = body.catatan 
        db.query(storage.TabelGabungan).filter(storage.TabelGabungan.queue_number == q_num).update({
            "catatan_medis": body.catatan
        })
        db.commit()
        return {"message": "Medical notes updated successfully"}
    except Exception as e:
        db.rollback()
        raise HTTPException(500, detail="Failed to update notes")

# =================================================================
# 6. PUBLIC ROUTER
# =================================================================

@router_public.get("/polis")
def get_polis(db: Session = Depends(get_db)):
    return db.query(storage.TabelPoli).all()

@router_public.get("/available-doctors")
def get_avail_docs(poli_name: str, db: Session = Depends(get_db)):
    return db.query(storage.TabelDokter).filter(storage.TabelDokter.poli == poli_name).all()

@router_public.post("/submit")
def submit_reg(p: schemas.TicketCreate, db: Session = Depends(get_db), current_user: dict = Depends(security.get_current_user_token)):
    
    # 1. IDENTITY LOGIC
    user_log = db.query(storage.TabelUser).filter(storage.TabelUser.username == current_user['username']).first()
    target_username = user_log.username
    final_nama = user_log.nama_lengkap 

    if current_user['role'] in ["admin", "administrasi", "perawat"]:
        if p.username_pasien:
            pasien_db = db.query(storage.TabelUser).filter(storage.TabelUser.username == p.username_pasien.lower().strip()).first()
            if not pasien_db: raise HTTPException(404, "Patient username not found.")
            target_username, final_nama = pasien_db.username, pasien_db.nama_lengkap 
        else: raise HTTPException(400, "Staff must provide target patient username.")

    # 2. VALIDATION
    q_date = p.visit_date
    if q_date < date.today(): raise HTTPException(400, "Cannot register for past dates.")

    doc = db.query(storage.TabelDokter).filter(storage.TabelDokter.doctor_id == p.doctor_id).first()
    if not doc or doc.clinic != p.clinic: raise HTTPException(400, "Doctor/Clinic association error.")

    # 3. QUOTA LOGIC
    current_count = db.query(storage.TabelPelayanan).filter(storage.TabelPelayanan.doctor_id_ref == p.doctor_id, storage.TabelPelayanan.visit_date == q_date).count()
    if current_count >= doc.max_patients: raise HTTPException(400, "Doctor quota is full.")

    if db.query(storage.TabelPelayanan).filter(storage.TabelPelayanan.username == target_username, storage.TabelPelayanan.visit_date == q_date).first():
        raise HTTPException(400, "Patient already has a ticket for this date.")

    # 4. SEQUENCE GENERATION
    seq = current_count + 1
    poli_data = db.query(storage.TabelPoli).filter(storage.TabelPoli.clinic == p.clinic).first()
    try: suf = doc.doctor_code.split('-')[-1]
    except: suf = "001"
    q_str = f"{poli_data.prefix}-{suf}-{seq:03d}"

    # 5. ATOMIC DATA SAVE
    try:
        # Create records
        new_t = storage.TabelPelayanan(
            username=target_username, nama_pasien=final_nama, poli=p.poli,
            dokter=doc.dokter, doctor_id_ref=doc.doctor_id, visit_date=q_date,
            service_status="Registered", queue_number=q_str, queue_sequence=seq,
            status_member="Member"
        )
        db.add(new_t)
        
        # Manually commit the session
        db.commit()
        db.refresh(new_t)

        # 6. DYNAMIC RESPONSE
        wait_min = get_estimated_wait_time(db, doc.doctor_id, seq, q_date) if q_date == date.today() else 0
        return {
            "id": new_t.id,
            "queue_number": new_t.queue_number,
            "patient_name": new_t.patient_name,
            "clinic": new_t.clinic,
            "doctor": new_t.doctor,
            "service_status": new_t.service_status,
            "visit_date": str(new_t.visit_date),
            "doctor_schedule": f"{str(doc.practice_start_time)[:5]} - {str(doc.practice_end_time)[:5]}"
        }

    except Exception as e:
        db.rollback() # Rollback if either save fails
        raise HTTPException(500, f"Save failed: {str(e)}")

@router_public.get("/my-history", response_model=List[schemas.PelayananSchema])
def get_history(db: Session = Depends(get_db), current_user: dict = Depends(security.get_current_user_token)):
    history = db.query(storage.TabelPelayanan).filter(storage.TabelPelayanan.username == current_user['username']).order_by(storage.TabelPelayanan.visit_date.desc()).all()
    for h in history:
        if h.status_pelayanan != "Finished" and h.visit_date == date.today():
            h.estimated_wait_time = get_estimated_wait_time(db, h.doctor_id_ref, h.queue_sequence, h.visit_date)
    return history

# =================================================================
# 7. ANALYTICS & MONITOR
# =================================================================

@router_monitor.get("/queue-board")
def get_board(db: Session = Depends(get_db)):
    return db.query(storage.TabelPelayanan).filter(
        storage.TabelPelayanan.visit_date == date.today(),
        storage.TabelPelayanan.status_pelayanan.in_(["Waiting", "Serving"])
    ).all()

@router_analytics.get("/comprehensive-report")
def get_analytics(db: Session = Depends(get_db)):
    res = db.query(storage.TabelPelayanan).all()
    if not res: return {"status": "No Data"}
    
    df = pd.DataFrame([r.__dict__ for r in res])
    for col in ['checkin_time', 'clinic_entry_time', 'completion_time']:
        df[col] = pd.to_datetime(df[col], errors='coerce')
    
    # 1. Wait vs Service Durations
    df['wait_min'] = (df['clinic_entry_time'] - df['checkin_time']).dt.total_seconds() / 60
    df['svc_min'] = (df['completion_time'] - df['clinic_entry_time']).dt.total_seconds() / 60
    
    # 2. Ghosting Rate
    ghosts = df[df['checkin_time'].isna() & (df['visit_date'] <= date.today())].shape[0]
    ghost_rate = round((ghosts / len(df)) * 100, 1) if len(df) > 0 else 0
    
    # 3. Predicted Peak Day
    df['day_name'] = pd.to_datetime(df['visit_date']).dt.day_name()
    busy_day = df['day_name'].mode()[0] if not df.empty else "N/A"

    return {
        "status": "Success",
        "total_patients": len(df),
        "ghost_rate": ghost_rate,
        "predicted_peak_day": busy_day,
        "poli_volume": df['poli'].value_counts().to_dict(),
        "text_mining": " ".join(df['catatan_medis'].dropna().astype(str))
    }

# =================================================================
# 8. APP ROUTER REGISTRATION
# =================================================================

app.include_router(router_auth, prefix="/auth")
app.include_router(router_public, prefix="/public", dependencies=[Depends(require_role(["admin", "administrasi", "pasien"]))])
app.include_router(router_ops, prefix="/ops", dependencies=[Depends(require_role(["admin", "perawat", "administrasi"]))])
app.include_router(router_monitor, prefix="/monitor", dependencies=[Depends(require_role(["admin", "administrasi", "pasien"]))])
app.include_router(router_admin, prefix="/admin", dependencies=[Depends(require_role(["admin"]))])
app.include_router(router_analytics, prefix="/analytics", dependencies=[Depends(require_role(["admin"]))])