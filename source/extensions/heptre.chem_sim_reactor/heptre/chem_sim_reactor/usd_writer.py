from pxr import Usd, UsdGeom, Gf, UsdShade, Sdf
from .Molecular import MolecularStructure, Atom, Bond
from .reaction_anim_builder import build_reaction_animation
import re
import os, math, carb, itertools
from collections import deque, defaultdict

# ---------- constants -----------------------------------------------------
ATOM_RADIUS = 0.20
BOND_RADIUS = 0.05
from pxr import Sdf
import os, pathlib

def _prepare_fresh_layer(path_str: str):
    """
    Ensure `Usd.Stage.CreateNew(path_str)` can succeed even when the same
    file was written earlier in this session.
    """
    # 1) evict from the in-memory layer cache, if present
    old_layer = Sdf.Layer.Find(path_str)
    if old_layer is not None:
        # Sdf.Layer.RemoveFromCache(old_layer)     # ← correct call
        pass

    # 2) delete any old file on disk (optional but keeps things tidy)
    if os.path.isfile(path_str):
        os.remove(path_str)
# ---------- utility -------------------------------------------------------
def sanitize_prim_name(txt: str) -> str:
    # Replace any character that’s not A–Z, a–z, 0–9, or underscore with underscore
    return re.sub(r'[^A-Za-z0-9_]', '_', txt)

def get_color_rgb(elem):
    palette = {"H":(1,1,1),"C":(.1,.1,.1),"O":(1,0,0),"N":(0,0,1)}
    return palette.get(elem, (.5,.5,.5))

# ---------- materials -----------------------------------------------------
def create_material(stage, atom):
    hex_color = getattr(atom, "color", "#888888")
    hex_color = hex_color.lstrip("#")
    r, g, b = [int(hex_color[i:i+2], 16) / 255.0 for i in (0, 2, 4)]

    root = f"/World/Materials/{sanitize_prim_name(atom.element)}"
    mat  = UsdShade.Material.Define(stage, root)
    sh   = UsdShade.Shader.Define(stage, root + "/Shader")
    sh.CreateIdAttr("UsdPreviewSurface")
    sh.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(r, g, b))
    mat.CreateSurfaceOutput().ConnectToSource(sh.ConnectableAPI(), "surface")
    return mat


# ---------- atoms ---------------------------------------------------------
def add_atom(stage, atom, parent, position):
    element = atom.element
    index = ''.join(filter(str.isdigit, atom.id)) or "0"
    prim_name = f"{element}_{index}"
    prim = UsdGeom.Sphere.Define(stage, f"{parent}/{sanitize_prim_name(prim_name)}")
    prim.GetRadiusAttr().Set(ATOM_RADIUS)
    UsdGeom.Xformable(prim).AddTranslateOp().Set(Gf.Vec3f(*position))
    mat = create_material(stage, atom)
    UsdShade.MaterialBindingAPI(prim.GetPrim()).Bind(mat)



# ---------- bonds ---------------------------------------------------------
# ────────────────────────────────────────────────────────────────────────────
# Bond helper – draw a capsule that really goes from the *surface* of one
# atom-sphere to the *surface* of the other, pointing in any direction.
# Capsule mesh in Omniverse points along +Y, so we rotate +Y → dir_vec.
# ────────────────────────────────────────────────────────────────────────────
# -*-  strictly the bond helper only  -*- ---------------------------------
# ------------------------------------------------------------------------
#  add_bond – capsule from sphere-centre p0 → sphere-centre p1
# ------------------------------------------------------------------------
ATOM_RADIUS = 0.20           # keep in sync with create_sphere()
BOND_RADIUS = 0.05

def add_bond(stage, p0, p1, idx, parent,
             r_sphere = ATOM_RADIUS,
             r_capsule = BOND_RADIUS):

    # ─────────── prims ────────────────────────────────────────────────
    xform_path = f"{parent}/bond_{idx}"
    xf  = UsdGeom.Xform  .Define(stage, xform_path)
    cap = UsdGeom.Capsule.Define(stage, f"{xform_path}/capsule")

    if not (xf.GetPrim().IsValid() and cap.GetPrim().IsValid()):
        raise RuntimeError(f"Cannot create bond {idx}")

    # ─────────── geometry numbers ─────────────────────────────────────
    p0 = Gf.Vec3d(*p0)
    p1 = Gf.Vec3d(*p1)

    dir_vec      = (p1 - p0).GetNormalized()
    centre_dist  = (p1 - p0).GetLength()
    height       = max(centre_dist - 2*r_sphere, 1e-4)   # trim to surfaces

    # ─────────── choose built-in axis (X / Y / Z) that is closest ─────
    comp_abs = [abs(dir_vec[0]), abs(dir_vec[1]), abs(dir_vec[2])]
    major_idx = comp_abs.index(max(comp_abs))            # 0,1,2

    axis_names  = ["X", "Y", "Z"]
    builtin_axis = axis_names[major_idx]                  # "X"|"Y"|"Z"
    builtin_vecs = {"X": Gf.Vec3d(1,0,0),
                    "Y": Gf.Vec3d(0,1,0),
                    "Z": Gf.Vec3d(0,0,1)}

    cap.CreateAxisAttr(builtin_axis)
    cap.CreateRadiusAttr(r_capsule)
    cap.CreateHeightAttr(height)

    # ─────────── residual rotation (only if needed) ───────────────────
    src_vec = builtin_vecs[builtin_axis]
    rot     = Gf.Rotation()
    if not Gf.IsClose(dir_vec, src_vec, 1e-6):
        rot.SetRotateInto(src_vec, dir_vec)               # tiny diagonal tilt

    # ─────────── place at midpoint ────────────────────────────────────
    mtx = Gf.Matrix4d().SetRotate(rot)
    mtx.SetTranslate((p0 + p1) * 0.5)

    xf.ClearXformOpOrder()
    xf.AddTransformOp().Set(mtx)

    stage.GetRootLayer().Save()
    carb.log_info(f"[bond {idx}] axis={builtin_axis} height={height:.3f}")

# ---------- quick BFS layout ---------------------------------------------
def auto_layout(atoms, bonds, bond_len=1.2):
    carb.log_info("🧠 Running auto_layout...")

    # Step 1: Build neighbor graph
    nbr = defaultdict(list)
    for b in bonds:
        nbr[b.from_atom].append(b.to_atom)
        nbr[b.to_atom].append(b.from_atom)

    # Step 2: Initialize layout
    dirs = [(1,0,0),(-1,0,0),(0,1,0),(0,-1,0),(0,0,1),(0,0,-1)]
    pos  = {atoms[0].id: (0.0, 0.0, 0.0)}
    q    = deque([atoms[0].id])

    carb.log_info(f"📌 Starting layout from atom: {atoms[0].id} at (0,0,0)")

    # Step 3: BFS layout for connected atoms
    while q:
        cur = q.popleft()
        base = Gf.Vec3d(*pos[cur])
        free = iter(itertools.cycle(dirs))

        for n in nbr[cur]:
            if n in pos:
                continue
            while True:
                d = next(free)
                cand = tuple(base + bond_len * Gf.Vec3d(*d))
                if cand not in pos.values():
                    pos[n] = cand
                    q.append(n)
                    carb.log_info(f"➕ Placed atom {n} near {cur} at {cand}")
                    break

    # Step 4: Handle unconnected atoms
    unplaced = [a.id for a in atoms if a.id not in pos]
    if unplaced:
        carb.log_warn(f"⚠️ Unconnected atoms detected: {unplaced}")
        base = Gf.Vec3d(5.0, 0, 0)  # place away from main cluster
        for i, aid in enumerate(unplaced):
            p = tuple(base + Gf.Vec3d(i * 1.5, 0, 0))
            pos[aid] = p
            carb.log_warn(f"📍 Manually placed unconnected atom {aid} at {p}")

    carb.log_info(f"✅ Final layout positions: {pos}")
    return pos


# ---------- USD generation -----------------------------------------------
# ─── USD generation ───────────────────────────────────────────────────────
def generate_usd_file(mol, path):
    # create a new stage
    _prepare_fresh_layer(path)
    st = Usd.Stage.CreateNew(path)
    UsdGeom.SetStageUpAxis(st, UsdGeom.Tokens.y)
    st.SetMetadata("metersPerUnit", 1)

    # /World and /World/Materials
    world = UsdGeom.Xform.Define(st, "/World")
    UsdGeom.Xform.Define(st, "/World/Materials")

    # mark /World as defaultPrim so referenced files open cleanly
    st.SetDefaultPrim(world.GetPrim())

    # molecule scope
    safe_name = sanitize_prim_name(mol.name or "UnnamedCompound")
    if not safe_name:
        safe_name = "UnnamedCompound"
    root = f"/World/{safe_name}"

    if not Sdf.Path(root).IsAbsolutePath() or root == "/World/":
        raise ValueError(f"Invalid prim path: {root}")
    UsdGeom.Xform.Define(st, root)

    # positions, atoms, bonds  … (everything below is unchanged)
    pos = auto_layout(mol.atoms, mol.bonds)
    carb.log_info(f"🧭 Layout positions: {pos}")
    for a in mol.atoms:
        if a.id not in pos:
            carb.log_error(f"❌ Atom {a.id} has no layout position!")
        else:
            carb.log_info(f"📍 Placing atom {a.id} at {pos[a.id]}")
        add_atom(st, a, root, pos[a.id])

    for i, b in enumerate(mol.bonds):
        try:
            p0 = pos[b.from_atom]
            p1 = pos[b.to_atom]
            carb.log_info(f"🔗 Drawing bond {i}: {b.from_atom} → {b.to_atom} at {p0} → {p1}")
            add_bond(st, p0, p1, i, root)
        except KeyError as ke:
            carb.log_error(f"❌ Bond refers to unknown atom ID: {ke}")
            raise

    st.GetRootLayer().Save()
    carb.log_info(f"✔  {path}")

import uuid  # Add to imports if not present
def write_usd_from_reaction(js, out_dir="output", source_file_name="reaction.json"):
    folder = os.path.join(out_dir, os.path.splitext(source_file_name)[0])
    os.makedirs(folder, exist_ok=True)

    for role in ("reactants", "products"):
        for m in js.get(role, []):
            carb.log_info(f"🔍 Processing {role}: {m.get('name', role)}")
            atom_ids = [a["id"] for a in m["atoms"]]
            bond_ids = [(b["from_atom"], b["to_atom"]) for b in m["bonds"]]
            carb.log_info(f"  🔬 Atoms: {atom_ids}")
            carb.log_info(f"  🔗 Bonds: {bond_ids}")

            try:
                mol_name = m.get("name") or f"{role}_{uuid.uuid4().hex[:6]}"
                mol = MolecularStructure(
                    mol_name,
                    [Atom(**a) for a in m["atoms"]],
                    [Bond(**b) for b in m["bonds"]]
                )
            except Exception as e:
                carb.log_error(f"❌ Error creating MolecularStructure: {e}")
                raise

            try:
                generate_usd_file(mol, os.path.join(folder, f"{role}_{sanitize_prim_name(mol.name)}.usd"))
            except Exception as e:
                carb.log_error(f"❌ Failed to generate USD for {mol.name}: {e}")
                raise
        carb.log_info(f"Animation build Starting")
        carb.log_info(f"write_usd_from_reaction called with: {len(js.get('reactants', []))} reactants, {len(js.get('products', []))} products")
        try:
            build_reaction_animation(folder)
        except Exception as e:
            carb.log_error(f"⚠️ Animation build failed: {e}")
