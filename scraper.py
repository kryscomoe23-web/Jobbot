"""
Scrapers JobBot (HTTP, sans navigateur).

Sources (LinkedIn, eFinancialCareers et HelloWork testees le 06/11/2026 ;
France Travail ecrit d'apres la doc officielle, a valider avec tes cles) :
  - linkedin      : API publique "jobs-guest" + page de detail (description)
  - efinancial    : API JSON publique d'eFinancialCareers (resume inclus)
  - hellowork     : page de resultats HTML + JSON-LD de la page offre (description)
  - francetravail : API officielle France Travail (cles gratuites sur francetravail.io)

Sources retirees : Indeed, APEC et Cadremploi bloquent les robots (captcha /
Cloudflare) ; Welcome to the Jungle n'a plus de recherche publique (compte
obligatoire) ; Wizbii cible stages/alternances et son URL de recherche n'existe plus.
"""

import json
import os
import random
import re
import time
from urllib.parse import urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
HEADERS = {
    "User-Agent": UA,
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
TIMEOUT = 20
MAX_PER_KEYWORD = 8
DESC_MAX = 3000


class SiteBlocked(Exception):
    """Le site refuse nos requetes (403/429) : on arrete ce site pour la session."""


def _session():
    s = requests.Session()
    s.headers.update(HEADERS)
    return s


def _get(s, url, **kw):
    r = s.get(url, timeout=TIMEOUT, **kw)
    if r.status_code == 429:
        # Trop de requetes : on patiente une fois avant d'abandonner le site
        time.sleep(random.uniform(20, 35))
        r = s.get(url, timeout=TIMEOUT, **kw)
    if r.status_code in (403, 429, 999):
        raise SiteBlocked("HTTP " + str(r.status_code))
    r.raise_for_status()
    return r


def _clean_url(url):
    """Retire les parametres de tracking pour que la deduplication par URL marche."""
    if not url:
        return ""
    p = urlsplit(url)
    return urlunsplit((p.scheme, p.netloc, p.path, "", ""))


def _html_to_text(html):
    if not html:
        return ""
    text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    return re.sub(r"\s+", " ", text)[:DESC_MAX]


def _txt(el):
    return el.get_text(" ", strip=True) if el else ""


def _pause(a=1.0, b=2.5):
    time.sleep(random.uniform(a, b))


# --------------------------------------------------------------------------
# LinkedIn (API invitee, sans connexion)
# --------------------------------------------------------------------------

def scrape_linkedin(s, keyword, location, cfg):
    r = _get(s, "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search", params={
        "keywords": keyword,
        "location": location,
        "f_TPR": "r604800",   # 7 derniers jours
        "sortBy": "DD",       # plus recentes d'abord
        "start": 0,
    })
    soup = BeautifulSoup(r.text, "html.parser")
    offers = []
    for card in soup.select("div.base-card")[:MAX_PER_KEYWORD]:
        urn = card.get("data-entity-urn", "")
        job_id = urn.rsplit(":", 1)[-1] if urn else ""
        title = _txt(card.select_one("h3.base-search-card__title"))
        if not title or not job_id:
            continue
        offers.append({
            "title": title,
            "company": _txt(card.select_one("h4.base-search-card__subtitle")) or "N/A",
            "location": _txt(card.select_one("span.job-search-card__location")) or location,
            "salary": _txt(card.select_one("span.job-search-card__salary-info")),
            "url": "https://www.linkedin.com/jobs/view/" + job_id,
            "site": "LinkedIn",
            "description": "",
            "_detail": job_id,
        })
    return offers


def detail_linkedin(s, offer):
    r = _get(s, "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/" + offer["_detail"])
    soup = BeautifulSoup(r.text, "html.parser")
    return _txt(soup.select_one("div.show-more-less-html__markup"))[:DESC_MAX]


# --------------------------------------------------------------------------
# eFinancialCareers (API JSON publique utilisee par leur site)
# --------------------------------------------------------------------------

def scrape_efinancial(s, keyword, location, cfg):
    r = _get(s, "https://job-search-ui.efinancialcareers.com/v1/efc/jobs/search", params={
        "q": keyword,
        "location": location,
        "page": 1,
        "pageSize": MAX_PER_KEYWORD,
        "currencyCode": "EUR",
        "culture": "fr",
        "includeRemote": "false",
        "includeUnspecifiedSalary": "true",
    }, headers={"Accept": "application/json"})
    offers = []
    for j in r.json().get("data", [])[:MAX_PER_KEYWORD]:
        if not j.get("title"):
            continue
        loc = (j.get("jobLocation") or {}).get("displayName", location)
        offers.append({
            "title": j["title"],
            "company": j.get("companyName") or j.get("clientBrandName") or "N/A",
            "location": loc,
            "salary": j.get("salary") or "",
            "url": _clean_url("https://www.efinancialcareers.fr" + j.get("detailsPageUrl", "")),
            "site": "eFinancialCareers",
            "description": (j.get("summary") or "")[:DESC_MAX],
        })
    return offers


# --------------------------------------------------------------------------
# HelloWork (HTML)
# --------------------------------------------------------------------------

def scrape_hellowork(s, keyword, location, cfg):
    r = _get(s, "https://www.hellowork.com/fr-fr/emploi/recherche.html", params={"k": keyword, "l": location})
    soup = BeautifulSoup(r.text, "html.parser")
    offers = []
    for card in soup.select("[data-cy='serpCard']")[:MAX_PER_KEYWORD]:
        link = card.select_one("a[data-cy='offerTitle']")
        if not link or not link.get("href"):
            continue
        h3 = link.select_one("h3")
        spans = h3.select("span") if h3 else []
        title = _txt(spans[0]) if spans else _txt(link)
        company = _txt(spans[1]) if len(spans) > 1 else "N/A"
        salary = _txt(card.select_one("div.typo-s-bold"))
        href = link["href"]
        offers.append({
            "title": title,
            "company": company,
            "location": _txt(card.select_one("[data-cy='localisationCard']")) or location,
            "salary": salary if "€" in salary else "",
            "url": _clean_url(href if href.startswith("http") else "https://www.hellowork.com" + href),
            "site": "HelloWork",
            "description": "",
            "_detail": True,
        })
    return offers


def detail_hellowork(s, offer):
    r = _get(s, offer["url"])
    soup = BeautifulSoup(r.text, "html.parser")
    for tag in soup.find_all("script", type=re.compile("ld")):
        try:
            data = json.loads(tag.string or "")
        except Exception:
            continue
        if isinstance(data, dict) and data.get("@type") == "JobPosting":
            return _html_to_text(data.get("description", ""))
    return ""


# --------------------------------------------------------------------------
# France Travail (API officielle, gratuite)
# Variables d'environnement : FT_CLIENT_ID et FT_CLIENT_SECRET
# --------------------------------------------------------------------------

_ft_token = {"value": None, "expires": 0}


def _ft_get_token(s):
    if _ft_token["value"] and time.time() < _ft_token["expires"] - 60:
        return _ft_token["value"]
    r = s.post(
        "https://entreprise.francetravail.fr/connexion/oauth2/access_token",
        params={"realm": "/partenaire"},
        data={
            "grant_type": "client_credentials",
            "client_id": os.environ["FT_CLIENT_ID"],
            "client_secret": os.environ["FT_CLIENT_SECRET"],
            "scope": "api_offresdemploiv2 o2dsoffre",
        },
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    data = r.json()
    _ft_token["value"] = data["access_token"]
    _ft_token["expires"] = time.time() + int(data.get("expires_in", 1400))
    return _ft_token["value"]


def scrape_francetravail(s, keyword, location, cfg):
    if not (os.environ.get("FT_CLIENT_ID") and os.environ.get("FT_CLIENT_SECRET")):
        raise SiteBlocked("cles API manquantes (FT_CLIENT_ID / FT_CLIENT_SECRET)")
    token = _ft_get_token(s)
    # L'API veut des mots-cles separes par des virgules, 2 caracteres minimum chacun
    words = [w for w in re.split(r"[\s']+", keyword) if len(w) >= 2]
    r = s.get(
        "https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search",
        params={
            "motsCles": ",".join(words),
            "departement": cfg.get("ft_departement", "75"),
            "sort": 1,
            "range": "0-" + str(MAX_PER_KEYWORD - 1),
        },
        headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
        timeout=TIMEOUT,
    )
    if r.status_code == 204:
        return []
    if r.status_code in (401, 403, 429):
        raise SiteBlocked("HTTP " + str(r.status_code))
    r.raise_for_status()
    offers = []
    for j in r.json().get("resultats", []):
        origine = (j.get("origineOffre") or {}).get("urlOrigine")
        offers.append({
            "title": j.get("intitule", ""),
            "company": (j.get("entreprise") or {}).get("nom") or "N/A",
            "location": (j.get("lieuTravail") or {}).get("libelle", location),
            "salary": (j.get("salaire") or {}).get("libelle", ""),
            "url": origine or "https://candidat.francetravail.fr/offres/recherche/detail/" + str(j.get("id", "")),
            "site": "France Travail",
            "description": (j.get("description") or "")[:DESC_MAX],
        })
    return offers


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------

SCRAPERS = {
    "linkedin": (scrape_linkedin, detail_linkedin),
    "efinancial": (scrape_efinancial, None),
    "hellowork": (scrape_hellowork, detail_hellowork),
    "francetravail": (scrape_francetravail, None),
}


def scrape_all(config, known_urls=None, log=None):
    """
    Recupere les offres de toutes les sources actives, pour chaque mot-cle des pistes A et B.

    known_urls : URLs deja en base -> ignorees AVANT de charger leur description
                 (economise des requetes et des appels Claude).
    log        : fonction log(message, level) optionnelle pour l'interface.
    """
    log = log or (lambda msg, level="info": print(msg))
    known = set(known_urls or [])
    sites = config.get("sites", {})
    location = config.get("localisation", "Paris")
    s = _session()

    all_offers, seen = [], set()
    blocked = set()
    counts = {}

    for track_key in ["a", "b"]:
        track_cfg = config.get("track_" + track_key, {})
        if not track_cfg.get("enabled", True):
            continue
        for keyword in track_cfg.get("keywords", []):
            for site_key, (search_fn, detail_fn) in SCRAPERS.items():
                if not sites.get(site_key, False) or site_key in blocked:
                    continue
                try:
                    offers = search_fn(s, keyword, location, config)
                except SiteBlocked as e:
                    blocked.add(site_key)
                    log("[" + site_key + "] desactive pour cette session : " + str(e), "warn")
                    continue
                except Exception as e:
                    log("[" + site_key + "] erreur sur \"" + keyword + "\" : " + str(e), "error")
                    continue

                for o in offers:
                    url = o.get("url", "")
                    if not url or url in seen or url in known:
                        continue
                    seen.add(url)
                    if detail_fn and site_key not in blocked:
                        try:
                            o["description"] = detail_fn(s, o)
                            _pause(2, 4) if site_key == "linkedin" else _pause(0.8, 1.8)
                        except SiteBlocked as e:
                            blocked.add(site_key)
                            log("[" + site_key + "] descriptions bloquees : " + str(e), "warn")
                        except Exception:
                            pass  # on garde l'offre sans description
                    o.pop("_detail", None)
                    o["track"] = track_key
                    all_offers.append(o)
                    counts[site_key] = counts.get(site_key, 0) + 1
                _pause()

    if counts:
        log("Nouvelles offres par source : " + ", ".join(k + "=" + str(v) for k, v in counts.items()), "info")
    return all_offers
