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


import dataclasses
from typing import Dict, List

from pydependence._core.module_data import ModuleMetadata
from pydependence._core.module_imports_ast import (
    LocImportInfo,
    load_imports_from_module_info,
)

# ========================================================================= #
# MODULE IMPORTS                                                            #
# ========================================================================= #


@dataclasses.dataclass
class ModuleImports:
    module_info: ModuleMetadata
    module_imports: "Dict[str, List[LocImportInfo]]"

    @classmethod
    def from_module_info_and_parsed_file(cls, module_info: ModuleMetadata):
        module_imports = load_imports_from_module_info(module_info=module_info)
        return ModuleImports(
            module_info=module_info,
            module_imports=dict(module_imports),
        )


# ========================================================================= #
# MODULE IMPORTS LOADER                                                     #
# ========================================================================= #


class _ModuleImportsLoader:

    def __init__(self):
        self._modules_imports: "Dict[str, ModuleImports]" = {}

    def load_module_imports(self, module_info: ModuleMetadata) -> ModuleImports:
        v = self._modules_imports.get(module_info.name, None)
        if v is None:
            v = ModuleImports.from_module_info_and_parsed_file(module_info)
            self._modules_imports[module_info.name] = v
        else:
            if v.module_info != module_info:
                raise RuntimeError(
                    f"ModuleMetadata mismatch: {v.module_info} != {module_info}"
                )
        return v


# GLOBAL INSTANCE
# TODO: can replace with disk cache
DEFAULT_MODULE_IMPORTS_LOADER = _ModuleImportsLoader()


# ========================================================================= #
# END                                                                       #
# ========================================================================= #


__all__ = (
    "ModuleImports",
    "DEFAULT_MODULE_IMPORTS_LOADER",
)
