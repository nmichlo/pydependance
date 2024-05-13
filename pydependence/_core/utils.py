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
from typing import List, Union

import tomlkit
import tomlkit.items
import tomlkit.toml_document

# ========================================================================= #
# AST IMPORT PARSER                                                         #
# ========================================================================= #


def assert_valid_tag(tag: str) -> str:
    if not tag:
        raise ValueError(f"Tag must not be empty: {tag}")
    if not tag.replace("-", "_").isidentifier():
        raise NameError(f"Tag must be a valid identifier: {tag}")
    return tag


def assert_valid_module_path(path: "Union[Path, str]") -> Path:
    path = Path(path)
    if not path.is_absolute():
        raise ValueError(f"Path must be absolute: {path}")
    if not path.exists():
        raise FileNotFoundError(f"File does not exist: {path}")
    if not path.is_file():
        raise RuntimeError(f"Path is not a file: {path}")
    return path


def assert_valid_import_name(import_: str) -> str:
    parts = import_.split(".")
    if not parts:
        raise ValueError(
            f"import path must have at least one part for: {repr(import_)}"
        )
    for part in parts:
        if not part.isidentifier():
            raise NameError(
                f"import part: {repr(part)} is not a valid identifier, obtained from: {repr(import_)}"
            )
    return import_


# ========================================================================= #
# PATH HELPER                                                               #
# ========================================================================= #


def apply_root_to_path_str(root: "Union[str, Path]", path: "Union[str, Path]") -> str:
    root = Path(root)
    path = Path(path)
    if not root.is_absolute():
        raise ValueError(f"root must be an absolute path, got: {root}")
    if path.is_absolute():
        merged = path
    else:
        merged = root / path
    return str(merged.resolve())


# ========================================================================= #
# LOAD                                                                      #
# ========================================================================= #


def load_toml_document(
    path: "Union[str, Path]",
) -> "tomlkit.toml_document.TOMLDocument":
    path = Path(path)
    if not path.name.endswith(".toml"):
        raise ValueError(f"path is not a .toml file: {path}")
    if not path.is_file():
        raise FileNotFoundError(f"path is not a file: {path}")
    with open(path) as fp:
        toml = tomlkit.load(fp)
        assert isinstance(
            toml, tomlkit.toml_document.TOMLDocument
        ), f"got {type(toml)}, not TOMLDocument"
    return toml


# ========================================================================= #
# WRITE                                                                     #
# ========================================================================= #


def txt_file_dump(
    *,
    file: "Union[str, Path]",
    contents: "str",
):
    # write
    with open(file, "w") as fp:
        fp.write(contents)
        if not contents.endswith("\n"):
            fp.write("\n")


def toml_file_replace_array(
    *,
    file: "Union[str, Path]",
    keys: "List[str]",
    array: "tomlkit.items.Array",
):
    # TODO: this needs multiple loads and writes if we are modifying multiple arrays
    #       which is not ideal... but it is a simple solution for now.

    assert isinstance(
        array, tomlkit.items.Array
    ), f"array must be a tomlkit Array, got: {type(array)}"

    # load file
    file = Path(file)
    assert file.is_absolute(), f"file must be an absolute path, got: {file}"
    toml = load_toml_document(file)

    # split parent keys from array key
    (*parent_keys, array_key) = keys

    # add parent sections if missing
    parent = toml
    for i, k in enumerate(parent_keys):
        section = parent.setdefault(k, {})
        assert isinstance(section, tomlkit.items.Table)
        parent = section

    # set array
    if array_key in parent:
        old_array = parent[array_key]
        assert isinstance(old_array, tomlkit.items.Array)
    parent[array_key] = array

    # write
    with open(file, "w") as fp:
        tomlkit.dump(toml, fp)


# ========================================================================= #
# END                                                                       #
# ========================================================================= #


__all__ = (
    "assert_valid_module_path",
    "assert_valid_import_name",
    "apply_root_to_path_str",
    "load_toml_document",
)
