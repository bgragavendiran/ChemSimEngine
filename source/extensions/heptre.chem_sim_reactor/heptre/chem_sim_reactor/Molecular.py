from typing import List, Tuple, Dict

ELEMENT_COLORS = {
    "H": "white",
    "C": "red",
    "O": "blue",
    "N": "green",
    "Cl": "lime",
    "Na": "purple",
    "K": "orange",
    "S": "yellow",
    "P": "pink",
    "Fe": "brown"
}

class Atom:
    def __init__(self, id: str, element: str, position: Tuple[float, float, float]):
        self.id = id              # Unique identifier
        self.element = element    # e.g., "H", "O", "C"
        self.position = position  # (x, y, z)

class Bond:
    def __init__(self, from_atom: str, to_atom: str):
        self.from_atom = from_atom  # Atom ID
        self.to_atom = to_atom      # Atom ID

class MolecularStructure:
    def __init__(self, name: str, atoms: List[Atom], bonds: List[Bond]):
        self.name = name
        self.atoms = atoms
        self.bonds = bonds

    def get_element_color_map(self) -> Dict[str, str]:
        unique_elements = {atom.element for atom in self.atoms}
        return {
            element: ELEMENT_COLORS.get(element, "gray")  # fallback color
            for element in unique_elements
        }
