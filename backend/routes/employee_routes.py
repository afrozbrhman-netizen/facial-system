from flask import Blueprint, request, jsonify, g
from backend.core.security import login_required, teacher_or_admin_required, admin_required
from backend.services.employee_service import employee_service
from backend.services.biometric_service import biometric_service

employee_bp = Blueprint("employee_bp", __name__, url_prefix="/api/employees")

@employee_bp.route("", methods=["GET"])
@login_required
def get_employees():
    search = request.args.get("search")
    department_id = request.args.get("department_id", type=int)
    status = request.args.get("status")
    limit = int(request.args.get("limit", 100))
    offset = int(request.args.get("offset", 0))

    result = employee_service.list_employees(
        search=search,
        department_id=department_id,
        status=status,
        limit=limit,
        offset=offset
    )
    return jsonify({"success": True, **result})

@employee_bp.route("/<int:emp_id>", methods=["GET"])
@login_required
def get_employee_detail(emp_id):
    emp = employee_service.get_employee_by_id(emp_id)
    if not emp:
        return jsonify({"success": False, "message": "Employee not found."}), 404
    return jsonify({"success": True, "employee": emp})

@employee_bp.route("", methods=["POST"])
@teacher_or_admin_required
def create_employee():
    data = request.get_json() or {}
    actor = g.current_user.get("username", "Admin")
    result = employee_service.create_employee(data, actor=actor)
    status_code = 201 if result.get("success") else 400
    return jsonify(result), status_code

@employee_bp.route("/<int:emp_id>", methods=["PUT"])
@teacher_or_admin_required
def update_employee(emp_id):
    data = request.get_json() or {}
    actor = g.current_user.get("username", "Admin")
    result = employee_service.update_employee(emp_id, data, actor=actor)
    status_code = 200 if result.get("success") else 400
    return jsonify(result), status_code

@employee_bp.route("/<int:emp_id>", methods=["DELETE"])
@admin_required
def delete_employee(emp_id):
    actor = g.current_user.get("username", "Admin")
    result = employee_service.delete_employee(emp_id, actor=actor)
    status_code = 200 if result.get("success") else 400
    return jsonify(result), status_code

@employee_bp.route("/<int:emp_id>/register-face", methods=["POST"])
@teacher_or_admin_required
def register_face(emp_id):
    emp = employee_service.get_employee_by_id(emp_id)
    if not emp:
        return jsonify({"success": False, "message": "Employee not found."}), 404

    data = request.get_json() or {}
    image_b64 = data.get("image")
    if not image_b64:
        return jsonify({"success": False, "message": "No image data provided."}), 400

    allow_duplicate = data.get("allow_duplicate", False)
    result = biometric_service.register_employee_face(emp_id, image_b64, allow_duplicate=allow_duplicate)
    status_code = 200 if result.get("success") else 400
    return jsonify(result), status_code

@employee_bp.route("/<int:emp_id>/stats", methods=["GET"])
@login_required
def get_stats(emp_id):
    stats = employee_service.get_employee_attendance_stats(emp_id)
    if "error" in stats:
        return jsonify({"success": False, "message": stats["error"]}), 404
    return jsonify({"success": True, "stats": stats})

@employee_bp.route("/<int:emp_id>/password", methods=["POST"])
@teacher_or_admin_required
def set_password(emp_id):
    data = request.get_json() or {}
    new_password = data.get("password")
    if not new_password:
        return jsonify({"success": False, "message": "Password is required."}), 400

    actor = g.current_user.get("username", "Admin")
    result = employee_service.set_employee_password(emp_id, new_password, actor=actor)
    status_code = 200 if result.get("success") else 400
    return jsonify(result), status_code

