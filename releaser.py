import sys
import pathlib
import subprocess
import typing
import os
import pypdf
import git


def run_command(commands: list[str]):
    result = subprocess.run(
        commands,
        # capture_output=True,
    )
    result.check_returncode()


def discover_kicad_projects(top_level_folder: pathlib.Path) -> str:
    results = list(top_level_folder.rglob("*.kicad_pro"))
    for x in results:
        print(f'Found project "{x.stem}" in {x.parent.absolute()}')

    assert (
        len(results) > 0
    ), f"No projects founds in {top_level_folder.absolute()} or its subdirectories"
    return results


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
            # I have no idea where these numbers come from - found by printing values
            # from pages of known sizes
            if width == 1190.52:
                page.merge_page(watermark_a3, over=False)
            elif width == 841.896:
                page.merge_page(watermark_a4, over=False)
            else:
                raise NotImplementedError(width)

    writer.write(output_folder / f"{kicad_project.stem}.pdf")


def generate_board_images(kicad_project: pathlib.Path, output_folder: pathlib.Path):
    run_command(
        [
            "pcbnew_do",
            "3d_view",
            "-z",
            "4",
            "--ray_tracing",
            "-o",
            f"{kicad_project.stem}.png",
            kicad_project.with_suffix(".kicad_pcb").absolute(),
            output_folder.absolute(),
        ],
    )


def generate_webpage(
    top_level_folder: pathlib.Path,
    project_paths: list[pathlib.Path],
    output_folder: pathlib.Path,
):
    repo = git.Repo(top_level_folder)
    url = repo.remotes.origin.url[:-4]  # Remove .git
    print(url)

    commands = [
        "kikit",
        "present",
        "boardpage",
        "-d",
        (top_level_folder.parent / "README.md").absolute(),
        "--name",
        top_level_folder.stem,
    ]
    for x in project_paths:
        commands += \
            ["-b", x.stem, "It's alive", x.with_suffix(".kicad_pcb").absolute()]
        
    commands += \
        [
            "--template",
            (pathlib.Path(__file__).parent / "template").absolute(),
            "--repository",
            url,
            output_folder.absolute(),
        ]
    print(commands)

    run_command(commands)


def create_kicad_source(kicad_project: pathlib.Path, output_folder: pathlib.Path):
    commands = [
        "zip",
        (
            output_folder / f"{kicad_project.stem}.zip"
        ).absolute(),
    ]

    commands += [x for x in (kicad_project.parent).glob("*") if not ".git" in str(x)]

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
            "JP*,LAYOUT*,H*",
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


def main(top_level_folder: pathlib.Path, release_folder: pathlib.Path):
    print(
        f"Releasing projects in {top_level_folder.absolute()} into {release_folder.absolute()}"
    )
    project_paths = discover_kicad_projects(top_level_folder)
    for x in project_paths:
        generate_schematic_pdf(
            x, release_folder
        )
        create_kicad_source(x, release_folder)
        generate_board_images(x, release_folder)
        create_step_file(x, release_folder)
        create_ibom(x, release_folder)
    generate_webpage(
        top_level_folder,
        project_paths,
        release_folder,
    )


if __name__ == "__main__":
    main(
        top_level_folder=pathlib.Path(sys.argv[1]),
        release_folder=pathlib.Path(sys.argv[2]),
    )
