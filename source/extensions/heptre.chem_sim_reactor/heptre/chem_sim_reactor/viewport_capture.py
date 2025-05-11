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

def capture_frame_to_png(frame_path):
    viewport = vp_util.get_active_viewport()
    if not viewport:
        carb.log_error("❌ No active viewport for screenshot.")
        return

    try:
        omni.kit.viewport.window.screenshot.capture_viewport_to_file_async(
            viewport,
            frame_path,
            resolution=None  # or set (width, height) tuple
        )
        carb.log_info(f"📸 Screenshot scheduled to: {frame_path}")
    except Exception as e:
        carb.log_error(f"❌ Failed to capture frame: {e}")

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

def render_usd_frames(usd_path, frame_dir, start=0, end=60, duration=0.1):
    ctx = omni.usd.get_context()
    ctx.open_stage(usd_path)
    stage = ctx.get_stage()  # ✅ this was missing
    add_default_light()
    set_lighting_grey_studio()
    cam_path = ensure_camera(stage)

    bind_camera_to_viewport(cam_path)

    timeline = omni.timeline.get_timeline_interface()
    timeline.stop()
    timeline.set_looping(False)
    timeline.set_current_time(start)
    timeline.play()

    os.makedirs(frame_dir, exist_ok=True)

    for frame in range(start, end + 1):
        timeline.set_current_time(frame)
        frame_path = os.path.join(frame_dir, f"frame_{frame:04d}.png")
        capture_frame_to_png(frame_path)
        carb.log_info(f"📸 Captured frame {frame}")

    timeline.stop()


def create_gif_from_frames(frame_dir, gif_path, duration=0.1):
    images = []
    files = sorted(f for f in os.listdir(frame_dir) if f.endswith(".png"))
    for fname in files:
        images.append(imageio.imread(os.path.join(frame_dir, fname)))
    imageio.mimsave(gif_path, images, duration=duration)
    carb.log_info(f"✅ GIF saved: {gif_path}")


async def run_capture_and_upload(usd_path, frames_dir, gif_path, folder, summary, start=0, end=60, duration=0.1):
    try:
        render_usd_frames(usd_path, frames_dir, start=start, end=end, duration=duration)
        create_gif_from_frames(frames_dir, gif_path, duration=duration)
        success, msg = upload_anim_and_update_db(gif_path, folder, folder, summary)
        if success:
            carb.log_info(f"✅ Uploaded GIF: {msg}")
        else:
            carb.log_error(f"❌ Upload failed: {msg}")
    except Exception as e:
        carb.log_error(f"❌ Error during render/upload: {e}")
