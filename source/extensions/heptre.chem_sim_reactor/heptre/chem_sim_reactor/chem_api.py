from fastapi import FastAPI, Request
from pydantic import BaseModel
import openai
import json
import logging
import os
import re
from .Molecular import Atom, Bond, MolecularStructure
import hashlib
# Load environment variables
from dotenv import load_dotenv
from .firebase_utils import get_firebase_reactions_ref, get_firebase_compounds_ref
from .firebase_utils import start_background_sync

dotenv_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(dotenv_path)

# Initialize Firebase
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
cred_path = os.path.join(BASE_DIR, "firebase-adminsdk.json")

firebase_reactions = get_firebase_reactions_ref()
firebase_compounds = get_firebase_compounds_ref()

# Initialize FastAPI
app = FastAPI()
start_background_sync()
openai.api_key = os.getenv("OPENAI_API_KEY")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("uvicorn")

# Request schema
class ReactionRequest(BaseModel):
    reaction_name: str

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
    # Step 1: Check if the prompt is already cached
    reaction_id = generate_reaction_id(prompt)
    existing = firebase_reactions.child(reaction_id).get()
    if existing:
        logger.info(f"Reaction already in Firebase: {reaction_id}")
        return existing

    # Step 2: Compose GPT prompt
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
    # Save raw content immediately for debugging
    raw_output_dir = os.path.join(BASE_DIR, "output_raw")
    os.makedirs(raw_output_dir, exist_ok=True)
    raw_output_path = os.path.join(raw_output_dir, f"{prompt.replace(' ', '_')}_raw.txt")
    with open(raw_output_path, "w", encoding="utf-8") as f:
        f.write(content)

    # Strip markdown formatting if present
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\\n?|```$", "", content.strip(), flags=re.IGNORECASE | re.MULTILINE).strip()

    try:
        parsed = json.loads(content.replace("```json",""))
    except json.JSONDecodeError as e:
        raise ValueError(f"GPT JSON parse failed: {e}\nContent:\n{content}")

    # Step 3: Cache all compounds
    reactants, products = [], []
    reactant_names, product_names = [], []

    for compound in parsed["reactants"]:
        name = compound["name"]
        firebase_compounds.child(name).set(compound)
        reactant_names.append(name)
        reactants.append(compound)

    for compound in parsed["products"]:
        name = compound["name"]
        firebase_compounds.child(name).set(compound)
        product_names.append(name)
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


# Parser Helper
def parse_molecular_structure(data):
    atoms = [Atom(
        id=a["id"],
        element=a["element"],
        color=a.get("color", "#808080")
    ) for a in data["atoms"]]

    bonds = [Bond(from_atom=b["from_atom"], to_atom=b["to_atom"]) for b in data["bonds"]]

    return MolecularStructure(
        name=data["name"],
        atoms=atoms,
        bonds=bonds,
        formula=data.get("formula", ""),
        description=data.get("description", "")
    )


# Main Reaction Endpoint
@app.post("/get-reaction")
async def get_reaction(request: ReactionRequest):
    return query_gpt_and_store_if_missing(request.reaction_name)

# GET version (Optional)
@app.get("/get-reaction/{reaction_name}")
async def get_stored_reaction(reaction_name: str):
    reaction_id = generate_reaction_id(reaction_name)
    reaction_snapshot = firebase_reactions.child(reaction_id).get()
    if not reaction_snapshot:
        return {"error": "Reaction not found."}

    reactants = [firebase_compounds.child(name).get() for name in reaction_snapshot["reactants"]]
    products = [firebase_compounds.child(name).get() for name in reaction_snapshot["products"]]

    return {"reaction": {"reactants": reactants, "products": products}}

def get_molecule_structure(prompt: str):
    result = query_gpt_and_store_if_missing(prompt)
    return result

# Run test call if needed
if __name__ == "__main__":
    print(query_gpt_and_store_if_missing("Ethanol Combustion Reaction"))