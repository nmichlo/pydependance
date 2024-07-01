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
