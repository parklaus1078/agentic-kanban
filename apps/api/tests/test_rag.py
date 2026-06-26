"""Phase 7 — RAG over the LLM Wiki (§15)."""
import pathlib


def test_embed_deterministic_and_normalized():
    from app.services import rag

    a = rag.embed("build a fastapi endpoint")
    assert a == rag.embed("build a fastapi endpoint")
    assert abs(rag._cosine(a, a) - 1.0) < 1e-6


def test_index_and_search_relevance(client):
    from app.db import SessionLocal
    from app.services import rag

    db = SessionLocal()
    rag.index_wiki_page(db, "wiki/concepts/fastapi.md",
                        "FastAPI endpoints and pytest testing for python backends",
                        page_type="concept", outcome="good")
    rag.index_wiki_page(db, "wiki/concepts/marketing.md",
                        "marketing campaign positioning and brand messaging", page_type="concept")
    db.commit()
    hits = rag.search(db, "python fastapi endpoint tests", k=2)
    assert hits and hits[0]["wiki_path"].endswith("fastapi.md")
    db.close()


def test_memory_search_endpoint(client):
    from app.db import SessionLocal
    from app.services import rag

    db = SessionLocal()
    rag.index_wiki_page(db, "wiki/entities/docker.md",
                        "docker compose kubernetes infrastructure deploy pipeline")
    db.commit()
    db.close()
    res = client.get("/memory/search?q=kubernetes deploy infrastructure").json()
    assert any("docker.md" in h["wiki_path"] for h in res)


def test_reindex_from_wiki_skips_underscore(client):
    from app.config import settings
    from app.db import SessionLocal
    from app.services import rag

    wiki = pathlib.Path(settings.llm_wiki_root) / "kay_second_brain" / "wiki" / "entities"
    wiki.mkdir(parents=True, exist_ok=True)
    (wiki / "valq.md").write_text("VALQ art valuation model and data pipeline")
    (wiki / "_ingested.md").write_text("ledger - should be skipped")
    db = SessionLocal()
    n = rag.reindex_from_wiki(db)
    assert n >= 1
    hits = rag.search(db, "art valuation pipeline", k=3)
    assert any(h["wiki_path"].endswith("valq.md") for h in hits)
    assert not any(h["wiki_path"].endswith("_ingested.md") for h in hits)
    db.close()
