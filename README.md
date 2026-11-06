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

## Activer France Travail (gratuit, 10 min)

1. Crée un compte sur https://francetravail.io (espace « Développeur »).
2. Crée une application et abonne-la à l'API **« Offres d'emploi v2 »**.
3. Dans Railway → Variables, ajoute :
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

La base SQLite (`/tmp/jobbot.db`) et `config.json` sont effacés à chaque redéploiement.
