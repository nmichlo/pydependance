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

import logging
import warnings
from collections import defaultdict
from enum import Enum
from pathlib import Path
from typing import Dict, List, Literal, Optional, Union

import pydantic
from packaging.requirements import Requirement
from typing_extensions import Annotated

from pydependence._core.module_imports_ast import ManualImportInfo
from pydependence._core.modules_scope import (
    ModulesScope,
    RestrictMode,
    RestrictOp,
    UnreachableModeEnum,
)
from pydependence._core.requirements_map import (
    DEFAULT_REQUIREMENTS_ENV,
    ImportMatcherBase,
    ImportMatcherGlobs,
    ImportMatcherScope,
    NoConfiguredRequirementMappingError,
    ReqMatcher,
    RequirementsMapper,
)
from pydependence._core.requirements_out import OutMappedRequirements
from pydependence._core.utils import (
    apply_root_to_path_str,
    load_toml_document,
    toml_file_replace_array,
    txt_file_dump,
)

# python 3.8 support
# TODO: this pattern is not yet supported by the lazy dependency resolver
#       we should specifically add support for this pattern, as it is a common.
# TODO: we should add the ability to exclude certain imports from the pydependence
#       resolve to handle cases like this.
# try:
#     from typing import Annotated
# except ImportError:
#     from typing_extensions import Annotated

LOGGER = logging.getLogger(__name__)

# ========================================================================= #
# CONFIGS                                                                   #
# ========================================================================= #


class _ResolveRules(pydantic.BaseModel, extra="forbid"):

    # If true, then vist all the lazy imports. Usually the lazy imports are removed from
    # the import graph and we don't traverse these edges. This on the other-hand allows
    # all these edges to be traversed. This is often useful if you want to create
    # packages that only require some minimal set of requirements, and everything else
    # that you define should be optional. Also useful if you want to generate a minimal
    # dependencies list, and then in optional dependency lists you want to create a full
    # set of requirements for everything!
    visit_lazy: Optional[bool] = None

    # only applicable when `visit_lazy=False`, then in this case we re-add the lazy
    # imports that are directly referenced in all the traversed files, i.e. it is a
    # shallow include of lazy imports without continuing to traverse them. This means
    # that we add the lazy imports but we don't continue traversing. This is often not
    # useful with complex lazy import graphs that continue to reference more module
    # within the same scope as this could cause missing imports, rather specify
    # `visit_lazy=True` in this case.
    # * [A.K.A.] `shallow_include_lazy=True`
    re_add_lazy: Optional[bool] = None

    # If true, then exclude imports that were not encountered as we traversed the import
    # graph. [NOTE]: this is probably useful if you don't want to include all imports
    # below a specific scope, but only want to resolve what is actually encountered.
    # Not entirely sure this has much of an effect?
    exclude_unvisited: Optional[bool] = None

    # If true, then exclude all imports that are part of the current scope. This usually
    # should not have any effect because imports are replaced as we traverse the graph
    # through the current scope, [NOTE] thus not entirely sure that this has any effect,
    # should it be a bug if we encounter any of these?
    exclude_in_search_space: Optional[bool] = None

    # If true, then exclude all the python builtin package names from being output in
    # the requirements files. This usually should be true unless you are trying to debug
    # as this would generate invalid requirements list as these would not exist on pypi.
    exclude_builtins: Optional[bool] = None

    # Check that generated imports and requirements have entries in the versions list.
    # If strict mode is enabled, then an error is thrown if a version entry is missing.
    # If strict mode is disabled, then a warning should be given, and the root import
    # name is used instead of the requirement name, which may or may not match up
    # to an actual python package.
    strict_requirements_map: Optional[bool] = None

    # TODO: we should add some sort of option to ensure that generated dependency lists
    #       exactly match some pre-defined set, while also outputting this set.

    # TODO: we do not yet ensure that raw added requirements do not conflict with
    #       generated requirements.

    @classmethod
    def make_default_base_rules(cls):
        return _ResolveRules(
            visit_lazy=False,
            re_add_lazy=False,
            exclude_unvisited=True,
            exclude_in_search_space=True,
            exclude_builtins=True,
            strict_requirements_map=True,
        )

    def set_defaults(self, defaults: "_ResolveRules"):
        assert defaults.visit_lazy is not None
        assert defaults.re_add_lazy is not None
        assert defaults.exclude_unvisited is not None
        assert defaults.exclude_in_search_space is not None
        assert defaults.exclude_builtins is not None
        assert defaults.strict_requirements_map is not None
        if self.visit_lazy is None:
            self.visit_lazy = defaults.visit_lazy
        if self.re_add_lazy is None:
            self.re_add_lazy = defaults.re_add_lazy
        if self.exclude_unvisited is None:
            self.exclude_unvisited = defaults.exclude_unvisited
        if self.exclude_in_search_space is None:
            self.exclude_in_search_space = defaults.exclude_in_search_space
        if self.exclude_builtins is None:
            self.exclude_builtins = defaults.exclude_builtins
        if self.strict_requirements_map is None:
            self.strict_requirements_map = defaults.strict_requirements_map


# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - #
# CONFIG - OUTPUT                                                           #
# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - #


class OutputModeEnum(str, Enum):
    requirements = "requirements"
    optional_dependencies = "optional-dependencies"
    dependencies = "dependencies"


class _Output(_ResolveRules, extra="forbid"):
    # resolve
    scope: Optional[str] = None
    start_scope: Optional[str] = None

    # raw requirements / imports that are mapped
    raw: Optional[List[str]] = None

    # requirements mapping
    env: str = DEFAULT_REQUIREMENTS_ENV

    # output
    output_mode: str
    output_file: str

    # !!!NB!!! DO NOT USE DIRECTLY! INSTEAD, USE `get_output_extras_name`
    output_name: Optional[str] = None

    def get_output_extras_name(self) -> str:
        if self.output_name is not None:
            name = self.output_name
        elif self.start_scope is not None:
            name = self.start_scope
        elif self.scope is not None:
            name = self.scope
        else:
            raise ValueError(
                f"output_name cannot be determined, please set output_name, start_scope, or scope for: {self}"
            )
        return normalize_extras_name(name, strict=False)

    def get_manual_imports(self):
        if not self.raw:
            return []
        return [ManualImportInfo.from_target(r) for r in self.raw]

    @pydantic.field_validator("output_name", mode="before")
    @classmethod
    def _validate_output_name(cls, v):
        # TODO: should maybe allow non-strict mode?
        if v is not None:
            return normalize_extras_name(v, strict=True)
        return v

    @pydantic.field_validator("raw", mode="before")
    @classmethod
    def _validate_raw(cls, v):
        if v is not None:
            normalized = []
            for r in v:
                normalized.append(normalize_pkg_name(r, strict=False))
            return normalized
        return v

    @pydantic.model_validator(mode="after")
    @classmethod
    def _validate_model(cls, v):
        if v.start_scope is not None:
            if v.scope is None:
                raise ValueError(f"start_scope is set, but scope is not set for: {v}")
        return v

    def get_resolved_imports(
        self,
        loaded_scopes: "LoadedScopes",
    ):
        if not self.scope:
            return []
        # * normal scope
        if self.scope not in loaded_scopes:
            raise ValueError(
                f"scope {repr(self.scope)} does not exist, must be one of: {loaded_scopes.sorted_names}"
            )
        else:
            scope = loaded_scopes[self.scope]
        # * start scope
        start_scope = None
        if self.start_scope:
            if self.start_scope not in loaded_scopes:
                raise ValueError(
                    f"start_scope {repr(self.start_scope)} does not exist, must be one of: {loaded_scopes.sorted_names}"
                )
            else:
                start_scope = loaded_scopes[self.start_scope]
        # * resolve imports
        return scope.resolve_imports(
            start_scope=start_scope,
            visit_lazy=self.visit_lazy,
            re_add_lazy=self.re_add_lazy,
            exclude_unvisited=self.exclude_unvisited,
            exclude_in_search_space=self.exclude_in_search_space,
            exclude_builtins=self.exclude_builtins,
        )

    def resolve_generate_and_write_requirements(
        self,
        loaded_scopes: "LoadedScopes",
        requirements_mapper: RequirementsMapper,
    ) -> None:
        # 1. resolve imports
        resolved_imports = self.get_resolved_imports(loaded_scopes=loaded_scopes)
        manual_imports = self.get_manual_imports()
        # 2. generate requirements
        try:
            mapped_requirements = requirements_mapper.generate_output_requirements(
                imports=resolved_imports + manual_imports,
                requirements_env=self.env,
                strict=self.strict_requirements_map,
                resolver_name=self.get_output_extras_name(),
            )
        except NoConfiguredRequirementMappingError as e:
            msg = f"\n  | ".join(["", *str(e).split("\n")])
            msg = f"[requirement-mapping-error] output: {self.get_output_extras_name()}{msg}"
            raise NoConfiguredRequirementMappingError(msg, e.imports) from e
        # 3. write requirements
        self._write_requirements(
            mapped_requirements=mapped_requirements,
        )

    def _write_requirements(self, mapped_requirements: OutMappedRequirements) -> None:
        raise NotImplementedError(
            f"tried to write imports for {repr(self.get_output_extras_name())}, write_imports not implemented for {self.__class__.__name__}"
        )


class _OutputRequirements(_Output):
    output_mode: Literal[OutputModeEnum.requirements]

    def _write_requirements(self, mapped_requirements: OutMappedRequirements):
        string = mapped_requirements.as_requirements_txt(
            notice=True,
            sources=True,
            sources_compact=False,
            sources_roots=False,
            indent_size=4,
        )
        LOGGER.info(f"writing requirements to: {self.output_file}")
        txt_file_dump(
            file=self.output_file,
            contents=string,
        )


class _OutputPyprojectOptionalDeps(_Output):
    output_mode: Literal[OutputModeEnum.optional_dependencies]
    output_file: Optional[str] = None

    def _write_requirements(self, mapped_requirements: OutMappedRequirements):
        array = mapped_requirements.as_toml_array(
            notice=True,
            sources=True,
            sources_compact=False,
            sources_roots=False,
            indent_size=4,
        )
        out_name = self.get_output_extras_name()
        LOGGER.info(
            f"writing optional dependencies: {repr(out_name)} to: {self.output_file}"
        )
        toml_file_replace_array(
            file=self.output_file,
            keys=["project", "optional-dependencies", out_name],
            array=array,
        )


class _OutputPyprojectDeps(_Output):
    output_mode: Literal[OutputModeEnum.dependencies]
    output_file: Optional[str] = None

    def _write_requirements(self, mapped_requirements: OutMappedRequirements):
        array = mapped_requirements.as_toml_array(
            notice=True,
            sources=True,
            sources_compact=False,
            sources_roots=False,
            indent_size=4,
        )
        LOGGER.info(f"writing dependencies to: {self.output_file}")
        toml_file_replace_array(
            file=self.output_file,
            keys=["project", "dependencies"],
            array=array,
        )


CfgResolver = Annotated[
    Union[
        _OutputRequirements,
        _OutputPyprojectOptionalDeps,
        _OutputPyprojectDeps,
    ],
    pydantic.Field(discriminator="output_mode", union_mode="left_to_right"),
]

# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - #
# CONFIG - PACKAGES                                                         #
# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - #


class InvalidRequirementsName(ValueError):
    pass


class InvalidExtrasName(ValueError):
    pass


def normalize_pkg_name(string: str, strict: bool = True):
    """
    Ensure uses "_" instead of "-", and no whitespace. Also convert to lowercase.
    """
    norm = string.replace("-", "_").lower()
    if any(c in norm for c in [" ", "\t", "\n"]):
        raise InvalidRequirementsName(f"Requirements name is invalid: {repr(string)}")
    if norm != string:
        if strict:
            raise InvalidRequirementsName(
                f"Requirements name is invalid: {repr(string)}, should be: {repr(norm)}"
            )
        else:
            warnings.warn(
                f"normalized requirements name from {repr(string)} to {repr(norm)}"
            )
    return norm


def normalize_extras_name(string: str, strict: bool = True):
    """
    Ensure uses "-" instead of "_", and no whitespace. Keeps case.
    """
    norm = string.replace("_", "-")
    if any(c in norm for c in [" ", "\t", "\n"]):
        raise InvalidExtrasName(f"Extras name is invalid: {repr(string)}")
    if norm != string:
        if strict:
            raise InvalidExtrasName(
                f"Extras name is invalid: {repr(string)}, should be: {repr(norm)}"
            )
        else:
            warnings.warn(f"normalized extras name from {repr(string)} to {repr(norm)}")
    return norm


def normalize_import_to_scope_name(string: str, strict: bool = True):
    """
    Ensure instead of "." we use "-", and instead of "*" we use "all".
    """
    norm = string.replace(".", "-").replace("*", "all")
    if norm != string:
        if strict:
            raise ValueError(
                f"import name is invalid: {repr(string)}, should be: {repr(norm)}"
            )
        else:
            warnings.warn(f"normalized import name from {repr(string)} to {repr(norm)}")
    return norm


class CfgVersion(pydantic.BaseModel, extra="forbid", arbitrary_types_allowed=True):
    # the pip install requirement
    requirement: str
    # the imports to replace
    import_: Optional[List[str]] = pydantic.Field(default=None, alias="import")
    scope: Optional[str] = None
    # only apply this import to this environment
    env: str = DEFAULT_REQUIREMENTS_ENV

    @property
    def parsed_requirement(self) -> Requirement:
        return Requirement(self.requirement)

    @property
    def package(self) -> str:
        return normalize_pkg_name(self.parsed_requirement.name, strict=False)

    @classmethod
    def from_string(cls, requirement: str):
        return cls(requirement=requirement)

    def get_import_matcher(self, loaded_scopes: "LoadedScopes") -> ImportMatcherBase:
        if self.scope is not None:
            if self.import_ is not None:
                raise ValueError(f"cannot specify both scope and import for: {self}")
            else:
                return ImportMatcherScope(scope=loaded_scopes[self.scope])
        else:
            if self.import_ is None:
                raise ValueError(f"must specify either scope or import for: {self}")
            else:
                return ImportMatcherGlobs(import_globs=self.import_)

    @pydantic.model_validator(mode="after")
    @classmethod
    def _validate_model_before(cls, v: "CfgVersion"):
        if not str.isidentifier(v.env.replace("-", "_")):
            raise ValueError(
                f"env must be a valid identifier (with hyphens replaced with underscores), got: {v.env}"
            )
        if v.import_ is None and v.scope is None:
            v.import_ = [f"{v.package}.*"]  # wildcard
        elif v.import_ is not None and v.scope is not None:
            raise ValueError(f"cannot specify both scope and import for: {v}")
        return v

    @pydantic.field_validator("import_", mode="before")
    @classmethod
    def _validate_import(cls, v):
        if v is not None:
            if isinstance(v, str):
                v = v.split(",")
        return v


# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - #
# CONFIG - SCOPE                                                            #
# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - #


class _ScopeRules(pydantic.BaseModel, extra="forbid"):

    # Specify how to handle modules that are unreachable, e.g. if there is no `__init__.py`
    # file in all the parents leading up to importing this module. If this is the case
    # then the module/package does not correctly follow python/PEP convention and is
    # technically invalid. By default, for `error`, we raise an exception and do not allow
    # the scope to be created, but this can be relaxed to `skip` or `keep` these files.
    unreachable_mode: Optional[UnreachableModeEnum] = None

    @classmethod
    def make_default_base_rules(cls):
        return _ScopeRules(
            unreachable_mode=UnreachableModeEnum.error,
        )

    def set_defaults(self, defaults: "_ScopeRules"):
        assert defaults.unreachable_mode is not None
        if self.unreachable_mode is None:
            self.unreachable_mode = defaults.unreachable_mode


class CfgScope(_ScopeRules, extra="forbid"):
    # name
    # - must be unique across all scopes & sub-scopes
    name: str

    # parents
    parents: List[str] = pydantic.Field(default_factory=list)

    # search paths
    search_paths: List[str] = pydantic.Field(default_factory=list)
    pkg_paths: List[str] = pydantic.Field(default_factory=list)
    unreachable_mode: Optional[UnreachableModeEnum] = None

    # extra packages
    # packages: List[str] = pydantic.Field(default_factory=list)

    # filtering: limit > exclude > [include!!] (in that order)
    # - order is important because it allows us to remove a band of modules
    #   e.g. limit=foo.bar, exclude=foo.bar.baz, include=foo.bar.baz.qux
    #   if order of include and exclude were swapped, then the exclude would
    #   remove the module after the include added it back in
    limit: Optional[List[str]] = None
    exclude: Optional[List[str]] = None
    # include: Optional[str] = None  # NOT IMPLEMENTED BECAUSE IT IS REDUNDANT, AND `PARENTS` CAN BE USED INSTEAD

    # sub-scopes
    # - name to import path map
    # - names must be unique across all scopes & sub-scopes
    # - imports must belong to the scope
    subscopes: Dict[str, str] = pydantic.Field(default_factory=dict)

    @pydantic.field_validator("search_paths", mode="before")
    @classmethod
    def _validate_search_paths(cls, v):
        return [v] if isinstance(v, str) else v

    @pydantic.field_validator("pkg_paths", mode="before")
    @classmethod
    def _validate_pkg_paths(cls, v):
        return [v] if isinstance(v, str) else v

    @pydantic.field_validator("limit", mode="before")
    @classmethod
    def _validate_limit(cls, v):
        return [v] if isinstance(v, str) else v

    @pydantic.field_validator("exclude", mode="before")
    @classmethod
    def _validate_exclude(cls, v):
        return [v] if isinstance(v, str) else v

    @pydantic.field_validator("subscopes", mode="before")
    @classmethod
    def _validate_subscopes(cls, v):
        # convert list to dict & normalize names
        if isinstance(v, list):
            return {x: normalize_import_to_scope_name(x, strict=False) for x in v}
        return v

    def make_module_scope(self, loaded_scopes: "LoadedScopes" = None):
        m = ModulesScope()

        # 1. load parents
        if self.parents:
            if loaded_scopes is None:
                raise ValueError("loaded_scopes must be provided if parents are used!")
            for parent in self.parents:
                if parent not in loaded_scopes:
                    raise ValueError(
                        f"parent scope {repr(parent)} has not yet been created, are you sure the order of definitions is correct?"
                    )
                m.add_modules_from_scope(loaded_scopes[parent])

        # 2. load new search paths and packages
        for path in self.search_paths:
            m.add_modules_from_search_path(
                Path(path),
                tag=self.name,
                unreachable_mode=self.unreachable_mode,
            )
        for path in self.pkg_paths:
            m.add_modules_from_package_path(
                Path(path),
                tag=self.name,
                unreachable_mode=self.unreachable_mode,
            )

        # 3. add extra packages
        # if self.packages:
        # m.add_modules_from_raw_imports(
        #     imports=self.packages,
        #     tag=self.name,
        # )
        # raise NotImplementedError("extra packages not yet implemented!")

        # 4. filter everything
        # - a. limit, b. exclude, [c. include (replaced with parents)]
        if self.limit:
            m = m.get_restricted_scope(
                imports=self.limit,
                mode=RestrictMode.CHILDREN,
                op=RestrictOp.LIMIT,
            )
        if self.exclude:
            m = m.get_restricted_scope(
                imports=self.exclude,
                mode=RestrictMode.CHILDREN,
                op=RestrictOp.EXCLUDE,
            )

        # done!
        return m


# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - #
# Loaded Scopes                                                             #
# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - #


class UndefinedScopeError(ValueError):
    pass


class LoadedScopes:

    def __init__(self):
        self._scopes = {}

    def __contains__(self, item):
        return item in self._scopes

    def __getitem__(self, item: str) -> ModulesScope:
        if item not in self._scopes:
            raise UndefinedScopeError(
                f"scope {repr(item)} is not defined, must be one of: {self.sorted_names}"
            )
        return self._scopes[item]

    def __setitem__(self, key, value):
        assert isinstance(value, ModulesScope)
        if key in self:
            raise ValueError(f"scope {repr(key)} is already defined!")
        self._scopes[key] = value

    @property
    def sorted_names(self) -> List[str]:
        return sorted(self._scopes.keys())


# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - #
# CONFIG - ROOT                                                             #
# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - #


class PydependenceCfg(pydantic.BaseModel, extra="forbid"):
    # default root is relative to the parent of the pyproject.toml file
    # and is the folder containing the repo of the pyproject.toml file
    default_root: str = "."

    # default write modes
    default_resolve_rules: _ResolveRules = pydantic.Field(
        default_factory=_ResolveRules.make_default_base_rules
    )
    default_scope_rules: _ScopeRules = pydantic.Field(
        default_factory=_ScopeRules.make_default_base_rules
    )

    # package versions
    versions: List[CfgVersion] = pydantic.Field(default_factory=list)

    # resolve
    scopes: List[CfgScope] = pydantic.Field(default_factory=dict)

    # outputs
    resolvers: List[CfgResolver] = pydantic.Field(default_factory=list)

    @pydantic.field_validator("versions", mode="before")
    @classmethod
    def _validate_versions(cls, v, values):
        versions = []
        reqs_envs = set()  # pairs of tags and req names must be unique for now
        for x in v:
            if isinstance(x, str):
                x = CfgVersion.from_string(x)
            else:
                x = CfgVersion.model_validate(x)
            req_env = (x.package, x.env)
            if req_env in reqs_envs:
                raise ValueError(
                    f"requirement {repr(x.package)} and env {repr(x.env)} combination is defined multiple times! ({repr(x.requirement)})"
                )
            reqs_envs.add(req_env)
            versions.append(x)
        return versions

    @pydantic.model_validator(mode="after")
    @classmethod
    def _validate_model(cls, cfg: "PydependenceCfg"):
        # 1. check that scope names are all unique
        scope_names = set()
        for scope in cfg.scopes:
            if scope.name in scope_names:
                raise ValueError(f"scope name {repr(scope.name)} is not unique!")
            scope_names.add(scope.name)

        # 2. check that all sub-scope names are unique
        for scope in cfg.scopes:
            for subscope_name in scope.subscopes:
                if subscope_name in scope_names:
                    raise ValueError(
                        f"sub-scope name {repr(subscope_name)} is not unique!"
                    )
                scope_names.add(subscope_name)

        # 3. check that all packages
        # TODO

        # 4. check that the default root is a relative path
        if Path(cfg.default_root).is_absolute():
            raise ValueError(
                f"default_root must be a relative path, got: {repr(cfg.default_root)}"
            )
        return cfg

    def apply_defaults(self, *, config_path: "Union[str, Path]"):
        """
        config_path is the path to the pyproject.toml file or the toml file that was
        used to load the configuration. This is used to determine the default root path,
        which is the folder containing the config. The default root is then used to
        resolve all relative paths in the configuration.
        """
        config_path = Path(config_path)

        # helper
        self.default_root = apply_root_to_path_str(
            config_path.parent, self.default_root
        )

        def _resolve_path(x: "Union[str, Path]") -> str:
            return apply_root_to_path_str(self.default_root, x)

        # apply to all paths
        for scope in self.scopes:
            scope.search_paths = [_resolve_path(x) for x in scope.search_paths]
            scope.pkg_paths = [_resolve_path(x) for x in scope.pkg_paths]
        for output in self.resolvers:
            if output.output_file is not None:
                output.output_file = _resolve_path(output.output_file)
            if output.output_file is None:
                if isinstance(
                    output, (_OutputPyprojectDeps, _OutputPyprojectOptionalDeps)
                ):
                    output.output_file = _resolve_path(config_path)
            # check kinds
            if isinstance(output, (_OutputPyprojectDeps, _OutputPyprojectOptionalDeps)):
                if Path(output.output_file).name != "pyproject.toml":
                    raise ValueError(
                        f"output_file must be the pyproject.toml file for: {output}"
                    )
            elif isinstance(output, _OutputRequirements):
                if Path(output.output_file).suffix != ".txt":
                    raise ValueError(
                        f"output_file must be requirements*.txt for: {output}"
                    )

        # also apply all default write modes
        self.default_scope_rules.set_defaults(_ScopeRules.make_default_base_rules())
        self.default_resolve_rules.set_defaults(_ResolveRules.make_default_base_rules())
        for scope in self.scopes:
            scope.set_defaults(self.default_scope_rules)
        for output in self.resolvers:
            output.set_defaults(self.default_resolve_rules)

    def load_scopes(self) -> "LoadedScopes":
        # resolve all scopes
        loaded_scopes = LoadedScopes()
        for scope_cfg in self.scopes:
            scope = scope_cfg.make_module_scope(loaded_scopes=loaded_scopes)
            loaded_scopes[scope_cfg.name] = scope
            # now create sub-scopes
            for subcol_name, subcol_import_root in scope_cfg.subscopes.items():
                subscope = scope.get_restricted_scope(
                    imports=[subcol_import_root], mode=RestrictMode.CHILDREN
                )
                loaded_scopes[subcol_name] = subscope
        # done!
        return loaded_scopes

    def make_requirements_mapper(
        self,
        loaded_scopes: "LoadedScopes",
    ):
        env_matchers = defaultdict(list)
        for v in self.versions:
            import_matcher = v.get_import_matcher(loaded_scopes=loaded_scopes)
            pair = ReqMatcher(requirement=v.requirement, matcher=import_matcher)
            env_matchers[v.env].append(pair)
        env_matchers = dict(env_matchers)

        return RequirementsMapper(
            env_matchers=env_matchers,
        )

    def write_all_outputs(self, loaded_scopes: "LoadedScopes"):
        # check that scope output names are unique
        # - output names only need to be unique if they are optional-dependencies!
        # - warn if generally not unique, error if optional-deps not unique
        names_all = set()
        names_optional_deps = set()
        for output in self.resolvers:
            name = output.get_output_extras_name()
            if name in names_all:
                warnings.warn(
                    f"output name {repr(name)} is not unique across all resolvers!"
                )
            names_all.add(name)
            if output.output_mode == OutputModeEnum.optional_dependencies:
                if name in names_optional_deps:
                    raise ValueError(
                        f"output name {repr(name)} is not unique across resolvers for optional dependencies!"
                    )
                names_optional_deps.add(name)

        # check that the scopes exists
        for output in self.resolvers:
            if output.scope is None:
                assert output.start_scope is None
                continue
            if output.scope not in loaded_scopes:
                raise ValueError(
                    f"output scope {repr(output.scope)} does not exist! Are you sure it has been defined? Available scopes: {loaded_scopes.sorted_names}"
                )
            if output.start_scope and output.start_scope not in loaded_scopes:
                raise ValueError(
                    f"output start_scope {repr(output.start_scope)} does not exist! Are you sure it has been defined? Available scopes: {loaded_scopes.sorted_names}"
                )

        # make the mapper
        requirements_mapper = self.make_requirements_mapper(loaded_scopes=loaded_scopes)

        # resolve the scopes!
        for output in self.resolvers:
            output.resolve_generate_and_write_requirements(
                loaded_scopes=loaded_scopes,
                requirements_mapper=requirements_mapper,
            )

    # ... LOADING ...

    @classmethod
    def from_pyproject(cls, path: Path) -> "PydependenceCfg":
        # 1. load pyproject.toml
        toml = load_toml_document(path)
        # 2. validate the model
        pyproject = _PyprojectToml.model_validate(toml.unwrap())
        pydependence = pyproject.tool.pydependence
        # 3. override paths in cfg using the default root
        pydependence.apply_defaults(config_path=path)
        return pydependence

    @classmethod
    def from_toml_config(cls, path: Path) -> "PydependenceCfg":
        # 1. load pyproject.toml
        toml = load_toml_document(path)
        # 2. validate the model
        tool = _PyprojectTomlTools.model_validate(toml.unwrap())
        pydependence = tool.pydependence
        # 3. override paths in cfg using the default root
        pydependence.apply_defaults(config_path=path)
        return pydependence

    @classmethod
    def from_file_automatic(cls, path: Path) -> "PydependenceCfg":
        if path.name == "pyproject.toml":
            return cls.from_pyproject(path)
        elif path.name == ".pydependence.toml":
            return cls.from_toml_config(path)
        elif path.suffix in (".toml", ".cfg"):
            LOGGER.warning(
                f"using legacy extension mode: {repr(path.suffix)}, not explicit file name as one of: 'pyproject.toml' OR '.pydependence.toml'"
            )
            return cls.from_toml_config(path)
        else:
            raise ValueError(f"unsupported file extension: {path.suffix} for: {path}")


# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - #
# CONFIG - PYPROJECT                                                        #
# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - #


class _PyprojectTomlTools(pydantic.BaseModel, extra="ignore"):
    pydependence: PydependenceCfg


class _PyprojectToml(pydantic.BaseModel, extra="ignore"):
    tool: _PyprojectTomlTools = pydantic.Field(default_factory=_PyprojectTomlTools)


# ========================================================================= #
# COLLECT MODULES                                                           #
# ========================================================================= #


def pydeps(
    *,
    config_path: Union[str, Path],
):
    # 1. get absolute
    config_path = Path(config_path).resolve().absolute()
    LOGGER.info(f"loading pydependence config from: {config_path}")
    # 2. load pyproject.toml
    pydependence = PydependenceCfg.from_file_automatic(config_path)
    # 3. generate search spaces, recursively resolving!
    loaded_scopes = pydependence.load_scopes()
    # 4. generate outputs
    pydependence.write_all_outputs(loaded_scopes)


# ========================================================================= #
# END                                                                       #
# ========================================================================= #
