import uuid
import pytest
from fastapi.testclient import TestClient
from main import app
from datetime import date, timedelta

client = TestClient(app)

def test_register_patient():
    unique_username = f"user_{uuid.uuid4().hex[:6]}"
    response = client.post(
        "/auth/register",
        json={
            "username": unique_username,
            "password": "password123",
            "nama_lengkap": "Unit Test Patient"
        }
    )
    assert response.status_code == 200
    assert response.json()["role"] == "pasien"

def test_login_wrong_password():
    response = client.post(
        "/auth/login",
        data={"username": "admin", "password": "wrongpassword"}
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid username or password"

def test_admin_access_without_token():
    response = client.get("/admin/doctors")
    assert response.status_code == 401

def test_registration_without_token():
    payload = {"poli": "Poli Gigi", "doctor_id": 1, "visit_date": str(date.today())}
    response = client.post("/public/submit", json=payload)
    assert response.status_code == 401

def get_token(username, password="123", nama="Test User"):
    client.post("/auth/register", json={"username": username, "password": password, "nama_lengkap": nama})
    response = client.post("/auth/login", data={"username": username, "password": password})
    return response.json().get("access_token")

def test_login_success():
    username = f"login_{uuid.uuid4().hex[:4]}"
    client.post("/auth/register", json={"username": username, "password": "123", "nama_lengkap": "User Login"})
    response = client.post("/auth/login", data={"username": username, "password": "123"})
    assert response.status_code == 200
    assert "access_token" in response.json()

def test_ticket_registration_success():
    username = f"ticket_{uuid.uuid4().hex[:4]}"
    token = get_token(username)
    headers = {"Authorization": f"Bearer {token}"}
    tomorrow = date.today() + timedelta(days=1)

    payload = {"poli": "Poli Gigi", "doctor_id": 1, "visit_date": str(tomorrow)}
    response = client.post("/public/submit", json=payload, headers=headers)
    assert response.status_code == 200
    assert "queue_number" in response.json()

def test_pendaftaran_dan_kuota():
    login_res = client.post("/auth/login", data={"username": "admin", "password": "123"})
    if login_res.status_code != 200:
        pytest.skip("Admin user not initialized.")
    
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    tomorrow = date.today() + timedelta(days=1)
    
    target_pasien = f"target_{uuid.uuid4().hex[:4]}"
    client.post("/auth/register", json={"username": target_pasien, "password": "123", "nama_lengkap": "Target Patient"})

    payload = {
        "poli": "Poli Gigi", 
        "doctor_id": 1, 
        "visit_date": str(tomorrow),
        "username_pasien": target_pasien
    }

    response = client.post("/public/submit", json=payload, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "sisa_kuota" in data
    assert "estimated_wait_time" in data

def test_trim_username_logic():
    unique = f"  Trim_{uuid.uuid4().hex[:4]}  "
    client.post("/auth/register", json={"username": unique, "password": "123", "nama_lengkap": "Trim Test"})
    response = client.post("/auth/login", data={"username": unique.strip().lower(), "password": "123"})
    assert response.status_code == 200