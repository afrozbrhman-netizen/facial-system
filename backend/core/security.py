import time
import json
import base64
import hmac
import hashlib
from functools import wraps
from flask import request, jsonify, g
from werkzeug.security import generate_password_hash, check_password_hash
from backend.core.config import Config

def hash_password(password: str) -> str:
    """Hashes password with PBKDF2 SHA256 and salt."""
    return generate_password_hash(password, method="pbkdf2:sha256", salt_length=16)

def verify_password(password: str, password_hash: str) -> bool:
    """Verifies plaintext password against hashed password."""
    if not password or not password_hash:
        return False
    return check_password_hash(password_hash, password)

def create_token(payload: dict) -> str:
    """Generates a signed, self-contained token with expiry timestamp."""
    exp = int(time.time()) + (Config.JWT_EXPIRATION_HOURS * 3600)
    payload_copy = dict(payload)
    payload_copy["exp"] = exp
    payload_bytes = json.dumps(payload_copy, separators=(',', ':')).encode('utf-8')
    payload_b64 = base64.urlsafe_b64encode(payload_bytes).decode('utf-8').rstrip('=')
    
    sig = hmac.new(Config.JWT_SECRET.encode('utf-8'), payload_b64.encode('utf-8'), hashlib.sha256).digest()
    sig_b64 = base64.urlsafe_b64encode(sig).decode('utf-8').rstrip('=')
    return f"{payload_b64}.{sig_b64}"

def decode_token(token: str) -> dict:
    """Validates token signature and returns decoded payload, or None if invalid/expired."""
    try:
        parts = token.strip().split('.')
        if len(parts) != 2:
            return None
        payload_b64, sig_b64 = parts
        
        # Verify HMAC signature
        expected_sig = hmac.new(Config.JWT_SECRET.encode('utf-8'), payload_b64.encode('utf-8'), hashlib.sha256).digest()
        expected_sig_b64 = base64.urlsafe_b64encode(expected_sig).decode('utf-8').rstrip('=')
        if not hmac.compare_digest(sig_b64, expected_sig_b64):
            return None
        
        # Decode payload
        pad_len = 4 - (len(payload_b64) % 4)
        if pad_len < 4:
            payload_b64 += '=' * pad_len
        payload = json.loads(base64.urlsafe_b64decode(payload_b64.encode('utf-8')).decode('utf-8'))
        
        if payload.get("exp", 0) < int(time.time()):
            return None  # Expired
        return payload
    except Exception:
        return None

def get_current_user():
    """Extracts authenticated user from Authorization header (Bearer <token>)."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
        return decode_token(token)
    return None

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_user()
        if not user:
            return jsonify({"success": False, "message": "Authentication required. Please log in."}), 401
        g.current_user = user
        return f(*args, **kwargs)
    return decorated

def roles_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            user = get_current_user()
            if not user:
                return jsonify({"success": False, "message": "Authentication required. Please log in."}), 401
            if user.get("role") not in roles:
                return jsonify({"success": False, "message": f"Access denied. Required role: {', '.join(roles)}"}), 403
            g.current_user = user
            return f(*args, **kwargs)
        return decorated
    return decorator

def admin_required(f):
    return roles_required("admin")(f)

def teacher_or_admin_required(f):
    return roles_required("admin", "teacher_hr", "teacher", "faculty", "hr", "staff")(f)
