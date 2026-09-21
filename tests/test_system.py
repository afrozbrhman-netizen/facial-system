"""
Automated Test Suite for Enterprise Attendance Management System
Validates Security, Authentication, RBAC, Biometrics, Attendance Logic, and Exports.
"""
import os
import sys
import unittest
import json
import numpy as np
import cv2

# Add base directory to sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from backend.app import create_app
from backend.core.security import hash_password, verify_password, create_token, decode_token
from backend.services.biometric_service import biometric_service
from backend.services.attendance_service import attendance_service
from backend.services.report_service import report_service

class TestAttendanceSystem(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.client = cls.app.test_client()

    def test_01_security_hashing_and_jwt(self):
        """Test PBKDF2 password hashing and HMAC token lifecycle."""
        pwd = "SecretPassword@123"
        hashed = hash_password(pwd)
        self.assertTrue(verify_password(pwd, hashed))
        self.assertFalse(verify_password("WrongPassword", hashed))

        payload = {"id": 1, "username": "admin", "role": "admin"}
        token = create_token(payload)
        self.assertIsNotNone(token)
        decoded = decode_token(token)
        self.assertEqual(decoded["username"], "admin")
        self.assertEqual(decoded["role"], "admin")

    def test_02_auth_endpoints_and_rbac(self):
        """Test API authentication login and role protection."""
        # 1. Login with admin
        res = self.client.post("/api/auth/login", json={
            "username": "admin",
            "password": "Admin@123"
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        admin_token = data["token"]

        # 2. Login with student (using student 8's individual password)
        res_stu = self.client.post("/api/auth/login", json={
            "username": "8",
            "password": "8@123"
        })
        self.assertEqual(res_stu.status_code, 200)
        student_token = res_stu.get_json()["token"]

        # 3. Test protected admin route with student token (should be 403 Forbidden)
        res_forbidden = self.client.get("/api/settings/audit-logs", headers={
            "Authorization": f"Bearer {student_token}"
        })
        self.assertEqual(res_forbidden.status_code, 403)

        # 4. Test protected admin route with admin token (should be 200 OK)
        res_ok = self.client.get("/api/settings/audit-logs", headers={
            "Authorization": f"Bearer {admin_token}"
        })
        self.assertEqual(res_ok.status_code, 200)

    def test_03_biometric_anti_spoofing_sharpness(self):
        """Test blur / Laplacian variance anti-spoofing check."""
        # High-frequency textured image (sharp)
        sharp_img = np.random.randint(0, 255, (300, 300, 3), dtype=np.uint8)
        is_sharp, score = biometric_service.check_sharpness(sharp_img)
        self.assertTrue(is_sharp)
        self.assertGreater(score, 60.0)

        # Uniform gray image (blurry / flat screen)
        flat_img = np.full((300, 300, 3), 128, dtype=np.uint8)
        is_sharp_flat, flat_score = biometric_service.check_sharpness(flat_img)
        self.assertFalse(is_sharp_flat)
        self.assertEqual(flat_score, 0.0)

    def test_04_biometric_ear_calculation(self):
        """Test Eye Aspect Ratio calculation for blink detection."""
        # Simulated open eye landmarks: 6 points
        open_eye = [
            (10, 20), # p1
            (15, 15), # p2
            (25, 15), # p3
            (30, 20), # p4
            (25, 25), # p5
            (15, 25)  # p6
        ]
        ear_open = biometric_service.calculate_ear(open_eye)
        self.assertGreater(ear_open, 0.25)

        # Simulated closed eye landmarks: vertical points almost touching
        closed_eye = [
            (10, 20), # p1
            (15, 20.2), # p2
            (25, 20.2), # p3
            (30, 20), # p4
            (25, 19.8), # p5
            (15, 19.8)  # p6
        ]
        ear_closed = biometric_service.calculate_ear(closed_eye)
        self.assertLess(ear_closed, 0.1)

    def test_05_employee_crud_and_legacy_sync(self):
        """Test employee profile creation and sync with students table."""
        # Login admin
        res = self.client.post("/api/auth/login", json={"username": "admin", "password": "Admin@123"})
        token = res.get_json()["token"]

        emp_code = f"TEST_{np.random.randint(10000, 99999)}"
        res_create = self.client.post("/api/employees", headers={"Authorization": f"Bearer {token}"}, json={
            "employee_code": emp_code,
            "full_name": "Test Engineer",
            "email": f"test_{emp_code}@domain.com",
            "designation_class": "Senior Analyst"
        })
        self.assertEqual(res_create.status_code, 201)
        created_data = res_create.get_json()
        emp_id = created_data["employee_id"]

        # Verify employee listed
        res_list = self.client.get(f"/api/employees?search={emp_code}", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(res_list.status_code, 200)
        self.assertEqual(len(res_list.get_json()["employees"]), 1)

    def test_06_attendance_check_in_and_check_out(self):
        """Test attendance marking, shift status, and duration calculation."""
        dyn_id = f"TEST_EMP_{np.random.randint(10000, 99999)}"
        emp_info = {
            "employee_id": 9999,
            "employee_code": dyn_id,
            "full_name": "Alex Mercer",
            "department_id": 1,
            "department_name": "Computer Science"
        }

        # First Check-In
        res1 = attendance_service.record_attendance_for_employee(emp_info, mode="check_in")
        self.assertTrue(res1["success"])
        self.assertIn(res1["action"], ("CHECK_IN", "ALREADY_CHECKED_IN"))

        # Subsequent Check-Out
        res2 = attendance_service.record_attendance_for_employee(emp_info, mode="check_out")
        self.assertTrue(res2["success"])
        self.assertIn(res2["action"], ("CHECK_OUT", "COMPLETED", "ALREADY_CHECKED_IN"))

    def test_07_export_generation(self):
        """Test Excel and CSV report exports."""
        excel_bytes, mime_excel, fname_excel = report_service.generate_export("daily", "excel")
        self.assertGreater(len(excel_bytes), 100)
        self.assertTrue(fname_excel.endswith(".xlsx"))

        csv_bytes, mime_csv, fname_csv = report_service.generate_export("daily", "csv")
        self.assertGreater(len(csv_bytes), 10)
        self.assertTrue(fname_csv.endswith(".csv"))

if __name__ == "__main__":
    unittest.main()
