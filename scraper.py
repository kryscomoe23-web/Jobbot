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
    location = config.get("localisation", "Paris")
    all_offers = []
    seen_urls = set()

    scrapers = {
        "indeed": scrape_indeed, "wttj": scrape_wttj,
        "apec": scrape_apec, "cadremploi": scrape_cadremploi,
        "hellowork": scrape_hellowork, "linkedin": scrape_linkedin,
    }

    for track_key in ["a", "b"]:
        track_cfg = config.get(f"track_{track_key}", {})
        if not track_cfg.get("enabled", True):
            continue
        for keyword in track_cfg.get("keywords", []):
            for site_key, fn in scrapers.items():
                if not sites.get(site_key, False):
                    continue
                try:
                    offers = fn(keyword, location)
                    for o in offers:
                        url = o.get("url", "")
                        if url and url in seen_urls:
                            continue
                        seen_urls.add(url)
                        o["track"] = track_key
                        all_offers.append(o)
                    time.sleep(random.uniform(1, 2))
                except Exception as e:
                    print(f"[{site_key}] {e}")

    return all_offers


def scrape_indeed(keyword, location):
    url = f"https://fr.indeed.com/jobs?q={requests.utils.quote(keyword)}&l={requests.utils.quote(location)}&sort=date"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")
        offers = []
        for card in soup.select("div.job_seen_beacon")[:8]:
            title = card.select_one("h2.jobTitle span")
            company = card.select_one("[data-testid='company-name']")
            loc = card.select_one("[data-testid='text-location']")
            salary = card.select_one("[class*='salary']")
            link = card.select_one("a[id^='job_']")
            if not title:
                continue
            href = link["href"] if link else ""
            offers.append({
                "title": title.get_text(strip=True),
                "company": company.get_text(strip=True) if company else "N/A",
                "location": loc.get_text(strip=True) if loc else location,
                "salary": salary.get_text(strip=True) if salary else "",
                "url": f"https://fr.indeed.com{href}" if href.startswith("/") else href,
                "site": "Indeed",
                "description": "",
            })
        return offers
    except Exception as e:
        print(f"[Indeed] {e}")
        return []


def scrape_wttj(keyword, location):
    url = f"https://www.welcometothejungle.com/fr/jobs?query={requests.utils.quote(keyword)}&aroundQuery={requests.utils.quote(location)}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")
        offers = []
        for card in soup.select("li[data-testid='search-results-list-item-wrapper']")[:8]:
            title = card.select_one("h4")
            company = card.select_one("span[data-testid='company-name']")
            loc = card.select_one("span[data-testid='job-location']")
            link = card.select_one("a")
            if not title:
                continue
            offers.append({
                "title": title.get_text(strip=True),
                "company": company.get_text(strip=True) if company else "N/A",
                "location": loc.get_text(strip=True) if loc else location,
                "salary": "",
                "url": "https://www.welcometothejungle.com" + link["href"] if link else "",
                "site": "Welcome to the Jungle",
                "description": "",
            })
        return offers
    except Exception as e:
        print(f"[WTTJ] {e}")
        return []


def scrape_apec(keyword, location):
    url = "https://www.apec.fr/cms/webservices/rechercheOffre/rechercheOffre"
    params = {"motsCles": keyword, "lieuTravail": location, "nbResultats": 10, "debut": 0}
    try:
        r = requests.get(url, params=params, headers=HEADERS, timeout=15)
        data = r.json()
        offers = []
        for item in data.get("resultats", [])[:8]:
            offers.append({
                "title": item.get("intitule", ""),
                "company": item.get("nomEmployeur", "N/A"),
                "location": item.get("lieuTravail", location),
                "salary": item.get("salaireTexte", ""),
                "url": f"https://www.apec.fr/candidat/recherche-emploi.html/emploi/{item.get('numeroOffre','')}",
                "site": "APEC",
                "description": item.get("texteHtml", "")[:1000],
            })
        return offers
    except Exception as e:
        print(f"[APEC] {e}")
        return []


def scrape_cadremploi(keyword, location):
    url = f"https://www.cadremploi.fr/emploi/liste_offres.html?intitule={requests.utils.quote(keyword)}&localisation={requests.utils.quote(location)}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")
        offers = []
        for card in soup.select("article.job-card, div.offer-card")[:8]:
            title = card.select_one("h2, h3")
            company = card.select_one("[class*='company'], [class*='entreprise']")
            loc = card.select_one("[class*='location'], [class*='lieu']")
            salary = card.select_one("[class*='salary'], [class*='salaire']")
            link = card.select_one("a")
            if not title:
                continue
            href = link["href"] if link else ""
            offers.append({
                "title": title.get_text(strip=True),
                "company": company.get_text(strip=True) if company else "N/A",
                "location": loc.get_text(strip=True) if loc else location,
                "salary": salary.get_text(strip=True) if salary else "",
                "url": href if href.startswith("http") else f"https://www.cadremploi.fr{href}",
                "site": "Cadremploi",
                "description": "",
            })
        return offers
    except Exception as e:
        print(f"[Cadremploi] {e}")
        return []


def scrape_hellowork(keyword, location):
    url = f"https://www.hellowork.com/fr-fr/emploi/recherche.html?k={requests.utils.quote(keyword)}&l={requests.utils.quote(location)}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")
        offers = []
        for card in soup.select("[data-cy='job-item'], article")[:8]:
            title = card.select_one("h2, h3, [data-cy='job-title']")
            company = card.select_one("[data-cy='company-name'], [class*='company']")
            loc = card.select_one("[data-cy='job-location'], [class*='location']")
            link = card.select_one("a")
            if not title:
                continue
            href = link["href"] if link else ""
            offers.append({
                "title": title.get_text(strip=True),
                "company": company.get_text(strip=True) if company else "N/A",
                "location": loc.get_text(strip=True) if loc else location,
                "salary": "",
                "url": href if href.startswith("http") else f"https://www.hellowork.com{href}",
                "site": "HelloWork",
                "description": "",
            })
        return offers
    except Exception as e:
        print(f"[HelloWork] {e}")
        return []


def scrape_linkedin(keyword, location):
    url = f"https://www.linkedin.com/jobs/search/?keywords={requests.utils.quote(keyword)}&location={requests.utils.quote(location)}&f_TPR=r86400"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")
        offers = []
        for card in soup.select("div.base-card")[:8]:
            title = card.select_one("h3.base-search-card__title, h3")
            company = card.select_one("h4.base-search-card__subtitle, h4")
            loc = card.select_one("span.job-search-card__location")
            link = card.select_one("a.base-card__full-link, a")
            if not title:
                continue
            offers.append({
                "title": title.get_text(strip=True),
                "company": company.get_text(strip=True) if company else "N/A",
                "location": loc.get_text(strip=True) if loc else location,
                "salary": "",
                "url": link["href"] if link else "",
                "site": "LinkedIn",
                "description": "",
            })
        return offers
    except Exception as e:
        print(f"[LinkedIn] {e}")
        return []
