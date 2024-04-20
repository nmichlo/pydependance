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
from collections import defaultdict
from enum import Enum
from typing import Dict, List, Optional

from pydependence._core.builtin import BUILTIN_MODULE_NAMES
from pydependence._core.module_imports_ast import LocImportInfo
from pydependence._core.modules_resolver import ScopeResolvedImports
from pydependence._core.modules_scope import ModulesScope
from pydependence._core.requirements_map import (
    NoConfiguredRequirementMappingError,
    RequirementsMapper,
)

# ========================================================================= #
# REQUIREMENTS WRITER                                                       #
# ========================================================================= #


class WriteMode(str, Enum):
    include = "include"
    comment = "comment"
    exclude = "exclude"

    @property
    def priority(self) -> int:
        return _WRITE_PRIORITIES[self]


_WRITE_PRIORITIES = {
    WriteMode.include: 0,
    WriteMode.comment: 1,
    WriteMode.exclude: 2,
}


class WriteLevel(str, Enum):
    start_scope = "start_scope"
    parent_scope = "parent_scope"
    external = "external"
    none = "none"

    @property
    def level(self) -> int:
        return _WRITE_LEVELS[self]


_WRITE_LEVELS = {
    WriteLevel.start_scope: 0,
    WriteLevel.parent_scope: 1,
    WriteLevel.external: 2,
    WriteLevel.none: 3,
}


@dataclasses.dataclass
class WriteRules:
    write_mode_is_builtin: WriteMode
    write_mode_start_scope: WriteMode
    # write_level_exclude: WriteLevel
    # write_level_comment: WriteLevel
    write_mode_is_lazy: WriteMode


# ========================================================================= #
# REQUIREMENTS GENERATOR                                                    #
# ========================================================================= #


@dataclasses.dataclass
class WriteRequirementSourceModule:
    source_module: str
    source_module_imports: List[LocImportInfo]
    target_imports: List[str]

    # debugging
    all_lazy: bool
    any_target_in_parent_scope: bool
    any_target_in_start_scope: bool
    any_source_in_parent_scope: bool
    any_source_in_start_scope: bool
    is_builtin: bool

    # actual write mode
    write_mode: WriteMode

    def apply_write_rules(self, rules: WriteRules):
        mode = self.write_mode
        if self.is_builtin:
            mode = max(mode, rules.write_mode_is_builtin, key=lambda x: x.priority)
        if self.all_lazy:
            mode = max(mode, rules.write_mode_is_lazy, key=lambda x: x.priority)
        self.write_mode = mode
        return self


@dataclasses.dataclass
class WriteRequirement:
    requirement: str
    source_modules: List[WriteRequirementSourceModule]

    # debugging
    is_builtin: bool

    # actual write mode
    write_mode: WriteMode

    @property
    def all_lazy(self):
        return all(x.all_lazy for x in self.source_modules)

    @property
    def any_target_in_parent_scope(self) -> bool:
        return any(x.any_target_in_parent_scope for x in self.source_modules)

    @property
    def any_target_in_start_scope(self) -> bool:
        return any(x.any_target_in_start_scope for x in self.source_modules)

    @property
    def any_source_in_parent_scope(self) -> bool:
        return any(x.any_source_in_parent_scope for x in self.source_modules)

    @property
    def any_source_in_start_scope(self) -> bool:
        return any(x.any_source_in_start_scope for x in self.source_modules)

    def apply_write_rules(self, rules: WriteRules):
        mode = self.write_mode
        if self.is_builtin:
            mode = max(mode, rules.write_mode_is_builtin, key=lambda x: x.priority)
        if self.any_target_in_start_scope:
            mode = max(mode, rules.write_mode_start_scope, key=lambda x: x.priority)
        if self.all_lazy:
            mode = max(mode, rules.write_mode_is_lazy, key=lambda x: x.priority)
        self.write_mode = mode
        return self


def generate_output_requirements(
    scope: ModulesScope,
    start_scope: Optional[ModulesScope],
    requirements_mapper: RequirementsMapper,
    requirements_env: str,
    write_rules: WriteRules,
) -> "List[WriteRequirement]":
    if start_scope is None:
        start_scope = scope

    # resolve
    resolved_explicit = ScopeResolvedImports.from_scope(
        scope=scope,
        start_scope=start_scope,
        skip_lazy=True,
    )
    resolved_all = ScopeResolvedImports.from_scope(
        scope=scope,
        start_scope=start_scope,
        skip_lazy=False,
    )

    # 1. get imports
    # - assert imports is a subset of imports_lazy
    # {module: {source: [import_info, ...], ...}, ...}
    imports_explicit = resolved_explicit.get_imports_sources()
    imports_all = resolved_all.get_imports_sources()
    extra = set(imports_explicit.keys()) - set(imports_all.keys())
    if extra:
        raise RuntimeError(
            f"imports_explicit must be a subset of imports_all, got extra imports: {extra}"
        )

    # 2. collect imports under requirements, BUT don't map builtins
    # {requirement: {source: [import_info, ...], ...}, ...}
    requirements_all: "Dict[str, Dict[str, List[LocImportInfo]]]" = defaultdict(
        lambda: defaultdict(list)
    )
    errors = []
    for imp in sorted(imports_all.keys()):
        # - map import to requirement
        try:
            if imp in BUILTIN_MODULE_NAMES:
                requirement = imp
            else:
                requirement = requirements_mapper.map_import_to_requirement(
                    imp,
                    requirements_env=requirements_env,
                )
            # - add to requirements
            for source, import_infos in imports_all[imp].items():
                assert {t.target for t in import_infos} == {imp}
                requirements_all[requirement][source].extend(import_infos)
        except NoConfiguredRequirementMappingError as e:
            errors.append(e)
    if errors:
        err_imports = {imp for e in errors for imp in e.imports}
        err_roots = {imp.split(".")[0] for imp in err_imports}
        raise NoConfiguredRequirementMappingError(
            msg=f"could not find mapped requirements for, roots: {sorted(err_roots)}, or full imports: {sorted(err_imports)}",
            imports=err_imports,
        )

    # 3. generate write imports & apply write rules
    write_reqs: "List[WriteRequirement]" = []
    for requirement in sorted(requirements_all.keys()):
        # {source: [import_info, ...], ...}
        requirement_sources = requirements_all[requirement]

        # - generate requirement sources
        source_modules = []
        for source in sorted(requirement_sources.keys()):
            target_imports = sorted({t.target for t in requirement_sources[source]})
            write_src = WriteRequirementSourceModule(
                source_module=source,
                source_module_imports=requirement_sources[source],
                target_imports=target_imports,
                all_lazy=all(v.is_lazy for v in requirement_sources[source]),
                any_source_in_parent_scope=scope.has_module(source),
                any_source_in_start_scope=start_scope.has_module(source),
                any_target_in_parent_scope=any(
                    scope.has_module(t) for t in target_imports
                ),
                any_target_in_start_scope=any(
                    start_scope.has_module(t) for t in target_imports
                ),
                is_builtin=source in BUILTIN_MODULE_NAMES,
                write_mode=WriteMode.include,
            )
            write_src.apply_write_rules(write_rules)
            source_modules.append(write_src)

        # - generate requirement
        write_req = WriteRequirement(
            requirement=requirement,
            source_modules=source_modules,
            is_builtin=requirement in BUILTIN_MODULE_NAMES,
            write_mode=WriteMode.include,
        )
        write_req.apply_write_rules(write_rules)
        write_reqs.append(write_req)

    # done!
    return write_reqs
