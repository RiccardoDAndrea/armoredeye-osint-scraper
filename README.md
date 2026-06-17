# 🛡️ ArmoredEye - Frontline News Scanner

**Eine Daten-Pipeline und OSINT-Erweiterung für das ArmoredEye-Projekt.**

Dieses Projekt sammelt automatisiert und hochaktuell Nachrichten, militärische Analysen und Berichte von den Frontlinien in der Ukraine. Es aggregiert Daten aus verifizierten und spezialisierten Quellen (wie dem *Institute for the Study of War*, *The Kyiv Independent*, *Ukrinform* etc.), um ein datengetriebenes Bild der aktuellen militärischen Lage zu zeichnen.

## 🎯 Ziel des Projekts
Während traditionelle Nachrichten oft verzögert berichten, zielt dieser Scraper darauf ab, Rohdaten und Berichte über Truppenbewegungen, Geländegewinne und Frontverschiebungen nahezu in Echtzeit zu sammeln und in einer zentralen Datenbank zu speichern.

### 🚀 Aktuelle Features
* **Automatisierte News-Aggregation:** Zieht Daten via NewsAPI aus ausgewählten militärischen und lokalen ukrainischen/internationalen Quellen.
* **Präzises Keyword-Targeting:** Filtert gezielt nach Begriffen wie *Battlefield, Frontline, Advance, Territory*, um irrelevanten Lärm auszublenden.
* **Robuste Datenspeicherung:** Speichert Artikel-Metadaten (Titel, Autor, URL, Zeitstempel und Volltext) in einer strukturierten Datenbank zur weiteren Verarbeitung.

### 🗺️ Roadmap (Geplante Features)
* [ ] **Sentiment Analysis (Stimmungsanalyse):** Implementierung von Natural Language Processing (NLP), um die gesammelten Texte zu analysieren. Ziel ist es, die "Stimmung" oder das Momentum an bestimmten Frontabschnitten (z. B. Pokrowsk, Kursk, Charkiw) messbar zu machen (Offensiv, Defensiv, Kritisch, Stabil).
* [ ] **Entity Extraction:** Automatisches Erkennen von Städtenamen und Waffensystemen in den Texten.
* [ ] **Dashboard-Integration:** Visualisierung der Daten und Stimmungs-Graphen im ArmoredEye-Hauptprojekt.

## 🛠️ Tech Stack
* **Sprache:** Python 3.x
* **APIs:** NewsAPI
* **Datenbank:** PostgreSQL (oder JSON im frühen Stadium)
* *(Geplant für NLP: NLTK, spaCy oder Hugging Face Transformers)*
