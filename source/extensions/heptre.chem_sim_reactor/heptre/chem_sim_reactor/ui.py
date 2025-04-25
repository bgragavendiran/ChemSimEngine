import omni.ui as ui
from pathlib import Path
import os
import json
import carb
from .Molecular import ELEMENT_COLORS
from .chem_api import get_molecule_structure
from .usd_writer import write_usd_from_reaction
from pxr import UsdGeom, Sdf
EXT_DIR = os.path.dirname(os.path.abspath(__file__))
JSON_OUTPUT_DIR = os.path.join(EXT_DIR, "output_json")
USD_OUTPUT_DIR = os.path.join(EXT_DIR, "output_usd")

log_info = carb.log_info
log_warn = carb.log_warn
log_error = carb.log_error



class ChemSimUI:
    ELEMENT_TO_COLOR = {
        "H": "white",
        "C": "black",
        "O": "red",
        "N": "blue",
        "Cl": "green",
        "Na": "purple",
        "K": "orange",
        "S": "yellow",
        "P": "brown",
        "Fe": "gray",
    }
    def __init__(self):
        self.prompt_input = None
        self.usd_file_list = None
        self.json_file_list = None
        self.overlay_label = None
        self._overlay_window = None



    def _convert_json_to_usd(self):
        try:
            selected_index = self.json_file_list.model.get_item_value_model().get_value_as_int()
            all_files = self._get_json_files()

            if selected_index >= len(all_files):
                log_error("[ChemSimUI] ❌ Selected index is out of range.")
                return

            selection = all_files[selected_index]
            log_info(f"[ChemSimUI] ✅ Final selected file from list: {selection}")

            json_path = os.path.join(JSON_OUTPUT_DIR, selection)

            with open(json_path, "r") as f:
                molecule_data = json.load(f)

            write_usd_from_reaction(molecule_data, USD_OUTPUT_DIR, source_file_name=selection)
            new_usd_list = self._get_usd_files()
            self.usd_file_list.model.set_item_list(new_usd_list)
            self.usd_file_list.model.set_value(0)


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
            import omni.usd
            ctx = omni.usd.get_context()
            ctx.open_stage(usd_path)

            # ➡️ Add reaction summary and legend
            stage = ctx.get_stage()
            if not stage:
                log_error("[ChemSimUI] ❌ No USD stage available.")
                return

            # Reaction info from filename
            # Load the corresponding JSON to get real reactants/products
            json_filename = selection.split("\\")[0]  # Get the folder name before \reaction_anim.usd
            json_path = os.path.join(JSON_OUTPUT_DIR, f"{json_filename}.json")

            if not os.path.exists(json_path):
                log_error(f"[ChemSimUI] ❌ JSON file not found for reaction: {json_path}")
                return

            with open(json_path, "r") as f:
                reaction_data = json.load(f)

            reactants = [mol["name"] for mol in reaction_data.get("reactants", [])]
            products = [mol["name"] for mol in reaction_data.get("products", [])]

            reaction_text = f"Reactants: {', '.join(reactants)} → Products: {', '.join(products)}"

            self._show_reaction_summary_overlay(reaction_text)
            stage.GetRootLayer().Save()
            log_info("[ChemSimUI] ✅ Saved stage after adding UI, Camera, Legend.")

        except Exception as e:
            log_error(f"[ChemSimUI] ❌ Error importing USD file: {e}")


    def _scan_anim_files(self):
        anims = []
        root  = Path(USD_OUTPUT_DIR)
        if not root.exists():
            return anims
        for sub in root.iterdir():
            if sub.is_dir():
                anim = sub / "reaction_anim.usd"
                if anim.exists():
                    # make path *relative* to USD_OUTPUT_DIR for the ComboBox
                    anims.append(str(anim.relative_to(root)))
        return sorted(anims)

    def color_rgb(self, name):
        table = {
            "white": (1, 1, 1),
            "red": (1, 0, 0),
            "blue": (0, 0, 1),
            "green": (0, 1, 0),
            "lime": (0.5, 1, 0),
            "purple": (0.5, 0, 0.5),
            "orange": (1, 0.5, 0),
            "yellow": (1, 1, 0),
            "pink": (1, 0.75, 0.8),
            "brown": (0.4, 0.26, 0.13),
            "gray": (0.5, 0.5, 0.5),
            "black": (0, 0, 0),
        }
        return table.get(name, (0.5, 0.5, 0.5))


    def _show_reaction_summary_overlay(self, text: str):
        log_info("[ChemSimUI] 🧪 Forcing visible color in UI overlay")

        if self.overlay_label is None:
            self._overlay_window = ui.Window("Reaction Summary", width=500, height=120)
            frame = self._overlay_window.frame

            with frame:
                with ui.VStack(spacing=10):
                    self.overlay_label = ui.Label(
                        f"Reactants: {text}",
                        style={"color": "white", "font_size": 20}
                    )

                    ui.Label("Color Test:", style={"color": "white", "font_size": 16})

                    bright_colors = {
                        "H": (1.0, 1.0, 1.0),
                        "C": (0.1, 0.1, 0.1),
                        "O": (1.0, 0.0, 0.0),
                        "N": (0.0, 0.4, 1.0),
                        "Cl": (0.1, 1.0, 0.2),
                        "Na": (0.6, 0.2, 1.0),
                        "K": (1.0, 0.6, 0.2),
                        "S": (1.0, 1.0, 0.1),
                        "P": (0.8, 0.4, 0.1),
                        "Fe": (0.6, 0.6, 0.6),
                    }

                    for elem, rgb in bright_colors.items():
                        with ui.HStack(height=20):
                            ui.Frame(
                                width=18,
                                height=18,
                                style={
                                    "background_color": (*rgb, 1.0),
                                    "border_radius": 9,
                                    "margin_right": 10,
                                    "padding": 0,
                                    "border_width": 0,
                                }
                            )

                            ui.Label(f"{elem}", style={"color": "white", "font_size": 16})

        else:
            self.overlay_label.text = f"Reactants: {text}"







    def _add_reaction_summary_to_world(self, stage, reactants, products):
        from pxr import Gf

        log_info("[ChemSimUI] ➡️ Adding Reaction Summary Marker (Visible Cube) to World")

        summary_xform = UsdGeom.Xform.Define(stage, "/World/UI/ReactionSummaryXform")
        UsdGeom.Xformable(summary_xform).AddTranslateOp().Set(Gf.Vec3f(0, 8, 0))

        cube = UsdGeom.Cube.Define(stage, "/World/UI/ReactionSummaryXform/ReactionCube")
        cube.CreateSizeAttr(1.5)
        UsdGeom.Xformable(cube).AddTranslateOp().Set(Gf.Vec3f(0, 0, 0))
        cube.CreateDisplayColorAttr().Set([(0.8, 0.2, 0.2)])  # Red color

        log_info(f"[ChemSimUI] ✅ Reaction Summary Cube Added.")

    def _add_camera_pointing_to_center(self, stage):
        from pxr import Gf

        log_info("[ChemSimUI] ➡️ Adding Camera to World")

        cam_xform = UsdGeom.Xform.Define(stage, "/World/UI/CameraXform")
        xformable = UsdGeom.Xformable(cam_xform)
        xformable.AddTranslateOp().Set(Gf.Vec3f(0, 10, 20))  # Camera is high and away

        cam = UsdGeom.Camera.Define(stage, "/World/UI/CameraXform/SceneCamera")
        cam.CreateFocusDistanceAttr(10.0)
        cam.CreateFocalLengthAttr(50.0)
        cam.CreateHorizontalApertureAttr(20.955)  # default in mm

        log_info("[ChemSimUI] ✅ Camera Added.")

    def _add_color_legend(self, stage, elements, base_position=(0, 5, -5)):
        log_info("[ChemSimUI] ➡️ Adding Color Legend to World")

        legend_xform = UsdGeom.Xform.Define(stage, "/World/UI/LegendXform")
        UsdGeom.Xformable(legend_xform).AddTranslateOp().Set(Gf.Vec3f(*base_position))

        for i, elem in enumerate(sorted(elements)):
            color = ELEMENT_COLORS.get(elem, "gray")
            x_offset = i * 3.0  # more spacing now that things are big

            # 🌐 Sphere
            sphere = UsdGeom.Sphere.Define(stage, f"/World/UI/LegendXform/{elem}")
            sphere.CreateRadiusAttr(0.5)
            UsdGeom.Xformable(sphere).AddTranslateOp().Set(Gf.Vec3f(x_offset, 0, 0))
            sphere.CreateDisplayColorAttr().Set([self.color_rgb(color)])

            # 🔤 Label
            label = UsdGeom.Text.Define(stage, f"/World/UI/LegendXform/{elem}_Label")
            label.CreateTextAttr(elem)
            label.CreateFontSizeAttr(150.0)
            UsdGeom.Xformable(label).AddTranslateOp().Set(Gf.Vec3f(x_offset, 1.0, 0))  # above sphere

        log_info("[ChemSimUI] ✅ Color Legend Added.")




    def build_ui(self):
        with ui.VStack():
            ui.Label("Enter a reaction prompt:")
            self.prompt_input = ui.StringField()

            ui.Button("Generate", clicked_fn=self._send_prompt_to_backend)

            ui.Label("Available JSON reaction results:")
            self.json_file_list = ui.ComboBox(0, *self._get_json_files())

            ui.Button("Convert Selected JSON to USD", clicked_fn=self._convert_json_to_usd)

            ui.Spacer(height=20)
            ui.Label("Available USD files:")
            self.usd_file_list = ui.ComboBox(0, *self._get_usd_files())

            ui.Button("Import Selected USD", clicked_fn=self._import_usd_file)

    def _get_json_files(self):
        try:
            json_files = [f.name for f in Path(JSON_OUTPUT_DIR).glob("*.json")]
            log_info(f"[ChemSimUI] Found JSON files: {json_files}")
            return json_files
        except Exception as e:
            log_error(f"[ChemSimUI] Error listing JSON files: {e}")
            return []

    def _get_usd_files(self):
        try:
            usd_files = self._scan_anim_files()
            log_info(f"[ChemSimUI] Found reaction_anim.usd files: {usd_files}")
            return usd_files
        except Exception as e:
            log_error(f"[ChemSimUI] Error listing USD files: {e}")
            return []

    def _send_prompt_to_backend(self):
        prompt = self.prompt_input.model.get_value_as_string().strip()
        if not prompt:
            log_warn("[ChemSimUI] Empty prompt. Skipping.")
            return

        log_info(f"[ChemSimUI] Sending prompt to backend: {prompt}")
        try:
            result = get_molecule_structure(prompt)
            os.makedirs(JSON_OUTPUT_DIR, exist_ok=True)

            output_path = os.path.join(JSON_OUTPUT_DIR, f"{prompt.replace(' ', '_')}.json")
            with open(output_path, "w") as f:
                json.dump(result, f, indent=2)

            log_info(f"[ChemSimUI] Wrote JSON output to: {output_path}")
            self.json_file_list.set_value_items(self._get_json_files())

        except Exception as e:
            log_error(f"[ChemSimUI] Error in GPT backend call: {e}")
