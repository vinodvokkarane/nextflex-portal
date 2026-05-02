# NextFlex Project Portal

Secure AI/ML data platform for NextFlex Project Calls. FastAPI + SQLite + vanilla JavaScript. Single-command boot, no external services required.

## What's in this build (v4)

- **Three-user auth** — Admin (full ops), DoD (mission-relevant), Member (public).  Bcrypt-hashed passwords, JWT in HttpOnly cookies, site-wide auth gate
- **390 synthetic projects** across PC 1.0 – 10.2 with $138.85M in funding, 809 knowledge-graph entities, 4,767 entity relationships
- **Synthetic PDF + PPTX per project** — generated on first download, content grounded in OWL-DL ontology subclasses; 3,494 ontology-classified chunks indexed for retrieval
- **Public NextFlex Dataset** — 56 real publicly-sourced assets (32 acknowledged academic papers, 9 patents, 7 Proposers Day webinars, 3 project reports, 5 PPTX templates) with 47 local files (125.7 MB), full text extracted and chunked into 1,156 retrieval chunks
- **GraphRAG** — hybrid FTS5 retrieval that returns a balanced 2/2/2/2 mix from synthetic PDF + synthetic PPTX + real public dataset + narrative chunks on every query
- **Manager dashboard at `/manager`** — role-aware view with knowledge-graph explorer, ingestion pipeline, district / deployment / PEO drill-downs
- **Drill-downs** — every district, deployment, PEO, focus area is clickable; opens a filtered project list modal; nested clicks open project detail with PDF + PPTX downloads
- **Production status banner** — pulsing green health indicator, FedRAMP / CMMC posture, live latency

## Quick start

```bash
pip install -r requirements.txt
JWT_SECRET="$(openssl rand -hex 32)" uvicorn app:app --port 8000

# Open http://localhost:8000 in your browser
# Login: nfx-admin / 3LEqkim$k!  (or nfx-member / nfx-dod, see below)
```

The first request triggers DB init + indexing of synthetic file chunks + indexing of real PDFs/PPTXs. Cold start: ~30-45 seconds for 47 PDF text extractions; subsequent requests are ~5 ms.

## Login credentials

| Role | Username | Password | Sees |
|---|---|---|---|
| NextFlex Admin | `nfx-admin` | `3LEqkim$k!` | All 390 projects + all 56 public assets |
| DoD User | `nfx-dod` | `f6&NTm@hNr` | Mission-relevant 285 + all 56 public |
| Member / Industry | `nfx-member` | `&vTXf4g9#s` | Public-tier 345 + all 56 public |

The public dataset is visible to every persona — it's, well, public.

## Tabs

| Tab | What it does |
|---|---|
| Dashboard | Overview stats, projects-by-PC bar chart, top focus areas, status banner |
| Projects | Filter by PC / focus / status, click for detail modal with PDF + PPTX downloads |
| Institutions | Top institutions by project count and funding |
| **Public Dataset** | Real NextFlex papers + patents + webinars + project reports + PPTX templates with category filters, year filter, full-text search, and per-asset modal with download |
| Search | FTS5 full-text search across all projects |
| ★ Manager Dashboard | Role-scoped at `/manager` with KG explorer, ingestion pipeline status, geographic / commercial / DoD acquisition mappings |

## API

All endpoints require an authenticated session cookie obtained via `POST /api/auth/login`.

| Method | Path | Description |
|---|---|---|
| POST | `/api/auth/login` | Form: `username`, `password` -> sets `nfx_session` cookie |
| POST | `/api/auth/logout` | Clears the cookie |
| GET | `/api/auth/whoami` | Returns current user |
| GET | `/api/health` | Liveness + version + latency + chunk/entity counts |
| GET | `/api/stats` | Role-scoped dashboard stats |
| GET | `/api/projects?pc=&focus=&status=&district=&peo=&q=&limit=` | List + filter projects |
| GET | `/api/projects/{id}` | Project detail |
| GET | `/api/projects/{id}/files` | Available downloadable files |
| GET | `/api/projects/{id}/files/pdf` | Synthetic Final Report PDF (lazy-generated) |
| GET | `/api/projects/{id}/files/pptx` | Synthetic Project Briefing PPTX (lazy-generated) |
| GET | `/api/entities` | KG entity list, filterable by type and subtype |
| GET | `/api/entity-counts` | KG counts grouped by ontology type / subtype |
| GET | `/api/districts` `/api/deployments` `/api/peos` | Mission/geo data |
| GET | `/api/public-dataset/stats` | Counts by category, year, agreement |
| GET | `/api/public-dataset/list?category=&year=&pc=&q=` | List + search public assets |
| GET | `/api/public-dataset/{id}` | Public asset detail |
| GET | `/api/public-dataset/{id}/download` | Stream the real PDF / PPTX |
| POST | `/api/graphrag` | Hybrid retrieval; body: `{question}`; returns citations + source breakdown |

## Repository layout

```
nextflex-portal/
├── README.md
├── requirements.txt
├── render.yaml              # Render Blueprint (free-tier deploy)
├── app.py                   # FastAPI server, auth middleware, all endpoints
├── auth.py                  # Bcrypt + JWT-cookie auth module
├── init_db.py               # DB schema + 390-project seed + entities/districts/deployments/PEOs
├── synthetic_files.py       # Generates PDF/PPTX per project, indexes ontology-grounded chunks
├── public_dataset.py        # Loads real NextFlex papers + funded assets, extracts text, indexes chunks
├── public_data/             # 130 MB of real PDFs/PPTXs from NextFlex bundles
│   ├── nextflex_acknowledged_papers_2016_2026/
│   │   ├── public_pdfs/        # 23 academic paper PDFs
│   │   └── manifest.csv
│   ├── nextflex_assets/
│   │   ├── webinar_pdfs/       # 7 Proposers Day decks (PC 7-11) + AI workshop
│   │   ├── patents/            # 9 NextFlex-acknowledged patents
│   │   ├── project_reports/    # 3 success-story PDFs
│   │   └── pptx/               # 5 PC summary templates
│   └── nextflex_assets_included_public_files.csv
└── static/
    ├── index.html           # Main portal SPA
    ├── login.html           # Login page
    ├── manager.html         # Manager dashboard (role-aware)
    ├── style.css
    └── app.js               # Frontend logic for all portal tabs
```

## Deployment to Render

1. Push to GitHub (with `public_data/` directory included — it's ~130 MB, well under Render's 1 GB repo limit)
2. New Blueprint on Render → connect repo
3. Render auto-detects `render.yaml`, provisions a free Web Service
4. Set `JWT_SECRET` in environment to any random 32-byte hex string
5. (Optional) Set `ANTHROPIC_API_KEY` to enable LLM-backed GraphRAG synthesis instead of the deterministic fallback

First boot will take ~45 seconds for full corpus indexing. Subsequent requests are ms-fast.

## Why the public_data folder is in the repo

Indexing all 47 PDFs and PPTXs every cold-start takes ~30 seconds. The text-extracted chunks live in SQLite, so once indexed they're reused. But Render's free tier has an ephemeral filesystem — the DB is rebuilt on every cold start. Keeping the source files in-repo means we have a deterministic, no-egress path to rebuild the index without depending on external storage.

For a production deployment you'd move `public_data/` to S3 with KMS encryption (see `NextFlex_Portal_FedRAMP_Scaling_Plan.docx` for the migration path).

## Replacing demo data with authoritative records

For NextFlex's real corpus (not just public assets):

1. Stand up Aurora PostgreSQL or equivalent, replace the SQLite calls in `app.py`
2. Replace `init_db.py`'s `generate_projects()` with a real ETL from your authoritative source
3. Run real PDFs through `public_dataset.py`'s extraction pipeline (or use AWS Textract for scanned content)
4. See FedRAMP scaling plan for the full path to 1M-document scale

## License

For NextFlex / DoD / academic use. Public dataset items retain their original licenses.
