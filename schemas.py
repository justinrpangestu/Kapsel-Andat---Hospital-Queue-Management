from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from typing import Optional, Literal
from datetime import date, datetime, time

# --- HELPER FUNCTIONS ---

def validate_not_empty(v: str, field_name: str):
    if not v or not v.strip():
        raise ValueError(f"{field_name} cannot be empty.")
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

def format_poli_name(name: str) -> str:
    if not name: return name
    
    # Standardize casing (e.g., 'dental clinic' -> 'Dental Clinic')
    clean_name = name.strip().title()
    
    # New Validation: Ensure it ends with 'Clinic' instead of starting with 'Poli'
    if not clean_name.endswith("Clinic"):
        return f"{clean_name} Clinic"
        
    return clean_name
# --- SCHEMAS ---

class PoliCreate(BaseModel):
    clinic: str = Field(..., min_length=3)
    prefix: str = Field(..., min_length=1, max_length=5)
    
    @field_validator('clinic')
    @classmethod
    def format_clinic_suffix(cls, v: str) -> str:
        if not v: return v
        # Normalisasi: Hapus spasi berlebih, jadikan Title Case
        clean = v.strip().title()
        # Jika input cuma "Ento", tambahkan " Clinic"
        if not clean.lower().endswith("clinic"):
            return f"{clean} Clinic"
        return clean
    @field_validator('prefix')
    def check_prefix(cls, v):
        v = validate_not_empty(v, "Prefix")
        if not v.isalpha(): raise ValueError('Prefix must contain only letters (A-Z).')
        return v.upper()
    
    model_config = ConfigDict(json_schema_extra={"example": {"clinic": "Dental", "prefix": "DENT"}})

class DoctorCreate(BaseModel):
    doctor: str = Field(..., min_length=3)
    clinic: str = Field(...)
    practice_start_time: str = Field(..., pattern=r"^\d{2}:\d{2}$")
    practice_end_time: str = Field(..., pattern=r"^\d{2}:\d{2}$")
    max_patients: int = Field(default=20, ge=1)
    doctor_id: Optional[int] = Field(default=None)

    @field_validator('doctor')
    def format_name(cls, v):
        return format_doctor_title(v)
    
    @field_validator('clinic')
    def format_poli_doc(cls, v):
        return format_poli_name(v)

    @model_validator(mode='after')
    def check_times(self):
        try:
            t1 = datetime.strptime(self.practice_start_time, "%H:%M").time()
            t2 = datetime.strptime(self.practice_end_time, "%H:%M").time()
            if t2 <= t1: raise ValueError('End time must be after start time.')
        except ValueError: raise ValueError("Invalid time format")
        return self
    
class ScanRequest(BaseModel):
    barcode_data: str
    location: Literal["arrival", "clinic", "finish"]

class MedicalNoteUpdate(BaseModel):
    catatan: str = Field(..., min_length=3)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "catatan": "Patient has a mild fever. Prescribed Paracetamol 500mg."
            }
        }
    )

class TicketCreate(BaseModel):
    clinic: str
    doctor_id: int
    username_pasien: Optional[str] = None
    visit_date: date

    @field_validator('visit_date')
    def check_date(cls, v):
        if v < date.today():
            raise ValueError('Cannot register for a past date.')
        return v

class UserCreate(BaseModel):
    username: str
    password: str
    nama_lengkap: str

    @field_validator('nama_lengkap')
    def clean_nama(cls, v):
        v = validate_not_empty(v, "Full Name")
        return v.strip().title() 

    @field_validator('username', 'password')
    def clean_credentials(cls, v, info):
        # Automatic Trimming and Lowercasing for Usernames
        return validate_not_empty(v.strip().lower() if info.field_name == 'username' else v, info.field_name)

class Token(BaseModel):
    access_token: str
    token_type: str
    role: str
    nama: str
    status_member: Optional[str] = "Regular"

class PelayananSchema(BaseModel):
    id: int
    patient_name: str
    doctor: str
    clinic: str
    visit_date: date
    service_status: str
    queue_number: str
    queue_sequence: int
    checkin_time: Optional[datetime] = None
    clinic_entry_time: Optional[datetime] = None
    completion_time: Optional[datetime] = None
    catatan_medis: Optional[str] = None 
    estimated_wait_time: Optional[int] = None
    sisa_kuota: Optional[int] = None
    doctor_schedule: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)