"""
NextFlex Project Portal — comprehensive secured FastAPI server.

All HTML pages and /api/* endpoints require authentication except:
  - /manager/login, /api/auth/login, /api/health, /static/*

GraphRAG endpoint uses Anthropic LLM if ANTHROPIC_API_KEY is set,
otherwise returns deterministic retrieval-only synthesis.
"""

import json
import os
import re
import sqlite3
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Request, Response, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import auth

DB_PATH = Path(__file__).parent / "nextflex.db"
STATIC_DIR = Path(__file__).parent / "static"


def ensure_db():
    if DB_PATH.exists():
        return
    print(f"[startup] Initializing DB", flush=True)
    init_script = Path(__file__).parent / "init_db.py"
    result = subprocess.run([sys.executable, str(init_script)], capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[startup] DB init failed:\n{result.stderr}", flush=True)
        raise RuntimeError("Database initialization failed")
    print(f"[startup] {result.stdout}", flush=True)


def ensure_synthetic_file_chunks():
    """Index synthetic PDF/PPTX content into chunks at startup so GraphRAG
    queries hit ontology-grounded file content."""
    try:
        from synthetic_files import index_file_chunks_to_db
        index_file_chunks_to_db()
    except Exception as e:
        print(f"[startup] WARNING: synthetic file chunk indexing failed: {e}", flush=True)


def ensure_public_dataset():
    """Index real NextFlex papers + funded assets at startup.

    Reads pre-extracted text from public_data/extracted_corpus.json
    (built offline via build_extracted_corpus.py). No pypdf or
    python-pptx at runtime, so memory stays under 100 MB.
    """
    try:
        from public_dataset import index_public_dataset
        index_public_dataset()
    except Exception as e:
        print(f"[startup] WARNING: public dataset indexing failed: {e}",
              flush=True)


ensure_db()
ensure_synthetic_file_chunks()
ensure_public_dataset()

app = FastAPI(title="NextFlex Project Portal", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
    allow_credentials=True,
)


@contextmanager
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def parse_json_field(val):
    if not val:
        return []
    try:
        return json.loads(val)
    except (json.JSONDecodeError, TypeError):
        return []


def row_to_dict(row):
    d = dict(row)
    for col in ("principal_investigators", "co_investigators", "industry_partners",
                "materials_used", "processes_used", "publications", "patents",
                "keywords", "properties", "source_project_ids", "notable_orgs",
                "program_offices"):
        if col in d:
            d[col] = parse_json_field(d[col])
    return d


# ────────── Site-wide auth gate ──────────

OPEN_PATHS = {"/manager/login", "/api/auth/login", "/api/health", "/favicon.ico"}


@app.middleware("http")
async def auth_gate(request: Request, call_next):
    path = request.url.path
    if path.startswith("/static/") or path in OPEN_PATHS:
        return await call_next(request)
    user = auth.current_user(request)
    if not user:
        if path.startswith("/api/"):
            return JSONResponse({"detail": "not_authenticated"}, status_code=401)
        return RedirectResponse(url="/manager/login", status_code=302)
    request.state.user = user
    return await call_next(request)


# ────────── Auth endpoints ──────────

@app.post("/api/auth/login")
def login(response: Response, username: str = Form(...), password: str = Form(...)):
    user = auth.authenticate(username.strip(), password)
    if not user:
        raise HTTPException(status_code=401, detail="invalid_credentials")
    token = auth.issue_token(user)
    response.set_cookie(
        key=auth.COOKIE_NAME, value=token,
        max_age=auth.JWT_EXPIRY_HOURS * 3600,
        httponly=True, secure=True, samesite="strict", path="/",
    )
    return {k: user[k] for k in ("username", "role", "display_name", "title", "avatar")}


@app.post("/api/auth/logout")
def logout(response: Response):
    response.delete_cookie(key=auth.COOKIE_NAME, path="/")
    return {"status": "logged_out"}


@app.get("/api/auth/whoami")
def whoami(request: Request):
    return request.state.user


# ────────── Pages ──────────

@app.get("/manager/login")
def login_page(request: Request):
    if auth.current_user(request):
        return RedirectResponse(url="/", status_code=302)
    return FileResponse(STATIC_DIR / "login.html")


@app.get("/")
def root():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/manager")
def manager():
    return FileResponse(STATIC_DIR / "manager.html")


@app.get("/api/health")
def health():
    import time, os
    t0 = time.time()
    try:
        with db() as conn:
            count = conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
            chunks = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
            entities = conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
        latency_ms = round((time.time() - t0) * 1000, 1)
        return {
            "status": "ok",
            "projects": count,
            "chunks": chunks,
            "entities": entities,
            "latency_ms": latency_ms,
            "build": os.environ.get("RENDER_GIT_COMMIT", "dev")[:7] or "dev",
            "version": "2.1.0",
            "llm_enabled": bool(os.environ.get("ANTHROPIC_API_KEY")),
        }
    except Exception as e:
        return JSONResponse({"status": "error", "detail": str(e)}, status_code=503)


# ────────── Role-scoped data endpoints ──────────

def role_classifications(role: str) -> list[str]:
    if role == "admin":
        return ["public", "member_share", "mission_relevant", "cui"]
    if role == "dow":
        return ["public", "mission_relevant", "cui"]
    if role == "member":
        return ["public", "member_share"]
    return ["public"]


@app.get("/api/stats")
def overall_stats(request: Request):
    user = request.state.user
    cls = role_classifications(user["role"])
    ph = ",".join("?" * len(cls))
    with db() as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM projects WHERE classification IN ({ph})", cls).fetchone()[0]
        funding = conn.execute(f"SELECT SUM(funding_amount) FROM projects WHERE classification IN ({ph})", cls).fetchone()[0] or 0
        n_pc = conn.execute(f"SELECT COUNT(DISTINCT project_call) FROM projects WHERE classification IN ({ph})", cls).fetchone()[0]
        n_inst = conn.execute(f"SELECT COUNT(DISTINCT lead_institution) FROM projects WHERE classification IN ({ph})", cls).fetchone()[0]
        n_focus = conn.execute(f"SELECT COUNT(DISTINCT focus_area) FROM projects WHERE classification IN ({ph})", cls).fetchone()[0]
        n_ent = conn.execute(f"SELECT COUNT(*) FROM entities WHERE classification IN ({ph})", cls).fetchone()[0]
        n_rel = conn.execute("SELECT COUNT(*) FROM relationships").fetchone()[0]
        n_chunks = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        n_districts = conn.execute("SELECT COUNT(*) FROM districts WHERE project_count > 0").fetchone()[0]
        n_deploy = conn.execute("SELECT COUNT(*) FROM deployments").fetchone()[0]
        n_peos = conn.execute("SELECT COUNT(*) FROM peos").fetchone()[0]
        by_year = conn.execute(f"""
            SELECT substr(start_date, 1, 4) AS year, COUNT(*) AS projects, SUM(funding_amount) AS funding
            FROM projects WHERE classification IN ({ph})
            GROUP BY year ORDER BY year
        """, cls).fetchall()
    return {
        "total_projects": total, "total_funding_usd": funding,
        "project_calls": n_pc, "institutions": n_inst, "focus_areas": n_focus,
        "entities": n_ent, "relationships": n_rel, "chunks": n_chunks,
        "districts": n_districts, "deployments": n_deploy, "peos": n_peos,
        "by_year": [dict(r) for r in by_year],
        "role": user["role"],
    }


@app.get("/api/project-calls")
def list_project_calls(request: Request):
    cls = role_classifications(request.state.user["role"])
    ph = ",".join("?" * len(cls))
    with db() as conn:
        rows = conn.execute(f"""
            SELECT project_call, COUNT(*) AS project_count, SUM(funding_amount) AS total_funding,
                   MIN(start_date) AS earliest, MAX(end_date) AS latest
            FROM projects WHERE classification IN ({ph})
            GROUP BY project_call ORDER BY project_call
        """, cls).fetchall()
    return [dict(r) for r in rows]


@app.get("/api/projects")
def list_projects(
    request: Request,
    pc: Optional[str] = None, focus: Optional[str] = None,
    institution: Optional[str] = None, status: Optional[str] = None,
    district: Optional[str] = None, peo: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0),
):
    cls = role_classifications(request.state.user["role"])
    cph = ",".join("?" * len(cls))
    with db() as conn:
        if q:
            tokens = re.findall(r"[A-Za-z0-9]+", q)
            if not tokens:
                return {"count": 0, "limit": limit, "offset": offset, "results": []}
            fts_query = " ".join(f'"{t}"' for t in tokens)
            sql = f"""
                SELECT p.* FROM projects p JOIN projects_fts fts ON p.id = fts.id
                WHERE projects_fts MATCH ? AND p.classification IN ({cph})
            """
            params = [fts_query] + cls
            order_clause = " ORDER BY rank"
        else:
            sql = f"SELECT * FROM projects WHERE classification IN ({cph})"
            params = list(cls)
            order_clause = " ORDER BY project_call, id"
        if pc:
            sql += " AND project_call = ?"; params.append(pc)
        if focus:
            sql += " AND focus_area = ?"; params.append(focus)
        if institution:
            sql += " AND lead_institution LIKE ?"; params.append(f"%{institution}%")
        if status:
            sql += " AND status = ?"; params.append(status)
        if district:
            sql += " AND congressional_district = ?"; params.append(district)
        if peo:
            sql += " AND peo = ?"; params.append(peo)
        sql += order_clause + " LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = conn.execute(sql, params).fetchall()
    return {"count": len(rows), "limit": limit, "offset": offset,
            "results": [row_to_dict(r) for r in rows]}


@app.get("/api/projects/{project_id}")
def get_project(project_id: str, request: Request):
    cls = role_classifications(request.state.user["role"])
    with db() as conn:
        row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="not_found")
    proj = row_to_dict(row)
    if proj["classification"] not in cls:
        raise HTTPException(status_code=403, detail="not_authorized")
    return proj


@app.get("/api/projects/{project_id}/report")
def project_report(project_id: str, request: Request):
    cls = role_classifications(request.state.user["role"])
    with db() as conn:
        prow = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if not prow:
            raise HTTPException(status_code=404, detail="not_found")
        proj = row_to_dict(prow)
        if proj["classification"] not in cls:
            raise HTTPException(status_code=403, detail="not_authorized")
        chunks = conn.execute(
            "SELECT id, section, page, text FROM chunks WHERE project_id = ? ORDER BY page",
            (project_id,)
        ).fetchall()
    return {"project": proj, "chunks": [dict(c) for c in chunks]}


@app.get("/api/projects/{project_id}/files")
def project_files_list(project_id: str, request: Request):
    """Return metadata about the synthetic PDF + PPTX for a project."""
    cls = role_classifications(request.state.user["role"])
    with db() as conn:
        prow = conn.execute(
            "SELECT id, classification, title FROM projects WHERE id = ?",
            (project_id,)
        ).fetchone()
    if not prow:
        raise HTTPException(status_code=404, detail="not_found")
    if prow["classification"] not in cls:
        raise HTTPException(status_code=403, detail="not_authorized")
    return {
        "project_id": project_id,
        "title": prow["title"],
        "files": [
            {"kind": "pdf", "name": f"{project_id}-final-report.pdf",
             "url": f"/api/projects/{project_id}/files/pdf",
             "description": "Final Report PDF (5-7 pages, ontology-classified materials/processes/results)"},
            {"kind": "pptx", "name": f"{project_id}-briefing.pptx",
             "url": f"/api/projects/{project_id}/files/pptx",
             "description": "Project Briefing PPTX (8 slides, executive summary through transition pathway)"},
        ],
    }


@app.get("/api/projects/{project_id}/files/{kind}")
def project_file_download(project_id: str, kind: str, request: Request):
    """Stream the synthetic PDF or PPTX file for a project."""
    if kind not in ("pdf", "pptx"):
        raise HTTPException(status_code=400, detail="kind_must_be_pdf_or_pptx")

    cls = role_classifications(request.state.user["role"])
    with db() as conn:
        prow = conn.execute(
            "SELECT classification FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
    if not prow:
        raise HTTPException(status_code=404, detail="not_found")
    if prow["classification"] not in cls:
        raise HTTPException(status_code=403, detail="not_authorized")

    try:
        from synthetic_files import get_or_generate_files
        pdf_path, pptx_path = get_or_generate_files(project_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"generation_failed: {e}")

    file_path = pdf_path if kind == "pdf" else pptx_path
    media_type = "application/pdf" if kind == "pdf" else \
        "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    filename = f"{project_id}-{'final-report' if kind == 'pdf' else 'briefing'}.{kind}"

    return FileResponse(file_path, media_type=media_type, filename=filename)


@app.get("/api/focus-areas")
def list_focus_areas(request: Request):
    cls = role_classifications(request.state.user["role"])
    ph = ",".join("?" * len(cls))
    with db() as conn:
        rows = conn.execute(f"""
            SELECT focus_area, COUNT(*) AS count FROM projects
            WHERE focus_area IS NOT NULL AND classification IN ({ph})
            GROUP BY focus_area ORDER BY count DESC
        """, cls).fetchall()
    return [dict(r) for r in rows]


@app.get("/api/institutions")
def list_institutions(request: Request, top: int = Query(20, ge=1, le=100)):
    cls = role_classifications(request.state.user["role"])
    ph = ",".join("?" * len(cls))
    with db() as conn:
        rows = conn.execute(f"""
            SELECT lead_institution, COUNT(*) AS count, SUM(funding_amount) AS total_funding
            FROM projects WHERE lead_institution IS NOT NULL AND classification IN ({ph})
            GROUP BY lead_institution ORDER BY count DESC LIMIT ?
        """, cls + [top]).fetchall()
    return [dict(r) for r in rows]


@app.get("/api/entity-counts")
def entity_counts_by_type(request: Request):
    """Return counts grouped by ontology type and subtype, role-scoped."""
    cls = role_classifications(request.state.user["role"])
    ph = ",".join("?" * len(cls))
    with db() as conn:
        by_type = conn.execute(f"""
            SELECT type, COUNT(*) AS count FROM entities
            WHERE classification IN ({ph})
            GROUP BY type ORDER BY count DESC
        """, cls).fetchall()
        by_subtype = conn.execute(f"""
            SELECT type, subtype, COUNT(*) AS count FROM entities
            WHERE classification IN ({ph}) AND subtype IS NOT NULL
            GROUP BY type, subtype ORDER BY type, count DESC
        """, cls).fetchall()
    return {
        "by_type": [dict(r) for r in by_type],
        "by_subtype": [dict(r) for r in by_subtype],
    }


@app.get("/api/entities")
def list_entities(request: Request,
                  type: Optional[str] = None, subtype: Optional[str] = None,
                  q: Optional[str] = None, limit: int = Query(100, ge=1, le=500)):
    cls = role_classifications(request.state.user["role"])
    ph = ",".join("?" * len(cls))
    sql = f"SELECT * FROM entities WHERE classification IN ({ph})"
    params = list(cls)
    if type:
        sql += " AND type = ?"; params.append(type)
    if subtype:
        sql += " AND subtype = ?"; params.append(subtype)
    if q:
        sql += " AND name LIKE ?"; params.append(f"%{q}%")
    sql += " ORDER BY type, name LIMIT ?"
    params.append(limit)
    with db() as conn:
        rows = conn.execute(sql, params).fetchall()
    return {"count": len(rows), "results": [row_to_dict(r) for r in rows]}


@app.get("/api/entities/{entity_id}")
def get_entity(entity_id: str, request: Request):
    cls = role_classifications(request.state.user["role"])
    with db() as conn:
        row = conn.execute("SELECT * FROM entities WHERE id = ?", (entity_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="not_found")
        ent = row_to_dict(row)
        if ent["classification"] not in cls:
            raise HTTPException(status_code=403, detail="not_authorized")
        rels_out = conn.execute("""
            SELECT r.rel_type, r.confidence, e.id, e.name, e.type, e.subtype
            FROM relationships r JOIN entities e ON r.to_id = e.id
            WHERE r.from_id = ? LIMIT 50
        """, (entity_id,)).fetchall()
        rels_in = conn.execute("""
            SELECT r.rel_type, r.confidence, e.id, e.name, e.type, e.subtype
            FROM relationships r JOIN entities e ON r.from_id = e.id
            WHERE r.to_id = ? LIMIT 50
        """, (entity_id,)).fetchall()
        ent["outgoing"] = [dict(r) for r in rels_out]
        ent["incoming"] = [dict(r) for r in rels_in]
    return ent


@app.get("/api/districts")
def list_districts(request: Request):
    with db() as conn:
        rows = conn.execute("""
            SELECT * FROM districts WHERE project_count > 0
            ORDER BY project_count DESC, total_funding DESC
        """).fetchall()
    return [row_to_dict(r) for r in rows]


@app.get("/api/deployments")
def list_deployments(request: Request):
    with db() as conn:
        rows = conn.execute("SELECT * FROM deployments ORDER BY deploy_date DESC").fetchall()
    return [row_to_dict(r) for r in rows]


@app.get("/api/peos")
def list_peos(request: Request):
    with db() as conn:
        rows = conn.execute("SELECT * FROM peos ORDER BY active_programs DESC").fetchall()
    return [row_to_dict(r) for r in rows]


# ────────── GraphRAG ──────────

class GraphRAGRequest(BaseModel):
    question: str


def retrieve_chunks(conn, question: str, classifications: list, top_k: int = 6):
    """Hybrid retrieval: pull top-ranked chunks across narrative + synthetic
    PDF/PPTX + real public dataset chunks so GraphRAG responses cite a
    diversity of sources."""
    tokens = re.findall(r"[A-Za-z0-9]+", question)
    if not tokens:
        return []
    fts_query = " OR ".join(f'"{t}"' for t in tokens)
    cph = ",".join("?" * len(classifications))

    # Public-dataset chunks have classification='public_dataset' which isn't
    # in any persona's whitelist. Add it so all roles can see public papers.
    full_classifications = list(classifications) + ["public_dataset"]
    full_cph = ",".join("?" * len(full_classifications))

    def fetch(section_clause, k):
        # LEFT JOIN both projects and public_assets, COALESCE the metadata
        sql = f"""
            SELECT c.id, c.text, c.section, c.page, c.project_id, c.classification,
                   COALESCE(p.title, pa.title) AS project_title,
                   COALESCE(p.project_call, pa.project_call) AS project_call,
                   COALESCE(p.lead_institution, pa.category) AS lead_institution,
                   COALESCE(p.focus_area, pa.subtype) AS focus_area,
                   COALESCE(p.congressional_district, '') AS congressional_district
            FROM chunks_fts fts
            JOIN chunks c ON c.id = fts.id
            LEFT JOIN projects p ON p.id = c.project_id
            LEFT JOIN public_assets pa ON pa.id = c.project_id
            WHERE chunks_fts MATCH ?
              AND (p.classification IN ({cph}) OR pa.id IS NOT NULL)
              AND c.classification IN ({full_cph})
              {section_clause}
            ORDER BY rank LIMIT ?
        """
        params = [fts_query] + classifications + full_classifications + [k]
        return conn.execute(sql, params).fetchall()

    # Diversify across four buckets: synthetic PDF, synthetic PPTX, real public, narrative
    quarter = max(1, top_k // 4)
    pdf_rows = fetch("AND c.section LIKE 'pdf:%'", quarter)
    pptx_rows = fetch("AND c.section LIKE 'pptx:%'", quarter)
    public_rows = fetch("AND c.section LIKE 'public:%'", quarter)
    narr_rows = fetch(
        "AND c.section NOT LIKE 'pdf:%' AND c.section NOT LIKE 'pptx:%' "
        "AND c.section NOT LIKE 'public:%'",
        max(1, top_k - len(pdf_rows) - len(pptx_rows) - len(public_rows)),
    )

    seen_ids = set()
    combined = []
    for batch in (pdf_rows, pptx_rows, public_rows, narr_rows):
        for r in batch:
            if r["id"] not in seen_ids:
                combined.append(r); seen_ids.add(r["id"])

    if len(combined) < top_k:
        for extra in fetch("", top_k * 2):
            if extra["id"] not in seen_ids:
                combined.append(extra); seen_ids.add(extra["id"])
                if len(combined) >= top_k:
                    break

    return [dict(r) for r in combined[:top_k]]


def retrieve_graph_context(conn, chunks):
    project_ids = list({c["project_id"] for c in chunks})
    if not project_ids:
        return []
    pid_set = set(project_ids)
    related = []
    for e in conn.execute("SELECT id, name, type, subtype, source_project_ids FROM entities").fetchall():
        srcs = parse_json_field(e["source_project_ids"])
        if any(s in pid_set for s in srcs):
            related.append({"id": e["id"], "name": e["name"], "type": e["type"], "subtype": e["subtype"]})
            if len(related) >= 20:
                break
    return related


def synthesize_offline(question, chunks, graph_ctx, role):
    if not chunks:
        return ("I couldn't find any source material matching your question in the corpus "
                "you have access to. Try simpler keywords like 'silver ink', 'phased array', "
                "'Kapton', or 'BST dielectric'.")
    pcs = sorted({c["project_call"] for c in chunks})
    insts = sorted({c["lead_institution"] for c in chunks if c["lead_institution"]})
    ent_names = ", ".join(e["name"] for e in graph_ctx[:6]) or "various entities"
    sections = sorted({c["section"] for c in chunks})
    return (
        f"Based on retrieval across {len(chunks)} source chunks from {len(pcs)} project call(s) "
        f"({', '.join(pcs)}), I found relevant material spanning {', '.join(sections)} sections. "
        f"Lead institutions involved: {', '.join(insts[:3])}{' and others' if len(insts) > 3 else ''}. "
        f"The knowledge graph links these projects to entities including {ent_names}. "
        f"Specific source citations are listed below."
    )


def synthesize_llm(question, chunks, graph_ctx, role):
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return synthesize_offline(question, chunks, graph_ctx, role)
    try:
        from anthropic import Anthropic
    except ImportError:
        return synthesize_offline(question, chunks, graph_ctx, role)

    client = Anthropic(api_key=api_key)
    chunk_block = "\n\n".join(
        f"[{i+1}] (PC {c['project_call']}, {c['lead_institution']}, p.{c['page']}, section: {c['section']})\n{c['text']}"
        for i, c in enumerate(chunks)
    )
    graph_block = ", ".join(f"{e['name']} ({e['type']})" for e in graph_ctx[:10]) or "(none)"
    role_guidance = {
        "admin": "You have full access. Answer comprehensively.",
        "dow": "Focus on mission relevance, RF performance, and acquisition pathways.",
        "member": "Focus on technical materials, processes, and performance characterization.",
    }.get(role, "")
    system = (
        "You are the NextFlex Project Portal GraphRAG assistant. "
        "Answer using ONLY the provided source chunks. "
        "Cite sources inline using [N] notation matching the chunk numbers. "
        "Be concise (3-5 sentences). Do not invent data. " + role_guidance
    )
    user_msg = (
        f"Question: {question}\n\n"
        f"Knowledge graph entities: {graph_block}\n\n"
        f"Source chunks:\n{chunk_block}\n\n"
        f"Provide your answer with inline citations."
    )
    try:
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=600, system=system,
            messages=[{"role": "user", "content": user_msg}],
        )
        return resp.content[0].text
    except Exception as e:
        print(f"[graphrag] LLM call failed: {e}", flush=True)
        return synthesize_offline(question, chunks, graph_ctx, role)


@app.post("/api/graphrag")
def graphrag(req: GraphRAGRequest, request: Request):
    user = request.state.user
    cls = role_classifications(user["role"])
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="empty_question")
    with db() as conn:
        chunks = retrieve_chunks(conn, req.question, cls, top_k=8)
        graph_ctx = retrieve_graph_context(conn, chunks)
    has_llm = bool(os.environ.get("ANTHROPIC_API_KEY"))
    if has_llm:
        answer = synthesize_llm(req.question, chunks, graph_ctx, user["role"])
        mode = "llm"
    else:
        answer = synthesize_offline(req.question, chunks, graph_ctx, user["role"])
        mode = "retrieval-only"
    citations = [
        {"n": i + 1, "chunk_id": c["id"], "project_id": c["project_id"],
         "project_title": c["project_title"], "project_call": c["project_call"],
         "lead_institution": c["lead_institution"], "focus_area": c["focus_area"],
         "section": c["section"], "page": c["page"],
         "source_type": (
             "public" if c["section"].startswith("public:")
             else "pdf" if c["section"].startswith("pdf:")
             else "pptx" if c["section"].startswith("pptx:")
             else "narrative"
         ),
         "snippet": c["text"][:280] + ("..." if len(c["text"]) > 280 else "")}
        for i, c in enumerate(chunks)
    ]
    pdf_count = sum(1 for c in citations if c["source_type"] == "pdf")
    pptx_count = sum(1 for c in citations if c["source_type"] == "pptx")
    public_count = sum(1 for c in citations if c["source_type"] == "public")
    narrative_count = len(citations) - pdf_count - pptx_count - public_count
    return {
        "question": req.question, "answer": answer, "mode": mode,
        "citations": citations, "graph_entities": graph_ctx,
        "source_breakdown": {
            "pdf": pdf_count, "pptx": pptx_count,
            "public": public_count, "narrative": narrative_count,
        },
    }


# ────────── Public NextFlex Dataset ──────────

PUBLIC_DATA_ROOT = Path(__file__).parent / "public_data"


@app.get("/api/public-dataset/stats")
def public_dataset_stats(request: Request):
    """Counts grouped by category for the real NextFlex dataset."""
    with db() as conn:
        total = conn.execute("SELECT COUNT(*) FROM public_assets").fetchone()[0]
        with_files = conn.execute(
            "SELECT COUNT(*) FROM public_assets WHERE has_local_file=1"
        ).fetchone()[0]
        size = conn.execute(
            "SELECT SUM(file_size_bytes) FROM public_assets WHERE has_local_file=1"
        ).fetchone()[0] or 0
        chunks = conn.execute(
            "SELECT COUNT(*) FROM chunks WHERE classification='public_dataset'"
        ).fetchone()[0]
        by_cat = conn.execute("""
            SELECT category, COUNT(*) AS n,
                   SUM(has_local_file) AS with_files,
                   COALESCE(SUM(file_size_bytes), 0) AS size
            FROM public_assets GROUP BY category ORDER BY n DESC
        """).fetchall()
        by_year = conn.execute("""
            SELECT year, COUNT(*) AS n FROM public_assets
            WHERE year IS NOT NULL GROUP BY year ORDER BY year
        """).fetchall()
        agreements = conn.execute("""
            SELECT agreement_numbers, COUNT(*) AS n FROM public_assets
            WHERE agreement_numbers IS NOT NULL AND agreement_numbers != ''
            GROUP BY agreement_numbers ORDER BY n DESC LIMIT 20
        """).fetchall()
    return {
        "total_assets": total,
        "with_local_files": with_files,
        "manifest_only": total - with_files,
        "total_size_bytes": size,
        "indexed_chunks": chunks,
        "by_category": [dict(r) for r in by_cat],
        "by_year": [dict(r) for r in by_year],
        "agreements": [dict(r) for r in agreements],
    }


@app.get("/api/public-dataset/list")
def public_dataset_list(
    request: Request,
    category: Optional[str] = None,
    year: Optional[int] = None,
    pc: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """List public dataset assets with optional filters and FTS search."""
    with db() as conn:
        if q:
            tokens = re.findall(r"[A-Za-z0-9]+", q)
            if not tokens:
                return {"count": 0, "results": []}
            fts_query = " ".join(f'"{t}"' for t in tokens)
            sql = """
                SELECT a.* FROM public_assets a
                JOIN public_assets_fts fts ON a.id = fts.id
                WHERE public_assets_fts MATCH ?
            """
            params = [fts_query]
            order = " ORDER BY rank"
        else:
            sql = "SELECT * FROM public_assets WHERE 1=1"
            params = []
            order = " ORDER BY year DESC, title"

        if category:
            sql += " AND category = ?"; params.append(category)
        if year:
            sql += " AND year = ?"; params.append(year)
        if pc:
            sql += " AND project_call = ?"; params.append(pc)

        sql += order + " LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = conn.execute(sql, params).fetchall()
    return {
        "count": len(rows),
        "limit": limit, "offset": offset,
        "results": [dict(r) for r in rows],
    }


@app.get("/api/public-dataset/{asset_id}")
def public_dataset_detail(asset_id: str, request: Request):
    """Get metadata for one public asset."""
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM public_assets WHERE id = ?", (asset_id,)
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="not_found")
    asset = dict(row)
    # Add chunk count and file URL
    with db() as conn:
        n_chunks = conn.execute(
            "SELECT COUNT(*) FROM chunks WHERE project_id = ?",
            (asset_id,)
        ).fetchone()[0]
    asset["indexed_chunks"] = n_chunks
    if asset.get("has_local_file"):
        asset["download_url"] = f"/api/public-dataset/{asset_id}/download"
    return asset


@app.get("/api/public-dataset/{asset_id}/download")
def public_dataset_download(asset_id: str, request: Request):
    """Stream the real PDF or PPTX file."""
    with db() as conn:
        row = conn.execute(
            "SELECT file_path, has_local_file, title FROM public_assets WHERE id = ?",
            (asset_id,)
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="not_found")
    if not row["has_local_file"] or not row["file_path"]:
        raise HTTPException(status_code=404, detail="file_not_available")

    file_path = PUBLIC_DATA_ROOT / row["file_path"]
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="file_missing_on_disk")

    ext = file_path.suffix.lower()
    media_type = {
        ".pdf": "application/pdf",
        ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    }.get(ext, "application/octet-stream")

    return FileResponse(file_path, media_type=media_type, filename=file_path.name)


# ────────── Static assets (mount last) ──────────
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
