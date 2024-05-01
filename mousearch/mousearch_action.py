import pcbnew

from .mousearch import Mousearch


class MousearchPluginAction(pcbnew.ActionPlugin):
    def defaults(self):
        self.name = "Mousearch BOM Check"
        self.category = "M0WUT Tools"
        self.description = "Checks BOM against current Mouser stock"

    def Run(self):
        Mousearch(pcbnew.GetBoard())
