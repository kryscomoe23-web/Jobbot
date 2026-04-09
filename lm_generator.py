import os
import anthropic


def generate_lm(offer: dict, config: dict) -> str:
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    tones = {
        "direct":  "Style direct et factuel. Phrases courtes. Pas de formules creuses.",
        "formal":  "Style formel et structuré. Registre professionnel soutenu.",
        "dynamic": "Style dynamique et engagé. Enthousiasme mesuré.",
    }
    tone = tones.get(config.get("lm_tone", "direct"), tones["direct"])

    template = ""
    if config.get("lm_template"):
        template = f"\nBase-toi sur ce template :\n{config['lm_template']}\n"

    prompt = f"""Tu es expert en LM pour la finance. Rédige une lettre de motivation.

PROFIL : {config.get('profil_summary', '')}
POSTE : {offer.get('title')} chez {offer.get('company')}
DESCRIPTION : {offer.get('description', '')[:600]}

CONSIGNES :
- {tone}
- 3 paragraphes max
- Mentionne spécifiquement l'entreprise et le poste
- Valorise IFCIC/BPI France
- Pas de "Je me permets de vous contacter"
- Termine par une formule sobre
{template}

Écris uniquement la lettre."""

    response = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}]
    )

    return response.content[0].text.strip()
