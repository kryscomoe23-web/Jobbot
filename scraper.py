"""
Scraper léger — requêtes HTTP uniquement, pas de navigateur.
Compatible cloud (Railway, Render, etc.)
"""

import re
import time
import random
import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "fr-FR,fr;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def scrape_all(config: dict) -> list:
    sites = config.get("sites", {})
    keyword = config.get("poste_cible", "analyste crédit")
    location = config.get("localisation", "Paris")
    all_offers = []

    scrapers = {
        "indeed":     scrape_indeed,
        "wttj":       scrape_wttj,
        "apec":       scrape_apec,
        "cadremploi": scrape_cadremploi,
        "hellowork":  scrape_hellowork,
        "linkedin":   scrape_linkedin,
    }

    for key, fn in scrapers.items():
        if not sites.get(key, False):
            continue
        try:
            offers = fn(keyword, location)
            all_offers.extend(offers)
            time.sleep(random.uniform(1, 3))
        except Exception as e:
            print(f"[{key}] Erreur : {e}")

    return all_offers


# ─── Indeed ──────────────────────────────────────────────────────────────────

def scrape_indeed(keyword, location):
    url = f"https://fr.indeed.com/jobs?q={keyword.replace(' ', '+')}&l={location.replace(' ', '+')}&sort=date"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")
        offers = []
        for card in soup.select("div.job_seen_beacon")[:10]:
            title = card.select_one("h2.jobTitle span")
            company = card.select_one("[data-testid='company-name']")
            loc = card.select_one("[data-testid='text-location']")
            salary = card.select_one("[class*='salary']")
            link = card.select_one("a[id^='job_']")
            if not title:
                continue
            href = link["href"] if link else ""
            offers.append({
                "title":    title.get_text(strip=True),
                "company":  company.get_text(strip=True) if company else "N/A",
                "location": loc.get_text(strip=True) if loc else location,
                "salary":   salary.get_text(strip=True) if salary else "",
                "url":      f"https://fr.indeed.com{href}" if href.startswith("/") else href,
                "site":     "Indeed",
                "description": get_indeed_description(href) if href else "",
            })
        return offers
    except Exception as e:
        print(f"[Indeed] {e}")
        return []


def get_indeed_description(href):
    try:
        url = f"https://fr.indeed.com{href}" if href.startswith("/") else href
        r = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")
        desc = soup.select_one("#jobDescriptionText")
        return desc.get_text(strip=True)[:1500] if desc else ""
    except Exception:
        return ""


# ─── Welcome to the Jungle ───────────────────────────────────────────────────

def scrape_wttj(keyword, location):
    url = f"https://www.welcometothejungle.com/fr/jobs?query={requests.utils.quote(keyword)}&aroundQuery={requests.utils.quote(location)}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")
        offers = []
        for card in soup.select("li[data-testid='search-results-list-item-wrapper']")[:10]:
            title = card.select_one("h4")
            company = card.select_one("span[data-testid='company-name']")
            loc = card.select_one("span[data-testid='job-location']")
            link = card.select_one("a")
            if not title:
                continue
            offers.append({
                "title":    title.get_text(strip=True),
                "company":  company.get_text(strip=True) if company else "N/A",
                "location": loc.get_text(strip=True) if loc else location,
                "salary":   "",
                "url":      "https://www.welcometothejungle.com" + link["href"] if link else "",
                "site":     "Welcome to the Jungle",
                "description": "",
            })
        return offers
    except Exception as e:
        print(f"[WTTJ] {e}")
        return []


# ─── APEC ────────────────────────────────────────────────────────────────────

def scrape_apec(keyword, location):
    url = "https://www.apec.fr/cms/webservices/rechercheOffre/rechercheOffre"
    params = {
        "motsCles": keyword,
        "lieuTravail": location,
        "typesContrat": "",
        "nbResultats": 10,
        "debut": 0,
    }
    try:
        r = requests.get(url, params=params, headers=HEADERS, timeout=15)
        data = r.json()
        offers = []
        for item in data.get("resultats", [])[:10]:
            offers.append({
                "title":    item.get("intitule", ""),
                "company":  item.get("nomEmployeur", "N/A"),
                "location": item.get("lieuTravail", location),
                "salary":   item.get("salaireTexte", ""),
                "url":      f"https://www.apec.fr/candidat/recherche-emploi.html/emploi/{item.get('numeroOffre','')}",
                "site":     "APEC",
                "description": item.get("texteHtml", "")[:1500],
            })
        return offers
    except Exception as e:
        print(f"[APEC] {e}")
        return []


# ─── Cadremploi ──────────────────────────────────────────────────────────────

def scrape_cadremploi(keyword, location):
    url = f"https://www.cadremploi.fr/emploi/liste_offres.html?intitule={requests.utils.quote(keyword)}&localisation={requests.utils.quote(location)}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")
        offers = []
        for card in soup.select("article.job-card, div.offer-card")[:10]:
            title = card.select_one("h2, h3")
            company = card.select_one("[class*='company'], [class*='entreprise']")
            loc = card.select_one("[class*='location'], [class*='lieu']")
            salary = card.select_one("[class*='salary'], [class*='salaire']")
            link = card.select_one("a")
            if not title:
                continue
            href = link["href"] if link else ""
            offers.append({
                "title":    title.get_text(strip=True),
                "company":  company.get_text(strip=True) if company else "N/A",
                "location": loc.get_text(strip=True) if loc else location,
                "salary":   salary.get_text(strip=True) if salary else "",
                "url":      href if href.startswith("http") else f"https://www.cadremploi.fr{href}",
                "site":     "Cadremploi",
                "description": "",
            })
        return offers
    except Exception as e:
        print(f"[Cadremploi] {e}")
        return []


# ─── HelloWork ───────────────────────────────────────────────────────────────

def scrape_hellowork(keyword, location):
    url = f"https://www.hellowork.com/fr-fr/emploi/recherche.html?k={requests.utils.quote(keyword)}&l={requests.utils.quote(location)}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")
        offers = []
        for card in soup.select("[data-cy='job-item'], article")[:10]:
            title = card.select_one("h2, h3, [data-cy='job-title']")
            company = card.select_one("[data-cy='company-name'], [class*='company']")
            loc = card.select_one("[data-cy='job-location'], [class*='location']")
            link = card.select_one("a")
            if not title:
                continue
            href = link["href"] if link else ""
            offers.append({
                "title":    title.get_text(strip=True),
                "company":  company.get_text(strip=True) if company else "N/A",
                "location": loc.get_text(strip=True) if loc else location,
                "salary":   "",
                "url":      href if href.startswith("http") else f"https://www.hellowork.com{href}",
                "site":     "HelloWork",
                "description": "",
            })
        return offers
    except Exception as e:
        print(f"[HelloWork] {e}")
        return []


# ─── LinkedIn (public, sans login) ───────────────────────────────────────────

def scrape_linkedin(keyword, location):
    url = f"https://www.linkedin.com/jobs/search/?keywords={requests.utils.quote(keyword)}&location={requests.utils.quote(location)}&f_TPR=r86400"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")
        offers = []
        for card in soup.select("div.base-card, li.jobs-search-results__list-item")[:10]:
            title = card.select_one("h3.base-search-card__title, h3")
            company = card.select_one("h4.base-search-card__subtitle, h4")
            loc = card.select_one("span.job-search-card__location, [class*='location']")
            link = card.select_one("a.base-card__full-link, a")
            if not title:
                continue
            offers.append({
                "title":    title.get_text(strip=True),
                "company":  company.get_text(strip=True) if company else "N/A",
                "location": loc.get_text(strip=True) if loc else location,
                "salary":   "",
                "url":      link["href"] if link else "",
                "site":     "LinkedIn",
                "description": "",
            })
        return offers
    except Exception as e:
        print(f"[LinkedIn] {e}")
        return []
