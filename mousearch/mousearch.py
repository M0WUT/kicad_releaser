import pathlib
import re
from datetime import datetime
from itertools import islice
from math import ceil
from time import sleep
import pathlib
from tqdm import tqdm
import sys
import os
import subprocess

from common import ErrorDialog, InfoDialog, WarningDialog
from mouser_api import MouserAPI
from farnell_api import FarnellAPI

MOUSER_BIT = 1 << 1
FARNELL_BIT = 1 << 0


class Mousearch:
    def __init__(self, mouser_key: str, farnell_key: str):
        self.mouser_key = mouser_key
        self.farnell_key = farnell_key

    def generate_bom(
        self, top_level_schematic: pathlib.Path, output_file: pathlib.Path = "bom.csv"
    ):
        commands = [
            "kicad-cli",
            "sch",
            "export",
            "bom",
            "--output",
            output_file,
            "--fields",
            "MPN,${QUANTITY}",
            "--exclude-dnp",
            "--group-by",
            "MPN",
            str(top_level_schematic),
        ]
        subprocess.check_output(commands)
        self.bom = output_file

    def query_suppliers(self, output_file: pathlib.Path):

        mouser_api = MouserAPI(self.mouser_key)
        farnell_api = FarnellAPI(self.farnell_key)

        found_parts = {}

        with open(self.bom) as bom_file:
            for line in tqdm(bom_file.readlines()[1:3]):  # @DEBUG
                mpn, quantity = line.split('","')
                mpn = re.sub('"', "", mpn)
                quantity = int(re.sub('"', "", quantity))

                start_time = datetime.now()
                score = 0
                # Check Mouser
                if mouser_api.check_for_stock(mpn) >= quantity:
                    score += MOUSER_BIT

                # Check Farnell
                if farnell_api.check_for_stock(mpn) >= quantity:
                    score += FARNELL_BIT

                found_parts[mpn] = score
                while (datetime.now() - start_time).seconds < 2:
                    sleep(0.1)

        # Print report in sorted order
        issues = {}
        with open(output_file, "w") as file:
            file.write("| MPN | Mouser | Farnell |\r")
            file.write("| --- | --- | --- |\r")
            for mpn, score in sorted(
                found_parts.items(), key=lambda item: (item[1], item[0])
            ):

                file.write(f"| {mpn} ")
                if score & MOUSER_BIT:
                    file.write("| ✅ ")
                else:
                    file.write("| ❌ ")

                if score & FARNELL_BIT:
                    file.write("| ✅ ")
                else:
                    file.write("| ❌ ")

                file.write("|\r")

                if score == 0:
                    issues[mpn] = "Not found in Mouser or Farnell"

            if issues:
                warning_string = "Issues found with the following parts:\n"
                for mpn, issue in issues.items():
                    warning_string += f"* {mpn}:    {issue}\n"
                print(warning_string)
                # WarningDialog(warning_string, "BOM Issues found")
            else:
                print("OK")
                # InfoDialog("No BOM issues found", "Mousearch")

    def run(
        self,
        top_level_schematic: pathlib.Path,
        output_file: pathlib.Path,
        csv_location: pathlib.Path = "bom.csv",
    ):
        self.generate_bom(
            top_level_schematic=top_level_schematic, output_file=csv_location
        )
        self.query_suppliers(output_file=output_file)


if __name__ == "__main__":
    input_dir = pathlib.Path(sys.argv[1])
    found_projects = list(input_dir.rglob("*.kicad_pro"))
    assert len(found_projects) == 1, f"Multiple projects found: {found_projects}"
    top_level_schematic = found_projects[0].with_suffix(".kicad_sch")
    print(f"Generating BOM for {top_level_schematic}")

    x = Mousearch(mouser_key=sys.argv[2], farnell_key=sys.argv[3])
    x.run(top_level_schematic=top_level_schematic, output_file=sys.argv[4])
