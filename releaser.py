import sys
import pathlib
import subprocess
import typing


def discover_kicad_projects(project_folder: pathlib.Path) -> str:
    kicad_projects = [x for x in project_folder.iterdir() if x.suffix == ".kicad_pro"]
    assert len(kicad_projects) == 1
    project_name = kicad_projects[0].stem
    print(f"Kicad project found: {project_name}")
    return project_name


def generate_schematic_pdf(
    schematic: pathlib.Path, output_file: typing.Optional[pathlib.Path] = None
):
    commands = [
        "kicad-cli",
        "sch",
        "export",
        "pdf",
        schematic.absolute(),
    ]

    if output_file:
        commands += [
            "-o",
            output_file.absolute(),
        ]

    result = subprocess.run(
        commands,
        capture_output=True,
    )
    result.check_returncode()


def generate_webpage(
    project_name: str, pcb_path: pathlib.Path, release_folder: pathlib.Path
):
    (release_folder / "web").mkdir(exist_ok=True)
    commands = [
        "kikit",
        "present",
        "boardpage",
        "-d",
        "README.md",
        "--name",
        f"{project_name}",
        "-b",
        "bob name",
        "it's alive",
        pcb_path.absolute(),
        "--template",
        "template",
        (release_folder / "web").absolute(),
    ]

    result = subprocess.run(
        commands,
        # capture_output=True,
    )
    result.check_returncode()


def main(project_folder: pathlib.Path, release_folder: pathlib.Path):
    print(
        f"Releasing project in {project_folder.absolute()} into {release_folder.absolute()}"
    )

    project_name = discover_kicad_projects(project_folder)
    # generate_schematic_pdf(
    #     project_folder / f"{project_name}.kicad_sch", release_folder / "schematic.pdf"
    # )
    generate_webpage(
        project_name=project_name,
        pcb_path=project_folder / f"{project_name}.kicad_pcb",
        release_folder=release_folder,
    )


if __name__ == "__main__":
    main(
        project_folder=pathlib.Path(sys.argv[1]),
        release_folder=pathlib.Path(sys.argv[2]),
    )
