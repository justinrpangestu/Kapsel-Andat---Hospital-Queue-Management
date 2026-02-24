import pandas as pd
import os
import csv

# Updated File and Field naming
FILE_CLINIC = "tabel_poli_normal.csv"
FILE_DOCTOR = "tabel_dokter_normal.csv"
FILE_SERVICE = "tabel_pelayanan_normal.csv"

def get_merged_random_data(count: int):
    """Reads the CSV files and cleans the data for the English schema."""
    if not (os.path.exists(FILE_CLINIC) and os.path.exists(FILE_DOCTOR) and os.path.exists(FILE_SERVICE)):
        raise FileNotFoundError("One or more CSV files are missing from the directory.")
    
    df_clinic = pd.read_csv(FILE_CLINIC, on_bad_lines='skip')
    df_doctor = pd.read_csv(FILE_DOCTOR, on_bad_lines='skip')
    df_service = pd.read_csv(FILE_SERVICE, on_bad_lines='skip')

    for df in [df_clinic, df_doctor, df_service]:
        # Remove any leftover 'Unnamed' columns from previous saves
        df = df.loc[:, ~df.columns.str.contains('^Unnamed')]
        # Trim white spaces from all string columns
        for col in df.select_dtypes(include=['object']).columns:
            df[col] = df[col].str.strip()

    return df_doctor, df_service

def append_to_csv(filename: str, data: dict):
    """Appends data to CSV using the new English field mapping."""
    file_exists = os.path.isfile(filename)
    field_order = []
    
    if "doctor" in filename: 
        field_order = ["doctor", "doctor_id", "practice_start_time", "practice_end_time", "doctor_code", "max_patients", "clinic", "prefix"]
    elif "poli" in filename or "clinic" in filename: 
        field_order = ["clinic", "prefix"]
    elif "pelayanan" in filename or "service" in filename: 
        field_order = ["patient_name", "clinic", "doctor", "visit_date", "checkin_time", "clinic_entry_time", "completion_time", "service_status", "queue_number", "queue_sequence"]
    
    with open(filename, mode='a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=field_order)
        if not file_exists:
            writer.writeheader()
        # Filter the dictionary to only include keys that match the CSV header
        row = {k: v for k, v in data.items() if k in field_order}
        writer.writerow(row)