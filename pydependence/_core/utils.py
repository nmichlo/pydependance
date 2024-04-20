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
import typing
from pathlib import Path
from typing import Union

# never actually imported at runtime, but used for type hints in IDEs
if typing.TYPE_CHECKING:
    from tomlkit import TOMLDocument


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


def is_relative_path(path: Union[str, Path]) -> bool:
    # '..' should be considered a relative path
    # '.' should be considered a relative path
    # `not is_absolute` is not enough!
    return Path(path).is_relative_to(Path("."))


def is_absolute_path(path: Union[str, Path]) -> bool:
    return not is_relative_path(path)


def apply_root_to_path_str(root: Union[str, Path], path: Union[str, Path]) -> str:
    if is_relative_path(root):
        raise ValueError(f"root must be an absolute path, got: {root}")
    if is_absolute_path(path):
        path = Path(path)
    else:
        path = Path(root) / path
    return str(path.resolve())


# ========================================================================= #
# LOAD                                                                      #
# ========================================================================= #


def load_toml_document(path: Union[str, Path]) -> "TOMLDocument":
    import tomlkit
    from tomlkit import TOMLDocument

    path = Path(path)
    if not path.name.endswith(".toml"):
        raise ValueError(f"path is not a .toml file: {path}")
    if not path.is_file():
        raise FileNotFoundError(f"path is not a file: {path}")
    with open(path) as fp:
        toml = tomlkit.load(fp)
        assert isinstance(toml, TOMLDocument), f"got {type(toml)}, not TOMLDocument"
    return toml


# ========================================================================= #
# END                                                                       #
# ========================================================================= #


__all__ = (
    "assert_valid_module_path",
    "assert_valid_import_name",
    "is_relative_path",
    "is_absolute_path",
    "apply_root_to_path_str",
    "load_toml_document",
)
