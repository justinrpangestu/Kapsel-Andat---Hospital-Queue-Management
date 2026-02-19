# main.py - FINAL CLEAN VERSION

from fastapi import FastAPI, Depends, HTTPException, status, APIRouter
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func
from typing import List, Optional
from datetime import datetime, date, time, timedelta
import random
import pandas as pd
from contextlib import asynccontextmanager
from faker import Faker
import re

# --- INTERNAL MODULES ---
# Pastikan file-file ini ada di folder yang sama
import storage
import schemas
import security
import csv_utils

# =================================================================
# 1. SETUP & LIFESPAN
# =================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Bikin tabel jika belum ada
    print("🏥 Sistem RS Pintar Starting...")
    storage.Base.metadata.create_all(bind=storage.engine)
    yield
    # Shutdown
    print("🛑 Sistem RS Pintar Shutting Down...")

app = FastAPI(
    title="Hospital Queue System",
    description="API Manajemen RS Pintar (Backend Final)",
    version="3.0.0",
    lifespan=lifespan
)

# Dependency Database
def get_db():
    db = storage.SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- HELPER FUNCTIONS ---
def clean_simple_name(full_name: str) -> str:
    """Membersihkan gelar dan mengambil nama belakang/panggilan."""
    if not full_name: return "TanpaNama"
    name_no_suffix = full_name.split(',')[0]
    name_clean = re.sub(r'^(dr\.|drs\.|dra\.|ir\.|prof\.|h\.|hj\.|ns\.|mr\.|mrs\.)\s*', '', name_no_suffix, flags=re.IGNORECASE)
    parts = name_clean.replace('.', ' ').split()
    return parts[-1].title() if parts else "User"

def get_random_time_window():
    """Helper untuk import data dummy waktu."""
    fake = Faker()
    dt = fake.date_between(start_date='-30d', end_date='today')
    t_chk = datetime.combine(dt, time(random.randint(8, 14), random.randint(0, 59)))
    t_ent = t_chk + timedelta(minutes=random.randint(10, 60))
    t_fin = t_ent + timedelta(minutes=random.randint(10, 30))
    return t_chk, t_ent, t_fin

# --- SECURITY GUARD (RBAC) ---
def require_role(allowed_roles: list):
    def role_checker(current_user: dict = Depends(security.get_current_user_token)):
        if current_user['role'] not in allowed_roles:
            raise HTTPException(
                status_code=403, 
                detail=f"Akses Ditolak! Role '{current_user['role']}' tidak diizinkan."
            )
        return current_user
    return role_checker

# =================================================================
# 2. ROUTER DEFINITIONS
# =================================================================

# Hapus prefix di sini agar tidak double saat di-include
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
 # [FIX] Paksa inputan jadi lowercase biar tidak peduli Capslock
    clean_username = form_data.username.lower().strip()
    
    # 1.Cek User di Database pakai username yang sudah dikecilkan
    user = db.query(storage.TabelUser).filter(storage.TabelUser.username == clean_username).first()
    
    if not user or not security.verify_password(form_data.password, user.password):
        raise HTTPException(status_code=401, detail="Username atau password salah")
    
    # 2. LOGIKA PENENTUAN STATUS MEMBER (SESUAI REQUEST)
    status_label = "User" # Default fallback
    
    if user.role == "admin":
        status_label = "Admin"
        
    elif user.role in ["perawat", "administrasi"]:
        status_label = "Staff"
        
    elif user.role == "pasien":
        # Hitung riwayat berobat
        cnt = db.query(storage.TabelPelayanan).filter(
            storage.TabelPelayanan.username == user.username,
            storage.TabelPelayanan.status_pelayanan == "Selesai"
        ).count()
        status_label = "Pasien Lama" if cnt > 0 else "Pasien Baru"
    
    # 3. Buat Token
    token = security.create_access_token(data={"sub": user.username, "role": user.role})
    
    return {
        "access_token": token, 
        "token_type": "bearer", 
        "role": user.role, 
        "nama": user.nama_lengkap, 
        "status_member": status_label # <--- Hasil logika di atas
    }

@router_auth.post("/register", response_model=schemas.Token)
def register(user: schemas.UserCreate, db: Session = Depends(get_db)):
# [FIX] Paksa lowercase saat daftar
    clean_username = user.username.lower().strip()

    if db.query(storage.TabelUser).filter(storage.TabelUser.username == clean_username).first():
        raise HTTPException(400, "Username sudah dipakai.")
    
    new_user = storage.TabelUser(
        username=user.username, password=security.get_password_hash(user.password),
        role="pasien", nama_lengkap=user.nama_lengkap
    )
    db.add(new_user); db.commit(); db.refresh(new_user)
    
    token = security.create_access_token(data={"sub": new_user.username, "role": new_user.role})
    return {
        "access_token": token, "token_type": "bearer", 
        "role": new_user.role, "nama": new_user.nama_lengkap, "status_member": "Pasien Baru"
    }

# =================================================================
# 4. ADMIN ROUTER (Manage Doctors, Poli, Import)
# =================================================================

@router_admin.get("/doctors")
def get_doctors(db: Session = Depends(get_db)):
    return db.query(storage.TabelDokter).all()

@router_admin.post("/doctors")
def add_doctor(p: schemas.DoctorCreate, db: Session = Depends(get_db)):
    # Validasi Poli
    if not db.query(storage.TabelPoli).filter(storage.TabelPoli.poli == p.poli).first():
        raise HTTPException(404, "Poli tidak ditemukan")
    
    # Nama & ID Bersih
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

@router_admin.put("/doctors/{id}")
def update_doctor(id: int, p: schemas.DoctorUpdate, db: Session = Depends(get_db)):
    d = db.query(storage.TabelDokter).filter(storage.TabelDokter.doctor_id == id).first()
    if not d: raise HTTPException(404, "Dokter tidak ditemukan")
    
    old_name = d.dokter
    
    # --- [VALIDASI BARU: GANTI POLI] ---
    # Jika user ingin mengganti poli, cek apakah dokter punya pasien (aktif/history)
    if p.poli and p.poli != d.poli:
        # Cek di tabel pelayanan
        patient_count = db.query(storage.TabelPelayanan).filter(storage.TabelPelayanan.doctor_id_ref == id).count()
        if patient_count > 0:
            raise HTTPException(
                status_code=400, 
                detail=f"Gagal ganti Poli! Dokter ini memiliki {patient_count} data pasien. Hapus data pasien terkait terlebih dahulu jika ingin memindahkan poli."
            )
        d.poli = p.poli

    # Update Field Lain
    if p.dokter: d.dokter = f"dr. {clean_simple_name(p.dokter)}"
    
    # [FIX] Hapus update max_patients sesuai request
    # if p.max_patients: d.max_patients = p.max_patients  <-- INI DIHAPUS/KOMENTAR
    
    if p.practice_start_time: d.practice_start_time = datetime.strptime(p.practice_start_time, "%H:%M").time()
    if p.practice_end_time: d.practice_end_time = datetime.strptime(p.practice_end_time, "%H:%M").time()
    
    # Cascade Update Transaksi (Hanya update nama jika berubah)
    if p.dokter and old_name != d.dokter:
        db.query(storage.TabelPelayanan).filter(storage.TabelPelayanan.doctor_id_ref == id).update({storage.TabelPelayanan.dokter: d.dokter}, synchronize_session=False)
        db.query(storage.TabelGabungan).filter(storage.TabelGabungan.doctor_id == id).update({storage.TabelGabungan.dokter: d.dokter}, synchronize_session=False)

    db.commit(); db.refresh(d)
    return d
@router_admin.delete("/doctors/{id}")
def delete_doctor(id: int, db: Session = Depends(get_db)):
    d = db.query(storage.TabelDokter).filter(storage.TabelDokter.doctor_id == id).first()
    if not d: raise HTTPException(404, "Dokter tidak ditemukan")
    
    # --- [VALIDASI BARU] ---
    # Cek apakah dokter punya data pasien
    patient_count = db.query(storage.TabelPelayanan).filter(storage.TabelPelayanan.doctor_id_ref == id).count()
    if patient_count > 0:
        raise HTTPException(
            status_code=400, 
            detail=f"TIDAK BISA MENGHAPUS! Dokter ini memiliki {patient_count} riwayat pasien di Database."
        )
    
    db.delete(d); db.commit()
    return {"message": "Dokter berhasil dihapus."}

# --- POLI MANAGEMENT ---
@router_admin.post("/polis")
def add_poli(p: schemas.PoliCreate, db: Session = Depends(get_db)): # <--- Pakai Schema
    
    # 1. Cek apakah Poli sudah ada
    if db.query(storage.TabelPoli).filter(storage.TabelPoli.poli == p.poli).first():
        raise HTTPException(status_code=400, detail=f"Poli '{p.poli}' sudah ada.")
        
    # 2. Cek apakah Prefix sudah ada
    if db.query(storage.TabelPoli).filter(storage.TabelPoli.prefix == p.prefix).first():
        raise HTTPException(status_code=400, detail=f"Prefix '{p.prefix}' sudah dipakai.")

    # 3. Simpan (Akses pakai titik karena sekarang Pydantic model)
    new_poli = storage.TabelPoli(
        poli=p.poli, 
        prefix=p.prefix
    )
    
    db.add(new_poli)
    db.commit()
    return {"message": "Poli berhasil ditambahkan"}

@router_admin.put("/polis/{original}")
def update_poli(original: str, p: schemas.PoliUpdate, db: Session = Depends(get_db)):
    poli = db.query(storage.TabelPoli).filter(storage.TabelPoli.poli == original).first()
    if not poli: raise HTTPException(404, "Poli not found")
    
    try:
        # Simpan state lama buat rollback manual jika perlu
        old_prefix = poli.prefix
        
        if p.new_prefix: 
            # Check manual (opsional, karena IntegrityError juga akan menangkapnya)
            existing_pref = db.query(storage.TabelPoli).filter(storage.TabelPoli.prefix == p.new_prefix.upper()).first()
            if existing_pref and existing_pref.poli != original:
                raise HTTPException(400, f"Prefix '{p.new_prefix}' sudah digunakan oleh poli lain.")
            poli.prefix = p.new_prefix.upper()
            
        if p.new_name and p.new_name != original:
            # Cascade update nama poli di tabel dokter
            db.query(storage.TabelDokter).filter(storage.TabelDokter.poli == original).update({storage.TabelDokter.poli: p.new_name}, synchronize_session=False)
            poli.poli = p.new_name
        
        db.commit()
        return {"message": "Poli updated"}
        
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Gagal Update: Prefix atau Nama Poli mungkin sudah digunakan.")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router_admin.delete("/polis/{name}")
def delete_poli(name: str, db: Session = Depends(get_db)):
    p = db.query(storage.TabelPoli).filter(storage.TabelPoli.poli == name).first()
    if not p: raise HTTPException(404, "Poli tidak ditemukan")
    
    # --- [VALIDASI BARU] ---
    # 1. Cek apakah ada dokter di poli ini
    doc_count = db.query(storage.TabelDokter).filter(storage.TabelDokter.poli == name).count()
    if doc_count > 0:
        raise HTTPException(400, f"Gagal hapus! Masih ada {doc_count} dokter di poli ini.")
        
    # 2. Cek apakah ada pasien yang mengambil poli ini (di Tabel Pelayanan)
    pat_count = db.query(storage.TabelPelayanan).filter(storage.TabelPelayanan.poli == name).count()
    if pat_count > 0:
        raise HTTPException(400, f"Gagal hapus! Masih ada {pat_count} riwayat pasien di poli ini.")

    db.delete(p); db.commit()
    return {"message": "Poli berhasil dihapus."}

# --- IMPORT RANDOM DATA (ROBUST VERSION) ---
@router_admin.get("/import-random-data")
def import_random_data(count: int = 10, db: Session = Depends(get_db)):
    try:
        fake = Faker('id_ID')
        df_doc, df_pas = csv_utils.get_merged_random_data(count)
        
        c = 0
        for i in range(count):
            # 1. SETUP DOKTER & POLI (Ambil dari CSV atau Default)
            if not df_doc.empty:
                # Ambil data acak tapi konsisten
                row = df_doc.sample(n=1).iloc[0]
                
                # Cleaning Nama & Poli
                r_poli = str(row['poli']).strip().title()
                if not r_poli.startswith("Poli "): r_poli = f"Poli {r_poli}"
                
                raw_doc = str(row['dokter']).strip().title()
                r_doc_name = f"dr. {clean_simple_name(raw_doc)}"
                
                r_prefix = str(row.get('prefix', r_poli[:4].upper())).strip()
                try: d_code = row['doctor_code']
                except: d_code = f"{r_prefix}-001"
                try: max_p = int(row['max_patients'])
                except: max_p = 20
                
                # Simpan Poli jika belum ada
                if not db.query(storage.TabelPoli).filter(storage.TabelPoli.poli == r_poli).first():
                    db.add(storage.TabelPoli(poli=r_poli, prefix=r_prefix)); db.commit()
                
                # Simpan Dokter jika belum ada
                doc = db.query(storage.TabelDokter).filter(storage.TabelDokter.dokter == r_doc_name).first()
                if not doc:
                    # Parse jam praktek
                    try: 
                        ts = datetime.strptime(str(row['practice_start_time']), "%H:%M:%S").time()
                        te = datetime.strptime(str(row['practice_end_time']), "%H:%M:%S").time()
                    except: ts=time(8,0); te=time(16,0)
                    
                    mid = db.query(func.max(storage.TabelDokter.doctor_id)).scalar() or 0
                    doc = storage.TabelDokter(doctor_id=mid+1, dokter=r_doc_name, poli=r_poli, 
                                              practice_start_time=ts, practice_end_time=te, 
                                              doctor_code=d_code, max_patients=max_p)
                    db.add(doc); db.commit()
            else:
                # Fallback jika CSV kosong
                r_poli = "Poli Umum"; r_doc_name = "dr. Umum"; r_prefix="UMUM"
                # ... (logika create dummy doctor manual disini jika perlu) ...
                continue # Skip loop ini agar aman

            # 2. SETUP PASIEN
            r_nama = clean_simple_name(fake.name()).strip().title()
            uname = r_nama.lower().replace(" ", "") + str(random.randint(1,999))
            
            if not db.query(storage.TabelUser).filter(storage.TabelUser.username == uname).first():
                db.add(storage.TabelUser(username=uname, password=security.get_password_hash("123"), role="pasien", nama_lengkap=r_nama))
                db.commit()

            # 3. SETUP TANGGAL & STATUS (LOGIKA VARIASI BARU)
            # Trik: 40% Kemungkinan data adalah HARI INI (agar dashboard ramai)
            is_today = random.random() < 0.4 
            
            if is_today:
                r_date = date.today()
                # Jika hari ini, statusnya acak
                r_stat = random.choices(
                    ["Menunggu", "Sedang Dilayani", "Selesai"], 
                    weights=[40, 30, 30] # 40% Menunggu, 30% Dilayani, 30% Selesai
                )[0]
            else:
                # Jika masa lalu, pasti selesai
                r_date = fake.date_between(start_date='-30d', end_date='-1d')
                r_stat = "Selesai"

            # 4. SETUP WAKTU (TIMESTAMPS) SESUAI STATUS
            # Waktu Checkin (Pasti ada)
            t_chk = datetime.combine(r_date, time(random.randint(7, 14), random.randint(0, 59)))
            
            # Waktu Masuk Poli (Ada jika BUKAN Menunggu)
            t_ent = None
            if r_stat in ["Sedang Dilayani", "Selesai"]:
                # Masuk 10-60 menit setelah checkin
                t_ent = t_chk + timedelta(minutes=random.randint(10, 60))
            
            # Waktu Selesai (Ada HANYA jika Selesai)
            t_fin = None
            if r_stat == "Selesai":
                # Selesai 10-30 menit setelah masuk
                t_fin = t_ent + timedelta(minutes=random.randint(10, 30))

            # Catatan Medis (Hanya jika selesai/sedang dilayani)
            r_note = None
            if r_stat != "Menunggu":
                options = ["Demam", "Flu", "Batuk", "Cek Darah", "Pusing", "Sakit Gigi", "Asam Lambung", "Sehat", "Kontrol Rutin"]
                r_note = f"{random.choice(options)} - Resep diberikan."

            # 5. GENERATE NOMOR ANTREAN
            l_cnt = db.query(storage.TabelPelayanan).filter(
                storage.TabelPelayanan.doctor_id_ref == doc.doctor_id, 
                storage.TabelPelayanan.visit_date == r_date
            ).count()
            q_seq = l_cnt + 1
            try: suf = doc.doctor_code.split('-')[-1]
            except: suf = "001"
            q_str = f"{r_prefix}-{suf}-{q_seq:03d}"
            
            stat_mem = "Pasien Lama" if db.query(storage.TabelPelayanan).filter(storage.TabelPelayanan.username == uname).count() > 0 else "Pasien Baru"
            
            # 6. SIMPAN TRANSAKSI
            pel = storage.TabelPelayanan(
                username=uname, status_member=stat_mem, nama_pasien=r_nama, poli=r_poli, 
                dokter=doc.dokter, doctor_id_ref=doc.doctor_id, visit_date=r_date, 
                checkin_time=t_chk, clinic_entry_time=t_ent, completion_time=t_fin, 
                status_pelayanan=r_stat, queue_number=q_str, queue_sequence=q_seq, catatan_medis=r_note
            )
            db.add(pel)
            
            db.add(storage.TabelGabungan(
                username=uname, status_member=stat_mem, nama_pasien=r_nama, poli=r_poli, prefix_poli=r_prefix,
                dokter=doc.dokter, doctor_code=doc.doctor_code, doctor_id=doc.doctor_id, visit_date=r_date, 
                checkin_time=t_chk, clinic_entry_time=t_ent, completion_time=t_fin, 
                status_pelayanan=r_stat, queue_number=q_str, queue_sequence=q_seq, catatan_medis=r_note
            ))
            db.commit()
            c += 1
            
        return {"message": f"Sukses import {c} data variatif (Hari Ini & History)."}
        
    except Exception as e:
        db.rollback()
        import traceback; traceback.print_exc()
        raise HTTPException(500, str(e))

# =================================================================
# 5. OPS ROUTER (Scanner & Notes)
# =================================================================

# ... (kode import di atas tetap sama)

@router_ops.post("/scan-barcode")
def scan_barcode(p: schemas.ScanRequest, db: Session = Depends(get_db)):
    val = p.barcode_data.strip()
    print(f"🔍 SCANNING: {val} di lokasi {p.location}")

    # 1. CARI TIKET (Prioritaskan yang terbaru)
    if val.isdigit():
        s = db.query(storage.TabelPelayanan).filter(storage.TabelPelayanan.id == int(val)).first()
    else:
        s = db.query(storage.TabelPelayanan)\
            .filter(storage.TabelPelayanan.queue_number == val)\
            .order_by(storage.TabelPelayanan.id.desc())\
            .first()
    
    if not s: 
        raise HTTPException(404, "Tiket tidak ditemukan")
    
    print(f"✅ Tiket Ditemukan: {s.nama_pasien} | Status DB: {s.status_pelayanan}")

    # 2. STATE MACHINE (Leveling)
    STATE_LVL = {"Terdaftar": 0, "Menunggu": 1, "Sedang Dilayani": 2, "Selesai": 3}
    LOC_MAP = {"arrival": ("Menunggu", 1), "clinic": ("Sedang Dilayani", 2), "finish": ("Selesai", 3)}
    
    # Ambil status saat ini (handle jika null default ke Terdaftar)
    current_status = s.status_pelayanan if s.status_pelayanan in STATE_LVL else "Terdaftar"
    curr_lvl = STATE_LVL.get(current_status, 0)
    
    # Ambil target status berdasarkan lokasi scan
    tgt_stat, tgt_lvl = LOC_MAP.get(p.location)
    
    # --- [VALIDASI BARU: URUTAN & CATATAN] ---

    # A. Validasi Urutan (Tidak Boleh Mundur & Tidak Boleh Loncat)
    if curr_lvl == tgt_lvl:
        return {"status": "Warning", "message": f"Pasien SUDAH berstatus '{s.status_pelayanan}'."}
    
    if tgt_lvl < curr_lvl:
        return {"status": "Error", "message": f"Alur Mundur Ditolak! Status pasien '{s.status_pelayanan}' tidak bisa kembali ke '{tgt_stat}'."}
    
    # Cek Loncat (Hanya boleh naik 1 level)
    # Contoh Salah: Menunggu (1) -> Scan Selesai (3). Selisih 2.
    if tgt_lvl > curr_lvl + 1:
        # Cari nama status yang seharusnya dilewati
        next_step_name = [k for k, v in STATE_LVL.items() if v == curr_lvl + 1][0]
        return {
            "status": "Error", 
            "message": f"Alur Loncat Ditolak! Pasien masih '{current_status}'. Harusnya ke '{next_step_name}' dulu."
        }

    # B. Validasi Catatan Medis (Khusus saat mau Finish)
    if tgt_stat == "Selesai":
        # Cek apakah catatan medis kosong/None
        if not s.catatan_medis or not s.catatan_medis.strip():
            return {
                "status": "Error", 
                "message": "Gagal Selesai! Dokter WAJIB mengisi Diagnosa/Resep sebelum pasien pulang."
            }

    # -----------------------------------------
    
    # 3. LAKUKAN UPDATE (Jika lolos validasi)
    now = datetime.now()
    
    if p.location == "arrival":
        s.checkin_time = now
    elif p.location == "clinic":
        s.clinic_entry_time = now
    elif p.location == "finish":
        s.completion_time = now
    
    s.status_pelayanan = tgt_stat
    db.add(s)

    # 4. SYNC KE GABUNGAN
    gab = db.query(storage.TabelGabungan).filter(
        storage.TabelGabungan.queue_number == s.queue_number,
        storage.TabelGabungan.visit_date == s.visit_date
    ).first()
    
    if gab:
        if s.checkin_time: gab.checkin_time = s.checkin_time
        if s.clinic_entry_time: gab.clinic_entry_time = s.clinic_entry_time
        if s.completion_time: gab.completion_time = s.completion_time
        gab.status_pelayanan = s.status_pelayanan
        db.add(gab)
    
    try:
        db.commit()
        db.refresh(s)
        return {"status": "Success", "message": f"Status berubah: {tgt_stat}"}
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"Database Error: {str(e)}")

@router_ops.put("/medical-notes/{q_num}")
def update_notes(q_num: str, body: schemas.MedicalNoteUpdate, db: Session = Depends(get_db)):
    # 1. Cari data di DB
    s = db.query(storage.TabelPelayanan).filter(storage.TabelPelayanan.queue_number == q_num).first()
    
    if not s:
        raise HTTPException(status_code=404, detail="Nomor antrean tidak ditemukan")

    # 2. Update Catatan
    # Perhatikan cara aksesnya sekarang pakai titik (.) bukan kurung siku
    s.catatan_medis = body.catatan 
    
    # 3. Update juga di Tabel Gabungan (untuk Analytics)
    gab = db.query(storage.TabelGabungan).filter(storage.TabelGabungan.queue_number == q_num).first()
    if gab: 
        gab.catatan_medis = body.catatan
        
    db.commit()
    return {"message": "Catatan medis berhasil diperbarui"}

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
    
    # --- 1. LOGIKA PENENTUAN PASIEN & NAMA ---
    user_log = db.query(storage.TabelUser).filter(storage.TabelUser.username == current_user['username']).first()
    target_username = user_log.username
    final_nama_pasien = user_log.nama_lengkap 

    # KONDISI KHUSUS: Jika yang login adalah PETUGAS (Admin/Perawat)
    if current_user['role'] in ["admin", "administrasi", "perawat"]:
        if p.username_pasien:
            target_search = p.username_pasien.lower().strip()
            pasien_db = db.query(storage.TabelUser).filter(storage.TabelUser.username == target_search).first()
            if not pasien_db: raise HTTPException(status_code=404, detail=f"Username pasien '{p.username_pasien}' tidak ditemukan.")
            
            target_username = pasien_db.username
            final_nama_pasien = pasien_db.nama_lengkap 
        else:
            raise HTTPException(status_code=400, detail="Petugas WAJIB memasukkan 'Username Pasien' yang sudah terdaftar.")
    
    # 2. VALIDASI TANGGAL
    # ... (Validasi Tanggal Lama dan Baru tetap sama) ...
    try:
        q_date = datetime.strptime(p.visit_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(400, "Format tanggal salah (Gunakan YYYY-MM-DD)")

    if q_date < date.today():
        raise HTTPException(status_code=400, detail=f"Tanggal tidak valid! Tidak bisa mendaftar untuk tanggal masa lalu ({q_date}).")

    # 3. VALIDASI DOKTER & POLI
    doc = db.query(storage.TabelDokter).filter(storage.TabelDokter.doctor_id == p.doctor_id).first()
    if not doc: raise HTTPException(404, "Dokter tidak ditemukan")
    
    pol = db.query(storage.TabelPoli).filter(storage.TabelPoli.poli == p.poli).first()
    if not pol: raise HTTPException(404, "Poli tidak ditemukan")

    # --- [FIX KRITIS: CEK ASOSIASI DOKTER & POLI] ---
    if doc.poli != p.poli:
        raise HTTPException(
            status_code=400, 
            detail=f"Asosiasi salah! Dokter '{doc.dokter}' bertugas di '{doc.poli}', bukan di '{p.poli}'."
        )
    # ------------------------------------------------

    # 4. CEK JAM PRAKTEK (Khusus Hari Ini)
    if q_date == date.today():
        current_time = datetime.now().time()
        if current_time > doc.practice_end_time:
             raise HTTPException(400, detail=f"Pendaftaran Gagal! Jam praktek dokter sudah berakhir pada pukul {doc.practice_end_time.strftime('%H:%M')}.")

    # ... (Validasi tiket, kuota, dan simpan data di bawahnya tetap sama) ...

    # 5. VALIDASI SATU TIKET PER HARI
    existing_ticket = db.query(storage.TabelPelayanan).filter(
        storage.TabelPelayanan.username == target_username,
        storage.TabelPelayanan.visit_date == q_date
    ).first()
    
    if existing_ticket:
        raise HTTPException(status_code=400, detail=f"Pasien '{target_username}' sudah memiliki tiket antrean untuk tanggal {q_date}.")

    # 6. VALIDASI KUOTA DOKTER
    current_patient_count = db.query(storage.TabelPelayanan).filter(
        storage.TabelPelayanan.doctor_id_ref == p.doctor_id,
        storage.TabelPelayanan.visit_date == q_date
    ).count()

    if current_patient_count >= doc.max_patients:
        raise HTTPException(status_code=400, detail=f"Kuota Dokter Penuh! Maksimal {doc.max_patients} pasien per hari.")

    # 7. GENERATE NOMOR & SIMPAN
    seq = current_patient_count + 1
    try: suf = doc.doctor_code.split('-')[-1]
    except: suf = "001"
    q_str = f"{pol.prefix}-{suf}-{seq:03d}"
    
    cnt_history = db.query(storage.TabelPelayanan).filter(
        storage.TabelPelayanan.username == target_username,
        storage.TabelPelayanan.status_pelayanan == "Selesai"
    ).count()
    stat_mem = "Pasien Lama" if cnt_history > 0 else "Pasien Baru"
    
    new_t = storage.TabelPelayanan(
        username=target_username,
        status_member=stat_mem, 
        nama_pasien=final_nama_pasien, # Menggunakan nama dari DB
        poli=p.poli, 
        dokter=doc.dokter, 
        doctor_id_ref=doc.doctor_id, 
        visit_date=q_date,
        status_pelayanan="Terdaftar", 
        queue_number=q_str, 
        queue_sequence=seq
    )
    db.add(new_t)
    
    gab = storage.TabelGabungan(
        username=target_username, status_member=stat_mem,
        nama_pasien=final_nama_pasien, # Menggunakan nama dari DB
        poli=p.poli, prefix_poli=pol.prefix,
        dokter=doc.dokter, doctor_code=doc.doctor_code, doctor_id=doc.doctor_id,
        visit_date=q_date, status_pelayanan="Terdaftar",
        queue_number=q_str, queue_sequence=seq
    )
    db.add(gab)
    
    db.commit(); db.refresh(new_t)
    
    return {**new_t.__dict__, "doctor_schedule": f"{str(doc.practice_start_time)[:5]} - {str(doc.practice_end_time)[:5]}"}

@router_public.get("/my-history")
def get_history(db: Session = Depends(get_db), current_user: dict = Depends(security.get_current_user_token)):
    return db.query(storage.TabelPelayanan).filter(storage.TabelPelayanan.username == current_user['username']).order_by(storage.TabelPelayanan.visit_date.desc()).all()

# =================================================================
# 7. ANALYTICS & MONITOR
# =================================================================

@router_monitor.get("/queue-board")
def get_board(db: Session = Depends(get_db)):
    return db.query(storage.TabelPelayanan).filter(
        storage.TabelPelayanan.visit_date == date.today(),
        storage.TabelPelayanan.status_pelayanan.in_(["Menunggu", "Sedang Dilayani"])
    ).all()

@router_analytics.get("/comprehensive-report")
def get_analytics(start_date: Optional[date] = None, end_date: Optional[date] = None, db: Session = Depends(get_db)):
    q = db.query(storage.TabelPelayanan)
    if start_date: q = q.filter(storage.TabelPelayanan.visit_date >= start_date)
    if end_date: q = q.filter(storage.TabelPelayanan.visit_date <= end_date)
    
    res = q.all()
    if not res: return {"status": "No Data"}
    
    # Konversi ke DataFrame
    data = [{
        "poli": r.poli, 
        "dokter": r.dokter, 
        "checkin": r.checkin_time, 
        "entry": r.clinic_entry_time, 
        "comp": r.completion_time, 
        "catatan": r.catatan_medis
    } for r in res]
    
    df = pd.DataFrame(data)
    
    # Konversi ke Datetime
    for c in ['checkin','entry','comp']: 
        df[c] = pd.to_datetime(df[c], errors='coerce')
    
    # 1. Hitung Durasi (Dalam Menit)
    # wait_min = Lama menunggu (Checkin -> Masuk Poli)
    # svc_min = Lama diperiksa (Masuk Poli -> Selesai)
    df['wait_min'] = (df['entry'] - df['checkin']).dt.total_seconds() / 60
    df['svc_min'] = (df['comp'] - df['entry']).dt.total_seconds() / 60
    
    # Bersihkan data minus (error input) atau NaN
    valid_svc = df[(df['svc_min'] >= 0) & (df['wait_min'] >= 0)].copy()
    
    # 2. HITUNG KORELASI PEARSON (Wait Time vs Service Time)
    # Logika: Apakah kalau 'wait_min' tinggi (antrean ramai), 'svc_min' jadi rendah (dokter ngebut)?
    corr_val = 0
    if len(valid_svc) > 1: # Butuh minimal 2 data untuk korelasi
        # Hitung korelasi
        c = valid_svc['wait_min'].corr(valid_svc['svc_min'])
        
        # Cek jika hasilnya NaN (misal datanya cuma 1 variasi angka), jadikan 0
        if pd.notna(c):
            corr_val = round(c, 2)
    
    # 3. Text Mining
    txt = " ".join([str(x) for x in df['catatan'].dropna().tolist()])
    
    return {
        "status": "Success",
        "total_patients": len(df),
        "poli_volume": df['poli'].value_counts().to_dict(),
        "peak_hours": df['checkin'].dropna().dt.hour.value_counts().sort_index().to_dict(),
        "ghost_rate": round(len(df[df['checkin'].isna()]) / len(df) * 100, 1),
        
        # Hitung Throughput (Pasien/Jam) hanya dari data yang valid
        "doctor_throughput": valid_svc.groupby('dokter')['svc_min'].mean().apply(lambda x: round(60/x, 1) if x>0 else 0).to_dict(),
        
        "poli_efficiency": {
            p: {
                "wait_minutes": round(df[df['poli']==p]['wait_min'].mean(), 1) if not df[df['poli']==p]['wait_min'].isnull().all() else 0,
                "service_minutes": round(df[df['poli']==p]['svc_min'].mean(), 1) if not df[df['poli']==p]['svc_min'].isnull().all() else 0
            } 
            for p in df['poli'].unique()
        },
        
        "correlation": corr_val, # <--- HASIL KORELASI NYATA
        "text_mining": txt
    }
# =================================================================
# 8. APP ROUTER REGISTRATION (FINAL RBAC)
# =================================================================

app.include_router(router_auth, prefix="/auth")

app.include_router(
    router_public, prefix="/public", 
    dependencies=[Depends(require_role(["admin", "administrasi", "pasien"]))]
)
app.include_router(
    router_ops, prefix="/ops", 
    dependencies=[Depends(require_role(["admin", "perawat", "administrasi"]))]
)
app.include_router(
    router_monitor, prefix="/monitor", 
    dependencies=[Depends(require_role(["admin", "administrasi", "pasien"]))]
)
app.include_router(
    router_admin, prefix="/admin", 
    dependencies=[Depends(require_role(["admin"]))]
)
app.include_router(
    router_analytics, prefix="/analytics", 
    dependencies=[Depends(require_role(["admin"]))]
)