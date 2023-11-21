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


def discover_kicad_projects(project_folder: pathlib.Path) -> str:
    kicad_projects = [x for x in project_folder.iterdir() if x.suffix == ".kicad_pro"]
    assert len(kicad_projects) == 1
    project_name = kicad_projects[0].stem
    print(f"Kicad project found: {project_name}")
    return project_name


def generate_schematic_pdf(schematic: pathlib.Path, output_file: pathlib.Path):
    temp_schematic_path = pathlib.Path(__file__).parent / "temp_schematic.pdf"
    run_command(
        [
            "kicad-cli",
            "sch",
            "export",
            "pdf",
            schematic.absolute(),
            "-o",
            temp_schematic_path.absolute(),
            "--no-background-color",
        ]
    )

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
    run_command(
        [
            "pcbnew_do",
            "3d_view",
            "-z",
            "6",
            "--ray_tracing",
            "-o",
            "board_front.png",
            pcb_file.absolute(),
            output_folder.absolute()
        ],
        use_wut_libraries=True,
    )


def generate_webpage(
    project_name: str, project_folder: pathlib.Path, release_folder: pathlib.Path
):
    repo = git.Repo(project_folder)
    url = repo.remotes.origin.url[:-4]  # Remove .git
    print(url)

    run_command(
        [
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
    )


def create_kicad_config():
    config_path = pathlib.Path.home() / ".config" / "kicad" / "7.0"
    config_path.mkdir(parents=True, exist_ok=True)
    run_command(["cp", "-r", "kicad_releaser/kicad_settings/*", config_path.absolute()])


def create_kicad_source(
    project_folder: pathlib.Path,
    project_name: str,
    release_folder: pathlib.Path,
):
    repo = git.Repo(project_folder)

    commands = [
        "zip",
        (
            release_folder / f"{project_name}_{repo.head.commit.hexsha[:7]}.zip"
        ).absolute(),
    ]

    commands += [x for x in (project_folder).glob("*") if not ".git" in str(x)]

    run_command(commands)


def create_step_file(
    pcb_file: pathlib.Path, project_name: str, output_folder: pathlib.Path
):
    run_command(
        [
            "kicad-cli",
            "pcb",
            "export",
            "step",
            "--subst-models",
            pcb_file.absolute(),
            "-o",
            (output_folder / f"{project_name}.step").absolute(),
        ]
    )


def create_netlist(project_folder: pathlib.Path, project_name: str):
    run_command(
        [
            "kicad-cli",
            "sch",
            "export",
            "netlist",
            "--output",
            (project_folder / f"{project_name}.net").absolute(),
            (project_folder / f"{project_name}.kicad_sch").absolute(),
        ]
    )


def create_ibom(
    project_folder: pathlib.Path, project_name: str, output_folder: pathlib.Path
):
    create_netlist(project_folder, project_name)
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
            f"{project_name}",
            "--netlist-file",
            (project_folder / f"{project_name}.net").absolute(),
            (project_folder / f"{project_name}.kicad_pcb").absolute(),
        ]
    )
def load_wut_libraries_path():
    LIBRARIES_PATH = pathlib.Path("..") / "wut-libraries"
    CONFIG_SETTINGS_FILE_LOCATION = pathlib.Path("~") / ".config" / "kicad" / "7.0" / "kicad_common.json"
    with open(CONFIG_SETTINGS_FILE_LOCATION, 'r') as file:
        filedata = file.read()

    filedata = filedata.replace("<PATH_TO_WUT_LIBRARIES>", str(LIBRARIES_PATH.absolute()))

    with open(CONFIG_SETTINGS_FILE_LOCATION, 'w') as file:
        file.write(filedata)



def main(project_folder: pathlib.Path, release_folder: pathlib.Path):
    print(
        f"Releasing project in {project_folder.absolute()} into {release_folder.absolute()}"
    )
    # create_kicad_config()
    project_name = discover_kicad_projects(project_folder)
    load_wut_libraries_path()
    generate_schematic_pdf(
        project_folder / f"{project_name}.kicad_sch", release_folder / "schematic.pdf"
    )
    create_kicad_source(project_folder, project_name, release_folder)
    generate_board_images(
        (project_folder) / f"{project_name}.kicad_pcb", release_folder
    )
    create_step_file(
        (project_folder) / f"{project_name}.kicad_pcb", project_name, release_folder
    )
    create_ibom(project_folder, project_name, release_folder)
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
