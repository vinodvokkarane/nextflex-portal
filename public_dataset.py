"""
Public NextFlex Dataset indexer.

Loads the real NextFlex acknowledged papers and funded assets into the
existing portal tables so they're queryable through the same UI:
  - GraphRAG retrieves from real PDF/PPTX content
  - Drill-downs work via project-style records
  - Files are downloadable through /api/public-dataset/files/{id}

Schema additions to nextflex.db:
  - public_assets table: holds metadata for each real PDF/PPTX file
  - public_assets_fts: FTS5 index on title + abstract + extracted text
  - chunks: extended with classification='public_dataset' for the
    actual paper text content (so existing GraphRAG endpoint hits them)

All records carry classification='public' so every persona sees them.

IMPORTANT: This module reads pre-extracted text from
  public_data/extracted_corpus.json
which is built locally via build_extracted_corpus.py and committed to
the repo. We do NOT run pypdf or python-pptx at server startup, because
on Render's 512 MB free tier that exceeds the memory budget. Pre-
extracting at build time and shipping the JSON keeps server cold-start
under 100 MB.
"""

import csv
import json
import re
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "nextflex.db"
DATA_ROOT = Path(__file__).parent / "public_data"
PAPERS_DIR = DATA_ROOT / "nextflex_acknowledged_papers_2016_2026"
ASSETS_DIR = DATA_ROOT / "nextflex_assets"
EXTRACTED_JSON = DATA_ROOT / "extracted_corpus.json"


PUBLIC_SCHEMA = """
CREATE TABLE IF NOT EXISTS public_assets (
    id TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    subtype TEXT,
    title TEXT NOT NULL,
    year INTEGER,
    authors TEXT,
    project_call TEXT,
    funding_acknowledgment TEXT,
    agreement_numbers TEXT,
    file_path TEXT,
    file_size_bytes INTEGER,
    pages INTEGER,
    source_url TEXT,
    public_access TEXT,
    download_status TEXT,
    has_local_file INTEGER DEFAULT 0,
    abstract TEXT,
    full_text_chars INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_pub_cat ON public_assets (category);
CREATE INDEX IF NOT EXISTS idx_pub_year ON public_assets (year);
CREATE INDEX IF NOT EXISTS idx_pub_pc ON public_assets (project_call);
CREATE INDEX IF NOT EXISTS idx_pub_local ON public_assets (has_local_file);

CREATE VIRTUAL TABLE IF NOT EXISTS public_assets_fts USING fts5(
    id UNINDEXED, title, authors, abstract, agreement_numbers, project_call
);
"""


def _safe_id(category: str, filename: str) -> str:
    base = Path(filename).stem.lower()
    base = re.sub(r"[^a-z0-9]+", "_", base).strip("_")[:80]
    return f"pub-{category}-{base}"


def _infer_project_call(text: str, default: str = "") -> str:
    if not text:
        return default
    m = re.search(r"\b(PC|Project Call|OPC)[\s\-]*?(\d{1,2}(?:\.\d)?)\b", text)
    if m:
        return f"PC {m.group(2)}"
    return default


def _chunk_text(text: str, chunk_chars: int = 1500, overlap: int = 150):
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_chars, len(text))
        if end < len(text):
            for p in (".", "!", "?", "\n"):
                idx = text.rfind(p, start + chunk_chars // 2, end)
                if idx > 0:
                    end = idx + 1
                    break
        chunks.append(text[start:end].strip())
        start = end - overlap if end - overlap > start else end
    return [c for c in chunks if len(c) > 50]


def index_public_dataset():
    """Idempotent: index real NextFlex papers + funded assets.

    Reads pre-extracted text from public_data/extracted_corpus.json
    instead of invoking pypdf/python-pptx — this keeps cold-start memory
    under 100 MB so we fit in Render's 512 MB free-tier budget.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(PUBLIC_SCHEMA)

    existing = conn.execute(
        "SELECT COUNT(*) FROM public_assets"
    ).fetchone()[0]
    if existing > 0:
        print(f"[public-data] {existing} assets already indexed, skipping",
              flush=True)
        conn.close()
        return existing

    # Load pre-extracted text. If the JSON is missing, we still index
    # metadata — but chunks will be empty and GraphRAG won't see this corpus.
    extracted = {}
    if EXTRACTED_JSON.exists():
        try:
            extracted = json.loads(EXTRACTED_JSON.read_text())
            print(f"[public-data] Loaded extracted text for "
                  f"{len(extracted)} files from {EXTRACTED_JSON.name}",
                  flush=True)
        except Exception as e:
            print(f"[public-data] WARNING: could not load {EXTRACTED_JSON}: {e}",
                  flush=True)
    else:
        print(f"[public-data] WARNING: {EXTRACTED_JSON.name} not found — "
              f"run build_extracted_corpus.py to generate it. "
              f"Indexing metadata-only for now.", flush=True)

    def _commit_chunks_for(asset_id: str, full_text: str, section: str):
        if not full_text:
            return 0
        rows = []
        for ci, ct in enumerate(_chunk_text(full_text)):
            rows.append((
                f"{asset_id}-c{ci:03d}", asset_id, section, ci + 1,
                ct, "public_dataset",
            ))
        if rows:
            conn.executemany(
                "INSERT OR IGNORE INTO chunks "
                "(id, project_id, section, page, text, classification) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                rows,
            )
            conn.executemany(
                "INSERT OR IGNORE INTO chunks_fts "
                "(id, text, project_id, section) VALUES (?, ?, ?, ?)",
                [(r[0], r[4], r[1], r[2]) for r in rows],
            )
            conn.commit()
        return len(rows)

    total_chunks = 0

    # ─── Papers ────────────────────────────────────────────────
    papers_manifest = PAPERS_DIR / "manifest.csv"
    if papers_manifest.exists():
        n_papers = 0
        with papers_manifest.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                year = int(row.get("year") or 0) or None
                title = (row.get("title") or "").strip()
                if not title:
                    continue
                folder = (row.get("folder") or "").strip()
                filename = (row.get("filename") or "").strip()
                rel_path = (
                    f"nextflex_acknowledged_papers_2016_2026/{folder}/{filename}"
                    if filename else ""
                )
                local_path = PAPERS_DIR / folder / filename if filename else None
                size = int(row.get("size_bytes") or 0)
                agreements = (row.get("agreements") or "").strip()
                ack_excerpt = (row.get("ack_or_funding_excerpt") or "").strip()
                has_file = bool(local_path and local_path.exists())

                # Pull text from pre-extracted JSON
                ext = extracted.get(rel_path, {})
                full_text = ext.get("text", "")
                pages = ext.get("pages", 0)

                abstract = (full_text[:600] if full_text
                            else ack_excerpt[:600]).strip()
                aid = _safe_id("paper", filename or title)
                inferred_pc = _infer_project_call(full_text or ack_excerpt)

                conn.execute(
                    """INSERT OR REPLACE INTO public_assets
                       (id, category, subtype, title, year, project_call,
                        funding_acknowledgment, agreement_numbers,
                        file_path, file_size_bytes, pages,
                        public_access, download_status, has_local_file,
                        abstract, full_text_chars)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (aid, "paper", "academic_paper", title, year, inferred_pc,
                     ack_excerpt, agreements, rel_path, size, pages,
                     "public", row.get("status", "included_public_pdf"),
                     1 if has_file else 0, abstract, len(full_text)),
                )
                n_papers += 1
                total_chunks += _commit_chunks_for(aid, full_text, "public:paper")
        print(f"[public-data] {n_papers} papers indexed", flush=True)

    # ─── Funded assets ─────────────────────────────────────────
    assets_manifest = DATA_ROOT / "nextflex_assets_included_public_files.csv"
    if assets_manifest.exists():
        n_assets = 0
        with assets_manifest.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                category = (row.get("category") or "").strip()
                subtype = (row.get("subtype") or "").strip()
                title = (row.get("title") or "").strip()
                year_raw = (row.get("year") or "").strip()
                try:
                    year = int(year_raw) if year_raw else None
                except ValueError:
                    year = None
                rel_path = (row.get("downloaded_filename") or "").strip()
                file_exists = (
                    (row.get("file_exists") or "").strip().lower() == "yes"
                )
                size = int(row.get("file_size_bytes") or 0)
                source_url = (row.get("source_url") or "").strip()
                agreements = (row.get("agreement_numbers") or "").strip()
                evidence = (row.get("evidence") or "").strip()
                public_access = (row.get("public_access") or "").strip()
                download_status = (row.get("download_status") or "").strip()

                if not title:
                    continue

                ext = extracted.get(rel_path, {})
                full_text = ext.get("text", "")
                pages = ext.get("pages", 0)

                abstract = (full_text[:600] if full_text
                            else evidence[:600]).strip()
                aid = _safe_id(category or "asset",
                               Path(rel_path).name or title)
                inferred_pc = _infer_project_call(full_text)

                conn.execute(
                    """INSERT OR REPLACE INTO public_assets
                       (id, category, subtype, title, year, project_call,
                        funding_acknowledgment, agreement_numbers,
                        file_path, file_size_bytes, pages, source_url,
                        public_access, download_status, has_local_file,
                        abstract, full_text_chars)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (aid, category, subtype, title, year, inferred_pc,
                     evidence, agreements, rel_path, size, pages, source_url,
                     public_access, download_status,
                     1 if file_exists else 0, abstract, len(full_text)),
                )
                n_assets += 1
                total_chunks += _commit_chunks_for(
                    aid, full_text, f"public:{category}"
                )
        print(f"[public-data] {n_assets} funded assets indexed", flush=True)

    print(f"[public-data] {total_chunks} text chunks indexed for GraphRAG",
          flush=True)

    # Build assets FTS
    rows = conn.execute(
        "SELECT id, title, COALESCE(authors,''), COALESCE(abstract,''), "
        "       COALESCE(agreement_numbers,''), COALESCE(project_call,'') "
        "FROM public_assets"
    ).fetchall()
    conn.executemany(
        "INSERT INTO public_assets_fts "
        "(id, title, authors, abstract, agreement_numbers, project_call) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [tuple(r) for r in rows],
    )

    conn.commit()
    total = conn.execute("SELECT COUNT(*) FROM public_assets").fetchone()[0]
    chunks = conn.execute(
        "SELECT COUNT(*) FROM chunks WHERE classification='public_dataset'"
    ).fetchone()[0]
    conn.close()
    print(f"[public-data] DONE: {total} assets, {chunks} chunks indexed",
          flush=True)
    return total


if __name__ == "__main__":
    n = index_public_dataset()
    print(f"Indexed {n} public assets")

