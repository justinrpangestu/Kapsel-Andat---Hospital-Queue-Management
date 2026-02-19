import streamlit as st
import requests
import pandas as pd
from datetime import datetime, time
import time as time_lib
import qrcode
import io
import cv2
import numpy as np
import json
import plotly.express as px
import plotly.graph_objects as go
from wordcloud import WordCloud
import matplotlib.pyplot as plt

# --- KONFIGURASI ---
API_URL = "http://127.0.0.1:8000"
st.set_page_config(page_title="Sistem RS Pintar", layout="wide", page_icon="🏥")

# --- CSS CUSTOM (Tampilan Lebih Modern) ---
st.markdown("""
<style>
    div.stButton > button:first-child { border-radius: 8px; font-weight: bold; }
    div[data-testid="stMetricValue"] { font-size: 28px; color: #007bff; font-weight: bold; }
    .reportview-container .main .block-container { max-width: 1200px; }
</style>
""", unsafe_allow_html=True)

# =================================================================
# 0. SETUP SESSION
# =================================================================
if 'token' not in st.session_state:
    st.session_state.update({'token': None, 'role': None, 'nama_user': None, 'status_member': None, 'selected_doc': None})

# --- HELPERS ---
def generate_qr(data):
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(json.dumps(data))
    qr.make(fit=True)
    return qr.make_image(fill_color="black", back_color="white")

def decode_qr_from_image(image_buffer):
    try:
        file_bytes = np.asarray(bytearray(image_buffer.read()), dtype=np.uint8)
        img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
        detector = cv2.QRCodeDetector()
        data, _, _ = detector.detectAndDecode(img)
        return data if data else None
    except: return None

# =================================================================
# A. LOGIKA LOGIN / REGISTER
# =================================================================
if st.session_state['token'] is None:
    st.markdown("<h1 style='text-align: center; color: #2E86C1;'>🏥 Sistem Rumah Sakit Pintar</h1>", unsafe_allow_html=True)
    st.divider()
    c1, c2 = st.columns(2)
    
    with c1:
        st.subheader("🔐 Login")
        u = st.text_input("Username", key="lu")
        p = st.text_input("Password", type="password", key="lp")
        if st.button("Masuk", type="primary", use_container_width=True):
            try:
                r = requests.post(f"{API_URL}/auth/login", data={"username": u, "password": p})
                if r.status_code == 200:
                    d = r.json()
                    st.session_state.update({
                        'token': d['access_token'], 
                        'role': d['role'], 
                        'nama_user': d['nama'], 
                        'status_member': d.get('status_member') 
                    })
                    st.rerun()
                else: st.error(r.json().get('detail', 'Login Gagal'))
            except Exception as e: st.error(f"Error Koneksi: {e}")

    with c2:
        st.subheader("📝 Daftar Pasien Baru")
        rn = st.text_input("Nama Lengkap", key="rn")
        ru = st.text_input("Username", key="ru")
        rp = st.text_input("Password", type="password", key="rp")
        
        if st.button("Daftar", use_container_width=True):
            if rn and ru and rp:
                sukses_daftar = False 
                try:
                    payload = {
                        "username": ru.strip(), 
                        "password": rp.strip(), 
                        "nama_lengkap": rn.strip(), 
                        "role": "pasien"
                    }
                    r = requests.post(f"{API_URL}/auth/register", json=payload)
                    
                    if r.status_code == 200:
                        d = r.json()
                        st.session_state.update({
                            'token': d['access_token'], 
                            'role': d['role'], 
                            'nama_user': d['nama'], 
                            'status_member': "Pasien Baru"
                        })
                        st.success("Berhasil! Mengalihkan...")
                        sukses_daftar = True 
                    else: 
                        st.error(f"Gagal: {r.json().get('detail', 'Unknown Error')}")
                except Exception as e: st.error(f"Error Koneksi: {str(e)}")

                if sukses_daftar:
                    time_lib.sleep(1); st.rerun()
            else:
                st.warning("Mohon isi semua kolom.")

# =================================================================
# B. APLIKASI UTAMA (SETELAH LOGIN)
# =================================================================
else:
    role = st.session_state['role']
    
    # --- SIDEBAR ---
    st.sidebar.image("https://cdn-icons-png.flaticon.com/512/3135/3135715.png", width=80)
    st.sidebar.write(f"Halo, **{st.session_state['nama_user']}**")
    if st.session_state.get('status_member'):
        st.sidebar.info(f"Status: **{st.session_state['status_member']}**")
    st.sidebar.caption(f"Akses Role: {role.upper()}")
    
    if st.sidebar.button("Logout"):
        st.session_state.clear(); st.rerun()
    st.sidebar.markdown("---")

    # --- MENU ---
    MENU_DAFTAR = "📝 Pendaftaran"
    MENU_RIWAYAT = "📂 Riwayat & Tiket"
    MENU_SCAN = "📠 Scanner QR"
    MENU_DOKTER = "👨‍⚕️ Ruang Periksa"
    MENU_TV = "📺 Layar Antrean"
    MENU_ADMIN = "📊 Dashboard Admin"
    MENU_ANALISIS = "📈 Data Science & Insights" # Nama baru biar keren

    menu_opts = []
    if role == "admin": menu_opts = [MENU_DAFTAR, MENU_SCAN, MENU_DOKTER, MENU_TV, MENU_ADMIN, MENU_ANALISIS]
    elif role == "perawat": menu_opts = [MENU_SCAN, MENU_DOKTER]
    elif role == "administrasi": menu_opts = [MENU_DAFTAR, MENU_SCAN, MENU_TV]
    elif role == "pasien": menu_opts = [MENU_DAFTAR, MENU_RIWAYAT, MENU_TV]
    else: menu_opts = [MENU_TV]

    menu = st.sidebar.radio("Navigasi", menu_opts)
    headers = {"Authorization": f"Bearer {st.session_state['token']}"}

    # =================================================================
    # 1. MENU PENDAFTARAN
    # =================================================================
    if menu == MENU_DAFTAR:
        st.header("📝 Pendaftaran Pasien")
        try: 
            p_map = {p['poli']: p for p in sorted(requests.get(f"{API_URL}/public/polis", headers=headers).json(), key=lambda x: x['poli'])}
        except: p_map = {}

        c1, c2 = st.columns(2)
        nm = ""
        target_user_input = None 
        
        if role in ['admin', 'administrasi', 'perawat']:
            nm = c1.text_input("Nama Pasien (Sesuai KTP)")
            target_user_input = c1.text_input("Username Akun Pasien", help="Opsional")
        else:
            nm = c1.text_input("Nama Pasien", value=st.session_state['nama_user'], disabled=True)
        
        pl = c1.selectbox("Poli Tujuan", list(p_map.keys()) if p_map else [], index=None, placeholder="Pilih Poli...")
        tg = c2.date_input("Tanggal Kunjungan", min_value=datetime.today())

        if pl:
            st.markdown("### Pilih Dokter")
            try:
                docs = requests.get(f"{API_URL}/public/available-doctors", params={"poli_name": pl}, headers=headers).json()
                if not docs: st.warning("Dokter libur/tidak tersedia.")
                else:
                    cols = st.columns(3)
                    for i, d in enumerate(docs):
                        with cols[i % 3]:
                            with st.container(border=True):
                                st.subheader(d['dokter'])
                                st.info(f"🕒 {str(d['practice_start_time'])[:5]} - {str(d['practice_end_time'])[:5]}")
                                st.caption(f"Sisa Kuota: {d['max_patients']}")
                                if st.button("Pilih", key=d['doctor_id'], use_container_width=True):
                                    st.session_state['selected_doc'] = d
                                    st.rerun()
            except: pass
        
        if st.session_state['selected_doc']:
            doc = st.session_state['selected_doc']
            st.success(f"Dokter Pilihan: **{doc['dokter']}**")
            
            if st.button("✅ Konfirmasi Pendaftaran", type="primary", use_container_width=True):
                clean_nm = nm.strip() if nm else ""
                if not clean_nm: st.error("⚠️ Nama Pasien WAJIB diisi!"); st.stop()
                
                payload = {"nama_pasien": clean_nm, "poli": pl, "doctor_id": doc['doctor_id'], "visit_date": str(tg)}
                if target_user_input: payload["username_pasien"] = target_user_input.strip()
                
                try:
                    r = requests.post(f"{API_URL}/public/submit", json=payload, headers=headers)
                    if r.status_code == 200:
                        d = r.json()
                        st.balloons()
                        with st.container(border=True):
                            st.markdown("### 🎫 Tiket Antrean Berhasil Dibuat")
                            cq, ct = st.columns([1, 2])
                            with cq:
                                buf = io.BytesIO()
                                generate_qr({"id": d['id'], "antrean": d['queue_number']}).save(buf, format="PNG")
                                st.image(buf, use_container_width=True)
                            with ct:
                                st.subheader(f"No. {d['queue_number']}")
                                st.write(f"**{d['poli']}** - {d['dokter']}")
                                st.write(f"📅 {d['visit_date']}")
                                st.info("Silakan cetak atau foto QR Code ini.")
                        st.session_state['selected_doc'] = None
                    else: st.error(f"⛔ Gagal! Status Code: {r.status_code}\n{r.text}")
                except Exception as e: st.error(f"Error Sistem: {str(e)}")

    # =================================================================
    # 2. MENU RIWAYAT
    # =================================================================
    elif menu == MENU_RIWAYAT:
        st.header("📂 Tiket & Riwayat Saya")
        try:
            r = requests.get(f"{API_URL}/public/my-history", headers=headers)
            data = r.json()
            if not data: st.info("Belum ada riwayat.")
            else:
                for t in data:
                    with st.container(border=True):
                        c1, c2, c3 = st.columns([1, 3, 1])
                        with c1:
                            buf = io.BytesIO(); generate_qr({"id": t['id'], "antrean": t['queue_number']}).save(buf, format="PNG")
                            st.image(buf)
                        with c2:
                            st.subheader(t['queue_number'])
                            st.write(f"**{t['poli']}** | {t['dokter']}")
                            st.caption(f"{t['visit_date']}")
                            if t.get('catatan_medis'): st.info(f"Catatan: {t['catatan_medis']}")
                        with c3:
                            st.write(f"Status: **{t['status_pelayanan']}**")
        except: st.error("Gagal load data.")

    # =================================================================
    # 3. MENU SCANNER
    # =================================================================
    elif menu == MENU_SCAN:
        st.header("📠 Scanner QR")
        loc_map = {"Pintu Masuk (Check-in)": "arrival", "Masuk Poli (Panggil)": "clinic", "Selesai (Pulang)": "finish"}
        sel_loc = loc_map[st.radio("Lokasi Scan:", list(loc_map.keys()), horizontal=True)]
        
        t1, t2 = st.tabs(["Kamera", "Manual"])
        
        # --- PERBAIKAN DI SINI (TAB KAMERA) ---
        with t1:
            img = st.camera_input("Arahkan ke QR")
            if img:
                code = decode_qr_from_image(img)
                
                # JIKA QR TERBACA
                if code:
                    try: val = str(json.loads(code.replace("'", '"')).get("antrean", code))
                    except: val = str(code)
                    
                    try:
                        r = requests.post(f"{API_URL}/ops/scan-barcode", json={"barcode_data": val, "location": sel_loc}, headers=headers)
                        d = r.json()
                        if r.status_code == 200:
                            if d['status'] == 'Success': st.success(f"✅ {d['message']}"); st.balloons()
                            elif d['status'] == 'Warning': st.warning(f"⚠️ {d['message']}")
                            else: st.error(f"⛔ {d['message']}")
                            time_lib.sleep(2); st.rerun()
                        else: st.error(f"❌ {r.text}")
                    except Exception as e: st.error(f"Koneksi: {e}")
                
                # JIKA QR GAGAL DIBACA (TIDAK JELAS/BURAM)
                else:
                    st.warning("⚠️ QR Code tidak terbaca. Pastikan pencahayaan cukup atau QR Code tidak buram.")
                    st.caption("Tips: Coba dekatkan atau jauhkan sedikit kamera dari QR Code.")

        with t2:
            mc = st.text_input("Kode Antrean (Contoh: MATA-001-001)", key="man_code")
            if st.button("Proses"):
                try:
                    r = requests.post(f"{API_URL}/ops/scan-barcode", json={"barcode_data": mc, "location": sel_loc}, headers=headers)
                    d = r.json()
                    if r.status_code == 200:
                        st.success(f"✅ {d['message']}"); time_lib.sleep(1); st.rerun()
                    else: st.error(f"❌ {r.text}")
                except Exception as e: st.error(f"Koneksi: {e}")

    # =================================================================
    # 4. MENU RUANG PERIKSA
    # =================================================================
    elif menu == MENU_DOKTER:
        st.header("👨‍⚕️ Ruang Periksa (Input Medis)")
        try:
            res_docs = requests.get(f"{API_URL}/admin/doctors", headers=headers) 
            doc_list = [d['dokter'] for d in res_docs.json()] if res_docs.status_code == 200 else []
            if not doc_list: st.warning("Gagal memuat list dokter."); st.stop()
            selected_doc = st.selectbox("Pilih Dokter Bertugas:", doc_list)
        except: st.error("Koneksi Error"); st.stop()

        st.markdown("---")
        current_p = None
        try:
            q_data = requests.get(f"{API_URL}/monitor/queue-board", headers=headers).json()
            current_p = next((p for p in q_data if p['dokter'] == selected_doc and p['status_pelayanan'] == "Sedang Dilayani"), None)
        except: pass

        if current_p:
            with st.container(border=True):
                st.info(f"🟢 PASIEN AKTIF: **{current_p['nama_pasien']}**")
                st.write(f"No: {current_p['queue_number']}")
                catatan = st.text_area("Hasil Diagnosa / Resep:")
                if st.button("✅ Simpan & Selesaikan", type="primary", use_container_width=True):
                    requests.put(f"{API_URL}/ops/medical-notes/{current_p['queue_number']}", json={"catatan": catatan}, headers=headers)
                    requests.post(f"{API_URL}/ops/scan-barcode", json={"barcode_data": current_p['queue_number'], "location": "finish"}, headers=headers)
                    st.success("Tersimpan!"); time_lib.sleep(1); st.rerun()
        else:
            st.warning(f"Tidak ada pasien di ruangan {selected_doc}.")
            st.caption("Scan 'Masuk Poli' pada tiket pasien untuk memulai sesi.")

    # =================================================================
    # 5. MENU TV
    # =================================================================
    elif menu == MENU_TV:
        # Layout Header Khusus TV (Lebih Bersih)
        st.markdown("<h1 style='text-align: center; color:#007bff; margin-bottom: -20px;'>📺 MONITOR ANTREAN UTAMA</h1>", unsafe_allow_html=True)
        st.write("")
        
        # --- 1. FILTER POLI ---
        # Ambil daftar poli dari API untuk isi Dropdown
        try:
            pol_res = requests.get(f"{API_URL}/public/polis", headers=headers)
            if pol_res.status_code == 200:
                # Tambahkan opsi 'SEMUA POLI' di paling atas
                poli_list = ["SEMUA POLI"] + [p['poli'] for p in pol_res.json()]
            else:
                poli_list = ["SEMUA POLI"]
        except: 
            poli_list = ["SEMUA POLI"]

        # Tampilkan Dropdown Filter
        c_filter, c_time = st.columns([1, 3])
        with c_filter:
            target_poli = st.selectbox("Tampilkan Antrean Untuk:", poli_list)
        with c_time:
            # Tampilkan Jam Digital Sederhana
            st.markdown(f"<h3 style='text-align: right; color: gray;'>🕒 {datetime.now().strftime('%H:%M:%S')}</h3>", unsafe_allow_html=True)

        st.markdown("---")

        # --- 2. LOGIKA DATA & FILTERING ---
        try:
            r = requests.get(f"{API_URL}/monitor/queue-board", headers=headers)
            
            if r.status_code == 200:
                raw_data = r.json()
                df = pd.DataFrame(raw_data)

                if not df.empty:
                    # Ambil kolom penting saja
                    df = df[['queue_number', 'poli', 'dokter', 'status_pelayanan']]

                    # *** INI LOGIKA FILTERNYA ***
                    if target_poli != "SEMUA POLI":
                        # Hanya ambil baris yang polinya sama dengan pilihan dropdown
                        df = df[df['poli'] == target_poli]
                    
                    # Cek lagi apakah setelah difilter datanya masih ada?
                    if not df.empty:
                        # Pisahkan Data: Yang Sedang Dilayani vs Menunggu
                        df_active = df[df['status_pelayanan'] == 'Sedang Dilayani']
                        df_wait = df[df['status_pelayanan'] == 'Menunggu']

                        # --- TAMPILAN LAYAR ---
                        col_active, col_wait = st.columns([2, 1])

                        # KOLOM KIRI: SEDANG DILAYANI (Besar)
                        with col_active:
                            st.success(f"🔊 SEDANG DIPANGGIL ({len(df_active)})")
                            if not df_active.empty:
                                for _, row in df_active.iterrows():
                                    # Card Design Custom dengan HTML CSS biar besar
                                    st.markdown(f"""
                                    <div style="background-color: #d4edda; padding: 20px; border-radius: 10px; border-left: 10px solid #28a745; margin-bottom: 10px;">
                                        <h1 style="color: #155724; margin:0; font-size: 50px;">{row['queue_number']}</h1>
                                        <h3 style="margin:0;">{row['poli']}</h3>
                                        <p style="margin:0; font-style: italic;">{row['dokter']}</p>
                                    </div>
                                    """, unsafe_allow_html=True)
                            else:
                                st.info("Belum ada panggilan.")

                        # KOLOM KANAN: MENUNGGU (Tabel)
                        with col_wait:
                            st.warning(f"🕒 MENUNGGU ({len(df_wait)})")
                            if not df_wait.empty:
                                # Tampilkan tabel simpel
                                st.dataframe(
                                    df_wait[['queue_number', 'poli']], 
                                    hide_index=True, 
                                    use_container_width=True
                                )
                            else:
                                st.write("Tidak ada antrean tunggu.")
                    
                    else:
                        st.info(f"Tidak ada antrean aktif untuk **{target_poli}** saat ini.")
                else:
                    st.info("Tidak ada antrean aktif di Rumah Sakit.")
            else:
                st.error("Gagal terhubung ke server antrean.")

        except Exception as e:
            st.error(f"Koneksi Error: {e}")

        # --- 3. AUTO REFRESH ---
        # Refresh halaman setiap 10 detik agar data update realtime
        time_lib.sleep(10)
        st.rerun()

    # =================================================================
    # 6. DASHBOARD ADMIN
    # =================================================================
    elif menu == MENU_ADMIN:
        st.header("🛠️ Dashboard Admin")
        t_doc, t_pol, t_imp = st.tabs(["Kelola Dokter", "Kelola Poli", "Import Data"])
        
        try: p_opts = [x['poli'] for x in requests.get(f"{API_URL}/public/polis", headers=headers).json()]
        except: p_opts = []

        with t_doc:
            st.subheader("Manajemen Dokter")
            
            # --- LOAD DATA DOKTER & POLI ---
            try:
                # Ambil data dokter
                raw_docs = requests.get(f"{API_URL}/admin/doctors", headers=headers).json()
                # Ambil data poli (untuk dropdown)
                raw_polis = requests.get(f"{API_URL}/public/polis", headers=headers).json()
                p_opts = [p['poli'] for p in raw_polis]
            except:
                raw_docs = []
                p_opts = []

            # Tampilkan Tabel
            if raw_docs:
                df_doc = pd.DataFrame(raw_docs)[['doctor_id', 'dokter', 'poli', 'doctor_code', 'max_patients', 'practice_start_time', 'practice_end_time']]
                st.dataframe(df_doc, use_container_width=True, hide_index=True)
            else:
                st.info("Belum ada data dokter.")

            # --- 1. TAMBAH DOKTER ---
            with st.expander("➕ Tambah Dokter Baru"):
                with st.form("add_doc_form"):
                    c1, c2 = st.columns(2)
                    dn = c1.text_input("Nama Dokter (Tanpa Gelar)", placeholder="Contoh: Budi Santoso")
                    dp = c2.selectbox("Poli", p_opts if p_opts else ["Default"])
                    
                    c3, c4, c5 = st.columns(3)
                    ts = c3.time_input("Jam Mulai", time(8, 0))
                    te = c4.time_input("Jam Selesai", time(16, 0))
                    dm = c5.number_input("Kuota Pasien", min_value=1, value=20)
                    
                    if st.form_submit_button("Simpan Dokter"):
                        # Validasi sederhana
                        if dn.strip():
                            payload = {
                                "dokter": dn.strip(), # Trim otomatis
                                "poli": dp,
                                "practice_start_time": ts.strftime("%H:%M"),
                                "practice_end_time": te.strftime("%H:%M"),
                                "max_patients": dm
                            }
                            try:
                                r = requests.post(f"{API_URL}/admin/doctors", json=payload, headers=headers)
                                if r.status_code == 200:
                                    st.success("Dokter berhasil ditambahkan!")
                                    time_lib.sleep(1); st.rerun()
                                else:
                                    st.error(f"Gagal: {r.text}")
                            except Exception as e:
                                st.error(f"Error: {e}")
                        else:
                            st.warning("Nama dokter wajib diisi.")

# --- 2. EDIT DOKTER ---
            with st.expander("✏️ Edit Dokter"):
                if raw_docs:
                    doc_options = {f"{d['doctor_id']} - {d['dokter']}": d for d in raw_docs}
                    selected_label = st.selectbox("Pilih Dokter untuk Diedit", list(doc_options.keys()))
                    sel_doc = doc_options[selected_label]
                    
                    with st.form(key="edit_doc_form"):
                        st.caption(f"Mengedit: **{sel_doc['dokter']}**")
                        st.info("Catatan: Kuota Dokter tidak dapat diubah di sini.") # Info user
                        
                        ec1, ec2 = st.columns(2)
                        raw_name = sel_doc['dokter'].replace("dr. ", "").replace("Dr. ", "")
                        ed_name = ec1.text_input("Ubah Nama", value=raw_name)
                        
                        curr_poli_idx = p_opts.index(sel_doc['poli']) if sel_doc['poli'] in p_opts else 0
                        ed_poli = ec2.selectbox("Ubah Poli", p_opts, index=curr_poli_idx)
                        
                        ec3, ec4 = st.columns(2) # [FIX] Hapus kolom kuota
                        try:
                            t_start_obj = datetime.strptime(str(sel_doc['practice_start_time']), "%H:%M:%S").time()
                            t_end_obj = datetime.strptime(str(sel_doc['practice_end_time']), "%H:%M:%S").time()
                        except:
                            t_start_obj = time(8,0); t_end_obj = time(16,0)

                        ed_start = ec3.time_input("Ubah Jam Mulai", value=t_start_obj)
                        ed_end = ec4.time_input("Ubah Jam Selesai", value=t_end_obj)
                        
                        # [HAPUS INPUT KUOTA DARI SINI]
                        
                        if st.form_submit_button("Update Perubahan"):
                            up_payload = {
                                "dokter": ed_name.strip(),
                                "poli": ed_poli,
                                "practice_start_time": ed_start.strftime("%H:%M"),
                                "practice_end_time": ed_end.strftime("%H:%M")
                                # Jangan kirim max_patients
                            }
                            
                            r = requests.put(f"{API_URL}/admin/doctors/{sel_doc['doctor_id']}", json=up_payload, headers=headers)
                            if r.status_code == 200:
                                st.success("Data dokter berhasil diperbarui!")
                                time_lib.sleep(1); st.rerun()
                            else:
                                st.error(f"Gagal Update: {r.json().get('detail', r.text)}")
                else:
                    st.info("Tidak ada dokter untuk diedit.")

            # --- 3. HAPUS DOKTER ---
            with st.expander("❌ Hapus Dokter"):
                if raw_docs:
                    del_opts = {f"{d['doctor_id']} - {d['dokter']}": d['doctor_id'] for d in raw_docs}
                    del_label = st.selectbox("Pilih Dokter untuk Dihapus", list(del_opts.keys()))
                    del_id = del_opts[del_label]
                    
                    if st.button("Hapus Permanen", type="primary"):
                        r = requests.delete(f"{API_URL}/admin/doctors/{del_id}", headers=headers)
                        if r.status_code == 200:
                            st.success("Dokter berhasil dihapus."); time_lib.sleep(1); st.rerun()
                        else:
                            st.error(f"Gagal menghapus: {r.text}")
                else:
                    st.info("Data kosong.")
        with t_pol:
            st.subheader("Daftar Poliklinik")
            try: 
                # Ambil data poli terbaru
                pol_data = requests.get(f"{API_URL}/public/polis", headers=headers).json()
                st.dataframe(pd.DataFrame(pol_data), use_container_width=True, hide_index=True)
                # List nama poli untuk dropdown
                p_names = [p['poli'] for p in pol_data]
            except: 
                pol_data = []
                p_names = []
            
            # --- 1. TAMBAH POLI ---
            with st.expander("➕ Tambah Poli"):
                pn = st.text_input("Nama Poli (Contoh: Poli Mata)")
                pp = st.text_input("Prefix (Contoh: MATA)")
                if st.button("Simpan Poli"):
                    # Trim Input
                    clean_pn = pn.strip()
                    clean_pp = pp.strip().upper() # Prefix biasanya huruf besar
                    
                    if clean_pn and clean_pp:
                        r = requests.post(f"{API_URL}/admin/polis", json={"poli": clean_pn, "prefix": clean_pp}, headers=headers)
                        if r.status_code == 200:
                            st.success("Berhasil disimpan!"); time_lib.sleep(1); st.rerun()
                        else:
                            st.error(f"Gagal: {r.text}")
                    else:
                        st.warning("Nama dan Prefix wajib diisi.")

            # --- 2. EDIT POLI (YANG HILANG TADI) ---
            with st.expander("✏️ Edit Poli"):
                if p_names:
                    pe = st.selectbox("Pilih Poli yang mau diedit", p_names, key="sel_edit_pol")
                    
                    # Cari data prefix lama untuk ditampilkan otomatis
                    old_prefix = next((item['prefix'] for item in pol_data if item["poli"] == pe), "")
                    
                    new_n = st.text_input("Nama Baru", value=pe, key="in_new_pol")
                    new_p = st.text_input("Prefix Baru", value=old_prefix, key="in_new_pref")
                    
                    if st.button("Update Poli", key="btn_up_pol"):
                        clean_new_n = new_n.strip()
                        clean_new_p = new_p.strip().upper()
                        
                        r = requests.put(f"{API_URL}/admin/polis/{pe}", json={"new_name": clean_new_n, "new_prefix": clean_new_p}, headers=headers)
                        if r.status_code == 200:
                            st.success("Berhasil diupdate!"); time_lib.sleep(1); st.rerun()
                        else:
                            st.error(f"Gagal: {r.text}")
                else:
                    st.info("Belum ada data poli.")
            
            # --- 3. HAPUS POLI (YANG HILANG TADI) ---
            with st.expander("❌ Hapus Poli"):
                if p_names:
                    pd_del = st.selectbox("Pilih Poli untuk dihapus", p_names, key="sel_del_pol")
                    st.warning(f"⚠️ Hati-hati! Menghapus **{pd_del}** akan menghapus semua dokter yang ada di poli tersebut.")
                    
                    if st.button("Hapus Poli Permanen", type="primary", key="btn_del_pol"):
                        r = requests.delete(f"{API_URL}/admin/polis/{pd_del}", headers=headers)
                        if r.status_code == 200:
                            st.success("Berhasil dihapus!"); time_lib.sleep(1); st.rerun()
                        else:
                            st.error(f"Gagal: {r.text}")
                else:
                    st.info("Belum ada data poli.")
        with t_imp:
            cnt = st.number_input("Jumlah Data", 10)
            if st.button("Import Data Dummy"):
                with st.spinner("Generating..."):
                    r = requests.get(f"{API_URL}/admin/import-random-data", params={"count": cnt}, headers=headers)
                    st.success(r.json()['message'])

    # =================================================================
    # 7. ANALISIS DATA (UPDATE BESAR-BESARAN SESUAI REQUEST)
    # =================================================================
    elif menu == MENU_ANALISIS:
        st.header("📈 Data Science & Business Insights")
        st.markdown("Dashboard ini mengubah data mentah menjadi wawasan strategis untuk manajemen Rumah Sakit.")
        
        # --- Filter Global ---
        with st.container(border=True):
            col_filter, col_btn = st.columns([3, 1])
            with col_filter:
                filter_mode = st.selectbox("📅 Pilih Periode Analisis:", ["Semua Waktu", "Hari Ini", "Minggu Ini", "Bulan Ini"])
            with col_btn:
                st.write(""); st.write("")
                refresh = st.button("🔄 Terapkan & Refresh", type="primary", use_container_width=True)

        # Setting Tanggal Filter
        today = datetime.today()
        start_date = None
        end_date = today
        if filter_mode == "Hari Ini": start_date = today
        elif filter_mode == "Minggu Ini": start_date = today - pd.Timedelta(days=today.weekday())
        elif filter_mode == "Bulan Ini": start_date = today.replace(day=1)
        else: start_date = None

        params = {}
        if start_date: params['start_date'] = str(start_date.date())
        if end_date: params['end_date'] = str(end_date.date())

        # Load Data
        data_loaded = False
        d = {}
        try:
            with st.spinner(f"Menganalisis big data dari database..."):
                r = requests.get(f"{API_URL}/analytics/comprehensive-report", params=params, headers=headers)
                if r.status_code == 200:
                    d = r.json()
                    if d.get("status") == "No Data": st.warning(f"Belum ada data transaksi untuk periode {filter_mode}."); st.stop()
                    else: data_loaded = True
                else: st.error("Gagal mengambil data dari server.")
        except Exception as e: st.error(f"Koneksi Error: {e}")

        if data_loaded:
            # --- KPI UTAMA (ATAS) ---
            k1, k2, k3, k4 = st.columns(4)
            with k1: st.metric("Total Pasien", d['total_patients'], help="Total volume pasien yang terdaftar.")
            with k2: 
                peak = str(max(d['peak_hours'], key=d['peak_hours'].get)) + ":00" if d['peak_hours'] else "-"
                st.metric("Jam Tersibuk", peak, help="Jam dimana kedatangan pasien paling tinggi.")
            with k3: st.metric("Ghosting Rate", f"{d['ghost_rate']}%", help="% Pasien daftar tapi tidak datang.")
            with k4: st.metric("Korelasi (Vol vs Speed)", d['correlation'], help="Positif: Makin ramai makin lambat. Negatif: Makin ramai makin ngebut.")

            st.markdown("---")

            # --- 1. VOLUME PASIEN (BAR CHART ORANYE) ---
            st.subheader("1. Analisis Volume Pasien (Patient Volume Analysis)")
            st.caption("Mengidentifikasi poli dengan beban kerja tertinggi.")
            
            df_vol = pd.DataFrame(list(d['poli_volume'].items()), columns=['Poli', 'Jumlah'])
            if not df_vol.empty:
                fig_vol = px.bar(
                    df_vol, x='Poli', y='Jumlah', 
                    color_discrete_sequence=['#FF8C00'], # ORANYE sesuai request
                    text='Jumlah',
                    title="Total Pasien per Poliklinik"
                )
                fig_vol.update_layout(xaxis_title="Nama Poli", yaxis_title="Jumlah Pasien")
                st.plotly_chart(fig_vol, use_container_width=True)
            else: st.info("Tidak ada data volume.")

            c_left, c_right = st.columns(2)

            # --- 2. EFISIENSI WAKTU (GROUPED BAR MERAH/HIJAU) ---
            with c_left:
                st.subheader("2. Efisiensi Waktu (Wait vs Service)")
                st.caption("Membandingkan waktu tunggu vs waktu layanan.")
                
                # Transform Data Nested ke Flat DataFrame untuk Plotly Grouped Bar
                eff_data = []
                for poli, metrics in d['poli_efficiency'].items():
                    eff_data.append({'Poli': poli, 'Waktu (Menit)': metrics['wait_minutes'], 'Jenis': 'Menunggu (Merah)'})
                    eff_data.append({'Poli': poli, 'Waktu (Menit)': metrics['service_minutes'], 'Jenis': 'Diperiksa (Hijau)'})
                
                df_eff = pd.DataFrame(eff_data)
                if not df_eff.empty:
                    # Warna Custom: Merah untuk Tunggu, Hijau untuk Periksa
                    color_map = {'Menunggu (Merah)': '#FF4B4B', 'Diperiksa (Hijau)': '#00CC96'}
                    fig_eff = px.bar(
                        df_eff, x='Poli', y='Waktu (Menit)', color='Jenis', barmode='group',
                        color_discrete_map=color_map,
                        title="Rata-rata Waktu (Menit)"
                    )
                    st.plotly_chart(fig_eff, use_container_width=True)
                else: st.info("Data waktu belum cukup.")

            # --- 3. TREND JAM SIBUK (AREA CHART) ---
            with c_right:
                st.subheader("3. Tren Jam Sibuk (Peak Hour Analysis)")
                st.caption("Pola kedatangan pasien berdasarkan jam.")
                
                df_peak = pd.DataFrame(list(d['peak_hours'].items()), columns=['Jam', 'Jumlah'])
                df_peak['Jam'] = df_peak['Jam'].astype(str) + ":00" # Format jam
                
                if not df_peak.empty:
                    fig_peak = px.area(
                        df_peak, x='Jam', y='Jumlah',
                        markers=True, title="Heatmap Kedatangan Harian"
                    )
                    st.plotly_chart(fig_peak, use_container_width=True)
                else: st.info("Data jam belum cukup.")

            st.markdown("---")
            c_prod, c_ghost = st.columns(2)

            # --- 4. PRODUKTIVITAS DOKTER (HORIZONTAL BAR) ---
            with c_prod:
                st.subheader("4. Produktivitas Dokter (Throughput)")
                st.caption("Kecepatan layanan (Pasien per Jam).")
                
                df_doc = pd.DataFrame(list(d['doctor_throughput'].items()), columns=['Dokter', 'Speed (Pasien/Jam)'])
                if not df_doc.empty:
                    fig_doc = px.bar(
                        df_doc, y='Dokter', x='Speed (Pasien/Jam)', orientation='h',
                        color='Speed (Pasien/Jam)', color_continuous_scale='Viridis',
                        title="Efektivitas Staff Medis"
                    )
                    st.plotly_chart(fig_doc, use_container_width=True)
                else: st.info("Belum ada data penyelesaian dokter.")

            # --- 5. GHOSTING RATE (GAUGE CHART) ---
            with c_ghost:
                st.subheader("5. Tingkat Ketidakhadiran (No-Show)")
                st.caption("Pasien yang daftar tapi tidak datang.")
                
                fig_gauge = go.Figure(go.Indicator(
                    mode = "gauge+number",
                    value = d['ghost_rate'],
                    title = {'text': "Ghosting Rate (%)"},
                    gauge = {
                        'axis': {'range': [None, 100]},
                        'bar': {'color': "darkred"},
                        'steps': [
                            {'range': [0, 20], 'color': "lightgreen"},
                            {'range': [20, 50], 'color': "yellow"},
                            {'range': [50, 100], 'color': "salmon"}],
                    }
                ))
                st.plotly_chart(fig_gauge, use_container_width=True)

            # --- 6. KORELASI (SCATTER PLOT SIMPLE) ---
            st.subheader("6. Analisis Korelasi (Kepadatan vs Kecepatan)")
            st.info(f"Nilai Korelasi Pearson: **{d['correlation']}**")

            # --- 7. TEXT MINING (WORD CLOUD) ---
            st.subheader("7. Penambangan Teks Diagnosa (Word Cloud)")
            st.caption("Kata kunci penyakit yang paling sering muncul di catatan medis.")
            
            text_data = d.get('text_mining', '')
            if len(text_data) > 5:
                try:
                    # Buat WordCloud
                    wc = WordCloud(width=1000, height=400, background_color='white', colormap='Reds').generate(text_data)
                    
                    # Tampilkan pakai Matplotlib
                    fig_wc, ax = plt.subplots(figsize=(12, 4))
                    ax.imshow(wc, interpolation='bilinear')
                    ax.axis("off")
                    st.pyplot(fig_wc)
                except Exception as e: st.error(f"Gagal generate WordCloud: {e}")
            else:
                st.info("Data teks diagnosa belum cukup untuk dianalisis.")