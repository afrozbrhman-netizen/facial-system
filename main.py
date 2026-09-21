"""
================================================================================
Face Recognition Based Attendance Monitoring System - Modernized Studio Edition
With SQLite Database Architecture & Multi-Frame Verification Filter
================================================================================
Fixes & Enhancements:
- Multi-frame Face Verification Streak (requires 6 consecutive high-confidence frames)
  to ensure one person scanning never falsely logs any other enrolled student.
- Global 4-second Post-Scan Lockout to prevent multiple rapid captures.
- Calibrated LBPH distance threshold (default strict 48, adjustable 35-60)
  preventing distant/unknown faces from matching wrong profiles.
- Clean and reliable Student Clearing: Wipes SQLite students, deletes dataset photos,
  clears Trainer.yml, updates StudentDetails.xlsx to clean headers, and prevents
  auto-migration resurrection.
- Explicit "Clear Form Inputs" vs "Clear All Enrolled Students" buttons in Tab 2.
- Real-time confidence percentage indicator on the scanner screen.
================================================================================
"""

import os
import sys
import time
import datetime
import shutil
import smtplib
import zipfile
import platform
import threading
import sqlite3
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from subprocess import check_output, CalledProcessError

import cv2
import numpy as np
import pandas as pd
from PIL import Image, ImageTk, ImageDraw
import openpyxl
from openpyxl import Workbook, load_workbook
from openpyxl.utils import get_column_letter

import tkinter as tk
from tkinter import ttk, messagebox, filedialog

# Ensure current working directory is the script folder
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)

# ----------------------------------------------------------------------
# Paths & Directories
# ----------------------------------------------------------------------
DB_FILE = os.path.join(BASE_DIR, "attendance.db")
STUDENT_DETAILS_DIR = os.path.join(BASE_DIR, "StudentDetails")
STUDENT_DETAILS_FILE = os.path.join(STUDENT_DETAILS_DIR, "StudentDetails.xlsx")

ATTENDANCE_DIR = os.path.join(BASE_DIR, "Attendance")
ATTENDANCE_FILE = os.path.join(ATTENDANCE_DIR, "Attendance.xlsx")

TRAINING_IMAGE_DIR = os.path.join(BASE_DIR, "TrainingImage")
TRAINING_LABEL_DIR = os.path.join(BASE_DIR, "TrainingImageLabel")
TRAINER_FILE = os.path.join(TRAINING_LABEL_DIR, "Trainer.yml")
PASSWORD_FILE = os.path.join(TRAINING_LABEL_DIR, "psd.txt")
HAARCASCADE_FILE = os.path.join(BASE_DIR, "haarcascade_frontalface_default.xml")

for folder in [STUDENT_DETAILS_DIR, ATTENDANCE_DIR, TRAINING_IMAGE_DIR, TRAINING_LABEL_DIR]:
    os.makedirs(folder, exist_ok=True)

# ----------------------------------------------------------------------
# Modern UI Theme Constants
# ----------------------------------------------------------------------
THEME = {
    "bg_app": "#0b0f19",          # Deep midnight canvas
    "card_bg": "#111827",         # Surface card background
    "card_border": "#1f2937",     # Subtle card border
    "card_sub": "#1a2234",        # Inner container background
    "input_bg": "#151e2e",        # Form entry background
    "input_border": "#374151",    # Form entry border
    "text_main": "#f8fafc",       # Primary bright text
    "text_muted": "#94a3b8",      # Secondary subdued text
    "text_dim": "#64748b",        # Tertiary muted text
    "accent": "#6366f1",          # Primary electric indigo
    "accent_hover": "#4f46e5",    # Darker indigo hover
    "accent_light": "#818cf8",    # Light indigo
    "cyan": "#06b6d4",            # Modern teal / cyan
    "cyan_hover": "#0891b2",
    "success": "#10b981",         # Emerald success
    "success_hover": "#059669",
    "warning": "#f59e0b",         # Amber alert
    "danger": "#ef4444",          # Crimson danger
    "danger_hover": "#dc2626",
    "danger_sub": "#3b1717",
    "font_main": "Segoe UI",
    "font_mono": "Consolas"
}

# ----------------------------------------------------------------------
# SQLite Database Manager
# ----------------------------------------------------------------------
class DatabaseManager:
    """Robust SQLite Database layer with auto-migration and thread safety."""
    def __init__(self, db_path=DB_FILE):
        self.db_path = db_path
        self.lock = threading.Lock()
        self.init_db()
        self.auto_migrate_from_excel()

    def get_connection(self):
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self):
        with self.lock:
            with self.get_connection() as conn:
                cur = conn.cursor()
                cur.execute('''
                    CREATE TABLE IF NOT EXISTS settings (
                        key TEXT PRIMARY KEY,
                        value TEXT
                    )
                ''')
                cur.execute('''
                    CREATE TABLE IF NOT EXISTS subjects (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT UNIQUE NOT NULL,
                        created_at TEXT
                    )
                ''')
                cur.execute('''
                    CREATE TABLE IF NOT EXISTS students (
                        serial_no INTEGER PRIMARY KEY AUTOINCREMENT,
                        student_id INTEGER UNIQUE NOT NULL,
                        name TEXT NOT NULL,
                        image_count INTEGER DEFAULT 0,
                        registered_at TEXT
                    )
                ''')
                cur.execute('''
                    CREATE TABLE IF NOT EXISTS attendance (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        student_id INTEGER NOT NULL,
                        name TEXT NOT NULL,
                        date TEXT NOT NULL,
                        time TEXT NOT NULL,
                        status TEXT DEFAULT 'Present',
                        log_type TEXT DEFAULT 'Check-In',
                        category TEXT DEFAULT 'Classroom Lecture',
                        subject TEXT DEFAULT 'General',
                        shift_status TEXT DEFAULT 'On-Time',
                        created_at TEXT
                    )
                ''')
                # Auto-upgrade columns for existing SQLite database
                cur.execute("PRAGMA table_info(attendance)")
                existing_cols = [c[1] for c in cur.fetchall()]
                if 'log_type' not in existing_cols:
                    cur.execute("ALTER TABLE attendance ADD COLUMN log_type TEXT DEFAULT 'Check-In'")
                if 'category' not in existing_cols:
                    cur.execute("ALTER TABLE attendance ADD COLUMN category TEXT DEFAULT 'Classroom Lecture'")
                if 'subject' not in existing_cols:
                    cur.execute("ALTER TABLE attendance ADD COLUMN subject TEXT DEFAULT 'General'")
                if 'shift_status' not in existing_cols:
                    cur.execute("ALTER TABLE attendance ADD COLUMN shift_status TEXT DEFAULT 'On-Time'")

                # Seed default subjects if table is empty
                cur.execute("SELECT COUNT(*) FROM subjects")
                if cur.fetchone()[0] == 0:
                    default_subs = [
                        "Mathematics", "Computer Science", "Physics",
                        "Operating Systems", "Data Structures", "Office / General"
                    ]
                    now_ts = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    for sub in default_subs:
                        cur.execute("INSERT OR IGNORE INTO subjects (name, created_at) VALUES (?, ?)", (sub, now_ts))

                # Seed default shift & session configurations in settings table
                defaults = {
                    "shift_in_time": "09:00 AM",
                    "shift_out_time": "05:00 PM",
                    "grace_period_mins": "15",
                    "active_category": "Classroom Lecture",
                    "active_subject": "Mathematics"
                }
                for k, v in defaults.items():
                    cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))

                conn.commit()

    def auto_migrate_from_excel(self):
        """Silently imports existing Excel data once. If user clears records, never re-migrates."""
        try:
            with self.lock:
                with self.get_connection() as conn:
                    cur = conn.cursor()

                    cur.execute("SELECT value FROM settings WHERE key = 'excel_migrated'")
                    row = cur.fetchone()
                    if row and row['value'] == '1':
                        return

                    # 1. Migrate Students
                    cur.execute('SELECT COUNT(*) FROM students')
                    db_stu_count = cur.fetchone()[0]

                    if db_stu_count == 0 and os.path.isfile(STUDENT_DETAILS_FILE):
                        try:
                            df_stu = pd.read_excel(STUDENT_DETAILS_FILE).dropna(subset=['ID', 'NAME'])
                            for _, r in df_stu.iterrows():
                                try:
                                    sid = int(r['ID'])
                                    name = str(r['NAME']).strip()
                                    cur.execute('''
                                        INSERT INTO students (student_id, name, registered_at)
                                        VALUES (?, ?, ?)
                                        ON CONFLICT(student_id) DO UPDATE SET name=excluded.name
                                    ''', (sid, name, datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
                                except Exception:
                                    pass
                        except Exception as e:
                            print("Auto-migrate students failed:", e)

                    # 2. Migrate Attendance
                    cur.execute('SELECT COUNT(*) FROM attendance')
                    db_att_count = cur.fetchone()[0]

                    if db_att_count == 0 and os.path.isfile(ATTENDANCE_FILE):
                        try:
                            df_att = pd.read_excel(ATTENDANCE_FILE).dropna(subset=['ID', 'Name'])
                            for _, r in df_att.iterrows():
                                try:
                                    sid = int(r['ID'])
                                    name = str(r['Name']).strip()
                                    d = str(r['Date']).strip()
                                    t = str(r['Time']).strip()
                                    cur.execute('''
                                        INSERT INTO attendance (student_id, name, date, time, status, log_type, category, subject, shift_status, created_at)
                                        VALUES (?, ?, ?, ?, 'Present', 'Check-In', 'Classroom Lecture', 'General', 'On-Time', ?)
                                    ''', (sid, name, d, t, datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
                                except Exception:
                                    pass
                        except Exception as e:
                            print("Auto-migrate attendance failed:", e)

                    cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('excel_migrated', '1')")
                    conn.commit()
        except Exception as e:
            print("Database migration check failed:", e)

    def add_or_update_student(self, sid, name, img_count=100):
        with self.lock:
            with self.get_connection() as conn:
                cur = conn.cursor()
                cur.execute('''
                    INSERT INTO students (student_id, name, image_count, registered_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(student_id) DO UPDATE SET
                        name=excluded.name,
                        image_count=excluded.image_count
                ''', (int(sid), str(name).strip(), int(img_count), datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
                conn.commit()

    def get_all_students(self):
        with self.lock:
            with self.get_connection() as conn:
                cur = conn.cursor()
                cur.execute('SELECT serial_no, student_id, name, image_count, registered_at FROM students ORDER BY student_id ASC')
                return [dict(r) for r in cur.fetchall()]

    def delete_student(self, sid):
        with self.lock:
            with self.get_connection() as conn:
                cur = conn.cursor()
                cur.execute('DELETE FROM students WHERE student_id = ?', (int(sid),))
                conn.commit()

    def clear_enrolled_students(self):
        with self.lock:
            with self.get_connection() as conn:
                cur = conn.cursor()
                cur.execute('DELETE FROM students')
                cur.execute("DELETE FROM sqlite_sequence WHERE name='students'")
                cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('excel_migrated', '1')")
                conn.commit()

    def get_subjects(self):
        with self.lock:
            with self.get_connection() as conn:
                cur = conn.cursor()
                cur.execute("SELECT name FROM subjects ORDER BY name ASC")
                subs = [r['name'] for r in cur.fetchall()]
                return subs if subs else ["General", "Mathematics", "Office / General"]

    def add_subject(self, name):
        name = str(name).strip()
        if not name:
            return False, "Subject name cannot be blank."
        with self.lock:
            with self.get_connection() as conn:
                cur = conn.cursor()
                try:
                    cur.execute("INSERT INTO subjects (name, created_at) VALUES (?, ?)",
                                (name, datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
                    conn.commit()
                    return True, "Subject added successfully."
                except sqlite3.IntegrityError:
                    return False, "Subject already exists."
                except Exception as e:
                    return False, str(e)

    def update_subject(self, old_name, new_name):
        new_name = str(new_name).strip()
        if not new_name:
            return False, "New subject name cannot be blank."
        with self.lock:
            with self.get_connection() as conn:
                cur = conn.cursor()
                try:
                    cur.execute("UPDATE subjects SET name = ? WHERE name = ?", (new_name, old_name))
                    cur.execute("UPDATE attendance SET subject = ? WHERE subject = ?", (new_name, old_name))
                    conn.commit()
                    return True, "Subject updated successfully."
                except sqlite3.IntegrityError:
                    return False, "A subject with this name already exists."
                except Exception as e:
                    return False, str(e)

    def delete_subject(self, name):
        with self.lock:
            with self.get_connection() as conn:
                cur = conn.cursor()
                cur.execute("DELETE FROM subjects WHERE name = ?", (name,))
                conn.commit()
                return True

    def get_setting(self, key, default=None):
        with self.lock:
            with self.get_connection() as conn:
                cur = conn.cursor()
                cur.execute("SELECT value FROM settings WHERE key = ?", (key,))
                row = cur.fetchone()
                return row['value'] if row else default

    def set_setting(self, key, value):
        with self.lock:
            with self.get_connection() as conn:
                cur = conn.cursor()
                cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
                conn.commit()

    def log_attendance(self, sid, name, date_str, time_str, log_type="Check-In", category="Classroom Lecture", subject="General", status="Present", shift_status="On-Time"):
        with self.lock:
            with self.get_connection() as conn:
                cur = conn.cursor()
                cur.execute('''
                    INSERT INTO attendance (student_id, name, date, time, status, log_type, category, subject, shift_status, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (int(sid), str(name).strip(), date_str, time_str, status, log_type, category, subject, shift_status, datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
                conn.commit()
                return cur.lastrowid

    def update_attendance_record(self, record_id, date_str, time_str, log_type, category, subject, status="Present", shift_status="On-Time"):
        with self.lock:
            with self.get_connection() as conn:
                cur = conn.cursor()
                cur.execute('''
                    UPDATE attendance SET
                        date = ?,
                        time = ?,
                        log_type = ?,
                        category = ?,
                        subject = ?,
                        status = ?,
                        shift_status = ?
                    WHERE id = ?
                ''', (date_str, time_str, log_type, category, subject, status, shift_status, int(record_id)))
                conn.commit()
                return True

    def delete_attendance_record(self, record_id):
        with self.lock:
            with self.get_connection() as conn:
                cur = conn.cursor()
                cur.execute('DELETE FROM attendance WHERE id = ?', (int(record_id),))
                conn.commit()
                return True

    def is_already_marked_today(self, sid, today_str, log_type=None, subject=None):
        with self.lock:
            with self.get_connection() as conn:
                cur = conn.cursor()
                query = 'SELECT COUNT(*) FROM attendance WHERE student_id = ? AND date = ?'
                params = [int(sid), today_str]
                if log_type:
                    query += ' AND log_type = ?'
                    params.append(log_type)
                if subject and subject != "General":
                    query += ' AND subject = ?'
                    params.append(subject)
                cur.execute(query, tuple(params))
                return cur.fetchone()[0] > 0

    def get_attendance_records(self, date_filter=None, category_filter=None, subject_filter=None, type_filter=None):
        with self.lock:
            with self.get_connection() as conn:
                cur = conn.cursor()
                query = 'SELECT id, student_id, name, date, time, status, log_type, category, subject, shift_status FROM attendance WHERE 1=1'
                params = []
                if date_filter:
                    query += ' AND date = ?'
                    params.append(date_filter)
                if category_filter and category_filter != "All Categories":
                    query += ' AND category = ?'
                    params.append(category_filter)
                if subject_filter and subject_filter != "All Subjects":
                    query += ' AND subject = ?'
                    params.append(subject_filter)
                if type_filter and type_filter != "All Types":
                    query += ' AND log_type = ?'
                    params.append(type_filter)
                query += ' ORDER BY id DESC'
                cur.execute(query, tuple(params))
                return [dict(r) for r in cur.fetchall()]

    def clear_attendance(self):
        with self.lock:
            with self.get_connection() as conn:
                cur = conn.cursor()
                cur.execute('DELETE FROM attendance')
                cur.execute("DELETE FROM sqlite_sequence WHERE name='attendance'")
                conn.commit()

    def clear_all(self):
        with self.lock:
            with self.get_connection() as conn:
                cur = conn.cursor()
                cur.execute('DELETE FROM students')
                cur.execute('DELETE FROM attendance')
                cur.execute("DELETE FROM sqlite_sequence")
                cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('excel_migrated', '1')")
                conn.commit()

    def sync_to_excel(self):
        """Mirror SQLite tables to StudentDetails.xlsx and Attendance.xlsx, including empty states."""
        try:
            students = self.get_all_students()
            if students:
                df_stu = pd.DataFrame([{
                    'SERIAL NO.': s['serial_no'],
                    'ID': s['student_id'],
                    'NAME': s['name']
                } for s in students])
            else:
                df_stu = pd.DataFrame(columns=['SERIAL NO.', 'ID', 'NAME'])
            df_stu.to_excel(STUDENT_DETAILS_FILE, index=False)
            autofit_excel(STUDENT_DETAILS_FILE)

            att = self.get_attendance_records()
            if att:
                df_att = pd.DataFrame([{
                    'S.No': a['id'],
                    'ID': a['student_id'],
                    'Name': a['name'],
                    'Type': a.get('log_type', 'Check-In'),
                    'Category': a.get('category', 'Classroom Lecture'),
                    'Subject': a.get('subject', 'General'),
                    'Date': a['date'],
                    'Time': a['time'],
                    'Status': a.get('status', 'Present'),
                    'Shift Status': a.get('shift_status', 'On-Time')
                } for a in reversed(att)])
            else:
                df_att = pd.DataFrame(columns=['S.No', 'ID', 'Name', 'Type', 'Category', 'Subject', 'Date', 'Time', 'Status', 'Shift Status'])
            df_att.to_excel(ATTENDANCE_FILE, index=False)
            autofit_excel(ATTENDANCE_FILE)
            return True
        except PermissionError:
            print("Excel file open in another program; skipping sync.")
            return False
        except Exception as e:
            print("Sync to Excel error:", e)
            return False

# ----------------------------------------------------------------------
# Helper Utilities
# ----------------------------------------------------------------------
def is_capslock_on():
    system = platform.system()
    try:
        if system == "Windows":
            import ctypes
            hll = ctypes.WinDLL("User32.dll")
            return bool(hll.GetKeyState(0x14) & 0x0001)
        elif system == "Darwin":
            try:
                from Quartz import CGEventSourceKeyState, kCGEventSourceStateHIDSystemState
                return bool(CGEventSourceKeyState(kCGEventSourceStateHIDSystemState, 57))
            except Exception:
                return False
        elif system == "Linux":
            try:
                out = check_output(["xset", "q"]).decode(errors='ignore')
                return "Caps Lock:   on" in out or "Caps Lock: on" in out
            except Exception:
                return False
    except Exception:
        pass
    return False

def check_capslock_continuous(entry_widget, warning_label):
    try:
        if is_capslock_on():
            warning_label.config(text="⚠ Caps Lock is ON")
        else:
            warning_label.config(text="")
    except Exception:
        warning_label.config(text="")
    try:
        entry_widget.after(250, lambda: check_capslock_continuous(entry_widget, warning_label))
    except Exception:
        pass

def autofit_excel(file_path):
    try:
        wb = load_workbook(file_path)
        for ws in wb.worksheets:
            for col in ws.columns:
                max_len = 0
                try:
                    col_letter = get_column_letter(col[0].column)
                except Exception:
                    continue
                for cell in col:
                    if cell.value is not None:
                        max_len = max(max_len, len(str(cell.value)))
                ws.column_dimensions[col_letter].width = max(max_len + 4, 10)
        wb.save(file_path)
    except Exception:
        pass

def evaluate_shift_status(log_time_str, log_type, shift_in_str, shift_out_str, grace_mins=15):
    """
    Evaluates whether a login is On-Time or Late, or a logout is On-Time or Early Departure.
    Gracefully handles 12-hour (e.g. 09:00:00 AM) and 24-hour timestamps.
    """
    try:
        def parse_time(t_str):
            if not t_str:
                return None
            t_str = str(t_str).strip().upper()
            for fmt in ('%I:%M:%S %p', '%I:%M %p', '%H:%M:%S', '%H:%M'):
                try:
                    return datetime.datetime.strptime(t_str, fmt).time()
                except ValueError:
                    continue
            return None

        lt = parse_time(log_time_str)
        if not lt:
            return "On-Time"

        today = datetime.date.today()
        dt_log = datetime.datetime.combine(today, lt)

        if "In" in log_type:  # Check-In / Login
            sin = parse_time(shift_in_str)
            if not sin:
                return "On-Time"
            dt_in = datetime.datetime.combine(today, sin)
            threshold = dt_in + datetime.timedelta(minutes=int(grace_mins))
            if dt_log > threshold:
                return "Late Login"
            return "On-Time"

        elif "Out" in log_type:  # Check-Out / Logout
            sout = parse_time(shift_out_str)
            if not sout:
                return "On-Time"
            dt_out = datetime.datetime.combine(today, sout)
            threshold = dt_out - datetime.timedelta(minutes=int(grace_mins))
            if dt_log < threshold:
                return "Early Departure"
            return "On-Time"

        return "On-Time"
    except Exception:
        return "On-Time"

def check_haarcascade():
    if os.path.isfile(HAARCASCADE_FILE):
        return True
    messagebox.showerror(
        "Missing File",
        f"Face cascade classifier is missing:\n{HAARCASCADE_FILE}\n\nPlease place haarcascade_frontalface_default.xml in the project directory."
    )
    return False

def get_admin_password():
    if os.path.isfile(PASSWORD_FILE):
        try:
            with open(PASSWORD_FILE, "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception:
            return None
    return None

def set_admin_password(new_pass):
    try:
        with open(PASSWORD_FILE, "w", encoding="utf-8") as f:
            f.write(new_pass.strip())
        return True
    except Exception:
        return False

# ----------------------------------------------------------------------
# Modern Password Modal Dialog
# ----------------------------------------------------------------------
def prompt_password_dialog(parent, title="Admin Authentication", prompt="Enter Admin Password", require_confirm=False):
    result = {"password": None}
    dialog = tk.Toplevel(parent)
    dialog.transient(parent)
    dialog.grab_set()
    dialog.title(title)
    dialog.geometry("440x260" if require_confirm else "440x200")
    dialog.resizable(False, False)
    dialog.configure(bg=THEME["card_bg"])

    dialog.update_idletasks()
    try:
        x = parent.winfo_x() + (parent.winfo_width() // 2) - 220
        y = parent.winfo_y() + (parent.winfo_height() // 2) - 120
        dialog.geometry(f"+{max(0, x)}+{max(0, y)}")
    except Exception:
        pass

    lbl_title = tk.Label(dialog, text=prompt, bg=THEME["card_bg"], fg=THEME["text_main"], font=(THEME["font_main"], 11, "bold"))
    lbl_title.pack(anchor="w", padx=24, pady=(20, 8))

    frm_pwd = tk.Frame(dialog, bg=THEME["card_bg"])
    frm_pwd.pack(fill="x", padx=24, pady=2)

    pwd_var = tk.StringVar()
    pwd_entry = tk.Entry(frm_pwd, textvariable=pwd_var, show="•", bg=THEME["input_bg"], fg=THEME["text_main"],
                         insertbackground=THEME["cyan"], relief="flat", highlightthickness=1,
                         highlightbackground=THEME["input_border"], highlightcolor=THEME["accent"], font=(THEME["font_main"], 11))
    pwd_entry.pack(side="left", fill="x", expand=True, ipady=5)
    pwd_entry.focus_set()

    def toggle_show():
        if pwd_entry.cget("show") == "":
            pwd_entry.config(show="•")
            btn_show.config(text="Show")
        else:
            pwd_entry.config(show="")
            btn_show.config(text="Hide")

    btn_show = tk.Button(frm_pwd, text="Show", command=toggle_show, bg=THEME["card_sub"], fg=THEME["text_muted"],
                         activebackground=THEME["card_border"], activeforeground=THEME["text_main"],
                         relief="flat", width=6, cursor="hand2", font=(THEME["font_main"], 9))
    btn_show.pack(side="left", padx=(8, 0), ipady=3)

    warn_lbl1 = tk.Label(dialog, text="", bg=THEME["card_bg"], fg=THEME["danger"], font=(THEME["font_main"], 9))
    warn_lbl1.pack(anchor="w", padx=24, pady=(2, 4))
    check_capslock_continuous(pwd_entry, warn_lbl1)

    confirm_var = tk.StringVar()
    if require_confirm:
        lbl_conf = tk.Label(dialog, text="Confirm Password", bg=THEME["card_bg"], fg=THEME["text_main"], font=(THEME["font_main"], 11, "bold"))
        lbl_conf.pack(anchor="w", padx=24, pady=(6, 4))

        frm_conf = tk.Frame(dialog, bg=THEME["card_bg"])
        frm_conf.pack(fill="x", padx=24, pady=2)

        conf_entry = tk.Entry(frm_conf, textvariable=confirm_var, show="•", bg=THEME["input_bg"], fg=THEME["text_main"],
                              insertbackground=THEME["cyan"], relief="flat", highlightthickness=1,
                              highlightbackground=THEME["input_border"], highlightcolor=THEME["accent"], font=(THEME["font_main"], 11))
        conf_entry.pack(side="left", fill="x", expand=True, ipady=5)

        warn_lbl2 = tk.Label(dialog, text="", bg=THEME["card_bg"], fg=THEME["danger"], font=(THEME["font_main"], 9))
        warn_lbl2.pack(anchor="w", padx=24, pady=(2, 4))
        check_capslock_continuous(conf_entry, warn_lbl2)

    frm_actions = tk.Frame(dialog, bg=THEME["card_bg"])
    frm_actions.pack(fill="x", padx=24, pady=(12, 16), side="bottom")

    def on_confirm():
        val = pwd_var.get()
        if require_confirm:
            cval = confirm_var.get()
            if not val:
                messagebox.showwarning("Validation", "Password cannot be blank.", parent=dialog)
                return
            if val != cval:
                messagebox.showerror("Mismatch", "Passwords do not match. Please verify.", parent=dialog)
                return
        result["password"] = val
        dialog.destroy()

    def on_cancel():
        dialog.destroy()

    btn_ok = tk.Button(frm_actions, text="Confirm", command=on_confirm, bg=THEME["accent"], fg="white",
                       activebackground=THEME["accent_hover"], activeforeground="white", relief="flat",
                       cursor="hand2", font=(THEME["font_main"], 10, "bold"), width=12)
    btn_ok.pack(side="right", padx=(8, 0), ipady=5)

    btn_cancel = tk.Button(frm_actions, text="Cancel", command=on_cancel, bg=THEME["card_sub"], fg=THEME["text_muted"],
                           activebackground=THEME["card_border"], activeforeground=THEME["text_main"], relief="flat",
                           cursor="hand2", font=(THEME["font_main"], 10), width=10)
    btn_cancel.pack(side="right", ipady=5)

    pwd_entry.bind("<Return>", lambda e: on_confirm())
    dialog.wait_window()
    return result["password"]

# ----------------------------------------------------------------------
# Modern Custom UI Components
# ----------------------------------------------------------------------
class ModernButton(tk.Button):
    def __init__(self, master, text="", command=None, bg=None, fg="white", hover_bg=None,
                 font=None, width=None, height=None, padx=12, pady=6, **kwargs):
        bg = bg or THEME["accent"]
        self.default_bg = bg
        self.hover_bg = hover_bg or THEME["accent_hover"]
        self.default_fg = fg
        super().__init__(
            master, text=text, command=command, bg=bg, fg=fg,
            activebackground=self.hover_bg, activeforeground=fg,
            relief="flat", bd=0, cursor="hand2",
            font=font or (THEME["font_main"], 10, "bold"),
            width=width, height=height, padx=padx, pady=pady, **kwargs
        )
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)

    def _on_enter(self, event):
        if self["state"] != tk.DISABLED:
            self.configure(bg=self.hover_bg)

    def _on_leave(self, event):
        if self["state"] != tk.DISABLED:
            self.configure(bg=self.default_bg)

    def set_color(self, bg, hover_bg=None):
        self.default_bg = bg
        self.hover_bg = hover_bg or bg
        self.configure(bg=bg, activebackground=self.hover_bg)


class MetricCard(tk.Frame):
    def __init__(self, master, title="Metric", value="0", icon="📊", accent_color=THEME["cyan"], **kwargs):
        super().__init__(master, bg=THEME["card_bg"], highlightthickness=1,
                         highlightbackground=THEME["card_border"], **kwargs)
        
        inner = tk.Frame(self, bg=THEME["card_bg"])
        inner.pack(fill="both", expand=True, padx=16, pady=12)

        top_row = tk.Frame(inner, bg=THEME["card_bg"])
        top_row.pack(fill="x")

        self.lbl_title = tk.Label(top_row, text=title.upper(), font=(THEME["font_main"], 9, "bold"),
                                  fg=THEME["text_dim"], bg=THEME["card_bg"])
        self.lbl_title.pack(side="left")

        self.lbl_icon = tk.Label(top_row, text=icon, font=(THEME["font_main"], 12),
                                 fg=accent_color, bg=THEME["card_bg"])
        self.lbl_icon.pack(side="right")

        self.lbl_value = tk.Label(inner, text=value, font=(THEME["font_main"], 20, "bold"),
                                  fg=THEME["text_main"], bg=THEME["card_bg"])
        self.lbl_value.pack(anchor="w", pady=(4, 0))

    def update_value(self, new_val):
        self.lbl_value.config(text=str(new_val))


# ----------------------------------------------------------------------
# Main Application Class
# ----------------------------------------------------------------------
class AttendanceStudioApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Attendance Studio • Face Recognition & Database Suite")
        self.root.geometry("1340x820")
        self.root.minsize(1120, 720)
        self.root.configure(bg=THEME["bg_app"])

        # Database Engine
        self.db = DatabaseManager()

        # State Variables
        self.camera_active = False
        self.camera_device = None
        self.camera_index = 0
        self.face_cascade = None
        self.recognizer = None
        self.current_frame = None

        # Verification Streak & Lockout (Prevents taking all attendance at once)
        self.current_candidate_id = None
        self.candidate_streak = 0
        self.required_consecutive_frames = 6   # ~0.3 - 0.5s of steady identification
        self.global_cooldown_until = 0         # 4-second lockout after marking attendance
        self.duplicate_cooldown = {}           # {student_id: timestamp}

        self.duplicate_check_enabled = tk.BooleanVar(value=True)
        self.confidence_threshold = tk.IntVar(value=48)  # LBPH distance (strict calibrated 48)
        self.auto_train_enabled = tk.BooleanVar(value=True)

        # Context, Mode & Subject Variables
        self.scan_mode_var = tk.StringVar(value="Check-In (Login)")
        self.scan_category_var = tk.StringVar(value=self.db.get_setting("active_category", "Classroom Lecture"))
        self.scan_subject_var = tk.StringVar(value=self.db.get_setting("active_subject", "Mathematics"))

        # Admin Shift Configuration Variables
        self.shift_in_var = tk.StringVar(value=self.db.get_setting("shift_in_time", "09:00 AM"))
        self.shift_out_var = tk.StringVar(value=self.db.get_setting("shift_out_time", "05:00 PM"))
        self.grace_period_var = tk.StringVar(value=self.db.get_setting("grace_period_mins", "15"))

        # Enrolled Students Cache: {student_id: name}
        self.students_cache = {}

        # Initialize models and cache
        self.load_models()

        # Build GUI Layout
        self.setup_styles()
        self.build_header()
        self.build_notebook()

        # Update real-time widgets
        self.refresh_dashboard_counters()
        self.reload_attendance_table()
        self.reload_students_directory()
        self.start_clock_ticker()

        self.root.protocol("WM_DELETE_WINDOW", self.on_close_application)

    # ------------------------------------------------------------------
    # Data Layer & Model Management
    # ------------------------------------------------------------------
    def load_models(self):
        """Loads Haar Cascade, LBPH Face Recognizer, and caches student profiles."""
        if os.path.isfile(HAARCASCADE_FILE):
            try:
                self.face_cascade = cv2.CascadeClassifier(HAARCASCADE_FILE)
            except Exception as e:
                print("Error loading face cascade:", e)

        if hasattr(cv2, 'face') and hasattr(cv2.face, 'LBPHFaceRecognizer_create'):
            try:
                self.recognizer = cv2.face.LBPHFaceRecognizer_create()
                if os.path.isfile(TRAINER_FILE):
                    self.recognizer.read(TRAINER_FILE)
            except Exception as e:
                print("Error loading LBPH recognizer:", e)

        self.load_students_cache()

    def load_students_cache(self):
        """Refreshes in-memory dictionary of {student_id: name} directly from SQLite."""
        students = self.db.get_all_students()
        self.students_cache = {s['student_id']: s['name'] for s in students}

    # ------------------------------------------------------------------
    # Styles & UI Architecture
    # ------------------------------------------------------------------
    def setup_styles(self):
        self.style = ttk.Style(self.root)
        try:
            self.style.theme_use('clam')
        except Exception:
            pass

        self.style.configure('Modern.TNotebook', background=THEME["bg_app"], borderwidth=0)
        self.style.configure('Modern.TNotebook.Tab',
                             background=THEME["card_bg"],
                             foreground=THEME["text_muted"],
                             padding=[18, 10],
                             font=(THEME["font_main"], 10, "bold"),
                             borderwidth=0)
        self.style.map('Modern.TNotebook.Tab',
                       background=[('selected', THEME["accent"]), ('active', THEME["card_border"])],
                       foreground=[('selected', 'white'), ('active', THEME["text_main"])])

        self.style.configure('Modern.Treeview',
                             background=THEME["card_bg"],
                             fieldbackground=THEME["card_bg"],
                             foreground=THEME["text_main"],
                             rowheight=32,
                             font=(THEME["font_main"], 10),
                             borderwidth=0)
        self.style.configure('Modern.Treeview.Heading',
                             background=THEME["card_sub"],
                             foreground=THEME["text_main"],
                             font=(THEME["font_main"], 10, "bold"),
                             relief='flat',
                             padding=[8, 8])
        self.style.map('Modern.Treeview',
                       background=[('selected', THEME["accent_hover"])],
                       foreground=[('selected', 'white')])

        self.style.configure('Modern.Vertical.TScrollbar',
                             troughcolor=THEME["card_bg"],
                             background=THEME["card_border"],
                             borderwidth=0, arrowsize=12)

        self.style.configure('Modern.Horizontal.TProgressbar',
                             troughcolor=THEME["input_bg"],
                             background=THEME["accent"],
                             thickness=10, borderwidth=0)

    def build_header(self):
        header_frame = tk.Frame(self.root, bg=THEME["card_bg"], highlightthickness=1,
                                highlightbackground=THEME["card_border"], height=64)
        header_frame.pack(fill="x", side="top", padx=16, pady=(12, 8))
        header_frame.pack_propagate(False)

        brand_box = tk.Frame(header_frame, bg=THEME["card_bg"])
        brand_box.pack(side="left", padx=16, pady=8)

        lbl_logo = tk.Label(brand_box, text="✦", font=(THEME["font_main"], 18, "bold"),
                            fg=THEME["cyan"], bg=THEME["card_bg"])
        lbl_logo.pack(side="left", padx=(0, 8))

        text_box = tk.Frame(brand_box, bg=THEME["card_bg"])
        text_box.pack(side="left")

        lbl_app_name = tk.Label(text_box, text="ATTENDANCE STUDIO", font=(THEME["font_main"], 13, "bold"),
                                fg=THEME["text_main"], bg=THEME["card_bg"])
        lbl_app_name.pack(anchor="w")

        lbl_app_sub = tk.Label(text_box, text="Face Recognition Intelligence Suite • SQLite Database Connected",
                               font=(THEME["font_main"], 8), fg=THEME["text_dim"], bg=THEME["card_bg"])
        lbl_app_sub.pack(anchor="w")

        info_box = tk.Frame(header_frame, bg=THEME["card_bg"])
        info_box.pack(side="right", padx=16, pady=8)

        self.pill_db = tk.Label(info_box, text="🗄 SQLITE CONNECTED", font=(THEME["font_mono"], 9, "bold"),
                                fg=THEME["cyan"], bg=THEME["input_bg"], padx=10, pady=4,
                                relief="flat", highlightthickness=1, highlightbackground=THEME["card_border"])
        self.pill_db.pack(side="left", padx=(0, 10))

        self.pill_cam_status = tk.Label(info_box, text="⚪ CAMERA STANDBY", font=(THEME["font_mono"], 9, "bold"),
                                        fg=THEME["text_dim"], bg=THEME["input_bg"], padx=10, pady=4,
                                        relief="flat", highlightthickness=1, highlightbackground=THEME["card_border"])
        self.pill_cam_status.pack(side="left", padx=(0, 14))

        self.lbl_live_date = tk.Label(info_box, text="", font=(THEME["font_main"], 10),
                                      fg=THEME["text_muted"], bg=THEME["card_bg"])
        self.lbl_live_date.pack(side="left", padx=(0, 14))

        self.lbl_live_clock = tk.Label(info_box, text="", font=(THEME["font_mono"], 12, "bold"),
                                       fg=THEME["cyan"], bg=THEME["card_bg"])
        self.lbl_live_clock.pack(side="left")

    def build_notebook(self):
        self.notebook = ttk.Notebook(self.root, style='Modern.TNotebook')
        self.notebook.pack(fill="both", expand=True, padx=16, pady=(4, 12))

        self.tab_monitor = tk.Frame(self.notebook, bg=THEME["bg_app"])
        self.tab_enroll = tk.Frame(self.notebook, bg=THEME["bg_app"])
        self.tab_reports = tk.Frame(self.notebook, bg=THEME["bg_app"])
        self.tab_settings = tk.Frame(self.notebook, bg=THEME["bg_app"])

        self.notebook.add(self.tab_monitor, text="  📷  Live Attendance  ")
        self.notebook.add(self.tab_enroll, text="  👤  Enrollment & Training  ")
        self.notebook.add(self.tab_reports, text="  📊  Attendance Analytics  ")
        self.notebook.add(self.tab_settings, text="  ⚙  System Settings  ")

        self.build_tab_monitor()
        self.build_tab_enroll()
        self.build_tab_reports()
        self.build_tab_settings()

    # ------------------------------------------------------------------
    # TAB 1: Live Attendance & Monitor
    # ------------------------------------------------------------------
    def build_tab_monitor(self):
        container = tk.Frame(self.tab_monitor, bg=THEME["bg_app"])
        container.pack(fill="both", expand=True, pady=8)

        left_col = tk.Frame(container, bg=THEME["bg_app"], width=620)
        left_col.pack(side="left", fill="both", padx=(0, 8))
        left_col.pack_propagate(False)

        cam_card = tk.Frame(left_col, bg=THEME["card_bg"], highlightthickness=1, highlightbackground=THEME["card_border"])
        cam_card.pack(fill="both", expand=True)

        cam_header = tk.Frame(cam_card, bg=THEME["card_bg"])
        cam_header.pack(fill="x", padx=16, pady=(12, 8))

        lbl_cam_title = tk.Label(cam_header, text="LIVE SCANNER FEED", font=(THEME["font_main"], 11, "bold"),
                                 fg=THEME["text_main"], bg=THEME["card_bg"])
        lbl_cam_title.pack(side="left")

        self.cam_index_var = tk.StringVar(value="Camera 0")
        cam_select = ttk.Combobox(cam_header, textvariable=self.cam_index_var, values=["Camera 0", "Camera 1", "Camera 2"],
                                  state="readonly", width=11)
        cam_select.pack(side="right")
        cam_select.bind("<<ComboboxSelected>>", self.on_camera_select_change)

        # Context & Session Settings Strip (Mode, Context Purpose, and Subject)
        sess_bar = tk.Frame(cam_card, bg=THEME["card_sub"], highlightthickness=1, highlightbackground=THEME["card_border"])
        sess_bar.pack(fill="x", padx=16, pady=(0, 6))

        lbl_mode = tk.Label(sess_bar, text="Mode:", font=(THEME["font_main"], 9, "bold"), fg=THEME["cyan"], bg=THEME["card_sub"])
        lbl_mode.pack(side="left", padx=(8, 4), pady=6)

        cb_mode = ttk.Combobox(sess_bar, textvariable=self.scan_mode_var,
                               values=["Check-In (Login)", "Check-Out (Logout)", "Auto (By Shift)"],
                               state="readonly", width=15)
        cb_mode.pack(side="left", padx=(0, 8), pady=6)

        lbl_cat = tk.Label(sess_bar, text="Context:", font=(THEME["font_main"], 9, "bold"), fg=THEME["text_muted"], bg=THEME["card_sub"])
        lbl_cat.pack(side="left", padx=(4, 4), pady=6)

        cb_cat = ttk.Combobox(sess_bar, textvariable=self.scan_category_var,
                              values=["Classroom Lecture", "Office Attendance", "Teachers / Faculty", "Laboratory Session", "Workshop / Seminar"],
                              state="readonly", width=15)
        cb_cat.pack(side="left", padx=(0, 8), pady=6)
        cb_cat.bind("<<ComboboxSelected>>", self.on_category_select_change)

        lbl_sub = tk.Label(sess_bar, text="Subject:", font=(THEME["font_main"], 9, "bold"), fg=THEME["text_muted"], bg=THEME["card_sub"])
        lbl_sub.pack(side="left", padx=(4, 4), pady=6)

        self.cb_subject = ttk.Combobox(sess_bar, textvariable=self.scan_subject_var, values=self.db.get_subjects(),
                                       state="readonly", width=14)
        self.cb_subject.pack(side="left", padx=(0, 8), pady=6)
        self.cb_subject.bind("<<ComboboxSelected>>", self.on_subject_select_change)

        self.canvas_cam = tk.Canvas(cam_card, width=580, height=380, bg="#050811",
                                    highlightthickness=1, highlightbackground=THEME["input_border"])
        self.canvas_cam.pack(padx=16, pady=4, fill="both", expand=True)
        self.draw_camera_placeholder("Scanner Inactive\nClick 'Start Scanner' below to launch camera feed.")

        self.banner_detection = tk.Label(cam_card, text="Ready for attendance scanning",
                                         font=(THEME["font_main"], 10, "bold"),
                                         fg=THEME["text_muted"], bg=THEME["card_sub"],
                                         padx=12, pady=8)
        self.banner_detection.pack(fill="x", padx=16, pady=(8, 12))

        ctrl_bar = tk.Frame(cam_card, bg=THEME["card_bg"])
        ctrl_bar.pack(fill="x", padx=16, pady=(0, 16))

        self.btn_toggle_cam = ModernButton(ctrl_bar, text="▶ Start Scanner", command=self.toggle_live_camera,
                                           bg=THEME["success"], hover_bg=THEME["success_hover"], width=16)
        self.btn_toggle_cam.pack(side="left", padx=(0, 8), fill="x", expand=True)

        self.btn_manual_mark = ModernButton(ctrl_bar, text="✍ Manual Check-in", command=self.show_manual_checkin_dialog,
                                            bg=THEME["card_sub"], hover_bg=THEME["card_border"], fg=THEME["text_main"], width=16)
        self.btn_manual_mark.pack(side="left", fill="x", expand=True)

        right_col = tk.Frame(container, bg=THEME["bg_app"])
        right_col.pack(side="right", fill="both", expand=True, padx=(8, 0))

        metrics_row = tk.Frame(right_col, bg=THEME["bg_app"])
        metrics_row.pack(fill="x", pady=(0, 8))

        self.card_total_students = MetricCard(metrics_row, title="Total Enrolled", value="0", icon="👥", accent_color=THEME["cyan"])
        self.card_total_students.pack(side="left", fill="both", expand=True, padx=(0, 6))

        self.card_today_present = MetricCard(metrics_row, title="Today's Present", value="0", icon="✅", accent_color=THEME["success"])
        self.card_today_present.pack(side="left", fill="both", expand=True, padx=6)

        self.card_last_marked = MetricCard(metrics_row, title="Latest Entry", value="None", icon="⏱", accent_color=THEME["accent_light"])
        self.card_last_marked.pack(side="left", fill="both", expand=True, padx=(6, 0))

        table_card = tk.Frame(right_col, bg=THEME["card_bg"], highlightthickness=1, highlightbackground=THEME["card_border"])
        table_card.pack(fill="both", expand=True)

        tbl_header = tk.Frame(table_card, bg=THEME["card_bg"])
        tbl_header.pack(fill="x", padx=16, pady=(12, 8))

        lbl_tbl_title = tk.Label(tbl_header, text="TODAY'S ATTENDANCE LOG", font=(THEME["font_main"], 11, "bold"),
                                 fg=THEME["text_main"], bg=THEME["card_bg"])
        lbl_tbl_title.pack(side="left")

        self.search_today_var = tk.StringVar()
        self.search_today_var.trace_add("write", lambda *args: self.filter_attendance_table())

        search_box = tk.Frame(tbl_header, bg=THEME["input_bg"], highlightthickness=1, highlightbackground=THEME["input_border"])
        search_box.pack(side="right", padx=(8, 0))

        lbl_search_ico = tk.Label(search_box, text="🔍", bg=THEME["input_bg"], fg=THEME["text_dim"], font=(THEME["font_main"], 9))
        lbl_search_ico.pack(side="left", padx=(6, 2))

        entry_search = tk.Entry(search_box, textvariable=self.search_today_var, bg=THEME["input_bg"], fg=THEME["text_main"],
                                insertbackground=THEME["cyan"], relief="flat", width=18, font=(THEME["font_main"], 9))
        entry_search.pack(side="left", ipady=3, padx=(0, 6))

        btn_refresh = tk.Button(tbl_header, text="🔄", command=self.reload_attendance_table,
                                bg=THEME["card_sub"], fg=THEME["text_main"], relief="flat", cursor="hand2")
        btn_refresh.pack(side="right", padx=(0, 6))

        tv_frame = tk.Frame(table_card, bg=THEME["card_bg"])
        tv_frame.pack(fill="both", expand=True, padx=16, pady=(0, 8))

        columns = ('sno', 'id', 'name', 'type', 'subject', 'date', 'time', 'status')
        self.tv_today = ttk.Treeview(tv_frame, columns=columns, show='headings', style='Modern.Treeview', height=13)

        self.tv_today.heading('sno', text='#')
        self.tv_today.heading('id', text='ID')
        self.tv_today.heading('name', text='Student / Employee')
        self.tv_today.heading('type', text='Type')
        self.tv_today.heading('subject', text='Subject / Dept')
        self.tv_today.heading('date', text='Date')
        self.tv_today.heading('time', text='Logged Time')
        self.tv_today.heading('status', text='Status')

        self.tv_today.column('sno', width=45, anchor=tk.CENTER)
        self.tv_today.column('id', width=80, anchor=tk.CENTER)
        self.tv_today.column('name', width=150, anchor=tk.W)
        self.tv_today.column('type', width=95, anchor=tk.CENTER)
        self.tv_today.column('subject', width=130, anchor=tk.W)
        self.tv_today.column('date', width=90, anchor=tk.CENTER)
        self.tv_today.column('time', width=105, anchor=tk.CENTER)
        self.tv_today.column('status', width=100, anchor=tk.CENTER)

        sb_v = ttk.Scrollbar(tv_frame, orient="vertical", command=self.tv_today.yview, style='Modern.Vertical.TScrollbar')
        self.tv_today.configure(yscrollcommand=sb_v.set)

        self.tv_today.pack(side="left", fill="both", expand=True)
        sb_v.pack(side="right", fill="y")
        self.tv_today.bind("<Double-1>", lambda e: self.on_edit_today_record())

        tbl_action_bar = tk.Frame(table_card, bg=THEME["card_bg"])
        tbl_action_bar.pack(fill="x", padx=16, pady=(0, 12))

        btn_edit_today = ModernButton(tbl_action_bar, text="✏ Edit Selected (Admin)", command=self.on_edit_today_record,
                                      bg=THEME["card_sub"], hover_bg=THEME["card_border"], fg=THEME["text_main"], padx=10)
        btn_edit_today.pack(side="left", padx=(0, 8))

        btn_del_today = ModernButton(tbl_action_bar, text="🗑 Delete Selected (Admin)", command=self.on_delete_today_record,
                                     bg=THEME["card_sub"], hover_bg=THEME["danger"], fg=THEME["danger"], padx=10)
        btn_del_today.pack(side="left")

    def draw_camera_placeholder(self, text):
        self.canvas_cam.delete("all")
        w = self.canvas_cam.winfo_width() or 580
        h = self.canvas_cam.winfo_height() or 410
        self.canvas_cam.create_rectangle(0, 0, w, h, fill="#070b14", outline="")
        self.canvas_cam.create_oval(w//2 - 40, h//2 - 60, w//2 + 40, h//2 + 20,
                                    outline=THEME["card_border"], width=2)
        self.canvas_cam.create_text(w//2, h//2 - 20, text="📷", font=(THEME["font_main"], 24), fill=THEME["text_dim"])
        self.canvas_cam.create_text(w//2, h//2 + 45, text=text, font=(THEME["font_main"], 11),
                                    fill=THEME["text_muted"], justify=tk.CENTER)

    # ------------------------------------------------------------------
    # TAB 2: Student Enrollment & Auto-Model Training
    # ------------------------------------------------------------------
    def build_tab_enroll(self):
        container = tk.Frame(self.tab_enroll, bg=THEME["bg_app"])
        container.pack(fill="both", expand=True, pady=8)

        left_col = tk.Frame(container, bg=THEME["bg_app"], width=460)
        left_col.pack(side="left", fill="both", padx=(0, 8))
        left_col.pack_propagate(False)

        reg_card = tk.Frame(left_col, bg=THEME["card_bg"], highlightthickness=1, highlightbackground=THEME["card_border"])
        reg_card.pack(fill="x", pady=(0, 10))

        reg_head = tk.Frame(reg_card, bg=THEME["card_bg"])
        reg_head.pack(fill="x", padx=16, pady=(14, 10))

        lbl_reg_title = tk.Label(reg_head, text="ENROLL NEW STUDENT", font=(THEME["font_main"], 11, "bold"),
                                 fg=THEME["text_main"], bg=THEME["card_bg"])
        lbl_reg_title.pack(side="left")

        frm_inputs = tk.Frame(reg_card, bg=THEME["card_bg"])
        frm_inputs.pack(fill="x", padx=16, pady=4)

        lbl_id = tk.Label(frm_inputs, text="Student ID (Numbers Only)", font=(THEME["font_main"], 9, "bold"),
                          fg=THEME["text_muted"], bg=THEME["card_bg"])
        lbl_id.pack(anchor="w", pady=(0, 2))

        self.reg_id_var = tk.StringVar()
        self.entry_reg_id = tk.Entry(frm_inputs, textvariable=self.reg_id_var, bg=THEME["input_bg"], fg=THEME["text_main"],
                                     insertbackground=THEME["cyan"], relief="flat", highlightthickness=1,
                                     highlightbackground=THEME["input_border"], highlightcolor=THEME["accent"],
                                     font=(THEME["font_main"], 11))
        self.entry_reg_id.pack(fill="x", ipady=6, pady=(0, 2))

        self.warn_reg_id = tk.Label(frm_inputs, text="", fg=THEME["danger"], bg=THEME["card_bg"], font=(THEME["font_main"], 8))
        self.warn_reg_id.pack(anchor="w")
        check_capslock_continuous(self.entry_reg_id, self.warn_reg_id)

        lbl_name = tk.Label(frm_inputs, text="Student Full Name", font=(THEME["font_main"], 9, "bold"),
                            fg=THEME["text_muted"], bg=THEME["card_bg"])
        lbl_name.pack(anchor="w", pady=(6, 2))

        self.reg_name_var = tk.StringVar()
        self.entry_reg_name = tk.Entry(frm_inputs, textvariable=self.reg_name_var, bg=THEME["input_bg"], fg=THEME["text_main"],
                                       insertbackground=THEME["cyan"], relief="flat", highlightthickness=1,
                                       highlightbackground=THEME["input_border"], highlightcolor=THEME["accent"],
                                       font=(THEME["font_main"], 11))
        self.entry_reg_name.pack(fill="x", ipady=6, pady=(0, 2))

        self.warn_reg_name = tk.Label(frm_inputs, text="", fg=THEME["danger"], bg=THEME["card_bg"], font=(THEME["font_main"], 8))
        self.warn_reg_name.pack(anchor="w")
        check_capslock_continuous(self.entry_reg_name, self.warn_reg_name)

        self.lbl_capture_status = tk.Label(frm_inputs, text="Fill details → Click 'Capture 100 Face Samples' (auto-trains model)",
                                           font=(THEME["font_main"], 9), fg=THEME["text_dim"], bg=THEME["card_bg"])
        self.lbl_capture_status.pack(anchor="w", pady=(8, 4))

        self.progress_capture = ttk.Progressbar(frm_inputs, orient="horizontal", mode="determinate",
                                               style='Modern.Horizontal.TProgressbar')
        self.progress_capture.pack(fill="x", pady=(0, 12))

        frm_enroll_btns = tk.Frame(reg_card, bg=THEME["card_bg"])
        frm_enroll_btns.pack(fill="x", padx=16, pady=(0, 16))

        self.btn_capture = ModernButton(frm_enroll_btns, text="📸 Capture Face Samples (100)", command=self.start_sample_capture,
                                        bg=THEME["accent"], hover_bg=THEME["accent_hover"])
        self.btn_capture.pack(side="left", fill="x", expand=True, padx=(0, 6))

        btn_clear_form = ModernButton(frm_enroll_btns, text="Clear Form", command=self.clear_enrollment_form,
                                      bg=THEME["card_sub"], hover_bg=THEME["card_border"], fg=THEME["text_muted"], width=10)
        btn_clear_form.pack(side="left")

        # Training Card
        train_card = tk.Frame(left_col, bg=THEME["card_bg"], highlightthickness=1, highlightbackground=THEME["card_border"])
        train_card.pack(fill="both", expand=True)

        train_head = tk.Frame(train_card, bg=THEME["card_bg"])
        train_head.pack(fill="x", padx=16, pady=(14, 8))

        lbl_train_title = tk.Label(train_head, text="MANUAL RE-TRAIN MODEL", font=(THEME["font_main"], 11, "bold"),
                                   fg=THEME["text_main"], bg=THEME["card_bg"])
        lbl_train_title.pack(side="left")

        lbl_train_desc = tk.Label(train_card, text="Note: New students are auto-trained upon capture. You can also manually re-train all image profiles here at any time.",
                                  font=(THEME["font_main"], 9), fg=THEME["text_dim"], bg=THEME["card_bg"],
                                  wraplength=410, justify="left")
        lbl_train_desc.pack(anchor="w", padx=16, pady=(0, 8))

        self.lbl_train_stat = tk.Label(train_card, text="Model Status: Ready & Loaded", font=(THEME["font_main"], 9, "bold"),
                                       fg=THEME["cyan"], bg=THEME["card_bg"])
        self.lbl_train_stat.pack(anchor="w", padx=16, pady=4)

        self.progress_train = ttk.Progressbar(train_card, orient="horizontal", mode="indeterminate",
                                             style='Modern.Horizontal.TProgressbar')
        self.progress_train.pack(fill="x", padx=16, pady=(0, 12))

        self.btn_train = ModernButton(train_card, text="⚡ Re-Train Recognition Model", command=self.trigger_model_training,
                                      bg=THEME["cyan"], hover_bg=THEME["cyan_hover"], fg=THEME["bg_app"])
        self.btn_train.pack(fill="x", padx=16, pady=(0, 16))

        right_col = tk.Frame(container, bg=THEME["bg_app"])
        right_col.pack(side="right", fill="both", expand=True, padx=(8, 0))

        dir_card = tk.Frame(right_col, bg=THEME["card_bg"], highlightthickness=1, highlightbackground=THEME["card_border"])
        dir_card.pack(fill="both", expand=True)

        dir_head = tk.Frame(dir_card, bg=THEME["card_bg"])
        dir_head.pack(fill="x", padx=16, pady=(14, 10))

        lbl_dir_title = tk.Label(dir_head, text="ENROLLED STUDENTS DIRECTORY (SQLITE)", font=(THEME["font_main"], 11, "bold"),
                                 fg=THEME["text_main"], bg=THEME["card_bg"])
        lbl_dir_title.pack(side="left")

        self.search_student_var = tk.StringVar()
        self.search_student_var.trace_add("write", lambda *args: self.filter_students_directory())

        stu_search_box = tk.Frame(dir_head, bg=THEME["input_bg"], highlightthickness=1, highlightbackground=THEME["input_border"])
        stu_search_box.pack(side="right", padx=(8, 0))

        lbl_stu_s_ico = tk.Label(stu_search_box, text="🔍", bg=THEME["input_bg"], fg=THEME["text_dim"], font=(THEME["font_main"], 9))
        lbl_stu_s_ico.pack(side="left", padx=(6, 2))

        entry_stu_search = tk.Entry(stu_search_box, textvariable=self.search_student_var, bg=THEME["input_bg"], fg=THEME["text_main"],
                                    insertbackground=THEME["cyan"], relief="flat", width=18, font=(THEME["font_main"], 9))
        entry_stu_search.pack(side="left", ipady=3, padx=(0, 6))

        btn_stu_refresh = tk.Button(dir_head, text="🔄", command=self.reload_students_directory,
                                    bg=THEME["card_sub"], fg=THEME["text_main"], relief="flat", cursor="hand2")
        btn_stu_refresh.pack(side="right", padx=(0, 6))

        stu_tv_frame = tk.Frame(dir_card, bg=THEME["card_bg"])
        stu_tv_frame.pack(fill="both", expand=True, padx=16, pady=(0, 10))

        stu_cols = ('serial', 'id', 'name', 'samples')
        self.tv_students = ttk.Treeview(stu_tv_frame, columns=stu_cols, show='headings', style='Modern.Treeview')

        self.tv_students.heading('serial', text='Serial #')
        self.tv_students.heading('id', text='Student ID')
        self.tv_students.heading('name', text='Full Name')
        self.tv_students.heading('samples', text='Saved Images')

        self.tv_students.column('serial', width=70, anchor=tk.CENTER)
        self.tv_students.column('id', width=110, anchor=tk.CENTER)
        self.tv_students.column('name', width=220, anchor=tk.W)
        self.tv_students.column('samples', width=110, anchor=tk.CENTER)

        sb_stu_v = ttk.Scrollbar(stu_tv_frame, orient="vertical", command=self.tv_students.yview, style='Modern.Vertical.TScrollbar')
        self.tv_students.configure(yscrollcommand=sb_stu_v.set)

        self.tv_students.pack(side="left", fill="both", expand=True)
        sb_stu_v.pack(side="right", fill="y")

        dir_actions = tk.Frame(dir_card, bg=THEME["card_bg"])
        dir_actions.pack(fill="x", padx=16, pady=(0, 16))

        self.btn_del_student = ModernButton(dir_actions, text="🗑 Delete Selected Student", command=self.delete_selected_student,
                                            bg=THEME["card_sub"], hover_bg=THEME["danger"], fg=THEME["text_main"], padx=10)
        self.btn_del_student.pack(side="left", padx=(0, 8))

        self.btn_clear_all_stu = ModernButton(dir_actions, text="🗑 Clear All Enrolled Students", command=self.clear_all_enrolled_students,
                                              bg=THEME["card_sub"], hover_bg=THEME["danger"], fg=THEME["danger"], padx=10)
        self.btn_clear_all_stu.pack(side="left", padx=(0, 8))

        lbl_dir_hint = tk.Label(dir_actions, text="(Requires admin password: smagix)",
                                font=(THEME["font_main"], 8), fg=THEME["text_dim"], bg=THEME["card_bg"])
        lbl_dir_hint.pack(side="left", padx=4)

    # ------------------------------------------------------------------
    # TAB 3: Attendance Analytics & Reports
    # ------------------------------------------------------------------
    def build_tab_reports(self):
        container = tk.Frame(self.tab_reports, bg=THEME["bg_app"])
        container.pack(fill="both", expand=True, pady=8)

        top_card = tk.Frame(container, bg=THEME["card_bg"], highlightthickness=1, highlightbackground=THEME["card_border"])
        top_card.pack(fill="x", pady=(0, 8))

        top_inner = tk.Frame(top_card, bg=THEME["card_bg"])
        top_inner.pack(fill="x", padx=16, pady=12)

        lbl_top_title = tk.Label(top_inner, text="HISTORICAL ATTENDANCE ARCHIVE", font=(THEME["font_main"], 11, "bold"),
                                 fg=THEME["text_main"], bg=THEME["card_bg"])
        lbl_top_title.pack(side="left", padx=(0, 16))

        self.history_search_var = tk.StringVar()
        self.history_search_var.trace_add("write", lambda *args: self.filter_history_table())

        hist_search_box = tk.Frame(top_inner, bg=THEME["input_bg"], highlightthickness=1, highlightbackground=THEME["input_border"])
        hist_search_box.pack(side="left", padx=(0, 12))

        lbl_h_s_ico = tk.Label(hist_search_box, text="🔍", bg=THEME["input_bg"], fg=THEME["text_dim"], font=(THEME["font_main"], 9))
        lbl_h_s_ico.pack(side="left", padx=(6, 2))

        entry_h_search = tk.Entry(hist_search_box, textvariable=self.history_search_var, bg=THEME["input_bg"], fg=THEME["text_main"],
                                  insertbackground=THEME["cyan"], relief="flat", width=22, font=(THEME["font_main"], 9))
        entry_h_search.pack(side="left", ipady=4, padx=(0, 8))

        self.history_filter_mode = tk.StringVar(value="All Records")
        filter_cb = ttk.Combobox(top_inner, textvariable=self.history_filter_mode,
                                 values=["All Records", "Today Only", "Specific Date..."], state="readonly", width=12)
        filter_cb.pack(side="left", padx=(0, 6))
        filter_cb.bind("<<ComboboxSelected>>", self.on_history_filter_change)

        self.history_cat_filter = tk.StringVar(value="All Categories")
        filter_cat_cb = ttk.Combobox(top_inner, textvariable=self.history_cat_filter,
                                     values=["All Categories", "Classroom Lecture", "Office Attendance", "Teachers / Faculty", "Laboratory Session", "Workshop / Seminar"],
                                     state="readonly", width=14)
        filter_cat_cb.pack(side="left", padx=(0, 6))
        filter_cat_cb.bind("<<ComboboxSelected>>", self.on_history_filter_change)

        self.history_sub_filter = tk.StringVar(value="All Subjects")
        self.cb_hist_sub = ttk.Combobox(top_inner, textvariable=self.history_sub_filter,
                                        values=["All Subjects"] + self.db.get_subjects(), state="readonly", width=13)
        self.cb_hist_sub.pack(side="left", padx=(0, 10))
        self.cb_hist_sub.bind("<<ComboboxSelected>>", self.on_history_filter_change)

        btn_export_xlsx = ModernButton(top_inner, text="📥 Excel (.xlsx)", command=self.export_to_excel,
                                       bg=THEME["success"], hover_bg=THEME["success_hover"], font=(THEME["font_main"], 9, "bold"))
        btn_export_xlsx.pack(side="right", padx=(6, 0))

        btn_export_csv = ModernButton(top_inner, text="📥 CSV", command=self.export_to_csv,
                                      bg=THEME["card_sub"], hover_bg=THEME["card_border"], fg=THEME["text_main"], font=(THEME["font_main"], 9, "bold"))
        btn_export_csv.pack(side="right")

        table_card = tk.Frame(container, bg=THEME["card_bg"], highlightthickness=1, highlightbackground=THEME["card_border"])
        table_card.pack(fill="both", expand=True, pady=(0, 8))

        hist_tv_frame = tk.Frame(table_card, bg=THEME["card_bg"])
        hist_tv_frame.pack(fill="both", expand=True, padx=16, pady=(16, 8))

        hist_cols = ('sno', 'id', 'name', 'type', 'category', 'subject', 'date', 'time', 'status')
        self.tv_history = ttk.Treeview(hist_tv_frame, columns=hist_cols, show='headings', style='Modern.Treeview')

        self.tv_history.heading('sno', text='#')
        self.tv_history.heading('id', text='ID')
        self.tv_history.heading('name', text='Student / Employee')
        self.tv_history.heading('type', text='Type')
        self.tv_history.heading('category', text='Context / Purpose')
        self.tv_history.heading('subject', text='Subject / Dept')
        self.tv_history.heading('date', text='Date')
        self.tv_history.heading('time', text='Logged Timestamp')
        self.tv_history.heading('status', text='Status')

        self.tv_history.column('sno', width=45, anchor=tk.CENTER)
        self.tv_history.column('id', width=80, anchor=tk.CENTER)
        self.tv_history.column('name', width=160, anchor=tk.W)
        self.tv_history.column('type', width=90, anchor=tk.CENTER)
        self.tv_history.column('category', width=140, anchor=tk.W)
        self.tv_history.column('subject', width=130, anchor=tk.W)
        self.tv_history.column('date', width=95, anchor=tk.CENTER)
        self.tv_history.column('time', width=110, anchor=tk.CENTER)
        self.tv_history.column('status', width=105, anchor=tk.CENTER)

        sb_h_v = ttk.Scrollbar(hist_tv_frame, orient="vertical", command=self.tv_history.yview, style='Modern.Vertical.TScrollbar')
        self.tv_history.configure(yscrollcommand=sb_h_v.set)

        self.tv_history.pack(side="left", fill="both", expand=True)
        sb_h_v.pack(side="right", fill="y")
        self.tv_history.bind("<Double-1>", lambda e: self.on_edit_history_record())

        hist_actions = tk.Frame(table_card, bg=THEME["card_bg"])
        hist_actions.pack(fill="x", padx=16, pady=(0, 12))

        btn_edit_hist = ModernButton(hist_actions, text="✏ Edit Selected (Admin)", command=self.on_edit_history_record,
                                     bg=THEME["card_sub"], hover_bg=THEME["card_border"], fg=THEME["text_main"], padx=10)
        btn_edit_hist.pack(side="left", padx=(0, 8))

        btn_del_hist = ModernButton(hist_actions, text="🗑 Delete Selected (Admin)", command=self.on_delete_history_record,
                                    bg=THEME["card_sub"], hover_bg=THEME["danger"], fg=THEME["danger"], padx=10)
        btn_del_hist.pack(side="left")

        email_card = tk.Frame(container, bg=THEME["card_bg"], highlightthickness=1, highlightbackground=THEME["card_border"])
        email_card.pack(fill="x")

        email_inner = tk.Frame(email_card, bg=THEME["card_bg"])
        email_inner.pack(fill="x", padx=16, pady=12)

        lbl_em_title = tk.Label(email_inner, text="EMAIL ATTENDANCE REPORT", font=(THEME["font_main"], 10, "bold"),
                                fg=THEME["text_main"], bg=THEME["card_bg"])
        lbl_em_title.pack(side="left", padx=(0, 16))

        self.email_recip_var = tk.StringVar()
        entry_recip = tk.Entry(email_inner, textvariable=self.email_recip_var, bg=THEME["input_bg"], fg=THEME["text_main"],
                               insertbackground=THEME["cyan"], relief="flat", width=22, font=(THEME["font_main"], 9))
        entry_recip.pack(side="left", ipady=4, padx=(0, 4))

        self.email_domain_var = tk.StringVar(value="@gmail.com")
        cb_domain = ttk.Combobox(email_inner, textvariable=self.email_domain_var,
                                 values=["@gmail.com", "@yahoo.com", "@outlook.com", "@hotmail.com", "Custom Domain"],
                                 state="readonly", width=12)
        cb_domain.pack(side="left", padx=(0, 16))

        btn_send_email = ModernButton(email_inner, text="✉ Send Today's Attendance Sheet", command=self.dispatch_email_report,
                                      bg=THEME["accent"], hover_bg=THEME["accent_hover"], font=(THEME["font_main"], 9, "bold"))
        btn_send_email.pack(side="right")

    # ------------------------------------------------------------------
    # TAB 4: System Settings & Security
    # ------------------------------------------------------------------
    def build_tab_settings(self):
        canvas = tk.Canvas(self.tab_settings, bg=THEME["bg_app"], highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.tab_settings, orient="vertical", command=canvas.yview, style='Modern.Vertical.TScrollbar')
        container = tk.Frame(canvas, bg=THEME["bg_app"])

        container.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas_win = canvas.create_window((0, 0), window=container, anchor="nw")

        def _on_cv_config(event):
            canvas.itemconfig(canvas_win, width=event.width)
        canvas.bind("<Configure>", _on_cv_config)
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True, padx=(0, 2))
        scrollbar.pack(side="right", fill="y")

        col1 = tk.Frame(container, bg=THEME["bg_app"])
        col1.pack(side="left", fill="both", expand=True, padx=(0, 8), pady=8)

        col2 = tk.Frame(container, bg=THEME["bg_app"])
        col2.pack(side="right", fill="both", expand=True, padx=(8, 0), pady=8)

        # 1. Shift Schedule Card (Admin)
        card_shift = tk.Frame(col1, bg=THEME["card_bg"], highlightthickness=1, highlightbackground=THEME["card_border"])
        card_shift.pack(fill="x", pady=(0, 12))

        lbl_shift_title = tk.Label(card_shift, text="ATTENDANCE SHIFT SCHEDULE (ADMIN)", font=(THEME["font_main"], 11, "bold"),
                                   fg=THEME["text_main"], bg=THEME["card_bg"])
        lbl_shift_title.pack(anchor="w", padx=16, pady=(14, 4))

        lbl_shift_desc = tk.Label(card_shift, text="Configure expected login/logout shift times. Scans arriving after grace period are flagged as Late Login or Early Departure.",
                                  font=(THEME["font_main"], 9), fg=THEME["text_dim"], bg=THEME["card_bg"], wraplength=480, justify="left")
        lbl_shift_desc.pack(anchor="w", padx=16, pady=(0, 10))

        frm_in = tk.Frame(card_shift, bg=THEME["card_bg"])
        frm_in.pack(fill="x", padx=16, pady=4)
        tk.Label(frm_in, text="Expected Login Time:", font=(THEME["font_main"], 9), fg=THEME["text_muted"], bg=THEME["card_bg"], width=20, anchor="w").pack(side="left")
        cb_in = ttk.Combobox(frm_in, textvariable=self.shift_in_var, values=["07:30 AM", "08:00 AM", "08:30 AM", "09:00 AM", "09:30 AM", "10:00 AM"], width=14)
        cb_in.pack(side="left")

        frm_out = tk.Frame(card_shift, bg=THEME["card_bg"])
        frm_out.pack(fill="x", padx=16, pady=4)
        tk.Label(frm_out, text="Expected Logout Time:", font=(THEME["font_main"], 9), fg=THEME["text_muted"], bg=THEME["card_bg"], width=20, anchor="w").pack(side="left")
        cb_out = ttk.Combobox(frm_out, textvariable=self.shift_out_var, values=["03:30 PM", "04:00 PM", "04:30 PM", "05:00 PM", "05:30 PM", "06:00 PM"], width=14)
        cb_out.pack(side="left")

        frm_grace = tk.Frame(card_shift, bg=THEME["card_bg"])
        frm_grace.pack(fill="x", padx=16, pady=4)
        tk.Label(frm_grace, text="Grace Period (Minutes):", font=(THEME["font_main"], 9), fg=THEME["text_muted"], bg=THEME["card_bg"], width=20, anchor="w").pack(side="left")
        e_grace = tk.Entry(frm_grace, textvariable=self.grace_period_var, bg=THEME["input_bg"], fg=THEME["text_main"],
                           insertbackground=THEME["cyan"], relief="flat", width=8, font=(THEME["font_main"], 9))
        e_grace.pack(side="left")

        btn_save_shift = ModernButton(card_shift, text="💾 Save Shift Schedule (Admin)", command=self.save_shift_schedule,
                                      bg=THEME["accent"], hover_bg=THEME["accent_hover"])
        btn_save_shift.pack(anchor="w", padx=16, pady=(10, 16))

        # 2. Recognition Sensitivity Card
        card_recog = tk.Frame(col1, bg=THEME["card_bg"], highlightthickness=1, highlightbackground=THEME["card_border"])
        card_recog.pack(fill="x", pady=(0, 12))

        lbl_rec_title = tk.Label(card_recog, text="RECOGNITION SENSITIVITY & VERIFICATION", font=(THEME["font_main"], 11, "bold"),
                                 fg=THEME["text_main"], bg=THEME["card_bg"])
        lbl_rec_title.pack(anchor="w", padx=16, pady=(14, 8))

        chk_dup = tk.Checkbutton(card_recog, text="Prevent duplicate check-ins/check-outs on the same calendar day",
                                 variable=self.duplicate_check_enabled, bg=THEME["card_bg"], fg=THEME["text_main"],
                                 selectcolor=THEME["input_bg"], activebackground=THEME["card_bg"],
                                 activeforeground=THEME["text_main"], font=(THEME["font_main"], 10))
        chk_dup.pack(anchor="w", padx=16, pady=4)

        chk_autotrain = tk.Checkbutton(card_recog, text="Auto-train model immediately after capturing new face samples",
                                       variable=self.auto_train_enabled, bg=THEME["card_bg"], fg=THEME["text_main"],
                                       selectcolor=THEME["input_bg"], activebackground=THEME["card_bg"],
                                       activeforeground=THEME["text_main"], font=(THEME["font_main"], 10))
        chk_autotrain.pack(anchor="w", padx=16, pady=4)

        lbl_slider = tk.Label(card_recog, text="LBPH Confidence Threshold (Lower = Stricter Match, Default: 48):",
                              font=(THEME["font_main"], 9), fg=THEME["text_muted"], bg=THEME["card_bg"])
        lbl_slider.pack(anchor="w", padx=16, pady=(8, 2))

        slider_frm = tk.Frame(card_recog, bg=THEME["card_bg"])
        slider_frm.pack(fill="x", padx=16, pady=(0, 16))

        self.slider_conf = tk.Scale(slider_frm, from_=35, to=60, orient="horizontal", variable=self.confidence_threshold,
                                    bg=THEME["card_bg"], fg=THEME["text_main"], highlightthickness=0,
                                    troughcolor=THEME["input_bg"], activebackground=THEME["accent"])
        self.slider_conf.pack(fill="x")

        # 3. Security Card
        card_sec = tk.Frame(col1, bg=THEME["card_bg"], highlightthickness=1, highlightbackground=THEME["card_border"])
        card_sec.pack(fill="x", pady=(0, 12))

        lbl_sec_title = tk.Label(card_sec, text="ADMIN SECURITY & ACCESS", font=(THEME["font_main"], 11, "bold"),
                                 fg=THEME["text_main"], bg=THEME["card_bg"])
        lbl_sec_title.pack(anchor="w", padx=16, pady=(14, 8))

        lbl_sec_desc = tk.Label(card_sec, text="Manage the master administrator password (default: smagix) required for modifying records.",
                                font=(THEME["font_main"], 9), fg=THEME["text_dim"], bg=THEME["card_bg"], wraplength=480, justify="left")
        lbl_sec_desc.pack(anchor="w", padx=16, pady=(0, 12))

        btn_chg_pwd = ModernButton(card_sec, text="🔑 Change Master Admin Password", command=self.change_admin_password,
                                   bg=THEME["card_sub"], hover_bg=THEME["card_border"], fg=THEME["text_main"])
        btn_chg_pwd.pack(anchor="w", padx=16, pady=(0, 16))

        # 4. Subject & Department Management Card (Admin)
        card_subjs = tk.Frame(col2, bg=THEME["card_bg"], highlightthickness=1, highlightbackground=THEME["card_border"])
        card_subjs.pack(fill="x", pady=(0, 12))

        lbl_sub_title = tk.Label(card_subjs, text="CLASS SUBJECTS & DEPARTMENTS (ADMIN)", font=(THEME["font_main"], 11, "bold"),
                                 fg=THEME["text_main"], bg=THEME["card_bg"])
        lbl_sub_title.pack(anchor="w", padx=16, pady=(14, 4))

        lbl_sub_desc = tk.Label(card_subjs, text="Manage subjects for teacher attendance taking (e.g. Mathematics, Physics, Networks). These are selectable directly on the live scanner.",
                                font=(THEME["font_main"], 9), fg=THEME["text_dim"], bg=THEME["card_bg"], wraplength=480, justify="left")
        lbl_sub_desc.pack(anchor="w", padx=16, pady=(0, 8))

        # Subjects Listbox Frame
        lb_frame = tk.Frame(card_subjs, bg=THEME["card_bg"])
        lb_frame.pack(fill="x", padx=16, pady=(0, 8))

        self.lb_subjects = tk.Listbox(lb_frame, bg=THEME["input_bg"], fg=THEME["text_main"],
                                      selectbackground=THEME["accent"], selectforeground="white",
                                      relief="flat", highlightthickness=1, highlightbackground=THEME["input_border"],
                                      height=6, font=(THEME["font_main"], 10))
        sb_lb = ttk.Scrollbar(lb_frame, orient="vertical", command=self.lb_subjects.yview, style='Modern.Vertical.TScrollbar')
        self.lb_subjects.configure(yscrollcommand=sb_lb.set)
        self.lb_subjects.pack(side="left", fill="both", expand=True)
        sb_lb.pack(side="right", fill="y")

        # Entry for Add / Edit
        frm_sub_input = tk.Frame(card_subjs, bg=THEME["card_bg"])
        frm_sub_input.pack(fill="x", padx=16, pady=(0, 8))

        self.entry_new_sub_var = tk.StringVar()
        entry_new_sub = tk.Entry(frm_sub_input, textvariable=self.entry_new_sub_var, bg=THEME["input_bg"], fg=THEME["text_main"],
                                 insertbackground=THEME["cyan"], relief="flat", highlightthickness=1,
                                 highlightbackground=THEME["input_border"], font=(THEME["font_main"], 10))
        entry_new_sub.pack(fill="x", ipady=4)

        # Subject Action Buttons
        frm_sub_btns = tk.Frame(card_subjs, bg=THEME["card_bg"])
        frm_sub_btns.pack(fill="x", padx=16, pady=(0, 16))

        btn_add_sub = ModernButton(frm_sub_btns, text="➕ Add Subject", command=self.on_add_subject_action,
                                   bg=THEME["accent"], hover_bg=THEME["accent_hover"], padx=8)
        btn_add_sub.pack(side="left", padx=(0, 6))

        btn_edit_sub = ModernButton(frm_sub_btns, text="✏ Rename Selected", command=self.on_edit_subject_action,
                                    bg=THEME["card_sub"], hover_bg=THEME["card_border"], fg=THEME["text_main"], padx=8)
        btn_edit_sub.pack(side="left", padx=(0, 6))

        btn_del_sub = ModernButton(frm_sub_btns, text="🗑 Remove", command=self.on_delete_subject_action,
                                   bg=THEME["card_sub"], hover_bg=THEME["danger"], fg=THEME["danger"], padx=8)
        btn_del_sub.pack(side="left")

        self.reload_subject_listbox()

        # 5. Database Sync Card
        card_data = tk.Frame(col2, bg=THEME["card_bg"], highlightthickness=1, highlightbackground=THEME["card_border"])
        card_data.pack(fill="x", pady=(0, 12))

        lbl_data_title = tk.Label(card_data, text="DATABASE SYNC & ARCHIVE", font=(THEME["font_main"], 11, "bold"),
                                  fg=THEME["text_main"], bg=THEME["card_bg"])
        lbl_data_title.pack(anchor="w", padx=16, pady=(14, 8))

        lbl_data_desc = tk.Label(card_data, text="Data is safely preserved in SQLite (attendance.db). You can trigger a manual Excel sync or download a full zip backup.",
                                 font=(THEME["font_main"], 9), fg=THEME["text_dim"], bg=THEME["card_bg"], wraplength=480, justify="left")
        lbl_data_desc.pack(anchor="w", padx=16, pady=(0, 12))

        frm_data_btns = tk.Frame(card_data, bg=THEME["card_bg"])
        frm_data_btns.pack(fill="x", padx=16, pady=(0, 16))

        btn_sync_xl = ModernButton(frm_data_btns, text="🔄 Sync SQLite to Excel Now", command=self.manual_sync_to_excel,
                                   bg=THEME["card_sub"], hover_bg=THEME["card_border"], fg=THEME["text_main"])
        btn_sync_xl.pack(side="left", padx=(0, 8))

        btn_backup = ModernButton(frm_data_btns, text="📦 Full System Backup (.zip)", command=self.create_data_backup,
                                  bg=THEME["cyan"], hover_bg=THEME["cyan_hover"], fg=THEME["bg_app"])
        btn_backup.pack(side="left")

        # 6. Danger Zone Card
        card_danger = tk.Frame(col2, bg=THEME["card_bg"], highlightthickness=1, highlightbackground=THEME["danger_sub"])
        card_danger.pack(fill="x", pady=(0, 16))

        lbl_dng_title = tk.Label(card_danger, text="DANGER ZONE", font=(THEME["font_main"], 11, "bold"),
                                 fg=THEME["danger"], bg=THEME["card_bg"])
        lbl_dng_title.pack(anchor="w", padx=16, pady=(14, 8))

        lbl_dng_desc = tk.Label(card_danger, text="Destructive operations are irreversible and require admin password verification.",
                                font=(THEME["font_main"], 9), fg=THEME["text_dim"], bg=THEME["card_bg"], wraplength=480, justify="left")
        lbl_dng_desc.pack(anchor="w", padx=16, pady=(0, 12))

        btn_del_att = ModernButton(card_danger, text="Clear Attendance Log (SQLite & Excel)", command=self.danger_clear_attendance,
                                   bg=THEME["card_sub"], hover_bg=THEME["danger"], fg=THEME["danger"])
        btn_del_att.pack(anchor="w", padx=16, pady=(0, 8))

        btn_del_all = ModernButton(card_danger, text="Reset Entire Dataset & Enrolled Images", command=self.danger_clear_all_data,
                                   bg=THEME["card_sub"], hover_bg=THEME["danger"], fg=THEME["danger"])
        btn_del_all.pack(anchor="w", padx=16, pady=(0, 16))

    # ------------------------------------------------------------------
    # Live Camera Engine with Multi-Frame Stability Filter
    # ------------------------------------------------------------------
    def on_camera_select_change(self, event=None):
        val = self.cam_index_var.get()
        try:
            self.camera_index = int(val.split()[-1])
        except Exception:
            self.camera_index = 0
        if self.camera_active:
            self.stop_live_camera()
            self.start_live_camera()

    def toggle_live_camera(self):
        if self.camera_active:
            self.stop_live_camera()
        else:
            self.start_live_camera()

    def start_live_camera(self):
        if not check_haarcascade():
            return
        try:
            self.camera_device = cv2.VideoCapture(self.camera_index)
            if not self.camera_device.isOpened():
                messagebox.showerror("Camera Error", f"Unable to access camera device index {self.camera_index}.")
                return
            self.camera_active = True
            self.btn_toggle_cam.configure(text="⏹ Stop Scanner")
            self.btn_toggle_cam.set_color(THEME["danger"], THEME["danger_hover"])
            self.pill_cam_status.config(text="🟢 SCANNER ACTIVE", fg=THEME["success"])
            self.banner_detection.config(text="Scanner running • Position face inside camera view", fg=THEME["cyan"])
            self.current_candidate_id = None
            self.candidate_streak = 0
            self.process_camera_loop()
        except Exception as e:
            messagebox.showerror("Camera Exception", str(e))
            self.stop_live_camera()

    def stop_live_camera(self):
        self.camera_active = False
        if self.camera_device:
            try:
                self.camera_device.release()
            except Exception:
                pass
            self.camera_device = None
        self.btn_toggle_cam.configure(text="▶ Start Scanner")
        self.btn_toggle_cam.set_color(THEME["success"], THEME["success_hover"])
        self.pill_cam_status.config(text="⚪ CAMERA STANDBY", fg=THEME["text_dim"])
        self.banner_detection.config(text="Ready for attendance scanning", fg=THEME["text_muted"])
        self.draw_camera_placeholder("Scanner Inactive\nClick 'Start Scanner' below to launch camera feed.")

    def process_camera_loop(self):
        if not self.camera_active or not self.camera_device:
            return

        now_ts = time.time()

        # Check post-attendance lockout pause
        if now_ts < self.global_cooldown_until:
            rem = max(1, int(self.global_cooldown_until - now_ts + 1))
            self.banner_detection.config(
                text=f"Verified! Scanner locked • Next student can scan in {rem}s...",
                fg=THEME["warning"]
            )
            # Read frame to keep stream alive
            ret, frame = self.camera_device.read()
            if ret and frame is not None:
                frame = cv2.flip(frame, 1)
                cv2.putText(frame, f"LOCKOUT: Next scan in {rem}s", (30, 40),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 200, 255), 2)
                self.render_frame_on_canvas(frame)
            if self.camera_active:
                self.root.after(100, self.process_camera_loop)
            return

        ret, frame = self.camera_device.read()
        if not ret or frame is None:
            self.root.after(30, self.process_camera_loop)
            return

        frame = cv2.flip(frame, 1)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        faces = []
        if self.face_cascade:
            try:
                faces = self.face_cascade.detectMultiScale(gray, scaleFactor=1.2, minNeighbors=5, minSize=(60, 60))
            except Exception:
                faces = []

        if len(faces) == 0:
            # Face lost: decay streak
            self.candidate_streak = max(0, self.candidate_streak - 1)
            self.banner_detection.config(text="Looking for face in camera view...", fg=THEME["text_muted"])
        else:
            # Pick largest face
            faces = sorted(faces, key=lambda b: b[2] * b[3], reverse=True)
            (x, y, w, h) = faces[0]

            matched_name = "Unknown Face"
            matched_id = None
            is_recognized = False
            match_pct = 0

            if self.recognizer and len(self.students_cache) > 0:
                try:
                    pred_id, conf = self.recognizer.predict(gray[y:y+h, x:x+w])
                    thresh = self.confidence_threshold.get()

                    # Strict calibrated threshold check: must be genuine match and enrolled in SQLite
                    if conf < thresh and pred_id in self.students_cache:
                        matched_id = pred_id
                        matched_name = self.students_cache[pred_id]
                        is_recognized = True
                        match_pct = max(0, min(100, int((100 - conf) * 1.5)))
                except Exception:
                    pass

            if is_recognized and matched_id is not None:
                # Multi-frame stability filter
                if self.current_candidate_id == matched_id:
                    self.candidate_streak += 1
                else:
                    self.current_candidate_id = matched_id
                    self.candidate_streak = 1

                box_color = (0, 220, 130)  # Green
                display_text = f"{matched_name} ({matched_id}) [{match_pct}%]"
                status_text = f"Identifying: {matched_name} ({self.candidate_streak}/{self.required_consecutive_frames} frames)"
                self.banner_detection.config(text=status_text, fg=THEME["cyan"])

                # Log attendance only when continuously verified across required frames
                if self.candidate_streak >= self.required_consecutive_frames:
                    self.handle_attendance_hit(matched_id, matched_name, now_ts)
                    self.candidate_streak = 0
                    self.current_candidate_id = None
            else:
                # Unknown face or below strict threshold
                self.candidate_streak = max(0, self.candidate_streak - 1)
                box_color = (50, 120, 240)  # Orange/Red
                display_text = "Unknown Face"
                self.banner_detection.config(text="⚠ Face not recognized (Unknown). Please enroll first.", fg=THEME["warning"])

            # Draw sleek targeting reticle
            self.draw_corner_rect(frame, x, y, w, h, box_color, thickness=2, corner_len=20)
            cv2.putText(frame, display_text, (x, max(24, y - 8)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2, cv2.LINE_AA)

        self.render_frame_on_canvas(frame)

        if self.camera_active:
            self.root.after(25, self.process_camera_loop)

    def render_frame_on_canvas(self, frame):
        try:
            cw = self.canvas_cam.winfo_width() or 580
            ch = self.canvas_cam.winfo_height() or 410
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            pil_img = Image.fromarray(frame_rgb)
            pil_img = pil_img.resize((cw, ch), Image.Resampling.BILINEAR)
            self.tk_frame_img = ImageTk.PhotoImage(image=pil_img)
            self.canvas_cam.create_image(0, 0, anchor="nw", image=self.tk_frame_img)
        except Exception:
            pass

    def draw_corner_rect(self, img, x, y, w, h, color, thickness=2, corner_len=20):
        cv2.rectangle(img, (x, y), (x + w, y + h), color, 1)
        cv2.line(img, (x, y), (x + corner_len, y), color, thickness)
        cv2.line(img, (x, y), (x, y + corner_len), color, thickness)
        cv2.line(img, (x + w, y), (x + w - corner_len, y), color, thickness)
        cv2.line(img, (x + w, y), (x + w, y + corner_len), color, thickness)
        cv2.line(img, (x, y + h), (x + corner_len, y + h), color, thickness)
        cv2.line(img, (x, y + h), (x, y + h - corner_len), color, thickness)
        cv2.line(img, (x + w, y + h), (x + w - corner_len, y + h), color, thickness)
        cv2.line(img, (x + w, y + h), (x + w, y + corner_len), color, thickness)

    def handle_attendance_hit(self, student_id, student_name, now_ts, custom_type=None, custom_cat=None, custom_sub=None):
        date_str = datetime.datetime.now().strftime('%d-%m-%Y')
        time_str = datetime.datetime.now().strftime('%I:%M:%S %p')

        # Determine effective mode (Check-In, Check-Out)
        mode_val = self.scan_mode_var.get()
        if custom_type:
            log_type = custom_type
        elif "Check-Out" in mode_val:
            log_type = "Check-Out"
        elif "Check-In" in mode_val:
            log_type = "Check-In"
        else:
            # Auto mode: determine based on current time vs halfway of shift (after 1:00 PM = Check-Out)
            now_hour = datetime.datetime.now().hour
            log_type = "Check-Out" if now_hour >= 13 else "Check-In"

        category = custom_cat or self.scan_category_var.get()
        subject = custom_sub or self.scan_subject_var.get()
        if not subject:
            subject = "General"

        # Calculate shift status based on admin shift configuration
        shift_in = self.shift_in_var.get()
        shift_out = self.shift_out_var.get()
        try:
            grace_mins = int(self.grace_period_var.get())
        except ValueError:
            grace_mins = 15

        shift_status = evaluate_shift_status(time_str, log_type, shift_in, shift_out, grace_mins)

        # Prevent duplicate check-in or check-out today for this student/subject
        if self.duplicate_check_enabled.get():
            if self.db.is_already_marked_today(student_id, date_str, log_type=log_type, subject=subject):
                self.global_cooldown_until = now_ts + 3.0
                self.banner_detection.config(
                    text=f"ℹ {student_name} (ID: {student_id}) has ALREADY logged {log_type} for [{subject}] today!",
                    fg=THEME["warning"]
                )
                return

        # Record attendance in SQLite with context, subject and shift status
        self.db.log_attendance(student_id, student_name, date_str, time_str,
                               log_type=log_type, category=category, subject=subject,
                               status="Present", shift_status=shift_status)
        threading.Thread(target=self.db.sync_to_excel, daemon=True).start()

        # Activate 4-second lockout so only this single person's attendance is taken
        self.global_cooldown_until = now_ts + 4.0

        status_color = THEME["warning"] if "Late" in shift_status or "Early" in shift_status else THEME["success"]
        self.banner_detection.config(
            text=f"✅ [{log_type} • {subject}] LOGGED: {student_name} (ID: {student_id}) at {time_str} ({shift_status})!",
            fg=status_color
        )
        self.card_last_marked.update_value(f"{student_name} ({log_type})")
        self.reload_attendance_table()
        self.refresh_dashboard_counters()

    def show_manual_checkin_dialog(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Manual Attendance Entry")
        dialog.geometry("450x390")
        dialog.configure(bg=THEME["card_bg"])
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()

        lbl_hdr = tk.Label(dialog, text="MANUAL ATTENDANCE ENTRY", font=(THEME["font_main"], 11, "bold"),
                           fg=THEME["text_main"], bg=THEME["card_bg"])
        lbl_hdr.pack(anchor="w", padx=24, pady=(20, 8))

        lbl_sel = tk.Label(dialog, text="Select Enrolled Student / Employee:", font=(THEME["font_main"], 9),
                           fg=THEME["text_muted"], bg=THEME["card_bg"])
        lbl_sel.pack(anchor="w", padx=24, pady=(4, 2))

        students = self.db.get_all_students()
        student_options = [f"{s['name']} (ID: {s['student_id']})" for s in students]

        sel_var = tk.StringVar()
        if student_options:
            sel_var.set(student_options[0])

        cb_stu = ttk.Combobox(dialog, textvariable=sel_var, values=student_options, state="readonly", width=38)
        cb_stu.pack(padx=24, pady=(0, 10))

        # Mode / Type
        lbl_m = tk.Label(dialog, text="Attendance Type (Login/Logout):", font=(THEME["font_main"], 9),
                         fg=THEME["text_muted"], bg=THEME["card_bg"])
        lbl_m.pack(anchor="w", padx=24, pady=(2, 2))
        type_var = tk.StringVar(value="Check-In")
        cb_t = ttk.Combobox(dialog, textvariable=type_var, values=["Check-In", "Check-Out"], state="readonly", width=38)
        cb_t.pack(padx=24, pady=(0, 10))

        # Context Category
        lbl_c = tk.Label(dialog, text="Context / Purpose:", font=(THEME["font_main"], 9),
                         fg=THEME["text_muted"], bg=THEME["card_bg"])
        lbl_c.pack(anchor="w", padx=24, pady=(2, 2))
        cat_var = tk.StringVar(value=self.scan_category_var.get())
        cb_c = ttk.Combobox(dialog, textvariable=cat_var,
                            values=["Classroom Lecture", "Office Attendance", "Teachers / Faculty", "Laboratory Session", "Workshop / Seminar"],
                            state="readonly", width=38)
        cb_c.pack(padx=24, pady=(0, 10))

        # Subject / Department
        lbl_s = tk.Label(dialog, text="Subject / Department:", font=(THEME["font_main"], 9),
                         fg=THEME["text_muted"], bg=THEME["card_bg"])
        lbl_s.pack(anchor="w", padx=24, pady=(2, 2))
        sub_var = tk.StringVar(value=self.scan_subject_var.get())
        cb_s = ttk.Combobox(dialog, textvariable=sub_var, values=self.db.get_subjects(), width=38)
        cb_s.pack(padx=24, pady=(0, 18))

        def on_confirm_manual():
            chosen = sel_var.get()
            if not chosen:
                return
            try:
                sid = int(chosen.split("ID:")[-1].replace(")", "").strip())
                sname = chosen.split("(ID:")[0].strip()
            except Exception:
                return

            now_ts = time.time()
            self.handle_attendance_hit(sid, sname, now_ts,
                                       custom_type=type_var.get().strip(),
                                       custom_cat=cat_var.get().strip(),
                                       custom_sub=sub_var.get().strip())
            dialog.destroy()

        btn_bar = tk.Frame(dialog, bg=THEME["card_bg"])
        btn_bar.pack(fill="x", padx=24, pady=(0, 16))

        btn_ok = ModernButton(btn_bar, text="Mark Attendance", command=on_confirm_manual, bg=THEME["accent"])
        btn_ok.pack(side="right", padx=(8, 0))

        btn_cancel = ModernButton(btn_bar, text="Cancel", command=dialog.destroy, bg=THEME["card_sub"], fg=THEME["text_muted"])
        btn_cancel.pack(side="right")

    # ------------------------------------------------------------------
    # TAB 2 Operations: Enrollment & Model Training
    # ------------------------------------------------------------------
    def clear_enrollment_form(self):
        self.reg_id_var.set("")
        self.reg_name_var.set("")
        self.progress_capture['value'] = 0
        self.lbl_capture_status.config(text="Fill details → Click 'Capture 100 Face Samples' (auto-trains model)", fg=THEME["text_dim"])

    def start_sample_capture(self):
        if not check_haarcascade():
            return

        sid = self.reg_id_var.get().strip()
        sname = self.reg_name_var.get().strip()

        if not sid.isdigit():
            messagebox.showwarning("Validation Error", "Student ID must contain numbers only.")
            self.entry_reg_id.focus_set()
            return

        if not sname or not sname.replace(" ", "").isalpha():
            messagebox.showwarning("Validation Error", "Student Name must contain letters and spaces only.")
            self.entry_reg_name.focus_set()
            return

        int_sid = int(sid)
        if int_sid in self.students_cache:
            existing_name = self.students_cache[int_sid]
            proceed = messagebox.askyesno(
                "ID Already Enrolled",
                f"Student ID '{int_sid}' is already registered as '{existing_name}'.\n\nDo you want to update face samples for this student?"
            )
            if not proceed:
                return

        if self.camera_active:
            self.stop_live_camera()

        self.btn_capture.config(state=tk.DISABLED)
        self.lbl_capture_status.config(text="Opening camera for sample capture...", fg=THEME["cyan"])
        self.progress_capture['value'] = 0

        threading.Thread(target=self._worker_capture_samples, args=(int_sid, sname), daemon=True).start()

    def _worker_capture_samples(self, sid, sname):
        safe_name = sname.replace(" ", "_")
        user_folder = os.path.join(TRAINING_IMAGE_DIR, f"{safe_name}_{sid}")
        os.makedirs(user_folder, exist_ok=True)

        cam = cv2.VideoCapture(self.camera_index)
        if not cam.isOpened():
            self.root.after(0, lambda: self._on_capture_error("Failed to access camera device."))
            return

        detector = cv2.CascadeClassifier(HAARCASCADE_FILE)
        sample_num = 0
        target_samples = 100

        try:
            while sample_num < target_samples:
                ret, img = cam.read()
                if not ret:
                    break
                img = cv2.flip(img, 1)
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                faces = detector.detectMultiScale(gray, 1.3, 5, minSize=(60, 60))

                for (x, y, w, h) in faces:
                    sample_num += 1
                    face_color = img[y:y+h, x:x+w]
                    filename = f"{sname}.{sid}.{sample_num}.jpg"
                    cv2.imwrite(os.path.join(user_folder, filename), face_color)
                    cv2.rectangle(img, (x, y), (x+w, y+h), (0, 255, 0), 2)

                cv2.imshow("Enrolling Face Samples (Press Q to cancel)", img)
                key = cv2.waitKey(80) & 0xFF
                if key in (ord('q'), ord('Q')):
                    break

                pct = int((sample_num / target_samples) * 100)
                self.root.after(0, lambda p=pct, n=sample_num: self._update_capture_progress(p, n))

        finally:
            cam.release()
            cv2.destroyAllWindows()

        if sample_num > 0:
            self.db.add_or_update_student(sid, sname, img_count=sample_num)
            threading.Thread(target=self.db.sync_to_excel, daemon=True).start()

            if self.auto_train_enabled.get():
                self.root.after(0, lambda: self._start_auto_training(sid, sname, sample_num))
            else:
                self.root.after(0, lambda: self._on_capture_finished_no_train(sample_num, sname))
        else:
            self.root.after(0, lambda: self._on_capture_error("No face samples were captured."))

    def _update_capture_progress(self, pct, sample_num):
        self.progress_capture['value'] = pct
        self.lbl_capture_status.config(text=f"Capturing: {sample_num} / 100 images ({pct}%)", fg=THEME["cyan"])

    def _start_auto_training(self, sid, sname, count):
        self.btn_capture.config(state=tk.DISABLED)
        self.lbl_capture_status.config(text=f"Auto-training recognition model for {sname}...", fg=THEME["warning"])
        self.progress_train.start(10)
        threading.Thread(target=self._worker_train_model, args=(True, sname, sid), daemon=True).start()

    def _on_capture_finished_no_train(self, count, sname):
        self.btn_capture.config(state=tk.NORMAL)
        self.lbl_capture_status.config(text=f"✅ Captured {count} samples for {sname}!", fg=THEME["success"])
        self.load_students_cache()
        self.reload_students_directory()
        self.refresh_dashboard_counters()
        messagebox.showinfo("Enrollment Success", f"Captured {count} face samples for {sname}!\nPlease click 'Re-Train Recognition Model' to activate.")

    def _on_capture_error(self, err):
        self.btn_capture.config(state=tk.NORMAL)
        self.lbl_capture_status.config(text=f"⚠ Capture aborted: {err}", fg=THEME["danger"])

    def trigger_model_training(self):
        admin_pwd = get_admin_password()
        if admin_pwd is None:
            new_pwd = prompt_password_dialog(self.root, title="Set Admin Password",
                                             prompt="Create Master Admin Password:", require_confirm=True)
            if not new_pwd:
                return
            set_admin_password(new_pwd)
            messagebox.showinfo("Security", "Master Admin Password saved successfully!")
        else:
            entered = prompt_password_dialog(self.root, title="Admin Verification",
                                             prompt="Enter Admin Password to Train Model:")
            if entered is None:
                return
            if entered != admin_pwd:
                messagebox.showerror("Access Denied", "Incorrect admin password.")
                return

        self.btn_train.config(state=tk.DISABLED)
        self.lbl_train_stat.config(text="Model Status: Compiling face embeddings...", fg=THEME["warning"])
        self.progress_train.start(10)

        threading.Thread(target=self._worker_train_model, args=(False, None, None), daemon=True).start()

    def _worker_train_model(self, is_auto_train=False, student_name=None, student_id=None):
        if not hasattr(cv2, 'face') or not hasattr(cv2.face, 'LBPHFaceRecognizer_create'):
            self.root.after(0, lambda: self._on_train_error("LBPHFaceRecognizer is not available in OpenCV."))
            return

        faces, ids = self.extract_images_and_labels(TRAINING_IMAGE_DIR)
        if len(faces) == 0 or len(ids) == 0:
            self.root.after(0, lambda: self._on_train_error("No enrollment images found in dataset folder."))
            return

        try:
            recognizer = cv2.face.LBPHFaceRecognizer_create()
            recognizer.train(faces, np.array(ids))
            recognizer.save(TRAINER_FILE)

            self.root.after(0, lambda: self._on_train_success(len(faces), is_auto_train, student_name, student_id))
        except Exception as e:
            self.root.after(0, lambda err=str(e): self._on_train_error(err))

    def extract_images_and_labels(self, path):
        faces = []
        ids = []
        for folder in os.listdir(path):
            folder_path = os.path.join(path, folder)
            if os.path.isdir(folder_path):
                try:
                    sid = int(folder.split('_')[-1])
                except Exception:
                    continue

                for file in os.listdir(folder_path):
                    if file.lower().endswith((".jpg", ".jpeg", ".png")):
                        img_path = os.path.join(folder_path, file)
                        try:
                            pil_img = Image.open(img_path).convert('L')
                            img_np = np.array(pil_img, 'uint8')
                            faces.append(img_np)
                            ids.append(sid)
                        except Exception:
                            continue
        return faces, ids

    def _on_train_success(self, count, is_auto_train=False, student_name=None, student_id=None):
        self.progress_train.stop()
        self.btn_train.config(state=tk.NORMAL)
        self.btn_capture.config(state=tk.NORMAL)

        if hasattr(cv2, 'face') and hasattr(cv2.face, 'LBPHFaceRecognizer_create'):
            try:
                self.recognizer = cv2.face.LBPHFaceRecognizer_create()
                self.recognizer.read(TRAINER_FILE)
            except Exception as e:
                print("Recognizer reload failed:", e)

        self.load_students_cache()
        self.reload_students_directory()
        self.refresh_dashboard_counters()

        self.lbl_train_stat.config(text=f"Model Status: Active ({count} images compiled)", fg=THEME["success"])

        if is_auto_train:
            self.lbl_capture_status.config(text=f"✅ Enrolled & Trained: {student_name} (ID: {student_id})!", fg=THEME["success"])
            messagebox.showinfo(
                "Enrollment & Auto-Train Complete",
                f"Successfully enrolled and trained {student_name} (ID: {student_id})!\n\n"
                f"Model has been updated with {count} face samples and is active immediately."
            )
        else:
            messagebox.showinfo("Training Complete", f"Model trained successfully on {count} face samples!\nAll enrolled students are active.")

    def _on_train_error(self, err):
        self.progress_train.stop()
        self.btn_train.config(state=tk.NORMAL)
        self.btn_capture.config(state=tk.NORMAL)
        self.lbl_train_stat.config(text="Model Status: Training Failed", fg=THEME["danger"])
        messagebox.showerror("Training Error", err)

    def delete_selected_student(self):
        sel = self.tv_students.selection()
        if not sel:
            messagebox.showinfo("Selection", "Please select a student from the table above.")
            return

        item = self.tv_students.item(sel[0])
        student_id = item['values'][1]
        student_name = item['values'][2]

        admin_pwd = get_admin_password()
        if admin_pwd:
            entered = prompt_password_dialog(self.root, prompt=f"Enter Password to Delete {student_name}:")
            if entered != admin_pwd:
                messagebox.showerror("Denied", "Incorrect password.")
                return

        confirm = messagebox.askyesno("Confirm Deletion", f"Permanently delete '{student_name}' (ID: {student_id}) from SQLite and delete their face samples?")
        if not confirm:
            return

        self.db.delete_student(student_id)
        self.db.sync_to_excel()

        for folder in os.listdir(TRAINING_IMAGE_DIR):
            if folder.endswith(f"_{student_id}"):
                try:
                    shutil.rmtree(os.path.join(TRAINING_IMAGE_DIR, folder))
                except Exception:
                    pass

        self.load_students_cache()
        self.reload_students_directory()
        self.refresh_dashboard_counters()

        proceed_retrain = messagebox.askyesno("Re-Train Now?", f"'{student_name}' removed.\n\nWould you like to re-train the model now to remove their facial embeddings?")
        if proceed_retrain:
            self.trigger_model_training()

    def clear_all_enrolled_students(self):
        """Cleans all enrolled students from SQLite, deletes image folders, resets Trainer.yml and Excel."""
        admin_pwd = get_admin_password()
        if admin_pwd:
            p = prompt_password_dialog(self.root, prompt="Enter Admin Password to Clear All Students:")
            if p != admin_pwd:
                messagebox.showerror("Denied", "Incorrect password.")
                return

        confirm = messagebox.askyesno(
            "Confirm Clear All Students",
            "Are you sure you want to permanently delete ALL enrolled student profiles and their face images?\n\n(Attendance history will be preserved)."
        )
        if not confirm:
            return

        try:
            self.db.clear_enrolled_students()

            if os.path.isdir(TRAINING_IMAGE_DIR):
                shutil.rmtree(TRAINING_IMAGE_DIR)
                os.makedirs(TRAINING_IMAGE_DIR, exist_ok=True)

            if os.path.isfile(TRAINER_FILE):
                os.remove(TRAINER_FILE)
            self.recognizer = None

            self.db.sync_to_excel()

            self.load_students_cache()
            self.reload_students_directory()
            self.refresh_dashboard_counters()
            self.lbl_train_stat.config(text="Model Status: Dataset Empty (0 students)", fg=THEME["text_dim"])
            messagebox.showinfo("Success", "All enrolled student profiles, face images, and model embeddings have been cleared.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to clear student records: {e}")

    # ------------------------------------------------------------------
    # Data Reload & Filtering Handlers
    # ------------------------------------------------------------------
    def refresh_dashboard_counters(self):
        total_students = len(self.students_cache)
        self.card_total_students.update_value(f"{total_students} Enrolled")

        today_str = datetime.datetime.now().strftime('%d-%m-%Y')
        records = self.db.get_attendance_records(date_filter=today_str)
        unique_ids = len(set(r['student_id'] for r in records))
        last_entry = "None"
        if records:
            last_entry = f"{records[0]['name']} ({str(records[0]['time']).split()[0]})"

        self.card_today_present.update_value(f"{unique_ids} Present")
        self.card_last_marked.update_value(last_entry)

    def on_category_select_change(self, event=None):
        cat = self.scan_category_var.get()
        self.db.set_setting("active_category", cat)
        if "Office" in cat:
            self.scan_subject_var.set("Office / General")
        elif "Teachers" in cat:
            self.scan_subject_var.set("Faculty Staff")

    def on_subject_select_change(self, event=None):
        sub = self.scan_subject_var.get()
        self.db.set_setting("active_subject", sub)

    def save_shift_schedule(self):
        if not self.verify_admin_access("Configure Shift Times"):
            return
        in_t = self.shift_in_var.get().strip()
        out_t = self.shift_out_var.get().strip()
        grace = self.grace_period_var.get().strip()

        if not in_t or not out_t:
            messagebox.showwarning("Validation", "Shift In and Out times cannot be blank.")
            return

        self.db.set_setting("shift_in_time", in_t)
        self.db.set_setting("shift_out_time", out_t)
        self.db.set_setting("grace_period_mins", grace)
        messagebox.showinfo("Saved", f"Shift schedule saved successfully:\n• Login Shift: {in_t}\n• Logout Shift: {out_t}\n• Grace Window: {grace} mins")

    def reload_subject_listbox(self):
        if hasattr(self, 'lb_subjects'):
            self.lb_subjects.delete(0, tk.END)
            subs = self.db.get_subjects()
            for s in subs:
                self.lb_subjects.insert(tk.END, s)
            if hasattr(self, 'cb_subject'):
                self.cb_subject['values'] = subs
            if hasattr(self, 'cb_hist_sub'):
                self.cb_hist_sub['values'] = ["All Subjects"] + subs

    def on_add_subject_action(self):
        new_name = self.entry_new_sub_var.get().strip()
        if not new_name:
            messagebox.showwarning("Input Required", "Please enter a subject or department name.")
            return
        if not self.verify_admin_access("Add Subject"):
            return
        ok, msg = self.db.add_subject(new_name)
        if ok:
            self.entry_new_sub_var.set("")
            self.reload_subject_listbox()
            messagebox.showinfo("Subject Added", f"Subject '{new_name}' was added successfully.")
        else:
            messagebox.showerror("Error", msg)

    def on_edit_subject_action(self):
        sel_idx = self.lb_subjects.curselection()
        if not sel_idx:
            messagebox.showwarning("Selection Required", "Please select a subject from the list to edit.")
            return
        old_name = self.lb_subjects.get(sel_idx[0])
        new_name = self.entry_new_sub_var.get().strip()
        if not new_name:
            messagebox.showwarning("Input Required", f"Enter the new name for '{old_name}' in the text box above.")
            return
        if not self.verify_admin_access("Modify Subject"):
            return
        ok, msg = self.db.update_subject(old_name, new_name)
        if ok:
            self.entry_new_sub_var.set("")
            self.reload_subject_listbox()
            messagebox.showinfo("Subject Updated", f"Renamed '{old_name}' to '{new_name}'.")
        else:
            messagebox.showerror("Error", msg)

    def on_delete_subject_action(self):
        sel_idx = self.lb_subjects.curselection()
        if not sel_idx:
            messagebox.showwarning("Selection Required", "Please select a subject from the list to remove.")
            return
        sub_name = self.lb_subjects.get(sel_idx[0])
        if not self.verify_admin_access("Remove Subject"):
            return
        if messagebox.askyesno("Confirm Deletion", f"Are you sure you want to remove '{sub_name}' from the subjects list?"):
            self.db.delete_subject(sub_name)
            self.reload_subject_listbox()
            messagebox.showinfo("Subject Removed", f"Subject '{sub_name}' was removed.")

    def verify_admin_access(self, action_title="Admin Verification"):
        admin_pwd = get_admin_password()
        if admin_pwd:
            p = prompt_password_dialog(self.root, title=action_title, prompt="Enter Master Admin Password:")
            if p != admin_pwd:
                messagebox.showerror("Access Denied", "Incorrect administrator password.")
                return False
        return True

    def show_edit_attendance_dialog(self, rec):
        if not self.verify_admin_access("Edit Attendance Record"):
            return

        dlg = tk.Toplevel(self.root)
        dlg.title(f"Edit Attendance Record #{rec['id']}")
        dlg.geometry("480x520")
        dlg.configure(bg=THEME["card_bg"])
        dlg.resizable(False, False)
        dlg.transient(self.root)
        dlg.grab_set()

        lbl_hdr = tk.Label(dlg, text=f"MODIFY ATTENDANCE RECORD #{rec['id']}", font=(THEME["font_main"], 11, "bold"),
                           fg=THEME["text_main"], bg=THEME["card_bg"])
        lbl_hdr.pack(anchor="w", padx=24, pady=(20, 4))

        lbl_sub = tk.Label(dlg, text=f"Student / Employee: {rec['name']} (ID: {rec['student_id']})",
                           font=(THEME["font_main"], 9), fg=THEME["cyan"], bg=THEME["card_bg"])
        lbl_sub.pack(anchor="w", padx=24, pady=(0, 14))

        lbl_date = tk.Label(dlg, text="Date (DD-MM-YYYY):", font=(THEME["font_main"], 9), fg=THEME["text_muted"], bg=THEME["card_bg"])
        lbl_date.pack(anchor="w", padx=24, pady=(4, 2))
        e_date_var = tk.StringVar(value=rec.get('date', ''))
        e_date = tk.Entry(dlg, textvariable=e_date_var, bg=THEME["input_bg"], fg=THEME["text_main"],
                          insertbackground=THEME["cyan"], relief="flat", highlightthickness=1,
                          highlightbackground=THEME["input_border"], font=(THEME["font_main"], 10))
        e_date.pack(fill="x", padx=24, ipady=4)

        lbl_time = tk.Label(dlg, text="Logged Time (e.g. 09:15:00 AM):", font=(THEME["font_main"], 9), fg=THEME["text_muted"], bg=THEME["card_bg"])
        lbl_time.pack(anchor="w", padx=24, pady=(8, 2))
        e_time_var = tk.StringVar(value=rec.get('time', ''))
        e_time = tk.Entry(dlg, textvariable=e_time_var, bg=THEME["input_bg"], fg=THEME["text_main"],
                          insertbackground=THEME["cyan"], relief="flat", highlightthickness=1,
                          highlightbackground=THEME["input_border"], font=(THEME["font_main"], 10))
        e_time.pack(fill="x", padx=24, ipady=4)

        lbl_type = tk.Label(dlg, text="Attendance Type (Login/Logout):", font=(THEME["font_main"], 9), fg=THEME["text_muted"], bg=THEME["card_bg"])
        lbl_type.pack(anchor="w", padx=24, pady=(8, 2))
        e_type_var = tk.StringVar(value=rec.get('log_type', 'Check-In'))
        cb_type = ttk.Combobox(dlg, textvariable=e_type_var, values=["Check-In", "Check-Out"], state="readonly")
        cb_type.pack(fill="x", padx=24, ipady=2)

        lbl_cat = tk.Label(dlg, text="Attendance Context / Purpose:", font=(THEME["font_main"], 9), fg=THEME["text_muted"], bg=THEME["card_bg"])
        lbl_cat.pack(anchor="w", padx=24, pady=(8, 2))
        e_cat_var = tk.StringVar(value=rec.get('category', 'Classroom Lecture'))
        cb_cat = ttk.Combobox(dlg, textvariable=e_cat_var,
                              values=["Classroom Lecture", "Office Attendance", "Teachers / Faculty", "Laboratory Session", "Workshop / Seminar"],
                              state="readonly")
        cb_cat.pack(fill="x", padx=24, ipady=2)

        lbl_subj = tk.Label(dlg, text="Subject / Department:", font=(THEME["font_main"], 9), fg=THEME["text_muted"], bg=THEME["card_bg"])
        lbl_subj.pack(anchor="w", padx=24, pady=(8, 2))
        e_subj_var = tk.StringVar(value=rec.get('subject', 'General'))
        cb_subj = ttk.Combobox(dlg, textvariable=e_subj_var, values=self.db.get_subjects())
        cb_subj.pack(fill="x", padx=24, ipady=2)

        lbl_stat = tk.Label(dlg, text="Status Tag:", font=(THEME["font_main"], 9), fg=THEME["text_muted"], bg=THEME["card_bg"])
        lbl_stat.pack(anchor="w", padx=24, pady=(8, 2))
        e_stat_var = tk.StringVar(value=rec.get('shift_status', rec.get('status', 'On-Time')))
        cb_stat = ttk.Combobox(dlg, textvariable=e_stat_var,
                               values=["On-Time", "Late Login", "Early Departure", "Present", "Excused", "Half-Day"])
        cb_stat.pack(fill="x", padx=24, ipady=2)

        frm_btns = tk.Frame(dlg, bg=THEME["card_bg"])
        frm_btns.pack(fill="x", padx=24, pady=(20, 16))

        def on_save():
            new_d = e_date_var.get().strip()
            new_t = e_time_var.get().strip()
            new_type = e_type_var.get().strip()
            new_cat = e_cat_var.get().strip()
            new_subj = e_subj_var.get().strip()
            new_stat = e_stat_var.get().strip()

            if not new_d or not new_t:
                messagebox.showwarning("Validation", "Date and Time cannot be empty.", parent=dlg)
                return

            self.db.update_attendance_record(rec['id'], new_d, new_t, new_type, new_cat, new_subj, "Present", new_stat)
            threading.Thread(target=self.db.sync_to_excel, daemon=True).start()
            self.reload_attendance_table()
            self.reload_history_table()
            self.refresh_dashboard_counters()
            dlg.destroy()
            messagebox.showinfo("Success", f"Attendance record #{rec['id']} has been updated.")

        btn_save = ModernButton(frm_btns, text="💾 Save Changes", command=on_save, bg=THEME["accent"])
        btn_save.pack(side="right", padx=(8, 0))

        btn_cancel = ModernButton(frm_btns, text="Cancel", command=dlg.destroy, bg=THEME["card_sub"], fg=THEME["text_muted"])
        btn_cancel.pack(side="right")

    def on_edit_today_record(self):
        sel = self.tv_today.selection()
        if not sel:
            messagebox.showwarning("Selection Required", "Please click on a record in Today's Attendance Log to edit.")
            return
        item = self.tv_today.item(sel[0])
        vals = item['values']
        rec = {
            'id': vals[0],
            'student_id': vals[1],
            'name': vals[2],
            'log_type': vals[3],
            'subject': vals[4],
            'date': vals[5],
            'time': vals[6],
            'shift_status': vals[7]
        }
        self.show_edit_attendance_dialog(rec)

    def on_delete_today_record(self):
        sel = self.tv_today.selection()
        if not sel:
            messagebox.showwarning("Selection Required", "Please select a record from the table to delete.")
            return
        if not self.verify_admin_access("Delete Attendance Record"):
            return
        item = self.tv_today.item(sel[0])
        vals = item['values']
        rec_id = vals[0]
        sname = vals[2]
        if messagebox.askyesno("Confirm Deletion", f"Are you sure you want to delete attendance record #{rec_id} for {sname}?"):
            self.db.delete_attendance_record(rec_id)
            threading.Thread(target=self.db.sync_to_excel, daemon=True).start()
            self.reload_attendance_table()
            self.reload_history_table()
            self.refresh_dashboard_counters()
            messagebox.showinfo("Deleted", f"Record #{rec_id} has been deleted.")

    def on_edit_history_record(self):
        sel = self.tv_history.selection()
        if not sel:
            messagebox.showwarning("Selection Required", "Please click on a record in the Historical Archive to edit.")
            return
        item = self.tv_history.item(sel[0])
        vals = item['values']
        rec = {
            'id': vals[0],
            'student_id': vals[1],
            'name': vals[2],
            'log_type': vals[3],
            'category': vals[4],
            'subject': vals[5],
            'date': vals[6],
            'time': vals[7],
            'shift_status': vals[8]
        }
        self.show_edit_attendance_dialog(rec)

    def on_delete_history_record(self):
        sel = self.tv_history.selection()
        if not sel:
            messagebox.showwarning("Selection Required", "Please select a record to delete.")
            return
        if not self.verify_admin_access("Delete Attendance Record"):
            return
        item = self.tv_history.item(sel[0])
        vals = item['values']
        rec_id = vals[0]
        sname = vals[2]
        if messagebox.askyesno("Confirm Deletion", f"Are you sure you want to delete attendance record #{rec_id} for {sname}?"):
            self.db.delete_attendance_record(rec_id)
            threading.Thread(target=self.db.sync_to_excel, daemon=True).start()
            self.reload_history_table()
            self.reload_attendance_table()
            self.refresh_dashboard_counters()
            messagebox.showinfo("Deleted", f"Record #{rec_id} has been deleted.")

    def reload_attendance_table(self):
        for item in self.tv_today.get_children():
            self.tv_today.delete(item)

        today_str = datetime.datetime.now().strftime('%d-%m-%Y')
        records = self.db.get_attendance_records(date_filter=today_str)
        for r in records:
            self.tv_today.insert('', 'end', values=(
                r['id'],
                r['student_id'],
                r['name'],
                r.get('log_type', 'Check-In'),
                r.get('subject', 'General'),
                r['date'],
                r['time'],
                r.get('shift_status', r.get('status', 'Present'))
            ))

    def filter_attendance_table(self):
        q = self.search_today_var.get().strip().lower()
        self.reload_attendance_table()
        if not q:
            return

        for item in list(self.tv_today.get_children()):
            vals = self.tv_today.item(item)['values']
            text_combo = f"{vals[1]} {vals[2]} {vals[3]} {vals[4]}".lower()
            if q not in text_combo:
                self.tv_today.delete(item)

    def reload_students_directory(self):
        for item in self.tv_students.get_children():
            self.tv_students.delete(item)

        students = self.db.get_all_students()
        for s in students:
            sid = s['student_id']
            sname = s['name']
            serial = s['serial_no']

            img_count = 0
            for folder in os.listdir(TRAINING_IMAGE_DIR):
                if folder.endswith(f"_{sid}"):
                    fp = os.path.join(TRAINING_IMAGE_DIR, folder)
                    if os.path.isdir(fp):
                        img_count = len([f for f in os.listdir(fp) if f.lower().endswith(('.jpg', '.png'))])
                    break

            self.tv_students.insert('', 'end', values=(serial, sid, sname, f"{img_count} imgs"))

    def filter_students_directory(self):
        q = self.search_student_var.get().strip().lower()
        self.reload_students_directory()
        if not q:
            return

        for item in list(self.tv_students.get_children()):
            vals = self.tv_students.item(item)['values']
            text_combo = f"{vals[1]} {vals[2]}".lower()
            if q not in text_combo:
                self.tv_students.delete(item)

    def on_history_filter_change(self, event=None):
        mode = self.history_filter_mode.get()
        if mode == "Specific Date...":
            custom_date = filedialog.askstring("Date Filter", "Enter date in format DD-MM-YYYY (e.g. 27-08-2026):")
            if custom_date:
                self.reload_history_table(filter_date=custom_date.strip())
            else:
                self.history_filter_mode.set("All Records")
                self.reload_history_table()
        elif mode == "Today Only":
            self.reload_history_table(filter_date=datetime.datetime.now().strftime('%d-%m-%Y'))
        else:
            self.reload_history_table()

    def reload_history_table(self, filter_date=None):
        for item in self.tv_history.get_children():
            self.tv_history.delete(item)

        cat_f = getattr(self, 'history_cat_filter', None)
        sub_f = getattr(self, 'history_sub_filter', None)
        cat_val = cat_f.get() if cat_f else None
        sub_val = sub_f.get() if sub_f else None

        records = self.db.get_attendance_records(
            date_filter=filter_date,
            category_filter=cat_val,
            subject_filter=sub_val
        )
        for r in records:
            self.tv_history.insert('', 'end', values=(
                r['id'],
                r['student_id'],
                r['name'],
                r.get('log_type', 'Check-In'),
                r.get('category', 'Classroom Lecture'),
                r.get('subject', 'General'),
                r['date'],
                r['time'],
                r.get('shift_status', r.get('status', 'Present'))
            ))

    def filter_history_table(self):
        q = self.history_search_var.get().strip().lower()
        self.reload_history_table()
        if not q:
            return

        for item in list(self.tv_history.get_children()):
            vals = self.tv_history.item(item)['values']
            text_combo = f"{vals[1]} {vals[2]} {vals[3]} {vals[4]} {vals[5]} {vals[6]}".lower()
            if q not in text_combo:
                self.tv_history.delete(item)

    # ------------------------------------------------------------------
    # TAB 3 Operations: Export & Email Dispatch
    # ------------------------------------------------------------------
    def manual_sync_to_excel(self):
        success = self.db.sync_to_excel()
        if success:
            messagebox.showinfo("Sync Successful", "SQLite database successfully synced to StudentDetails.xlsx and Attendance.xlsx!")
        else:
            messagebox.showwarning("Sync Warning", "Could not sync to Excel. Please ensure files are not locked by Microsoft Excel.")

    def export_to_excel(self):
        records = self.db.get_attendance_records()
        if not records:
            messagebox.showinfo("No Data", "No attendance records found to export.")
            return

        dest = filedialog.asksaveasfilename(defaultextension=".xlsx",
                                            filetypes=[("Excel Workbook", "*.xlsx")],
                                            initialfile=f"Attendance_Export_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx")
        if not dest:
            return

        try:
            df = pd.DataFrame([{
                'S.No': r['id'],
                'ID': r['student_id'],
                'Name': r['name'],
                'Type': r.get('log_type', 'Check-In'),
                'Category': r.get('category', 'Classroom Lecture'),
                'Subject': r.get('subject', 'General'),
                'Date': r['date'],
                'Time': r['time'],
                'Status': r.get('status', 'Present'),
                'Shift Status': r.get('shift_status', 'On-Time')
            } for r in reversed(records)])
            df.to_excel(dest, index=False)
            autofit_excel(dest)
            messagebox.showinfo("Export Successful", f"Attendance records exported to:\n{dest}")
        except Exception as e:
            messagebox.showerror("Export Error", f"Failed to export Excel file: {e}")

    def export_to_csv(self):
        records = self.db.get_attendance_records()
        if not records:
            messagebox.showinfo("No Data", "No attendance records found to export.")
            return

        dest = filedialog.asksaveasfilename(defaultextension=".csv",
                                            filetypes=[("CSV File", "*.csv")],
                                            initialfile=f"Attendance_Export_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
        if not dest:
            return

        try:
            df = pd.DataFrame([{
                'S.No': r['id'],
                'ID': r['student_id'],
                'Name': r['name'],
                'Type': r.get('log_type', 'Check-In'),
                'Category': r.get('category', 'Classroom Lecture'),
                'Subject': r.get('subject', 'General'),
                'Date': r['date'],
                'Time': r['time'],
                'Status': r.get('status', 'Present'),
                'Shift Status': r.get('shift_status', 'On-Time')
            } for r in reversed(records)])
            df.to_csv(dest, index=False)
            messagebox.showinfo("Export Successful", f"Attendance records exported to CSV:\n{dest}")
        except Exception as e:
            messagebox.showerror("Export Error", f"Failed to export CSV: {e}")

    def dispatch_email_report(self):
        recip = self.email_recip_var.get().strip()
        domain = self.email_domain_var.get().strip()

        if not recip:
            messagebox.showwarning("Validation", "Please enter recipient email address.")
            return

        if "@" not in recip and not domain.startswith("Custom"):
            recip = recip + domain

        dlg = tk.Toplevel(self.root)
        dlg.title("Sender SMTP Configuration")
        dlg.geometry("420x260")
        dlg.configure(bg=THEME["card_bg"])
        dlg.transient(self.root)
        dlg.grab_set()

        lbl_s_mail = tk.Label(dlg, text="Sender Email:", bg=THEME["card_bg"], fg=THEME["text_main"], font=(THEME["font_main"], 9, "bold"))
        lbl_s_mail.pack(anchor="w", padx=20, pady=(16, 2))

        s_email_var = tk.StringVar()
        e_s_mail = tk.Entry(dlg, textvariable=s_email_var, bg=THEME["input_bg"], fg=THEME["text_main"],
                            insertbackground=THEME["cyan"], relief="flat", width=34)
        e_s_mail.pack(padx=20, fill="x")

        lbl_s_pwd = tk.Label(dlg, text="Sender App Password:", bg=THEME["card_bg"], fg=THEME["text_main"], font=(THEME["font_main"], 9, "bold"))
        lbl_s_pwd.pack(anchor="w", padx=20, pady=(10, 2))

        s_pwd_var = tk.StringVar()
        e_s_pwd = tk.Entry(dlg, textvariable=s_pwd_var, show="•", bg=THEME["input_bg"], fg=THEME["text_main"],
                           insertbackground=THEME["cyan"], relief="flat", width=34)
        e_s_pwd.pack(padx=20, fill="x")

        def on_send():
            semail = s_email_var.get().strip()
            spwd = s_pwd_var.get().strip()
            if not semail or not spwd:
                messagebox.showwarning("Incomplete", "Both sender email and password are required.", parent=dlg)
                return
            dlg.destroy()
            threading.Thread(target=self._worker_send_email, args=(semail, spwd, recip), daemon=True).start()

        btn_commit = ModernButton(dlg, text="Send Now", command=on_send, bg=THEME["accent"])
        btn_commit.pack(side="right", padx=20, pady=20)

    def _worker_send_email(self, sender, password, recipient):
        self.db.sync_to_excel()
        if not os.path.isfile(ATTENDANCE_FILE):
            self.root.after(0, lambda: messagebox.showerror("File Error", "Attendance.xlsx file not found."))
            return

        try:
            msg = MIMEMultipart()
            msg['From'] = sender
            msg['To'] = recipient
            msg['Subject'] = f"Attendance Report - {datetime.datetime.now().strftime('%d-%m-%Y')}"

            body = f"Hello,\n\nPlease find attached the latest attendance tracking report generated on {datetime.datetime.now().strftime('%d-%m-%Y %I:%M %p')}.\n\nBest regards,\nAttendance Studio Automated Dispatcher"
            msg.attach(MIMEText(body, 'plain'))

            with open(ATTENDANCE_FILE, "rb") as attachment:
                part = MIMEBase('application', 'vnd.openxmlformats-officedocument.spreadsheetml.sheet')
                part.set_payload(attachment.read())
                encoders.encode_base64(part)
                part.add_header('Content-Disposition', f"attachment; filename={os.path.basename(ATTENDANCE_FILE)}")
                msg.attach(part)

            server = smtplib.SMTP('smtp.gmail.com', 587)
            server.starttls()
            server.login(sender, password)
            server.sendmail(sender, recipient, msg.as_string())
            server.quit()

            self.root.after(0, lambda: messagebox.showinfo("Email Sent", f"Attendance report delivered successfully to:\n{recipient}"))
        except Exception as e:
            self.root.after(0, lambda err=str(e): messagebox.showerror("Delivery Error", f"Failed to send email:\n{err}"))

    # ------------------------------------------------------------------
    # TAB 4 Operations: Settings, Password & Backups
    # ------------------------------------------------------------------
    def change_admin_password(self):
        admin_pwd = get_admin_password()
        if admin_pwd:
            old = prompt_password_dialog(self.root, title="Verify Existing Password", prompt="Enter Current Admin Password:")
            if old != admin_pwd:
                messagebox.showerror("Denied", "Incorrect old password.")
                return

        new_p = prompt_password_dialog(self.root, title="New Admin Password", prompt="Enter New Password:", require_confirm=True)
        if new_p:
            set_admin_password(new_p)
            messagebox.showinfo("Success", "Master admin password updated successfully!")

    def create_data_backup(self):
        dest = filedialog.asksaveasfilename(defaultextension=".zip",
                                            filetypes=[("Zip Archive", "*.zip")],
                                            initialfile=f"Attendance_Backup_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.zip")
        if not dest:
            return

        try:
            self.db.sync_to_excel()
            with zipfile.ZipFile(dest, 'w', zipfile.ZIP_DEFLATED) as zf:
                for f in [DB_FILE, STUDENT_DETAILS_FILE, ATTENDANCE_FILE, TRAINER_FILE, PASSWORD_FILE]:
                    if os.path.isfile(f):
                        zf.write(f, os.path.relpath(f, BASE_DIR))
                for root_dir, _, files in os.walk(TRAINING_IMAGE_DIR):
                    for file in files:
                        p = os.path.join(root_dir, file)
                        zf.write(p, os.path.relpath(p, BASE_DIR))
            messagebox.showinfo("Backup Created", f"Full database and images archive created successfully:\n{dest}")
        except Exception as e:
            messagebox.showerror("Backup Failed", f"Could not create backup: {e}")

    def danger_clear_attendance(self):
        admin_pwd = get_admin_password()
        if admin_pwd:
            p = prompt_password_dialog(self.root, prompt="Enter Admin Password to Clear Attendance:")
            if p != admin_pwd:
                messagebox.showerror("Denied", "Incorrect password.")
                return

        if not messagebox.askyesno("Confirm Reset", "Are you sure you want to delete ALL attendance records? This cannot be undone."):
            return

        try:
            self.db.clear_attendance()
            self.db.sync_to_excel()
            self.reload_attendance_table()
            self.reload_history_table()
            self.refresh_dashboard_counters()
            messagebox.showinfo("Reset Complete", "Attendance log has been cleared.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to reset attendance log: {e}")

    def danger_clear_all_data(self):
        admin_pwd = get_admin_password()
        if admin_pwd:
            p = prompt_password_dialog(self.root, prompt="Enter Admin Password to Wipe Dataset:")
            if p != admin_pwd:
                messagebox.showerror("Denied", "Incorrect password.")
                return

        if not messagebox.askyesno("CRITICAL WARNING", "This will delete all enrolled students, all captured training face images, and all attendance logs. Continue?"):
            return

        try:
            self.db.clear_all()
            if os.path.isdir(TRAINING_IMAGE_DIR):
                shutil.rmtree(TRAINING_IMAGE_DIR)
                os.makedirs(TRAINING_IMAGE_DIR, exist_ok=True)
            if os.path.isfile(TRAINER_FILE):
                os.remove(TRAINER_FILE)

            self.db.sync_to_excel()

            self.load_models()
            self.reload_attendance_table()
            self.reload_students_directory()
            self.reload_history_table()
            self.refresh_dashboard_counters()
            messagebox.showinfo("Wipe Complete", "System dataset, SQLite database, and student profiles have been reset.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to reset dataset: {e}")

    # ------------------------------------------------------------------
    # Clock & Graceful Exit Handlers
    # ------------------------------------------------------------------
    def start_clock_ticker(self):
        now = datetime.datetime.now()
        self.lbl_live_date.config(text=now.strftime("%A, %d %B %Y"))
        self.lbl_live_clock.config(text=now.strftime("%I:%M:%S %p"))
        self.root.after(1000, self.start_clock_ticker)

    def on_close_application(self):
        self.camera_active = False
        if self.camera_device:
            try:
                self.camera_device.release()
            except Exception:
                pass
        try:
            cv2.destroyAllWindows()
        except Exception:
            pass
        self.root.destroy()


# ----------------------------------------------------------------------
# Application Entry Point
# ----------------------------------------------------------------------
def main():
    root = tk.Tk()
    app = AttendanceStudioApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
