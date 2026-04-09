import os
import json
import anthropic


def score_offer(offer: dict, config: dict) -> dict:
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    prompt = f"""Tu es un expert en recrutement finance. Analyse cette offre par rapport au profil candidat.

PROFIL :
- Poste recherché : {config.get('poste_cible')}
- Expérience : {config.get('profil_summary')}
- Localisation : {config.get('localisation')}
- Salaire min : {config.get('salaire_min', 0)}€

OFFRE :
Titre : {offer.get('title')}
Entreprise : {offer.get('company')}
Lieu : {offer.get('location', 'N/A')}
Salaire : {offer.get('salary', 'N/A')}
Description : {offer.get('description', 'N/A')[:800]}

Réponds UNIQUEMENT en JSON valide sans markdown :
{{"score": <1-10>, "analysis": "<2-3 phrases en français>", "highlights": ["<point 1>", "<point 2>"]}}"""

    response = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}]
    )

    text = response.content[0].text.strip()
    return json.loads(text)
