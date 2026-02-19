from storage import SessionLocal, TabelUser
import security

def init_users_final():
    db = SessionLocal()
    try:
        print("🔄 Menginisialisasi Akun Sesuai Role Baru...")
        
        staff_list = [
            # 1. ADMIN (Bisa Semua)
            {"username": "admin", "nama": "Super Admin", "role": "admin"},
            
            # 2. PERAWAT (Scanner + Ruang Periksa)
            {"username": "perawat", "nama": "Ns. Melati", "role": "perawat"},
            
            # 3. ADMINISTRASI (Pendaftaran + Scanner + TV)
            {"username": "admin_depan", "nama": "Petugas Administrasi", "role": "administrasi"},
        ]
        
        for staff in staff_list:
            cek = db.query(TabelUser).filter(TabelUser.username == staff['username']).first()
            if not cek:
                new_user = TabelUser(
                    username=staff['username'],
                    password=security.get_password_hash("123"),
                    role=staff['role'],
                    nama_lengkap=staff['nama']
                )
                db.add(new_user)
                print(f"✅ Akun dibuat: {staff['username']} ({staff['role']})")
            else:
                # Update role jika beda (agar sesuai request terbaru Anda)
                if cek.role != staff['role']:
                    cek.role = staff['role']
                    db.commit()
                    print(f"🔄 Role diupdate: {staff['username']} -> {staff['role']}")
                else:
                    print(f"ℹ️ Akun sudah ada: {staff['username']}")

        db.commit()
        print("Selesai. Password default: 123")
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    init_users_final()