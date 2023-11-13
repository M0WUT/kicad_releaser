import sys
import pathlib
import subprocess
import typing
import os
import pypdf
import git


def discover_kicad_projects(project_folder: pathlib.Path) -> str:
    kicad_projects = [x for x in project_folder.iterdir() if x.suffix == ".kicad_pro"]
    assert len(kicad_projects) == 1
    project_name = kicad_projects[0].stem
    print(f"Kicad project found: {project_name}")
    return project_name


def generate_schematic_pdf(schematic: pathlib.Path, output_file: pathlib.Path):
    temp_schematic_path = pathlib.Path(__file__).parent / "temp_schematic.pdf"
    commands = [
        "kicad-cli",
        "sch",
        "export",
        "pdf",
        schematic.absolute(),
        "-o",
        temp_schematic_path.absolute(),
        "--no-background-color",
    ]

    result = subprocess.run(
        commands,
        capture_output=True,
    )
    result.check_returncode()

    # Check if draft release and add watermarks if so
    repo = git.Repo(pathlib.Path(schematic.parent))
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

    writer.write(output_file.absolute())


def generate_board_images(pcb_file: pathlib.Path, output_folder: pathlib.Path):
    for side in ["front", "back"]:
        commands = [
            "pcbdraw",
            "render",
            pcb_file.absolute(),
            "--side",
            f"{side}",
            "--transparent",
            (output_folder / f"board_{side}.png").absolute(),
        ]

        print(commands)

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
    repo = git.Repo(project_folder)
    url = repo.remotes.origin.url[:-4]  # Remove .git
    print(url)
    commands = [
        "kikit",
        "present",
        "boardpage",
        "-d",
        (project_folder / "README.md").absolute(),
        "--name",
        f"{project_name}",
        "-b",
        f"{project_name}",
        "it's alive",
        (project_folder / f"{project_name}.kicad_pcb").absolute(),
        "--template",
        (pathlib.Path(__file__).parent / "template").absolute(),
        "--repository",
        url,
        release_folder.absolute(),
    ]

    result = subprocess.run(
        commands,
        # capture_output=True,
    )
    result.check_returncode()


def create_kicad_config():
    config_path = pathlib.Path.home() / ".config" / "kicad" / "7.0"
    config_path.mkdir(parents=True, exist_ok=True)
    commands = ["cp", "-r", "kicad_releaser/kicad_settings/*", config_path.absolute()]

    result = subprocess.run(
        commands,
        # capture_output=True,
    )
    result.check_returncode()


def create_kicad_source(
    project_folder: pathlib.Path,
    project_name: pathlib.Path,
    release_folder: pathlib.Path,
):
    repo = git.Repo(project_folder)
    commands = [
        "zip",
        (release_folder / f"{project_name}_{repo.head.commit.hexsha}.zip").absolute(),
    ]

    commands += [x for x in (project_folder).glob("*") if not ".git" in str(x)]

    result = subprocess.run(
        commands,
        # capture_output=True,
    )
    result.check_returncode()


def main(project_folder: pathlib.Path, release_folder: pathlib.Path):
    print(
        f"Releasing project in {project_folder.absolute()} into {release_folder.absolute()}"
    )
    # create_kicad_config()
    project_name = discover_kicad_projects(project_folder)
    generate_schematic_pdf(
        project_folder / f"{project_name}.kicad_sch", release_folder / "schematic.pdf"
    )
    create_kicad_source(project_folder, project_name, release_folder)
    # generate_board_images(
    #     (project_folder) / f"{project_name}.kicad_pcb", release_folder
    # )
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
