from fastapi import FastAPI, Request
from pydantic import BaseModel
import openai
import json
import logging
import os
import re
from .Molecular import Atom, Bond, MolecularStructure

import firebase_admin
from firebase_admin import credentials, db
import hashlib
# Load environment variables
from dotenv import load_dotenv

dotenv_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(dotenv_path)

# Initialize Firebase
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
cred_path = os.path.join(BASE_DIR, "firebase-adminsdk.json")

if not firebase_admin._apps:
    cred = credentials.Certificate(cred_path)
    firebase_admin.initialize_app(cred, {
        'databaseURL': "https://vrchemlab-d3f91-default-rtdb.asia-southeast1.firebasedatabase.app/"
    })

firebase_compounds = db.reference("compounds")
firebase_reactions = db.reference("reactions")

# Initialize FastAPI
app = FastAPI()
openai.api_key = os.getenv("OPENAI_API_KEY")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("uvicorn")

# Request schema
class ReactionRequest(BaseModel):
    reaction_name: str

LLM_STRUCTURE_GUIDE = """
You are a chemistry simulation assistant for a 3D simulation engine. Your responses are parsed by an automated parser, so you must respond ONLY in **VALID JSON**, with NO explanation, NO markdown, and NO code blocks.

❗ DO NOT return only names like ["Ethanol"]. ❗
You MUST return the **full molecular structure**, in this exact format:

{
  "reactants": [MolecularStructure],
  "products": [MolecularStructure]
}

Each MolecularStructure is a dictionary:
{
  "name": "MoleculeName",
  "atoms": [
    { "id": "a1", "element": "C", "position": [0.0, 0.0, 0.0] },
    ...
  ],
  "bonds": [
    { "from_atom": "a1", "to_atom": "a2" },
    ...
  ]
}

✅ Example Output:

{
  "reactants": [
    {
      "name": "Ethanol",
      "atoms": [
        { "id": "a1", "element": "C", "position": [0.0, 0.0, 0.0] },
        { "id": "a2", "element": "O", "position": [0.2, 0.1, 0.0] }
      ],
      "bonds": [
        { "from_atom": "a1", "to_atom": "a2" }
      ]
    }
  ],
  "products": [
    {
      "name": "Acetaldehyde",
      "atoms": [
        { "id": "p1", "element": "C", "position": [1.0, 0.0, 0.0] },
        { "id": "p2", "element": "O", "position": [1.2, 0.1, 0.0] }
      ],
      "bonds": [
        { "from_atom": "p1", "to_atom": "p2" }
      ]
    }
  ]
}

Respond only with the JSON content as above.
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
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "You are a chemistry modeling assistant."},
            {"role": "user", "content": full_prompt}
        ],
        max_tokens=3500,
        temperature=1
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
        "reactants": reactant_names,
        "products": product_names
    })

    return {
        "reaction_id": reaction_id,
        "reactants": reactants,
        "products": products
    }

# Parser Helper
def parse_molecular_structure(data):
    atoms = [Atom(id=a["id"], element=a["element"], position=tuple(a["position"])) for a in data["atoms"]]
    bonds = [Bond(from_atom=b["from_atom"], to_atom=b["to_atom"]) for b in data["bonds"]]
    return MolecularStructure(name=data["name"], atoms=atoms, bonds=bonds)

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