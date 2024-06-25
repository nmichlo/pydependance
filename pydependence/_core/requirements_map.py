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
import abc
import dataclasses
import functools
import warnings
from typing import TYPE_CHECKING, Dict, List, NamedTuple, Optional, Set, Union

from pydependence._core.builtin import BUILTIN_MODULE_NAMES
from pydependence._core.module_imports_ast import (
    BasicImportInfo,
    LocImportInfo,
    ManualImportInfo,
)
from pydependence._core.requirements_out import (
    OutMappedRequirement,
    OutMappedRequirements,
    OutMappedRequirementSource,
)

if TYPE_CHECKING:
    from pydependence._core.modules_scope import ModulesScope


# The version matching env
DEFAULT_REQUIREMENTS_ENV = "default"


# ========================================================================= #
# IMPORT MATCHER                                                            #
# ========================================================================= #


class ImportMatcherBase(abc.ABC):

    @abc.abstractmethod
    def match(self, import_: str) -> bool:
        raise NotImplementedError

    @abc.abstractmethod
    def cfg_str(self) -> str:
        raise NotImplementedError


class ImportMatcherScope(ImportMatcherBase):

    def __init__(self, scope: "ModulesScope"):
        self.scope = scope

    def match(self, import_: str) -> bool:
        return self.scope.has_module(import_)

    def cfg_str(self) -> str:
        return f"scope={repr(self.scope)}"


class ImportMatcherGlob(ImportMatcherBase):

    def __init__(self, import_glob: str):
        self._orig = import_glob
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

    def cfg_str(self) -> str:
        return f"import={repr(self._orig)}"


class ImportMatcherGlobs(ImportMatcherBase):

    def __init__(self, import_globs: "Union[str, List[str]]"):
        if isinstance(import_globs, str):
            import_globs = import_globs.split(",")
        self._orig = ",".join(import_globs)
        # create
        self._matchers = []
        # dedupe
        _added = set()
        for x in import_globs:
            if x not in _added:
                self._matchers.append(ImportMatcherGlob(x))
                _added.add(x)

    def match(self, import_: str) -> bool:
        # linear search... inefficient...
        for matcher in self._matchers:
            if matcher.match(import_):
                return True
        return False

    def cfg_str(self) -> str:
        return f"import={repr(self._orig)}"


# ========================================================================= #
# REQUIREMENTS MAPPER (INFO)                                                #
# ========================================================================= #


class MappedRequirementInfo(NamedTuple):
    requirement: str
    is_mapped: bool
    original_name: str


# ========================================================================= #
# REQUIREMENTS MAPPER (INTERMEDIATE)                                        #
# # similar data structures to output, but with more information
# ========================================================================= #


@dataclasses.dataclass
class MappedRequirementSource:
    source_module: str
    source_module_imports: List[BasicImportInfo]

    def to_output_requirement_source(self):
        return OutMappedRequirementSource(
            source_module=self.source_module,
            is_lazy=all(imp.is_lazy for imp in self.source_module_imports),
            is_manual=any(
                isinstance(imp, ManualImportInfo) for imp in self.source_module_imports
            ),
        )


@dataclasses.dataclass
class MappedRequirement:
    requirement: str  # mapped name
    sources: Dict[str, MappedRequirementSource]  # k == v.source_module

    def get_sorted_sources(self) -> List[MappedRequirementSource]:
        return sorted(self.sources.values(), key=lambda x: x.source_module)

    def to_output_requirement(self):
        return OutMappedRequirement(
            requirement=self.requirement,
            sources=[
                source.to_output_requirement_source()
                for source in self.get_sorted_sources()
            ],
        )


@dataclasses.dataclass
class MappedRequirements:
    requirements: Dict[str, MappedRequirement]  # k == v.requirement
    resolver_name: Optional[str] = None

    def get_sorted_requirements(self) -> List[MappedRequirement]:
        return sorted(
            self.requirements.values(),
            key=lambda x: x.requirement,
        )

    def to_output_requirements(self):
        return OutMappedRequirements(
            requirements=[
                requirement_info.to_output_requirement()
                for requirement_info in self.get_sorted_requirements()
            ],
            resolver_name=self.resolver_name,
        )


# ========================================================================= #
# REQUIREMENTS MAPPER                                                       #
# ========================================================================= #


class NoConfiguredRequirementMappingError(ValueError):

    def __init__(self, msg: str, imports: Set[str]):
        self.msg = msg
        self.imports = imports
        super().__init__(msg)


@dataclasses.dataclass(frozen=True)
class ReqMatcher:
    requirement: str
    matcher: ImportMatcherBase

    def cfg_str(self) -> str:
        return f"{{requirement={repr(self.requirement)}, {self.matcher.cfg_str()}}}"


class RequirementsMapper:

    def __init__(
        self,
        *,
        env_matchers: "Optional[Union[Dict[str, List[ReqMatcher]], List[ReqMatcher]]]",
    ):
        # env -> [(requirement, import matcher), ...]
        # * we use a list to maintain order, and then linear search. This is because
        #   we could have multiple imports that match to the same requirement.
        #   we could potentially be stricter about this in future...
        self._env_matchers = self._validate_env_matchers(env_matchers)

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
                        f"env_matchers must be a dictionary of lists of ReqMatcherPair, got: {type(matcher)}, {matcher}"
                    )
                if not isinstance(matcher.requirement, str):
                    raise ValueError(
                        f"requirement must be a string, got: {type(matcher.requirement)}"
                    )
                if not isinstance(matcher.matcher, ImportMatcherBase):
                    raise ValueError(
                        f"matcher must be an ImportMatcherBase, got: {type(matcher.matcher)}, {matcher.matcher}"
                    )
        return env_matchers

    def map_import_to_requirement(
        self,
        import_: str,
        *,
        requirements_env: "Optional[str]" = None,
        strict: bool = False,
    ) -> str:
        req_info = self.map_import_to_requirement_info(
            import_,
            requirements_env=requirements_env,
            strict=strict,
        )
        return req_info.requirement

    @functools.lru_cache(maxsize=256)
    def map_import_to_requirement_info(
        self,
        import_: str,
        *,
        requirements_env: "Optional[str]" = None,
        strict: bool = False,
    ) -> "MappedRequirementInfo":
        """
        :raises NoConfiguredRequirementMappingError: if no requirement is found for an import and if strict mode is enabled.
        """
        if requirements_env is None:
            requirements_env = DEFAULT_REQUIREMENTS_ENV
        # 1. take the specific env
        if requirements_env != DEFAULT_REQUIREMENTS_ENV:
            if requirements_env not in self._env_matchers:
                raise ValueError(
                    f"env: {repr(requirements_env)} has not been defined for a requirement."
                )
            for rm in self._env_matchers[requirements_env]:
                if rm.matcher.match(import_):
                    return MappedRequirementInfo(
                        rm.requirement,
                        is_mapped=True,
                        original_name=import_,
                    )
        # 2. take the default env
        for rm in self._env_matchers.get(DEFAULT_REQUIREMENTS_ENV, []):
            if rm.matcher.match(import_):
                return MappedRequirementInfo(
                    rm.requirement,
                    is_mapped=True,
                    original_name=import_,
                )
        # 3. return the root
        if strict:
            raise NoConfiguredRequirementMappingError(
                msg=f"could not find import to requirement mappings: {repr(import_)},\ndefine a scope or glob matcher for this import, or set disable strict mode!",
                imports={import_},
            )
        else:
            root = import_.split(".")[0]
            warnings.warn(
                f"could not find a matching requirement for import: {repr(import_)}, returning the import root: {repr(root)} as the requirement"
            )
            return MappedRequirementInfo(
                root,
                is_mapped=False,
                original_name=import_,  # TODO: or should this be root?
            )

    def _get_joined_matchers(
        self,
        requirements_env: "Optional[str]" = None,
    ) -> "List[ReqMatcher]":
        if requirements_env is None:
            requirements_env = DEFAULT_REQUIREMENTS_ENV
        matchers = self._env_matchers.get(requirements_env, [])
        if requirements_env != DEFAULT_REQUIREMENTS_ENV:
            matchers = self._env_matchers.get(DEFAULT_REQUIREMENTS_ENV, []) + matchers
        return matchers

    def _get_matcher_cfg_sting(self, requirements_env: "Optional[str]" = None) -> "str":
        return ", ".join(
            [
                rm.cfg_str()
                for rm in self._get_joined_matchers(requirements_env=requirements_env)
            ]
        )

    def generate_mapped_requirements(
        self,
        imports: "List[BasicImportInfo]",
        *,
        requirements_env: "Optional[str]" = None,
        strict: bool = False,
        raw: List[str] = None,
        resolver_name: Optional[str] = None,
    ) -> "MappedRequirements":
        """
        Map imports to requirements, returning the imports grouped by the requirement.

        :raises NoConfiguredRequirementMappingError: if no requirement is found for an import, but only if strict mode is enabled, and after all imports have been processed so that pretty error messages can be generated.
        """
        if raw:
            raise NotImplementedError("raw imports are not yet supported, TODO!!!")

        # group imports by requirement
        r = MappedRequirements(
            requirements={},
            resolver_name=resolver_name,
        )
        errors = []
        for imp in imports:
            # 1. map requirements
            if imp.target in BUILTIN_MODULE_NAMES:  # TODO: needed?
                req_info = MappedRequirementInfo(
                    imp.target,
                    is_mapped=False,
                    original_name=imp.target,
                )
            elif imp.root_target in BUILTIN_MODULE_NAMES:
                req_info = MappedRequirementInfo(
                    imp.root_target,
                    is_mapped=False,
                    original_name=imp.target,  # TODO: or should this be root?
                )
            else:
                try:
                    req_info = self.map_import_to_requirement_info(
                        imp.target,
                        requirements_env=requirements_env,
                        strict=strict,
                    )
                except NoConfiguredRequirementMappingError as e:
                    errors.append(e)
                    continue

            # 2. get or create requirement sources
            req_group = r.requirements.get(req_info.requirement, None)
            if req_group is None:
                req_group = MappedRequirement(
                    requirement=req_info.requirement,
                    sources={},
                )
                r.requirements[req_info.requirement] = req_group

            # - get or create requirement source import
            req_group_source = req_group.sources.get(imp.source_name, None)
            if req_group_source is None:
                req_group_source = MappedRequirementSource(
                    source_module=imp.source_name,
                    source_module_imports=[],
                )
                req_group.sources[imp.source_name] = req_group_source

            # - append import to source & update
            req_group_source.source_module_imports.append(imp)

        if errors:
            err_imports = {imp for e in errors for imp in e.imports}
            err_roots = {imp.split(".")[0] for imp in err_imports}
            raise NoConfiguredRequirementMappingError(
                msg=(
                    f"could not find import to requirement mappings for roots:"
                    f"\n  * {', '.join(map(repr, map(str, sorted(set(err_roots)))))},"
                    f"\nor full imports:"
                    f"\n  * {', '.join(map(repr, map(str, sorted(set(err_imports)))))},"
                    f"\navailable matchers: {self._get_matcher_cfg_sting(requirements_env=requirements_env) or '<NONE>'},"
                    f"\notherwise if running from a config file, set strict_requirements_map=False to disable strict mode and use the root module name instead."
                ),
                imports=err_imports,
            )

        # done!
        return r

    def generate_output_requirements(
        self,
        imports: "List[BasicImportInfo]",
        *,
        requirements_env: "Optional[str]" = None,
        strict: bool = False,
        resolver_name: Optional[str] = None,
    ) -> "OutMappedRequirements":
        """
        :raises NoConfiguredRequirementMappingError: if no requirement is found for any import, but only if strict mode is enabled.
        """
        # 1. map imports to requirements
        r = self.generate_mapped_requirements(
            imports,
            requirements_env=requirements_env,
            strict=strict,
            resolver_name=resolver_name,
        )
        # 2. generate output requirements lists
        return r.to_output_requirements()


# ========================================================================= #
# END                                                                       #
# ========================================================================= #
