"""
Candidatures : lettre de motivation en PDF, brouillons Gmail, suivi des envois,
detection des reponses et brouillons de relance.

Gmail est utilise en IMAP avec un "mot de passe d'application" Google :
  GMAIL_ADDRESS       ton adresse Gmail
  GMAIL_APP_PASSWORD  mot de passe d'application (myaccount.google.com/apppasswords)
Le bot ne fait que CREER des brouillons : c'est toi qui cliques sur Envoyer dans Gmail.
"""

import imaplib
import io
import os
import re
import time
import unicodedata
from datetime import datetime, timedelta
from email.message import EmailMessage
from email.parser import BytesHeaderParser
from email.utils import formataddr, formatdate, make_msgid, parsedate_to_datetime
from xml.sax.saxutils import escape

IMAP_HOST = "imap.gmail.com"
CV_PATH = os.environ.get("CV_PATH", "cv.pdf")
RELANCE_MODEL = "claude-haiku-4-5-20251001"

MOIS = ["janvier", "fevrier", "mars", "avril", "mai", "juin", "juillet",
        "aout", "septembre", "octobre", "novembre", "decembre"]
MOIS_ACCENTS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
                "août", "septembre", "octobre", "novembre", "décembre"]
IMAP_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

DEFAULT_EMAIL_TEMPLATE = (
    "Madame, Monsieur,\n\n"
    "Je vous adresse ma candidature au poste de {poste} au sein de {entreprise}. "
    "Vous trouverez ci-joint mon CV ainsi que ma lettre de motivation.\n\n"
    "Je me tiens à votre disposition pour un entretien.\n\n"
    "Bien cordialement,\n\n"
    "{nom}\n{telephone}"
)

SENT_STATUSES = ("sent", "followup", "replied", "interview", "rejected", "offer")


class CandidatureError(Exception):
    """Erreur affichable telle quelle dans l'interface."""


# --------------------------------------------------------------------------
# Utilitaires
# --------------------------------------------------------------------------

def gmail_configured():
    return bool(os.environ.get("GMAIL_ADDRESS") and os.environ.get("GMAIL_APP_PASSWORD"))


def candidate(config):
    return {
        "nom": (config.get("candidat_nom") or "").strip(),
        "email": (config.get("candidat_email") or os.environ.get("GMAIL_ADDRESS") or "").strip(),
        "telephone": (config.get("candidat_tel") or "").strip(),
    }


def _ascii_slug(text, maxlen=40):
    for a, b in (("Œ", "OE"), ("œ", "oe"), ("Æ", "AE"), ("æ", "ae"), ("ß", "ss")):
        text = (text or "").replace(a, b)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_")
    return text[:maxlen] or "x"


def _elide(text):
    """Corrige « de Analyste » -> « d'Analyste » devant une voyelle (pas devant « h » : titres anglais)."""
    return re.sub(r"\b(de|que|le) ([AEIOUaeiouÀÂÉÈÊÎÔÛàâéèêîôû])", lambda m: m.group(1)[0] + "'" + m.group(2), text)


def default_subject(offer, config):
    nom = candidate(config)["nom"]
    subject = "Candidature – " + (offer.get("title") or "")
    return subject + (" – " + nom if nom else "")


def email_body(offer, config):
    c = candidate(config)
    tpl = config.get("email_template") or DEFAULT_EMAIL_TEMPLATE
    body = tpl.replace("de {poste}", _elide("de " + (offer.get("title") or "")))
    body = (body.replace("{poste}", offer.get("title") or "")
                .replace("{entreprise}", offer.get("company") or "")
                .replace("{nom}", c["nom"])
                .replace("{telephone}", c["telephone"])
                .replace("{email}", c["email"]))
    return body.rstrip() + "\n"


_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_EMAIL_BLOCKLIST = ("noreply", "no-reply", "donotreply", "linkedin.com", "example.", "sentry",
                    "francetravail.fr", "pole-emploi", "hellowork.com", "efinancialcareers")


def extract_email(text):
    """Premiere adresse email plausible de recruteur trouvee dans la description."""
    for m in _EMAIL_RE.findall(text or ""):
        low = m.lower()
        if low.endswith((".png", ".jpg", ".gif", ".svg", ".webp")):
            continue
        if any(b in low for b in _EMAIL_BLOCKLIST):
            continue
        return m
    return ""


def cv_info():
    if os.path.exists(CV_PATH):
        return {"exists": True, "size_kb": round(os.path.getsize(CV_PATH) / 1024)}
    return {"exists": False, "size_kb": 0}


def save_cv(data):
    if not data.startswith(b"%PDF"):
        raise CandidatureError("Le fichier n'est pas un PDF.")
    if len(data) > 5 * 1024 * 1024:
        raise CandidatureError("Le CV depasse 5 Mo.")
    with open(CV_PATH, "wb") as f:
        f.write(data)


def _date_fr(d=None):
    d = d or datetime.now()
    return str(d.day) + " " + MOIS_ACCENTS[d.month - 1] + " " + str(d.year)


def _imap_date(d):
    return "%02d-%s-%d" % (d.day, IMAP_MONTHS[d.month - 1], d.year)


# --------------------------------------------------------------------------
# Lettre de motivation en PDF
# --------------------------------------------------------------------------

def _pdf_text(s):
    # Helvetica (WinAnsi) gere les accents, l'euro, les guillemets ; on remplace le reste
    for a, b in ((" ", " "), (" ", " "), ("‑", "-"), ("−", "-")):
        s = s.replace(a, b)
    return escape(s)


def build_lm_pdf(offer, lm_text, config):
    try:
        from reportlab.lib.enums import TA_JUSTIFY, TA_RIGHT
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
    except ImportError:
        raise CandidatureError("Module reportlab manquant : relance « Lancer JobBot.bat » pour l'installer.")

    c = candidate(config)
    base = ParagraphStyle("base", fontName="Helvetica", fontSize=10.5, leading=15.5)
    body = ParagraphStyle("body", parent=base, alignment=TA_JUSTIFY, spaceAfter=9)
    right = ParagraphStyle("right", parent=base, alignment=TA_RIGHT)
    bold = ParagraphStyle("bold", parent=base, fontName="Helvetica-Bold", fontSize=12, leading=16)

    story = []
    if c["nom"]:
        story.append(Paragraph(_pdf_text(c["nom"]), bold))
    contact = " · ".join(x for x in (c["email"], c["telephone"]) if x)
    if contact:
        story.append(Paragraph(_pdf_text(contact), base))
    story.append(Spacer(1, 0.6 * cm))
    story.append(Paragraph(_pdf_text((config.get("localisation") or "Paris") + ", le " + _date_fr()), right))
    story.append(Spacer(1, 0.4 * cm))
    story.append(Paragraph(_pdf_text(offer.get("company") or ""), base))
    story.append(Paragraph("Service recrutement", base))
    story.append(Spacer(1, 0.6 * cm))
    story.append(Paragraph("<b>Objet :</b> " + _pdf_text(_elide("Candidature au poste de " + (offer.get("title") or ""))), base))
    story.append(Spacer(1, 0.5 * cm))

    for para in re.split(r"\n\s*\n", (lm_text or "").strip()):
        if para.strip():
            story.append(Paragraph(_pdf_text(para.strip()).replace("\n", "<br/>"), body))

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=2.3 * cm, rightMargin=2.3 * cm,
                            topMargin=2 * cm, bottomMargin=2 * cm,
                            title="Lettre de motivation", author=c["nom"] or "JobBot")
    doc.build(story)
    return buf.getvalue()


def lm_filename(offer, config):
    nom = candidate(config)["nom"]
    return "LM_" + (_ascii_slug(nom) + "_" if nom else "") + _ascii_slug(offer.get("company")) + ".pdf"


# --------------------------------------------------------------------------
# Gmail (IMAP)
# --------------------------------------------------------------------------

def _connect():
    if not gmail_configured():
        raise CandidatureError("Gmail n'est pas configure : ajoute GMAIL_ADDRESS et GMAIL_APP_PASSWORD dans .env.")
    try:
        imap = imaplib.IMAP4_SSL(IMAP_HOST, timeout=30)
        imap.login(os.environ["GMAIL_ADDRESS"], os.environ["GMAIL_APP_PASSWORD"].replace(" ", ""))
        return imap
    except imaplib.IMAP4.error:
        raise CandidatureError("Connexion Gmail refusee : verifie l'adresse et le mot de passe d'application.")
    except OSError as e:
        raise CandidatureError("Impossible de joindre Gmail : " + str(e))


_LIST_RE = re.compile(r'\((?P<flags>[^)]*)\) "(?P<delim>[^"]*)" (?P<name>.+)$')


def _find_folder(imap, flag):
    """Dossier special Gmail (\\Drafts, \\Sent...) quelle que soit la langue du compte."""
    typ, data = imap.list()
    for raw in data or []:
        line = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else str(raw)
        m = _LIST_RE.match(line)
        if m and flag.lower() in m.group("flags").lower():
            name = m.group("name").strip()
            return name if name.startswith('"') else '"' + name + '"'
    raise CandidatureError("Dossier Gmail " + flag + " introuvable.")


def test_gmail():
    imap = _connect()
    try:
        _find_folder(imap, "\\Drafts")
        _find_folder(imap, "\\Sent")
        return "Connexion Gmail OK (" + os.environ["GMAIL_ADDRESS"] + ")."
    finally:
        imap.logout()


def _build_message(config, to, subject, body, attachments=(), in_reply_to=None):
    c = candidate(config)
    msg = EmailMessage()
    msg["From"] = formataddr((c["nom"], os.environ.get("GMAIL_ADDRESS", c["email"])))
    if to:
        msg["To"] = to
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain="jobbot.local")
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = in_reply_to
    msg.set_content(body)
    for filename, data in attachments:
        msg.add_attachment(data, maintype="application", subtype="pdf", filename=filename)
    return msg


def _append_draft(imap, msg):
    folder = _find_folder(imap, "\\Drafts")
    typ, data = imap.append(folder, "(\\Draft)", imaplib.Time2Internaldate(time.time()), msg.as_bytes())
    if typ != "OK":
        raise CandidatureError("Gmail a refuse le brouillon : " + str(data))


def create_application_draft(offer, config, lm_text, to, subject, body=None):
    """Cree le brouillon de candidature (CV + LM en PDF) dans Gmail."""
    if not cv_info()["exists"]:
        raise CandidatureError("Ajoute d'abord ton CV (PDF) dans l'onglet Config.")
    attachments = []
    with open(CV_PATH, "rb") as f:
        nom = candidate(config)["nom"]
        attachments.append(("CV_" + (_ascii_slug(nom) if nom else "candidat") + ".pdf", f.read()))
    attachments.append((lm_filename(offer, config), build_lm_pdf(offer, lm_text, config)))
    msg = _build_message(config, to, subject, body or email_body(offer, config), attachments)
    imap = _connect()
    try:
        _append_draft(imap, msg)
    finally:
        imap.logout()


# --------------------------------------------------------------------------
# Suivi : envois, reponses, relances
# --------------------------------------------------------------------------

def _search(imap, *criteria, literal=None):
    if literal is not None:
        imap.literal = literal.encode("utf-8")
        typ, data = imap.uid("SEARCH", "CHARSET", "UTF-8", *criteria)
    else:
        typ, data = imap.uid("SEARCH", *criteria)
    if typ != "OK" or not data or not data[0]:
        return []
    return data[0].split()


def _headers(imap, uid):
    typ, data = imap.uid("FETCH", uid, "(BODY.PEEK[HEADER.FIELDS (MESSAGE-ID DATE SUBJECT)])")
    for part in data or []:
        if isinstance(part, tuple):
            return BytesHeaderParser().parsebytes(part[1])
    return None


def _relance_text(offer, config, sent_date):
    c = candidate(config)
    fallback = (
        "Madame, Monsieur,\n\n"
        "Je me permets de revenir vers vous au sujet de ma candidature au poste "
        + _elide("de " + (offer.get("title") or "")) + ", envoyée le " + _date_fr(sent_date) + ". "
        "Ce poste correspond pleinement à mon parcours et je reste très motivé(e) à l'idée de rejoindre "
        + (offer.get("company") or "votre équipe") + ".\n\n"
        "Je serais ravi(e) d'échanger avec vous lors d'un entretien.\n\n"
        "Bien cordialement,\n\n" + c["nom"] + "\n" + c["telephone"] + "\n"
    )
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return fallback
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
        prompt = (
            "Redige un email de relance court (4 phrases maximum) et professionnel, en francais, "
            "pour une candidature restee sans reponse.\n"
            "Poste : " + (offer.get("title") or "") + "\n"
            "Entreprise : " + (offer.get("company") or "") + "\n"
            "Candidature envoyee le : " + _date_fr(sent_date) + "\n"
            "Profil : " + (config.get("profil_summary") or "") + "\n\n"
            "Commence par « Madame, Monsieur, ». Pas d'objet. Rappelle la candidature, reaffirme "
            "la motivation en une phrase concrete liee au poste, propose un echange. "
            "Termine par « Bien cordialement, » puis sur deux lignes : " + c["nom"] + " / " + c["telephone"] + ".\n"
            "Ecris uniquement l'email."
        )
        r = client.messages.create(model=RELANCE_MODEL, max_tokens=400,
                                   messages=[{"role": "user", "content": prompt}])
        text = r.content[0].text.strip()
        return text + "\n" if text else fallback
    except Exception:
        return fallback


def check_followups(db, config, log=None):
    """
    Passe sur les candidatures et met a jour leur statut :
      brouillon -> envoyee   (le mail est apparu dans le dossier Envoyes)
      envoyee   -> reponse   (un mail est arrive de l'adresse du recruteur)
      envoyee   -> relance   (sans reponse apres N jours : brouillon de relance cree)
    """
    log = log or (lambda m, level="info": None)
    result = {"envois": 0, "reponses": 0, "relances": 0}
    if not gmail_configured():
        return result
    relance_days = int(config.get("relance_jours") or 7)
    now = datetime.now()

    imap = _connect()
    try:
        sent_folder = _find_folder(imap, "\\Sent")

        # 1. Brouillons envoyes ?
        drafts = db.execute("SELECT * FROM offers WHERE status='draft'").fetchall()
        if drafts:
            imap.select(sent_folder, readonly=True)
            for o in drafts:
                since = _imap_date(datetime.fromisoformat(o["draft_at"] or o["created_at"]) - timedelta(days=1))
                if o["contact_email"]:
                    uids = _search(imap, "SINCE", since, "TO", '"' + o["contact_email"] + '"')
                else:
                    uids = _search(imap, "SINCE", since, "SUBJECT", literal=o["email_subject"] or o["title"])
                if not uids:
                    continue
                h = _headers(imap, uids[-1])
                sent_at = now
                if h and h.get("Date"):
                    try:
                        sent_at = parsedate_to_datetime(h["Date"]).astimezone().replace(tzinfo=None)
                    except Exception:
                        pass
                db.execute("UPDATE offers SET status='sent', sent_at=?, sent_message_id=? WHERE id=?",
                           (sent_at.isoformat(timespec="seconds"), (h.get("Message-ID") if h else "") or "", o["id"]))
                db.commit()
                result["envois"] += 1
                log("[Suivi] Candidature envoyee detectee : " + o["company"], "success")

        # 2. Reponses recues ?
        waiting = db.execute(
            "SELECT * FROM offers WHERE status IN ('sent','followup') AND contact_email IS NOT NULL AND contact_email != ''"
        ).fetchall()
        if waiting:
            imap.select("INBOX", readonly=True)
            for o in waiting:
                since = _imap_date(datetime.fromisoformat(o["sent_at"] or o["created_at"]))
                if _search(imap, "SINCE", since, "FROM", '"' + o["contact_email"] + '"'):
                    db.execute("UPDATE offers SET status='replied', replied_at=? WHERE id=?",
                               (now.isoformat(timespec="seconds"), o["id"]))
                    db.commit()
                    result["reponses"] += 1
                    log("[Suivi] Reponse recue de " + o["company"] + " !", "success")

        # 3. Relances a preparer
        due = db.execute(
            "SELECT * FROM offers WHERE status='sent' AND contact_email IS NOT NULL AND contact_email != '' "
            "AND sent_at IS NOT NULL AND followup_at IS NULL"
        ).fetchall()
        for o in due:
            sent_date = datetime.fromisoformat(o["sent_at"])
            if now - sent_date < timedelta(days=relance_days):
                continue
            subject = o["email_subject"] or default_subject(dict(o), config)
            if not subject.lower().startswith("re:"):
                subject = "Re: " + subject
            msg = _build_message(config, o["contact_email"], subject,
                                 _relance_text(dict(o), config, sent_date),
                                 in_reply_to=o["sent_message_id"] or None)
            _append_draft(imap, msg)
            db.execute("UPDATE offers SET status='followup', followup_at=? WHERE id=?",
                       (now.isoformat(timespec="seconds"), o["id"]))
            db.commit()
            result["relances"] += 1
            log("[Suivi] Brouillon de relance cree pour " + o["company"], "success")
    finally:
        try:
            imap.logout()
        except Exception:
            pass
    return result
