# reaction_anim_builder.py  – FINAL
# ------------------------------------------------------------------ #
from pathlib import Path
from pxr import Usd, UsdGeom, Sdf, Gf
import carb, itertools, math
LOG = carb.log_info

from pxr import Sdf
import os, pathlib, time

import re

def sanitize_prim_name(txt: str) -> str:
    # Replace any character that’s not A–Z, a–z, 0–9, or underscore with underscore
     return re.sub(r'[^A-Za-z0-9_]', '_', txt)

def _prepare_fresh_layer(path_str: str):
    """
    Properly clean up existing USD layer so we can safely CreateNew without conflict.
    """
    # Step 1: Delete file if exists
    if os.path.isfile(path_str):
        os.remove(path_str)

    # Step 2: Evict from in-memory cache
    old_layer = Sdf.Layer.Find(path_str)
    if old_layer is not None:
        old_layer.TransferContent(Sdf.Layer.CreateAnonymous())  # Detach contents

# ------------------------------------------------------------------ #
def build_reaction_animation(folder: str,
                             *,
                             ring_radius  = 4.0,     # reactant ring
                             react_frames = 24,      # reactant->origin time
                             hold_frames  = 24,      # hold after mix
                             label_height = 0.8):

    folder = Path(folder)
    LOG(f"[anim]  Building reaction animation in ➜ {folder}")

    # ---------- collect USDs ---------------------------------------------
    react_paths = sorted(itertools.chain(folder.glob("[Rr]eactant*.usd"),
                                         folder.glob("[Rr]eactants*.usd")))
    prod_paths  = sorted(itertools.chain(folder.glob("[Pp]roduct*.usd"),
                                         folder.glob("[Pp]roducts*.usd")))
    if not react_paths or not prod_paths:
        raise RuntimeError("Need at least one reactant*.usd and product*.usd")

    # ---------- stage -----------------------------------------------------
    timestamp = int(time.time())
    stage = Usd.Stage.CreateNew(str(folder / f"reaction_anim_{timestamp}.usd"))
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.y)
    UsdGeom.Xform.Define(stage, "/World")

    t0, tmix, tend = 0, react_frames, react_frames + hold_frames
    stage.SetStartTimeCode(t0)
    stage.SetEndTimeCode(tend)

    # ---------- helpers ---------------------------------------------------
    def ring_layout(n, radius):
        inc = 2*math.pi / max(n, 1)
        for i in range(n):
            a = i * inc
            yield Gf.Vec3d(radius*math.cos(a), 0, radius*math.sin(a))

    def ensure_translate(xf: UsdGeom.Xformable):
        for op in xf.GetOrderedXformOps():
            if op.GetOpType() == UsdGeom.XformOp.TypeTranslate:
                return op
        return xf.AddTranslateOp()

    def add_ref(file: Path, stage_path: str, pos: Gf.Vec3d, label: str):
        xf = UsdGeom.Xform.Define(stage, stage_path)
        xf.GetPrim().GetReferences().AddReference(file.as_posix())
        ensure_translate(UsdGeom.Xformable(xf)).Set(pos, t0)

        if hasattr(UsdGeom, "Text"):
            lbl = UsdGeom.Text.Define(stage, Sdf.Path(stage_path + "/Label"))
            lbl.CreateTextAttr(label)
            lbl.CreateDisplayColorAttr([(1, 1, 1)])
            ensure_translate(UsdGeom.Xformable(lbl)).Set(
                (0, label_height, 0), t0)
        return xf

    # ---------- place xforms ----------------------------------------------
    outer_pos   = list(ring_layout(len(react_paths), ring_radius))
    inner_r     = max(1.2, ring_radius*0.4)
    inner_pos   = list(ring_layout(len(prod_paths),  inner_r))

    react_xf = [add_ref(p, f"/World/Reactants/{sanitize_prim_name(p.stem)}", pos, p.stem)
                for p, pos in zip(react_paths, outer_pos)]
    prod_xf  = [add_ref(p, f"/World/Products/{sanitize_prim_name(p.stem)}",  pos, p.stem)
                for p, pos in zip(prod_paths,  inner_pos)]

    # ---------- animate reactants -----------------------------------------
    for xf in react_xf:
        tr = ensure_translate(UsdGeom.Xformable(xf))
        start = Gf.Vec3d(tr.Get(t0))
        tr.Set(start, t0)
        tr.Set(Gf.Vec3d(0, 0, 0), tmix)          # slide to origin
        xf.CreateVisibilityAttr().Set("inherited", t0)
        xf.GetVisibilityAttr()   .Set("invisible",  tmix)

    # ---------- animate products ------------------------------------------
    for xf, final_pos in zip(prod_xf, inner_pos):
        tr = ensure_translate(UsdGeom.Xformable(xf))
        tr.Set(final_pos + Gf.Vec3d(0, -2, 0), t0)  # start below
        tr.Set(final_pos,                      tmix)
        tr.Set(final_pos,                      tend)
        xf.CreateVisibilityAttr().Set("invisible",  t0)
        xf.GetVisibilityAttr()   .Set("inherited",  tmix)

    stage.GetRootLayer().Save()
    usd_path = str(folder / f"reaction_anim_{timestamp}.usd")
    LOG(f"✅  wrote {usd_path}")
    return usd_path


# test ---------------------------------------------------------------------
if __name__ == "__main__":
    build_reaction_animation("./output_usd/Ethanol_Combust_reaction")
