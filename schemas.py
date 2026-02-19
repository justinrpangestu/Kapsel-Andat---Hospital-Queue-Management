from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from typing import Optional, Literal
from datetime import date, datetime, time

# --- HELPER FUNCTIONS ---

def validate_not_empty(v: str, field_name: str):
    if not v or not v.strip():
        raise ValueError(f"{field_name} tidak boleh kosong.")
    return v.strip()

def format_doctor_title(name: str) -> str:
    if not name: return name
    clean_name = name.strip()
    lower_name = clean_name.lower()
    if lower_name.startswith("dr."):
        clean_name = clean_name[3:].strip()
    elif lower_name.startswith("dr"):
        clean_name = clean_name[2:].strip()
    return f"dr. {clean_name.title()}"

# [BARU] Helper untuk Format Nama Poli
def format_poli_name(name: str) -> str:
    if not name: return name
    # 1. Bersihkan spasi & ubah ke Title Case (PolI GigI -> Poli Gigi)
    clean_name = name.strip().title()
    
    # 2. Cek apakah sudah ada "Poli" di depan
    # Kita pakai startswith. Jika belum ada "Poli ", tambahkan.
    if not clean_name.startswith("Poli "):
        # Tangani kasus nempel misal "Poligigi" -> "Poli Gigi" (Opsional, tapi bagus)
        if clean_name.startswith("Poli") and len(clean_name) > 4:
             clean_name = clean_name[4:].strip()
        
        return f"Poli {clean_name}"
    
    return clean_name

# --- SCHEMAS ---

class PoliCreate(BaseModel):
    poli: str = Field(..., min_length=3)
    prefix: str = Field(..., min_length=1, max_length=5)
    
    # --- VALIDATOR OTOMATIS POLI ---
    @field_validator('poli')
    def format_poli(cls, v):
        return format_poli_name(v)
    # -------------------------------

    @field_validator('prefix')
    def check_prefix(cls, v):
        v = validate_not_empty(v, "Prefix")
        if not v.isalpha(): raise ValueError('Prefix hanya boleh huruf (A-Z).')
        return v.upper()
    
    model_config = ConfigDict(json_schema_extra={"example": {"poli": "Mata", "prefix": "MATA"}})

class DoctorCreate(BaseModel):
    dokter: str = Field(..., min_length=3)
    poli: str = Field(...)
    practice_start_time: str = Field(..., pattern=r"^\d{2}:\d{2}$")
    practice_end_time: str = Field(..., pattern=r"^\d{2}:\d{2}$")
    max_patients: int = Field(default=20, ge=1)
    doctor_id: Optional[int] = Field(default=None)

    @field_validator('dokter')
    def format_name(cls, v):
        return format_doctor_title(v)
    
    # [BARU] Validasi Poli di Dokter juga biar konsisten
    # Kalau user kirim dokter baru di "Gigi", otomatis jadi "Poli Gigi"
    @field_validator('poli')
    def format_poli_doc(cls, v):
        return format_poli_name(v)

    @model_validator(mode='after')
    def check_times(self):
        try:
            t1 = datetime.strptime(self.practice_start_time, "%H:%M").time()
            t2 = datetime.strptime(self.practice_end_time, "%H:%M").time()
            if t2 <= t1: raise ValueError('Jam Selesai harus lebih akhir.')
        except ValueError: raise ValueError("Format jam salah")
        return self
        
    model_config = ConfigDict(json_schema_extra={"example": {"dokter": "Jeri", "poli": "Mata", "practice_start_time": "08:00", "practice_end_time": "16:00", "max_patients": 20}})

class DoctorUpdate(BaseModel):
    dokter: Optional[str] = None
    poli: Optional[str] = None
    max_patients: Optional[int] = Field(default=None, ge=1)
    practice_start_time: Optional[str] = None
    practice_end_time: Optional[str] = None
    
    @field_validator('dokter')
    def format_name(cls, v):
        if v: return format_doctor_title(v)
        return v

    @field_validator('poli')
    def format_poli(cls, v):
        if v: return format_poli_name(v)
        return v

    model_config = ConfigDict(json_schema_extra={"example": {"dokter": "Jeri Edit", "poli": "Poli Mata", "max_patients": 25, "practice_start_time": "09:00", "practice_end_time": "17:00"}})

class RegistrationFinal(BaseModel):
    nama_pasien: str = Field(..., min_length=3)
    poli: str = Field(...)
    doctor_id: int = Field(...)
    visit_date: date = Field(...)
    
    @field_validator('nama_pasien')
    def check_pasien(cls, v): return validate_not_empty(v, "Nama Pasien")
    
    @field_validator('visit_date')
    def check_date(cls, v):
        if v < date.today(): raise ValueError('Tanggal masa lalu.')
        return v
        
    model_config = ConfigDict(json_schema_extra={"example": {"nama_pasien": "Budi", "poli": "Poli Mata", "doctor_id": 1, "visit_date": "2025-12-01"}})

class ScanRequest(BaseModel):
    barcode_data: str = Field(..., min_length=1)
    location: str = Field(..., pattern="^(arrival|clinic|finish)$")
    model_config = ConfigDict(json_schema_extra={"example": {"barcode_data": "MATA-001-001", "location": "arrival"}})

class MedicalNoteUpdate(BaseModel):
    catatan: str = Field(..., min_length=3, description="Hasil diagnosa atau catatan dokter")

    # --- TAMBAHKAN BAGIAN INI (CONFIG DENGAN CONTOH) ---
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "catatan": "Pasien mengalami flu ringan. Diberikan resep Paracetamol 3x1."
            }
        }
    )

class PoliSchema(BaseModel):
    poli: str; prefix: str
    model_config = ConfigDict(from_attributes=True)

class PoliUpdate(BaseModel):
    new_name: Optional[str] = None
    new_prefix: Optional[str] = None

class DoctorSchema(BaseModel):
    doctor_id: int; dokter: str; poli: str; doctor_code: str
    practice_start_time: time; practice_end_time: time; max_patients: int
    model_config = ConfigDict(from_attributes=True)

class PelayananSchema(BaseModel):
    id: int; nama_pasien: str; dokter: str; poli: str; visit_date: date
    status_pelayanan: Literal["Terdaftar", "Menunggu", "Sedang Dilayani", "Selesai"]
    queue_number: str; queue_sequence: int
    checkin_time: Optional[datetime] = None
    clinic_entry_time: Optional[datetime] = None
    completion_time: Optional[datetime] = None
    doctor_schedule: Optional[str] = None 
    catatan_medis: Optional[str] = None 
    model_config = ConfigDict(from_attributes=True)

class ClinicStats(BaseModel):
    poli_name: str; total_doctors: int; total_patients_today: int
    patients_waiting: int; patients_being_served: int; patients_finished: int
    model_config = ConfigDict(from_attributes=True)

# --- AUTH SCHEMAS ---

class UserLogin(BaseModel):
    username: str
    password: str

# HAPUS validator 'clean_nama' dari sini jika ada!
    # Validator ini hanya boleh ada di UserLogin:
    @field_validator('username', 'password')
    def clean_credentials(cls, v, info):
        return validate_not_empty(v, info.field_name)


class UserCreate(BaseModel):
    username: str
    password: str
    nama_lengkap: str

    # Validator Nama Lengkap (Trim + Title Case) -> TEMPATNYA DI SINI
    @field_validator('nama_lengkap')
    def clean_nama(cls, v):
        v = validate_not_empty(v, "Nama Lengkap")
        return v.title() 

    # Validator Username & Password
    @field_validator('username', 'password')
    def clean_credentials(cls, v, info):
        return validate_not_empty(v, info.field_name)

class Token(BaseModel):
    access_token: str
    token_type: str
    role: str
    nama: str
    status_member: Optional[str] = "Reguler"

class TicketCreate(BaseModel):
    poli: str
    doctor_id: int
    username_pasien: Optional[str] = None # Tetap ada untuk Petugas/Admin
    visit_date: str

    # KHUSUS POLI: Cukup Trim (karena poli biasanya dipilih dari dropdown, formatnya sudah tetap)
    @field_validator('poli')
    def clean_poli(cls, v):
        return validate_not_empty(v, "Poli")
    
    # --- TAMBAHKAN CONTOH DI SINI ---
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "nama_pasien": "Budi Santoso",
                "poli": "Poli Umum",
                "doctor_id": 1,
                "visit_date": "2023-12-31",
                "username_pasien": "budi123"
            }
        }
    )