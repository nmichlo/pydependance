# ============================================================================== #
# MIT License                                                                    #
#                                                                                #
# Copyright (c) 2023 Nathan Juraj Michlo                                         #
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
import os
from pathlib import Path

import pytest

from pydependence._core._OLD_type_import import Import
from pydependence._core._OLD_type_module import (
    ModuleFile,
    ModuleImportStatement,
    _package_normalized_module_paths,
    _path_is_python_module_file,
    _path_is_python_package_dir,
    iter_modules_from_package_root,
    iter_modules_from_python_path,
)

# ========================================================================= #
# TESTS                                                                     #
# ========================================================================= #


@dataclasses.dataclass
class TestPaths:
    root: Path
    root_file: Path
    root_pkg: Path
    root_mod: Path
    root_pkg_init: Path
    root_pkg_mod: Path


_T_ROOT = "test_directory"
_T_ROOT_FILE = os.path.join(_T_ROOT, "test_file.txt")
_T_ROOT_MOD = os.path.join(_T_ROOT, "test_module.py")
_T_ROOT_PKG = os.path.join(_T_ROOT, "test_package")
_T_ROOT_PKG_INIT = os.path.join(_T_ROOT_PKG, "__init__.py")
_T_ROOT_PKG_MOD = os.path.join(_T_ROOT_PKG, "sub_module.py")

_I_ROOT_MOD = "os.path"
_C_ROOT_MOD = f"import {_I_ROOT_MOD}"
_I_ROOT_PKG_MOD = "os"
_C_ROOT_PKG_MOD = f"import {_I_ROOT_PKG_MOD}"


@pytest.fixture(scope="session", autouse=True)
def test_paths(tmpdir_factory) -> TestPaths:
    root = Path(tmpdir_factory.mktemp(_T_ROOT))
    # paths
    paths = TestPaths(
        root=root.joinpath(_T_ROOT),
        root_file=root.joinpath(_T_ROOT_FILE),
        root_pkg=root.joinpath(_T_ROOT_PKG),
        root_mod=root.joinpath(_T_ROOT_MOD),
        root_pkg_init=root.joinpath(_T_ROOT_PKG_INIT),
        root_pkg_mod=root.joinpath(_T_ROOT_PKG_MOD),
    )
    # make dirs
    paths.root.mkdir(parents=True)
    paths.root_pkg.mkdir(parents=True)
    # fill files
    paths.root_file.write_text("")
    paths.root_mod.write_text(_C_ROOT_MOD)
    paths.root_pkg_init.write_text("")
    paths.root_pkg_mod.write_text(_C_ROOT_PKG_MOD)
    # get files
    return paths


def test_module_import(test_paths: TestPaths):
    target_import = Import(_I_ROOT_MOD)
    source_module = ModuleFile(test_paths.root_mod, _I_ROOT_MOD)
    module_import = ModuleImportStatement(target_import, source_module, False)

    assert module_import.target == target_import
    assert module_import.source == source_module


def test__path_is_python_module(test_paths: TestPaths):
    assert _path_is_python_module_file(test_paths.root_mod) == True
    assert _path_is_python_module_file(test_paths.root_file) == False


def test__path_is_python_package(test_paths: TestPaths):
    assert _path_is_python_package_dir(test_paths.root_pkg) == True
    assert _path_is_python_package_dir(test_paths.root_mod) == False


def test__package_normalized_module_path(test_paths: TestPaths):
    # make sure files are not packages and that they have .py removed for the import path
    assert _package_normalized_module_paths(test_paths.root_mod) == (
        test_paths.root_mod,
        False,
        test_paths.root_mod.with_name("test_module"),
    )
    # make sure __init__.py is remove for the import path
    assert _package_normalized_module_paths(test_paths.root_pkg_init) == (
        test_paths.root_pkg_init,
        True,
        test_paths.root_pkg_init.parent,
    )
    # make sure dirs have the __init__.py added
    assert _package_normalized_module_paths(test_paths.root_pkg) == (
        test_paths.root_pkg_init,
        True,
        test_paths.root_pkg_init.parent,
    )
    with pytest.raises(ValueError):
        _package_normalized_module_paths(test_paths.root_file)


def test_module_file(test_paths: TestPaths):
    module_file = ModuleFile(test_paths.root_mod, "os.path")
    assert module_file.abs_file_path == test_paths.root_mod
    assert module_file.is_package == False
    assert module_file.module_import.keys == ("os", "path")
    assert isinstance(module_file.import_statements, list)
    assert isinstance(module_file.import_statements[0], ModuleImportStatement)


def test_find_modules(test_paths: TestPaths):
    from_pkg_root = lambda root: list(iter_modules_from_package_root(root=root))
    from_py_path = lambda python_path: list(
        iter_modules_from_python_path(python_path=python_path)
    )

    # direct package root style searching
    with pytest.raises(ValueError):
        from_pkg_root(test_paths.root)
    with pytest.raises(ValueError):
        from_pkg_root(test_paths.root_file)
    [r_test_pkg_init, r_test_pkg_mod] = from_pkg_root(test_paths.root_pkg)
    [r_test_mod] = from_pkg_root(test_paths.root_mod)
    with pytest.raises(ValueError):
        from_pkg_root(test_paths.root_pkg_init)
    with pytest.raises(ValueError):
        from_pkg_root(test_paths.root_pkg_mod)

    # PYTHON_PATH style searching
    [p_test_mod, p_test_pkg_init, p_test_pkg_mod] = from_py_path(test_paths.root)
    with pytest.raises(NotADirectoryError):
        from_py_path(test_paths.root_file)
    with pytest.raises(ValueError):
        from_py_path(test_paths.root_pkg)
    with pytest.raises(NotADirectoryError):
        from_py_path(test_paths.root_mod)
    with pytest.raises(NotADirectoryError):
        from_py_path(test_paths.root_pkg_init)
    with pytest.raises(NotADirectoryError):
        from_py_path(test_paths.root_pkg_mod)

    assert isinstance(r_test_pkg_init, ModuleFile)
    assert isinstance(r_test_pkg_mod, ModuleFile)
    assert isinstance(r_test_mod, ModuleFile)

    assert r_test_pkg_init == p_test_pkg_init
    assert r_test_pkg_mod == p_test_pkg_mod
    assert r_test_mod == p_test_mod


# ========================================================================= #
# END                                                                       #
# ========================================================================= #
