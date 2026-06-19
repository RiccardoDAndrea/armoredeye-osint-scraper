import json
from pathlib import Path
from urllib.parse import urlparse

try:
    import duckdb
except ModuleNotFoundError as e:
    raise SystemExit(
        "Fehlendes Paket: duckdb. Installiere es mit: python -m pip install duckdb"
    ) from e


BASE_DIR = Path(__file__).resolve().parents[1]
DB_PATH = Path(__file__).resolve().parent / "armoredeye_newspaper.duckdb"
DEFAULT_JSON_PATH = BASE_DIR / "getnews_json" / "battlefield_changes.json"


def connect():
    return duckdb.connect(DB_PATH)


def table_exists(con, table_name):
    result = con.execute(
        "SELECT count(*) FROM information_schema.tables WHERE table_name = ?",
        [table_name],
    ).fetchone()[0]
    return result > 0


def column_exists(con, table_name, column_name):
    if not table_exists(con, table_name):
        return False

    rows = con.execute(f"DESCRIBE {table_name}").fetchall()
    return any(row[0] == column_name for row in rows)


def backup_old_flat_articles_table(con):
    if table_exists(con, "articles") and not column_exists(con, "articles", "source_id"):
        if not table_exists(con, "articles_flat_backup"):
            con.execute("CREATE TABLE articles_flat_backup AS SELECT * FROM articles")

        con.execute("DROP INDEX IF EXISTS idx_articles_published_at")
        con.execute("DROP INDEX IF EXISTS idx_articles_source_domain")
        con.execute("DROP INDEX IF EXISTS idx_articles_source_id")
        con.execute("DROP TABLE articles")


def reset_partial_foreign_key_schema(con):
    if table_exists(con, "schema_versions"):
        return

    if not table_exists(con, "article_texts"):
        return

    con.execute("DROP TABLE IF EXISTS import_articles")
    con.execute("DROP TABLE IF EXISTS article_texts")
    con.execute("DROP TABLE IF EXISTS articles")
    con.execute("DROP TABLE IF EXISTS import_runs")
    con.execute("DROP TABLE IF EXISTS authors")
    con.execute("DROP TABLE IF EXISTS sources")


def create_tables():
    with connect() as con:
        backup_old_flat_articles_table(con)
        reset_partial_foreign_key_schema(con)

        con.execute("CREATE SEQUENCE IF NOT EXISTS source_id_seq")
        con.execute("CREATE SEQUENCE IF NOT EXISTS author_id_seq")
        con.execute("CREATE SEQUENCE IF NOT EXISTS article_id_seq")
        con.execute("CREATE SEQUENCE IF NOT EXISTS import_run_id_seq")

        con.execute("""
            CREATE TABLE IF NOT EXISTS schema_versions (
                version INTEGER PRIMARY KEY,
                description TEXT,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)

        con.execute("""
            CREATE TABLE IF NOT EXISTS sources (
                id BIGINT PRIMARY KEY DEFAULT nextval('source_id_seq'),
                source_key TEXT NOT NULL UNIQUE,
                newsapi_id TEXT,
                name TEXT,
                domain TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)

        con.execute("""
            CREATE TABLE IF NOT EXISTS authors (
                id BIGINT PRIMARY KEY DEFAULT nextval('author_id_seq'),
                name TEXT NOT NULL UNIQUE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)

        con.execute("""
            CREATE TABLE IF NOT EXISTS articles (
                id BIGINT PRIMARY KEY DEFAULT nextval('article_id_seq'),
                source_id BIGINT,
                author_id BIGINT,
                title TEXT NOT NULL,
                description TEXT,
                url TEXT NOT NULL UNIQUE,
                url_to_image TEXT,
                published_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)

        con.execute("""
            CREATE TABLE IF NOT EXISTS article_texts (
                article_id BIGINT PRIMARY KEY,
                content TEXT,
                full_text TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)

        con.execute("""
            CREATE TABLE IF NOT EXISTS import_runs (
                id BIGINT PRIMARY KEY DEFAULT nextval('import_run_id_seq'),
                file_path TEXT NOT NULL,
                status TEXT,
                total_results INTEGER,
                articles_seen INTEGER NOT NULL DEFAULT 0,
                started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                finished_at TIMESTAMPTZ
            )
        """)

        con.execute("""
            CREATE TABLE IF NOT EXISTS import_articles (
                import_run_id BIGINT,
                article_id BIGINT,
                position INTEGER,
                imported_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                PRIMARY KEY (import_run_id, article_id)
            )
        """)

        con.execute("CREATE INDEX IF NOT EXISTS idx_articles_published_at ON articles (published_at)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_articles_source_id ON articles (source_id)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_sources_domain ON sources (domain)")
        con.execute("""
            INSERT INTO schema_versions (version, description)
            VALUES (1, 'normalized news article schema without duckdb foreign key constraints')
            ON CONFLICT (version) DO NOTHING
        """)


def get_domain(url):
    if not url:
        return None

    domain = urlparse(url).netloc.lower()
    if domain.startswith("www."):
        domain = domain[4:]
    return domain or None


def get_source_key(source, domain):
    return domain or source.get("id") or source.get("name") or "unknown"


def upsert_source(con, source, domain):
    source_key = get_source_key(source, domain)
    con.execute("""
        INSERT INTO sources (source_key, newsapi_id, name, domain)
        VALUES (?, ?, ?, ?)
        ON CONFLICT (source_key) DO NOTHING
    """, [source_key, source.get("id"), source.get("name"), domain])

    return con.execute(
        "SELECT id FROM sources WHERE source_key = ?",
        [source_key],
    ).fetchone()[0]


def upsert_author(con, author_name):
    if not author_name:
        return None

    author_name = author_name.strip()
    if not author_name:
        return None

    con.execute("""
        INSERT INTO authors (name)
        VALUES (?)
        ON CONFLICT (name) DO NOTHING
    """, [author_name])

    return con.execute(
        "SELECT id FROM authors WHERE name = ?",
        [author_name],
    ).fetchone()[0]


def upsert_article(con, article, source_id, author_id):
    existing = con.execute(
        "SELECT id FROM articles WHERE url = ?",
        [article.get("url")],
    ).fetchone()

    if existing:
        article_id = existing[0]
        con.execute("""
            UPDATE articles
            SET
                source_id = ?,
                author_id = ?,
                title = ?,
                description = ?,
                url_to_image = ?,
                published_at = ?,
                updated_at = now()
            WHERE id = ?
        """, [
            source_id,
            author_id,
            article.get("title") or "",
            article.get("description"),
            article.get("urlToImage"),
            article.get("publishedAt"),
            article_id,
        ])
        return article_id

    con.execute("""
        INSERT INTO articles (
            source_id,
            author_id,
            title,
            description,
            url,
            url_to_image,
            published_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, [
        source_id,
        author_id,
        article.get("title") or "",
        article.get("description"),
        article.get("url"),
        article.get("urlToImage"),
        article.get("publishedAt"),
    ])

    return con.execute(
        "SELECT id FROM articles WHERE url = ?",
        [article.get("url")],
    ).fetchone()[0]


def upsert_article_text(con, article_id, article):
    existing = con.execute(
        "SELECT article_id FROM article_texts WHERE article_id = ?",
        [article_id],
    ).fetchone()

    if existing:
        con.execute("""
            UPDATE article_texts
            SET content = ?, full_text = ?, updated_at = now()
            WHERE article_id = ?
        """, [
            article.get("content"),
            article.get("full_text") or article.get("fullText"),
            article_id,
        ])
        return

    con.execute("""
        INSERT INTO article_texts (article_id, content, full_text)
        VALUES (?, ?, ?)
    """, [
        article_id,
        article.get("content"),
        article.get("full_text") or article.get("fullText"),
    ])


def load_articles_from_json(json_path=DEFAULT_JSON_PATH):
    create_tables()

    with open(json_path, encoding="utf-8") as file:
        data = json.load(file)

    articles = data.get("articles", data) if isinstance(data, dict) else data

    with connect() as con:
        import_run_id = con.execute("""
            INSERT INTO import_runs (file_path, status, total_results)
            VALUES (?, ?, ?)
            RETURNING id
        """, [
            str(json_path),
            data.get("status") if isinstance(data, dict) else None,
            data.get("totalResults") if isinstance(data, dict) else None,
        ]).fetchone()[0]

        imported_count = 0

        for position, article in enumerate(articles, start=1):
            if not article.get("url"):
                continue

            source = article.get("source") or {}
            domain = get_domain(article.get("url"))
            source_id = upsert_source(con, source, domain)
            author_id = upsert_author(con, article.get("author"))
            article_id = upsert_article(con, article, source_id, author_id)
            upsert_article_text(con, article_id, article)

            con.execute("""
                INSERT INTO import_articles (import_run_id, article_id, position)
                VALUES (?, ?, ?)
                ON CONFLICT (import_run_id, article_id) DO NOTHING
            """, [import_run_id, article_id, position])

            imported_count += 1

        con.execute("""
            UPDATE import_runs
            SET articles_seen = ?, finished_at = now()
            WHERE id = ?
        """, [imported_count, import_run_id])

        totals = {
            "sources": con.execute("SELECT count(*) FROM sources").fetchone()[0],
            "authors": con.execute("SELECT count(*) FROM authors").fetchone()[0],
            "articles": con.execute("SELECT count(*) FROM articles").fetchone()[0],
            "article_texts": con.execute("SELECT count(*) FROM article_texts").fetchone()[0],
            "import_runs": con.execute("SELECT count(*) FROM import_runs").fetchone()[0],
        }

    return imported_count, totals


def main():
    imported, totals = load_articles_from_json()
    print(f"Datenbank bereit: {DB_PATH.resolve()}")
    print(f"Importierte Artikel: {imported}")
    print(f"Quellen insgesamt: {totals['sources']}")
    print(f"Autoren insgesamt: {totals['authors']}")
    print(f"Artikel insgesamt: {totals['articles']}")
    print(f"Artikeltexte insgesamt: {totals['article_texts']}")
    print(f"Import-Laeufe insgesamt: {totals['import_runs']}")


if __name__ == "__main__":
    main()
