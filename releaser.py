import sys
import pathlib
import subprocess
import typing
import os


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


def generate_board_images(pcb_file: pathlib.Path, output_folder: pathlib.Path):
    for side in ["front", "back"]:
        commands = [
            "pcbdraw",
            "render",
            pcb_file.absolute(),
            "--side",
            f"{side}",
            "--transparent",
            "--renderer",
            "raytrace",
            (output_folder / f"board_{side}.png").absolute(),
        ]

        system_env = os.environ.copy()
        system_env["WUT_LIBRARIES"] = pathlib.Path("wut-libraries").absolute()

        result = subprocess.run(
            commands,
            env=system_env,
            # capture_output=True,
        )
        result.check_returncode()


def generate_webpage(
    project_name: str, project_folder: pathlib.Path, release_folder: pathlib.Path
):
    commands = [
        "kikit",
        "present",
        "boardpage",
        "-d",
        (project_folder / "README.md").absolute(),
        "--name",
        f"{project_name}",
        "-b",
        "bob name",
        "it's alive",
        (project_folder / f"{project_name}.kicad_pcb").absolute(),
        "--template",
        "kicad_releaser/template",
        release_folder.absolute(),
    ]

    result = subprocess.run(
        commands,
        # capture_output=True,
    )
    result.check_returncode()


def create_kicad_config():
    config_path = pathlib.Path("~") / ".config" / "kicad" / "7.0"
    config_path.mkdir(parents=True, exist_ok=True)
    commands = ["cp", "-r", "kicad_releaser/kicad_settings/*", config_path.absolute()]

    result = subprocess.run(
        commands,
        # capture_output=True,
    )
    result.check_returncode()


def main(project_folder: pathlib.Path, release_folder: pathlib.Path):
    print(
        f"Releasing project in {project_folder.absolute()} into {release_folder.absolute()}"
    )
    create_kicad_config()
    project_name = discover_kicad_projects(project_folder)
    # generate_schematic_pdf(
    #     project_folder / f"{project_name}.kicad_sch", release_folder / "schematic.pdf"
    # )
    generate_board_images(
        (project_folder) / f"{project_name}.kicad_pcb", release_folder
    )
    generate_webpage(
        project_name=project_name,
        project_folder=project_folder,
        release_folder=release_folder,
    )


if __name__ == "__main__":
    main(
        project_folder=pathlib.Path(sys.argv[1]),
        release_folder=pathlib.Path(sys.argv[2]),
    )
