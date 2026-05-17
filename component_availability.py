from dataclasses import dataclass
from enum import Enum
from io import TextIOWrapper
from pathlib import Path
import re
from datetime import datetime
from time import sleep
from tqdm import tqdm
import sys
import subprocess
from typing import Optional
from enum import StrEnum
from contextlib import ExitStack, suppress

import argparse


from supplier_api.mouser_api import MouserAPI
from supplier_api.farnell_api import FarnellAPI
from supplier_api.supplier_api import SupplierAPI


class ComponentSupplierNames(StrEnum):
    FARNELL = "Farnell"
    MOUSER = "Mouser"


# Display name: (priority (higher number = higher priority), API class)
SUPPLIER_PREFERENCES: dict[ComponentSupplierNames, tuple[int, type[SupplierAPI]]] = {
    ComponentSupplierNames.MOUSER: (1, MouserAPI),
    ComponentSupplierNames.FARNELL: (0, FarnellAPI),
}


@dataclass
class ComponentSupplier:
    name: str
    priority: int  # Higher = higher priority
    supplier_api: SupplierAPI
    num_parts_to_be_sourced: int = 0
    bom_file: Optional[TextIOWrapper] = None


class ComponentAvailabilitySearcher:

    DELAY_BETWEEN_QUERIES_S = 2

    def __init__(
        self, api_keys: dict[ComponentSupplierNames, Optional[str]], output_folder: Path
    ):
        self.suppliers: list[ComponentSupplier] = []
        self.output_folder = output_folder
        for supplier in ComponentSupplierNames:
            if supplier in api_keys:
                api_key = api_keys[supplier]
                if api_key is None:
                    continue
                priority, api_class = SUPPLIER_PREFERENCES[supplier]
                self.suppliers.append(
                    ComponentSupplier(supplier.value, priority, api_class(api_key))
                )

        # Sort so highest priority suppliers are first
        self.suppliers.sort(key=lambda x: x.priority, reverse=True)

    def generate_bom(self, top_level_schematic: Path):
        self.bom_path = self.output_folder / "overall_bom.csv"
        self.bom_path.parent.mkdir(parents=True, exist_ok=True)

        commands = [
            "kicad-cli",
            "sch",
            "export",
            "bom",
            "--output",
            self.bom_path,
            "--fields",
            "MPN,${QUANTITY}",
            "--exclude-dnp",
            "--group-by",
            "MPN",
            str(top_level_schematic),
        ]
        subprocess.check_output(commands)

    def query_suppliers(
        self,
        # Set to true to only test a few parts to speed up dev cycle
        dev_run: bool = False,
    ):

        with (
            open(self.bom_path) as bom_file,
            open(self.output_folder / "availability_report.md", "w") as bom_report,
            ExitStack() as exit_stack,
        ):
            parts_to_check = bom_file.readlines()[1:]

            if dev_run:
                # Only check as few parts as this takes ages
                parts_to_check = parts_to_check[:5]

            print(f"Saving results to {self.bom_path.absolute()}")

            if len(self.suppliers) == 0:
                bom_report.write(
                    "No API keys supplied. Unable to query part availability"
                )
                return

            # Effectively calls with open ..... on each file without knowing
            # how many exist at "compile" time
            for supplier in self.suppliers:
                supplier.bom_file = exit_stack.enter_context(
                    open(self.output_folder / f"{supplier.name.lower()}_bom.csv", "w")
                )

            # Initialise variables for holding results
            issues_found_str = ""
            num_unavailable_parts = 0

            for line in tqdm(parts_to_check):
                mpn, needed_quantity = line.split('","')
                mpn = re.sub('"', "", mpn)
                needed_quantity = int(re.sub('"', "", needed_quantity))

                start_time = datetime.now()
                availability_str = f"| {mpn} "

                # Used to track if already dealt with
                added_to_bom = False
                availability_isses = False

                # This list is already sorted
                for supplier in self.suppliers:

                    available_quantity = supplier.supplier_api.query_stock_quantity(mpn)
                    if available_quantity > needed_quantity:
                        availability_str += "| ✅ "
                        if added_to_bom is False:
                            supplier.bom_file.write(f"{mpn},{needed_quantity}\n")
                            supplier.num_parts_to_be_sourced += 1
                            added_to_bom = True
                    else:
                        # Report if component isn't available from all queried parties
                        # Possibily paranoid but part may be single sourced
                        availability_isses = True
                        # Something went wrong with the query
                        availability_str += (
                            "| ⚠️ " if available_quantity == -1 else "| ❌ "
                        )

                availability_str += "|\r"

                if added_to_bom is False:
                    num_unavailable_parts += 1

                if availability_isses:
                    # Add header to issues_found_str the first time an issue
                    if issues_found_str == "":
                        issues_found_str = "### Issues\rPossible supply issues were found with the following items:\r\r"
                        issues_found_str += f"| MPN | {' | '.join([supplier.name for supplier in self.suppliers])} |\r"
                        issues_found_str += f"|{' --- |' * (1+len(self.suppliers))} \r"
                    # Add problematic componenet
                    issues_found_str += availability_str

                # Meet rate limiting on free api access
                while (
                    datetime.now() - start_time
                ).seconds < self.DELAY_BETWEEN_QUERIES_S:
                    sleep(0.1)

            issues_found_str += "\r\r✅: Required quantity is available, ❌: Part successfully queried - insufficient quantity, ⚠️: Query unsuccessful (Part not found, multiple parts found etc.)\r"

            # Have finished going through parts
            if issues_found_str == "":
                issues_found_str = "### Issues\rNo supply issues found\r"

            sourcing_table = f"### Supply breakdown\r"
            sourcing_table += f"| Source | {' | '.join([supplier.name for supplier in self.suppliers])} | Unavailable |\r"
            sourcing_table += f"|{' --- |' * (2+len(self.suppliers))} \r"
            sourcing_table += f"| Components | {' | '.join(str(supplier.num_parts_to_be_sourced) for supplier in self.suppliers)} | {num_unavailable_parts} |\r\r\r"

            bom_report.write(sourcing_table + issues_found_str)

    def generate_report(
        self,
        top_level_schematic: Path,
        dev_run: bool = False,
    ):
        self.generate_bom(top_level_schematic=top_level_schematic)
        self.query_suppliers(dev_run=dev_run)


if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description="Search KiCad projects and generate output files."
    )
    parser.add_argument(
        "-i",
        "--input_folder",
        required=True,
        help="Folder to search for Kicad projects",
    )
    parser.add_argument(
        "-o",
        "--output_folder",
        required=True,
        help="Folder where generated files will be saved",
    )
    parser.add_argument("-m", "--mouser_api_key", required=False, help="Mouser API Key")
    parser.add_argument(
        "-f", "--farnell_api_key", required=False, help="Farnell API Key"
    )

    args = parser.parse_args()

    print(args)

    input_folder = Path(args.input_folder)
    output_folder = Path(args.output_folder)

    found_projects = list(input_folder.rglob("*.kicad_pro"))
    assert len(found_projects) == 1, f"Multiple projects found: {found_projects}"
    top_level_schematic = found_projects[0].with_suffix(".kicad_sch")
    print(f"Generating BOM for {top_level_schematic}")

    api_keys = {}

    if args.mouser_api_key:
        api_keys[ComponentSupplierNames.MOUSER] = args.mouser_api_key
    if args.farnell_api_key:
        api_keys[ComponentSupplierNames.FARNELL] = args.farnell_api_key

    x = ComponentAvailabilitySearcher(api_keys, output_folder)
    x.generate_report(top_level_schematic)
