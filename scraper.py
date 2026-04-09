import os
import json
import anthropic


def score_offer(offer: dict, config: dict) -> dict:
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    prompt = f"""Tu es un expert en recrutement finance/conseil. Note cette offre pour ce candidat.

PROFIL DU CANDIDAT :
{config.get('profil_summary', '')}
Poste recherché : {config.get('label', 'Finance')}
Localisation : Paris / Île-de-France
Salaire minimum : {config.get('salaire_min', 0)}€

OFFRE :
Titre : {offer.get('title')}
Entreprise : {offer.get('company')}
Lieu : {offer.get('location', 'N/A')}
Salaire : {offer.get('salary', 'Non précisé')}
Description : {offer.get('description', 'Non disponible')[:800]}

RÈGLES DE NOTATION :
- Note de 1 à 10
- Sois GÉNÉREUX si le titre correspond même partiellement au profil
- Un titre pertinent sans description vaut au moins 6
- Pénalise seulement si le poste est clairement hors sujet (marketing, IT pur, RH...)
- Ne pénalise pas l'absence de description
- Salaire non précisé = ne pénalise pas

Réponds UNIQUEMENT avec un objet JSON valide sans texte avant ni après :
{{"score": 7, "analysis": "explication courte en français", "highlights": ["point 1", "point 2"]}}"""

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
