from fastapi import FastAPI, Depends, HTTPException, status, APIRouter
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from sqlalchemy import text, func
from typing import List, Optional
from datetime import datetime, date, time, timedelta
import random
import math
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

def normalize_doctor_name(name: str) -> str:
    """Membersihkan gelar ganda seperti dr.Dr. atau Dr.dr. menjadi dr. saja"""
    if not name: return "dr. Unknown"
    # Menghapus semua variasi dr, dr., Dr, DR di awal string berulang kali
    clean = re.sub(r'^(?:dr|dr\.|drs|dra|ir|prof|h|hj|ns|mr|mrs)\.?\s*', '', name, flags=re.IGNORECASE)
    while re.match(r'^(?:dr|dr\.|drs|dra|ir|prof|h|hj|ns|mr|mrs)\.?\s*', clean, flags=re.IGNORECASE):
        clean = re.sub(r'^(?:dr|dr\.|drs|dra|ir|prof|h|hj|ns|mr|mrs)\.?\s*', '', clean, flags=re.IGNORECASE)
    return f"dr. {clean.strip().title()}"

def get_estimated_wait_time(db: Session, doctor_id: int, current_queue_seq: int, v_date: date):
    # Calculate average service duration (Finished status)
    avg_service_query = db.query(
        func.avg(func.timestampdiff(text("MINUTE"), storage.TabelPelayanan.clinic_entry_time, storage.TabelPelayanan.completion_time))
    ).filter(
        storage.TabelPelayanan.doctor_id_ref == doctor_id,
        storage.TabelPelayanan.service_status == "Finished"
    ).scalar()

    avg_service_time = float(avg_service_query) if avg_service_query else 15.0

    # Count people still ahead in the queue
    people_ahead = db.query(storage.TabelPelayanan).filter(
        storage.TabelPelayanan.doctor_id_ref == doctor_id,
        storage.TabelPelayanan.visit_date == v_date,
        storage.TabelPelayanan.queue_sequence < current_queue_seq,
        storage.TabelPelayanan.service_status.in_(["Registered", "Waiting", "Serving"])
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
    clean_username = form_data.username.lower().strip()
    user = db.query(storage.TabelUser).filter(storage.TabelUser.username == clean_username).first()
    
    if not user or not security.verify_password(form_data.password, user.password):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    
    # DETERMINE MEMBER STATUS
    status_label = "User"
    if user.role == "admin":
        status_label = "Admin"
    elif user.role in ["nurse", "reception"]:
        status_label = "Staff"
    elif user.role == "patient":
        cnt = db.query(storage.TabelPelayanan).filter(
            storage.TabelPelayanan.username == user.username,
            storage.TabelPelayanan.service_status == "Finished"
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
        role="patient", 
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
    if not db.query(storage.TabelPoli).filter(storage.TabelPoli.clinic == p.clinic).first():
        raise HTTPException(404, "Clinic not found")
    
    clean_name = f"dr. {clean_simple_name(p.doctor)}"
    max_id = db.query(func.max(storage.TabelDokter.doctor_id)).scalar()
    next_id = 1 if max_id is None else max_id + 1
    
    # Generate Code
    last = db.query(storage.TabelDokter).filter(storage.TabelDokter.clinic == p.clinic).order_by(storage.TabelDokter.doctor_id.desc()).first()
    try: nxt_num = int(last.doctor_code.split('-')[-1]) + 1 if last else 1
    except: nxt_num = 1
    prefix = db.query(storage.TabelPoli).filter(storage.TabelPoli.clinic == p.clinic).first().prefix
    code = f"{prefix}-{nxt_num:03d}"
    
    new = storage.TabelDokter(
        doctor_id=next_id, doctor=clean_name, clinic=p.clinic,
        practice_start_time=datetime.strptime(p.practice_start_time, "%H:%M").time(),
        practice_end_time=datetime.strptime(p.practice_end_time, "%H:%M").time(),
        doctor_code=code, max_patients=p.max_patients
    )
    db.add(new); db.commit(); db.refresh(new)
    return new
@router_admin.put("/doctors/{id}")
def update_doctor(id: int, p: schemas.DoctorCreate, db: Session = Depends(get_db)):
    doc = db.query(storage.TabelDokter).filter(storage.TabelDokter.doctor_id == id).first()
    if not doc: raise HTTPException(404, "Doctor not found")
    
    doc.doctor = f"dr. {clean_simple_name(p.doctor)}"
    doc.clinic = p.clinic
    doc.max_patients = p.max_patients
    doc.practice_start_time = datetime.strptime(p.practice_start_time, "%H:%M").time()
    doc.practice_end_time = datetime.strptime(p.practice_end_time, "%H:%M").time()
    db.commit()
    return {"message": "Doctor information updated"}
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
    if db.query(storage.TabelPoli).filter(storage.TabelPoli.clinic == p.clinic).first():
        raise HTTPException(status_code=400, detail=f"Clinic '{p.clinic}' already exists.")
        
    if db.query(storage.TabelPoli).filter(storage.TabelPoli.prefix == p.prefix).first():
        raise HTTPException(status_code=400, detail=f"Prefix '{p.prefix}' is already used.")

    new_poli = storage.TabelPoli(clinic=p.clinic, prefix=p.prefix)
    db.add(new_poli); db.commit()
    return {"message": "Clinic added successfully"}
@router_admin.put("/polis/{old_clinic_name}")
def update_poli(old_clinic_name: str, p: schemas.PoliCreate, db: Session = Depends(get_db)):
    poli = db.query(storage.TabelPoli).filter(storage.TabelPoli.clinic == old_clinic_name).first()
    if not poli: raise HTTPException(404, "Clinic not found")
    
    # Validasi: Cek jika nama baru sudah dipakai klinik lain
    if old_clinic_name != p.clinic:
        if db.query(storage.TabelPoli).filter(storage.TabelPoli.clinic == p.clinic).first():
            raise HTTPException(400, "New clinic name already exists")
    
    # Update data utama dan relasi di tabel dokter
    db.query(storage.TabelDokter).filter(storage.TabelDokter.clinic == old_clinic_name).update({"clinic": p.clinic})
    poli.clinic = p.clinic
    poli.prefix = p.prefix
    db.commit()
    return {"message": "Clinic and linked doctors updated"}

@router_admin.delete("/polis/{clinic_name}")
def delete_poli(clinic_name: str, db: Session = Depends(get_db)):
    # VALIDASI KUAT: Integritas Referensial (Himpunan Tidak Kosong)
    # Jika Set(Dokter) != Ø, maka Delete dilarang.
    doc_count = db.query(storage.TabelDokter).filter(storage.TabelDokter.clinic == clinic_name).count()
    if doc_count > 0:
        raise HTTPException(400, f"Cannot delete! {doc_count} doctors are still assigned to this clinic.")
    
    db.query(storage.TabelPoli).filter(storage.TabelPoli.clinic == clinic_name).delete()
    db.commit()
    return {"message": "Clinic deleted"}

@router_admin.get("/import-random-data")
def import_random_data(count: int = 10, db: Session = Depends(get_db)):
    try:
        fake = Faker('id_ID')
        df_doc, df_pas = csv_utils.get_merged_random_data(count)
        
        c = 0
        for i in range(count):
            if not df_doc.empty:
                row = df_doc.sample(n=1).iloc[0]
                r_clinic = schemas.format_poli_name(str(row['clinic']))
                r_doc_name = f"dr. {clean_simple_name(str(row['doctor']))}"
                r_prefix = str(row.get('prefix', r_clinic[:4].upper())).strip()
                
                if not db.query(storage.TabelPoli).filter(storage.TabelPoli.clinic == r_clinic).first():
                    db.add(storage.TabelPoli(clinic=r_clinic, prefix=r_prefix)); db.commit()
                
                doc = db.query(storage.TabelDokter).filter(storage.TabelDokter.doctor == r_doc_name).first()
                if not doc:
                    mid = db.query(func.max(storage.TabelDokter.doctor_id)).scalar() or 0
                    doc = storage.TabelDokter(doctor_id=mid+1, doctor=r_doc_name, clinic=r_clinic, 
                                              practice_start_time=time(8,0), practice_end_time=time(16,0), 
                                              doctor_code=f"{r_prefix}-001", max_patients=20)
                    db.add(doc); db.commit()
            
            r_nama = clean_simple_name(fake.name())
            uname = r_nama.lower() + str(random.randint(1,999))
            if not db.query(storage.TabelUser).filter(storage.TabelUser.username == uname).first():
                db.add(storage.TabelUser(username=uname, password=security.get_password_hash("123"), role="patient", nama_lengkap=r_nama))
                db.commit()

            r_date = date.today()
            r_stat = "Finished"

            new_t = storage.TabelPelayanan(
                username=uname, status_member="Member", patient_name=r_nama, clinic=r_clinic, 
                doctor=doc.doctor, doctor_id_ref=doc.doctor_id, visit_date=r_date, 
                service_status=r_stat, queue_number=f"{r_prefix}-001-{i:03d}", queue_sequence=i+1
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
    
    if val.isdigit():
        s = db.query(storage.TabelPelayanan).filter(storage.TabelPelayanan.id == int(val)).first()
    else:
        s = db.query(storage.TabelPelayanan).filter(storage.TabelPelayanan.queue_number == val).order_by(storage.TabelPelayanan.id.desc()).first()
    
    if not s: raise HTTPException(404, detail="Ticket not found")

    STATE_LVL = {"Registered": 0, "Waiting": 1, "Serving": 2, "Finished": 3}
    LOC_MAP = {"arrival": ("Waiting", 1), "clinic": ("Serving", 2), "finish": ("Finished", 3)}
    
    curr_lvl = STATE_LVL.get(s.service_status, 0)
    tgt_stat, tgt_lvl = LOC_MAP.get(p.location)

    if curr_lvl == tgt_lvl: return {"status": "Warning", "message": f"Already '{s.service_status}'."}
    if tgt_lvl < curr_lvl: return {"status": "Error", "message": "Backward flow denied."}
    if tgt_lvl > curr_lvl + 1: return {"status": "Error", "message": "Step skipped."}
    if tgt_stat == "Finished" and not s.catatan_medis: return {"status": "Error", "message": "Notes required."}

    try:
        now = datetime.now()
        if p.location == "arrival": s.checkin_time = now
        elif p.location == "clinic": s.clinic_entry_time = now
        elif p.location == "finish": s.completion_time = now
        
        s.service_status = tgt_stat
        db.query(storage.TabelGabungan).filter(storage.TabelGabungan.queue_number == s.queue_number, storage.TabelGabungan.visit_date == s.visit_date).update({"service_status": tgt_stat})
        db.commit()
        return {"status": "Success", "message": f"Status: {tgt_stat}"}
    except Exception as e:
        db.rollback()
        raise HTTPException(500, detail=str(e))

@router_ops.put("/medical-notes/{q_num}")
def update_notes(q_num: str, body: schemas.MedicalNoteUpdate, db: Session = Depends(get_db)):
    s = db.query(storage.TabelPelayanan).filter(storage.TabelPelayanan.queue_number == q_num).first()
    if not s: raise HTTPException(404, detail="Queue not found")

    try:
        s.catatan_medis = body.catatan 
        db.query(storage.TabelGabungan).filter(storage.TabelGabungan.queue_number == q_num).update({"catatan_medis": body.catatan})
        db.commit()
        return {"message": "Medical notes updated"}
    except Exception as e:
        db.rollback()
        raise HTTPException(500, detail="Update failed")

# =================================================================
# 6. PUBLIC ROUTER
# =================================================================

@router_public.get("/polis")
def get_polis(db: Session = Depends(get_db)):
    return db.query(storage.TabelPoli).all()

@router_public.get("/available-doctors")
def get_avail_docs(clinic_name: str, db: Session = Depends(get_db)):
    return db.query(storage.TabelDokter).filter(storage.TabelDokter.clinic == clinic_name).all()

@router_public.post("/submit")
def submit_reg(p: schemas.TicketCreate, db: Session = Depends(get_db), current_user: dict = Depends(security.get_current_user_token)):
    user_log = db.query(storage.TabelUser).filter(storage.TabelUser.username == current_user['username']).first()
    target_username, final_nama = user_log.username, user_log.nama_lengkap 

    if current_user['role'] in ["admin", "nurse", "reception"] and p.username_pasien:
        pasien_db = db.query(storage.TabelUser).filter(storage.TabelUser.username == p.username_pasien.lower().strip()).first()
        if not pasien_db: raise HTTPException(404, "Patient not found.")
        target_username, final_nama = pasien_db.username, pasien_db.nama_lengkap 

    q_date = p.visit_date
    if q_date < date.today(): raise HTTPException(400, "Past date.")

    doc = db.query(storage.TabelDokter).filter(storage.TabelDokter.doctor_id == p.doctor_id).first()
    if not doc or doc.clinic != p.clinic: raise HTTPException(400, "Clinic mismatch.")

    current_count = db.query(storage.TabelPelayanan).filter(storage.TabelPelayanan.doctor_id_ref == p.doctor_id, storage.TabelPelayanan.visit_date == q_date).count()
    if current_count >= doc.max_patients: raise HTTPException(400, "Quota full.")

    if db.query(storage.TabelPelayanan).filter(storage.TabelPelayanan.username == target_username, storage.TabelPelayanan.visit_date == q_date).first():
        raise HTTPException(400, "Already booked today.")

    seq = current_count + 1
    poli_data = db.query(storage.TabelPoli).filter(storage.TabelPoli.clinic == p.clinic).first()
    q_str = f"{poli_data.prefix}-{doc.doctor_id:03d}-{seq:03d}"

    try:
        new_t = storage.TabelPelayanan(
            username=target_username, patient_name=final_nama, clinic=p.clinic,
            doctor=doc.doctor, doctor_id_ref=doc.doctor_id, visit_date=q_date,
            service_status="Registered", queue_number=q_str, queue_sequence=seq
        )
        db.add(new_t)
        
        db.add(storage.TabelGabungan(
            username=target_username, patient_name=final_nama, clinic=p.clinic, prefix_poli=poli_data.prefix,
            doctor=doc.doctor, doctor_id=doc.doctor_id, visit_date=q_date, 
            service_status="Registered", queue_number=q_str, queue_sequence=seq
        ))
        db.commit()
        db.refresh(new_t)

        return {
            "id": new_t.id,
            "queue_number": q_str,
            "patient_name": new_t.patient_name,
            "clinic": new_t.clinic,
            "doctor": new_t.doctor,
            "service_status": new_t.service_status,
            "visit_date": str(new_t.visit_date),
            "doctor_schedule": f"{str(doc.practice_start_time)[:5]} - {str(doc.practice_end_time)[:5]}"
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"Save failed: {str(e)}")

@router_public.get("/my-history", response_model=List[schemas.PelayananSchema])
def get_history(db: Session = Depends(get_db), current_user: dict = Depends(security.get_current_user_token)):
    return db.query(storage.TabelPelayanan).filter(storage.TabelPelayanan.username == current_user['username']).order_by(storage.TabelPelayanan.visit_date.desc()).all()

# =================================================================
# 7. ANALYTICS & MONITOR
# =================================================================

@router_monitor.get("/queue-board")
def get_board(db: Session = Depends(get_db)):
    return db.query(storage.TabelPelayanan).filter(
        storage.TabelPelayanan.visit_date == date.today(),
        storage.TabelPelayanan.service_status.in_(["Waiting", "Serving"])
    ).all()

@router_analytics.get("/comprehensive-report")
def get_analytics(db: Session = Depends(get_db)):
    try:
        res = db.query(storage.TabelPelayanan).all()
        if not res: return {"status": "No Data"}

        df = pd.DataFrame([r.__dict__ for r in res])
        
        # Konversi waktu secara aman
        for col in ['checkin_time', 'clinic_entry_time', 'completion_time']:
            df[col] = pd.to_datetime(df[col], errors='coerce')
        
        # 1. Hitung Durasi (Menit)
        df['wait_min'] = (df['clinic_entry_time'] - df['checkin_time']).dt.total_seconds() / 60
        df['svc_min'] = (df['completion_time'] - df['clinic_entry_time']).dt.total_seconds() / 60

        # 2. Time Efficiency per Clinic (Hanya yang datanya valid)
        valid_eff = df[(df['wait_min'] >= 0) & (df['svc_min'] >= 0)]
        clinic_efficiency = {}
        if not valid_eff.empty:
            raw_eff = valid_eff.groupby('clinic')[['wait_min', 'svc_min']].mean().fillna(0).to_dict('index')
            clinic_efficiency = {k: {"wait_minutes": round(v['wait_min'], 1), 
                                     "service_minutes": round(v['svc_min'], 1)} 
                                 for k, v in raw_eff.items()}

        # 3. Peak Hour Trends
        peak_hours = df['checkin_time'].dt.hour.value_counts().sort_index().to_dict()

        # 4. Correlation (Wait vs Service)
        correlation = 0
        if len(valid_eff) > 1:
            c = valid_eff['wait_min'].corr(valid_eff['svc_min'])
            correlation = round(c, 2) if not math.isnan(c) else 0

        return {
            "status": "Success",
            "total_patients": len(df),
            "ghost_rate": round(df['checkin_time'].isna().sum() / len(df) * 100, 1) if len(df) > 0 else 0,
            "correlation": correlation,
            "peak_hours": peak_hours,
            "clinic_volume": df['clinic'].value_counts().to_dict(),
            "clinic_efficiency": clinic_efficiency,
            "doctor_throughput": df[df['service_status'] == 'Finished']['doctor'].value_counts().to_dict(),
            "text_mining": " ".join(df['catatan_medis'].dropna().astype(str))
        }
    except Exception as e:
        raise HTTPException(500, detail=str(e))

# =================================================================
# 8. APP ROUTER REGISTRATION
# =================================================================

app.include_router(router_auth, prefix="/auth")
app.include_router(router_public, prefix="/public", dependencies=[Depends(require_role(["admin", "reception", "patient"]))])
app.include_router(router_ops, prefix="/ops", dependencies=[Depends(require_role(["admin", "nurse", "reception"]))])
app.include_router(router_monitor, prefix="/monitor", dependencies=[Depends(require_role(["admin", "reception", "patient"]))])
app.include_router(router_admin, prefix="/admin", dependencies=[Depends(require_role(["admin"]))])
app.include_router(router_analytics, prefix="/analytics", dependencies=[Depends(require_role(["admin"]))])