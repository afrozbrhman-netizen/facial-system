import sqlite3
import threading
import datetime
from backend.core.config import Config
from backend.core.security import hash_password

class Database:
    """Thread-safe SQLite connection and relational schema manager."""
    def __init__(self, db_path=Config.DB_PATH):
        self.db_path = db_path
        self.lock = threading.Lock()
        self.init_db()

    def get_connection(self):
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def init_db(self):
        with self.lock:
            with self.get_connection() as conn:
                cur = conn.cursor()

                # 1. Users table (Role-Based Access Control)
                cur.execute('''
                    CREATE TABLE IF NOT EXISTS users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        username TEXT UNIQUE NOT NULL,
                        email TEXT UNIQUE,
                        password_hash TEXT NOT NULL,
                        role TEXT NOT NULL CHECK(role IN ('admin', 'teacher_hr', 'student_employee')),
                        employee_id INTEGER,
                        status TEXT DEFAULT 'active',
                        created_at TEXT NOT NULL,
                        last_login TEXT
                    )
                ''')

                # 2. Departments table
                cur.execute('''
                    CREATE TABLE IF NOT EXISTS departments (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT UNIQUE NOT NULL,
                        code TEXT UNIQUE,
                        created_at TEXT NOT NULL
                    )
                ''')

                # 3. Employees / Students Profile table
                cur.execute('''
                    CREATE TABLE IF NOT EXISTS employees (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        employee_code TEXT UNIQUE NOT NULL,
                        full_name TEXT NOT NULL,
                        email TEXT,
                        phone TEXT,
                        department_id INTEGER,
                        designation_class TEXT DEFAULT 'Student',
                        joining_date TEXT,
                        profile_photo_path TEXT,
                        status TEXT DEFAULT 'active',
                        created_at TEXT NOT NULL,
                        FOREIGN KEY (department_id) REFERENCES departments(id) ON DELETE SET NULL
                    )
                ''')

                # 4. Face Biometric Embeddings (128-d vector storage)
                cur.execute('''
                    CREATE TABLE IF NOT EXISTS face_embeddings (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        employee_id INTEGER NOT NULL,
                        embedding_json TEXT NOT NULL,
                        photo_path TEXT,
                        quality_score REAL DEFAULT 1.0,
                        created_at TEXT NOT NULL,
                        FOREIGN KEY (employee_id) REFERENCES employees(id) ON DELETE CASCADE
                    )
                ''')

                # 5. Configurable Attendance Rules & Thresholds
                cur.execute('''
                    CREATE TABLE IF NOT EXISTS attendance_rules (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        rule_name TEXT DEFAULT 'Standard Shift',
                        work_start_time TEXT DEFAULT '09:00 AM',
                        late_threshold_time TEXT DEFAULT '09:15 AM',
                        work_end_time TEXT DEFAULT '05:00 PM',
                        min_attendance_percent REAL DEFAULT 75.0,
                        is_active INTEGER DEFAULT 1,
                        updated_at TEXT NOT NULL
                    )
                ''')

                # 6. Leave Records
                cur.execute('''
                    CREATE TABLE IF NOT EXISTS leaves (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        employee_id INTEGER NOT NULL,
                        start_date TEXT NOT NULL,
                        end_date TEXT NOT NULL,
                        leave_type TEXT DEFAULT 'Casual',
                        reason TEXT,
                        status TEXT DEFAULT 'Approved' CHECK(status IN ('Pending', 'Approved', 'Rejected')),
                        approved_by TEXT,
                        created_at TEXT NOT NULL,
                        FOREIGN KEY (employee_id) REFERENCES employees(id) ON DELETE CASCADE
                    )
                ''')

                # 7. Holidays
                cur.execute('''
                    CREATE TABLE IF NOT EXISTS holidays (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        holiday_date TEXT UNIQUE NOT NULL,
                        name TEXT NOT NULL,
                        description TEXT
                    )
                ''')

                # 8. Audit Activity Logs
                cur.execute('''
                    CREATE TABLE IF NOT EXISTS audit_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER,
                        username TEXT,
                        action TEXT NOT NULL,
                        entity_type TEXT,
                        entity_id TEXT,
                        details TEXT,
                        ip_address TEXT,
                        timestamp TEXT NOT NULL
                    )
                ''')

                # 9. System Notifications
                cur.execute('''
                    CREATE TABLE IF NOT EXISTS notifications (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER,
                        title TEXT NOT NULL,
                        message TEXT NOT NULL,
                        type TEXT DEFAULT 'info' CHECK(type IN ('info', 'warning', 'success', 'danger')),
                        is_read INTEGER DEFAULT 0,
                        created_at TEXT NOT NULL
                    )
                ''')

                # Ensure attendance table has check_in_time, check_out_time, duration_minutes
                cur.execute("PRAGMA table_info(attendance)")
                att_cols = [c[1] for c in cur.fetchall()]
                if 'check_in_time' not in att_cols:
                    cur.execute("ALTER TABLE attendance ADD COLUMN check_in_time TEXT")
                if 'check_out_time' not in att_cols:
                    cur.execute("ALTER TABLE attendance ADD COLUMN check_out_time TEXT")
                if 'duration_minutes' not in att_cols:
                    cur.execute("ALTER TABLE attendance ADD COLUMN duration_minutes INTEGER DEFAULT 0")
                if 'confidence_score' not in att_cols:
                    cur.execute("ALTER TABLE attendance ADD COLUMN confidence_score REAL DEFAULT 0.0")
                if 'verified_by' not in att_cols:
                    cur.execute("ALTER TABLE attendance ADD COLUMN verified_by TEXT DEFAULT 'face'")

                # Create indexes for high-throughput queries
                cur.execute("CREATE INDEX IF NOT EXISTS idx_att_date ON attendance(date);")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_att_student ON attendance(student_id);")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_emp_code ON employees(employee_code);")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_audit_time ON audit_logs(timestamp);")

                # Seed initial departments if empty
                cur.execute("SELECT COUNT(*) FROM departments")
                if cur.fetchone()[0] == 0:
                    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    depts = [
                        ("Computer Science", "CS"),
                        ("Information Technology", "IT"),
                        ("Electronics & Comm.", "ECE"),
                        ("Human Resources", "HR"),
                        ("Administration", "ADMIN")
                    ]
                    for d_name, d_code in depts:
                        cur.execute("INSERT OR IGNORE INTO departments (name, code, created_at) VALUES (?, ?, ?)",
                                    (d_name, d_code, now))

                # Seed initial attendance rules if empty
                cur.execute("SELECT COUNT(*) FROM attendance_rules")
                if cur.fetchone()[0] == 0:
                    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    cur.execute('''
                        INSERT INTO attendance_rules 
                        (rule_name, work_start_time, late_threshold_time, work_end_time, min_attendance_percent, is_active, updated_at)
                        VALUES ('Default Standard Policy', '09:00 AM', '09:15 AM', '05:00 PM', 75.0, 1, ?)
                    ''', (now,))

                # Seed initial administrative and faculty accounts
                now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                users_to_seed = [
                    ("admin", "admin@attendance.studio", "Admin@123", "admin", None),
                    ("teacher", "teacher@attendance.studio", "Teacher@123", "teacher_hr", None),
                    ("misba", "misba@attendance.studio", "Misba@123", "teacher_hr", None),
                    ("EMP001", "student@attendance.studio", "Student@123", "student_employee", 1)
                ]
                for u, email, pwd, role, eid in users_to_seed:
                    pwd_h = hash_password(pwd)
                    cur.execute('''
                        INSERT OR IGNORE INTO users (username, email, password_hash, role, employee_id, status, created_at)
                        VALUES (?, ?, ?, ?, ?, 'active', ?)
                    ''', (u, email, pwd_h, role, eid, now))

                # Auto-sync existing 'students' table to 'employees' table so existing students appear seamlessly
                cur.execute("SELECT serial_no, student_id, name, registered_at FROM students")
                existing_students = cur.fetchall()
                for s in existing_students:
                    sid_str = str(s["student_id"])
                    sname = str(s["name"])
                    reg_at = s["registered_at"] or datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    cur.execute('''
                        INSERT INTO employees (employee_code, full_name, email, department_id, designation_class, joining_date, created_at)
                        VALUES (?, ?, ?, 1, 'Enrolled Student', ?, ?)
                        ON CONFLICT(employee_code) DO NOTHING
                    ''', (sid_str, sname, f"{sid_str}@student.local", reg_at, reg_at))

                    # Ensure each student has their own unique user login account & distinct password
                    pwd_h = hash_password(f"{sid_str}@123")
                    cur.execute('''
                        INSERT INTO users (username, email, password_hash, role, employee_id, status, created_at)
                        VALUES (?, ?, ?, 'student_employee', (SELECT id FROM employees WHERE employee_code = ?), 'active', ?)
                        ON CONFLICT(username) DO NOTHING
                    ''', (sid_str, f"{sid_str}@student.local", pwd_h, sid_str, reg_at))

                conn.commit()

# Global database instance
db = Database()
