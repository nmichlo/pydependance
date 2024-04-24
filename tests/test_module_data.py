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
from pydependence._core.modules_resolver import ScopeResolvedImports
from pydependence._core.modules_scope import (
    _find_modules, DuplicateModuleNamesError,
    DuplicateModulePathsError, DuplicateModulesError, ModulesScope,
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
        't_ast_parser',
        'A',
        'A.a1',
        'A.a2',
        'A.a3',
        'A.a3.a3i',
        'B',
        'B.b1',
        'B.b2',
        'C',
    }
    unreachable = {
        'A.a4.a4i',
    }
    edges_reachable = {
        ('A', 'A.a1'),
        ('A', 'A.a2'),
        ('A', 'A.a3'),
        ('A.a3', 'A.a3.a3i'),
        ('B', 'B.b1'),
        ('B', 'B.b2'),
    }
    # not included!
    edges_unreachable = {
        ('A.a4', 'A.a4.a4i'),
    }

    # load all modules (default)
    results = _find_modules(
        search_paths=[PKGS_ROOT],
        package_paths=None,
        tag="test",
    )
    assert set(results.nodes) == (reachable | unreachable)
    assert set(results.edges) == edges_reachable

    # load only reachable modules
    results = _find_modules(
        search_paths=[PKGS_ROOT],
        package_paths=None,
        tag="test",
        reachable_only=True,
    )
    assert set(results.nodes) == reachable
    assert set(results.edges) == edges_reachable

    # load missing
    with pytest.raises(FileNotFoundError):
        _find_modules(
            search_paths=[PKGS_ROOT / 'THIS_DOES_NOT_EXIST'],
            package_paths=None,
            tag="test",
        )

    # load file
    assert PKG_AST_TEST.exists() and PKG_AST_TEST.is_file()
    with pytest.raises(NotADirectoryError):
        _find_modules(
            search_paths=[PKG_AST_TEST],
            package_paths=None,
            tag="test",
        )

    # load subdir
    results = _find_modules(
        search_paths=[PKG_A],
        package_paths=None,
        tag="test",
    )
    assert set(results.nodes) == {'a1', 'a2', 'a3', 'a3.a3i', 'a4.a4i'}

    # load conflicting modules -- reference same files but different search paths
    with pytest.raises(DuplicateModuleNamesError):
        _find_modules(
            search_paths=[PKGS_ROOT, PKGS_ROOT],
            package_paths=None,
            tag="test",
        )


def test_find_modules_pkg_path():
    reachable_a = {
        'A',
        'A.a1',
        'A.a2',
        'A.a3',
        'A.a3.a3i',
    }
    unreachable_a = {
        'A.a4.a4i',
    }

    # load all modules (default)
    results = _find_modules(
        search_paths=None,
        package_paths=[PKG_A],
        tag="test",
    )
    assert set(results.nodes) == (reachable_a | unreachable_a)

    # load only reachable modules
    results = _find_modules(
        search_paths=None,
        package_paths=[PKG_A],
        tag="test",
        reachable_only=True,
    )
    assert set(results.nodes) == reachable_a

    # load all
    results = _find_modules(
        search_paths=None,
        package_paths=[PKG_B],
        tag="test",
    )
    assert set(results.nodes) == {'B', 'B.b1', 'B.b2'}

    results = _find_modules(
        search_paths=None,
        package_paths=[PKG_C],
        tag="test",
    )
    assert set(results.nodes) == {'C'}

    # load invalid
    with pytest.raises(FileNotFoundError):
        _find_modules(
            search_paths=None,
            package_paths=[PKGS_ROOT / 'THIS_DOES_NOT_EXIST.py'],
            tag="test",
        )

    # load conflicting modules -- reference same files but different search paths
    with pytest.raises(DuplicateModulePathsError):
        _find_modules(
            search_paths=None,
            package_paths=[PKG_A, PKG_A / 'a1.py'],
            tag="test",
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
    scope.add_modules_from_package_path(PKG_A)
    assert set(scope.iter_modules()) == modules_a
    # this should not edit the original if it fails
    with pytest.raises(DuplicateModulePathsError):
        scope.add_modules_from_package_path(PKG_A / 'a1.py')
    with pytest.raises(DuplicateModulePathsError):
        scope.add_modules_from_package_path(PKG_A)
    assert set(scope.iter_modules()) == modules_a

    scope = ModulesScope()
    scope.add_modules_from_search_path(PKGS_ROOT)
    assert set(scope.iter_modules()) == modules_all

    scope = ModulesScope()
    scope.add_modules_from_raw_imports(imports=["A.a1"], tag="test")
    with pytest.raises(DuplicateModuleNamesError):
        scope.add_modules_from_raw_imports(imports=["A.a1"], tag="test")
    assert set(scope.iter_modules()) == {"A.a1"}

    # merge scopes & check subsets
    scope_all = ModulesScope()
    scope_all.add_modules_from_search_path(PKGS_ROOT)
    assert set(scope_all.iter_modules()) == modules_all

    scope_a = ModulesScope()
    scope_a.add_modules_from_package_path(PKG_A)
    assert set(scope_a.iter_modules()) == modules_a

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
    scope_ast = scope_ast.add_modules_from_package_path(PKG_AST_TEST)

    resolved = ScopeResolvedImports.from_scope(scope=scope_ast)
    assert resolved._get_imports_sources_counts() == {
        'os': {'t_ast_parser': 1},
        'sys': {'t_ast_parser': 2},
        'foo.bar': {'t_ast_parser': 1},
        'package': {'t_ast_parser': 1},
        'json': {'t_ast_parser': 1},
        'asdf.fdsa': {'t_ast_parser': 1},
        'buzz': {'t_ast_parser': 1},
    }

    # lazy should be skipped, even if repeated
    resolved = ScopeResolvedImports.from_scope(scope=scope_ast, skip_lazy=True)
    assert resolved._get_imports_sources_counts() == {
        'os': {'t_ast_parser': 1},
        'sys': {'t_ast_parser': 1},
        'foo.bar': {'t_ast_parser': 1},
        'package': {'t_ast_parser': 1},
    }


# ========================================================================= #
# END                                                                       #
# ========================================================================= #
