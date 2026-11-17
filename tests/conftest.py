"""Make the scripts importable as modules: they are run as files and import each other by name."""
import pathlib, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / 'scripts'))
