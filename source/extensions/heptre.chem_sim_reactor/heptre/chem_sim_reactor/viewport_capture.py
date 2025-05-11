import carb
import omni.usd
import omni.kit.commands
import omni.kit.viewport.utility as vp_util
import omni.kit.app
import omni.timeline
import imageio
from omni.kit.viewport.utility import get_active_viewport
from PIL import Image
import numpy as np
import os
from .firebase_utils import upload_anim_and_update_db
from pxr import UsdGeom, UsdLux, Gf
from omni.kit.widget.viewport.capture import FileCapture
import asyncio



def set_lighting_grey_studio():
    carb.log_info("🔆 Setting Grey Studio lighting...")
    carb.settings.get_settings().set(
        "/persistent/exts/omni.kit.viewport.menubar.lighting/environmentPreset", "Grey Studio"
    )


def ensure_camera(stage):
    camera_path = "/World/RenderCam"
    if not stage.GetPrimAtPath(camera_path).IsValid():
        cam = UsdGeom.Camera.Define(stage, camera_path)
        cam.AddTranslateOp().Set(Gf.Vec3f((61.50000091642141, 59.10000088065863, 56.300000838935375)))
        cam.AddRotateXYZOp().Set(Gf.Vec3f(-38, 46.400001525878906, -3.5))
        carb.log_info("📷 RenderCam added to stage.")
    return camera_path

def bind_camera_to_viewport(camera_prim_path):
    viewport = vp_util.get_active_viewport()
    if not viewport:
        carb.log_error("❌ No active viewport.")
        return

    try:
        viewport.camera_path = camera_prim_path
        carb.log_info(f"📷 Bound viewport to camera: {camera_prim_path}")
    except Exception as e:
        carb.log_error(f"❌ Failed to set viewport camera: {e}")

def add_default_light():
    stage = omni.usd.get_context().get_stage()
    light_path = "/World/DefaultLight"
    if not stage.GetPrimAtPath(light_path):
        light = UsdLux.DistantLight.Define(stage, light_path)
        light.CreateIntensityAttr(5000.0)
        light.CreateColorAttr(Gf.Vec3f(1.0, 1.0, 1.0))
        light.AddTranslateOp().Set(Gf.Vec3f(10.0, 10.0, 10.0))
        carb.log_info("💡 Default distant light added to scene.")


def set_grey_studio_light_rig():
    carb.log_info("🔆 Setting Grey Studio Light Rig...")

    stage = omni.usd.get_context().get_stage()

    # Clear old lights
    for light_path in ["/World/KeyLight", "/World/FillLight", "/World/RimLight", "/World/DomeLight"]:
        if stage.GetPrimAtPath(light_path).IsValid():
            stage.RemovePrim(light_path)

    # Dome Light (ambient light)
    dome_light = UsdLux.DomeLight.Define(stage, "/World/DomeLight")
    dome_light.CreateIntensityAttr(300.0)
    dome_light.CreateColorAttr(Gf.Vec3f(1.0, 1.0, 1.0))
    dome_light.CreateTextureFileAttr("")  # No HDR texture (pure ambient)

    # Key Light (big softbox)
    key_light = UsdLux.RectLight.Define(stage, "/World/KeyLight")
    key_light.CreateIntensityAttr(5000.0)
    key_light.CreateWidthAttr(5.0)
    key_light.CreateHeightAttr(5.0)
    key_light.AddTranslateOp().Set(Gf.Vec3f(5, 5, 5))
    key_light.AddRotateXYZOp().Set(Gf.Vec3f(-45, 45, 0))

    # Fill Light (weaker softbox)
    fill_light = UsdLux.RectLight.Define(stage, "/World/FillLight")
    fill_light.CreateIntensityAttr(2000.0)
    fill_light.CreateWidthAttr(4.0)
    fill_light.CreateHeightAttr(4.0)
    fill_light.AddTranslateOp().Set(Gf.Vec3f(-5, 4, 4))
    fill_light.AddRotateXYZOp().Set(Gf.Vec3f(-30, -45, 0))

    # Rim Light (backlight)
    rim_light = UsdLux.RectLight.Define(stage, "/World/RimLight")
    rim_light.CreateIntensityAttr(3000.0)
    rim_light.CreateWidthAttr(3.0)
    rim_light.CreateHeightAttr(3.0)
    rim_light.AddTranslateOp().Set(Gf.Vec3f(0, 6, -5))
    rim_light.AddRotateXYZOp().Set(Gf.Vec3f(-90, 0, 0))

    carb.log_info("💡 Grey Studio Light Rig setup complete.")

async def render_usd_frames(usd_path, start=0, end=60, duration=0.1):
    ctx = omni.usd.get_context()
    ctx.open_stage(usd_path)
    stage = ctx.get_stage()  # ✅ this was missing
    add_default_light()
    # set_lighting_grey_studio()
    set_grey_studio_light_rig()

    cam_path = ensure_camera(stage)

    bind_camera_to_viewport(cam_path)

    timeline = omni.timeline.get_timeline_interface()
    timeline.stop()
    timeline.set_looping(False)
    timeline.set_current_time(start)
    timeline.play()
    for frame in range(start, end + 1):
        timeline.set_current_time(frame)
        carb.log_info(f"✅Ran Frame {frame} ")
    timeline.stop()



async def run_capture_and_upload(usd_path,folder, summary, start=0, end=60, duration=0.1):
    try:
        await render_usd_frames(usd_path, start=start, end=end, duration=duration)
    except Exception as e:
        carb.log_error(f"❌ Error during render/upload: {e}")
