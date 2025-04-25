from typing import List, Tuple, Dict

class Atom:
    def __init__(self, id: str, element: str, color: str = "#808080"):
        self.id = id              # Unique identifier
        self.element = element    # e.g., "H", "O", "C"
        self.color = color

class Bond:
    def __init__(self, from_atom: str, to_atom: str):
        self.from_atom = from_atom  # Atom ID
        self.to_atom = to_atom      # Atom ID

class MolecularStructure:
    def __init__(
        self,
        name: str,
        atoms: List[Atom],
        bonds: List[Bond],
        formula: str = "",
        description: str = ""
    ):
        self.name = name
        self.atoms = atoms
        self.bonds = bonds
        self.formula = formula  # New
        self.description = description  # New

    def get_element_color_map(self) -> Dict[str, str]:
        return {
            atom.element: atom.color
            for atom in self.atoms
        }
