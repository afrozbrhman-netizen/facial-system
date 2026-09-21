import os
import secrets

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "enterprise_attendance_studio_secret_2026_x7k9")
    JWT_SECRET = os.environ.get("JWT_SECRET", "enterprise_attendance_studio_jwt_token_2026_m4p2")
    JWT_EXPIRATION_HOURS = int(os.environ.get("JWT_EXPIRATION_HOURS", 24))
    
    # Database
    DB_PATH = os.path.join(BASE_DIR, "attendance.db")
    
    # Biometric directories
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
    TRAINING_IMAGE_DIR = os.path.join(BASE_DIR, "TrainingImage")
    TRAINER_FILE = os.path.join(BASE_DIR, "TrainingImageLabel", "Trainer.yml")
    HAARCASCADE_FILE = os.path.join(BASE_DIR, "haarcascade_frontalface_default.xml")
    
    # Reports & Exports
    EXCEL_ATTENDANCE_FILE = os.path.join(BASE_DIR, "Attendance", "Attendance.xlsx")
    EXCEL_STUDENT_FILE = os.path.join(BASE_DIR, "StudentDetails", "StudentDetails.xlsx")
    
    # Recognition tolerances
    FACE_MATCH_TOLERANCE = float(os.environ.get("FACE_MATCH_TOLERANCE", 0.52))  # dlib distance: lower = stricter
    LIVENESS_EAR_THRESHOLD = float(os.environ.get("LIVENESS_EAR_THRESHOLD", 0.22)) # Eye Aspect Ratio for blink
    LIVENESS_BLUR_THRESHOLD = float(os.environ.get("LIVENESS_BLUR_THRESHOLD", 60.0)) # Laplacian variance

os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
