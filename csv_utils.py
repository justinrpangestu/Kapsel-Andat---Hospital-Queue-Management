import pandas as pd
import os
import csv

FILE_POLI = "tabel_poli_normal.csv"
FILE_DOKTER = "tabel_dokter_normal.csv"
FILE_PELAYANAN = "tabel_pelayanan_normal.csv"

def get_merged_random_data(count: int):
    if not (os.path.exists(FILE_POLI) and os.path.exists(FILE_DOKTER) and os.path.exists(FILE_PELAYANAN)):
        raise FileNotFoundError("File CSV tidak lengkap.")
    
    # Baca dengan skip error
    df_poli = pd.read_csv(FILE_POLI, on_bad_lines='skip')
    df_dokter = pd.read_csv(FILE_DOKTER, on_bad_lines='skip')
    df_layanan = pd.read_csv(FILE_PELAYANAN, on_bad_lines='skip')

    # Cleaning Unnamed columns
    df_poli = df_poli.loc[:, ~df_poli.columns.str.contains('^Unnamed')]
    df_dokter = df_dokter.loc[:, ~df_dokter.columns.str.contains('^Unnamed')]
    df_layanan = df_layanan.loc[:, ~df_layanan.columns.str.contains('^Unnamed')]

    for df in [df_poli, df_dokter, df_layanan]:
        for col in df.select_dtypes(include=['object']).columns:
            df[col] = df[col].str.strip()

    # Return raw dataframes for main.py to handle
    return df_dokter, df_layanan

def append_to_csv(filename: str, data: dict):
    file_exists = os.path.isfile(filename)
    field_order = []
    if "dokter" in filename: 
        field_order = ["dokter", "doctor_id", "practice_start_time", "practice_end_time", "doctor_code", "max_patients", "poli", "prefix"]
    elif "poli" in filename: 
        field_order = ["poli", "prefix"]
    elif "pelayanan" in filename: 
        field_order = ["nama_pasien", "poli", "dokter", "visit_date", "checkin_time", "clinic_entry_time", "completion_time", "status_pelayanan", "queue_number", "queue_sequence"]
    
    with open(filename, mode='a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=field_order)
        if not file_exists: writer.writeheader()
        row = {k: v for k, v in data.items() if k in field_order}
        writer.writerow(row)