# JobBot Cloud

Bot qui récupère des offres d'emploi finance, les fait noter par Claude, rédige une
lettre de motivation pour les meilleures et les met en file de validation.

## Sources d'offres

| Source | Méthode | Description de l'offre |
|---|---|---|
| LinkedIn | API publique « jobs-guest » (sans connexion) | oui (page de détail) |
| eFinancialCareers | API JSON publique | oui (résumé) |
| HelloWork | Page de résultats HTML | oui (page de détail) |
| France Travail | API officielle (clés gratuites) | oui |

Retirées : Indeed, APEC et Cadremploi bloquent les robots (captcha / Cloudflare),
Welcome to the Jungle exige désormais un compte pour chercher, Wizbii ne vise que
stages et alternances. France Travail reprend une bonne partie des offres de ces sites.

Les offres déjà en base sont ignorées avant de charger leur description : on économise
des requêtes et des appels Claude. Si un site répond « trop de requêtes » (429), le bot
patiente une fois puis le met de côté jusqu'à la session suivante.

## Lancer sur ton PC (Windows, gratuit)

1. Double-clique sur **Lancer JobBot.bat**.
2. Au premier lancement, le fichier `.env` s'ouvre dans le Bloc-notes : colle ta clé
   Anthropic après `ANTHROPIC_API_KEY=`, enregistre, ferme, puis relance le .bat.
3. La première fois, l'installation prend environ une minute. L'interface s'ouvre ensuite
   sur http://localhost:5000 (identifiants : ceux du fichier `.env`).
4. Clique sur **Démarrer** dans l'interface. Le bot tourne tant que la fenêtre noire reste ouverte.

En local, les offres (`jobbot.db`) et la config (`config.json`) sont conservées d'une fois
sur l'autre, et l'interface n'est accessible que depuis ton PC.

## Candidatures par Gmail (brouillons, suivi, relances)

Pour chaque offre validée, le bot prépare la candidature, mais **c'est toi qui envoies** :

1. **Brouillon Gmail** : bouton « Créer le brouillon Gmail ». Le brouillon contient ton CV,
   la lettre de motivation en PDF (en-tête, date, objet) et un court message. Le destinataire
   est pré-rempli quand l'offre contient l'email du recruteur ; sinon tu le complètes dans Gmail.
2. **Suivi automatique** à chaque session du bot (ou bouton « Vérifier Gmail ») :
   - brouillon envoyé → statut « Envoyée » ;
   - email reçu de l'adresse du recruteur → « Réponse reçue » ;
   - pas de réponse après N jours (5, 7, 10 ou 14) → brouillon de relance, dans le même fil.
3. Statuts modifiables à la main : Entretien, Refus, Offre…

Pour les offres sans email (formulaire en ligne) : « Postuler sur le site » copie la LM et
ouvre l'offre, et « PDF » télécharge la lettre à joindre.

### Configuration (une seule fois)

1. Active la validation en 2 étapes de ton compte Google, puis crée un
   **mot de passe d'application** : https://myaccount.google.com/apppasswords
2. Dans `.env` : `GMAIL_ADDRESS=...` et `GMAIL_APP_PASSWORD=...` (16 lettres), puis relance le bot.
3. Onglet Config : nom, téléphone, **CV en PDF**, délai de relance, texte du mail.
   Le bouton « Tester la connexion Gmail » vérifie que tout est prêt.

Le bot n'utilise Gmail que pour créer des brouillons et lire les en-têtes nécessaires au suivi :
il n'envoie jamais rien lui-même.

## Activer France Travail (gratuit, 10 min)

1. Crée un compte sur https://francetravail.io (espace « Développeur »).
2. Crée une application et abonne-la à l'API **« Offres d'emploi v2 »**.
3. Dans le fichier `.env` (en local) ou dans Railway → Variables, ajoute :
   - `FT_CLIENT_ID` = l'identifiant client
   - `FT_CLIENT_SECRET` = la clé secrète
4. Optionnel : `"ft_departement": "75"` dans la config (ex. `"92"` pour les Hauts-de-Seine).

Sans ces clés, la source est simplement ignorée (message dans les logs).

## Déploiement Railway

1. Pousse ce dossier sur un repo GitHub (`app.py`, `scraper.py`, `scorer.py`,
   `lm_generator.py`, `database.py`, `requirements.txt`, `Procfile`, `railway.toml`, `templates/`).
2. railway.app → New Project → Deploy from GitHub repo.
3. Variables : `ANTHROPIC_API_KEY`, `BOT_USERNAME`, `BOT_PASSWORD`, `SECRET_KEY`
   (et `FT_CLIENT_ID` / `FT_CLIENT_SECRET`).
4. Settings → Domains → Generate Domain.

> Si tu as défini la variable `BOT_CONFIG` sur Railway, mets à jour sa section `sites`
> (`linkedin`, `efinancial`, `hellowork`, `francetravail`), sinon les nouvelles sources
> resteront désactivées. Le plus simple : supprime `BOT_CONFIG` et règle tout depuis l'onglet Config.

## Limite connue

Sur Railway, la base SQLite (`/tmp/jobbot.db`) et `config.json` sont effacés à chaque redéploiement.
