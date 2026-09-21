#!/usr/bin/env python3
"""
Enterprise Attendance Management System - Server Launcher
Runs Flask web server serving both REST API and modern responsive Web UI.
"""
import os
import sys

# Ensure project root is in sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from backend.app import create_app

app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"================================================================")
    print(f"  ATTENDANCE MANAGEMENT STUDIO (Enterprise Edition 2.0)")
    print(f"  Web Application: http://localhost:{port}")
    print(f"  Default Admin:   admin   / Admin@123")
    print(f"  Default Teacher: teacher / Teacher@123")
    print(f"  Default Student: EMP001  / Student@123")
    print(f"================================================================")
    app.run(host="0.0.0.0", port=port, debug=False)
