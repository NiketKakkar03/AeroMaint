"""PostgreSQL full-text/pgvector persistence for retrieval chunks."""

from __future__ import annotations

from packages.retrieval.hybrid import HybridIndex


class PostgresHybridIndex:
    def __init__(self, database: object) -> None:
        self.database = database

    async def reindex(self, index: HybridIndex) -> bool:
        """Publish a complete immutable version once and activate it transactionally."""
        async with self.database.connection() as connection, connection.transaction():  # type: ignore[attr-defined]
            cursor = await connection.execute(
                """INSERT INTO retrieval_indexes(version) VALUES (%s)
                ON CONFLICT DO NOTHING RETURNING version""",
                (index.version,),
            )
            created = await cursor.fetchone() is not None
            if created:
                for chunk in index.chunks:
                    await connection.execute(
                        """INSERT INTO retrieval_chunks
                        (chunk_id,index_version,source_url,title,document_version,page,section,
                         start_char,end_char,checksum,content,embedding)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::vector)""",
                        (
                            chunk.chunk_id,
                            index.version,
                            chunk.source_url,
                            chunk.title,
                            chunk.version,
                            chunk.page,
                            chunk.section,
                            chunk.start_char,
                            chunk.end_char,
                            chunk.checksum,
                            chunk.text,
                            "[" + ",".join(str(value) for value in chunk.embedding) + "]",
                        ),
                    )
            await connection.execute("UPDATE retrieval_indexes SET active=false WHERE active")
            await connection.execute(
                "UPDATE retrieval_indexes SET active=true WHERE version=%s", (index.version,)
            )
        return created

    @staticmethod
    def search_sql() -> str:
        """SQL contract used by adapters: PostgreSQL FTS + cosine distance + RRF."""
        return """
        WITH lexical AS (
          SELECT chunk_id, row_number() OVER (ORDER BY ts_rank_cd(search_vector,
            websearch_to_tsquery('english', %(query)s)) DESC) rank
          FROM retrieval_chunks WHERE index_version=%(version)s
            AND search_vector @@ websearch_to_tsquery('english', %(query)s) LIMIT 50
        ), semantic AS (
          SELECT chunk_id, row_number() OVER (ORDER BY embedding <=> %(embedding)s::vector) rank
          FROM retrieval_chunks WHERE index_version=%(version)s
          ORDER BY embedding <=> %(embedding)s::vector LIMIT 50
        )
        SELECT c.*, coalesce(1.15/(60+l.rank),0)+coalesce(1.0/(60+s.rank),0) AS score
        FROM retrieval_chunks c
        LEFT JOIN lexical l USING(chunk_id) LEFT JOIN semantic s USING(chunk_id)
        WHERE c.index_version=%(version)s AND (l.rank IS NOT NULL OR s.rank IS NOT NULL)
        ORDER BY score DESC, c.chunk_id LIMIT %(limit)s
        """
