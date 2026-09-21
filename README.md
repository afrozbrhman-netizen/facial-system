# Attendance Management Studio 2.0
> **Enterprise Face Biometrics & Attendance Monitoring System**

A modern AI-powered attendance system featuring deep facial biometrics (128-d ResNet embeddings), anti-spoofing liveness detection (Eye-Aspect-Ratio + Laplacian blur filtering), role-based access control (Admin, Faculty/HR, Student/Employee), and real-time multi-frame verification.

---

## 🌟 Key Features

- **Biometric AI Recognition**: 128-dimensional deep metric embeddings with calibrated Euclidean distance matching.
- **Anti-Spoofing & Liveness**: Dual-stage verification with blink detection (EAR) and texture sharpness validation (Laplacian variance) to prevent photo/screen spoofing.
- **Role-Based Portals**:
  - **Administrator**: User management, system audit trail, shift & late-marking rules, department configuration.
  - **Faculty / HR**: Real-time camera kiosk terminal, student directory, manual attendance override, Excel reports.
  - **Student / Employee**: Individual attendance logs, monthly percentage analytics, and shift breakdown.
- **Cloud & Container Ready**: Includes production `Dockerfile` and `render.yaml` for 1-click cloud deployment.

---

## 🚀 Quick Start (Local)

### Prerequisites
- Python 3.10+
- Webcam

### Installation
```bash
pip install -r requirements.txt
```

### Run Server
```bash
python run_server.py
```
Or double-click `run_web_server.bat` on Windows.
Access the web terminal at: **http://localhost:5000**

### Default Accounts
| Role | Username | Password |
|---|---|---|
| **Admin** | `admin` | `Admin@123` |
| **Faculty / HR** | `teacher` | `Teacher@123` |
| **Student** | `EMP001` | `Student@123` |

---

## 🐳 Cloud Deployment (Render / Docker)

This repository includes a pre-configured `Dockerfile` and `render.yaml` for deployment on **[Render](https://render.com)**:
1. Connect this repository to Render as a **Web Service**.
2. Render will automatically detect the `Dockerfile` and launch with Gunicorn.
3. Access your live attendance portal over HTTPS!
