import os
import json
import anthropic


def score_offer(offer: dict, config: dict) -> dict:
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    prompt = f"""Tu es un expert en recrutement finance/conseil. Note cette offre pour ce candidat.

PROFIL DU CANDIDAT :
{config.get('profil_summary', '')}
Poste recherche : {config.get('label', 'Finance')}
Localisation : Paris / Ile-de-France
Salaire minimum : {config.get('salaire_min', 0)} euros

OFFRE :
Titre : {offer.get('title')}
Entreprise : {offer.get('company')}
Lieu : {offer.get('location', 'N/A')}
Salaire : {offer.get('salary', 'Non precise')}
Description : {offer.get('description', 'Non disponible')[:800]}

REGLES DE NOTATION :
- Note de 1 a 10
- Sois GENEREUX si le titre correspond meme partiellement au profil
- Un titre pertinent sans description vaut au moins 6
- Penalise seulement si le poste est clairement hors sujet (marketing, IT pur, RH...)
- Ne penalise pas l absence de description
- Salaire non precise = ne penalise pas

Reponds UNIQUEMENT avec un objet JSON valide sans texte avant ni apres :
{{"score": 7, "analysis": "explication courte en francais", "highlights": ["point 1", "point 2"]}}"""

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}]
    )

    text = response.content[0].text.strip()
    text = text.replace("```json", "").replace("```", "").strip()

    try:
        return json.loads(text)
    except Exception:
        return {"score": 6, "analysis": text[:200], "highlights": []}
