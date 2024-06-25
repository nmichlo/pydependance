import logging
import sys

from pydependence._cli import pydeps
from pydependence._core.requirements_map import NoConfiguredRequirementMappingError

LOGGER = logging.getLogger(__name__)

# ========================================================================= #
# CLI                                                                       #
# ========================================================================= #


if __name__ == "__main__":
    # set default log level to info
    logging.basicConfig(level=logging.INFO)

    # get file
    if len(sys.argv) < 2:
        LOGGER.critical("[pydependence] missing file argument.")
        exit(1)
    elif len(sys.argv) == 2:
        script, file = sys.argv
    else:
        LOGGER.critical("[pydependence] too many arguments.")
        exit(1)

    # run
    try:
        pydeps(file=file)
    except NoConfiguredRequirementMappingError as e:
        LOGGER.critical(
            f"[pydependence] no configured requirement mapping found, either specify all missing version mappings or disable strict mode:\n{e}"
        )
        exit(1)


# ========================================================================= #
# END                                                                       #
# ========================================================================= #
