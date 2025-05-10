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


def capture_frame_to_png(frame_path):
    vp = get_active_viewport()
    texture = vp.get_render_target_color_texture()
    buffer = texture.download_to_buffer()
    arr = np.frombuffer(buffer, dtype=np.uint8).reshape((texture.height, texture.width, 4))
    image = Image.fromarray(arr[:, :, :3])
    image.save(frame_path)


def set_lighting_grey_studio():
    carb.log_info("🔆 Setting Grey Studio lighting...")
    carb.settings.get_settings().set(
        "/persistent/exts/omni.kit.viewport.menubar.lighting/environmentPreset", "Grey Studio"
    )


def focus_world():
    ctx = omni.usd.get_context()
    stage = ctx.get_stage()
    if not stage:
        carb.log_warn("⚠️ No stage available.")
        return
    world_prim = stage.GetPrimAtPath("/World")
    if not world_prim or not world_prim.IsValid():
        return
    ctx.set_selected_prims([world_prim])
    vp_util.get_active_viewport().focus_on_selection()


def ensure_camera(stage):
    camera_path = "/World/RenderCam"
    if not stage.GetPrimAtPath(camera_path).IsValid():
        cam = UsdGeom.Camera.Define(stage, camera_path)
        cam.AddTranslateOp().Set(Gf.Vec3f(8.0, 6.0, 8.0))
        cam.AddRotateXYZOp().Set(Gf.Vec3f(-30, 45, 0))
        carb.log_info("📷 RenderCam added to stage.")
    return camera_path

def bind_camera_to_viewport(camera_prim_path):
    try:
        omni.kit.commands.execute(
            "ChangeCameraCommand",
            path=camera_prim_path,
            camera_type="persp"
        )
        carb.log_info(f"🎥 Camera changed to: {camera_prim_path}")
    except Exception as e:
        carb.log_error(f"❌ Failed to bind camera: {e}")

def add_default_light():
    stage = omni.usd.get_context().get_stage()
    light_path = "/World/DefaultLight"
    if not stage.GetPrimAtPath(light_path):
        light = UsdGeom.DistantLight.Define(stage, light_path)
        light.CreateIntensityAttr(5000.0)
        light.CreateColorAttr(Gf.Vec3f(1.0, 1.0, 1.0))
        light.AddTranslateOp().Set(Gf.Vec3f(10.0, 10.0, 10.0))
        carb.log_info("💡 Default distant light added to scene.")

def render_usd_frames(usd_path, frame_dir, start=0, end=60, duration=0.1):
    ctx = omni.usd.get_context()
    ctx.open_stage(usd_path)
    add_default_light()
    set_lighting_grey_studio()
    cam_path = ensure_camera(stage)
    bind_camera_to_viewport(cam_path)
    focus_world()

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
