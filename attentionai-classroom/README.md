---
title: AttentionAI Classroom
emoji: 🧠
colorFrom: blue
colorTo: purple
sdk: docker
pinned: false
---

# AttentionAI Classroom

Real-time attention monitoring for online classrooms.

- Teachers create batches, start sessions, and monitor students live
- Students join via class code and monitoring runs entirely in the browser (no install needed)
- Detailed post-session reports with distraction episodes, fatigue onset, attention timeline

## Environment Variables (set in HF Space secrets)

| Variable | Description |
|---|---|
| `SECRET_KEY` | JWT signing secret (required) |
| `DATABASE_URL` | SQLite path — defaults to `/data/classroom.db` |
