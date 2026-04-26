---
title: AttentionAI Classroom Backend
emoji: 🧠
colorFrom: blue
colorTo: purple
sdk: docker
pinned: false
---

# AttentionAI Classroom Backend

FastAPI backend for the AttentionAI Classroom system.

## Environment Variables (set in HF Space secrets)

| Variable | Description |
|---|---|
| `SECRET_KEY` | JWT signing secret (use a long random string) |
| `DATABASE_URL` | SQLite path — use `/data/classroom.db` for persistence |

## API Endpoints

- `POST /auth/register` — Teacher registration
- `POST /auth/login` — Teacher login → JWT
- `POST /batches` — Create batch
- `GET /batches` — List teacher's batches
- `POST /batches/{id}/sessions/start` — Start session
- `POST /batches/{id}/sessions/end` — End session
- `POST /students/join` — Student join by name + class code
- `POST /send-data` — CV engine data ingestion
- `GET /class-data/{class_code}` — Live class snapshot
- `GET /reports/sessions/{batch_id}` — Session history
- `GET /reports/students/{batch_id}` — Student summaries
- `GET /student-history` — Student's own history
