import datetime
from backend.models.database import db
from backend.services.audit_service import audit_service
from backend.services.biometric_service import biometric_service

class EmployeeService:
    """Enterprise Employee / Student Directory and Biometric Profile Management."""

    @staticmethod
    def list_employees(search: str = None, department_id: int = None, status: str = None, limit: int = 100, offset: int = 0) -> dict:
        """Lists employees/students with face registration status and department details."""
        with db.get_connection() as conn:
            cur = conn.cursor()
            query = """
                SELECT e.*, d.name as department_name,
                       (SELECT COUNT(*) FROM face_embeddings fe WHERE fe.employee_id = e.id) as face_samples_count
                FROM employees e
                LEFT JOIN departments d ON e.department_id = d.id
                WHERE 1=1
            """
            params = []

            if status:
                query += " AND e.status = ?"
                params.append(status)
            if department_id:
                query += " AND e.department_id = ?"
                params.append(department_id)
            if search:
                query += " AND (e.full_name LIKE ? OR e.employee_code LIKE ? OR e.email LIKE ?)"
                term = f"%{search}%"
                params.extend([term, term, term])

            count_query = f"SELECT COUNT(*) FROM ({query})"
            cur.execute(count_query, params)
            total_count = cur.fetchone()[0]

            query += " ORDER BY e.id DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])

            cur.execute(query, params)
            employees = [dict(r) for r in cur.fetchall()]

            return {
                "employees": employees,
                "total": total_count,
                "limit": limit,
                "offset": offset
            }

    @staticmethod
    def get_employee_by_id(emp_id: int) -> dict | None:
        """Fetches full employee record with statistics."""
        with db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT e.*, d.name as department_name,
                       (SELECT COUNT(*) FROM face_embeddings fe WHERE fe.employee_id = e.id) as face_samples_count
                FROM employees e
                LEFT JOIN departments d ON e.department_id = d.id
                WHERE e.id = ?
            """, (emp_id,))
            row = cur.fetchone()
            if not row:
                return None
            return dict(row)

    @staticmethod
    def create_employee(data: dict, actor: str = "Admin") -> dict:
        """Registers a new employee/student and syncs with legacy students table."""
        code = str(data.get("employee_code", "")).strip()
        name = str(data.get("full_name", "")).strip()
        email = data.get("email", "").strip() or None
        phone = data.get("phone", "").strip() or None
        dept_id = data.get("department_id")
        designation = data.get("designation_class", "Student")
        joining_date = data.get("joining_date") or datetime.date.today().isoformat()
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if not code or not name:
            return {"success": False, "message": "Employee Code and Full Name are required."}

        try:
            with db.get_connection() as conn:
                cur = conn.cursor()

                # Check unique code
                cur.execute("SELECT id FROM employees WHERE employee_code = ?", (code,))
                if cur.fetchone():
                    return {"success": False, "message": f"Employee/Student Code '{code}' already exists."}

                cur.execute("""
                    INSERT INTO employees (
                        employee_code, full_name, email, phone, department_id,
                        designation_class, joining_date, status, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?)
                """, (code, name, email, phone, dept_id, designation, joining_date, now_str))
                emp_id = cur.lastrowid

                # Synchronize to legacy 'students' table for Tkinter main.py compatibility
                try:
                    cur.execute("""
                        INSERT OR IGNORE INTO students (student_id, name, registered_at)
                        VALUES (?, ?, ?)
                    """, (code, name, now_str))
                except Exception as sync_err:
                    print(f"[SyncWarning] Legacy students sync: {sync_err}")

                # Create dedicated login account with individual password for this student
                from backend.core.security import hash_password
                student_pwd = str(data.get("password", "")).strip() or f"{code}@123"
                pwd_hash = hash_password(student_pwd)
                cur.execute("""
                    INSERT INTO users (username, email, password_hash, role, employee_id, status, created_at)
                    VALUES (?, ?, ?, 'student_employee', ?, 'active', ?)
                    ON CONFLICT(username) DO UPDATE SET 
                        password_hash = excluded.password_hash,
                        employee_id = excluded.employee_id,
                        email = COALESCE(excluded.email, users.email)
                """, (code, email, pwd_hash, emp_id, now_str))

                conn.commit()

            audit_service.log_action("EMPLOYEE_CREATED", username=actor, entity_type="employee", entity_id=str(emp_id), details=f"Registered {name} ({code}) with dedicated account")
            return {
                "success": True,
                "message": f"Successfully enrolled {name}. Student Login Password: {student_pwd}",
                "employee_id": emp_id,
                "default_password": student_pwd
            }
        except Exception as e:
            return {"success": False, "message": f"Failed to register employee: {str(e)}"}

    @staticmethod
    def set_employee_password(emp_id: int, new_password: str, actor: str = "Admin") -> dict:
        """Sets or resets an individual password for an employee/student account."""
        if not new_password or len(new_password) < 4:
            return {"success": False, "message": "Password must be at least 4 characters long."}

        from backend.core.security import hash_password
        pwd_hash = hash_password(new_password)
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT id, employee_code, full_name, email FROM employees WHERE id = ?", (emp_id,))
            emp = cur.fetchone()
            if not emp:
                return {"success": False, "message": "Employee not found."}

            code = emp["employee_code"]
            email = emp["email"]

            # Update existing user or create one if not yet present
            cur.execute("SELECT id FROM users WHERE employee_id = ? OR username = ?", (emp_id, code))
            existing_user = cur.fetchone()

            if existing_user:
                cur.execute("UPDATE users SET password_hash = ? WHERE id = ?", (pwd_hash, existing_user["id"]))
            else:
                cur.execute("""
                    INSERT INTO users (username, email, password_hash, role, employee_id, status, created_at)
                    VALUES (?, ?, ?, 'student_employee', ?, 'active', ?)
                """, (code, email, pwd_hash, emp_id, now_str))

            conn.commit()

        audit_service.log_action("PASSWORD_RESET", username=actor, entity_type="employee", entity_id=str(emp_id), details=f"Password updated for {emp['full_name']} ({code})")
        return {"success": True, "message": f"Password for {emp['full_name']} ({code}) has been updated successfully."}

    @staticmethod
    def sync_all_student_accounts():
        """Ensures every registered student/employee has their own distinct user login account."""
        from backend.core.security import hash_password
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT id, employee_code, full_name, email FROM employees")
            all_emps = cur.fetchall()

            for emp in all_emps:
                code = str(emp["employee_code"])
                eid = emp["id"]
                email = emp["email"]
                # Check if user already exists
                cur.execute("SELECT id FROM users WHERE employee_id = ? OR username = ?", (eid, code))
                if not cur.fetchone():
                    # Check if email is already taken by another user
                    if email:
                        cur.execute("SELECT id FROM users WHERE email = ?", (email,))
                        if cur.fetchone():
                            email = f"{code}@student.local"
                    else:
                        email = f"{code}@student.local"

                    pwd = f"{code}@123"
                    pwd_hash = hash_password(pwd)
                    cur.execute("""
                        INSERT INTO users (username, email, password_hash, role, employee_id, status, created_at)
                        VALUES (?, ?, ?, 'student_employee', ?, 'active', ?)
                    """, (code, email, pwd_hash, eid, now_str))
            conn.commit()


    @staticmethod
    def update_employee(emp_id: int, data: dict, actor: str = "Admin") -> dict:
        """Updates employee profile."""
        with db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM employees WHERE id = ?", (emp_id,))
            existing = cur.fetchone()
            if not existing:
                return {"success": False, "message": "Employee not found."}

            cur.execute("""
                UPDATE employees
                SET full_name = ?, email = ?, phone = ?, department_id = ?,
                    designation_class = ?, status = ?
                WHERE id = ?
            """, (
                data.get("full_name", existing["full_name"]),
                data.get("email", existing["email"]),
                data.get("phone", existing["phone"]),
                data.get("department_id", existing["department_id"]),
                data.get("designation_class", existing["designation_class"]),
                data.get("status", existing["status"]),
                emp_id
            ))
            conn.commit()

        audit_service.log_action("EMPLOYEE_UPDATED", username=actor, entity_type="employee", entity_id=str(emp_id), details=f"Updated employee ID {emp_id}")
        return {"success": True, "message": "Employee profile updated successfully."}

    @staticmethod
    def delete_employee(emp_id: int, actor: str = "Admin") -> dict:
        """Deletes an employee and associated biometric embeddings."""
        with db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT full_name, employee_code FROM employees WHERE id = ?", (emp_id,))
            emp = cur.fetchone()
            if not emp:
                return {"success": False, "message": "Employee not found."}

            # Delete face embeddings and employee
            cur.execute("DELETE FROM face_embeddings WHERE employee_id = ?", (emp_id,))
            cur.execute("DELETE FROM employees WHERE id = ?", (emp_id,))
            conn.commit()

        audit_service.log_action("EMPLOYEE_DELETED", username=actor, entity_type="employee", entity_id=str(emp_id), details=f"Deleted {emp['full_name']} ({emp['employee_code']})")
        return {"success": True, "message": "Employee record and biometrics deleted successfully."}

    @staticmethod
    def get_employee_attendance_stats(emp_id: int) -> dict:
        """Calculates attendance stats for an individual profile."""
        with db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT employee_code, full_name FROM employees WHERE id = ?", (emp_id,))
            emp = cur.fetchone()
            if not emp:
                return {"error": "Employee not found"}

            code = emp["employee_code"]

            # Total sessions recorded in attendance table
            cur.execute("SELECT COUNT(DISTINCT date) FROM attendance")
            total_sessions = cur.fetchone()[0] or 0

            # Present days
            cur.execute("SELECT COUNT(DISTINCT date) FROM attendance WHERE student_id = ? AND status = 'Present'", (code,))
            present_days = cur.fetchone()[0] or 0

            # Late days
            cur.execute("SELECT COUNT(*) FROM attendance WHERE student_id = ? AND shift_status = 'Late'", (code,))
            late_days = cur.fetchone()[0] or 0

            pct = round((present_days / total_sessions * 100), 1) if total_sessions > 0 else 0.0

            return {
                "employee_id": emp_id,
                "full_name": emp["full_name"],
                "employee_code": code,
                "total_sessions": total_sessions,
                "present_days": present_days,
                "late_days": late_days,
                "attendance_percentage": pct
            }

employee_service = EmployeeService()
