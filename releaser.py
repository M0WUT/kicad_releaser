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


def generate_bom_report(kicad_project: pathlib.Path, output_folder: pathlib.Path):
    x = Mousearch()


def generate_schematic_pdf(kicad_project: pathlib.Path, output_folder: pathlib.Path):
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


def generate_board_images(kicad_project: pathlib.Path, output_folder: pathlib.Path):
    for side in ["front", "back"]:
        run_command(
            [
                "kicad-cli",
                "pcb",
                "render",
                "--side",
                f"{'top' if side == 'front' else 'bottom'}",
                "--background",
                "transparent",
                "-o",
                (output_folder / f"{side}_render.png").absolute(),
                kicad_project.with_suffix(".kicad_pcb").absolute(),
            ],
        )


def generate_webpage(
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
    repo_name = re.sub(r'[_-]', ' ', repo_name)
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
    with open(os.path.join(template.directory, "index.html"), encoding="utf-8") as templateFile:
        html_template = pybars.Compiler().compile(templateFile.read())
        gitRev = template.gitRevision()
        content = html_template({
            "repo": template.repository,
            "gitRev": gitRev,
            "gitRevShort": gitRev[:7] if gitRev else None,
            "datetime": template.currentDateTime(),
            "name": repo_name,
            "boards": template.boards,
            "description": template.description
        })
        # Fix escaping of < and > symbols in pybars
        content = re.sub('&lt;', '<', content)
        content = re.sub('&gt;', '>', content)

        # Write out file
        with open(os.path.join(output_folder, "index.html"),"w", encoding="utf-8") as outFile:
            outFile.write(content)

def create_kicad_source(kicad_project: pathlib.Path, output_folder: pathlib.Path):
    commands = [
        "zip",
        (output_folder / f"{kicad_project.stem}.zip").absolute(),
    ]

    commands += [x for x in (kicad_project.parent).glob("*") if ".git" not in str(x)]

    run_command(commands)


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
        generate_schematic_pdf(x, release_folder)
        create_kicad_source(x, release_folder)
        generate_board_images(x, release_folder)
        # create_step_file(x, release_folder)
        create_ibom(x, release_folder)
        if bom_checker:
            bom_checker.run(
                x.with_suffix(".kicad_sch").absolute(), release_folder / f"{x.stem}-bom.md",
                mouser_basket=release_folder / f"{x.stem}-mouser-bom.csv",
                farnell_basket=release_folder / f"{x.stem}-farnell-bom.csv"
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

    generate_webpage(
        top_level_folder=top_level_folder,      
        output_folder=release_folder,
        board_list=boards,
        resources=[]
    )


if __name__ == "__main__":
    main(
        top_level_folder=pathlib.Path(sys.argv[1]),
        release_folder=pathlib.Path(sys.argv[2]),
        mouser_key=sys.argv[3],
        farnell_key=sys.argv[4],
    )
