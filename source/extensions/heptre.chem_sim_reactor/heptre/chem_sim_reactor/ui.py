import omni.ui as ui
from pathlib import Path
import os
import json
import carb

from .chem_api import get_molecule_structure
from .usd_writer import write_usd_from_reaction

EXT_DIR = os.path.dirname(os.path.abspath(__file__))
JSON_OUTPUT_DIR = os.path.join(EXT_DIR, "output_json")
USD_OUTPUT_DIR = os.path.join(EXT_DIR, "output_usd")

log_info = carb.log_info
log_warn = carb.log_warn
log_error = carb.log_error


class ChemSimUI:
    def __init__(self):
        self.prompt_input = None
        self.usd_file_list = None
        self.json_file_list = None

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

            self.usd_file_list.set_value_items(self._get_usd_files())

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
            omni.usd.get_context().open_stage(usd_path)

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
