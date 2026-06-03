from sqlalchemy import text


PGVECTOR_DDL = """
DO $$
BEGIN
    CREATE EXTENSION IF NOT EXISTS vector;
    ALTER TABLE resumes ADD COLUMN IF NOT EXISTS embedding vector(384);
    CREATE INDEX IF NOT EXISTS ix_resumes_embedding_cosine
    ON resumes USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);
EXCEPTION
    WHEN undefined_file OR undefined_object OR duplicate_object OR feature_not_supported THEN
        RAISE NOTICE 'pgvector is not installed; using JSON embedding fallback until pgvector is available.';
END
$$;
"""


def ensure_pgvector(connection) -> None:
    if connection.dialect.name == "postgresql":
        connection.execute(text(PGVECTOR_DDL))
