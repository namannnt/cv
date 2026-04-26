FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend
COPY . .

# Copy frontend (relative to build context = attentionai-classroom/)
COPY ../frontend /app/../frontend

# Persistent storage for SQLite
RUN mkdir -p /data

ENV DATABASE_URL=/data/classroom.db

EXPOSE 7860

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860"]
