FROM python:3.11-slim

WORKDIR /app

# Install backend dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend source
COPY backend/ ./backend/

# Copy frontend
COPY frontend/ ./frontend/

# Set working directory to backend (where app.py lives)
WORKDIR /app/backend

# Persistent storage for SQLite
RUN mkdir -p /data

ENV DATABASE_URL=/data/classroom.db

EXPOSE 7860

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860"]
