import argparse
import logging
import typing

from pydependence._cli import pydeps
from pydependence._core.requirements_map import NoConfiguredRequirementMappingError

LOGGER = logging.getLogger(__name__)

# ========================================================================= #
# CLI                                                                       #
# ========================================================================= #


if typing.TYPE_CHECKING:

    class PyDepsCliArgsProto(typing.Protocol):
        config: str


def _parse_args() -> "PyDepsCliArgsProto":
    """
    Make argument parser, that has a `--file` argument which is required, then
    returns the parsed arguments.
    """
    parser = argparse.ArgumentParser(
        description="PyDependence: A tool for scanning and resolving python dependencies across files."
    )
    parser.add_argument(
        "config",
        type=str,
        help="The python file to analyse for dependencies.",
    )
    return parser.parse_args()


def _cli():
    # args
    args = _parse_args()

    # run
    try:
        pydeps(config_path=args.config)
    except NoConfiguredRequirementMappingError as e:
        LOGGER.critical(
            f"[pydependence] no configured requirement mapping found, either specify all missing version mappings or disable strict mode:\n{e}"
        )
        exit(1)


if __name__ == "__main__":
    # set default log level to info
    logging.basicConfig(level=logging.INFO)
    # run cli
    _cli()


# ========================================================================= #
# END                                                                       #
# ========================================================================= #
