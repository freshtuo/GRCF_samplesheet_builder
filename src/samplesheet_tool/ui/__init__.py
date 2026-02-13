# __init__.py
#

from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("samplesheet-tool")
except PackageNotFoundError:
    __version__ = "dev"

