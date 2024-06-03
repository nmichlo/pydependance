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

import pkgutil
import warnings
from importlib.machinery import FileFinder
from pathlib import Path
from typing import Iterator, NamedTuple

from pydependence._core.utils import assert_valid_import_name, assert_valid_tag

# ========================================================================= #
# MODULE INFO                                                               #
# ========================================================================= #


class ModuleMetadata(NamedTuple):
    path: Path
    name: str
    ispkg: bool

    # tag e.g. if package `yolov5` package loaded this, the `utils` module is not unique...
    tag: str

    @property
    def root_name(self) -> str:
        return self.name.split(".")[0]

    @property
    def tagged_name(self):
        return f"{self.tag}:{self.name}"

    @property
    def is_name_valid(self):
        try:
            assert_valid_import_name(self.name)
            return True
        except Exception:
            return False

    @property
    def pkgutil_module_info(self):
        if not self.path.is_absolute():
            raise ValueError(f"Path must be absolute, got: {self.path}")
        return pkgutil.ModuleInfo(
            module_finder=FileFinder(path=str(self.path)),
            name=self.name,
            ispkg=self.ispkg,
        )

    @classmethod
    def from_root_and_subpath(
        cls,
        root: Path,
        subpath: Path,
        tag: str,
    ) -> "ModuleMetadata":
        if not root.is_absolute():
            raise ValueError(f"Root path must be absolute, got: {root}")
        if not subpath.is_absolute():
            subpath = root / subpath
        if not subpath.name.endswith(".py"):
            raise ValueError(f"Subpath must be a python file, got: {subpath}")
        if not subpath.is_file():
            raise FileNotFoundError(f"Subpath must be an existing file, got: {subpath}")
        tag = assert_valid_tag(tag)
        rel = subpath.relative_to(root)
        if rel.name == "__init__.py":
            return ModuleMetadata(
                path=subpath,
                name=".".join(rel.parts[:-1]),
                ispkg=True,
                tag=tag,
            )
        else:
            return ModuleMetadata(
                path=subpath,
                name=".".join(rel.parts)[: -len(".py")],
                ispkg=False,
                tag=tag,
            )

    @classmethod
    def yield_search_path_modules(
        cls, search_path: Path, *, tag: str, valid_only: bool = True
    ) -> "Iterator[ModuleMetadata]":
        def _visit(p: Path):
            if p.is_dir():
                yield from p.glob("**/*.py")
            else:
                raise ValueError(f"Invalid path: {p}")

        for p in _visit(search_path):
            m = cls.from_root_and_subpath(search_path, subpath=p, tag=tag)
            if valid_only and (not m.is_name_valid):
                warnings.warn(
                    f"Invalid module name: {m.name}, cannot be imported or resolved, skipping: {m.path}"
                )
                continue
            yield m
        # Only one level deep & does not work if __init__.py is not present.
        # yield from pkgutil.iter_modules(path=[str(search_path)], prefix='')

    @classmethod
    def yield_package_modules(
        cls, package_path: Path, *, tag: str, valid_only: bool = True
    ) -> "Iterator[ModuleMetadata]":
        def _visit(p: Path):
            if p.is_file():
                yield p
            elif p.is_dir():
                yield from p.glob("**/*.py")
            else:
                raise ValueError(f"Invalid path: {p}")

        for p in _visit(package_path):
            m = cls.from_root_and_subpath(package_path.parent, subpath=p, tag=tag)
            if valid_only and (not m.is_name_valid):
                warnings.warn(
                    f"Invalid module name: {m.name}, cannot be imported or resolved, skipping: {m.path}"
                )
                continue
            yield m
        # Only one level deep & does not work if __init__.py is not present.
        # yield from pkgutil.iter_modules(path=[str(package_path)], prefix=f"{package_path.name}.")


# ========================================================================= #
# END                                                                       #
# ========================================================================= #


__all__ = ("ModuleMetadata",)
