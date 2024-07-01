# ============================================================================== #
# MIT License                                                                    #
#                                                                                #
# Copyright (c) 2024 Nathan Juraj Michlo                                         #
#                                                                                #
# Permission is hereby granted, free of charge, to any person obtaining a copy   #
# of this software and associated documentation files (the "Software"), to deal  #
# in the Software without restriction, including without limitation the rights   #
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell      #
# copies of the Software, and to permit persons to whom the Software is          #
# furnished to do so, subject to the following conditions:                       #
#                                                                                #
# The above copyright notice and this permission notice shall be included in all #
# copies or substantial portions of the Software.                                #
#                                                                                #
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR     #
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,       #
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE    #
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER         #
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,  #
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE  #
# SOFTWARE.                                                                      #
# ============================================================================== #


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
        dry_run: bool
        exit_zero: bool


def _parse_args() -> "PyDepsCliArgsProto":
    """
    Make argument parser for:
    `config`, required
    `--dry-run`, optional
    `--exit-zero`, optional # always return success exit code even if files changed

    Then parse the arguments and return them.
    """
    parser = argparse.ArgumentParser(
        description="PyDependence: A tool for scanning and resolving python dependencies across files."
    )
    parser.add_argument(
        "config",
        type=str,
        help="The python file to analyse for dependencies.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run the script without making any changes.",
    )
    parser.add_argument(
        "--exit-zero",
        action="store_true",
        help="Always return a success exit code, even if files changed.",
    )
    return parser.parse_args()


def _cli():
    # args
    args = _parse_args()

    # run
    try:
        changed = pydeps(
            config_path=args.config,
            dry_run=args.dry_run,
        )
    except NoConfiguredRequirementMappingError as e:
        LOGGER.critical(
            f"[pydependence] no configured requirement mapping found, either specify all missing version mappings or disable strict mode:\n{e}"
        )
        exit(1)

    # check if files changed
    if changed:
        LOGGER.info("[pydependence] files changed.")
        if args.exit_zero:
            LOGGER.info(
                "[pydependence] exit-zero enabled, returning success exit code."
            )
            exit(0)
        else:
            exit(1)
    else:
        LOGGER.info("[pydependence] files unchanged.")
        exit(0)


if __name__ == "__main__":
    # set default log level to info
    logging.basicConfig(level=logging.INFO)
    # run cli
    _cli()


# ========================================================================= #
# END                                                                       #
# ========================================================================= #
