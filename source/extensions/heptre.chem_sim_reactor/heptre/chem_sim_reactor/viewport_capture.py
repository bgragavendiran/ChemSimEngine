import carb
import omni.usd
import omni.timeline
import omni.kit.commands
import omni.kit.actions.core
from omni.kit.viewport.utility import get_active_viewport
from pxr import UsdGeom, Gf
import time
import os
import shutil
import imageio
import asyncio

def get_context():
    return omni.usd.get_context()

def set_lighting_grey_studio():
    carb.log_info("🔆 Setting Grey Studio lighting...")
    carb.settings.get_settings().set(
        "/persistent/exts/omni.kit.viewport.menubar.lighting/environmentPreset", "Grey Studio"
    )

def setup_camera_and_zoom():
    ctx = get_context()
    stage = ctx.get_stage()
    if not stage:
        carb.log_warn("⚠️ No stage available.")
        return

    camera_path = "/World/ChemSim_Camera"
    if not stage.GetPrimAtPath(camera_path).IsValid():
        camera = UsdGeom.Camera.Define(stage, camera_path)
        xform = UsdGeom.Xformable(camera)
        xform.AddTranslateOp().Set(Gf.Vec3f(21.91, 28.56, 25.47))
        xform.AddRotateXYZOp().Set(Gf.Vec3f(-12.5, 53.0, 42.9))
        carb.log_info("🎥 Camera created and positioned")

        camera.CreateClippingRangeAttr().Set(Gf.Vec2f(0.1, 10000.0))
        camera.CreateFocalLengthAttr().Set(30)
        camera.CreateHorizontalApertureAttr().Set(20.955)
        camera.CreateVerticalApertureAttr().Set(15.2908)

    vp = get_active_viewport()
    if vp:
        vp.set_active_camera(camera_path)
        carb.log_info("🎥 Camera set as active viewport camera")

def capture_viewport_frame(frame_path, done_callback):
    def callback(success: bool, image_path: str):
        if success and os.path.exists(image_path):
            shutil.copyfile(image_path, frame_path)
            carb.log_info(f"📸 Frame saved to {frame_path}")
        else:
            carb.log_error("❌ Screenshot failed.")
        done_callback()

    omni.kit.actions.core.execute_action(
        "omni.kit.menu.edit", "capture_screenshot", callback
    )
from omni.kit.app import get_app

def defer_to_main_thread(func):
    get_app().get_update_event_stream().create_subscription_to_push(lambda e: func())


import carb

def _capture_frame_loop(frames, frame_dir, on_complete):
    if not frames:
        omni.timeline.get_timeline_interface().stop()
        carb.log_info("✅ Playback and frame capture complete.")
        if on_complete:
            defer_to_main_thread(on_complete)
        return

    frame = frames.pop(0)
    timeline = omni.timeline.get_timeline_interface()
    timeline.set_current_time(frame)
    omni.kit.app.get_app().update()

    def after_capture():
        defer_to_main_thread(lambda: _capture_frame_loop(frames, frame_dir, on_complete))

    capture_viewport_frame(os.path.join(frame_dir, f"frame_{frame:04d}.png"), after_capture)


from omni.kit.app import get_app

def safe_render_usd_frames(*args, **kwargs):
    render_usd_frames(*args, **kwargs)


def render_usd_frames(usd_path, frame_dir, start=0, end=60, on_complete=None):
    ctx = omni.usd.get_context()
    ctx.open_stage(usd_path)
    carb.log_info(f"✅ Stage loaded: {usd_path}")

    # ✅ Force camera & lighting now (not deferred)
    set_lighting_grey_studio()
    setup_camera_and_zoom()

    os.makedirs(frame_dir, exist_ok=True)

    timeline = omni.timeline.get_timeline_interface()
    timeline.stop()
    timeline.set_looping(False)
    timeline.set_current_time(start)
    timeline.play()

    frames = list(range(start, end + 1))
    _capture_frame_loop(frames, frame_dir, on_complete)




def create_gif_from_frames(frame_dir, gif_path, duration=0.1):
    pngs = sorted(f for f in os.listdir(frame_dir) if f.endswith(".png"))
    if not pngs:
        carb.log_error("❌ No PNGs captured. Skipping GIF.")
        return

    images = [imageio.imread(os.path.join(frame_dir, f)) for f in pngs]
    imageio.mimsave(gif_path, images, duration=duration)
    carb.log_info(f"✅ GIF created: {gif_path}")
