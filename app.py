"""
NextFlex Project Portal — a simple, fully-functioning web server
serving project data for Project Calls 1.0 through 10.0.

Stack: FastAPI + SQLite + vanilla HTML/JS frontend.
Run: uvicorn app:app --reload --port 8000
"""

import json
import sqlite3
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

DB_PATH = Path(__file__).parent / "nextflex.db"
STATIC_DIR = Path(__file__).parent / "static"


# Auto-create the database on first boot.
# This matters on hosts with ephemeral filesystems (e.g. Render free tier),
# where the DB file is wiped on every redeploy and cold start.
def ensure_db():
    if DB_PATH.exists():
        return
    print(f"[startup] {DB_PATH} not found — initializing from init_db.py", flush=True)
    init_script = Path(__file__).parent / "init_db.py"
    result = subprocess.run(
        [sys.executable, str(init_script)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        print(f"[startup] DB init failed:\n{result.stderr}", flush=True)
        raise RuntimeError("Database initialization failed")
    print(f"[startup] DB ready: {result.stdout}", flush=True)


ensure_db()

app = FastAPI(
    title="NextFlex Project Portal",
    description="Browse, search, and analyze NextFlex Project Call data (PC 1.0–10.0)",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@contextmanager
def db():
    """SQLite connection with row factory for dict-like access."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def row_to_dict(row: sqlite3.Row) -> dict:
    """Convert a row, parsing JSON columns."""
    d = dict(row)
    for col in ("principal_investigators", "co_investigators", "industry_partners",
                "materials_used", "processes_used", "publications", "patents", "keywords"):
        if col in d and d[col]:
            try:
                d[col] = json.loads(d[col])
            except (json.JSONDecodeError, TypeError):
                d[col] = []
    return d


# ─── API Endpoints ───

@app.get("/api/health")
def health():
    """Liveness check + DB sanity."""
    try:
        with db() as conn:
            count = conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
        return {"status": "ok", "projects_in_db": count}
    except Exception as e:
        return JSONResponse(status_code=503, content={"status": "error", "detail": str(e)})


@app.get("/api/project-calls")
def list_project_calls():
    """List all Project Calls with project counts and total funding."""
    with db() as conn:
        rows = conn.execute("""
            SELECT
                project_call,
                COUNT(*) AS project_count,
                SUM(funding_amount) AS total_funding,
                MIN(start_date) AS earliest,
                MAX(end_date) AS latest
            FROM projects
            GROUP BY project_call
            ORDER BY project_call
        """).fetchall()
    return [dict(r) for r in rows]


@app.get("/api/projects")
def list_projects(
    pc: Optional[str] = Query(None, description="Filter by project call e.g. 'PC 7.1'"),
    focus: Optional[str] = Query(None, description="Filter by focus area"),
    institution: Optional[str] = Query(None, description="Filter by lead institution"),
    status: Optional[str] = Query(None, description="completed | in-progress"),
    q: Optional[str] = Query(None, description="Full-text search across title, abstract, materials, processes"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """List projects with optional filters and full-text search."""
    with db() as conn:
        if q:
            # Full-text search via FTS5 virtual table
            sql = """
                SELECT p.* FROM projects p
                JOIN projects_fts fts ON p.id = fts.id
                WHERE projects_fts MATCH ?
            """
            params = [q]
            if pc:
                sql += " AND p.project_call = ?"
                params.append(pc)
            if focus:
                sql += " AND p.focus_area = ?"
                params.append(focus)
            if institution:
                sql += " AND p.lead_institution LIKE ?"
                params.append(f"%{institution}%")
            if status:
                sql += " AND p.status = ?"
                params.append(status)
            sql += " ORDER BY rank LIMIT ? OFFSET ?"
            params.extend([limit, offset])
        else:
            conditions = ["1=1"]
            params = []
            if pc:
                conditions.append("project_call = ?")
                params.append(pc)
            if focus:
                conditions.append("focus_area = ?")
                params.append(focus)
            if institution:
                conditions.append("lead_institution LIKE ?")
                params.append(f"%{institution}%")
            if status:
                conditions.append("status = ?")
                params.append(status)
            sql = f"""
                SELECT * FROM projects
                WHERE {' AND '.join(conditions)}
                ORDER BY project_call, id
                LIMIT ? OFFSET ?
            """
            params.extend([limit, offset])

        rows = conn.execute(sql, params).fetchall()

    return {
        "count": len(rows),
        "limit": limit,
        "offset": offset,
        "results": [row_to_dict(r) for r in rows],
    }


@app.get("/api/projects/{project_id}")
def get_project(project_id: str):
    """Get a single project by ID."""
    with db() as conn:
        row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
    return row_to_dict(row)


@app.get("/api/focus-areas")
def list_focus_areas():
    """Distinct focus areas with counts."""
    with db() as conn:
        rows = conn.execute("""
            SELECT focus_area, COUNT(*) AS count
            FROM projects
            WHERE focus_area IS NOT NULL
            GROUP BY focus_area
            ORDER BY count DESC
        """).fetchall()
    return [dict(r) for r in rows]


@app.get("/api/institutions")
def list_institutions(top: int = Query(20, ge=1, le=100)):
    """Top institutions by project count."""
    with db() as conn:
        rows = conn.execute("""
            SELECT lead_institution, COUNT(*) AS count, SUM(funding_amount) AS total_funding
            FROM projects
            WHERE lead_institution IS NOT NULL
            GROUP BY lead_institution
            ORDER BY count DESC, total_funding DESC
            LIMIT ?
        """, (top,)).fetchall()
    return [dict(r) for r in rows]


@app.get("/api/stats")
def overall_stats():
    """Top-level dashboard statistics."""
    with db() as conn:
        c = conn.cursor()
        total = c.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
        funding = c.execute("SELECT SUM(funding_amount) FROM projects").fetchone()[0] or 0
        n_pc = c.execute("SELECT COUNT(DISTINCT project_call) FROM projects").fetchone()[0]
        n_inst = c.execute("SELECT COUNT(DISTINCT lead_institution) FROM projects").fetchone()[0]
        n_focus = c.execute("SELECT COUNT(DISTINCT focus_area) FROM projects").fetchone()[0]
        completed = c.execute("SELECT COUNT(*) FROM projects WHERE status = 'completed'").fetchone()[0]
        in_progress = c.execute("SELECT COUNT(*) FROM projects WHERE status = 'in-progress'").fetchone()[0]

        # Funding by year (extracted from start_date)
        by_year = c.execute("""
            SELECT substr(start_date, 1, 4) AS year, COUNT(*) AS projects, SUM(funding_amount) AS funding
            FROM projects
            WHERE start_date IS NOT NULL
            GROUP BY year
            ORDER BY year
        """).fetchall()

    return {
        "total_projects": total,
        "total_funding_usd": funding,
        "project_calls": n_pc,
        "institutions": n_inst,
        "focus_areas": n_focus,
        "completed": completed,
        "in_progress": in_progress,
        "by_year": [dict(r) for r in by_year],
    }


# ─── Static frontend ───
# Serve the frontend; FastAPI catches /api/* first, then falls through to static.
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def root():
    """Serve the SPA entry point."""
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/manager")
def manager_dashboard():
    """Serve the NextFlex Program Manager dashboard (v6 with role switcher)."""
    return FileResponse(STATIC_DIR / "manager.html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
