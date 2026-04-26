import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from db.database import init_db
from routers.auth    import router as auth_router
from routers.classes import router as classes_router
from routers.data    import router as data_router
from routers.reports import router as reports_router

app = FastAPI(title="AttentionAI Classroom API v2")

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.on_event("startup")
def startup():
    init_db()

app.include_router(auth_router,    prefix="")
app.include_router(classes_router, prefix="")
app.include_router(data_router,    prefix="")
app.include_router(reports_router, prefix="")

@app.get("/api/health")
def health():
    return {"status": "ok", "version": "2.0"}

# ── Serve frontend ──
# Works both locally (../frontend) and in Docker (/app/frontend)
_here = os.path.dirname(__file__)
FRONTEND = os.path.join(_here, "..", "frontend")
if not os.path.exists(FRONTEND):
    FRONTEND = os.path.join(_here, "..", "..", "frontend")  # fallback
if os.path.exists(FRONTEND):
    app.mount("/static", StaticFiles(directory=os.path.join(FRONTEND, "static")), name="static")

    @app.get("/")
    def idx():  return FileResponse(os.path.join(FRONTEND, "index.html"))
    @app.get("/teacher")
    def tch():  return FileResponse(os.path.join(FRONTEND, "teacher.html"))
    @app.get("/student")
    def stu():  return FileResponse(os.path.join(FRONTEND, "student.html"))
    @app.get("/reports")
    def rep():  return FileResponse(os.path.join(FRONTEND, "reports.html"))
    # .html aliases for direct navigation
    @app.get("/teacher.html")
    def tch2(): return FileResponse(os.path.join(FRONTEND, "teacher.html"))
    @app.get("/student.html")
    def stu2(): return FileResponse(os.path.join(FRONTEND, "student.html"))
    @app.get("/reports.html")
    def rep2(): return FileResponse(os.path.join(FRONTEND, "reports.html"))
    @app.get("/index.html")
    def idx2(): return FileResponse(os.path.join(FRONTEND, "index.html"))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=7860, reload=True)
