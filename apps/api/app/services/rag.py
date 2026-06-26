"""Phase 7 — RAG over the LLM Wiki (spec §15).

Embeds the wiki *synthesized* pages (never raw — the cheap-read rule) and retrieves
relevant chunks to inject into Navigator decisions and Executor prompts.

The default embedding is a deterministic local hashing bag-of-words so the pipeline
runs offline and is unit-testable; ``set_embedder`` swaps in a real LangChain
embedding model in production. Similarity is cosine over JSON-stored vectors
(portable across SQLite/Postgres); pgvector is the production optimization.
"""
from __future__ import annotations

import hashlib
import math
import re
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import WikiEmbedding

DIM = 256


def _default_embed(text: str) -> list[float]:
    vec = [0.0] * DIM
    for tok in re.findall(r"[a-z0-9]+", (text or "").lower()):
        h = int(hashlib.md5(tok.encode()).hexdigest(), 16)  # noqa: S324 (non-crypto use)
        vec[h % DIM] += 1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


_embed = _default_embed


def set_embedder(fn) -> None:
    """Swap the embedding function (e.g. a LangChain embeddings model) in production."""
    global _embed
    _embed = fn


def embed(text: str) -> list[float]:
    return _embed(text)


def _cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))  # vectors are unit-normalized


def _chunks(text: str, size: int = 800) -> list[str]:
    paras = [p.strip() for p in re.split(r"\n\s*\n", text or "") if p.strip()]
    out, buf = [], ""
    for p in paras:
        if len(buf) + len(p) > size and buf:
            out.append(buf)
            buf = p
        else:
            buf = f"{buf}\n\n{p}" if buf else p
    if buf:
        out.append(buf)
    return out or ([text] if text else [])


def index_wiki_page(db: Session, wiki_path: str, text: str,
                    page_type: str | None = None, outcome: str | None = None) -> int:
    """(Re)index one wiki page. Replaces any existing rows for that path."""
    db.execute(delete(WikiEmbedding).where(WikiEmbedding.wiki_path == wiki_path))
    n = 0
    for i, ch in enumerate(_chunks(text)):
        db.add(WikiEmbedding(wiki_path=wiki_path, chunk_index=i, chunk=ch,
                             embedding_json=embed(ch), page_type=page_type, outcome=outcome))
        n += 1
    db.flush()
    return n


def search(db: Session, query: str, k: int = 4) -> list[dict]:
    qv = embed(query)
    rows = db.scalars(select(WikiEmbedding)).all()
    scored = [
        {"wiki_path": r.wiki_path, "chunk": r.chunk, "outcome": r.outcome,
         "score": round(_cosine(qv, r.embedding_json or []), 4)}
        for r in rows
    ]
    scored.sort(key=lambda x: x["score"], reverse=True)
    return [s for s in scored[:k] if s["score"] > 0]


def context_packet(db: Session, query: str, k: int = 4) -> str:
    hits = search(db, query, k)
    if not hits:
        return ""
    lines = ["## Relevant prior knowledge (RAG over LLM Wiki)"]
    for h in hits:
        tag = f" [outcome: {h['outcome']}]" if h.get("outcome") else ""
        lines.append(f"- ({h['wiki_path']}{tag}) {h['chunk'][:280]}")
    return "\n".join(lines)


def reindex_from_wiki(db: Session) -> int:
    """Index every synthesized wiki page (wiki/, excluding `_` index/ledger files)."""
    wiki_dir = Path(settings.llm_wiki_root) / "kay_second_brain" / "wiki"
    if not wiki_dir.exists():
        return 0
    total = 0
    for md in wiki_dir.rglob("*.md"):
        if md.name.startswith("_"):
            continue
        text = md.read_text(encoding="utf-8", errors="ignore")
        page_type = md.parent.name.rstrip("s")  # entities→entity, concepts→concept, ...
        total += index_wiki_page(db, str(md), text, page_type=page_type)
    db.commit()
    return total
