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

import pydependence._colors as C
from pydependence._core.utils import (
    apply_root_to_path_str,
    assert_valid_import_name,
    assert_valid_module_path,
    assert_valid_tag,
)


def test_colors():
    for attr in [
        "RST",
        # dark colors
        "GRY",
        "lRED",
        "lGRN",
        "lYLW",
        "lBLU",
        "lMGT",
        "lCYN",
        "WHT",
        # light colors
        "BLK",
        "RED",
        "GRN",
        "YLW",
        "BLU",
        "MGT",
        "CYN",
        "lGRY",
    ]:
        assert hasattr(C, attr)


def test_assert_valid_tag():
    # does not normalize tag
    assert assert_valid_tag("valid_tag") == "valid_tag"
    assert assert_valid_tag("valid-tag") == "valid-tag"
    with pytest.raises(ValueError):
        assert_valid_tag("")


def test_assert_valid_module_path():
    assert assert_valid_module_path(Path(__file__)) == Path(__file__).resolve()
    with pytest.raises(ValueError):
        assert_valid_module_path("relative/path")
    with pytest.raises(FileNotFoundError):
        assert_valid_module_path("/path/does/not/exist")
    with pytest.raises(RuntimeError):
        assert_valid_module_path(Path.home())  # assuming home directory is not a file


def test_assert_valid_import_name():
    assert assert_valid_import_name("valid.import.name") == "valid.import.name"
    with pytest.raises(NameError):
        assert_valid_import_name("")
    with pytest.raises(NameError):
        assert_valid_import_name("invalid.import.name.")


def test_apply_root_to_path_str():
    root = str(Path.home())
    assert apply_root_to_path_str(root, "relative/path") == str(
        (Path(root) / "relative/path").resolve()
    )
    with pytest.raises(ValueError):
        apply_root_to_path_str("relative/path", "another/relative/path")
    assert apply_root_to_path_str(root, str(Path.home())) == str(Path.home().resolve())
