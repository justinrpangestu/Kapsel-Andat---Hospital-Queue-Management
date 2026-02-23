from storage import engine, Base
from sqlalchemy import text

def reset():
    print("Deleting old database...")
    with engine.connect() as conn:
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        conn.execute(text("DROP TABLE IF EXISTS tabel_gabungan_transaksi"))
        conn.execute(text("DROP TABLE IF EXISTS tabel_pelayanan_normal"))
        conn.execute(text("DROP TABLE IF EXISTS tabel_dokter_normal"))
        conn.execute(text("DROP TABLE IF EXISTS tabel_poli_normal"))
        conn.execute(text("DROP TABLE IF EXISTS tabel_users"))
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
        conn.commit()
    
    print("Creating new database schema...")
    Base.metadata.create_all(bind=engine)
    print("Success! The database is ready.")

if __name__ == "__main__":
    reset()