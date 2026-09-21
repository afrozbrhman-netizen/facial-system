import os
from flask import Flask, send_from_directory, jsonify
from flask_cors import CORS
from backend.core.config import Config, BASE_DIR
from backend.routes.auth_routes import auth_bp
from backend.routes.employee_routes import employee_bp
from backend.routes.attendance_routes import attendance_bp
from backend.routes.report_routes import report_bp
from backend.routes.settings_routes import settings_bp

def create_app():
    """Application factory for Enterprise Face Biometrics & Attendance Management System."""
    frontend_dir = os.path.join(BASE_DIR, "frontend")
    static_dir = os.path.join(frontend_dir, "static")

    app = Flask(
        __name__,
        static_folder=static_dir,
        static_url_path="/static"
    )
    app.config.from_object(Config)

    # Enable CORS for API routes
    CORS(app, resources={r"/api/*": {"origins": "*"}})

    # Register Blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(employee_bp)
    app.register_blueprint(attendance_bp)
    app.register_blueprint(report_bp)
    app.register_blueprint(settings_bp)

    # System Health Check
    @app.route("/api/health")
    def health():
        return jsonify({
            "status": "healthy",
            "service": "Attendance Management Studio",
            "biometrics": "128-d ResNet + EAR Liveness Engine",
            "version": "2.0.0"
        })

    # Serve Uploaded Profile Photos
    @app.route("/uploads/<path:filename>")
    def serve_upload(filename):
        return send_from_directory(Config.UPLOAD_FOLDER, filename)

    # Frontend Single-Page Application Entry
    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def serve_frontend(path):
        # If requested path is a real file inside frontend_dir, serve it
        full_path = os.path.join(frontend_dir, path)
        if path and os.path.exists(full_path) and os.path.isfile(full_path):
            return send_from_directory(frontend_dir, path)
        # Otherwise fallback to index.html for client-side SPA routing
        index_file = os.path.join(frontend_dir, "index.html")
        if os.path.exists(index_file):
            return send_from_directory(frontend_dir, "index.html")
        return jsonify({
            "message": "Enterprise Attendance System Backend running.",
            "api_docs": "/api/health"
        })

    # Error handlers
    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"success": False, "message": "Resource not found."}), 404

    @app.errorhandler(500)
    def server_error(e):
        return jsonify({"success": False, "message": "Internal server error occurred."}), 500

    return app

if __name__ == "__main__":
    application = create_app()
    port = int(os.environ.get("PORT", 5000))
    print(f"[*] Starting Attendance Management Server on http://localhost:{port}")
    application.run(host="0.0.0.0", port=port, debug=True)
