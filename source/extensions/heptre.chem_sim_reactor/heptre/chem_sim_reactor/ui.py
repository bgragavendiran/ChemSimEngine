import omni.ui as ui
from pathlib import Path
import os
import json
import carb
from .chem_api import get_molecule_structure
from .usd_writer import write_usd_from_reaction
from pxr import UsdGeom, Sdf
from typing import Dict

EXT_DIR = os.path.dirname(os.path.abspath(__file__))

# Check if running inside a _build environment
if "_build" in EXT_DIR:
    OUTPUT_ROOT_DIR = EXT_DIR
else:
    # Dynamically map to _build output if running from source
    OUTPUT_ROOT_DIR = EXT_DIR.replace(
        r"source\extensions",
        r"_build\windows-x86_64\release\exts"
    )

JSON_OUTPUT_DIR = os.path.join(OUTPUT_ROOT_DIR, "output_json")
USD_OUTPUT_DIR = os.path.join(OUTPUT_ROOT_DIR, "output_usd")


log_info = carb.log_info
log_warn = carb.log_warn
log_error = carb.log_error



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
            log_info(f"[ChemSimUI] ✅ Final selected file from list: {selection}")

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

            # build element → color map dynamically from parsed atoms
            element_color_map = {}
            for compound in reaction_data["reactants"] + reaction_data["products"]:
                for atom in compound.get("atoms", []):
                    element = atom["element"]
                    color = atom.get("color")
                    if color:
                        element_color_map[element] = color
                    elif element not in element_color_map:
                        element_color_map[element] = "#888888"  # Only fallback if no color ever given


            reaction_formula = reaction_data.get("reaction", "No formula provided")
            reaction_description = reaction_data.get("reactionDescription", "No description available")
            reaction_process = f"This reaction involves {', '.join(reactants)} converting into {', '.join(products)}."

            self._show_reaction_summary_overlay(
                formula=reaction_formula,
                description=reaction_description,
                process=reaction_process,
                element_color_map=element_color_map
            )

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



    def _show_reaction_summary_overlay(self, formula: str, description: str, process: str, element_color_map: Dict[str, str]):
        log_info("[ChemSimUI] Showing floating overlay with updated reaction info")

        if self.overlay_window is None:
            self.overlay_window = ui.Window("Reaction Summary", width=600, height=300)
            frame = self.overlay_window.frame

            with frame:
                with ui.VStack(spacing=10):
                    self.overlay_formula_label = ui.Label(
                        formula,
                        style={"color": "yellow", "font_size": 24, "alignment": ui.Alignment.CENTER}
                    )
                    self.overlay_description_label = ui.Label(
                        description,
                        style={"color": "white", "font_size": 18, "word_wrap": True}
                    )
                    self.overlay_process_label = ui.Label(
                        process,
                        style={"color": "white", "font_size": 16, "word_wrap": True}
                    )
                    for element, hex_color in element_color_map.items():
                        hex_color = hex_color.lstrip("#")
                        r, g, b = [int(hex_color[i:i+2], 16) / 255.0 for i in (0, 2, 4)]
                        rgb = (r, g, b)
                        ui.Label(
                            f"{element}",
                            style={"color": rgb, "font_size": 14}
                        )
        else:
            # Update existing window content
            self.overlay_formula_label.text = formula
            self.overlay_description_label.text = description
            self.overlay_process_label.text = process


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

            self._reload_extension()

        except Exception as e:
            log_error(f"[ChemSimUI] Error in GPT backend call: {e}")

    def _reload_extension(self):
        try:
            window = ui.Workspace.get_window("ChemSim Panel")
            if window:
                log_info("[ChemSimUI] 🧹 Clearing ChemSim Panel before UI rebuild")
                window.frame.clear()
                with window.frame:
                    self.build_ui()
                log_info("[ChemSimUI] 🔁 Extension UI rebuilt successfully.")
            else:
                log_warn("[ChemSimUI] ⚠️ Could not find window 'ChemSim Panel'. Rebuilding directly.")
                self.build_ui()
        except Exception as e:
            log_error(f"[ChemSimUI] ❌ Failed to reload extension: {e}")
