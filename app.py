import os
import io
import csv
import json
import threading
import time
import random
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, jsonify, request, session, redirect, url_for, Response
from database import get_db, init_db
from scorer import score_offer
from lm_generator import generate_lm
from scraper import scrape_all

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "jobbot-secret-change-me")
bot_state = {"running": False, "thread": None}

BOT_USERNAME = os.environ.get("BOT_USERNAME", "admin")
BOT_PASSWORD = os.environ.get("BOT_PASSWORD", "jobbot2024")

DEFAULT_CONFIG = {
    "localisation": "Paris",
    "frequence_minutes": 180,
    "lm_tone": "direct",
    "lm_template": "",
    "profil_summary": "3 ans analyste credit, IFCIC + BPI France. Expertise financement structure, analyse LBO, DSCR/LLCR, covenants, SPV.",
    "ft_departement": "75",
    "sites": {
        "linkedin": True, "efinancial": True,
        "hellowork": True, "francetravail": True
    },
    "track_a": {
        "enabled": True,
        "label": "Banque / Analyse credit",
        "score_min": 7,
        "salaire_min": 55000,
        "keywords": [
            "analyste credit senior",
            "credit risk analyst",
            "charge d affaires financement",
            "analyste risque credit",
            "charge de financement structure"
        ]
    },
    "track_b": {
        "enabled": True,
        "label": "Conseil / Advisory",
        "score_min": 7,
        "salaire_min": 55000,
        "keywords": [
            "consultant financement",
            "transaction services",
            "consultant corporate finance",
            "analyste M&A",
            "consultant restructuring"
        ]
    }
}


def load_config():
    env_config = os.environ.get("BOT_CONFIG")
    if env_config:
        try:
            return json.loads(env_config)
        except Exception:
            pass
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


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "Non autorise"}), 401
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        if request.form.get("username") == BOT_USERNAME and request.form.get("password") == BOT_PASSWORD:
            session["logged_in"] = True
            return redirect(url_for("index"))
        error = "Identifiants incorrects."
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def index():
    return render_template("index.html")


@app.route("/api/bot/start", methods=["POST"])
@login_required
def start_bot():
    if bot_state["running"]:
        return jsonify({"ok": False})
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
            SUM(CASE WHEN status='sent' THEN 1 ELSE 0 END) as sent,
            SUM(CASE WHEN status='skipped' THEN 1 ELSE 0 END) as skipped,
            SUM(CASE WHEN status='pending' AND track='a' THEN 1 ELSE 0 END) as pending_a,
            SUM(CASE WHEN status='pending' AND track='b' THEN 1 ELSE 0 END) as pending_b
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
    return jsonify([dict(o) for o in db.execute(
        "SELECT * FROM offers WHERE status='pending' ORDER BY score DESC, created_at DESC"
    ).fetchall()])


@app.route("/api/offers/all")
@login_required
def get_all_offers():
    db = get_db()
    return jsonify([dict(o) for o in db.execute(
        "SELECT * FROM offers ORDER BY created_at DESC LIMIT 200"
    ).fetchall()])


@app.route("/api/offers/export")
@login_required
def export_offers():
    db = get_db()
    offers = db.execute(
        "SELECT title, company, site, track, location, salary, url, score, ai_analysis, lm_draft, status, created_at FROM offers ORDER BY score DESC"
    ).fetchall()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Poste", "Entreprise", "Site", "Piste", "Lieu", "Salaire", "URL", "Score", "Analyse IA", "LM generee", "Statut", "Date"])
    for o in offers:
        writer.writerow([
            o["title"], o["company"], o["site"],
            "Banque" if o["track"] == "a" else "Conseil",
            o["location"], o["salary"], o["url"],
            o["score"], o["ai_analysis"], o["lm_draft"],
            o["status"], o["created_at"]
        ])
    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=offres_jobbot.csv"}
    )


@app.route("/api/offers/<int:offer_id>/validate", methods=["POST"])
@login_required
def validate_offer(offer_id):
    db = get_db()
    db.execute(
        "UPDATE offers SET status='sent', lm_final=?, sent_at=? WHERE id=?",
        (request.json.get("lm", ""), datetime.now().isoformat(), offer_id)
    )
    db.commit()
    offer = db.execute("SELECT * FROM offers WHERE id=?", (offer_id,)).fetchone()
    add_log(db, "[" + offer["site"] + "] Envoyee -> " + offer["company"] + " (" + offer["title"] + ")", "success")
    return jsonify({"ok": True})


@app.route("/api/offers/<int:offer_id>/skip", methods=["POST"])
@login_required
def skip_offer(offer_id):
    db = get_db()
    db.execute("UPDATE offers SET status='skipped' WHERE id=?", (offer_id,))
    db.commit()
    offer = db.execute("SELECT * FROM offers WHERE id=?", (offer_id,)).fetchone()
    add_log(db, "[" + offer["site"] + "] Ignoree : " + offer["company"], "warn")
    return jsonify({"ok": True})


@app.route("/api/offers/<int:offer_id>/regenerate_lm", methods=["POST"])
@login_required
def regen_lm(offer_id):
    db = get_db()
    offer = db.execute("SELECT * FROM offers WHERE id=?", (offer_id,)).fetchone()
    if not offer:
        return jsonify({"ok": False})
    config = load_config()
    tc = config.get("track_" + offer["track"], config.get("track_a", {}))
    tc.update({
        "profil_summary": config.get("profil_summary", ""),
        "lm_tone": config.get("lm_tone", "direct"),
        "lm_template": config.get("lm_template", "")
    })
    new_lm = generate_lm(dict(offer), tc)
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
    return jsonify({"ok": True, "json_to_save": json.dumps(config, ensure_ascii=False)})


def bot_loop():
    db = get_db()
    config = load_config()
    add_log(db, "Bot demarre - mode validation manuelle", "success")
    add_log(db, "Plateformes : " + ", ".join([k for k, v in config["sites"].items() if v]), "info")
    for t in ["a", "b"]:
        tc = config.get("track_" + t, {})
        if tc.get("enabled"):
            add_log(db, "Piste " + t.upper() + " [" + tc.get("label", "") + "] : " + str(len(tc.get("keywords", []))) + " intitules", "info")

    while bot_state["running"]:
        config = load_config()
        add_log(db, "Nouvelle session de scraping...", "info")
        try:
            known = [r["url"] for r in db.execute("SELECT url FROM offers WHERE url IS NOT NULL").fetchall()]
            all_offers = scrape_all(config, known_urls=known, log=lambda m, lvl="info": add_log(db, m, lvl))
            add_log(db, str(len(all_offers)) + " offres recuperees", "info")
            for offer in all_offers:
                if not bot_state["running"]:
                    break
                if not offer.get("title") or not offer.get("company"):
                    continue
                if offer.get("url") and db.execute("SELECT id FROM offers WHERE url=?", (offer["url"],)).fetchone():
                    continue
                track = offer.get("track", "a")
                tc = config.get("track_" + track, {})
                tc.update({
                    "profil_summary": config.get("profil_summary", ""),
                    "lm_tone": config.get("lm_tone", "direct"),
                    "lm_template": config.get("lm_template", "")
                })
                score_min = tc.get("score_min", 7)
                label = tc.get("label", track)
                add_log(db, "[" + offer["site"] + "][" + label + "] \"" + offer["title"] + "\" chez " + offer["company"] + "...", "info")
                scored = score_offer(offer, tc)
                score = scored.get("score", 0)
                add_log(db, "Score " + str(score) + "/10 - " + offer["company"], "success" if score >= score_min else "info")
                if score >= score_min:
                    lm = generate_lm(offer, tc)
                    db.execute(
                        "INSERT OR IGNORE INTO offers (title, company, site, track, location, salary, url, score, ai_analysis, lm_draft, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)",
                        (offer["title"], offer["company"], offer["site"], track,
                         offer.get("location", ""), offer.get("salary", ""), offer.get("url", ""),
                         score, scored.get("analysis", ""), lm, datetime.now().isoformat())
                    )
                    db.commit()
                    add_log(db, "[" + label + "] -> File de validation : " + offer["company"], "success")
                time.sleep(random.uniform(2, 4))
        except Exception as e:
            add_log(db, "Erreur : " + str(e), "error")

        wait = config.get("frequence_minutes", 180) * 60
        add_log(db, "Session terminee. Prochaine dans " + str(config.get("frequence_minutes", 180)) + " min.", "info")
        elapsed = 0
        while elapsed < wait and bot_state["running"]:
            time.sleep(10)
            elapsed += 10

    add_log(db, "Bot arrete.", "warn")


init_db()
if not os.path.exists("config.json"):
    with open("config.json", "w") as f:
        json.dump(DEFAULT_CONFIG, f, indent=2, ensure_ascii=False)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
