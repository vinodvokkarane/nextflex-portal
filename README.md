# NextFlex Project Portal

A simple, fully-functioning web server for browsing and searching NextFlex Project Call data (PC 1.0 – 10.0).

**Stack:** FastAPI + SQLite + vanilla JavaScript. No external services. Single-command boot.

## Features

- **Dashboard** — high-level stats: total projects, funding, project calls, institutions
- **Project Calls view** — see all PCs with funding totals and project counts
- **Projects browser** — filter by Project Call, focus area, status
- **Search** — full-text search across titles, abstracts, materials, processes, PIs (SQLite FTS5)
- **Institution view** — top institutions by project count and funding
- **Project detail modal** — full record including PIs, materials, processes, outcomes, publications, patents

## Quick start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Initialize the database (creates nextflex.db with ~95 demo projects)
python init_db.py

# 3. Start the server
uvicorn app:app --reload --port 8000

# 4. Open in browser
open http://localhost:8000
```

That's it.

## API

All endpoints return JSON. No auth in this build.

| Method | Path | Description |
|---|---|---|
| GET | `/api/health` | Liveness check + project count |
| GET | `/api/stats` | Dashboard statistics |
| GET | `/api/project-calls` | List PCs with project counts and funding |
| GET | `/api/projects?pc=&focus=&status=&q=&limit=&offset=` | List/filter/search projects |
| GET | `/api/projects/{id}` | Get a single project |
| GET | `/api/focus-areas` | Distinct focus areas with counts |
| GET | `/api/institutions?top=20` | Top institutions by project count |

### Examples

```bash
# Get dashboard stats
curl http://localhost:8000/api/stats

# List all projects in PC 7.1
curl "http://localhost:8000/api/projects?pc=PC%207.1"

# Search for projects mentioning "silver ink Kapton"
curl "http://localhost:8000/api/projects?q=silver+ink+Kapton"

# Get specific project
curl http://localhost:8000/api/projects/NFX-PC1_2-001
```

## Repository layout

```
nextflex-portal/
├── README.md
├── requirements.txt
├── app.py              # FastAPI server
├── init_db.py          # DB schema + seed data
├── nextflex.db         # SQLite DB (created by init_db.py)
└── static/
    ├── index.html      # SPA
    ├── style.css       # Styles
    └── app.js          # Frontend logic
```

## Replacing the demo data

The seed script in `init_db.py` generates **~95 demonstration projects** based on publicly known NextFlex focus areas. To replace with your authoritative data:

1. Export your records as JSON or CSV with columns matching the `projects` table schema (see `init_db.py`)
2. Replace the `generate_projects()` function with your loader
3. Run `python init_db.py --reset`

## Production considerations (kept out of scope here)

This build is intentionally simple. For production you'd add:

- Authentication (OAuth/JWT)
- HTTPS via reverse proxy (nginx, Caddy)
- Postgres instead of SQLite for concurrent writes
- Background workers for ingestion
- Rate limiting
- Structured audit logging

But for browsing PC 1.0–10.0 internally, the current build is enough.

## License

For internal NextFlex use. Not for redistribution.
