import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, Integer, String, Date, Time, DateTime, ForeignKey
from sqlalchemy.orm import sessionmaker, relationship, declarative_base
import datetime
from datetime import datetime

load_dotenv()

# Konfigurasi Database
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "3306")
DB_NAME = os.getenv("DB_NAME", "hospital_db")

DB_URL = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

engine = create_engine(DB_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def init_db():
    Base.metadata.create_all(bind=engine)

class TabelPoli(Base):
    __tablename__ = "tabel_poli_normal"
    poli = Column(String(100), primary_key=True, index=True)
    
    prefix = Column(String(10), unique=True) 
    
    dokters = relationship("TabelDokter", back_populates="poli_rel")

class TabelDokter(Base):
    __tablename__ = "tabel_dokter_normal"
    doctor_id = Column(Integer, primary_key=True, index=True) 
    dokter = Column(String(100))
    poli = Column(String(100), ForeignKey("tabel_poli_normal.poli"))
    practice_start_time = Column(Time)
    practice_end_time = Column(Time)
    doctor_code = Column(String(50))
    max_patients = Column(Integer)
    poli_rel = relationship("TabelPoli", back_populates="dokters")
    pelayanans = relationship("TabelPelayanan", back_populates="dokter_rel")

class TabelPelayanan(Base):
    __tablename__ = "tabel_pelayanan_normal"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    username = Column(String(50), index=True)
    nama_pasien = Column(String(100))
    poli = Column(String(100))
    dokter = Column(String(100))
    doctor_id_ref = Column(Integer, ForeignKey("tabel_dokter_normal.doctor_id"))
    visit_date = Column(Date)
    checkin_time = Column(DateTime, nullable=True)
    clinic_entry_time = Column(DateTime, nullable=True)
    completion_time = Column(DateTime, nullable=True)
    status_pelayanan = Column(String(50))
    queue_number = Column(String(50))
    queue_sequence = Column(Integer)
    # [BARU] Kolom Catatan Medis
    catatan_medis = Column(String(255), nullable=True)
    status_member = Column(String(20))
    
    dokter_rel = relationship("TabelDokter", back_populates="pelayanans")

class TabelGabungan(Base):
    __tablename__ = "tabel_gabungan_transaksi"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), index=True)
    nama_pasien = Column(String(100))
    poli = Column(String(100))
    prefix_poli = Column(String(10))
    dokter = Column(String(100))
    doctor_code = Column(String(50))
    doctor_id = Column(Integer)
    visit_date = Column(Date)
    checkin_time = Column(DateTime)
    clinic_entry_time = Column(DateTime)
    completion_time = Column(DateTime)
    status_pelayanan = Column(String(50))
    queue_number = Column(String(50))
    queue_sequence = Column(Integer)
    
    # [BARU] Kolom Catatan Medis (untuk Analytics)
    catatan_medis = Column(String(255), nullable=True)
    status_member = Column(String(20))

class TabelUser(Base):
    __tablename__ = "tabel_users"
    username = Column(String(50), primary_key=True, index=True)
    password = Column(String(255))
    role = Column(String(20)) # 'admin', 'dokter', 'pasien'
    nama_lengkap = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)