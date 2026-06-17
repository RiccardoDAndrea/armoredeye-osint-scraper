import configparser
import json
import time
from datetime import datetime, timedelta

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


def get_apikey(path="credentials.conf"):
    parser = configparser.ConfigParser()
    if not parser.read(path):
        raise FileNotFoundError(f"Konfigurationsdatei nicht gefunden: {path}")
    apikey = parser.get("newsapi", "apikey", fallback="").strip()
    if not apikey:
        raise ValueError("Kein API-Key in der Sektion [newsapi] gefunden.")
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


def save_articles(data, filename="battlefield_changes.json"):
    with open(filename, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=4, ensure_ascii=False)


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

    print("Lade vollständige Artikeltexte nach (kann etwas dauern)...")
    articles = enrich_articles_with_full_text(articles)
    all_articles['articles'] = articles

    save_articles(all_articles)
    print(f"Fertig. {len(articles)} Artikel inkl. Volltext gespeichert in 'battlefield_changes.json'.")


if __name__ == "__main__":
    main()
