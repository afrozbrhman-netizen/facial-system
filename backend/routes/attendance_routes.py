from flask import Blueprint, request, jsonify, g
import datetime
from backend.core.security import login_required, teacher_or_admin_required
from backend.services.attendance_service import attendance_service

attendance_bp = Blueprint("attendance_bp", __name__, url_prefix="/api/attendance")

@attendance_bp.route("/scan", methods=["POST"])
@login_required
def scan_face():
    """Real-time camera attendance endpoint with Anti-Spoofing & Liveness verification."""
    data = request.get_json() or {}
    image_b64 = data.get("image")
    if not image_b64:
        return jsonify({"success": False, "message": "No camera frame provided."}), 400

    mode = data.get("mode", "auto")
    subject = data.get("subject", "General")
    category = data.get("category", "Classroom Lecture")

    result = attendance_service.process_biometric_scan(
        image_b64=image_b64,
        mode=mode,
        subject=subject,
        category=category
    )
    return jsonify(result)

@attendance_bp.route("/manual-mark", methods=["POST"])
@teacher_or_admin_required
def manual_mark():
    """Manual attendance correction or marking by authorized Teacher/Admin."""
    data = request.get_json() or {}
    student_id = data.get("student_id")
    status = data.get("status", "Present")
    date_str = data.get("date")
    time_str = data.get("time")
    subject = data.get("subject", "General")
    shift_status = data.get("shift_status", "On-Time")

    if not student_id:
        return jsonify({"success": False, "message": "Student/Employee ID is required."}), 400

    actor = g.current_user.get("username", "Admin")
    result = attendance_service.manual_mark_attendance(
        student_id=str(student_id),
        status=status,
        date_str=date_str,
        time_str=time_str,
        subject=subject,
        shift_status=shift_status,
        actor=actor
    )
    return jsonify(result)

@attendance_bp.route("/history", methods=["GET"])
@login_required
def get_history():
    """Paginated attendance history with multi-column filtering."""
    # If logged-in user is a student, enforce filter to only their records
    user = g.current_user
    search = request.args.get("search")
    if user.get("role") == "student_employee":
        emp_code = user.get("employee_code") or user.get("username")
        records = attendance_service.get_student_attendance_records(emp_code, limit=100)
        return jsonify({"success": True, "records": records, "total": len(records), "limit": 100, "offset": 0})

    date_from = request.args.get("date_from")
    date_to = request.args.get("date_to")
    department_id = request.args.get("department_id", type=int)
    status = request.args.get("status")
    limit = int(request.args.get("limit", 100))
    offset = int(request.args.get("offset", 0))

    result = attendance_service.get_attendance_history(
        date_from=date_from,
        date_to=date_to,
        department_id=department_id,
        search=search,
        status=status,
        limit=limit,
        offset=offset
    )
    return jsonify({"success": True, **result})

@attendance_bp.route("/today", methods=["GET"])
@login_required
def get_today():
    """Convenience endpoint returning all attendance records for today."""
    now = datetime.datetime.now()
    d_dmy = now.strftime("%d-%m-%Y")
    d_iso = now.strftime("%Y-%m-%d")

    res = attendance_service.get_attendance_history(date_from=d_dmy, date_to=d_dmy, limit=500)
    return jsonify({"success": True, "records": res["records"]})
