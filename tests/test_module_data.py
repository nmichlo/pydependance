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

from pathlib import Path

import pytest

from pydependence._cli import pydeps
from pydependence._core.module_data import ModuleMetadata
from pydependence._core.module_imports_ast import (
    ImportSourceEnum,
    LocImportInfo,
    ManualImportInfo,
    load_imports_from_module_info,
)
from pydependence._core.module_imports_loader import (
    DEFAULT_MODULE_IMPORTS_LOADER,
    ModuleImports,
)
from pydependence._core.modules_resolver import (
    ScopeNotASubsetError,
    ScopeResolvedImports,
)
from pydependence._core.modules_scope import (
    DuplicateModuleNamesError,
    DuplicateModulePathsError,
    DuplicateModulesError,
    ModulesScope,
    UnreachableModeEnum,
    UnreachableModuleError,
    _find_modules,
)
from pydependence._core.requirements_map import (
    DEFAULT_REQUIREMENTS_ENV,
    ImportMatcherBase,
    ImportMatcherGlob,
    ImportMatcherScope,
    NoConfiguredRequirementMappingError,
    ReqMatcher,
    RequirementsMapper,
)
from pydependence._core.utils import load_toml_document, toml_file_replace_array

# ========================================================================= #
# fixture                                                                   #
# ========================================================================= #


PKGS_ROOT = Path(__file__).parent / "test-packages"

PKGS_ROOT_PYPROJECT = PKGS_ROOT / "pyproject.toml"

PKG_AST_TEST = PKGS_ROOT / "t_ast_parser.py"
PKG_A = PKGS_ROOT / "A"
PKG_B = PKGS_ROOT / "B"
PKG_C = PKGS_ROOT / "C.py"

PKG_A_INVALID = PKGS_ROOT / "A.py"
PKG_B_INVALID = PKGS_ROOT / "B.py"
PKG_C_INVALID = PKGS_ROOT / "C"


@pytest.fixture
def module_info():
    return ModuleMetadata.from_root_and_subpath(
        root=PKGS_ROOT,
        subpath=PKG_AST_TEST,
        tag="test",
    )


# ========================================================================= #
# TESTS - DATA & AST                                                        #
# ========================================================================= #


def test_get_module_imports(module_info):
    # checks
    results = load_imports_from_module_info(module_info)

    a = {
        "asdf.fdsa": [
            LocImportInfo(
                source_name=module_info.name,
                source_module_info=module_info,
                source_type=ImportSourceEnum.import_from,
                target="asdf.fdsa",
                is_lazy=True,
                lineno=13,
                col_offset=4,
                stack_type_names=("Module", "FunctionDef", "ImportFrom"),
                is_relative=False,
            )
        ],
        "buzz": [
            LocImportInfo(
                source_name=module_info.name,
                source_module_info=module_info,
                source_type=ImportSourceEnum.lazy_plugin,
                target="buzz",
                is_lazy=True,
                lineno=16,
                col_offset=7,
                stack_type_names=("Module", "Assign", "Call"),
                is_relative=False,
            )
        ],
        "foo.bar": [
            LocImportInfo(
                source_name=module_info.name,
                source_module_info=module_info,
                source_type=ImportSourceEnum.import_from,
                target="foo.bar",
                is_lazy=False,
                lineno=4,
                col_offset=0,
                stack_type_names=("Module", "ImportFrom"),
                is_relative=False,
            )
        ],
        "json": [
            LocImportInfo(
                source_name=module_info.name,
                source_module_info=module_info,
                source_type=ImportSourceEnum.import_,
                target="json",
                is_lazy=True,
                lineno=10,
                col_offset=4,
                stack_type_names=("Module", "FunctionDef", "Import"),
                is_relative=False,
            )
        ],
        "os": [
            LocImportInfo(
                source_name=module_info.name,
                source_module_info=module_info,
                source_type=ImportSourceEnum.import_,
                target="os",
                is_lazy=False,
                lineno=1,
                col_offset=0,
                stack_type_names=("Module", "Import"),
                is_relative=False,
            )
        ],
        "sys": [
            LocImportInfo(
                source_name=module_info.name,
                source_module_info=module_info,
                source_type=ImportSourceEnum.import_from,
                target="sys",
                is_lazy=False,
                lineno=2,
                col_offset=0,
                stack_type_names=("Module", "ImportFrom"),
                is_relative=False,
            ),
            LocImportInfo(
                source_name=module_info.name,
                source_module_info=module_info,
                source_type=ImportSourceEnum.import_,
                target="sys",
                is_lazy=True,
                lineno=11,
                col_offset=4,
                stack_type_names=("Module", "FunctionDef", "Import"),
                is_relative=False,
            ),
        ],
        "package": [
            LocImportInfo(
                source_name=module_info.name,
                source_module_info=module_info,
                source_type=ImportSourceEnum.import_from,
                target="package",
                is_lazy=False,
                lineno=6,
                col_offset=0,
                stack_type_names=("Module", "ImportFrom"),
                is_relative=True,
            )
        ],
    }

    assert set(results.keys()) == set(a.keys())
    assert results == a

    # checks
    results_2 = DEFAULT_MODULE_IMPORTS_LOADER.load_module_imports(module_info)
    assert set(results_2.module_imports.keys()) == set(a.keys())
    assert results_2.module_imports == a
    assert results_2.module_info == module_info

    results_3 = DEFAULT_MODULE_IMPORTS_LOADER.load_module_imports(module_info)
    assert set(results_3.module_imports.keys()) == set(a.keys())
    assert results_3.module_imports == a
    assert results_3.module_info == module_info

    # check same instance i.e. cache is working!
    assert results_2.module_info is module_info
    assert results_3.module_info is module_info
    assert results_2 is results_3


# ========================================================================= #
# TESTS - FIND MODULES                                                      #
# ========================================================================= #


def test_find_modules_search_path(module_info):
    reachable = {
        "t_ast_parser",
        "A",
        "A.a1",
        "A.a2",
        "A.a3",
        "A.a3.a3i",
        "B",
        "B.b1",
        "B.b2",
        "C",
    }
    unreachable = {
        "A.a4.a4i",
    }
    edges_reachable = {
        ("A", "A.a1"),
        ("A", "A.a2"),
        ("A", "A.a3"),
        ("A.a3", "A.a3.a3i"),
        ("B", "B.b1"),
        ("B", "B.b2"),
    }
    # not included!
    edges_unreachable = {
        ("A.a4", "A.a4.a4i"),
    }

    # load all modules (default)
    results = _find_modules(
        search_paths=[PKGS_ROOT],
        package_paths=None,
        tag="test",
        unreachable_mode=UnreachableModeEnum.keep,
    )
    assert set(results.nodes) == (reachable | unreachable)
    assert set(results.edges) == edges_reachable

    # load only reachable modules
    results = _find_modules(
        search_paths=[PKGS_ROOT],
        package_paths=None,
        tag="test",
        unreachable_mode=UnreachableModeEnum.skip,
    )
    assert set(results.nodes) == reachable
    assert set(results.edges) == edges_reachable

    # error if unreachable
    with pytest.raises(
        UnreachableModuleError, match="Unreachable module found: A.a4.a4i from root: A"
    ):
        _find_modules(
            search_paths=[PKGS_ROOT],
            package_paths=None,
            tag="test",
            unreachable_mode=UnreachableModeEnum.error,
        )

    # load missing
    with pytest.raises(FileNotFoundError):
        _find_modules(
            search_paths=[PKGS_ROOT / "THIS_DOES_NOT_EXIST"],
            package_paths=None,
            tag="test",
            unreachable_mode=UnreachableModeEnum.keep,
        )

    # load file
    assert PKG_AST_TEST.exists() and PKG_AST_TEST.is_file()
    with pytest.raises(NotADirectoryError):
        _find_modules(
            search_paths=[PKG_AST_TEST],
            package_paths=None,
            tag="test",
            unreachable_mode=UnreachableModeEnum.keep,
        )

    # load subdir
    results = _find_modules(
        search_paths=[PKG_A],
        package_paths=None,
        tag="test",
        unreachable_mode=UnreachableModeEnum.keep,
    )
    assert set(results.nodes) == {"a1", "a2", "a3", "a3.a3i", "a4.a4i"}

    # load conflicting modules -- reference same files but different search paths
    with pytest.raises(DuplicateModuleNamesError):
        _find_modules(
            search_paths=[PKGS_ROOT, PKGS_ROOT],
            package_paths=None,
            tag="test",
            unreachable_mode=UnreachableModeEnum.keep,
        )


def test_find_modules_pkg_path():
    reachable_a = {
        "A",
        "A.a1",
        "A.a2",
        "A.a3",
        "A.a3.a3i",
    }
    unreachable_a = {
        "A.a4.a4i",
    }

    # load all modules (default)
    results = _find_modules(
        search_paths=None,
        package_paths=[PKG_A],
        tag="test",
        unreachable_mode=UnreachableModeEnum.keep,
    )
    assert set(results.nodes) == (reachable_a | unreachable_a)

    # load only reachable modules
    results = _find_modules(
        search_paths=None,
        package_paths=[PKG_A],
        tag="test",
        unreachable_mode=UnreachableModeEnum.skip,
    )
    assert set(results.nodes) == reachable_a

    # error if unreachable
    with pytest.raises(
        UnreachableModuleError, match="Unreachable module found: A.a4.a4i from root: A"
    ):
        _find_modules(
            search_paths=None,
            package_paths=[PKG_A],
            tag="test",
            unreachable_mode=UnreachableModeEnum.error,
        )

    # load all
    results = _find_modules(
        search_paths=None,
        package_paths=[PKG_B],
        tag="test",
        unreachable_mode=UnreachableModeEnum.keep,
    )
    assert set(results.nodes) == {"B", "B.b1", "B.b2"}

    results = _find_modules(
        search_paths=None,
        package_paths=[PKG_C],
        tag="test",
        unreachable_mode=UnreachableModeEnum.keep,
    )
    assert set(results.nodes) == {"C"}

    # load invalid
    with pytest.raises(FileNotFoundError):
        _find_modules(
            search_paths=None,
            package_paths=[PKGS_ROOT / "THIS_DOES_NOT_EXIST.py"],
            tag="test",
            unreachable_mode=UnreachableModeEnum.keep,
        )

    # load conflicting modules -- reference same files but different search paths
    with pytest.raises(DuplicateModulePathsError):
        _find_modules(
            search_paths=None,
            package_paths=[PKG_A, PKG_A / "a1.py"],
            tag="test",
            unreachable_mode=UnreachableModeEnum.keep,
        )


# ========================================================================= #
# TESTS - MODULES SCOPES                                                    #
# ========================================================================= #


def test_modules_scope():

    modules_a = {"A", "A.a1", "A.a2", "A.a3", "A.a3.a3i", "A.a4.a4i"}
    modules_b = {"B", "B.b1", "B.b2"}
    modules_c = {"C"}
    modules_all = modules_a | modules_b | modules_c | {"t_ast_parser"}

    scope = ModulesScope()
    scope.add_modules_from_package_path(
        PKG_A, unreachable_mode=UnreachableModeEnum.keep
    )
    assert set(scope.iter_modules()) == modules_a
    # this should not edit the original if it fails
    with pytest.raises(DuplicateModulePathsError):
        scope.add_modules_from_package_path(
            PKG_A / "a1.py", unreachable_mode=UnreachableModeEnum.keep
        )
    with pytest.raises(DuplicateModulePathsError):
        scope.add_modules_from_package_path(
            PKG_A, unreachable_mode=UnreachableModeEnum.keep
        )
    assert set(scope.iter_modules()) == modules_a
    # handle unreachable
    with pytest.raises(UnreachableModuleError):
        scope.add_modules_from_package_path(PKG_A)

    scope = ModulesScope()
    scope.add_modules_from_search_path(
        PKGS_ROOT, unreachable_mode=UnreachableModeEnum.keep
    )
    assert set(scope.iter_modules()) == modules_all

    scope = ModulesScope()
    scope.add_modules_from_raw_imports(imports=["A.a1"], tag="test")
    with pytest.raises(DuplicateModuleNamesError):
        scope.add_modules_from_raw_imports(imports=["A.a1"], tag="test")
    assert set(scope.iter_modules()) == {"A.a1"}

    # merge scopes & check subsets
    scope_all = ModulesScope()
    scope_all.add_modules_from_search_path(
        PKGS_ROOT, unreachable_mode=UnreachableModeEnum.keep
    )
    assert set(scope_all.iter_modules()) == modules_all
    with pytest.raises(UnreachableModuleError):
        scope_all.add_modules_from_search_path(PKGS_ROOT)

    scope_a = ModulesScope()
    scope_a.add_modules_from_package_path(
        PKG_A, unreachable_mode=UnreachableModeEnum.keep
    )
    assert set(scope_a.iter_modules()) == modules_a
    with pytest.raises(UnreachableModuleError):
        scope_a.add_modules_from_package_path(PKG_A)

    scope_b = ModulesScope()
    scope_b.add_modules_from_package_path(PKG_B)
    assert set(scope_b.iter_modules()) == modules_b

    assert scope_all.is_scope_subset(scope_all)
    assert scope_all.is_scope_subset(scope_a)
    assert scope_all.is_scope_subset(scope_b)
    assert not scope_a.is_scope_subset(scope_all)
    assert not scope_b.is_scope_subset(scope_all)
    assert not scope_a.is_scope_equal(scope_all)
    assert not scope_b.is_scope_equal(scope_all)

    # refine
    scope_a_filter = scope_all.get_restricted_scope(imports=["A"])
    assert scope_a_filter.is_scope_subset(scope_a)
    assert scope_a.is_scope_subset(scope_a_filter)
    assert scope_a.is_scope_equal(scope_a_filter)
    assert set(scope_a_filter.iter_modules()) == modules_a

    # check conflcits
    assert scope_all.is_scope_conflicts(scope_a)
    assert scope_all.is_scope_conflicts(scope_b)
    assert scope_a.is_scope_conflicts(scope_all)
    assert scope_b.is_scope_conflicts(scope_all)
    assert not scope_a.is_scope_conflicts(scope_b)
    assert not scope_b.is_scope_conflicts(scope_a)

    # merge scopes
    scope_ab_filter = scope_all.get_restricted_scope(imports=["A", "B"])
    scope_ab_merge = ModulesScope()
    scope_ab_merge.add_modules_from_scope(scope_a)
    scope_ab_merge.add_modules_from_scope(scope_b)
    assert scope_ab_filter.is_scope_equal(scope_ab_merge)
    assert set(scope_ab_filter.iter_modules()) == (modules_a | modules_b)
    assert set(scope_ab_merge.iter_modules()) == (modules_a | modules_b)

    scope_ab_merge.add_modules_from_raw_imports(imports=["C"], tag="test")
    assert not scope_ab_filter.is_scope_equal(scope_ab_merge)
    assert set(scope_ab_merge.iter_modules()) == (modules_a | modules_b | modules_c)

    # restrict modes
    restrict_scope_a = scope_all.get_restricted_scope(imports=["A"])
    assert set(restrict_scope_a.iter_modules()) == modules_a
    restrict_scope_aa = scope_all.get_restricted_scope(imports=["A.a3"])
    assert set(restrict_scope_aa.iter_modules()) == {"A.a3", "A.a3.a3i"}


def test_error_instance_of():
    assert issubclass(DuplicateModuleNamesError, DuplicateModulesError)
    assert issubclass(DuplicateModulePathsError, DuplicateModulesError)
    assert not issubclass(DuplicateModulesError, DuplicateModulePathsError)
    assert not issubclass(DuplicateModulesError, DuplicateModuleNamesError)
    assert not issubclass(DuplicateModuleNamesError, DuplicateModulePathsError)
    assert not issubclass(DuplicateModulePathsError, DuplicateModuleNamesError)


# ========================================================================= #
# TESTS - RESOLVE SCOPES                                                    #
# ========================================================================= #


def test_resolve_scope():
    scope_ast = ModulesScope()
    scope_ast.add_modules_from_package_path(PKG_AST_TEST)

    resolved = ScopeResolvedImports.from_scope(scope=scope_ast)
    assert resolved._get_targets_sources_counts() == {
        "os": {"t_ast_parser": 1},
        "sys": {"t_ast_parser": 2},
        "foo.bar": {"t_ast_parser": 1},
        "package": {"t_ast_parser": 1},
        "json": {"t_ast_parser": 1},
        "asdf.fdsa": {"t_ast_parser": 1},
        "buzz": {"t_ast_parser": 1},
    }

    # lazy should be skipped, even if repeated
    resolved = ScopeResolvedImports.from_scope(scope=scope_ast, visit_lazy=False)
    assert resolved._get_targets_sources_counts() == {
        "os": {"t_ast_parser": 1},
        "sys": {"t_ast_parser": 1},
        "foo.bar": {"t_ast_parser": 1},
        "package": {"t_ast_parser": 1},
    }


def test_resolve_across_scopes():
    scope_all = ModulesScope()
    scope_all.add_modules_from_package_path(
        package_path=PKG_A, unreachable_mode=UnreachableModeEnum.keep
    )
    scope_all.add_modules_from_package_path(package_path=PKG_B)
    scope_all.add_modules_from_package_path(package_path=PKG_C)

    # restrict
    scope_a = scope_all.get_restricted_scope(imports=["A"])
    scope_b = scope_all.get_restricted_scope(imports=["B"])
    scope_c = scope_all.get_restricted_scope(imports=["C"])

    # subscope
    with pytest.raises(ScopeNotASubsetError):
        ScopeResolvedImports.from_scope(scope=scope_c, start_scope=scope_all)

    # >>> ALL <<< #

    resolved_all = ScopeResolvedImports.from_scope(scope=scope_all)
    assert resolved_all._get_targets_sources_counts() == {
        "A.a2": {"A.a1": 1},
        "A.a4.a4i": {"A.a3.a3i": 1},
        "B.b1": {"A.a4.a4i": 1},
        "B.b2": {"A.a2": 1, "A.a3.a3i": 1, "B.b1": 1},
        "C": {"B.b2": 2},
        "extern_C": {"C": 1},
        "extern_a1": {"A.a1": 1},
        "extern_a2": {"A.a2": 2},
        "extern_a3i": {"A.a3.a3i": 1},
        "extern_a4i": {"A.a4.a4i": 1},
        "extern_b1": {"B.b1": 1},
        "extern_b2": {"B.b2": 1},
    }

    # *NB* *NB* *NB* *NB* *NB* *NB* *NB*
    # e.g. this is how we can get all external deps for a project with multiple packages
    assert resolved_all.get_filtered()._get_targets_sources_counts() == {
        "extern_a1": {"A.a1": 1},
        "extern_a2": {"A.a2": 2},
        "extern_a3i": {"A.a3.a3i": 1},
        "extern_a4i": {"A.a4.a4i": 1},
        "extern_b1": {"B.b1": 1},
        "extern_b2": {"B.b2": 1},
        "extern_C": {"C": 1},
    }

    # >>> A <<< #

    resolved_a = ScopeResolvedImports.from_scope(scope=scope_a)
    assert resolved_a._get_targets_sources_counts() == {
        "A.a2": {"A.a1": 1},
        "A.a4.a4i": {"A.a3.a3i": 1},
        "B.b1": {"A.a4.a4i": 1},
        "B.b2": {"A.a2": 1, "A.a3.a3i": 1},
        "extern_a1": {"A.a1": 1},
        "extern_a2": {"A.a2": 2},
        "extern_a3i": {"A.a3.a3i": 1},
        "extern_a4i": {"A.a4.a4i": 1},
    }

    # *NB* *NB* *NB* *NB* *NB* *NB* *NB*
    # e.g. this is how we can get external deps for the current package, and all its internal deps
    assert resolved_a.get_filtered()._get_targets_sources_counts() == {
        "B.b1": {"A.a4.a4i": 1},
        "B.b2": {"A.a2": 1, "A.a3.a3i": 1},
        "extern_a1": {"A.a1": 1},
        "extern_a2": {"A.a2": 2},
        "extern_a3i": {"A.a3.a3i": 1},
        "extern_a4i": {"A.a4.a4i": 1},
    }

    resolved_all_a = ScopeResolvedImports.from_scope(
        scope=scope_all, start_scope=scope_a
    )
    assert resolved_all_a._get_targets_sources_counts() == {
        "A.a2": {"A.a1": 1},
        "A.a4.a4i": {"A.a3.a3i": 1},
        "B.b1": {"A.a4.a4i": 1},
        "B.b2": {"A.a2": 1, "A.a3.a3i": 1, "B.b1": 1},
        "C": {"B.b2": 2},
        "extern_C": {"C": 1},
        "extern_a1": {"A.a1": 1},
        "extern_a2": {"A.a2": 2},
        "extern_a3i": {"A.a3.a3i": 1},
        "extern_a4i": {"A.a4.a4i": 1},
        "extern_b1": {"B.b1": 1},
        "extern_b2": {"B.b2": 1},
    }
    # *NB* *NB* *NB* *NB* *NB* *NB* *NB*
    # e.g. this is how we can get external deps for the current package, resolved across the current project, WITHOUT internal deps
    assert resolved_all_a.get_filtered()._get_targets_sources_counts() == {
        "extern_a1": {"A.a1": 1},
        "extern_a2": {"A.a2": 2},
        "extern_a3i": {"A.a3.a3i": 1},
        "extern_a4i": {"A.a4.a4i": 1},
        "extern_b1": {"B.b1": 1},
        "extern_b2": {"B.b2": 1},
        "extern_C": {"C": 1},
    }

    # >>> B <<< #

    resolved_b = ScopeResolvedImports.from_scope(scope=scope_b)
    assert resolved_b._get_targets_sources_counts() == {
        "B.b2": {"B.b1": 1},
        "C": {"B.b2": 2},
        "extern_b1": {"B.b1": 1},
        "extern_b2": {"B.b2": 1},
    }
    assert resolved_b.get_filtered()._get_targets_sources_counts() == {
        "C": {"B.b2": 2},
        "extern_b1": {"B.b1": 1},
        "extern_b2": {"B.b2": 1},
    }

    resolved_all_b = ScopeResolvedImports.from_scope(
        scope=scope_all, start_scope=scope_b
    )
    assert resolved_all_b._get_targets_sources_counts() == {
        "B.b2": {"B.b1": 1},
        "C": {"B.b2": 2},
        "extern_C": {"C": 1},
        "extern_b1": {"B.b1": 1},
        "extern_b2": {"B.b2": 1},
    }
    assert resolved_all_b.get_filtered()._get_targets_sources_counts() == {
        "extern_b1": {"B.b1": 1},
        "extern_b2": {"B.b2": 1},
        "extern_C": {"C": 1},
    }

    # >>> C <<< #

    resolved_c = ScopeResolvedImports.from_scope(scope=scope_c)
    assert resolved_c._get_targets_sources_counts() == {
        "extern_C": {"C": 1},  #
    }
    assert resolved_c.get_filtered()._get_targets_sources_counts() == {
        "extern_C": {"C": 1},
    }

    resolved_all_c = ScopeResolvedImports.from_scope(
        scope=scope_all, start_scope=scope_c
    )
    assert resolved_all_c._get_targets_sources_counts() == {
        "extern_C": {"C": 1},  #
    }
    assert resolved_all_c.get_filtered()._get_targets_sources_counts() == {
        "extern_C": {"C": 1},
    }


# ========================================================================= #
# TESTS - REQUIREMENT REPLACEMENT                                           #
# ========================================================================= #


def test_import_matchers():
    scope_a = ModulesScope()
    scope_a.add_modules_from_package_path(
        PKG_A, unreachable_mode=UnreachableModeEnum.keep
    )
    scope_b = ModulesScope()
    scope_b.add_modules_from_package_path(PKG_B)

    # SCOPE
    matcher_scope = ImportMatcherScope(scope=scope_a)
    # - contains
    assert matcher_scope.match("A")
    assert matcher_scope.match("A.a1")
    assert not matcher_scope.match("A.a1.asdf")
    for module in scope_a.iter_modules():
        assert matcher_scope.match(module)
    # - does not contain
    assert not matcher_scope.match("B")
    for module in scope_b.iter_modules():
        assert not matcher_scope.match(module)

    # GLOB
    matcher_glob = ImportMatcherGlob("A.*")
    # - contains
    assert matcher_glob.match("A")
    assert matcher_glob.match("A.a1")
    assert matcher_glob.match("A.a1.asdf")
    for module in scope_a.iter_modules():
        assert matcher_glob.match(module)
    # - does not contain
    assert not matcher_glob.match("B")
    for module in scope_b.iter_modules():
        assert not matcher_glob.match(module)

    # GLOB EXACT
    matcher_glob = ImportMatcherGlob("A")
    assert matcher_glob.match("A")
    assert not matcher_glob.match("A.a1")
    assert not matcher_glob.match("A.a1.asdf")

    # GLOB
    matcher_glob = ImportMatcherGlob("A.*")
    assert matcher_glob.match("A")  # TODO: this is maybe unintuitive?
    assert matcher_glob.match("A.a1")
    assert matcher_glob.match("A.a1.asdf")

    # GLOB NESTED
    matcher_glob = ImportMatcherGlob("A.a1.*")
    assert not matcher_glob.match("A")
    assert matcher_glob.match("A.a1")
    assert matcher_glob.match("A.a1.asdf")

    # INVALID
    with pytest.raises(ValueError):
        ImportMatcherGlob("A.*.*")
    with pytest.raises(ValueError):
        ImportMatcherGlob("*")
    with pytest.raises(ValueError):
        ImportMatcherGlob(".*")
    with pytest.raises(ValueError):
        ImportMatcherGlob("A.")
    with pytest.raises(ValueError):
        ImportMatcherGlob("asdf-fdsa")


def test_requirement_mapping():
    scope_all = ModulesScope().add_modules_from_search_path(
        PKGS_ROOT, unreachable_mode=UnreachableModeEnum.keep
    )
    scope_a = scope_all.get_restricted_scope(imports=["A"])
    scope_b = scope_all.get_restricted_scope(imports=["B"])

    mapper = RequirementsMapper(
        env_matchers={
            "default": [
                ReqMatcher("glob_Aa3", ImportMatcherGlob("A.a3.*")),
                ReqMatcher("glob_Aa4", ImportMatcherGlob("A.a4.a4i")),
                ReqMatcher("glob_A", ImportMatcherGlob("A.*")),
                ReqMatcher("glob_Aa2", ImportMatcherGlob("A.a2.*")),
                ReqMatcher("scope_b", ImportMatcherScope(scope=scope_b)),
                ReqMatcher("scope_a", ImportMatcherScope(scope=scope_a)),
                ReqMatcher("scope_all", ImportMatcherScope(scope=scope_all)),
            ],
            "asdf": [
                ReqMatcher("ALT_glob_Aa3", ImportMatcherGlob("A.a3.*")),
                ReqMatcher("ALT_glob_asdf", ImportMatcherGlob("asdf.*")),
            ],
        }
    )

    # test
    m = lambda x: mapper.map_import_to_requirement(x, requirements_env="default")
    # in order:
    assert m("A.a3.a3i") == "glob_Aa3"
    assert m("A.a4") == "glob_A"
    assert m("A.a4.a4i") == "glob_Aa4"
    assert m("A.a1") == "glob_A"
    assert m("A.a2") == "glob_A"  # != glob_Aa2
    assert m("B.b1") == "scope_b"
    assert m("A.a1") == "glob_A"  # != scope_a
    assert m("C") == "scope_all"
    assert m("asdf.fdsa") == "asdf"  # take root

    # test alt
    m = lambda x: mapper.map_import_to_requirement(x, requirements_env="asdf")
    # in order:
    assert m("A.a3.a3i") == "ALT_glob_Aa3"
    assert m("A.a4") == "glob_A"
    assert m("A.a4.a4i") == "glob_Aa4"
    assert m("A.a1") == "glob_A"
    assert m("A.a2") == "glob_A"  # != glob_Aa2
    assert m("B.b1") == "scope_b"
    assert m("A.a1") == "glob_A"  # != scope_a
    assert m("C") == "scope_all"
    assert m("asdf.fdsa") == "ALT_glob_asdf"  # take root

    # test strict
    mapped = mapper.map_import_to_requirement("INVALID.IMPORT", strict=False)
    assert mapped == "INVALID"
    with pytest.raises(
        NoConfiguredRequirementMappingError,
        match="could not find a mapped requirement for import: 'INVALID.IMPORT'",
    ):
        mapper.map_import_to_requirement("INVALID.IMPORT", strict=True)


# ========================================================================= #
# TESTS - REQUIREMENT GENERATION                                            #
# ========================================================================= #


@pytest.fixture
def mapper():
    return RequirementsMapper(
        env_matchers={
            "default": [
                ReqMatcher("glob_B", ImportMatcherGlob("B.*")),
                ReqMatcher("glob_extern", ImportMatcherGlob("extern_a1.*")),
                ReqMatcher("glob_extern", ImportMatcherGlob("extern_a2.*")),
                ReqMatcher("glob_extern", ImportMatcherGlob("extern_a3i.*")),
                ReqMatcher("glob_extern", ImportMatcherGlob("extern_b1.*")),
                ReqMatcher("glob_extern", ImportMatcherGlob("extern_b2.*")),
                ReqMatcher("glob_extern", ImportMatcherGlob("extern_C.*")),
                # purposely wrong, correct is `extern_a4i`
                ReqMatcher("glob_extern_WRONG", ImportMatcherGlob("extern_a4.*")),
                ReqMatcher("glob_manual1", ImportMatcherGlob("manual1.*")),
            ],
            "asdf": [
                ReqMatcher("glob_extern", ImportMatcherGlob("extern_a4i.*")),
            ],
        }
    )


def test_requirements_list_generation(mapper: RequirementsMapper):
    scope_all = ModulesScope().add_modules_from_search_path(
        PKGS_ROOT, unreachable_mode=UnreachableModeEnum.keep
    )
    scope_a = scope_all.get_restricted_scope(imports=["A"])

    # >>> SCOPE A <<< #

    imports = scope_a.resolve_imports()

    mapped = mapper.generate_output_requirements(imports)
    assert mapped._get_debug_struct() == [
        ("extern_a4i", ["A.a4.a4i"]),
        ("glob_B", ["A.a2", "A.a3.a3i", "A.a4.a4i"]),
        ("glob_extern", ["A.a1", "A.a2", "A.a3.a3i"]),
    ]

    mapped = mapper.generate_output_requirements(imports, requirements_env="asdf")
    assert mapped._get_debug_struct() == [
        ("glob_B", ["A.a2", "A.a3.a3i", "A.a4.a4i"]),
        ("glob_extern", ["A.a1", "A.a2", "A.a3.a3i", "A.a4.a4i"]),
    ]

    # >>> SCOPE ALL <<< #

    imports = scope_all.resolve_imports()

    mapped = mapper.generate_output_requirements(imports)
    assert mapped._get_debug_struct() == [
        ("asdf", ["t_ast_parser"]),
        ("buzz", ["t_ast_parser"]),
        ("extern_a4i", ["A.a4.a4i"]),
        ("foo", ["t_ast_parser"]),
        ("glob_extern", ["A.a1", "A.a2", "A.a3.a3i", "B.b1", "B.b2", "C"]),
        ("package", ["t_ast_parser"]),
    ]

    mapped = mapper.generate_output_requirements(imports, requirements_env="asdf")
    assert mapped._get_debug_struct() == [
        ("asdf", ["t_ast_parser"]),
        ("buzz", ["t_ast_parser"]),
        ("foo", ["t_ast_parser"]),
        ("glob_extern", ["A.a1", "A.a2", "A.a3.a3i", "A.a4.a4i", "B.b1", "B.b2", "C"]),
        ("package", ["t_ast_parser"]),
    ]

    # >>> SCOPE ALL, FROM SCOPE A <<< #

    imports = scope_all.resolve_imports(start_scope=scope_a)
    mapped = mapper.generate_output_requirements(imports, requirements_env="asdf")
    assert mapped._get_debug_struct() == [
        ("glob_extern", ["A.a1", "A.a2", "A.a3.a3i", "A.a4.a4i", "B.b1", "B.b2", "C"]),
    ]

    imports = scope_all.resolve_imports(
        start_scope=scope_a, exclude_in_search_space=False
    )
    mapped = mapper.generate_output_requirements(imports, requirements_env="asdf")
    assert mapped._get_debug_struct() == [
        ("A", ["A.a1", "A.a3.a3i"]),
        ("C", ["B.b2"]),
        ("glob_B", ["A.a2", "A.a3.a3i", "A.a4.a4i", "B.b1"]),
        ("glob_extern", ["A.a1", "A.a2", "A.a3.a3i", "A.a4.a4i", "B.b1", "B.b2", "C"]),
    ]

    # >>> SCOPE ALL, FILTERED <<< #

    imports = scope_all.resolve_imports(
        exclude_in_search_space=False, exclude_builtins=False
    )
    mapped = mapper.generate_output_requirements(imports, requirements_env="asdf")
    assert mapped._get_debug_struct() == [
        ("A", ["A.a1", "A.a3.a3i"]),
        ("C", ["B.b2"]),
        ("asdf", ["t_ast_parser"]),
        ("buzz", ["t_ast_parser"]),
        ("foo", ["t_ast_parser"]),
        ("glob_B", ["A.a2", "A.a3.a3i", "A.a4.a4i", "B.b1"]),
        ("glob_extern", ["A.a1", "A.a2", "A.a3.a3i", "A.a4.a4i", "B.b1", "B.b2", "C"]),
        ("json", ["t_ast_parser"]),
        ("os", ["t_ast_parser"]),
        ("package", ["t_ast_parser"]),
        ("sys", ["t_ast_parser"]),
    ]

    imports = scope_all.resolve_imports(
        exclude_in_search_space=True, exclude_builtins=False
    )
    mapped = mapper.generate_output_requirements(imports, requirements_env="asdf")
    assert mapped._get_debug_struct() == [
        ("asdf", ["t_ast_parser"]),
        ("buzz", ["t_ast_parser"]),
        ("foo", ["t_ast_parser"]),
        # appears wrong, but is correct
        ("glob_extern", ["A.a1", "A.a2", "A.a3.a3i", "A.a4.a4i", "B.b1", "B.b2", "C"]),
        ("json", ["t_ast_parser"]),
        ("os", ["t_ast_parser"]),
        ("package", ["t_ast_parser"]),
        ("sys", ["t_ast_parser"]),
    ]

    imports = scope_all.resolve_imports(
        exclude_in_search_space=True,
        exclude_builtins=True,
        visit_lazy=False,
    )
    mapped = mapper.generate_output_requirements(imports, requirements_env="asdf")
    assert mapped._get_debug_struct() == [
        ("foo", ["t_ast_parser"]),
        ("glob_extern", ["A.a1", "A.a2", "A.a3.a3i", "A.a4.a4i", "C"]),
        ("package", ["t_ast_parser"]),
    ]


# ========================================================================= #
# TESTS - REQUIREMENT WRITING                                               #
# ========================================================================= #


def test_requirements_txt_gen(mapper: RequirementsMapper):
    scope_all = ModulesScope().add_modules_from_search_path(
        PKGS_ROOT, unreachable_mode=UnreachableModeEnum.keep
    )

    # >>> GENERATE REQUIREMENTS <<< #

    imports = scope_all.resolve_imports(
        start_scope=None,
        exclude_in_search_space=True,
        exclude_builtins=True,
        exclude_unvisited=True,
        visit_lazy=False,
    )
    mapped = mapper.generate_output_requirements(
        imports,
        requirements_env="asdf",
    )

    # >>> OUTPUT REQUIREMENTS <<< #

    assert mapped.as_requirements_txt(
        notice=False,
        sources=False,
        sources_compact=True,
        sources_roots=True,
        indent_size=4,
    ) == ("foo\n" "glob_extern\n" "package\n")

    assert mapped.as_requirements_txt(
        notice=True,
        sources=False,
        sources_compact=True,
        sources_roots=True,
        indent_size=4,
    ) == (
        "[AUTOGEN] by pydependence **DO NOT EDIT** [AUTOGEN]\n"
        "foo\n"
        "glob_extern\n"
        "package\n"
    )

    assert mapped.as_requirements_txt(
        notice=False,
        sources=True,
        sources_compact=True,
        sources_roots=True,
        indent_size=4,
    ) == ("foo # t_ast_parser\n" "glob_extern # A, C\n" "package # t_ast_parser\n")

    assert mapped.as_requirements_txt(
        notice=False,
        sources=True,
        sources_compact=True,
        sources_roots=False,
        indent_size=4,
    ) == (
        "foo # t_ast_parser\n"
        "glob_extern # A.a1, A.a2, A.a3.a3i, A.a4.a4i, C\n"
        "package # t_ast_parser\n"
    )

    assert mapped.as_requirements_txt(
        notice=False,
        sources=True,
        sources_compact=False,
        sources_roots=True,
        indent_size=4,
    ) == (
        "foo\n"
        "    # ← t_ast_parser\n"
        "glob_extern\n"
        "    # ← A\n"
        "    # ← C\n"
        "package\n"
        "    # ← t_ast_parser\n"
    )

    assert mapped.as_requirements_txt(
        notice=False,
        sources=True,
        sources_compact=False,
        sources_roots=False,
        indent_size=4,
    ) == (
        "foo\n"
        "    # ← t_ast_parser\n"
        "glob_extern\n"
        "    # ← A.a1\n"
        "    # ← A.a2\n"
        "    # ← A.a3.a3i\n"
        "    # ← A.a4.a4i\n"
        "    # ← C\n"
        "package\n"
        "    # ← t_ast_parser\n"
    )


def test_toml_array_gen(mapper: RequirementsMapper):
    scope_all = ModulesScope().add_modules_from_search_path(
        PKGS_ROOT, unreachable_mode=UnreachableModeEnum.keep
    )

    # >>> GENERATE REQUIREMENTS <<< #

    imports = scope_all.resolve_imports(
        start_scope=None,
        exclude_in_search_space=True,
        exclude_builtins=True,
        exclude_unvisited=True,
        visit_lazy=False,
    )
    mapped = mapper.generate_output_requirements(
        imports,
        requirements_env="asdf",
    )

    # >>> OUTPUT REQUIREMENTS <<< #

    assert mapped.as_toml_array(
        notice=False,
        sources=False,
        sources_compact=True,
        sources_roots=True,
        indent_size=4,
    ).as_string() == (
        "[\n" '    "foo",\n' '    "glob_extern",\n' '    "package",\n' "]"
    )

    assert mapped.as_toml_array(
        notice=True,
        sources=False,
        sources_compact=True,
        sources_roots=True,
        indent_size=4,
    ).as_string() == (
        "[\n"
        "    # [AUTOGEN] by pydependence **DO NOT EDIT** [AUTOGEN]\n"
        '    "foo",\n'
        '    "glob_extern",\n'
        '    "package",\n'
        "]"
    )

    assert mapped.as_toml_array(
        notice=False,
        sources=True,
        sources_compact=True,
        sources_roots=True,
        indent_size=4,
    ).as_string() == (
        "[\n"
        '    "foo", # t_ast_parser\n'
        '    "glob_extern", # A, C\n'
        '    "package", # t_ast_parser\n'
        "]"
    )

    assert mapped.as_toml_array(
        notice=False,
        sources=True,
        sources_compact=True,
        sources_roots=False,
        indent_size=4,
    ).as_string() == (
        "[\n"
        '    "foo", # t_ast_parser\n'
        '    "glob_extern", # A.a1, A.a2, A.a3.a3i, A.a4.a4i, C\n'
        '    "package", # t_ast_parser\n'
        "]"
    )

    # NOTE: bug in tomlkit prevents indents from being applied to comments when array is not in a table?
    assert mapped.as_toml_array(
        notice=False,
        sources=True,
        sources_compact=False,
        sources_roots=True,
        indent_size=4,
    ).as_string() == (
        "[\n"
        '    "foo",\n'
        "    # ← t_ast_parser\n"
        '    "glob_extern",\n'
        "    # ← A\n"
        "    # ← C\n"
        '    "package",\n'
        "    # ← t_ast_parser\n"
        "]"
    )

    # NOTE: bug in tomlkit prevents indents from being applied to comments when array is not in a table?
    assert mapped.as_toml_array(
        notice=False,
        sources=True,
        sources_compact=False,
        sources_roots=False,
        indent_size=4,
    ).as_string() == (
        "[\n"
        '    "foo",\n'
        "    # ← t_ast_parser\n"
        '    "glob_extern",\n'
        "    # ← A.a1\n"
        "    # ← A.a2\n"
        "    # ← A.a3.a3i\n"
        "    # ← A.a4.a4i\n"
        "    # ← C\n"
        '    "package",\n'
        "    # ← t_ast_parser\n"
        "]"
    )

    # >>> OUTPUT REQUIREMENTS WITH MANUAL ADDITIONS <<< #

    # update!
    mapped = mapper.generate_output_requirements(
        imports
        + [
            ManualImportInfo.from_target("manual2_no_match"),
            ManualImportInfo.from_target("manual1"),
        ],
        requirements_env="asdf",
    )

    # NOTE: bug in tomlkit prevents indents from being applied to comments when array is not in a table?
    assert mapped.as_toml_array(
        notice=False,
        sources=True,
        sources_compact=False,
        sources_roots=False,
        indent_size=4,
    ).as_string() == (
        "[\n"
        '    "foo",\n'
        "    # ← t_ast_parser\n"
        '    "glob_extern",\n'
        "    # ← A.a1\n"
        "    # ← A.a2\n"
        "    # ← A.a3.a3i\n"
        "    # ← A.a4.a4i\n"
        "    # ← C\n"
        '    "glob_manual1", # [M]\n'
        "    # ← <manual: manual1>\n"
        '    "manual2_no_match", # [M]\n'
        "    # ← <manual: manual2_no_match>\n"
        '    "package",\n'
        "    # ← t_ast_parser\n"
        "]"
    )


# ========================================================================= #
# TEST CLI                                                                  #
# ========================================================================= #


def test_pydeps_cli():
    import tomlkit

    TARGET_PROJECT_DEPS = [
        "asdf",
        "extern_C",
        "foo",
        "package",
    ]
    TARGET_OPTIONAL_DEPS = [
        "asdf",
        "buzz",
        "extern_C",
        "extern_b1",
        "extern_b2",
        "foo",
        "package",
    ]

    doc = load_toml_document(PKGS_ROOT_PYPROJECT)

    # load original document
    orig_project_deps = doc["project"]["dependencies"]
    orig_optional_deps = doc["project"]["optional-dependencies"]["all"]
    assert orig_project_deps.unwrap() == TARGET_PROJECT_DEPS
    assert orig_optional_deps.unwrap() == TARGET_OPTIONAL_DEPS

    # replace arrays
    toml_file_replace_array(
        file=PKGS_ROOT_PYPROJECT,
        keys=["project", "dependencies"],
        array=tomlkit.array(),
    )
    toml_file_replace_array(
        file=PKGS_ROOT_PYPROJECT,
        keys=["project", "optional-dependencies", "all"],
        array=tomlkit.array(),
    )

    # load modified document
    doc = load_toml_document(PKGS_ROOT_PYPROJECT)
    reset_project_deps = doc["project"]["dependencies"]
    reset_optional_deps = doc["project"]["optional-dependencies"]["all"]
    assert reset_project_deps.unwrap() == []
    assert reset_optional_deps.unwrap() == []

    # run cli
    pydeps(PKGS_ROOT_PYPROJECT)

    # load modified document
    doc = load_toml_document(PKGS_ROOT_PYPROJECT)
    new_project_deps = doc["project"]["dependencies"]
    new_optional_deps = doc["project"]["optional-dependencies"]["all"]
    assert new_project_deps.unwrap() == TARGET_PROJECT_DEPS
    assert new_optional_deps.unwrap() == TARGET_OPTIONAL_DEPS


# ========================================================================= #
# END                                                                       #
# ========================================================================= #
