from pxr import Usd, UsdGeom, Gf, UsdShade, Sdf
from .Molecular import MolecularStructure, Atom, Bond, ELEMENT_COLORS
import math
import os
import carb

# Utility to sanitize prim names for USD compatibility
def sanitize_prim_name(name: str) -> str:
    invalid = [' ', '/', '\\', ':', '*', '?', '"', '<', '>', '|']
    for ch in invalid:
        name = name.replace(ch, '_')
    return name

# Lookup table for element colors
def get_color_rgb(element: str):
    COLORS = {
        "white": (1,1,1), "red": (1,0,0), "blue": (0,0,1),
        "green": (0,1,0), "yellow": (1,1,0), "pink": (1,0.4,0.7),
        "purple": (0.5,0,0.5), "gray": (0.5,0.5,0.5),
        "lime": (0.2,1,0.2), "orange": (1,0.5,0), "brown": (0.6,0.3,0.1)
    }
    return COLORS.get(element, (0.5,0.5,0.5))

# Create a PBR material under /World/Materials
def create_material(stage, element: str, color: tuple) -> UsdShade.Material:
    mat_path = f"/World/Materials/{sanitize_prim_name(element)}"
    mat = UsdShade.Material.Define(stage, Sdf.Path(mat_path))
    shdr = UsdShade.Shader.Define(stage, Sdf.Path(f"{mat_path}/Shader"))
    shdr.CreateIdAttr("UsdPreviewSurface")  # Standard preview shader
    shdr.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*color))
    mat.CreateSurfaceOutput().ConnectToSource(shdr.ConnectableAPI(), "surface")
    carb.log_info(f"✅ Material created: {element}")
    return mat

# Create an atom as a Sphere and bind its material
def create_sphere(stage, atom: Atom, color: tuple, parent: str):
    path = f"{parent}/{atom.id}"
    carb.log_info(f"🛠 Defining Sphere at {path}")
    sphere = UsdGeom.Sphere.Define(stage, path)
    if not sphere.GetPrim().IsValid():
        raise RuntimeError(f"Invalid sphere prim: {path}")
    sphere.GetRadiusAttr().Set(0.2)
    UsdGeom.Xformable(sphere).AddTranslateOp().Set(Gf.Vec3f(*atom.position))

    mat = create_material(stage, atom.element, color)
    UsdShade.MaterialBindingAPI(sphere.GetPrim()).Bind(mat)
    carb.log_info(f"✅ Sphere {atom.id} created and material bound")
    stage.GetRootLayer().Save()

# Create a bond as a Capsule with correct orientation
def create_cylinder(stage, start: list, end: list, index: int, parent: str):
    xform_path = f"{parent}/bond_{index}"
    carb.log_info(f"🛠 Defining Capsule at {xform_path}/capsule")

    # Define Xform and Capsule prims
    xform = UsdGeom.Xform.Define(stage, xform_path)
    cap   = UsdGeom.Capsule.Define(stage, f"{xform_path}/capsule")
    if not cap.GetPrim().IsValid() or not xform.GetPrim().IsValid():
        raise RuntimeError(f"Invalid bond prim at {xform_path}")

    # Ensure capsule's internal axis is Z
    axis_attr = cap.CreateAxisAttr()
    axis_attr.Set('Z')  # USD capsules default to Z-axis

    # Compute geometry parameters
    length = math.dist(start, end)
    cap.CreateHeightAttr(length)
    cap.CreateRadiusAttr(0.05)

    # Compute midpoint
    sv  = Gf.Vec3d(*start)
    ev  = Gf.Vec3d(*end)
    mid = (sv + ev) * 0.5

    # Compute direction vector
    dir_vec = (ev - sv).GetNormalized()
    default_axis = Gf.Vec3d(0, 0, 1)  # Z-axis

    # Compute rotation axis and angle
    axis  = Gf.Cross(default_axis, dir_vec)
    # handle parallel case
    if axis.GetLength() < 1e-6:
        axis = Gf.Vec3d(1, 0, 0)  # arbitrary orthogonal axis
    angle = math.degrees(math.acos(max(-1.0, min(1.0, Gf.Dot(default_axis, dir_vec)))))

    # Build transform matrix (rotation then translate)
    rot = Gf.Rotation(axis, angle)
    mtx = Gf.Matrix4d()
    mtx.SetRotate(rot)
    mtx.SetTranslate(mid)

    # Apply the transform in one operation
    op = xform.AddTransformOp()
    op.Set(mtx)

    carb.log_info(f"✅ Bond {index} created")
    stage.GetRootLayer().Save()

# Generate USD for a single molecule
def generate_usd_file(mol: MolecularStructure, out_path="output.usda"):
    carb.log_info(f"🛠 Generating USD: {out_path}")
    stage = Usd.Stage.CreateNew(out_path)
    if not stage:
        raise RuntimeError("Cannot create USD stage")

    # Setup stage metadata
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.y)
    stage.SetMetadata("metersPerUnit", 1.0)

    # Root scopes
    UsdGeom.Xform.Define(stage, "/World")
    UsdGeom.Xform.Define(stage, "/World/Materials")

    # Molecule scope
    mol_path = f"/World/{sanitize_prim_name(mol.name)}"
    UsdGeom.Xform.Define(stage, mol_path)

    # Atom creation
    cmap = mol.get_element_color_map()
    lookup = {atom.id: atom for atom in mol.atoms}
    for atom in mol.atoms:
        color = get_color_rgb(cmap.get(atom.element, "gray"))
        create_sphere(stage, atom, color, mol_path)

    # Bond creation
    for i, bond in enumerate(mol.bonds):
        if bond.from_atom not in lookup or bond.to_atom not in lookup:
            carb.log_warn(f"⚠️ Skipping unknown bond {bond.from_atom}->{bond.to_atom}")
            continue
        s = lookup[bond.from_atom].position
        e = lookup[bond.to_atom].position
        create_cylinder(stage, s, e, i, mol_path)

    stage.GetRootLayer().Save()
    carb.log_info(f"🎉 USD saved: {out_path}")

# Generate USDs from a reaction JSON
def write_usd_from_reaction(json_data, out_dir="output_usd", source_file_name="reaction.json"):
    base = os.path.splitext(source_file_name)[0]
    folder = os.path.join(out_dir, base)
    os.makedirs(folder, exist_ok=True)

    molecules = []
    for role in ("reactants", "products"):
        for m in json_data.get(role, []):
            atoms = [Atom(**a) for a in m.get("atoms", [])]
            bonds = [Bond(**b) for b in m.get("bonds", [])]
            molecules.append((m.get("name", role), atoms, bonds, role))

    for name, atoms, bonds, role in molecules:
        mol = MolecularStructure(name=name, atoms=atoms, bonds=bonds)
        filename = f"{role}_{sanitize_prim_name(name)}.usd"
        generate_usd_file(mol, os.path.join(folder, filename))

    carb.log_info(f"🎉 All USDs written to {folder}")
