import os
import json
import re
import hashlib
import openai
from dotenv import load_dotenv
from .firebase_utils import get_firebase_reactions_ref, get_firebase_compounds_ref

# Load .env variables
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
dotenv_path = os.path.join(BASE_DIR, ".env")
load_dotenv(dotenv_path)
openai.api_key = os.getenv("OPENAI_API_KEY")

firebase_reactions = get_firebase_reactions_ref()
firebase_compounds = get_firebase_compounds_ref()

LLM_STRUCTURE_GUIDE = """
You are a chemistry simulation assistant for a 3D simulation engine. Your responses are parsed by an automated parser, so you must respond ONLY in **VALID JSON**, with NO explanation, NO markdown, and NO code blocks.
❗️ CRITICAL REQUIREMENTS:
- DO NOT return only molecule names like ["Ethanol"] — full molecular structures are mandatory.
- DO NOT skip atoms or bonds. For example, if the formula is C3H6O, you **must** include 3 carbon, 6 hydrogen, and 1 oxygen atoms in the `atoms` list, and connect them fully via the `bonds` list.
OUTPUT FORMAT (REQUIRED):
{
  "reactants": [MolecularStructure],
  "products": [MolecularStructure],
  "reaction": "Full balanced chemical equation (e.g., CH3COOH + NaOH → CH3COONa + H2O)",
  "reactionDescription": "One-line description of the reaction process"
}
Each MolecularStructure is a dictionary with this format:
{
  "name": "MoleculeName",
  "formula": "C3H6O",
  "description": "Short description of the molecule",
  "atoms": [
    { "id": "a1", "element": "C", "color": "#000000" },
    ...
  ],
  "bonds": [
    { "from_atom": "a1", "to_atom": "a2" },
    ...
  ]
}
ENFORCED RULES:
1. Every atom MUST include:
   - `id` (e.g., "a1", "a2", ...)
   - `element` (e.g., "C", "H", "O")
   - `color` (hex color, e.g., "#000000")
2. Each **unique element** (C, H, O, N, etc.) must use the SAME color code consistently throughout ALL molecules.
   - Suggested: C → "#000000", H → "#FFFFFF", O → "#FF0000", N → "#0000FF", etc.
3. The atoms listed MUST MATCH the chemical formula EXACTLY.
   - C3H6O = 3 Carbon, 6 Hydrogen, 1 Oxygen atoms.
   - You MUST list ALL atoms and connect them appropriately.
4. You MUST include ALL bonds between atoms.
   - No atom should be left floating unless it's a free radical (rare).
   - Validate atom valency: Carbon usually forms 4 bonds, Oxygen 2, Hydrogen 1, Nitrogen 3.
5. Use accurate molecular geometry whenever possible. If unknown, represent all bonds clearly and fully.
6. DO NOT include text before or after the JSON.
EXAMPLE OUTPUT FORMAT (FOR "Ethanol"):
{
  "reactants": [
    {
      "name": "Ethanol",
      "formula": "C2H6O",
      "description": "A two-carbon alcohol molecule.",
      "atoms": [
        { "id": "a1", "element": "C", "color": "#000000" },
        { "id": "a2", "element": "C", "color": "#000000" },
        { "id": "a3", "element": "O", "color": "#FF0000" },
        { "id": "a4", "element": "H", "color": "#FFFFFF" },
        { "id": "a5", "element": "H", "color": "#FFFFFF" },
        { "id": "a6", "element": "H", "color": "#FFFFFF" },
        { "id": "a7", "element": "H", "color": "#FFFFFF" },
        { "id": "a8", "element": "H", "color": "#FFFFFF" },
        { "id": "a9", "element": "H", "color": "#FFFFFF" }
      ],
      "bonds": [
        { "from_atom": "a1", "to_atom": "a2" },
        { "from_atom": "a1", "to_atom": "a4" },
        { "from_atom": "a1", "to_atom": "a5" },
        { "from_atom": "a1", "to_atom": "a6" },
        { "from_atom": "a2", "to_atom": "a3" },
        { "from_atom": "a2", "to_atom": "a7" },
        { "from_atom": "a2", "to_atom": "a8" },
        { "from_atom": "a2", "to_atom": "a9" }
      ]
    }
  ],
  "products": [],
  "reaction": "",
  "reactionDescription": ""
}

Respond only with the JSON content as shown above.
""".strip()


def generate_reaction_id(prompt: str) -> str:
    return hashlib.sha256(prompt.encode()).hexdigest()[:16]

def query_gpt_and_store_if_missing(prompt: str):
    reaction_id = generate_reaction_id(prompt)
    existing = firebase_reactions.child(reaction_id).get()
    if existing:
        return existing

    full_prompt = LLM_STRUCTURE_GUIDE.strip() + "\n\nReaction prompt:\n" + prompt

    response = openai.ChatCompletion.create(
        model="gpt-4-turbo",
        messages=[
            {"role": "system", "content": "You are a chemistry modeling assistant."},
            {"role": "user", "content": full_prompt}
        ],
        max_tokens=3500,
        temperature=0.5
    )

    content = response.choices[0].message.content.strip()

    raw_output_dir = os.path.join(BASE_DIR, "output_raw")
    os.makedirs(raw_output_dir, exist_ok=True)
    raw_output_path = os.path.join(raw_output_dir, f"{prompt.replace(' ', '_')}_raw.txt")
    with open(raw_output_path, "w", encoding="utf-8") as f:
        f.write(content)

    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\\n?|```$", "", content.strip(), flags=re.IGNORECASE | re.MULTILINE).strip()

    try:
        parsed = json.loads(content.replace("```json", ""))
    except json.JSONDecodeError as e:
        raise ValueError(f"GPT JSON parse failed: {e}\nContent:\n{content}")

    reactants, products = [], []

    for compound in parsed["reactants"]:
        name = compound["name"]
        firebase_compounds.child(name).set(compound)
        reactants.append(compound)

    for compound in parsed["products"]:
        name = compound["name"]
        firebase_compounds.child(name).set(compound)
        products.append(compound)

    firebase_reactions.child(reaction_id).set({
        "prompt": prompt,
        "reactants": reactants,
        "products": products,
        "reaction": parsed.get("reaction", ""),
        "reactionDescription": parsed.get("reactionDescription", "")
    })

    return {
        "reaction_id": reaction_id,
        "reactants": reactants,
        "products": products,
        "reaction": parsed.get("reaction", ""),
        "reactionDescription": parsed.get("reactionDescription", "")
    }
