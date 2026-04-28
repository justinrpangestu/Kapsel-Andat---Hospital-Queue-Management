# 🏥 RS Pintar 2026 - Clinic Management System

A robust, full-stack hospital management system featuring a **FastAPI backend** and a **Streamlit frontend**.
This system manages clinic registrations, doctor schedules, patient queuing, and medical records with role-based access control.

---

## 🚀 Key Features

* 🔐 **Role-Based Access Control (RBAC)**
  Specific interfaces for Admins, Nurses, Receptionists, and Patients.

* ⏳ **Automated Queuing**
  Intelligent queue number generation and estimated wait time calculation.

* 📂 **CSV Integration**
  Seamlessly loads and cleans data from legacy CSV files.

* 🔒 **Security**
  Password hashing using Argon2 and secure JWT authentication.

* 🏥 **Medical Records**
  Digital storage for medical notes and patient history.

* 📊 **Live Dashboard**
  Real-time statistics and data visualization using Plotly and Matplotlib.

---

## 🛠️ Tech Stack

| Layer    | Technology                       |
| -------- | -------------------------------- |
| Backend  | Python, FastAPI, SQLAlchemy      |
| Frontend | Streamlit                        |
| Database | MySQL (MariaDB)                  |
| Security | JWT (jose), Argon2-cffi, Passlib |
| Data     | Pandas, NumPy, Pydantic          |
| Testing  | Pytest, HTTPX                    |

---

## 📂 Project Structure

```
├── main.py             # FastAPI Backend Entry Point
├── frontend.py         # Streamlit Frontend Application
├── storage.py          # SQLAlchemy Models & Database Config
├── schemas.py          # Pydantic Data Validation Models
├── security.py         # Authentication & JWT Logic
├── csv_utils.py        # CSV Data Cleaning & Processing
├── init_users.py       # Default User Seed Script
├── reset_db.py         # Database Reset & Table Creation
├── requirements.txt    # Project Dependencies
├── .env                # Environment Variables (Secrets)
└── tests/              # Pytest Unit Tests
```

---

## ⚙️ Installation & Setup

### 1. Prerequisites

* Python 3.10+
* MySQL Server running locally

---

### 2. Clone and Install

```bash
git clone <your-repo-url>
cd <project-folder>

python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

pip install -r requirements.txt
```

---

### 3. Environment Configuration

Create a `.env` file in the root directory:

```env
DB_USER=root
DB_PASSWORD=YourPassword
DB_HOST=localhost
DB_PORT=3306
DB_NAME=kapita_selekta_a

SECRET_KEY=your_very_secure_random_secret_key
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60
```

---

### 4. Database Initialization

```bash
# Create tables (will drop existing tables)
python reset_db.py

# Seed default users
python init_users.py
```

**Default Credentials:**

```
Username: admin / nurse / reception
Password: 123
```

---

## 🖥️ Running the Application

### ▶️ Start Backend (API)

```bash
uvicorn main:app --reload
```

* API: http://127.0.0.1:8000
* Docs (Swagger): http://127.0.0.1:8000/docs

---

### ▶️ Start Frontend (UI)

```bash
streamlit run frontend.py
```

* Web UI: http://localhost:8501

---

## 🧪 Running Tests

```bash
pytest test_main.py -v
```

---

## 📝 Important Notes

* ⚠️ Ensure database `kapita_selekta_a` already exists
* 📄 Required CSV files:

  * `tabel_poli_normal.csv`
  * `tabel_dokter_normal.csv`
  * `tabel_pelayanan_normal.csv`
* 🔐 Never commit `.env` file (already in `.gitignore`)

---

## ⭐ Future Improvements

* Dockerization
* CI/CD Pipeline
* Deployment (AWS / GCP)
* UI enhancement

---
