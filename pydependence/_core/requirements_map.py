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
# REQUIREMENTS MAPPER (INTERMEDIATE)                                        #
# ========================================================================= #


# similar data structures to below, but nested differently. Could in theory be merged,
# but not really worth it for now. The below is more intended for user output, while
# this is more intended for actual information and for example isn't sorted and doesn't
# contain helper functions.


class ReqInfo(NamedTuple):
    requirement: str
    has_mapping: bool


@dataclasses.dataclass
class ReqInfoSources:
    requirement: str
    has_mapping: bool
    sources: Dict[str, List[LocImportInfo]]


# ========================================================================= #
# REQUIREMENTS MAPPER                                                       #
# ========================================================================= #


@dataclasses.dataclass
class MappedRequirementSourceModule:
    source_module: str
    source_module_imports: List[LocImportInfo]

    @property
    def source_module_root(self):
        return self.source_module.split(".")[0]


@dataclasses.dataclass
class MappedRequirement:
    requirement: str
    source_modules: List[MappedRequirementSourceModule]

    def get_source_names(
        self,
        enabled: bool = True,
        roots: bool = False,
    ) -> "List[str]":
        if enabled:
            return sorted(
                {
                    src.source_module_root if roots else src.source_module
                    for src in self.source_modules
                }
            )
        else:
            return []

    def get_sources_string(
        self,
        enabled: bool = True,
        roots: bool = False,
    ) -> str:
        return ", ".join(self.get_source_names(enabled=enabled, roots=roots))


@dataclasses.dataclass
class MappedRequirements:
    requirements: List[MappedRequirement]

    _AUTOGEN_NOTICE = "[AUTOGEN] by pydependence **DO NOT EDIT** [AUTOGEN]"

    def _get_debug_struct(self) -> "List[Tuple[str, List[str]]]":
        return [
            (req.requirement, [src.source_module for src in req.source_modules])
            for req in self.requirements
        ]

    def as_requirements_txt(
        self,
        notice: bool = True,
        sources: bool = True,
        sources_compact: bool = False,
        sources_roots: bool = False,
        indent_size: int = 4,
    ) -> str:
        lines = []
        if notice:
            lines.append(self._AUTOGEN_NOTICE)
        for req in self.requirements:
            # add requirement
            lines.append(f"{req.requirement}")
            # add compact sources
            if sources:
                if sources_compact:
                    lines[-1] += f" # {req.get_sources_string(roots=sources_roots)}"
                else:
                    for src_name in req.get_source_names(roots=sources_roots):
                        lines.append(f"{' '*indent_size*1}# ← {src_name}")
        if self.requirements or notice:
            lines.append("")
        return "\n".join(lines)

    def as_toml_array(
        self,
        notice: bool = True,
        sources: bool = True,
        sources_compact: bool = False,
        sources_roots: bool = False,
        indent_size: int = 4,
    ):
        import tomlkit
        import tomlkit.items

        # create table
        array = tomlkit.array().multiline(True)
        if notice:
            array.add_line(
                indent=" " * (indent_size * 1),
                comment=self._AUTOGEN_NOTICE,
            )
        for req in self.requirements:
            # add requirement & compact sources
            array.add_line(
                req.requirement,
                indent=" " * (indent_size * 1),
                comment=req.get_sources_string(
                    enabled=sources and sources_compact,
                    roots=sources_roots,
                ),
            )
            # add extended sources
            for src_name in req.get_source_names(
                enabled=sources and not sources_compact,
                roots=sources_roots,
            ):
                array.add_line(indent=" " * (indent_size * 2), comment=f"← {src_name}")
        if self.requirements or notice:
            array.add_line(indent="")
        # done!
        return array


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
    ) -> "ReqInfo":
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
                    return ReqInfo(rm.requirement, has_mapping=True)
        # 2. take the default env
        for rm in self._env_matchers.get(DEFAULT_REQUIREMENTS_ENV, []):
            if rm.matcher.match(import_):
                return ReqInfo(rm.requirement, has_mapping=True)
        # 3. return the root
        if strict:
            raise NoConfiguredRequirementMappingError(
                msg=f"could not find a mapped requirement for import: {repr(import_)}, define a scope or glob matcher for this import, or set disable strict mode!",
                imports={import_},
            )
        else:
            root = import_.split(".")[0]
            warnings.warn(
                f"could not find a matching requirement for import: {repr(import_)}, returning the import root: {repr(root)} as the requirement"
            )
            return ReqInfo(root, has_mapping=False)

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

    def _group_imports_by_mapped_requirements(
        self,
        imports: "List[LocImportInfo]",
        *,
        requirements_env: "Optional[str]" = None,
        strict: bool = False,
    ) -> "Dict[str, ReqInfoSources]":
        """
        Map imports to requirements, returning the imports grouped by the requirement.

        :raises NoConfiguredRequirementMappingError: if no requirement is found for an import, but only if strict mode is enabled, and after all imports have been processed so that pretty error messages can be generated.
        """
        # group imports by requirement
        requirements: "Dict[str, ReqInfoSources]" = dict()
        errors = []
        for imp in imports:
            # map requirements
            if imp.target in BUILTIN_MODULE_NAMES:
                req_info = ReqInfo(imp.target, has_mapping=False)  # TODO: needed?
            elif imp.root_target in BUILTIN_MODULE_NAMES:
                req_info = ReqInfo(imp.root_target, has_mapping=False)
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
            # get or create group
            req_group = requirements.get(req_info.requirement, None)
            if req_group is None:
                req_group = ReqInfoSources(
                    requirement=req_info.requirement,
                    sources={},
                    has_mapping=req_info.has_mapping,  # TODO: might not be updated?
                )
                requirements[req_info.requirement] = req_group
            # append source
            req_group.sources.setdefault(imp.source_name, []).append(imp)

        if errors:
            err_imports = {imp for e in errors for imp in e.imports}
            err_roots = {imp.split(".")[0] for imp in err_imports}
            raise NoConfiguredRequirementMappingError(
                msg=f"could not find import to requirement mappings for, "
                f"roots: {sorted(err_roots)}, or full imports: {sorted(err_imports)}, "
                f"available matchers: {self._get_matcher_cfg_sting(requirements_env=requirements_env)}, "
                f"otherwise if running from a config file, set strict_requirements_map=False to disable strict mode and use the root module name instead.",
                imports=err_imports,
            )

        # shallow copy
        return requirements

    def generate_requirements(
        self,
        imports: "List[LocImportInfo]",
        *,
        requirements_env: "Optional[str]" = None,
        strict: bool = False,
    ) -> "MappedRequirements":
        """
        :raises NoConfiguredRequirementMappingError: if no requirement is found for any import, but only if strict mode is enabled.
        """
        # 1. map imports to requirements
        # {requirement: {source: [import_info, ...], ...}, ...}
        mapped_requirements_infos: "Dict[str, ReqInfoSources]" = (
            self._group_imports_by_mapped_requirements(
                imports,
                requirements_env=requirements_env,
                strict=strict,
            )
        )

        # 2. generate requirements list
        output_reqs = []
        for requirement in sorted(mapped_requirements_infos.keys()):
            # {source: [import_info, ...], ...}
            mapped_requirement_info = mapped_requirements_infos[requirement]

            # - generate requirement sources
            source_modules = []
            for source in sorted(mapped_requirement_info.sources.keys()):
                sources = mapped_requirement_info.sources[source]
                write_src = MappedRequirementSourceModule(
                    source_module=source,
                    source_module_imports=sources,
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
