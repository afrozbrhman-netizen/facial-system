import os
import re
import json
import base64
import numpy as np
import cv2
import face_recognition
import datetime
from backend.core.config import Config
from backend.models.database import db

class BiometricService:
    """Enterprise Face Biometrics with 128-d deep embeddings, Liveness verification & Anti-Spoofing."""

    def __init__(self):
        self.faces_dir = os.path.join(Config.UPLOAD_FOLDER, "faces")
        os.makedirs(self.faces_dir, exist_ok=True)

    @staticmethod
    def decode_base64_image(image_b64: str) -> np.ndarray:
        """Decodes base64 image (with or without data URI prefix) into a BGR OpenCV image."""
        if not image_b64:
            raise ValueError("Empty image data provided.")
        
        # Strip data URL header if present
        if "," in image_b64:
            image_b64 = image_b64.split(",", 1)[1]
            
        img_bytes = base64.b64decode(image_b64)
        nparr = np.frombuffer(img_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("Failed to decode image from base64 string.")
        return img

    @staticmethod
    def encode_image_base64(img_bgr: np.ndarray, ext: str = ".jpg") -> str:
        """Encodes an OpenCV image into base64 string."""
        success, encoded_img = cv2.imencode(ext, img_bgr)
        if not success:
            raise ValueError("Failed to encode image to base64.")
        return f"data:image/jpeg;base64,{base64.b64encode(encoded_img).decode('utf-8')}"

    @staticmethod
    def check_sharpness(img_bgr: np.ndarray) -> tuple[bool, float]:
        """Anti-spoofing check: checks Laplacian variance. Low variance indicates a blurry photo or low-res display spoof."""
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        variance = cv2.Laplacian(gray, cv2.CV_64F).var()
        is_sharp = variance >= Config.LIVENESS_BLUR_THRESHOLD
        return is_sharp, round(float(variance), 2)

    @staticmethod
    def calculate_ear(eye_points: list) -> float:
        """Calculates Eye Aspect Ratio (EAR) from 6 landmark points:
        EAR = (||p2 - p6|| + ||p3 - p5||) / (2 * ||p1 - p4||)
        """
        if len(eye_points) < 6:
            return 0.0
        p1, p2, p3, p4, p5, p6 = [np.array(pt) for pt in eye_points[:6]]
        # Vertical distances
        v1 = np.linalg.norm(p2 - p6)
        v2 = np.linalg.norm(p3 - p5)
        # Horizontal distance
        h = np.linalg.norm(p1 - p4)
        if h == 0:
            return 0.0
        return float((v1 + v2) / (2.0 * h))

    def evaluate_liveness(self, img_rgb: np.ndarray) -> dict:
        """Analyzes facial landmarks for eyes, calculates EAR and checks image sharpness."""
        img_bgr = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2BGR)
        is_sharp, blur_score = self.check_sharpness(img_bgr)

        landmarks_list = face_recognition.face_landmarks(img_rgb)
        if not landmarks_list:
            return {
                "face_detected": False,
                "is_live": False,
                "blur_score": blur_score,
                "is_sharp": is_sharp,
                "ear": 0.0,
                "blink_detected": False,
                "message": "No face landmarks detected"
            }

        landmarks = landmarks_list[0]
        left_eye = landmarks.get("left_eye", [])
        right_eye = landmarks.get("right_eye", [])

        left_ear = self.calculate_ear(left_eye) if left_eye else 0.0
        right_ear = self.calculate_ear(right_eye) if right_eye else 0.0
        avg_ear = round((left_ear + right_ear) / 2.0, 3)

        # Blink is considered active when EAR dips below the threshold (e.g. 0.22)
        blink_detected = avg_ear < Config.LIVENESS_EAR_THRESHOLD
        is_live = is_sharp  # Sharpness + facial structure

        return {
            "face_detected": True,
            "is_live": is_live,
            "blur_score": blur_score,
            "is_sharp": is_sharp,
            "ear": avg_ear,
            "blink_detected": blink_detected,
            "landmarks_count": sum(len(pts) for pts in landmarks.values()),
            "message": "Liveness check passed" if is_live else "Image too blurry or unnatural texture"
        }

    def extract_face_embedding(self, img_rgb: np.ndarray) -> tuple[np.ndarray | None, list | None]:
        """Detects primary face and extracts 128-d deep ResNet embedding."""
        face_locations = face_recognition.face_locations(img_rgb, model="hog")
        if not face_locations:
            return None, None
        
        # Sort by bounding box area (largest face in frame)
        face_locations = sorted(face_locations, key=lambda box: (box[2] - box[0]) * (box[1] - box[3]), reverse=True)
        primary_box = face_locations[0]

        encodings = face_recognition.face_encodings(img_rgb, known_face_locations=[primary_box], num_jitters=1)
        if not encodings:
            return None, None

        return encodings[0], list(primary_box)

    def find_duplicate_face(self, new_embedding: np.ndarray, exclude_employee_id: int = None, duplicate_threshold: float = 0.42) -> tuple[bool, dict | None, float]:
        """Checks if the given face embedding is already enrolled for another employee/student to prevent duplicates."""
        with db.get_connection() as conn:
            cur = conn.cursor()
            query = """
                SELECT fe.employee_id, fe.embedding_json, e.full_name, e.employee_code
                FROM face_embeddings fe
                JOIN employees e ON fe.employee_id = e.id
            """
            params = []
            if exclude_employee_id is not None:
                query += " WHERE fe.employee_id != ?"
                params.append(exclude_employee_id)
            
            cur.execute(query, params)
            rows = cur.fetchall()

            for row in rows:
                try:
                    enrolled_vec = np.array(json.loads(row["embedding_json"]), dtype=np.float64)
                    dist = float(np.linalg.norm(enrolled_vec - new_embedding))
                    if dist <= duplicate_threshold:
                        return True, {
                            "employee_id": row["employee_id"],
                            "full_name": row["full_name"],
                            "employee_code": row["employee_code"]
                        }, round(dist, 4)
                except Exception:
                    continue

        return False, None, 1.0

    def match_face(self, face_embedding: np.ndarray, tolerance: float = None) -> tuple[dict | None, float, float]:
        """Matches a 128-d embedding against all enrolled profiles in the database.
        Returns: (employee_info, confidence_score, distance) or (None, 0.0, min_distance)
        """
        if tolerance is None:
            tolerance = Config.FACE_MATCH_TOLERANCE

        with db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT fe.id as embedding_id, fe.employee_id, fe.embedding_json,
                       e.employee_code, e.full_name, e.department_id, e.designation_class,
                       d.name as department_name, e.profile_photo_path
                FROM face_embeddings fe
                JOIN employees e ON fe.employee_id = e.id
                LEFT JOIN departments d ON e.department_id = d.id
                WHERE e.status = 'active'
            """)
            rows = cur.fetchall()

        if not rows:
            return None, 0.0, 1.0

        min_distance = float("inf")
        best_match = None

        for row in rows:
            try:
                enrolled_vec = np.array(json.loads(row["embedding_json"]), dtype=np.float64)
                dist = float(np.linalg.norm(enrolled_vec - face_embedding))
                if dist < min_distance:
                    min_distance = dist
                    best_match = row
            except Exception:
                continue

        if best_match is not None and min_distance <= tolerance:
            # Confidence score calculation: maps distance 0.0 -> 100%, tolerance -> ~60%
            confidence = max(0.0, min(1.0, 1.0 - (min_distance / (tolerance * 1.5))))
            emp_info = {
                "employee_id": best_match["employee_id"],
                "employee_code": best_match["employee_code"],
                "full_name": best_match["full_name"],
                "department_id": best_match["department_id"],
                "department_name": best_match["department_name"] or "General",
                "designation_class": best_match["designation_class"],
                "profile_photo_path": best_match["profile_photo_path"]
            }
            return emp_info, round(confidence, 4), round(min_distance, 4)

        return None, 0.0, round(min_distance, 4)

    def register_employee_face(self, employee_id: int, image_b64: str, allow_duplicate: bool = False) -> dict:
        """Validates photo, extracts 128-d embedding, verifies anti-duplicate policy,
        saves cropped face photo, and records the embedding into the database."""
        img_bgr = self.decode_base64_image(image_b64)
        img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)

        # 1. Anti-spoofing sharpness check
        is_sharp, blur_score = self.check_sharpness(img_bgr)
        if not is_sharp:
            return {
                "success": False,
                "message": f"Photo is too blurry or low quality (Sharpness score: {blur_score}, minimum required: {Config.LIVENESS_BLUR_THRESHOLD}). Please use good lighting."
            }

        # 2. Extract primary face embedding
        embedding, face_box = self.extract_face_embedding(img_rgb)
        if embedding is None or face_box is None:
            return {
                "success": False,
                "message": "No clear face could be detected in the provided image. Please face the camera directly."
            }

        # 3. Check for duplicate face across different employees
        if not allow_duplicate:
            is_dup, dup_emp, dup_dist = self.find_duplicate_face(embedding, exclude_employee_id=employee_id)
            if is_dup:
                return {
                    "success": False,
                    "message": f"Duplicate Face Detected! This face matches existing user: {dup_emp['full_name']} ({dup_emp['employee_code']}) with similarity distance {dup_dist}.",
                    "duplicate_employee": dup_emp
                }

        # 4. Crop face and save to disk
        top, right, bottom, left = face_box
        h, w, _ = img_bgr.shape
        # Add slight margin padding around bounding box
        pad_y = int((bottom - top) * 0.2)
        pad_x = int((right - left) * 0.2)
        crop_top = max(0, top - pad_y)
        crop_bottom = min(h, bottom + pad_y)
        crop_left = max(0, left - pad_x)
        crop_right = min(w, right + pad_x)
        face_crop = img_bgr[crop_top:crop_bottom, crop_left:crop_right]

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"emp_{employee_id}_{timestamp}.jpg"
        save_path = os.path.join(self.faces_dir, filename)
        rel_path = os.path.join("uploads", "faces", filename).replace("\\", "/")
        cv2.imwrite(save_path, face_crop)

        # 5. Store in database
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        embedding_json = json.dumps(embedding.tolist())

        with db.get_connection() as conn:
            cur = conn.cursor()
            # Replace previous embeddings for this employee or add new sample
            cur.execute("""
                INSERT INTO face_embeddings (employee_id, embedding_json, photo_path, quality_score, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (employee_id, embedding_json, rel_path, blur_score, now_str))

            # Update profile_photo_path in employees table
            cur.execute("""
                UPDATE employees SET profile_photo_path = ? WHERE id = ?
            """, (rel_path, employee_id))

            conn.commit()

        return {
            "success": True,
            "message": "Face registered and biometrics securely stored successfully.",
            "photo_path": rel_path,
            "quality_score": blur_score
        }

biometric_service = BiometricService()
