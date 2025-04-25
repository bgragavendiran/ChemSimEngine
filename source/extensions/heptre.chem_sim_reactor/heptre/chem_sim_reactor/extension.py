import omni.ext
from omni import log
import omni.ui as ui
from .ui import ChemSimUI


class ChemSimReactorExtension(omni.ext.IExt):
    def on_startup(self, ext_id):
        log.info("[heptre.chem_sim_reactor] Extension startup")

        self._window = ui.Window("ChemSim Panel", width=400, height=300)
        with self._window.frame:
            self._ui = ChemSimUI()
            self._ui.build_ui()

    def on_shutdown(self):
        log.info("[heptre.chem_sim_reactor] Extension shutdown")
        if self._window:
            self._window.visible = False
            self._window = None
