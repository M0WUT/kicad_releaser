import sys
import pathlib
import subprocess


def main(project_folder: pathlib.PurePath, release_folder: pathlib.PurePath):
    print(
        f"Releasing project in {project_folder.absolute()} into {release_folder.absolute()}"
    )


if __name__ == "__main__":
    main(
        project_folder=pathlib.PurePath(sys.argv[1]),
        release_folder=pathlib.PurePath(sys.argv[2]),
    )
