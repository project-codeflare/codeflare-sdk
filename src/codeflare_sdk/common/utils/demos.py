import pathlib
import shutil

package_dir = pathlib.Path(__file__).parent.parent.parent.resolve()
demo_dir = f"{package_dir}/demo-notebooks"


def copy_demo_nbs(dir: str = "./demo-notebooks", overwrite: bool = False):
    """
    Copy the demo notebooks from the package to the current working directory

    overwrite=True will overwrite any files that exactly match files written by copy_demo_nbs in the target directory.
    Any files that exist in the directory that don't match these values will remain untouched.

    Args:
        dir (str):
            The directory to copy the demo notebooks to. Defaults to "./demo-notebooks".
        overwrite (bool):
            Whether to overwrite files in the directory if it already exists. Defaults to False.

    Raises:
        FileExistsError:
            If the directory already exists.
    """
    # does dir exist already?
    if overwrite is False and pathlib.Path(dir).exists():
        raise FileExistsError(
            f"Directory {dir} already exists. Please remove it or provide a different location."
        )

    shutil.copytree(demo_dir, dir, dirs_exist_ok=True)
