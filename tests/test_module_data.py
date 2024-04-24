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

from pydependence._core.module_data import ModuleMetadata
from pydependence._core.module_imports_ast import (
    LocImportInfo,
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
    ImportMatcherBase,
    ImportMatcherGlob,
    ImportMatcherScope,
    RequirementsMapper,
)

# ========================================================================= #
# fixture                                                                   #
# ========================================================================= #


PKGS_ROOT = Path(__file__).parent / "test-packages"

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
                source_module_info=module_info,
                source="import_from",
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
                source_module_info=module_info,
                source="lazy_plugin",
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
                source_module_info=module_info,
                source="import_from",
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
                source_module_info=module_info,
                source="import_",
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
                source_module_info=module_info,
                source="import_",
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
                source_module_info=module_info,
                source="import_from",
                target="sys",
                is_lazy=False,
                lineno=2,
                col_offset=0,
                stack_type_names=("Module", "ImportFrom"),
                is_relative=False,
            ),
            LocImportInfo(
                source_module_info=module_info,
                source="import_",
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
                source_module_info=module_info,
                source="import_from",
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
    assert resolved._get_imports_sources_counts() == {
        "os": {"t_ast_parser": 1},
        "sys": {"t_ast_parser": 2},
        "foo.bar": {"t_ast_parser": 1},
        "package": {"t_ast_parser": 1},
        "json": {"t_ast_parser": 1},
        "asdf.fdsa": {"t_ast_parser": 1},
        "buzz": {"t_ast_parser": 1},
    }

    # lazy should be skipped, even if repeated
    resolved = ScopeResolvedImports.from_scope(scope=scope_ast, skip_lazy=True)
    assert resolved._get_imports_sources_counts() == {
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
    assert resolved_all._get_imports_sources_counts() == {
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
    assert resolved_all.get_filtered()._get_imports_sources_counts() == {
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
    assert resolved_a._get_imports_sources_counts() == {
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
    assert resolved_a.get_filtered()._get_imports_sources_counts() == {
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
    assert resolved_all_a._get_imports_sources_counts() == {
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
    assert resolved_all_a.get_filtered()._get_imports_sources_counts() == {
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
    assert resolved_b._get_imports_sources_counts() == {
        "B.b2": {"B.b1": 1},
        "C": {"B.b2": 2},
        "extern_b1": {"B.b1": 1},
        "extern_b2": {"B.b2": 1},
    }
    assert resolved_b.get_filtered()._get_imports_sources_counts() == {
        "C": {"B.b2": 2},
        "extern_b1": {"B.b1": 1},
        "extern_b2": {"B.b2": 1},
    }

    resolved_all_b = ScopeResolvedImports.from_scope(
        scope=scope_all, start_scope=scope_b
    )
    assert resolved_all_b._get_imports_sources_counts() == {
        "B.b2": {"B.b1": 1},
        "C": {"B.b2": 2},
        "extern_C": {"C": 1},
        "extern_b1": {"B.b1": 1},
        "extern_b2": {"B.b2": 1},
    }
    assert resolved_all_b.get_filtered()._get_imports_sources_counts() == {
        "extern_b1": {"B.b1": 1},
        "extern_b2": {"B.b2": 1},
        "extern_C": {"C": 1},
    }

    # >>> C <<< #

    resolved_c = ScopeResolvedImports.from_scope(scope=scope_c)
    assert resolved_c._get_imports_sources_counts() == {
        "extern_C": {"C": 1},  #
    }
    assert resolved_c.get_filtered()._get_imports_sources_counts() == {
        "extern_C": {"C": 1},
    }

    resolved_all_c = ScopeResolvedImports.from_scope(
        scope=scope_all, start_scope=scope_c
    )
    assert resolved_all_c._get_imports_sources_counts() == {
        "extern_C": {"C": 1},  #
    }
    assert resolved_all_c.get_filtered()._get_imports_sources_counts() == {
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
    scope_all = ModulesScope()
    scope_all.add_modules_from_search_path(
        PKGS_ROOT, unreachable_mode=UnreachableModeEnum.keep
    )
    scope_a = scope_all.get_restricted_scope(imports=["A"])
    scope_b = scope_all.get_restricted_scope(imports=["B"])

    mapper = RequirementsMapper(
        env_matchers={
            "default": [
                ("glob_Aa3", ImportMatcherGlob("A.a3.*")),
                ("glob_Aa4", ImportMatcherGlob("A.a4.a4i")),
                ("glob_A", ImportMatcherGlob("A.*")),
                ("glob_Aa2", ImportMatcherGlob("A.a2.*")),
                ("scope_b", ImportMatcherScope(scope=scope_b)),
                ("scope_a", ImportMatcherScope(scope=scope_a)),
                ("scope_all", ImportMatcherScope(scope=scope_all)),
            ]
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


# ========================================================================= #
# END                                                                       #
# ========================================================================= #
