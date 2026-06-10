# Hockey Shot Analyzer — container recipe for Google Cloud Run (and any Docker host).
# Build:  docker build -t hockey-shot-analyzer .
# Run:    docker run -p 8000:8000 hockey-shot-analyzer
FROM python:3.10-slim

# System libraries MediaPipe/OpenCV and the video re-encoder (ffmpeg) need.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        libgl1 \
        libglib2.0-0 \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first so Docker can cache this layer.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the app.
COPY . .

# Download the pose-detection model at build time (it's gitignored, ~6 MB).
RUN curl -fsSL -o backend/pose_landmarker.task \
    https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task

# Cloud Run sends traffic to $PORT (defaults to 8080); fall back to 8000 locally.
ENV PORT=8000
EXPOSE 8000

# Start the server. main.py finds the frontend relative to its own location,
# so running from backend/ works regardless of WORKDIR.
CMD ["sh", "-c", "cd backend && uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
