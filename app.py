import os
import json
import threading
import time
import random
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, jsonify, request, session, redirect, url_for
from database import init_db, get_db
from scorer import score_offer
from lm_generator import generate_lm
from scraper import scrape_all

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "jobbot-secret-change-me")
bot_state = {"running": False, "thread": None}

BOT_USERNAME = os.environ.get("BOT_USERNAME", "admin")
BOT_PASSWORD = os.environ.get("BOT_PASSWORD", "jobbot2024")


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "Non autorisé"}), 401
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        if username == BOT_USERNAME and password == BOT_PASSWORD:
            session["logged_in"] = True
            return redirect(url_for("index"))
        error = "Identifiants incorrects."
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

DEFAULT_CONFIG = {
    "poste_cible": "Analyste crédit senior",
    "keywords": ["credit analyst", "financement", "LBO", "DSCR", "risque crédit"],
    "localisation": "Paris",
    "salaire_min": 55000,
    "score_min": 7,
    "cv_path": "cv.pdf",
    "lm_template": "",
    "lm_tone": "direct",
    "frequence_minutes": 180,
    "sites": {
        "linkedin": True,
        "indeed": True,
        "wttj": True,
        "apec": True,
        "cadremploi": True,
        "hellowork": False
    },
    "profil_summary": "3 ans analyste crédit, IFCIC + BPI France. Expertise financement structuré, analyse LBO, DSCR/LLCR, covenants, SPV."
}


def load_config():
    if os.path.exists("config.json"):
        with open("config.json") as f:
            return json.load(f)
    return DEFAULT_CONFIG.copy()


def add_log(db, message, level="info"):
    db.execute(
        "INSERT INTO logs (message, level, created_at) VALUES (?, ?, ?)",
        (message, level, datetime.now().strftime("%H:%M:%S"))
    )
    db.commit()


# ─── Routes ──────────────────────────────────────────────────────────────────

@app.route("/")
@login_required
def index():
    return render_template("index.html")


@app.route("/api/bot/start", methods=["POST"])
@login_required
def start_bot():
    if bot_state["running"]:
        return jsonify({"ok": False, "msg": "Déjà en cours"})
    bot_state["running"] = True
    bot_state["thread"] = threading.Thread(target=bot_loop, daemon=True)
    bot_state["thread"].start()
    return jsonify({"ok": True})


@app.route("/api/bot/stop", methods=["POST"])
@login_required
def stop_bot():
    bot_state["running"] = False
    return jsonify({"ok": True})


@app.route("/api/bot/status")
@login_required
def bot_status():
    db = get_db()
    stats = db.execute("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN status='pending' THEN 1 ELSE 0 END) as pending,
            SUM(CASE WHEN status='sent'    THEN 1 ELSE 0 END) as sent,
            SUM(CASE WHEN status='skipped' THEN 1 ELSE 0 END) as skipped
        FROM offers
    """).fetchone()
    logs = db.execute("SELECT * FROM logs ORDER BY id DESC LIMIT 60").fetchall()
    return jsonify({
        "running": bot_state["running"],
        "stats": dict(stats),
        "logs": [dict(l) for l in logs],
    })


@app.route("/api/offers/queue")
@login_required
def get_queue():

    db = get_db()
    offers = db.execute(
        "SELECT * FROM offers WHERE status='pending' ORDER BY score DESC, created_at DESC"
    ).fetchall()
    return jsonify([dict(o) for o in offers])


@app.route("/api/offers/all")
@login_required
def get_all_offers():

    db = get_db()
    offers = db.execute(
        "SELECT * FROM offers ORDER BY created_at DESC LIMIT 100"
    ).fetchall()
    return jsonify([dict(o) for o in offers])


@app.route("/api/offers/<int:offer_id>/validate", methods=["POST"])
@login_required
def validate_offer(offer_id):

    data = request.json
    lm_final = data.get("lm", "")
    db = get_db()
    db.execute(
        "UPDATE offers SET status='sent', lm_final=?, sent_at=? WHERE id=?",
        (lm_final, datetime.now().isoformat(), offer_id)
    )
    db.commit()
    offer = db.execute("SELECT * FROM offers WHERE id=?", (offer_id,)).fetchone()
    add_log(db, f"[{offer['site']}] Candidature envoyée → {offer['company']} ({offer['title']})", "success")
    return jsonify({"ok": True})


@app.route("/api/offers/<int:offer_id>/skip", methods=["POST"])
@login_required
def skip_offer(offer_id):

    db = get_db()
    db.execute("UPDATE offers SET status='skipped' WHERE id=?", (offer_id,))
    db.commit()
    offer = db.execute("SELECT * FROM offers WHERE id=?", (offer_id,)).fetchone()
    add_log(db, f"[{offer['site']}] Ignorée : {offer['company']}", "warn")
    return jsonify({"ok": True})


@app.route("/api/offers/<int:offer_id>/regenerate_lm", methods=["POST"])
@login_required
def regen_lm(offer_id):

    db = get_db()
    offer = db.execute("SELECT * FROM offers WHERE id=?", (offer_id,)).fetchone()
    if not offer:
        return jsonify({"ok": False})
    config = load_config()
    new_lm = generate_lm(dict(offer), config)
    db.execute("UPDATE offers SET lm_draft=? WHERE id=?", (new_lm, offer_id))
    db.commit()
    return jsonify({"ok": True, "lm": new_lm})


@app.route("/api/config", methods=["GET"])
@login_required
def get_config():
    return jsonify(load_config())


@app.route("/api/config", methods=["POST"])
@login_required
def save_config():
    config = request.json
    with open("config.json", "w") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    return jsonify({"ok": True})


# ─── Bot loop ─────────────────────────────────────────────────────────────────

def bot_loop():
    db = get_db()
    config = load_config()
    add_log(db, "Bot démarré — mode validation manuelle", "success")
    add_log(db, f"Plateformes : {', '.join([k for k,v in config['sites'].items() if v])}", "info")

    while bot_state["running"]:
        config = load_config()
        add_log(db, "Nouvelle session de scraping...", "info")

        try:
            offers = scrape_all(config)
            add_log(db, f"{len(offers)} offres récupérées", "info")

            for offer in offers:
                if not bot_state["running"]:
                    break
                if not offer.get("title") or not offer.get("company"):
                    continue

                # Dédoublonnage par URL
                if offer.get("url"):
                    existing = db.execute(
                        "SELECT id FROM offers WHERE url=?", (offer["url"],)
                    ).fetchone()
                    if existing:
                        continue

                add_log(db, f"[{offer['site']}] Analyse : \"{offer['title']}\" chez {offer['company']}...", "info")

                scored = score_offer(offer, config)
                score = scored.get("score", 0)
                analysis = scored.get("analysis", "")

                add_log(db, f"[{offer['site']}] Score {score}/10 — {offer['company']}", "success" if score >= config['score_min'] else "info")

                if score >= config["score_min"]:
                    lm = generate_lm(offer, config)
                    db.execute("""
                        INSERT OR IGNORE INTO offers
                        (title, company, site, location, salary, url, score, ai_analysis, lm_draft, status, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
                    """, (
                        offer["title"], offer["company"], offer["site"],
                        offer.get("location", ""), offer.get("salary", ""),
                        offer.get("url", ""), score, analysis, lm,
                        datetime.now().isoformat()
                    ))
                    db.commit()
                    add_log(db, f"[{offer['site']}] → En file de validation : {offer['company']}", "success")

                time.sleep(random.uniform(2, 5))

        except Exception as e:
            add_log(db, f"Erreur : {str(e)}", "error")

        wait = config.get("frequence_minutes", 180) * 60
        add_log(db, f"Session terminée. Prochaine dans {config.get('frequence_minutes', 180)} min.", "info")
        elapsed = 0
        while elapsed < wait and bot_state["running"]:
            time.sleep(10)
            elapsed += 10

    db.execute("INSERT INTO logs (message, level, created_at) VALUES (?, ?, ?)",
               ("Bot arrêté.", "warn", datetime.now().strftime("%H:%M:%S")))
    db.commit()


if __name__ == "__main__":
    init_db()
    if not os.path.exists("config.json"):
        with open("config.json", "w") as f:
            json.dump(DEFAULT_CONFIG, f, indent=2, ensure_ascii=False)
    port = int(os.environ.get("PORT", 5000))
    print(f"\n  JobBot → http://localhost:{port}\n")
    app.run(host="0.0.0.0", port=port, debug=False)
