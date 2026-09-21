import os
import datetime
import pandas as pd
from backend.core.config import Config
from backend.models.database import db
from backend.services.biometric_service import biometric_service
from backend.services.audit_service import audit_service

class AttendanceService:
    """Enterprise Attendance Lifecycle Engine with Check-In/Check-Out, Late detection, and Analytics."""

    @staticmethod
    def parse_time_str(time_str: str) -> datetime.time:
        """Parses times like '09:00 AM', '09:15', '17:00:00' into a datetime.time object."""
        if not time_str:
            return datetime.time(9, 0)
        time_str = time_str.strip()
        for fmt in ("%I:%M %p", "%I:%M:%S %p", "%H:%M", "%H:%M:%S", "%d-%m-%Y %I:%M %p"):
            try:
                return datetime.datetime.strptime(time_str, fmt).time()
            except ValueError:
                continue
        return datetime.time(9, 0)

    @staticmethod
    def get_active_rule() -> dict:
        """Fetches active attendance rule or returns standard defaults."""
        with db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM attendance_rules WHERE is_active = 1 ORDER BY id DESC LIMIT 1")
            row = cur.fetchone()
            if row:
                return dict(row)
            return {
                "rule_name": "Standard Shift",
                "work_start_time": "09:00 AM",
                "late_threshold_time": "09:15 AM",
                "work_end_time": "05:00 PM",
                "min_attendance_percent": 75.0
            }

    def process_biometric_scan(self, image_b64: str, mode: str = "auto", subject: str = "General", category: str = "Classroom Lecture") -> dict:
        """Full biometric recognition pipeline:
        1. Evaluates liveness & anti-spoofing
        2. Extracts 128-d face embedding
        3. Identifies employee/student against DB
        4. Handles Check-In / Check-Out with duplicate suppression
        """
        try:
            img_bgr = biometric_service.decode_base64_image(image_b64)
            import cv2
            img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
        except Exception as e:
            return {"success": False, "status": "error", "message": f"Invalid image format: {str(e)}"}

        # 1. Anti-spoofing liveness check
        liveness = biometric_service.evaluate_liveness(img_rgb)
        if not liveness["face_detected"]:
            return {
                "success": False,
                "status": "no_face",
                "message": "No face detected in camera feed. Please position your face inside the frame.",
                "liveness": liveness
            }

        if not liveness["is_sharp"]:
            return {
                "success": False,
                "status": "spoof_warning",
                "message": f"Anti-Spoof Alert: Blurry image or unnatural screen/print detected (Score: {liveness['blur_score']}).",
                "liveness": liveness
            }

        # 2. Extract embedding
        embedding, face_box = biometric_service.extract_face_embedding(img_rgb)
        if embedding is None:
            return {
                "success": False,
                "status": "no_face",
                "message": "Could not compute facial biometrics. Ensure direct lighting.",
                "liveness": liveness
            }

        # 3. Match against enrolled database
        matched_emp, confidence, distance = biometric_service.match_face(embedding)
        if not matched_emp:
            return {
                "success": False,
                "status": "unknown_person",
                "message": "Unknown Person: Face not enrolled in system. Please register first.",
                "distance": distance,
                "liveness": liveness,
                "bounding_box": face_box
            }

        # 4. Mark or update attendance
        attendance_res = self.record_attendance_for_employee(
            employee_info=matched_emp,
            mode=mode,
            confidence=confidence,
            subject=subject,
            category=category
        )
        attendance_res["liveness"] = liveness
        attendance_res["bounding_box"] = face_box
        return attendance_res

    def record_attendance_for_employee(self, employee_info: dict, mode: str = "auto", confidence: float = 1.0, 
                                       subject: str = "General", category: str = "Classroom Lecture") -> dict:
        """Handles check-in, check-out, duration calculation, and duplicate suppression."""
        now = datetime.datetime.now()
        date_dmy = now.strftime("%d-%m-%Y")
        date_iso = now.strftime("%Y-%m-%d")
        time_str = now.strftime("%I:%M:%S %p")
        now_full_str = now.strftime("%Y-%m-%d %H:%M:%S")

        emp_code = employee_info["employee_code"]
        emp_name = employee_info["full_name"]
        emp_id = employee_info.get("employee_id")

        rule = self.get_active_rule()
        late_threshold = self.parse_time_str(rule.get("late_threshold_time", "09:15 AM"))
        current_time_obj = now.time()

        shift_status = "Late" if current_time_obj > late_threshold else "On-Time"

        with db.get_connection() as conn:
            cur = conn.cursor()
            # Check if record already exists today (checking both DMY and ISO formats)
            cur.execute("""
                SELECT * FROM attendance
                WHERE (student_id = ? OR student_id = ?) AND (date = ? OR date = ?)
                ORDER BY id DESC LIMIT 1
            """, (emp_code, str(emp_code), date_dmy, date_iso))
            existing = cur.fetchone()

            if not existing:
                # Mode check: if explicitly requested check_out but no check_in exists
                if mode == "check_out":
                    return {
                        "success": False,
                        "status": "no_check_in",
                        "message": f"No Check-In record found for {emp_name} ({emp_code}) today.",
                        "employee": employee_info
                    }

                # Create new Check-In record
                cur.execute("""
                    INSERT INTO attendance (
                        student_id, name, date, time, status, created_at,
                        log_type, category, subject, shift_status,
                        check_in_time, check_out_time, duration_minutes,
                        confidence_score, verified_by
                    ) VALUES (?, ?, ?, ?, 'Present', ?, 'Check-In', ?, ?, ?, ?, NULL, 0, ?, 'face')
                """, (
                    emp_code, emp_name, date_dmy, time_str, now_full_str,
                    category, subject, shift_status,
                    time_str, confidence
                ))
                rec_id = cur.lastrowid
                conn.commit()

                # Sync to Excel
                self.sync_record_to_excel(emp_code, emp_name, date_dmy, time_str, subject, "Present")

                audit_service.log_action(
                    "ATTENDANCE_CHECK_IN",
                    entity_type="attendance",
                    entity_id=str(rec_id),
                    details=f"Checked In: {emp_name} ({emp_code}) at {time_str} - Status: {shift_status}"
                )

                return {
                    "success": True,
                    "status": "check_in_success",
                    "action": "CHECK_IN",
                    "message": f"Attendance Marked: {emp_name} checked in successfully at {time_str} ({shift_status}).",
                    "attendance_id": rec_id,
                    "check_in_time": time_str,
                    "shift_status": shift_status,
                    "employee": employee_info
                }

            # Record already exists for today
            existing_dict = dict(existing)
            check_in_time_str = existing_dict.get("check_in_time") or existing_dict.get("time")
            check_out_time_str = existing_dict.get("check_out_time")

            # Prevent rapid duplicate spamming within 60 seconds
            created_at_dt = None
            if existing_dict.get("created_at"):
                try:
                    created_at_dt = datetime.datetime.strptime(existing_dict["created_at"], "%Y-%m-%d %H:%M:%S")
                except Exception:
                    pass

            if created_at_dt and (now - created_at_dt).total_seconds() < 60 and not check_out_time_str:
                return {
                    "success": True,
                    "status": "already_marked",
                    "action": "ALREADY_CHECKED_IN",
                    "message": f"Already Marked: {emp_name} checked in at {check_in_time_str}.",
                    "attendance_id": existing_dict["id"],
                    "check_in_time": check_in_time_str,
                    "shift_status": existing_dict.get("shift_status", "On-Time"),
                    "employee": employee_info
                }

            # If check-out requested or auto mode with existing check-in
            if (mode in ("check_out", "auto")) and not check_out_time_str:
                # Calculate duration in minutes
                duration = 0
                try:
                    t_in = self.parse_time_str(check_in_time_str)
                    dt_in = datetime.datetime.combine(now.date(), t_in)
                    dt_out = now
                    if dt_out >= dt_in:
                        duration = int((dt_out - dt_in).total_seconds() / 60)
                except Exception:
                    duration = 0

                cur.execute("""
                    UPDATE attendance
                    SET check_out_time = ?, duration_minutes = ?, log_type = 'Check-Out'
                    WHERE id = ?
                """, (time_str, duration, existing_dict["id"]))
                conn.commit()

                hours, mins = divmod(duration, 60)
                dur_str = f"{hours}h {mins}m" if hours > 0 else f"{mins} mins"

                audit_service.log_action(
                    "ATTENDANCE_CHECK_OUT",
                    entity_type="attendance",
                    entity_id=str(existing_dict["id"]),
                    details=f"Checked Out: {emp_name} at {time_str}. Duration: {dur_str}"
                )

                return {
                    "success": True,
                    "status": "check_out_success",
                    "action": "CHECK_OUT",
                    "message": f"Check-Out Complete: {emp_name} checked out at {time_str}. Total time: {dur_str}.",
                    "attendance_id": existing_dict["id"],
                    "check_in_time": check_in_time_str,
                    "check_out_time": time_str,
                    "duration_minutes": duration,
                    "duration_formatted": dur_str,
                    "employee": employee_info
                }

            # If already both checked in and checked out
            return {
                "success": True,
                "status": "completed_today",
                "action": "COMPLETED",
                "message": f"Day Completed: {emp_name} checked in at {check_in_time_str} and checked out at {check_out_time_str}.",
                "attendance_id": existing_dict["id"],
                "check_in_time": check_in_time_str,
                "check_out_time": check_out_time_str,
                "employee": employee_info
            }

    @staticmethod
    def sync_record_to_excel(student_id, name, date_str, time_str, subject, status):
        """Maintains backward compatibility with Attendance/Attendance.xlsx."""
        try:
            excel_path = Config.EXCEL_ATTENDANCE_FILE
            os.makedirs(os.path.dirname(excel_path), exist_ok=True)
            new_row = {
                "Student ID": str(student_id),
                "Name": str(name),
                "Date": str(date_str),
                "Time": str(time_str),
                "Subject": str(subject),
                "Status": str(status)
            }
            if os.path.exists(excel_path):
                try:
                    df = pd.read_excel(excel_path)
                    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
                except Exception:
                    df = pd.DataFrame([new_row])
            else:
                df = pd.DataFrame([new_row])
            df.to_excel(excel_path, index=False)
        except Exception as e:
            print(f"[AttendanceService] Excel sync notice: {e}")

    @staticmethod
    def manual_mark_attendance(student_id: str, status: str, date_str: str = None, time_str: str = None, 
                               subject: str = "General", shift_status: str = "On-Time", actor: str = "Admin") -> dict:
        """Allows Teacher/Admin to manually mark or correct attendance."""
        now = datetime.datetime.now()
        if not date_str:
            date_str = now.strftime("%d-%m-%Y")
        if not time_str:
            time_str = now.strftime("%I:%M:%S %p")

        with db.get_connection() as conn:
            cur = conn.cursor()
            # Fetch employee name
            cur.execute("SELECT full_name FROM employees WHERE employee_code = ? LIMIT 1", (student_id,))
            emp = cur.fetchone()
            emp_name = emp["full_name"] if emp else f"ID {student_id}"

            # Check if record exists for this date
            cur.execute("SELECT id FROM attendance WHERE student_id = ? AND date = ? LIMIT 1", (student_id, date_str))
            existing = cur.fetchone()

            if existing:
                cur.execute("""
                    UPDATE attendance
                    SET status = ?, time = ?, shift_status = ?, verified_by = ?
                    WHERE id = ?
                """, (status, time_str, shift_status, f"manual_{actor}", existing["id"]))
                rec_id = existing["id"]
            else:
                cur.execute("""
                    INSERT INTO attendance (
                        student_id, name, date, time, status, created_at,
                        log_type, category, subject, shift_status,
                        check_in_time, confidence_score, verified_by
                    ) VALUES (?, ?, ?, ?, ?, ?, 'Manual', 'Lecture', ?, ?, ?, 1.0, ?)
                """, (
                    student_id, emp_name, date_str, time_str, status,
                    now.strftime("%Y-%m-%d %H:%M:%S"), subject, shift_status,
                    time_str if status == "Present" else None, f"manual_{actor}"
                ))
                rec_id = cur.lastrowid
            conn.commit()

        audit_service.log_action(
            "MANUAL_ATTENDANCE",
            username=actor,
            entity_type="attendance",
            entity_id=str(rec_id),
            details=f"Manually set {emp_name} ({student_id}) to {status} for {date_str}"
        )

        return {"success": True, "message": f"Attendance for {emp_name} set to {status}.", "attendance_id": rec_id}

    @staticmethod
    def get_attendance_history(date_from: str = None, date_to: str = None, department_id: int = None,
                               search: str = None, status: str = None, limit: int = 100, offset: int = 0) -> dict:
        """Multi-field filter search for attendance records with pagination."""
        with db.get_connection() as conn:
            cur = conn.cursor()
            query = """
                SELECT a.*, e.id as emp_id, e.email, e.phone, e.designation_class,
                       d.name as department_name, e.profile_photo_path
                FROM attendance a
                LEFT JOIN employees e ON a.student_id = e.employee_code
                LEFT JOIN departments d ON e.department_id = d.id
                WHERE 1=1
            """
            params = []

            if date_from:
                # Support comparing dates in DB
                query += " AND (a.date >= ? OR a.created_at >= ?)"
                params.extend([date_from, date_from])
            if date_to:
                query += " AND (a.date <= ? OR a.created_at <= ?)"
                params.extend([date_to, f"{date_to} 23:59:59"])
            if department_id:
                query += " AND e.department_id = ?"
                params.append(department_id)
            if status:
                query += " AND a.status = ?"
                params.append(status)
            if search:
                query += " AND (a.name LIKE ? OR a.student_id LIKE ? OR e.email LIKE ?)"
                term = f"%{search}%"
                params.extend([term, term, term])

            # Count total matching
            count_query = f"SELECT COUNT(*) FROM ({query})"
            cur.execute(count_query, params)
            total_count = cur.fetchone()[0]

            query += " ORDER BY a.id DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])

            cur.execute(query, params)
            rows = [dict(r) for r in cur.fetchall()]

            return {
                "records": rows,
                "total": total_count,
                "limit": limit,
                "offset": offset
            }

    @staticmethod
    def get_student_attendance_records(employee_code: str, limit: int = 50) -> list:
        """Retrieves history specific to a single student/employee."""
        with db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT a.*, d.name as department_name
                FROM attendance a
                LEFT JOIN employees e ON a.student_id = e.employee_code
                LEFT JOIN departments d ON e.department_id = d.id
                WHERE a.student_id = ?
                ORDER BY a.id DESC LIMIT ?
            """, (str(employee_code), limit))
            return [dict(r) for r in cur.fetchall()]

attendance_service = AttendanceService()
