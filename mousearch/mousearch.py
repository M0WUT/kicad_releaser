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


from mousearch.mouser_api import MouserAPI
from mousearch.farnell_api import FarnellAPI

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

    def query_suppliers(
        self,
        output_file: pathlib.Path,
        mouser_basket: pathlib.Path,
        farnell_basket: pathlib.Path,
    ):

        mouser_api = MouserAPI(self.mouser_key)
        farnell_api = FarnellAPI(self.farnell_key)

        found_parts = {}

        with open(self.bom) as bom_file:
            for line in tqdm(bom_file.readlines()[1:3]):
                mpn, quantity = line.split('","')
                mpn = re.sub('"', "", mpn)
                quantity = int(re.sub('"', "", quantity))

                start_time = datetime.now()
                score = 0  # Use score to sort results easily
                # Check Mouser
                if mouser_api.check_for_stock(mpn) >= quantity:
                    score += MOUSER_BIT

                # Check Farnell
                if farnell_api.check_for_stock(mpn) >= quantity:
                    score += FARNELL_BIT

                found_parts[mpn] = {
                    "score": score,
                    "stockedAtMouser": bool(score & MOUSER_BIT),
                    "stockedAtFarnell": bool(score & FARNELL_BIT),
                    "quantityNeeded": quantity,
                }
                while (datetime.now() - start_time).seconds < 2:
                    sleep(0.1)

        # Print report in sorted order
        with (
            open(output_file, "w") as bom_report,
            open(mouser_basket, "w") as mouser_csv,
            open(farnell_basket, "w") as farnell_csv,
        ):

            issues_found_str = ""
            num_parts_from_mouser = 0
            num_parts_from_farnell = 0
            num_unavailable_parts = 0
            for mpn, status in sorted(
                found_parts.items(), key=lambda item: (item[1]["score"], item[0])
            ):
                # Order from first supplier that has stock
                quantity = status["quantityNeeded"]
                if status["stockedAtMouser"]:
                    mouser_csv.write(f"{mpn},{quantity}\n")
                    num_parts_from_mouser += 1
                elif status["stockedAtFarnell"]:
                    farnell_csv.write(f"{mpn},{quantity}\n")
                    num_parts_from_farnell += 1
                else:
                    num_unavailable_parts += 1

                # Highlight potential issues for any part that is not
                # in stock by every supplier
                if status["score"] < (MOUSER_BIT | FARNELL_BIT):
                    if issues_found_str == "":
                        # Put header in
                        issues_found_str = "### Issues\rPossible supply issues were found with the following items:\r\r"
                        issues_found_str += "| MPN | Mouser | Farnell |\r"
                        issues_found_str += "| --- | --- | --- |\r"

                    issues_found_str += f"| {mpn} "
                    if status["stockedAtMouser"]:
                        issues_found_str += "| ✅ "
                    else:
                        issues_found_str += "| ❌ "

                    if status["stockedAtFarnell"]:
                        issues_found_str += "| ✅ "
                    else:
                        issues_found_str += "| ❌ "

                    issues_found_str += "|\r"

            # Have finished going through parts
            if issues_found_str == "":
                issues_found_str = '### Issues\rNo supply issues found\r'

            sourcing_table = f"### Supply breakdown\r"
            sourcing_table += "| Source | Mouser | Farnell | Unavailable |\r"
            sourcing_table += "| --- | --- | --- | --- |\r"
            sourcing_table += f"| Components | {num_parts_from_mouser} | {num_parts_from_farnell} | {num_unavailable_parts} |\r\r\r"
            bom_report.write(sourcing_table + issues_found_str)

    def run(
        self,
        top_level_schematic: pathlib.Path,
        output_file: pathlib.Path,
        mouser_basket: pathlib.Path,
        farnell_basket: pathlib.Path,
        csv_location: pathlib.Path = "bom.csv",
    ):
        self.generate_bom(
            top_level_schematic=top_level_schematic, output_file=csv_location
        )
        self.query_suppliers(
            output_file=output_file,
            mouser_basket=mouser_basket,
            farnell_basket=farnell_basket,
        )


if __name__ == "__main__":
    input_dir = pathlib.Path(sys.argv[1])
    found_projects = list(input_dir.rglob("*.kicad_pro"))
    assert len(found_projects) == 1, f"Multiple projects found: {found_projects}"
    top_level_schematic = found_projects[0].with_suffix(".kicad_sch")
    print(f"Generating BOM for {top_level_schematic}")

    x = Mousearch(mouser_key=sys.argv[2], farnell_key=sys.argv[3])
    x.run(top_level_schematic=top_level_schematic, output_file=sys.argv[4])
