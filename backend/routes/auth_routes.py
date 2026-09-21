from flask import Blueprint, request, jsonify, g
from backend.core.security import login_required, admin_required
from backend.services.auth_service import auth_service
from backend.services.audit_service import audit_service

auth_bp = Blueprint("auth_bp", __name__, url_prefix="/api/auth")

@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json() or {}
    username = data.get("username", "")
    password = data.get("password", "")
    ip_addr = request.remote_addr

    result = auth_service.authenticate(username, password, ip_address=ip_addr)
    status_code = 200 if result.get("success") else 401
    return jsonify(result), status_code

@auth_bp.route("/me", methods=["GET"])
@login_required
def get_me():
    user = auth_service.get_user_profile(g.current_user["id"])
    if not user:
        return jsonify({"success": False, "message": "User not found."}), 404
    # Do not expose password hash
    user.pop("password_hash", None)
    return jsonify({"success": True, "user": user})

@auth_bp.route("/change-password", methods=["POST"])
@login_required
def change_password():
    data = request.get_json() or {}
    curr_pwd = data.get("current_password", "")
    new_pwd = data.get("new_password", "")

    result = auth_service.change_password(g.current_user["id"], curr_pwd, new_pwd)
    status_code = 200 if result.get("success") else 400
    return jsonify(result), status_code

@auth_bp.route("/users", methods=["GET"])
@admin_required
def get_users():
    limit = int(request.args.get("limit", 100))
    offset = int(request.args.get("offset", 0))
    users = auth_service.list_users(limit, offset)
    return jsonify({"success": True, "users": users})

@auth_bp.route("/users", methods=["POST"])
@admin_required
def create_user():
    data = request.get_json() or {}
    username = data.get("username")
    email = data.get("email")
    password = data.get("password")
    role = data.get("role")
    employee_id = data.get("employee_id")

    result = auth_service.create_user(
        username=username,
        email=email,
        password=password,
        role=role,
        employee_id=employee_id,
        actor_username=g.current_user.get("username")
    )
    status_code = 201 if result.get("success") else 400
    return jsonify(result), status_code

@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    audit_service.log_action("LOGOUT", user_id=g.current_user["id"], username=g.current_user["username"])
    return jsonify({"success": True, "message": "Logged out successfully."})
