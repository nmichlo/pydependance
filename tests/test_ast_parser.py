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

from pydependence._core.module_data import ModuleMetadata
from pydependence._core.module_imports_ast import (
    LocImportInfo,
    load_imports_from_module_info,
)

PKG_ROOT = Path(__file__).parent / "test-packages"

TEST_MODULE_INFO = ModuleMetadata.from_root_and_subpath(
    root=PKG_ROOT,
    subpath=PKG_ROOT / "t_ast_parser.py",
    tag="test",
)

# ========================================================================= #
# TESTS                                                                     #
# ========================================================================= #


def test_ast_get_module_imports(tmp_path):
    # checks
    results = load_imports_from_module_info(TEST_MODULE_INFO)

    a = {
        "asdf.fdsa": [
            LocImportInfo(
                source_module_info=TEST_MODULE_INFO,
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
                source_module_info=TEST_MODULE_INFO,
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
                source_module_info=TEST_MODULE_INFO,
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
                source_module_info=TEST_MODULE_INFO,
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
                source_module_info=TEST_MODULE_INFO,
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
                source_module_info=TEST_MODULE_INFO,
                source="import_from",
                target="sys",
                is_lazy=False,
                lineno=2,
                col_offset=0,
                stack_type_names=("Module", "ImportFrom"),
                is_relative=False,
            ),
            LocImportInfo(
                source_module_info=TEST_MODULE_INFO,
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
                source_module_info=TEST_MODULE_INFO,
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
    assert a == results


# ========================================================================= #
# END                                                                       #
# ========================================================================= #
