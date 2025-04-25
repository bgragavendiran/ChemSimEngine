from pxr import Usd, UsdGeom, Gf, UsdShade, Sdf
from .Molecular import MolecularStructure, Atom, Bond
from .reaction_anim_builder import build_reaction_animation

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
        Sdf.Layer.RemoveFromCache(old_layer)     # ← correct call

    # 2) delete any old file on disk (optional but keeps things tidy)
    if os.path.isfile(path_str):
        os.remove(path_str)
# ---------- utility -------------------------------------------------------
def sanitize_prim_name(txt):
    for ch in ' /\\:*?"<>|':
        txt = txt.replace(ch, '_')
    return txt

def get_color_rgb(elem):
    palette = {"H":(1,1,1),"C":(.1,.1,.1),"O":(1,0,0),"N":(0,0,1)}
    return palette.get(elem, (.5,.5,.5))

# ---------- materials -----------------------------------------------------
def create_material(stage, element):
    rgb = get_color_rgb(element)
    root = f"/World/Materials/{sanitize_prim_name(element)}"
    mat  = UsdShade.Material.Define(stage, root)
    sh   = UsdShade.Shader.Define(stage, root+"/Shader")
    sh.CreateIdAttr("UsdPreviewSurface")
    sh.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*rgb))
    mat.CreateSurfaceOutput().ConnectToSource(sh.ConnectableAPI(), "surface")
    return mat

# ---------- atoms ---------------------------------------------------------
def add_atom(stage, atom, parent):
    prim = UsdGeom.Sphere.Define(stage, f"{parent}/{atom.id}")
    prim.GetRadiusAttr().Set(ATOM_RADIUS)
    UsdGeom.Xformable(prim).AddTranslateOp().Set(Gf.Vec3f(*atom.position))
    mat = create_material(stage, atom.element)
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
    nbr = defaultdict(list)
    for b in bonds:
        nbr[b.from_atom].append(b.to_atom)
        nbr[b.to_atom].append(b.from_atom)

    dirs = [(1,0,0),(-1,0,0),(0,1,0),(0,-1,0),(0,0,1),(0,0,-1)]
    pos  = {atoms[0].id:(0.,0.,0.)}
    q    = deque([atoms[0].id])

    while q:
        cur = q.popleft()
        base= Gf.Vec3d(*pos[cur])
        free = iter(itertools.cycle(dirs))
        for n in nbr[cur]:
            if n in pos: continue
            while True:
                d = next(free)
                cand = tuple(base+bond_len*Gf.Vec3d(*d))
                if cand not in pos.values():
                    pos[n]=cand; q.append(n); break
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
    root = f"/World/{sanitize_prim_name(mol.name)}"
    UsdGeom.Xform.Define(st, root)

    # positions, atoms, bonds  … (everything below is unchanged)
    pos = auto_layout(mol.atoms, mol.bonds)
    for a in mol.atoms:
        a.position = pos[a.id]
        add_atom(st, a, root)
    for i, b in enumerate(mol.bonds):
        add_bond(st, pos[b.from_atom], pos[b.to_atom], i, root)

    st.GetRootLayer().Save()
    carb.log_info(f"✔  {path}")

def write_usd_from_reaction(js, out_dir="output", source_file_name="reaction.json"):
    folder=os.path.join(out_dir,os.path.splitext(source_file_name)[0]); os.makedirs(folder,exist_ok=True)
    for role in ("reactants","products"):
        for m in js.get(role,[]):
            mol=MolecularStructure(m.get("name",role),
                                   [Atom(**a) for a in m["atoms"]],
                                   [Bond(**b) for b in m["bonds"]])
            generate_usd_file(mol, os.path.join(folder,f"{role}_{sanitize_prim_name(mol.name)}.usd"))
    carb.log_info("🎉  all done")
    carb.log_info(f"🎉 All USDs written to {folder}")
    # -------------------------------------------------------------
    # 🔄  Generate the combined reaction animation in that folder
    # -------------------------------------------------------------
    try:
        build_reaction_animation(
            folder=str(folder),          # where the USDs are
            ring_radius=5.0,             # tweak as desired
            react_frames=24,
            hold_frames=24
        )
        carb.log_info("🎬 reaction_anim.usd built successfully")
    except Exception as e:
        carb.log_warn(f"⚠️  Could not build reaction animation: {e}")
