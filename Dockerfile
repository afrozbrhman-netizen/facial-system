# Base Python Image
FROM python:3.10-slim

# Prevents Python from writing pyc files and buffering stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=10000
ENV CMAKE_BUILD_PARALLEL_LEVEL=1

# Install system libraries needed by OpenCV, Dlib, Git, and CMake
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    git \
    libopenblas-dev \
    liblapack-dev \
    libgl1 \
    libglib2.0-0 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Upgrade packaging tools (pin setuptools<70.0.0 to retain pkg_resources needed by face_recognition)
RUN pip install --no-cache-dir --upgrade pip wheel && \
    pip install --no-cache-dir "setuptools<70.0.0"

# Install precompiled binary dlib to avoid 12+ min C++ compilation and out-of-memory errors
RUN pip install --no-cache-dir dlib-bin

# Install official face_recognition_models and face-recognition
RUN pip install --no-cache-dir face-recognition-models
RUN pip install --no-cache-dir --no-deps face-recognition

# Copy dependency requirements first to leverage Docker caching
COPY requirements.txt .

# Install remaining dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy all application files
COPY . .

# Expose standard Render port
EXPOSE 10000

# Run with Gunicorn production server bound to dynamic $PORT (defaults to 10000 on Render)
CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT:-10000} --workers 1 --threads 4 --timeout 120 run_server:app"]

