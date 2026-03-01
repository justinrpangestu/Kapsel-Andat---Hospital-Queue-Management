import streamlit as st
import requests
import pandas as pd
from datetime import datetime, date, time
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

# --- CONFIGURATION ---
API_URL = "http://127.0.0.1:8000"
st.set_page_config(page_title="Smart Hospital System", layout="wide", page_icon="🏥")

# --- CUSTOM CSS ---
st.markdown("""
<style>
    div.stButton > button:first-child { border-radius: 8px; font-weight: bold; }
    div[data-testid="stMetricValue"] { font-size: 28px; color: #007bff; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# =================================================================
# 0. SESSION SETUP
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
# A. LOGIN / REGISTER LOGIC
# =================================================================
if st.session_state['token'] is None:
    st.markdown("<h1 style='text-align: center; color: #2E86C1;'>🏥 Smart Hospital System</h1>", unsafe_allow_html=True)
    st.divider()
    c1, c2 = st.columns(2)
    
    with c1:
        st.subheader("🔐 Secure Login")
        u = st.text_input("Username", key="lu")
        p = st.text_input("Password", type="password", key="lp")
        if st.button("Sign In", type="primary", use_container_width=True):
            try:
                r = requests.post(f"{API_URL}/auth/login", data={"username": u, "password": p})
                if r.status_code == 200:
                    d = r.json()
                    st.session_state.update({
                        'token': d['access_token'], 'role': d['role'], 
                        'nama_user': d['nama'], 'status_member': d.get('status_member') 
                    })
                    st.rerun()
                else: st.error(r.json().get('detail', 'Login Failed'))
            except Exception as e: st.error(f"Connection Error: {e}")

    with c2:
        st.subheader("📝 Patient Registration")
        rn = st.text_input("Full Name", key="rn")
        ru = st.text_input("Username", key="ru")
        rp = st.text_input("Password", type="password", key="rp")
        if st.button("Create Account", use_container_width=True):
            if rn and ru and rp:
                try:
                    payload = {"username": ru.strip(), "password": rp.strip(), "nama_lengkap": rn.strip()}
                    r = requests.post(f"{API_URL}/auth/register", json=payload)
                    if r.status_code == 200:
                        d = r.json()
                        st.session_state.update({
                            'token': d['access_token'], 'role': d['role'], 
                            'nama_user': d['nama'], 'status_member': "New Patient"
                        })
                        st.success("Success! Redirecting...")
                        time_lib.sleep(1); st.rerun()
                    else: st.error(f"Failed: {r.json().get('detail', 'Error')}")
                except Exception as e: st.error(f"Connection Error: {str(e)}")

# =================================================================
# B. MAIN APPLICATION
# =================================================================
else:
    role = st.session_state['role']
    headers = {"Authorization": f"Bearer {st.session_state['token']}"}
    
    # --- SIDEBAR ---
    st.sidebar.image("https://cdn-icons-png.flaticon.com/512/3135/3135715.png", width=80)
    st.sidebar.write(f"Welcome, **{st.session_state['nama_user']}**")
    if st.session_state.get('status_member'):
        st.sidebar.info(f"Status: **{st.session_state['status_member']}**")
    st.sidebar.caption(f"Role: {role.upper()}")
    if st.sidebar.button("Log Out"):
        st.session_state.clear(); st.rerun()
    st.sidebar.markdown("---")

    # --- MENU DEFINITIONS ---
    MENU_BOOK = "📝 Registration"
    MENU_HISTORY = "📂 History & Tickets"
    MENU_SCAN = "📠 QR Scanner"
    MENU_CLINIC = "👨‍⚕️ Examination Room"
    MENU_TV = "📺 Queue Monitor"
    MENU_ADMIN = "📊 Admin Dashboard"
    MENU_INSIGHTS = "📈 Data Science & Insights"

    menu_opts = []
    if role == "admin": menu_opts = [MENU_BOOK, MENU_SCAN, MENU_CLINIC, MENU_TV, MENU_ADMIN, MENU_INSIGHTS]
    elif role in ["nurse", "reception"]: menu_opts = [MENU_BOOK, MENU_SCAN, MENU_CLINIC, MENU_TV]
    elif role == "patient": menu_opts = [MENU_BOOK, MENU_HISTORY, MENU_TV]
    else: menu_opts = [MENU_TV]

    menu = st.sidebar.radio("Navigation", menu_opts)

# =================================================================
    # 1. REGISTRATION MENU (INDENTATION & UI FIXED)
    # =================================================================
    if menu == MENU_BOOK:
        st.header("📋 Book Appointment")
        
        try: 
            res = requests.get(f"{API_URL}/public/polis", headers=headers)
            raw_polis = res.json() if res.status_code == 200 else []
            p_map = {p['clinic']: p for p in sorted(raw_polis, key=lambda x: x['clinic'])}
        except: p_map = {}

        c1, c2 = st.columns(2)
        if role in ['admin', 'nurse', 'reception']:
            patient_nm = c1.text_input("Patient Name (As per ID Card)", key="reg_nm")
            target_uname = c1.text_input("Patient Username (Optional)", key="reg_un")
        else:
            patient_nm = c1.text_input("Patient Name", value=st.session_state['nama_user'], disabled=True, key="reg_nm_lock")
            target_uname = None
        
        sel_clinic = c1.selectbox("Target Clinic", list(p_map.keys()) if p_map else [], index=None, placeholder="Choose Clinic...", key="reg_cl")
        sel_date = c2.date_input("Visit Date", min_value=date.today(), key="reg_dt")

        # --- B. DOCTOR SELECTION ---
        if sel_clinic:
            st.markdown("---")
            st.subheader(f"Available Doctors at {sel_clinic}")
            try:
                doc_res = requests.get(f"{API_URL}/public/available-doctors", params={"clinic_name": sel_clinic}, headers=headers)
                docs = doc_res.json() if doc_res.status_code == 200 else []
                
                if not docs:
                    st.warning("No doctors available.")
                else:
                    cols = st.columns(3)
                    for i, d in enumerate(docs):
                        with cols[i % 3]:
                            is_selected = st.session_state.get('selected_doc') and st.session_state['selected_doc']['doctor_id'] == d['doctor_id']
                            with st.container(border=True):
                                if is_selected: st.markdown("✅ **SELECTED**")
                                else: st.caption("Available")
                                st.markdown(f"#### {d['doctor']}")
                                st.info(f"🕒 {str(d['practice_start_time'])[:5]} - {str(d['practice_end_time'])[:5]}")
                                if st.button("Select", key=f"btn_doc_{d['doctor_id']}", use_container_width=True):
                                    st.session_state['selected_doc'] = d
                                    st.rerun() 
            except Exception as e:
                st.error(f"Connection error: {e}")

        # --- C. SUBMISSION & LARGE TICKET (DI LUAR EXCEPT) ---
        if st.session_state.get('selected_doc'):
            sel = st.session_state['selected_doc']
            with st.container(border=True):
                st.markdown("### 🔍 Confirm Appointment")
                st.warning(f"Register for **{sel['doctor']}** at **{sel_clinic}**?")
                
                if st.button("✅ Yes, Confirm Booking", type="primary", use_container_width=True, key="btn_sub_final"):
                    if not patient_nm.strip(): st.error("Patient name is required.")
                    else:
                        payload = {"clinic": sel_clinic, "doctor_id": sel['doctor_id'], "visit_date": str(sel_date)}
                        if target_uname: payload["username_pasien"] = target_uname.strip()
                        
                        try:
                            r = requests.post(f"{API_URL}/public/submit", json=payload, headers=headers)
                            if r.status_code == 200:
                                d = r.json()
                                st.balloons()
                                
                                # TAMPILAN TIKET SESUAI PERMINTAAN (NOMOR BESAR)
                                with st.container(border=True):
                                    st.markdown(f"""
                                        <div style='text-align: center; background-color: #f0f8ff; padding: 30px; border-radius: 15px; border: 2px solid #2E86C1;'>
                                            <p style='margin:0; font-size: 20px; color: #555;'>Your Queue Number</p>
                                            <h1 style='font-size: 110px; color: #2E86C1; margin: 10px 0;'>{d['queue_number']}</h1>
                                        </div>
                                    """, unsafe_allow_html=True)
                                    
                                    st.write("") 
                                    col_a, col_b = st.columns(2)
                                    col_a.write(f"🏢 **Clinic:**\n{d['clinic']}")
                                    col_b.write(f"👨‍⚕️ **Doctor:**\n{d['doctor']}")
                                    st.divider()
                                    col_c, col_d, col_e = st.columns(3)
                                    col_c.write(f"👤 **Patient:**\n{d['patient_name']}")
                                    col_d.write(f"📅 **Date:**\n{d['visit_date']}")
                                    col_e.write(f"🕒 **Hours:**\n{d['doctor_schedule']}")
                                    
                                    st.divider()
                                    qr_col1, qr_col2, qr_col3 = st.columns([1, 1, 1])
                                    with qr_col2:
                                        qr_buf = io.BytesIO()
                                        generate_qr({"id": d['id'], "antrean": d['queue_number']}).save(qr_buf, format="PNG")
                                        st.image(qr_buf, caption="Scan at Reception", use_container_width=True)
                                
                                st.session_state['selected_doc'] = None
                            else: st.error(f"⛔ Error: {r.text}")
                        except Exception as e: st.error(f"System Error: {e}")
        
    # 2. HISTORY MENU
    elif menu == MENU_HISTORY:
        st.header("📂 My Tickets & Visit History")
        try:
            r = requests.get(f"{API_URL}/public/my-history", headers=headers)
            data = r.json()
            if not data: st.info("No visit history found.")
            else:
                for t in data:
                    with st.container(border=True):
                        c1, c2, c3 = st.columns([1, 3, 1])
                        with c1:
                            buf = io.BytesIO(); generate_qr({"id": t['id'], "antrean": t['queue_number']}).save(buf, format="PNG")
                            st.image(buf)
                        with c2:
                            st.subheader(t['queue_number'])
                            st.write(f"**{t['clinic']}** | {t['doctor']}")
                            st.caption(f"{t['visit_date']}")
                            if t.get('catatan_medis'): st.info(f"Medical Notes: {t['catatan_medis']}")
                        with c3:
                            st.write(f"Status: **{t['service_status']}**")
        except: st.error("Failed to load records.")

    # 3. QR SCANNER MENU
    elif menu == MENU_SCAN:
        st.header("📠 QR Scanner Operations")
        loc_map = {"Entrance (Check-in)": "arrival", "Clinic Entry (Calling)": "clinic", "Finished (Discharged)": "finish"}
        sel_loc = loc_map[st.radio("Scan Location:", list(loc_map.keys()), horizontal=True)]
        
        t1, t2 = st.tabs(["Camera Scan", "Manual Input"])
        
        with t1:
            img = st.camera_input("Aim camera at QR Code")
            if img:
                code = decode_qr_from_image(img)
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
                    except Exception as e: st.error(f"Connection error: {e}")
                else:
                    st.warning("⚠️ QR Code not readable. Ensure proper lighting and focus.")

        with t2:
            mc = st.text_input("Queue Code (e.g., DENT-001-001)", key="man_code")
            if st.button("Process Entry"):
                try:
                    r = requests.post(f"{API_URL}/ops/scan-barcode", json={"barcode_data": mc, "location": sel_loc}, headers=headers)
                    d = r.json()
                    if r.status_code == 200:
                        st.success(f"✅ {d['message']}"); time_lib.sleep(1); st.rerun()
                    else: st.error(f"❌ {r.text}")
                except Exception as e: st.error(f"Connection error: {e}")

    # 4. EXAMINATION ROOM MENU
    elif menu == MENU_CLINIC:
        st.header("👨‍⚕️ Examination Room (Medical Input)")
        try:
            res_docs = requests.get(f"{API_URL}/admin/doctors", headers=headers) 
            doc_list = [d['doctor'] for d in res_docs.json()] if res_docs.status_code == 200 else []
            if not doc_list: st.warning("Failed to load doctor list."); st.stop()
            selected_doc = st.selectbox("Select On-duty Doctor:", doc_list)
        except: st.error("Connection Error"); st.stop()

        st.markdown("---")
        current_p = None
        try:
            q_data = requests.get(f"{API_URL}/monitor/queue-board", headers=headers).json()
            # Status mapping in English
            current_p = next((p for p in q_data if p['doctor'] == selected_doc and p['status_pelayanan'] == "Serving"), None)
        except: pass

        if current_p:
            with st.container(border=True):
                st.info(f"🟢 ACTIVE PATIENT: **{current_p['nama_pasien']}**")
                st.write(f"Ticket No: {current_p['queue_number']}")
                notes = st.text_area("Diagnosis / Prescription Result:")
                if st.button("✅ Save & Discharge Patient", type="primary", use_container_width=True):
                    requests.put(f"{API_URL}/ops/medical-notes/{current_p['queue_number']}", json={"catatan": notes}, headers=headers)
                    requests.post(f"{API_URL}/ops/scan-barcode", json={"barcode_data": current_p['queue_number'], "location": "finish"}, headers=headers)
                    st.success("Record Saved!"); time_lib.sleep(1); st.rerun()
        else:
            st.warning(f"No active patients in {selected_doc}'s room.")
            st.caption("Scan 'Clinic Entry' on the patient's ticket to start the session.")

    # 5. TV MONITOR MENU
    elif menu == MENU_TV:
        st.markdown("<h1 style='text-align: center; color:#007bff; margin-bottom: -20px;'>📺 MAIN QUEUE MONITOR</h1>", unsafe_allow_html=True)
        st.write("")
        
        try:
            pol_res = requests.get(f"{API_URL}/public/polis", headers=headers)
            poli_list = ["ALL CLINICS"] + [p['clinic'] for p in pol_res.json()] if pol_res.status_code == 200 else ["ALL CLINICS"]
        except: poli_list = ["ALL CLINICS"]

        c_filter, c_time = st.columns([1, 3])
        with c_filter:
            target_poli = st.selectbox("Display Queue For:", poli_list)
        with c_time:
            st.markdown(f"<h3 style='text-align: right; color: gray;'>🕒 {datetime.now().strftime('%H:%M:%S')}</h3>", unsafe_allow_html=True)

        st.markdown("---")

        try:
            r = requests.get(f"{API_URL}/monitor/queue-board", headers=headers)
            if r.status_code == 200:
                raw_data = r.json()
                df = pd.DataFrame(raw_data)

                if not df.empty:
                    df = df[['queue_number', 'clinic', 'doctor', 'service_status']]
                    if target_poli != "ALL CLINICS":
                        df = df[df['clinic'] == target_poli]
                    
                    if not df.empty:
                        df_active = df[df['service_status'] == 'Serving']
                        df_wait = df[df['service_status'] == 'Waiting']

                        col_active, col_wait = st.columns([2, 1])
                        with col_active:
                            st.success(f"🔊 NOW SERVING ({len(df_active)})")
                            if not df_active.empty:
                                for _, row in df_active.iterrows():
                                    st.markdown(f"""
                                    <div style="background-color: #d4edda; padding: 20px; border-radius: 10px; border-left: 10px solid #28a745; margin-bottom: 10px;">
                                        <h1 style="color: #155724; margin:0; font-size: 50px;">{row['queue_number']}</h1>
                                        <h3 style="margin:0;">{row['clinic']}</h3>
                                        <p style="margin:0; font-style: italic;">{row['doctor']}</p>
                                    </div>
                                    """, unsafe_allow_html=True)
                            else: st.info("No patients currently being served.")

                        with col_wait:
                            st.warning(f"🕒 WAITING LIST ({len(df_wait)})")
                            if not df_wait.empty:
                                st.dataframe(df_wait[['queue_number', 'clinic']], hide_index=True, use_container_width=True)
                            else: st.write("Waiting list empty.")
                    else: st.info(f"No active queue for **{target_poli}**.")
                else: st.info("Hospital queue is currently empty.")
            else: st.error("Failed to connect to the queue server.")
        except Exception as e: st.error(f"Connection Error: {e}")

        time_lib.sleep(10); st.rerun()

 # =================================================================
    # 6. ADMIN DASHBOARD (FIXED & FULL FEATURES)
    # =================================================================
    elif menu == MENU_ADMIN:
        st.header("🛠️ Administrative Controls")
        t_doc, t_pol, t_imp = st.tabs(["👨‍⚕️ Doctor Management", "🏥 Clinic Management", "📊 Data Importer"])
        
        # --- A. DATA PREPARATION ---
        try:
            r_pol = requests.get(f"{API_URL}/public/polis", headers=headers)
            # Pastikan raw_polis adalah list. Jika server error, jadikan list kosong.
            raw_polis = r_pol.json() if (r_pol.status_code == 200 and isinstance(r_pol.json(), list)) else []
            p_opts = [x['clinic'] for x in raw_polis]
        except: 
            raw_polis, p_opts = [], []

        # --- TAB 1: DOCTOR MANAGEMENT (FILTER + EDIT + DELETE) ---
        with t_doc:
            st.subheader("Manage Doctors")
            
            # 1. Add New Doctor
            with st.expander("➕ Add New Doctor"):
                with st.form("add_doc_form"):
                    c1, c2 = st.columns(2)
                    dn = c1.text_input("Doctor Name")
                    dp = c2.selectbox("Assign to Clinic", p_opts if p_opts else ["Default"])
                    ts = st.time_input("Start Time", time(8, 0))
                    te = st.time_input("End Time", time(16, 0))
                    dm = st.number_input("Daily Patient Quota", min_value=1, value=20)
                    if st.form_submit_button("Save Doctor"):
                        # Gelar akan dinormalisasi secara otomatis oleh Pydantic di Backend
                        payload = {"doctor": dn, "clinic": dp, "practice_start_time": ts.strftime("%H:%M"), "practice_end_time": te.strftime("%H:%M"), "max_patients": dm}
                        r = requests.post(f"{API_URL}/admin/doctors", json=payload, headers=headers)
                        if r.status_code == 200: st.success("Added!"); st.rerun()
                        else: st.error(r.text)

            st.write("---")
            st.write("#### 🛠️ Edit or Delete Existing Doctors")
            
            # 2. Filter Clinic: Task 2
            f_col1, f_col2 = st.columns([2, 1])
            sel_filter = f_col1.selectbox("🔍 Filter list by Clinic:", ["All Clinics"] + p_opts, key="admin_filter_doc")
            
            try:
                raw_docs = requests.get(f"{API_URL}/admin/doctors", headers=headers).json()
                docs_to_show = [d for d in raw_docs if d['clinic'] == sel_filter] if sel_filter != "All Clinics" else raw_docs
                
                for d in docs_to_show:
                    with st.expander(f"{d['doctor']} — {d['clinic']}"):
                        # Opsi Edit
                        e_name = st.text_input("Full Name", value=d['doctor'], key=f"nm_{d['doctor_id']}")
                        e_clinic = st.selectbox("Clinic", p_opts, index=p_opts.index(d['clinic']) if d['clinic'] in p_opts else 0, key=f"cl_{d['doctor_id']}")
                        e_quota = st.number_input("Quota", value=int(d['max_patients']), key=f"q_{d['doctor_id']}")
                        
                        btn_sv, btn_dl = st.columns(2)
                        if btn_sv.button("💾 Save Changes", key=f"sv_{d['doctor_id']}", use_container_width=True):
                            upd_payload = {"doctor": e_name, "clinic": e_clinic, "max_patients": e_quota, 
                                           "practice_start_time": str(d['practice_start_time'])[:5], "practice_end_time": str(d['practice_end_time'])[:5]}
                            res = requests.put(f"{API_URL}/admin/doctors/{d['doctor_id']}", json=upd_payload, headers=headers)
                            if res.status_code == 200: st.success("Updated!"); st.rerun()
                        
                        if btn_dl.button("🗑️ Delete Doctor", key=f"dl_{d['doctor_id']}", use_container_width=True, type="secondary"):
                            res = requests.delete(f"{API_URL}/admin/doctors/{d['doctor_id']}", headers=headers)
                            if res.status_code == 200: st.warning("Deleted"); st.rerun()
            except: pass

        # --- TAB 2: CLINIC MANAGEMENT (ADD CLINIC + EDIT + DELETE) ---
        with t_pol:
            st.subheader("Clinic Management")
            
            # 1. Fitur Tambah Clinic: Task 2
            with st.container(border=True):
                st.markdown("#### ➕ Add New Clinic")
                c_n = st.text_input("Clinic Name (e.g., Cardiology Clinic)", key="new_cl_name")
                c_p = st.text_input("Prefix Code (e.g., CARD)", key="new_cl_pref")
                if st.button("✨ Create Clinic", use_container_width=True):
                    if c_n and c_p:
                        res = requests.post(f"{API_URL}/admin/polis", json={"clinic": c_n, "prefix": c_p}, headers=headers)
                        if res.status_code == 200: st.success("Clinic Created!"); st.rerun()
                        else: st.error(res.text)

            st.markdown("---")
            st.write("#### 🛠️ Edit or Delete Existing Clinics")
            
            # 2. Edit/Delete Clinics: Fix TypeError
            if isinstance(raw_polis, list) and len(raw_polis) > 0:
                for p in raw_polis:
                    with st.expander(f"Clinic: {p['clinic']} ({p['prefix']})"):
                        edit_name = st.text_input("Change Name", value=p['clinic'], key=f"ed_cl_nm_{p['clinic']}")
                        edit_pref = st.text_input("Change Prefix", value=p['prefix'], key=f"ed_cl_pr_{p['clinic']}")
                        
                        col_c1, col_c2 = st.columns(2)
                        if col_c1.button("💾 Save", key=f"btn_sv_cl_{p['clinic']}", use_container_width=True):
                            res = requests.put(f"{API_URL}/admin/polis/{p['clinic']}", json={"clinic": edit_name, "prefix": edit_pref}, headers=headers)
                            if res.status_code == 200: st.success("Updated!"); st.rerun()
                            else: st.error(res.text)
                            
                        if col_c2.button("🗑️ Delete", key=f"btn_dl_cl_{p['clinic']}", use_container_width=True, type="secondary"):
                            res = requests.delete(f"{API_URL}/admin/polis/{p['clinic']}", headers=headers)
                            if res.status_code == 200: st.success("Deleted!"); st.rerun()
                            else: st.error(res.json().get('detail', 'Error'))
            else:
                st.info("No clinic data found. Add a clinic above first.")
        # --- TAB 3: DATA IMPORTER (VARIED DATA) ---
        with t_imp:
            st.subheader("Generate Data for Analytics")
            cnt = st.number_input("Records to generate", 10, 100, 30)
            if st.button("🚀 Start Import (Varied Data)"):
                with st.spinner("Simulating varied traffic..."):
                    r = requests.get(f"{API_URL}/admin/import-random-data", params={"count": cnt}, headers=headers)
                    if r.status_code == 200: st.success(r.json().get('message')); st.balloons()
    # 7. DATA SCIENCE MENU
    elif menu == MENU_INSIGHTS:
        st.header("📈 Data Science & Strategic Insights")
        st.markdown("Turning raw transaction data into operational insights for hospital management.")
        
        with st.container(border=True):
            col_filter, col_btn = st.columns([3, 1])
            with col_filter:
                filter_mode = st.selectbox("📅 Analysis Period:", ["All Time", "Today", "This Week", "This Month"])
            with col_btn:
                st.write(""); st.write("")
                st.button("🔄 Refresh Data", type="primary", use_container_width=True)

        today = datetime.today()
        start_date = None
        if filter_mode == "Today": start_date = today
        elif filter_mode == "This Week": start_date = today - pd.Timedelta(days=today.weekday())
        elif filter_mode == "This Month": start_date = today.replace(day=1)

        params = {}
        if start_date: params['start_date'] = str(start_date.date())
        params['end_date'] = str(today.date())

        try:
            with st.spinner("Analyzing big data from engine..."):
                r = requests.get(f"{API_URL}/analytics/comprehensive-report", params=params, headers=headers)
                if r.status_code == 200:
                    d = r.json()
                    
                    # --- KPI METRICS ---
                    k1, k2, k3, k4 = st.columns(4)
                    k1.metric("Total Patient Volume", d['total_patients'])
                    
                    # FIX: Robust peak hour display
                    peak_dict = d.get('peak_hours', {})
                    peak_hour = max(peak_dict, key=peak_dict.get) if peak_dict else "N/A"
                    k2.metric("Peak Arrival Hour", f"{peak_hour}:00" if peak_hour != "N/A" else "-")
                    
                    k3.metric("Ghosting Rate", f"{d['ghost_rate']}%")
                    k4.metric("Load Correlation", d['correlation'])

                    st.markdown("---")

                    # --- 1. VOLUME ANALYSIS ---
                    st.subheader("1. Patient Distribution by Clinic")
                    df_vol = pd.DataFrame(list(d['clinic_volume'].items()), columns=['Clinic', 'Total'])
                    if not df_vol.empty:
                        fig_vol = px.bar(df_vol, x='Clinic', y='Total', color_discrete_sequence=['#FF8C00'], title="Volume per Clinic")
                        st.plotly_chart(fig_vol, use_container_width=True)

                    c_left, c_right = st.columns(2)

                    # --- 2. TIME EFFICIENCY ---
                    with c_left:
                        st.subheader("2. Time Efficiency (Wait vs Serving)")
                        eff_data = []
                        for p, m in d['clinic_efficiency'].items():
                            eff_data.append({'Clinic': p, 'Minutes': m['wait_minutes'], 'Type': 'Waiting (Red)'})
                            eff_data.append({'Clinic': p, 'Minutes': m['service_minutes'], 'Type': 'Serving (Green)'})
                        df_eff = pd.DataFrame(eff_data)
                        if not df_eff.empty:
                            fig_eff = px.bar(df_eff, x='Clinic', y='Minutes', color='Type', barmode='group',
                                            color_discrete_map={'Waiting (Red)': '#FF4B4B', 'Serving (Green)': '#00CC96'},
                                            title="Avg Duration (Min)")
                            st.plotly_chart(fig_eff, use_container_width=True)

                    # --- 3. PEAK HOUR TREND ---
                    with c_right:
                        st.subheader("3. Daily Peak Hour Trends")
                        df_peak = pd.DataFrame(list(d['peak_hours'].items()), columns=['Hour', 'Total'])
                        df_peak['Hour'] = df_peak['Hour'].astype(str) + ":00"
                        if not df_peak.empty:
                            st.plotly_chart(px.area(df_peak, x='Hour', y='Total', markers=True, title="Hourly Heatmap"), use_container_width=True)

                    st.markdown("---")
                    c_prod, c_ghost = st.columns(2)

                    # --- 4. DOCTOR PRODUCTIVITY (THROUGHPUT) ---
                    st.subheader("4. Doctor Throughput (Total Served)")
                    doc_data = d.get('doctor_throughput', {})
                    if doc_data:
                        df_doc_t = pd.DataFrame(list(doc_data.items()), columns=['Doctor', 'Patients'])
                        fig_prod = px.bar(df_doc_t, y='Doctor', x='Patients', orientation='h', 
                                        color='Patients', color_continuous_scale='Viridis')
                        st.plotly_chart(fig_prod, use_container_width=True)
                    else:
                        st.info("No doctors have finished serving patients yet.")
                    # --- 5. GHOSTING RATE GAUGE ---
                    with c_ghost:
                        st.subheader("5. No-Show Rate Analysis")
                        fig_gauge = go.Figure(go.Indicator(
                            mode = "gauge+number", value = d['ghost_rate'], title = {'text': "Ghosting Rate %"},
                            gauge = {'axis': {'range': [0, 100]}, 'bar': {'color': "darkred"},
                                     'steps': [{'range': [0, 20], 'color': "lightgreen"}, {'range': [20, 50], 'color': "yellow"}, {'range': [50, 100], 'color': "salmon"}]}
                        ))
                        st.plotly_chart(fig_gauge, use_container_width=True)

                    # --- 7. WORD CLOUD ---
                    st.subheader("7. Medical Diagnosis Text Mining (Word Cloud)")
                    text_data = d.get('text_mining', '')
                    if len(text_data) > 5:
                        try:
                            wc = WordCloud(width=1000, height=400, background_color='white', colormap='Reds').generate(text_data)
                            fig_wc, ax = plt.subplots(figsize=(12, 4))
                            ax.imshow(wc, interpolation='bilinear'); ax.axis("off")
                            st.pyplot(fig_wc)
                        except Exception as e: st.error(f"WordCloud Error: {e}")
                    else: st.info("Insufficient diagnosis text data for mining.")

                else: st.error("Failed to fetch analytics from engine.")
        except Exception as e: st.error(f"Analytics Pipeline Error: {e}")