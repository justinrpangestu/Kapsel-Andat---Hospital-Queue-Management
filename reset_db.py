from storage import engine, Base
from sqlalchemy import text

def reset_database():
    print("🔄 Wiping old database tables...")
    with engine.connect() as conn:
        # Disable checks to allow dropping tables with relationships
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        
        tables = [
            "tabel_gabungan_transaksi",
            "tabel_pelayanan_normal",
            "tabel_dokter_normal",
            "tabel_poli_normal",
            "tabel_users"
        ]
        
        for table in tables:
            conn.execute(text(f"DROP TABLE IF EXISTS {table}"))
            print(f"🗑️ Dropped: {table}")
            
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
        conn.commit()
    
    print("🏗️ Creating new database schema with English field names...")
    Base.metadata.create_all(bind=engine)
    print("✅ Success! Database is now clean and ready.")

if __name__ == "__main__":
    reset_database()