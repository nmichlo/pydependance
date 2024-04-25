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
import functools
import warnings
from collections import defaultdict
from typing import TYPE_CHECKING, Dict, List, NamedTuple, Optional, Set, Tuple, Union

from pydependence._core.builtin import BUILTIN_MODULE_NAMES
from pydependence._core.module_imports_ast import LocImportInfo

if TYPE_CHECKING:
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

    def __init__(self, scope: "ModulesScope"):
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
        self._base = ".".join(self._parts)

    def match(self, import_: str) -> bool:
        if not self._wildcard:
            return import_ == self._base
        else:
            parts = import_.split(".")
            return self._parts == parts[: len(self._parts)]


# ========================================================================= #
# REQUIREMENTS MAPPER                                                       #
# ========================================================================= #


@dataclasses.dataclass
class MappedRequirementSourceModule:
    source_module: str
    source_module_imports: List[LocImportInfo]


@dataclasses.dataclass
class MappedRequirement:
    requirement: str
    source_modules: List[MappedRequirementSourceModule]


@dataclasses.dataclass
class MappedRequirements:
    requirements: List[MappedRequirement]

    def _get_debug_struct(self) -> "List[Tuple[str, List[str]]]":
        return [
            (req.requirement, [src.source_module for src in req.source_modules])
            for req in self.requirements
        ]


# ========================================================================= #
# REQUIREMENTS MAPPER                                                       #
# ========================================================================= #


class NoConfiguredRequirementMappingError(ValueError):

    def __init__(self, msg: str, imports: Set[str]):
        self.msg = msg
        self.imports = imports
        super().__init__(msg)


class ReqMatcher(NamedTuple):
    requirement: str
    matcher: ImportMatcherBase


class RequirementsMapper:

    def __init__(
        self,
        *,
        env_matchers: "Optional[Union[Dict[str, List[ReqMatcher]], List[ReqMatcher]]]",
        strict: bool = False,
    ):
        # env -> [(requirement, import matcher), ...]
        # * we use a list to maintain order, and then linear search. This is because
        #   we could have multiple imports that match to the same requirement.
        #   we could potentially be stricter about this in future...
        self._env_matchers = self._validate_env_matchers(env_matchers)
        self._strict = strict

    @classmethod
    def _validate_env_matchers(cls, env_matchers) -> "Dict[str, List[ReqMatcher]]":
        # normalize
        if env_matchers is None:
            env_matchers = {}
        elif not isinstance(env_matchers, dict):
            env_matchers = {DEFAULT_REQUIREMENTS_ENV: list(env_matchers)}
        # shift
        if None in env_matchers:
            if DEFAULT_REQUIREMENTS_ENV in env_matchers:
                raise ValueError(
                    f"env_matchers cannot have both {repr(None)} and {repr(DEFAULT_REQUIREMENTS_ENV)} as keys."
                )
            env_matchers[DEFAULT_REQUIREMENTS_ENV] = env_matchers.pop(None)
        # check
        if not isinstance(env_matchers, dict):
            raise ValueError(
                f"env_matchers must be a dictionary, got: {type(env_matchers)}"
            )
        for env, matchers in env_matchers.items():
            if not isinstance(matchers, list):
                raise ValueError(
                    f"env_matchers must be a dictionary of lists, got: {type(matchers)}"
                )
            for matcher in matchers:
                if not isinstance(matcher, ReqMatcher):
                    raise ValueError(
                        f"env_matchers must be a dictionary of lists of ReqMatcherPair, got: {type(matcher)}"
                    )
                if not isinstance(matcher.requirement, str):
                    raise ValueError(
                        f"requirement must be a string, got: {type(matcher.requirement)}"
                    )
                if not isinstance(matcher.matcher, ImportMatcherBase):
                    raise ValueError(
                        f"matcher must be an ImportMatcherBase, got: {type(matcher.matcher)}"
                    )
        return env_matchers

    @functools.lru_cache(maxsize=256)
    def map_import_to_requirement(
        self,
        import_: str,
        *,
        requirements_env: "Optional[str]" = None,
    ) -> str:
        if requirements_env is None:
            requirements_env = DEFAULT_REQUIREMENTS_ENV
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

    def _group_imports_by_mapped_requirements(
        self,
        imports: "List[LocImportInfo]",
        *,
        requirements_env: "Optional[str]" = None,
    ) -> "Dict[str, Dict[str, List[LocImportInfo]]]":
        """
        Map imports to requirements, returning the imports grouped by the requirement.

        :raises NoConfiguredRequirementMappingError: if no requirement is found for an import, but only if strict mode is enabled, and after all imports have been processed so that pretty error messages can be generated.
        """
        requirements: "Dict[str, Dict[str, List[LocImportInfo]]]" = defaultdict(
            lambda: defaultdict(list)
        )
        errors = []
        for imp in imports:
            try:
                if imp in BUILTIN_MODULE_NAMES:
                    requirement = imp
                else:
                    requirement = self.map_import_to_requirement(
                        imp.target,
                        requirements_env=requirements_env,
                    )
                requirements[requirement][imp.source_name].append(imp)
            except NoConfiguredRequirementMappingError as e:
                errors.append(e)

        if errors:
            err_imports = {imp for e in errors for imp in e.imports}
            err_roots = {imp.split(".")[0] for imp in err_imports}
            raise NoConfiguredRequirementMappingError(
                msg=f"could not find mapped requirements for, roots: {sorted(err_roots)}, or full imports: {sorted(err_imports)}",
                imports=err_imports,
            )

        # shallow copy
        return {k: dict(v) for k, v in requirements.items()}

    def generate_requirements(
        self,
        imports: "List[LocImportInfo]",
        *,
        requirements_env: "Optional[str]" = None,
    ) -> "MappedRequirements":
        # 1. map imports to requirements
        # {requirement: {source: [import_info, ...], ...}, ...}
        requirements_sources_imports: "Dict[str, Dict[str, List[LocImportInfo]]]" = (
            self._group_imports_by_mapped_requirements(
                imports,
                requirements_env=requirements_env,
            )
        )

        # 2. generate requirements list
        output_reqs = []
        for requirement in sorted(requirements_sources_imports.keys()):
            # {source: [import_info, ...], ...}
            requirement_sources = requirements_sources_imports[requirement]
            # - generate requirement sources
            source_modules = []
            for source in sorted(requirement_sources.keys()):
                write_src = MappedRequirementSourceModule(
                    source_module=source,
                    source_module_imports=requirement_sources[source],
                )
                source_modules.append(write_src)
            # - generate requirement
            out_req = MappedRequirement(
                requirement=requirement,
                source_modules=source_modules,
            )
            output_reqs.append(out_req)
        # done!
        return MappedRequirements(requirements=output_reqs)


# ========================================================================= #
# END                                                                       #
# ========================================================================= #
