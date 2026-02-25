from storage import SessionLocal, TabelUser
import security

def init_users_final():
    db = SessionLocal()
    try:
        print("🔄 Initializing Staff Accounts...")
        
        staff_list = [
        {"username": "admin", "nama": "Super Admin", "role": "admin"},
        {"username": "nurse", "nama": "Nurse Melati", "role": "nurse"},
        {"username": "reception", "nama": "Reception Staff", "role": "reception"},
        ]
        
        for staff in staff_list:
            check = db.query(TabelUser).filter(TabelUser.username == staff['username']).first()
            if not check:
                new_user = TabelUser(
                    username=staff['username'],
                    password=security.get_password_hash("123"),
                    role=staff['role'],
                    nama_lengkap=staff['nama']
                )
                db.add(new_user)
                print(f"✅ Account created: {staff['username']} ({staff['role']})")
            else:
                if check.role != staff['role']:
                    check.role = staff['role']
                    db.commit()
                    print(f"🔄 Role updated: {staff['username']} -> {staff['role']}")
                else:
                    print(f"ℹ️ Account already exists: {staff['username']}")

        db.commit()
        print("Done. Default password: 123")
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    init_users_final()