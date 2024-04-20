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

import functools
import warnings
from typing import Dict, List, Set, Tuple

from pydependence._core.modules_scope import ModulesScope

# The version matching env
DEFAULT_REQUIREMENTS_ENV = "default"


# ========================================================================= #
# IMPORT MATCHER                                                            #
# ========================================================================= #


class ImportMatcherBase:

    def match(self, import_: str) -> bool:
        raise NotImplementedError


class ImportMatcherScope(ImportMatcherBase):

    def __init__(self, scope: ModulesScope):
        self.scope = scope

    def match(self, import_: str) -> bool:
        return self.scope.has_module(import_)


class ImportMatcherGlob(ImportMatcherBase):

    def __init__(self, import_glob: str):
        (*parts, last) = import_glob.split(".")
        # check all parts are identifiers, OR, at least one identifier with the last part being a glob
        if parts:
            if not all(str.isidentifier(x) for x in parts):
                raise ValueError(
                    f"parts of import glob {repr(import_glob)} are not valid identifiers"
                )
            if not (str.isidentifier(last) or last == "*"):
                raise ValueError(
                    f"last part of import glob {repr(import_glob)} is not a valid identifier or '*'"
                )
        else:
            if not str.isidentifier(last):
                raise ValueError(
                    f"last part of import glob {repr(import_glob)} is not a valid identifier"
                )
        # create glob
        if last == "*":
            self._parts = parts
            self._wildcard = True
        else:
            self._parts = (*parts, last)
            self._wildcard = False
        self._base = ".".join(parts)

    def match(self, import_: str) -> bool:
        if not self._wildcard:
            return import_ == self._base
        else:
            parts = import_.split(".")
            return self._parts == parts[: len(self._parts)]


# ========================================================================= #
# REQUIREMENTS MAPPER                                                       #
# ========================================================================= #


class NoConfiguredRequirementMappingError(ValueError):

    def __init__(self, msg: str, imports: Set[str]):
        self.msg = msg
        self.imports = imports
        super().__init__(msg)


class RequirementsMapper:

    def __init__(
        self,
        *,
        env_matchers: "Dict[str, List[Tuple[str, ImportMatcherBase]]]",
        strict: bool = False,
    ):
        # env -> [(requirement, import matcher), ...]
        # * we use a list to maintain order, and then linear search. This is because
        #   we could have multiple imports that match to the same requirement.
        #   we could potentially be stricter about this in future...
        self._env_matchers = env_matchers
        self._strict = strict

    @functools.lru_cache(maxsize=256)
    def map_import_to_requirement(self, import_: str, requirements_env: str) -> str:
        # 1. take the specific env
        if requirements_env != DEFAULT_REQUIREMENTS_ENV:
            if requirements_env not in self._env_matchers:
                raise ValueError(
                    f"env: {repr(requirements_env)} has not been defined for a requirement."
                )
            for requirement, matcher in self._env_matchers[requirements_env]:
                if matcher.match(import_):
                    return requirement
        # 2. take the default env
        for requirement, matcher in self._env_matchers.get(
            DEFAULT_REQUIREMENTS_ENV, []
        ):
            if matcher.match(import_):
                return requirement
        # 3. return the root
        if self._strict:
            raise NoConfiguredRequirementMappingError(
                msg=f"could not find a mapped requirement for import: {repr(import_)}, define a scope or glob matcher for this import, or set disable strict mode!",
                imports={import_},
            )
        else:
            root = import_.split(".")[0]
            warnings.warn(
                f"could not find a matching requirement for import: {repr(import_)}, returning the import root: {repr(root)} as the requirement"
            )
            return root


# ========================================================================= #
# END                                                                       #
# ========================================================================= #
