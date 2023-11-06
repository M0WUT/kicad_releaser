import sys
import pathlib
import subprocess


def main(project_folder: str, release_folder: str):
    print(f"Releasing project in {project_folder} into {release_folder}")


if __name__ == "__main__":
    main(
        project_folder=pathlib.PurePath(sys.argv[1]),
        release_folder=pathlib.PurePath(sys.argv[2]),
    )
