from fastapi import FastAPI, Request
from pydantic import BaseModel
import json
import logging
import os
import re
from .Molecular import Atom, Bond, MolecularStructure
import hashlib
# Load environment variables
from dotenv import load_dotenv
from .firebase_utils import get_firebase_reactions_ref, get_firebase_compounds_ref

from .gpt_utils import query_gpt_and_store_if_missing

dotenv_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(dotenv_path)

# Initialize Firebase
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
cred_path = os.path.join(BASE_DIR, "firebase-adminsdk.json")

firebase_reactions = get_firebase_reactions_ref()
firebase_compounds = get_firebase_compounds_ref()

# Initialize FastAPI
app = FastAPI()


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("uvicorn")

# Request schema
class ReactionRequest(BaseModel):
    reaction_name: str

def generate_reaction_id(prompt: str) -> str:
    return hashlib.sha256(prompt.encode()).hexdigest()[:16]


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
