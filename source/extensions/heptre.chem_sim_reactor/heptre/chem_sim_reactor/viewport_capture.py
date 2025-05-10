import carb
import omni.usd
import omni.kit.viewport.utility as vp_util
import omni.kit.app
import omni.timeline
import imageio
from omni.kit.viewport.utility import get_active_viewport
from PIL import Image
import numpy as np
import os

def capture_frame_to_png(frame_path):
    vp = vp_util.get_active_viewport()
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
def frame_scene_objects():
    ctx = omni.usd.get_context()
    stage = ctx.get_stage()
    vp = vp_util.get_active_viewport()
    vp.focus_on_selected()

def focus_world():
    ctx = omni.usd.get_context()
    stage = ctx.get_stage()
    if not stage:
        carb.log_warn("⚠️ No stage available.")
        return
    world_prim = stage.GetPrimAtPath("/World")
    ctx.clear_selection()
    ctx.set_selected_prims([world_prim])
    vp_util.get_active_viewport().focus_on_selected()

def render_usd_frames(usd_path, frame_dir, start=0, end=60):
    ctx = get_context()
    ctx.open_stage(usd_path)

    set_lighting_grey_studio()
    focus_world_and_zoom()

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

def create_gif_from_frames(frame_dir, gif_path, duration=0.1):
    images = []
    files = sorted(f for f in os.listdir(frame_dir) if f.endswith(".png"))
    for fname in files:
        images.append(imageio.imread(os.path.join(frame_dir, fname)))
    imageio.mimsave(gif_path, images, duration=duration)
    carb.log_info(f"✅ GIF saved: {gif_path}")