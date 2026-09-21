from flask import Blueprint, request, jsonify, g
import datetime
from backend.core.security import login_required, admin_required
from backend.models.database import db
from backend.services.attendance_service import attendance_service
from backend.services.audit_service import audit_service

settings_bp = Blueprint("settings_bp", __name__, url_prefix="/api/settings")

@settings_bp.route("/rules", methods=["GET"])
@login_required
def get_rules():
    rule = attendance_service.get_active_rule()
    return jsonify({"success": True, "rule": rule})

@settings_bp.route("/rules", methods=["PUT"])
@admin_required
def update_rules():
    data = request.get_json() or {}
    rule_name = data.get("rule_name", "Standard Shift")
    work_start_time = data.get("work_start_time", "09:00 AM")
    late_threshold_time = data.get("late_threshold_time", "09:15 AM")
    work_end_time = data.get("work_end_time", "05:00 PM")
    min_pct = float(data.get("min_attendance_percent", 75.0))
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with db.get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id FROM attendance_rules WHERE is_active = 1 LIMIT 1")
        row = cur.fetchone()
        if row:
            cur.execute("""
                UPDATE attendance_rules
                SET rule_name = ?, work_start_time = ?, late_threshold_time = ?,
                    work_end_time = ?, min_attendance_percent = ?, updated_at = ?
                WHERE id = ?
            """, (rule_name, work_start_time, late_threshold_time, work_end_time, min_pct, now_str, row["id"]))
        else:
            cur.execute("""
                INSERT INTO attendance_rules (rule_name, work_start_time, late_threshold_time, work_end_time, min_attendance_percent, is_active, updated_at)
                VALUES (?, ?, ?, ?, ?, 1, ?)
            """, (rule_name, work_start_time, late_threshold_time, work_end_time, min_pct, now_str))
        conn.commit()

    audit_service.log_action("UPDATE_RULES", username=g.current_user.get("username"), details=f"Rules updated: Late threshold {late_threshold_time}, Min % {min_pct}%")
    return jsonify({"success": True, "message": "Attendance rules updated successfully."})

@settings_bp.route("/departments", methods=["GET"])
@login_required
def get_departments():
    with db.get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT d.*, COUNT(e.id) as employee_count
            FROM departments d
            LEFT JOIN employees e ON d.id = e.department_id
            GROUP BY d.id
            ORDER BY d.name ASC
        """)
        depts = [dict(r) for r in cur.fetchall()]
    return jsonify({"success": True, "departments": depts})

@settings_bp.route("/departments", methods=["POST"])
@admin_required
def add_department():
    data = request.get_json() or {}
    name = str(data.get("name", "")).strip()
    code = str(data.get("code", "")).strip().upper()
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if not name:
        return jsonify({"success": False, "message": "Department name is required."}), 400

    try:
        with db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("INSERT INTO departments (name, code, created_at) VALUES (?, ?, ?)", (name, code or None, now_str))
            dept_id = cur.lastrowid
            conn.commit()
        audit_service.log_action("CREATE_DEPARTMENT", username=g.current_user.get("username"), details=f"Created department {name} ({code})")
        return jsonify({"success": True, "message": f"Department '{name}' created.", "department_id": dept_id}), 201
    except Exception as e:
        return jsonify({"success": False, "message": f"Could not create department: {str(e)}"}), 400

@settings_bp.route("/departments/<int:dept_id>", methods=["DELETE"])
@admin_required
def delete_department(dept_id):
    with db.get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT name FROM departments WHERE id = ?", (dept_id,))
        dept = cur.fetchone()
        if not dept:
            return jsonify({"success": False, "message": "Department not found."}), 404

        cur.execute("DELETE FROM departments WHERE id = ?", (dept_id,))
        conn.commit()

    audit_service.log_action("DELETE_DEPARTMENT", username=g.current_user.get("username"), details=f"Deleted department {dept['name']}")
    return jsonify({"success": True, "message": f"Department '{dept['name']}' deleted."})

@settings_bp.route("/audit-logs", methods=["GET"])
@admin_required
def get_audit_logs():
    limit = int(request.args.get("limit", 100))
    offset = int(request.args.get("offset", 0))
    action_filter = request.args.get("action")
    search = request.args.get("search")

    logs = audit_service.get_logs(limit=limit, offset=offset, action_filter=action_filter, search=search)
    return jsonify({"success": True, "logs": logs})

@settings_bp.route("/notifications", methods=["GET"])
@login_required
def get_notifications():
    user_id = g.current_user.get("id")
    notifs = audit_service.get_notifications(user_id=user_id)
    return jsonify({"success": True, "notifications": notifs})

@settings_bp.route("/notifications/read-all", methods=["POST"])
@login_required
def mark_read():
    user_id = g.current_user.get("id")
    audit_service.mark_all_read(user_id=user_id)
    return jsonify({"success": True, "message": "Notifications marked as read."})
