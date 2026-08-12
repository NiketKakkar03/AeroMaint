from pathlib import Path

from packages.retrieval import PostgresHybridIndex


def test_postgres_profile_combines_full_text_vector_and_rrf() -> None:
    sql = PostgresHybridIndex.search_sql()
    assert "websearch_to_tsquery" in sql
    assert "embedding <=>" in sql
    assert "60+l.rank" in sql


def test_retrieval_migration_has_required_indexes() -> None:
    migration = Path(
        "apps/data-api/src/aeromaint_api/db/migrations/0004_retrieval.up.sql"
    ).read_text()
    assert "CREATE EXTENSION IF NOT EXISTS vector" in migration
    assert "USING gin(search_vector)" in migration
    assert "USING hnsw (embedding vector_cosine_ops)" in migration
