import configparser
import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

try:
    import trafilatura
    from newsapi import NewsApiClient
except ModuleNotFoundError as e:
    missing_package = e.name
    package_hint = "newsapi-python" if missing_package == "newsapi" else missing_package
    raise SystemExit(
        f"Fehlendes Paket: {missing_package}. "
        f"Installiere es mit: pip install {package_hint}"
    ) from e

### Ziel: Daten sammeln in umkämpften Gebieten der Ukraine
### inkl. vollständigem Artikeltext (nicht nur NewsAPI-Snippet)


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
DEFAULT_OUTPUT_PATH = BASE_DIR / "getnews_json" / "battlefield_changes.json"


def get_apikey(path=None):
    env_apikey = os.getenv("NEWSAPI_KEY")
    if env_apikey:
        return env_apikey.strip()

    candidates = [Path(path)] if path else [
        BASE_DIR / "credentials.conf",
        PROJECT_ROOT / "credentials.conf",
    ]

    parser = configparser.ConfigParser()

    config_path = None
    for candidate in candidates:
        if candidate.exists():
            config_path = candidate
            break

    if config_path is None:
        searched = ", ".join(str(candidate) for candidate in candidates)
        raise FileNotFoundError(
            "Konfigurationsdatei nicht gefunden. "
            f"Gesucht wurde hier: {searched}. "
            "Alternativ kannst du NEWSAPI_KEY als Umgebungsvariable setzen."
        )

    parser.read(config_path)
    apikey = parser.get("newsapi", "apikey", fallback="").strip()
    if not apikey:
        raise ValueError(f"Kein API-Key in der Sektion [newsapi] gefunden: {config_path}")
    return apikey


def get_date_range(days_back=5):
    today = datetime.today()
    start = today - timedelta(days=days_back)
    today = today.strftime('%Y-%m-%d')
    start = start.strftime('%Y-%m-%d')
    return start,today

def build_query(query):
    """Gibt die NewsAPI-Suchanfrage zurück."""
    return query


def fetch_articles(client, query, domains, date_from, date_to):
    response = client.get_everything(
        q=query,
        domains=domains,
        from_param=date_from,
        to=date_to,
        language='en',
        sort_by='relevancy',
        page_size=100
    )

    if response.get('status') != 'ok':
        raise RuntimeError(f"NewsAPI-Fehler: {response.get('code')} - {response.get('message')}")

    return response


def fetch_full_text(url, timeout=10):
    """Lädt die Artikelseite und extrahiert den vollständigen Haupttext."""
    try:
        downloaded = trafilatura.fetch_url(url)
        if downloaded is None:
            return None
        text = trafilatura.extract(downloaded, include_comments=False, include_tables=False)
        return text
    except Exception as e:
        print(f"  Fehler beim Laden von {url}: {e}")
        return None


def enrich_articles_with_full_text(articles, delay=1.0):
    """Ergänzt jeden Artikel um ein 'full_text'-Feld."""
    for i, article in enumerate(articles):
        url = article.get('url')
        print(f"[{i+1}/{len(articles)}] Lade Volltext: {url}")
        full_text = fetch_full_text(url)
        article['full_text'] = full_text if full_text else article.get('content', '')
        time.sleep(delay)  # höflich sein, Server nicht überlasten
    return articles


def load_existing_articles(filename=DEFAULT_OUTPUT_PATH):
    path = Path(filename)
    if not path.exists():
        return {"status": "ok", "totalResults": 0, "articles": []}

    with open(path, encoding="utf-8") as file:
        return json.load(file)


def merge_new_articles(existing_data, fetched_data):
    existing_articles = existing_data.get("articles", [])
    fetched_articles = fetched_data.get("articles", [])
    existing_urls = {article.get("url") for article in existing_articles if article.get("url")}
    new_articles = [
        article for article in fetched_articles
        if article.get("url") and article.get("url") not in existing_urls
    ]

    merged_articles = existing_articles + new_articles
    merged_data = {
        **existing_data,
        "status": fetched_data.get("status", existing_data.get("status", "ok")),
        "totalResults": len(merged_articles),
        "articles": merged_articles,
    }

    return merged_data, new_articles


def save_articles(data, filename=DEFAULT_OUTPUT_PATH):
    path = Path(filename)
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=4, ensure_ascii=False)


def load_database(json_path=DEFAULT_OUTPUT_PATH):
    try:
        from database.database import load_articles_from_json
    except ModuleNotFoundError:
        print("Datenbank-Modul nicht gefunden. JSON wurde trotzdem gespeichert.")
        return

    try:
        imported, totals = load_articles_from_json(json_path)
    except Exception as e:
        print(f"DuckDB konnte nicht aktualisiert werden: {e}")
        return

    print(f"DuckDB aktualisiert: {imported} Artikel aus JSON gelesen.")
    print(f"Artikel insgesamt in DuckDB: {totals['articles']}")


def main():
    apikey = get_apikey()
    five_days_before, today = get_date_range(days_back=5)

    client = NewsApiClient(api_key=apikey)
    query = build_query(query="Ukraine AND (battlefield OR frontline OR territory OR gains OR map)")
    target_domains = (
        'understandingwar.org,kyivindependent.com,ukrinform.net,'
        'euromaidanpress.com,kyivpost.com,english.nv.ua,united24media.com'
    )

    try:
        all_articles = fetch_articles(client, query, target_domains, five_days_before, today)
    except RuntimeError as e:
        print(f"Abfrage fehlgeschlagen: {e}")
        return
    except Exception as e:
        print(f"Abfrage fehlgeschlagen: {e}")
        return

    print(f"Status: {all_articles.get('status')}")
    print(f"Gefundene Artikel: {all_articles.get('totalResults')}")

    if all_articles.get('totalResults', 0) == 0:
        print("Keine Treffer mit Domain-Filter. Versuche ohne 'domains'...")
        try:
            all_articles = client.get_everything(
                q=query, from_param=five_days_before, to=today,
                language='en', sort_by='relevancy', page_size=100
            )
        except Exception as e:
            print(f"Abfrage ohne Domain-Filter fehlgeschlagen: {e}")
            return

    articles = all_articles.get('articles', [])
    if not articles:
        print("Keine Artikel zum Anreichern gefunden.")
        return

    existing_data = load_existing_articles()
    all_articles, new_articles = merge_new_articles(existing_data, all_articles)

    if new_articles:
        print(f"Neue Artikel gefunden: {len(new_articles)}")
        print("Lade vollständige Texte für neue Artikel nach (kann etwas dauern)...")
        enrich_articles_with_full_text(new_articles)
    else:
        print("Keine neuen Artikel gefunden. JSON und Datenbank bleiben ohne Duplikate.")

    save_articles(all_articles)
    load_database()
    print(f"Fertig. {len(all_articles['articles'])} Artikel gespeichert in '{DEFAULT_OUTPUT_PATH}'.")


if __name__ == "__main__":
    main()
