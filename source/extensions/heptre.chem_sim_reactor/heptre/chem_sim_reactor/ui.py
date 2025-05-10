import omni.ui as ui
from pathlib import Path
import os
import json
import carb
from .chem_api import get_molecule_structure
from .usd_writer import write_usd_from_reaction
from pxr import UsdGeom, Sdf
from typing import Dict
from .viewport_capture import render_usd_frames, create_gif_from_frames
from .firebase_utils import upload_anim_and_update_db

import omni.usd
import omni.timeline
import omni.kit.viewport.utility as vp_util
import carb.settings

EXT_DIR = os.path.dirname(os.path.abspath(__file__))

if "_build" in EXT_DIR:
    OUTPUT_ROOT_DIR = EXT_DIR
else:
    OUTPUT_ROOT_DIR = EXT_DIR.replace(
        r"source\extensions",
        r"_build\windows-x86_64\release\exts"
    )

JSON_OUTPUT_DIR = os.path.join(OUTPUT_ROOT_DIR, "output_json")
USD_OUTPUT_DIR = os.path.join(OUTPUT_ROOT_DIR, "output_usd")

log_info = carb.log_info
log_warn = carb.log_warn
log_error = carb.log_error


def _set_grey_studio_lighting():
    settings = carb.settings.get_settings()
    settings.set("/persistent/exts/omni.kit.viewport.menubar.lighting/environmentPreset", "Grey Studio")


def focus_and_zoom_on_world():
    ctx = omni.usd.get_context()
    stage = ctx.get_stage()
    if not stage:
        carb.log_error("❌ No USD stage found.")
        return

    world_prim = stage.GetPrimAtPath("/World")
    if not world_prim or not world_prim.IsValid():
        carb.log_error("❌ '/World' prim not found or invalid.")
        return

    ctx.clear_selection()
    ctx.set_selected_prims([world_prim])

    # Perform viewport focus
    viewport = vp_util.get_active_viewport()
    if viewport:
        carb.log_info("🎯 Zooming camera to focus on /World")
        viewport.focus_on_selection()


class ChemSimUI:
    def __init__(self):
        self.prompt_input = None
        self.json_model = None
        self.usd_model = None
        self.usd_file_list = None
        self.json_file_list = None
        self.overlay_window = None
        self.overlay_formula_label = None
        self.overlay_description_label = None
        self.overlay_process_label = None

    def _convert_json_to_usd(self):
        try:
            selected_index = self.json_file_list.model.get_item_value_model().get_value_as_int()
            all_files = self._get_json_files()
            if selected_index >= len(all_files):
                log_error("[ChemSimUI] ❌ Selected index is out of range.")
                return
            selection = all_files[selected_index]
            json_path = os.path.join(JSON_OUTPUT_DIR, selection)
            with open(json_path, "r") as f:
                molecule_data = json.load(f)
            write_usd_from_reaction(molecule_data, USD_OUTPUT_DIR, source_file_name=selection)
            self._reload_extension()
        except Exception as e:
            log_error(f"[ChemSimUI] ❌ Exception during Convert: {e}")

    def _import_usd_file(self):
        try:
            selected_index = self.usd_file_list.model.get_item_value_model().get_value_as_int()
            all_files = self._get_usd_files()
            if selected_index >= len(all_files):
                log_error("[ChemSimUI] ❌ Selected index is out of range.")
                return

            selection = all_files[selected_index]
            usd_path = os.path.join(USD_OUTPUT_DIR, selection)
            log_info(f"[ChemSimUI] Importing USD file: {usd_path}")
            ctx = omni.usd.get_context()
            ctx.open_stage(usd_path)

            stage = ctx.get_stage()
            if not stage:
                log_error("[ChemSimUI] ❌ No USD stage available.")
                return

            # Zoom and light
            _set_grey_studio_lighting()
            focus_and_zoom_on_world()

            # ✅ Play animation
            timeline = omni.timeline.get_timeline_interface()
            timeline.set_current_time(0)
            timeline.play()

            # 💤 Allow time before capturing
            import time
            time.sleep(1.0)

            json_filename = selection.split("\\")[0]
            json_path = os.path.join(JSON_OUTPUT_DIR, f"{json_filename}.json")
            if not os.path.exists(json_path):
                log_error(f"[ChemSimUI] ❌ JSON file not found for reaction: {json_path}")
                return

            with open(json_path, "r") as f:
                reaction_data = json.load(f)

            reactants = [mol["name"] for mol in reaction_data.get("reactants", [])]
            products = [mol["name"] for mol in reaction_data.get("products", [])]
            element_color_map = {}
            for compound in reaction_data["reactants"] + reaction_data["products"]:
                for atom in compound.get("atoms", []):
                    element = atom["element"]
                    color = atom.get("color")
                    if color:
                        element_color_map[element] = color
                    elif element not in element_color_map:
                        element_color_map[element] = "#888888"

            reaction_formula = reaction_data.get("reaction", "No formula provided")
            reaction_description = reaction_data.get("reactionDescription", "No description available")
            reaction_process = f"This reaction involves {', '.join(reactants)} converting into {', '.join(products)}."

            self._show_reaction_summary_overlay(
                formula=reaction_formula,
                description=reaction_description,
                process=reaction_process,
                element_color_map=element_color_map
            )

            # Play animation and capture
            if selection.endswith(".usd") and "reaction_anim_" in selection:
                folder = os.path.join(USD_OUTPUT_DIR, selection.split("\\")[0])
                gif_path = os.path.join(folder, selection.replace(".usd", ".gif"))
                frames_dir = os.path.join(folder, "frames")
                os.makedirs(frames_dir, exist_ok=True)

                timeline = omni.timeline.get_timeline_interface()
                timeline.play()
                render_usd_frames(usd_path, frames_dir, start=0, end=60)
                create_gif_from_frames(frames_dir, gif_path)
                timeline.stop()

                success, msg = upload_anim_and_update_db(gif_path, json_filename, json_filename, {
                    "reaction": reaction_formula,
                    "reactionDescription": reaction_description
                })
                if success:
                    log_info(f"✅ GIF uploaded: {msg}")
                else:
                    log_error(f"❌ GIF upload failed: {msg}")

            stage.GetRootLayer().Save()
            log_info("[ChemSimUI] ✅ Saved stage after adding UI, Camera, Legend.")
        except Exception as e:
            log_error(f"[ChemSimUI] ❌ Error importing USD file: {e}")

    def _scan_anim_files(self):
        anims = []
        root = Path(USD_OUTPUT_DIR)
        if not root.exists():
            return anims
        for sub in root.iterdir():
            if sub.is_dir():
                for usd_file in sub.glob("reaction_anim_*.usd"):
                    anims.append(str(usd_file.relative_to(root)))
        return sorted(anims)

    def color_rgb(self, name):
        table = {
            "white": (1, 1, 1), "red": (1, 0, 0), "blue": (0, 0, 1), "green": (0, 1, 0),
            "lime": (0.5, 1, 0), "purple": (0.5, 0, 0.5), "orange": (1, 0.5, 0),
            "yellow": (1, 1, 0), "pink": (1, 0.75, 0.8), "brown": (0.4, 0.26, 0.13),
            "gray": (0.5, 0.5, 0.5), "black": (0, 0, 0),
        }
        return table.get(name, (0.5, 0.5, 0.5))

    def _show_reaction_summary_overlay(self, formula: str, description: str, process: str, element_color_map: Dict[str, str]):
        log_info("[ChemSimUI] Showing floating overlay with updated reaction info")
        if self.overlay_window is None:
            self.overlay_window = ui.Window("Reaction Summary", width=600, height=300)
            frame = self.overlay_window.frame
            with frame:
                with ui.VStack(spacing=10):
                    self.overlay_formula_label = ui.Label(formula, style={"color": "yellow", "font_size": 24, "alignment": ui.Alignment.CENTER})
                    self.overlay_description_label = ui.Label(description, style={"color": "white", "font_size": 18, "word_wrap": True})
                    self.overlay_process_label = ui.Label(process, style={"color": "white", "font_size": 16, "word_wrap": True})
                    for element, hex_color in element_color_map.items():
                        hex_color = hex_color.lstrip("#")
                        r, g, b = [int(hex_color[i:i+2], 16) / 255.0 for i in (0, 2, 4)]
                        ui.Label(f"{element}", style={"color": (r, g, b), "font_size": 14})
        else:
            self.overlay_formula_label.text = formula
            self.overlay_description_label.text = description
            self.overlay_process_label.text = process

    def build_ui(self):
        self._build_main_ui()

    def _build_main_ui(self):
        with ui.VStack():
            ui.Label("ChemSim Panel", style={"font_size": 20})
            ui.Label("Enter a reaction prompt:")
            self.prompt_input = ui.StringField()
            ui.Button("Generate", clicked_fn=self._send_prompt_to_backend)
            ui.Spacer(height=20)
            ui.Label("Available JSON reaction results:")
            self.json_file_list = ui.ComboBox(0, *self._get_json_files())
            ui.Button("Convert Selected JSON to USD", clicked_fn=self._convert_json_to_usd)
            ui.Spacer(height=20)
            ui.Label("Available USD files:")
            self.usd_file_list = ui.ComboBox(0, *self._get_usd_files())
            ui.Button("Import Selected USD", clicked_fn=self._import_usd_file)
            ui.Spacer(height=20)
            ui.Button("Open Advanced Rendering", clicked_fn=self._open_advanced_window)

    def _get_json_files(self):
        try:
            return [f.name for f in Path(JSON_OUTPUT_DIR).glob("*.json")]
        except Exception as e:
            log_error(f"[ChemSimUI] Error listing JSON files: {e}")
            return []

    def _get_usd_files(self):
        try:
            return self._scan_anim_files()
        except Exception as e:
            log_error(f"[ChemSimUI] Error listing USD files: {e}")
            return []

    def _send_prompt_to_backend(self):
        prompt = self.prompt_input.model.get_value_as_string().strip()
        if not prompt:
            log_warn("[ChemSimUI] Empty prompt. Skipping.")
            return
        try:
            result = get_molecule_structure(prompt)
            os.makedirs(JSON_OUTPUT_DIR, exist_ok=True)
            output_path = os.path.join(JSON_OUTPUT_DIR, f"{prompt.replace(' ', '_')}.json")
            with open(output_path, "w") as f:
                json.dump(result, f, indent=2)
            log_info(f"[ChemSimUI] Wrote JSON output to: {output_path}")
            self._reload_extension()
        except Exception as e:
            log_error(f"[ChemSimUI] Error in GPT backend call: {e}")

    def _reload_extension(self):
        try:
            if self.overlay_window:
                self.overlay_window.close()
                self.overlay_window = None
                self.overlay_formula_label = None
                self.overlay_description_label = None
                self.overlay_process_label = None
            window = ui.Workspace.get_window("ChemSim Panel")
            if window:
                window.frame.clear()
                with window.frame:
                    self.build_ui()
            else:
                self.build_ui()
        except Exception as e:
            log_error(f"[ChemSimUI] ❌ Failed to reload extension: {e}")

    def _open_advanced_window(self):
        if hasattr(self, 'advanced_window') and self.advanced_window and not self.advanced_window.is_closed:
            self.advanced_window.focus()
            return
        self.advanced_window = ui.Window("Advanced Rendering", width=600, height=400)
        with self.advanced_window.frame:
            with ui.VStack():
                ui.Label("Advanced Rendering Options", style={"font_size": 18})
                ui.Label("Simulation parameters (PhysX, visuals, etc.) coming soon...")
                ui.FloatSlider(min=20, max=100, default=25, label="Temperature (°C)")
                ui.FloatSlider(min=1, max=10, default=1, label="Pressure (atm)")
                ui.FloatSlider(min=0, max=1, default=0.5, label="Reactant A Concentration")
