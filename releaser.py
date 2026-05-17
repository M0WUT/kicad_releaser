from dataclasses import dataclass
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Optional, Sequence, Tuple
from zipfile import ZipFile
from datetime import datetime

import git
import markdown2
import pybars
import pypdf

from component_availability import ComponentAvailabilitySearcher, ComponentSupplierNames

from kikit.present import readTemplate


@dataclass
class GitCommitInfo:
    commit_hash: str
    commit_tag: str | None
    commit_date: str
    commit_time: str


@dataclass
class KicadArtefactsGenerator:
    search_folder: Path
    output_folder: Path
    wut_library_folder: Path
    mouser_api_key: Optional[str] = None
    farnell_api_key: Optional[str] = None

    def __post_init__(self):
        self.discover_kicad_project(self.search_folder)
        self.generate_kicad_extra_args()
        print(f"Running with generated args: {self.kicad_extra_args}")

        self.add_wut_libraries()

        api_keys = {
            ComponentSupplierNames.MOUSER: self.mouser_api_key,
            ComponentSupplierNames.FARNELL: self.farnell_api_key,
        }
        self._component_availability_searcher = ComponentAvailabilitySearcher(
            api_keys, self.output_folder
        )

    def run_command(
        self,
        commands: Sequence[str | Path],
        include_extra_kicad_args: bool = True,
        env=None,
    ):

        command_list = [str(x) for x in commands]
        if include_extra_kicad_args:
            command_list += self.kicad_extra_args

        subprocess.run(command_list, check=True, capture_output=True)

    def get_git_info(self, repo_path: Path):
        if not (repo_path / ".git").exists():
            raise ValueError(f"Not a git repository: {repo_path}")

        def git(*args: str) -> str:
            result = subprocess.run(
                ["git", *args],
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout.strip()

        try:
            # Full commit hash
            commit_hash = git("rev-parse", "HEAD")

            # Tag pointing at HEAD (if any)
            try:
                commit_tag = git("describe", "--tags", "--exact-match")
            except subprocess.CalledProcessError:
                commit_tag = None

            # Commit timestamp in ISO format
            iso_datetime = git("show", "-s", "--format=%cI", "HEAD")
            dt = datetime.fromisoformat(iso_datetime)

            return GitCommitInfo(
                commit_hash=commit_hash,
                commit_tag=commit_tag,
                commit_date=dt.date().isoformat(),
                commit_time=dt.time().strftime("%H:%M"),
            )

        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Git command failed: {e.stderr.strip()}") from e

    def generate_kicad_extra_args(self):
        self.kicad_extra_args: list[str] = []

        # WUT_GIT_VERSION
        # WUT_GIT_COMMIT_TAG
        # WUT_GIT_COMMIT_DATE
        # WUT_GIT_COMMIT_TIME
        # WUT_LIBRARIES

        self.git_info = self.get_git_info(self.project_path.parent)

        extra_info = {
            "WUT_GIT_VERSION": self.git_info.commit_hash[:8],
            "WUT_GIT_COMMIT_DATE": self.git_info.commit_date,
            "WUT_GIT_COMMIT_TIME": self.git_info.commit_time,
            "WUT_LIBRARIES": str(self.wut_library_folder.absolute()),
        }
        if self.git_info.commit_tag is not None:
            extra_info["WUT_GIT_COMMIT_TAG"] = f" ({self.git_info.commit_tag})"

        for key, value in extra_info.items():
            self.kicad_extra_args += ["-D", f"{key}={value}"]

    def add_wut_libraries(self):
        # Kicad needs to be told about the new WUT libraries
        kicad_settings_folder = Path.home() / ".config" / "kicad"

        def add_wut_libs_to_kicad(kicad_table_file_name: str, library_file_suffix: str):
            table_paths = list(kicad_settings_folder.rglob(kicad_table_file_name))
            assert (
                len(table_paths) == 1
            ), f"Couldn't find table called {kicad_table_file_name}"
            table_path = table_paths[0]
            print(f"Found table at {table_path.absolute()}")

            wut_library_names = [
                x.stem for x in self.wut_library_folder.glob(f"*.{library_file_suffix}")
            ]

            # Deal with symbols first
            with open(table_path, "r") as file:
                contents = file.readlines()

            contents = (
                contents[:-1]
                + [
                    f'\t(lib (name "{x}")(type "KiCad")(uri "${{WUT_LIBRARIES}}/{x}.{library_file_suffix}")(options "")(descr ""))\n'
                    for x in wut_library_names
                ]
                + [")\n"]
            )

            with open(table_path, "w") as file:
                file.writelines(contents)

        add_wut_libs_to_kicad("sym-lib-table", "kicad_sym")
        add_wut_libs_to_kicad("fp-lib-table", "pretty")

        # Copy non-standard colour settings over too
        colour_folders = list(kicad_settings_folder.rglob("sym-lib-table"))
        assert len(colour_folders) == 1
        colour_folder = colour_folders[0].parent / "colors"
        colour_folder.mkdir(parents=True, exist_ok=True)
        shutil.copy2(
            Path(__file__).parent / "export_colours.json", colour_folder / "user.json"
        )

    def discover_kicad_project(
        self,
        top_level_folder: Path,
    ) -> None:
        results = list(top_level_folder.rglob("*.kicad_pro"))
        for x in results:
            print(f'Found project "{x.stem}" in {x.parent.absolute()}')

        assert (
            len(results) > 0
        ), f"No projects founds in {top_level_folder.absolute()} or its subdirectories"
        self.project_path = results[0]

    def create_schematic_pdf(self):
        temp_schematic_path = self.output_folder / "temp_schematic.pdf"
        self.run_command(
            [
                "kicad-cli",
                "sch",
                "export",
                "pdf",
                self.project_path.with_suffix(".kicad_sch").absolute(),
                "-o",
                temp_schematic_path.absolute(),
                "--no-background-color",
            ]
        )

        writer = pypdf.PdfWriter(clone_from=temp_schematic_path.absolute())

        if self.git_info.commit_tag is None:
            # Load watermark pdfs
            watermark_a3 = pypdf.PdfReader(
                (Path(__file__).parent / "draft_watermark_a3.pdf").absolute()
            ).pages[0]

            watermark_a4 = pypdf.PdfReader(
                (Path(__file__).parent / "draft_watermark_a4.pdf").absolute()
            ).pages[0]

            for page in writer.pages:
                width = page.mediabox.width
                # I have no idea where these numbers come from
                # This was found by printing values from pages
                # of known sizes
                if width == 1190.52:
                    page.merge_page(watermark_a3, over=False)
                elif width == 841.896:
                    page.merge_page(watermark_a4, over=False)
                else:
                    raise NotImplementedError(width)

        writer.write(self.output_folder / f"{self.project_path.stem}.pdf")
        temp_schematic_path.unlink()

    def create_board_images(self):
        for side in ["front", "back"]:
            commands = ["kicad-cli", "pcb", "render", "--quality", "high"]
            commands += [
                "--side",
                f"{'top' if side == 'front' else 'bottom'}",
                "-o",
                (
                    self.output_folder / f"{self.project_path.stem}-{side}.png"
                ).absolute(),
                self.project_path.with_suffix(".kicad_pcb").absolute(),
            ]
            self.run_command(commands)

    def create_kicad_source(self):
        with ZipFile(
            self.output_folder / f"{self.project_path.stem}.zip", "w"
        ) as zip_file:
            for x in (self.project_path.parent).glob("*"):
                if ".git" not in str(x):
                    zip_file.write(x, x.name)

    def create_step_file(self):
        self.run_command(
            [
                "kicad-cli",
                "pcb",
                "export",
                "step",
                "--subst-models",
                self.project_path.with_suffix(".kicad_pcb").absolute(),
                "-o",
                (self.output_folder / f"{self.project_path.stem}.step").absolute(),
            ]
        )

    def create_gerbers(self):
        try:
            # Setup temporary folder
            tmp_folder = Path() / ".." / f"gerber-{self.project_path.stem}-tmp"
            tmp_folder.mkdir()
            # Generate drill files
            self.run_command(
                [
                    "kicad-cli",
                    "pcb",
                    "export",
                    "drill",
                    "--excellon-separate-th",
                    "-o",
                    f"{tmp_folder.absolute()}/",
                    self.project_path.with_suffix(".kicad_pcb").absolute(),
                ]
            )

            # Generate Gerbers
            self.run_command(
                [
                    "kicad-cli",
                    "pcb",
                    "export",
                    "gerbers",
                    "--no-netlist",
                    "-o",
                    str(tmp_folder.absolute())
                    + "/",  # This is awful but crashes unless ends with "/"
                    self.project_path.with_suffix(".kicad_pcb").absolute(),
                ]
            )

            # Remove unnecessary files
            banned_suffixes = ["gta", "gba", "gbr", "gbrjob"]
            for x in tmp_folder.glob("*"):
                if x.name.split(".")[-1] in banned_suffixes:
                    x.unlink()

            # Zip it
            with ZipFile(
                self.output_folder / f"{self.project_path.stem}-gerbers.zip", "w"
            ) as zip_file:
                for x in tmp_folder.glob("*"):
                    zip_file.write(x, x.name)

        finally:
            pass
            # Erase tmp folder
            for x in tmp_folder.glob("*"):
                x.unlink()
            tmp_folder.rmdir()

    def create_netlist(self):
        self.run_command(
            [
                "kicad-cli",
                "sch",
                "export",
                "netlist",
                "--output",
                self.project_path.with_suffix(".net").absolute(),
                self.project_path.with_suffix(".kicad_sch").absolute(),
            ],
            include_extra_kicad_args=False,  # For some reason, doesn't support -D
        )

    def create_ibom(self):
        self.create_netlist()

        os.environ["INTERACTIVE_HTML_BOM_NO_DISPLAY"] = "1"

        self.run_command(
            [
                "python3",
                "../ibom/InteractiveHtmlBom/generate_interactive_bom.py",
                "--dark-mode",
                "--highlight-pin1",
                "all",
                "--no-browser",
                "--blacklist",
                "JP*,LAYOUT*",
                "--extra-fields",
                "Manufacturer,MPN",
                "--show-fields",
                "Manufacturer,MPN,Value",
                "--group-fields",
                "MPN",
                "--dest-dir",
                self.output_folder.absolute(),
                "--dnp-field",
                "kicad_dnp",
                "--name-format",
                self.project_path.stem,
                "--netlist-file",
                self.project_path.with_suffix(".net").absolute(),
                self.project_path.with_suffix(".kicad_pcb").absolute(),
            ],
            include_extra_kicad_args=False,
        )

    def create_webpage(self):
        # repo = git.Repo(top_level_folder)

        # url = repo.remotes.origin.url
        # if url.endswith(".git"):
        #     url = url[:-4]

        # repo_name = repo.remotes.origin.url.split("/")[-1]
        # if repo_name.endswith(".git"):
        #     repo_name = repo_name[:-4]
        # # Replace all underscores and hypens with spaces
        # repo_name = re.sub(r"[_-]", " ", repo_name)
        # # Capitalise each word
        # repo_name = " ".join([x.capitalize() for x in repo_name.split()])

        # resources = []

        # Below is an expansion of kikit.boardpage with the broken command (which calls pcbdraw)
        # commented out as pcbdraw does not currently work and the output isn't used anyway

        self._component_availability_searcher.generate_report(
            self.project_path.with_suffix(".kicad_sch")
        )

        template = readTemplate((Path(__file__).parent / "webpage_template").absolute())
        template.addDescriptionFile(
            str((self.project_path.parent / "README.md").absolute())
        )
        # template.setRepository(url)
        template.setName(self.project_path.stem)
        comment = markdown2.markdown_path(
            str((self.output_folder / f"availability_report.md").absolute()),
            extras=["fenced-code-blocks", "tables"],
        )

        template.addBoard(
            self.project_path.stem,
            comment,
            self.project_path.with_suffix(".kicad_pcb").absolute(),
        )

        template._copyResources(self.output_folder)
        # self._renderBoards(outputDirectory)  # BROKEN LINE

        # Render page
        with open(
            os.path.join(template.directory, "index.html"), encoding="utf-8"
        ) as templateFile:
            html_template = pybars.Compiler().compile(templateFile.read())
            gitRev = template.gitRevision()
            content = html_template(
                {
                    "repo": template.repository,
                    "gitRev": gitRev,
                    "gitRevShort": gitRev[:8] if gitRev else None,
                    "datetime": template.currentDateTime(),
                    "name": "TEST",
                    "boards": template.boards,
                    "description": template.description,
                }
            )
            # Fix escaping of < and > symbols in pybars
            content = re.sub("&lt;", "<", content)
            content = re.sub("&gt;", ">", content)

            # Write out file
            with open(
                os.path.join(self.output_folder, "index.html"), "w", encoding="utf-8"
            ) as outFile:
                outFile.write(content)


if __name__ == "__main__":
    debug = False
    if debug:
        top_level_folder = Path("..") / "p0001-001_test-board"
        release_folder = Path("temp")
        wut_library_folder = Path("..") / "wut-libraries"
        mouser_api_key = None
        farnell_api_key = None
    else:
        top_level_folder = Path(sys.argv[1])
        release_folder = Path(sys.argv[2])
        wut_library_folder = Path(sys.argv[3])
        try:
            mouser_api_key = sys.argv[4]
        except IndexError:
            mouser_api_key = None
        try:
            farnell_api_key = sys.argv[5]
        except IndexError:
            farnell_api_key = None

    x = KicadArtefactsGenerator(
        top_level_folder,
        release_folder,
        wut_library_folder,
        mouser_api_key,
        farnell_api_key,
    )
    x.create_schematic_pdf()
    x.create_board_images()
    x.create_kicad_source()
    x.create_step_file()
    x.create_ibom()
    x.create_webpage()
