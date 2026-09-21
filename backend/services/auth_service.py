import datetime
from backend.models.database import db
from backend.core.security import hash_password, verify_password, create_token
from backend.services.audit_service import audit_service

class AuthService:
    """Authentication and User Lifecycle Management with RBAC."""

    @staticmethod
    def authenticate(username_or_email: str, password: str, ip_address: str = None) -> dict:
        """Authenticates credentials, updates last_login, logs audit event, and returns JWT."""
        if not username_or_email or not password:
            return {"success": False, "message": "Username/Email and password are required."}

        with db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT u.id, u.username, u.email, u.password_hash, u.role, u.employee_id, u.status,
                       e.full_name, e.employee_code, e.designation_class, e.profile_photo_path
                FROM users u
                LEFT JOIN employees e ON u.employee_id = e.id
                WHERE (u.username = ? OR u.email = ?)
            """, (username_or_email.strip(), username_or_email.strip()))
            user = cur.fetchone()

        if not user:
            audit_service.log_action("LOGIN_FAILED", details=f"Unknown user: {username_or_email}", ip_address=ip_address)
            return {"success": False, "message": "Invalid username or password."}

        if user["status"] != "active":
            return {"success": False, "message": "Account is disabled. Please contact administrator."}

        if not verify_password(password, user["password_hash"]):
            audit_service.log_action("LOGIN_FAILED", user_id=user["id"], username=user["username"], details="Incorrect password", ip_address=ip_address)
            return {"success": False, "message": "Invalid username or password."}

        # Update last login
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("UPDATE users SET last_login = ? WHERE id = ?", (now_str, user["id"]))
            conn.commit()

        # Token payload
        payload = {
            "id": user["id"],
            "username": user["username"],
            "email": user["email"],
            "role": user["role"],
            "employee_id": user["employee_id"],
            "full_name": user["full_name"] or user["username"]
        }
        token = create_token(payload)

        # Audit log
        audit_service.log_action("LOGIN_SUCCESS", user_id=user["id"], username=user["username"], details="Successful sign-in", ip_address=ip_address)

        return {
            "success": True,
            "message": "Login successful.",
            "token": token,
            "user": {
                "id": user["id"],
                "username": user["username"],
                "email": user["email"],
                "role": user["role"],
                "employee_id": user["employee_id"],
                "employee_code": user["employee_code"],
                "full_name": user["full_name"] or user["username"],
                "designation": user["designation_class"],
                "profile_photo_path": user["profile_photo_path"]
            }
        }

    @staticmethod
    def get_user_profile(user_id: int) -> dict | None:
        """Fetches full user profile and associated employee records."""
        with db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT u.id, u.username, u.email, u.role, u.employee_id, u.status, u.created_at, u.last_login,
                       e.full_name, e.employee_code, e.phone, e.designation_class, e.joining_date,
                       e.profile_photo_path, d.name as department_name
                FROM users u
                LEFT JOIN employees e ON u.employee_id = e.id
                LEFT JOIN departments d ON e.department_id = d.id
                WHERE u.id = ?
            """, (user_id,))
            row = cur.fetchone()
            if not row:
                return None
            return dict(row)

    @staticmethod
    def change_password(user_id: int, current_password: str, new_password: str) -> dict:
        """Changes user password after checking current password."""
        if not new_password or len(new_password) < 6:
            return {"success": False, "message": "New password must be at least 6 characters long."}

        with db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT password_hash, username FROM users WHERE id = ?", (user_id,))
            user = cur.fetchone()
            if not user or not verify_password(current_password, user["password_hash"]):
                return {"success": False, "message": "Current password is incorrect."}

            new_hash = hash_password(new_password)
            cur.execute("UPDATE users SET password_hash = ? WHERE id = ?", (new_hash, user_id))
            conn.commit()

        audit_service.log_action("PASSWORD_CHANGED", user_id=user_id, username=user["username"])
        return {"success": True, "message": "Password updated successfully."}

    @staticmethod
    def list_users(limit: int = 100, offset: int = 0) -> list:
        """Lists users with their roles and status."""
        with db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT u.id, u.username, u.email, u.role, u.employee_id, u.status, u.created_at, u.last_login,
                       e.full_name, e.employee_code
                FROM users u
                LEFT JOIN employees e ON u.employee_id = e.id
                ORDER BY u.id ASC LIMIT ? OFFSET ?
            """, (limit, offset))
            return [dict(row) for row in cur.fetchall()]

    @staticmethod
    def create_user(username: str, email: str, password: str, role: str, employee_id: int = None, actor_username: str = None) -> dict:
        """Creates a new administrative, teacher, or student user."""
        if role not in ('admin', 'teacher_hr', 'student_employee'):
            return {"success": False, "message": "Invalid role specified."}
        if not username or not password:
            return {"success": False, "message": "Username and password are required."}

        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        pwd_hash = hash_password(password)

        try:
            with db.get_connection() as conn:
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO users (username, email, password_hash, role, employee_id, status, created_at)
                    VALUES (?, ?, ?, ?, ?, 'active', ?)
                """, (username.strip(), email.strip() if email else None, pwd_hash, role, employee_id, now_str))
                new_id = cur.lastrowid
                conn.commit()

            audit_service.log_action("USER_CREATED", username=actor_username, entity_type="user", entity_id=str(new_id), details=f"Created user {username} with role {role}")
            return {"success": True, "message": f"User {username} created successfully.", "user_id": new_id}
        except Exception as e:
            return {"success": False, "message": f"Could not create user: {str(e)}"}

auth_service = AuthService()
