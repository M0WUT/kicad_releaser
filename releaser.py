import os
import pathlib
import subprocess
import sys
from mousearch.mousearch import Mousearch
import markdown2
import pybars
from kikit.present import readTemplate
from typing import Optional, Tuple
import re

import git
import pypdf
from zipfile import ZipFile


def run_command(commands: list[str | pathlib.Path]):
    subprocess.check_call(
        commands,
        # capture_output=True,
    )


def discover_kicad_projects(
    top_level_folder: pathlib.Path,
) -> list[pathlib.Path]:
    results = list(top_level_folder.rglob("*.kicad_pro"))
    for x in results:
        print(f'Found project "{x.stem}" in {x.parent.absolute()}')

    assert (
        len(results) > 0
    ), f"No projects founds in {top_level_folder.absolute()} or its subdirectories"
    return results


def create_schematic_pdf(kicad_project: pathlib.Path, output_folder: pathlib.Path):
    temp_schematic_path = pathlib.Path(__file__).parent / "temp_schematic.pdf"
    run_command(
        [
            "kicad-cli",
            "sch",
            "export",
            "pdf",
            kicad_project.with_suffix(".kicad_sch").absolute(),
            "-o",
            temp_schematic_path.absolute(),
            "--no-background-color",
        ]
    )

    # Check if draft release and add watermarks if so
    repo = git.Repo(pathlib.Path("."))
    last_commit = repo.head.commit

    writer = pypdf.PdfWriter(clone_from=temp_schematic_path.absolute())

    if "RELEASE:" not in last_commit.message:
        # Load watermark pdfs
        watermark_a3 = pypdf.PdfReader(
            (pathlib.Path(__file__).parent / "draft_watermark_a3.pdf").absolute()
        ).pages[0]

        watermark_a4 = pypdf.PdfReader(
            (pathlib.Path(__file__).parent / "draft_watermark_a4.pdf").absolute()
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

    writer.write(output_folder / f"{kicad_project.stem}.pdf")


def create_board_images(
    kicad_project: pathlib.Path, output_folder: pathlib.Path, full_release: bool = True
):
    for side in ["front", "back"]:
        commands = ["kicad-cli", "pcb", "render"]
        if full_release:
            commands += ["--quality", "high"]
        commands += [
            "--side",
            f"{'top' if side == 'front' else 'bottom'}",
            "-o",
            (output_folder / f"{kicad_project.stem}-{side}.png").absolute(),
            kicad_project.with_suffix(".kicad_pcb").absolute(),
        ]
        run_command(commands)


def create_webpage(
    top_level_folder: pathlib.Path,
    output_folder: pathlib.Path,
    board_list: list[Tuple[str, str, str]],
    resources: Optional[list[pathlib.Path]],
):
    repo = git.Repo(top_level_folder)

    url = repo.remotes.origin.url
    if url.endswith(".git"):
        url = url[:-4]

    repo_name = repo.remotes.origin.url.split("/")[-1]
    if repo_name.endswith(".git"):
        repo_name = repo_name[:-4]
    # Replace all underscores and hypens with spaces
    repo_name = re.sub(r"[_-]", " ", repo_name)
    # Capitalise each word
    repo_name = " ".join([x.capitalize() for x in repo_name.split()])

    resources = []

    # Below is an expansion of kikit.boardpage with the broken command (which calls pcbdraw)
    # commented out as pcbdraw does not currently work and the output isn't used anyway
    output_folder.mkdir(parents=True, exist_ok=True)
    template = readTemplate((pathlib.Path(__file__).parent / "template").absolute())
    template.addDescriptionFile(str((top_level_folder.parent / "README.md").absolute()))
    template.setRepository(url)
    template.setName(top_level_folder.absolute().stem)
    for r in resources:
        template.addResource(r)
    for name, comment, file in board_list:
        template.addBoard(name, comment, file)

    template._copyResources(output_folder)
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
                "gitRevShort": gitRev[:7] if gitRev else None,
                "datetime": template.currentDateTime(),
                "name": repo_name,
                "boards": template.boards,
                "description": template.description,
            }
        )
        # Fix escaping of < and > symbols in pybars
        content = re.sub("&lt;", "<", content)
        content = re.sub("&gt;", ">", content)

        # Write out file
        with open(
            os.path.join(output_folder, "index.html"), "w", encoding="utf-8"
        ) as outFile:
            outFile.write(content)


def create_kicad_source(kicad_project: pathlib.Path, output_folder: pathlib.Path):
        with ZipFile(output_folder / f"{kicad_project.stem}.zip", 'w') as zip_file:
             for x in (kicad_project.parent).glob("*"):
                if ".git" not in str(x):
                    zip_file.write(x, x.name)


def create_step_file(kicad_project: pathlib.Path, output_folder: pathlib.Path):
    run_command(
        [
            "kicad-cli",
            "pcb",
            "export",
            "step",
            "--subst-models",
            kicad_project.with_suffix(".kicad_pcb").absolute(),
            "-o",
            (output_folder / f"{kicad_project.stem}.step").absolute(),
        ]
    )


def create_gerbers(kicad_project: pathlib.Path, output_folder: pathlib.Path):
    try:
        # Setup temporary folder
        tmp_folder = pathlib.Path() / ".." / f"gerber-{kicad_project.stem}-tmp"
        tmp_folder.mkdir()
        # Generate drill files
        run_command(
            [
                "kicad-cli",
                "pcb",
                "export",
                "drill",
                "--excellon-separate-th",
                "-o",
                str(tmp_folder.absolute())
                + "/",  # This is awful but crashes unless ends with "/"
                kicad_project.with_suffix(".kicad_pcb").absolute(),
            ]
        )

        # Generate Gerbers
        run_command(
            [
                "kicad-cli",
                "pcb",
                "export",
                "gerbers",
                "--no-netlist",
                "-o",
                str(tmp_folder.absolute())
                + "/",  # This is awful but crashes unless ends with "/"
                kicad_project.with_suffix(".kicad_pcb").absolute(),
            ]
        )

        # Remove unnecessary files
        banned_suffixes = ["gta", "gba", "gbr", "gbrjob"]
        for x in tmp_folder.glob("*"):
            if x.name.split(".")[-1] in banned_suffixes:
                x.unlink()

        # Zip it
        with ZipFile(output_folder / f"{kicad_project.stem}-gerbers.zip", 'w') as zip_file:
            for x in tmp_folder.glob("*"):
                zip_file.write(x, x.name)


    finally:
        pass
        # Erase tmp folder
        for x in tmp_folder.glob("*"):
            x.unlink()
        tmp_folder.rmdir()


def create_netlist(kicad_project: pathlib.Path, output_folder: pathlib.Path):
    run_command(
        [
            "kicad-cli",
            "sch",
            "export",
            "netlist",
            "--output",
            kicad_project.with_suffix(".net").absolute(),
            kicad_project.with_suffix(".kicad_sch").absolute(),
        ]
    )


def create_ibom(kicad_project: pathlib.Path, output_folder: pathlib.Path):
    create_netlist(kicad_project, output_folder)
    run_command(
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
            output_folder.absolute(),
            "--name-format",
            kicad_project.stem,
            "--netlist-file",
            kicad_project.with_suffix(".net").absolute(),
            kicad_project.with_suffix(".kicad_pcb").absolute(),
        ]
    )


def main(
    top_level_folder: pathlib.Path,
    release_folder: pathlib.Path,
    mouser_key: Optional[str] = None,
    farnell_key: Optional[str] = None,
):
    FULL_RELEASE = True
    print(
        f"Releasing projects in {top_level_folder.absolute()} into {release_folder.absolute()}"
    )
    project_paths = discover_kicad_projects(top_level_folder)
    if mouser_key and farnell_key:
        bom_checker = Mousearch(mouser_key=mouser_key, farnell_key=farnell_key)
    else:
        bom_checker = None

    boards = []
    for x in project_paths:
        # Do this first in case of accidential file creation in the repo
        create_kicad_source(x, release_folder)

        create_gerbers(x, release_folder)
        if FULL_RELEASE:
            create_schematic_pdf(x, release_folder)
            
            create_board_images(x, release_folder, full_release=FULL_RELEASE)
            create_step_file(x, release_folder)
            create_ibom(x, release_folder)
        if bom_checker:
            bom_checker.run(
                x.with_suffix(".kicad_sch").absolute(),
                release_folder / f"{x.stem}-bom.md",
                mouser_basket=release_folder / f"{x.stem}-mouser-bom.csv",
                farnell_basket=release_folder / f"{x.stem}-farnell-bom.csv",
                full_release=FULL_RELEASE
            )
            comment = markdown2.markdown_path(
                (release_folder / f"{x.stem}-bom.md").absolute(),
                extras=["fenced-code-blocks", "tables"],
            )
        else:
            comment = ""
        boards.append(
            (
                x.stem,
                comment,
                x.with_suffix(".kicad_pcb").absolute(),
            )
        )

    create_webpage(
        top_level_folder=top_level_folder,
        output_folder=release_folder,
        board_list=boards,
        resources=[],
    )


if __name__ == "__main__":
    main(
        top_level_folder=pathlib.Path(sys.argv[1]),
        release_folder=pathlib.Path(sys.argv[2]),
        mouser_key=sys.argv[3],
        farnell_key=sys.argv[4],
    )
