import uuid
import pytest
from fastapi.testclient import TestClient
from main import app
from storage import Base, engine, SessionLocal
from datetime import date,timedelta

# Setup Client untuk testing
client = TestClient(app)

# Test Fungsi Register Pasien Baru
def test_register_pasien():
    unique_username = f"user_{uuid.uuid4().hex[:6]}"
    response = client.post(
        "/auth/register",
        json={
            "username": unique_username,
            "password": "password123",
            "nama_lengkap": "Pasien Test Unit"
        }
    )
    assert response.status_code == 200
    assert response.json()["role"] == "pasien"

# Test Login Gagal (Password Salah)
def test_login_salah_password():
    response = client.post(
        "/auth/login",
        data={"username": "pasientest", "password": "salahpassword"}
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Username atau password salah"

# Test Akses Menu Admin Tanpa Token (Harus Ditolak)
def test_akses_admin_tanpa_token():
    response = client.get("/admin/doctors")
    assert response.status_code == 401 # Unauthorized

def test_pendaftaran_tanpa_token():
    # Mencoba daftar tanpa header Authorization
    payload = {
        "poli": "Poli Umum",
        "doctor_id": 1,
        "visit_date": str(date.today())
    }
    response = client.post("/public/submit", json=payload)
    assert response.status_code == 401


def test_trim_username_login():
    # Memastikan login berhasil meski input username di-trim otomatis
    response = client.post(
        "/auth/login",
        data={"username": "  ADMIN  ", "password": "123"} 
    )
    assert response.status_code == 200

#Helper untuk mendapatkan token tanpa mengulang kode
def get_token(username, password="123", nama="Test User"):
    # Pastikan user terdaftar dulu
    client.post("/auth/register", json={
        "username": username, "password": password, "nama_lengkap": nama
    })
    # Login
    response = client.post("/auth/login", data={"username": username, "password": password})
    return response.json().get("access_token")


def test_login_berhasil():
    # Buat user baru khusus untuk test ini agar tidak tergantung test lain
    username = f"login_{uuid.uuid4().hex[:4]}"
    client.post("/auth/register", json={
        "username": username, "password": "password123", "nama_lengkap": "User Login"
    })
    
    response = client.post(
        "/auth/login",
        data={"username": username, "password": "password123"}
    )
    assert response.status_code == 200
    assert "access_token" in response.json()

def test_pendaftaran_tiket_berhasil():
    username = f"ptiket_{uuid.uuid4().hex[:4]}"
    token = get_token(username)
    headers = {"Authorization": f"Bearer {token}"}

    # Gunakan H+1 agar tidak kena validasi jam praktek yang sudah tutup
    besok = date.today() + timedelta(days=1)

    # SESUAIKAN DENGAN CSV: Doctor ID 1 adalah Poli Gigi
    payload = {
        "poli": "Poli Gigi", # Ubah dari Poli Umum ke Poli Gigi
        "doctor_id": 1,
        "visit_date": str(besok)
    }

    response = client.post("/public/submit", json=payload, headers=headers)
    assert response.status_code == 200
    assert "queue_number" in response.json()

def test_pendaftaran_dan_kuota():
    # Gunakan akun admin (asumsi sudah jalan init_users.py)
    # Jika ragu, kita buat admin baru di sini
    admin_user = f"admin_{uuid.uuid4().hex[:4]}"
    # Daftarkan manual sebagai admin lewat DB atau gunakan user yang ada
    # Untuk testing, kita gunakan user biasa tapi role-nya dipaksa lewat register jika diizinkan
    # Namun sesuai main.py, register defaultnya 'pasien'. 
    # Mari gunakan 'admin' yang sudah ada dari init_users.py
    
    login_res = client.post("/auth/login", data={"username": "admin", "password": "123"})
    if login_res.status_code != 200:
        pytest.skip("User 'admin' belum diinisialisasi. Jalankan python init_users.py dulu.")
    
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    besok = date.today() + timedelta(days=1)
    # BUAT PASIEN BARU untuk didaftarkan oleh admin agar tidak bentrok tiket
    target_pasien = f"target_{uuid.uuid4().hex[:4]}"
    client.post("/auth/register", json={"username": target_pasien, "password": "123", "nama_lengkap": "Pasien Target"})
    # Test pendaftaran dengan Poli yang benar (Gigi untuk ID 1)
    payload = {
        "poli": "Poli Gigi", 
        "doctor_id": 1,
        "visit_date": str(besok),
        "username_pasien": target_pasien # Mendaftarkan pasien target
    }

    response = client.post("/public/submit", json=payload, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "sisa_kuota" in data
    assert "estimated_wait_time" in data

def test_trim_username_logic():
    unique = f"  Trim_{uuid.uuid4().hex[:4]}  "
    # Register
    client.post("/auth/register", json={
        "username": unique, "password": "123", "nama_lengkap": "Trim Test"
    })
    
    # Login dengan huruf kecil tanpa spasi (karena backend harusnya sudah nge-trim)
    response = client.post(
        "/auth/login",
        data={"username": unique.strip().lower(), "password": "123"}
    )
    assert response.status_code == 200