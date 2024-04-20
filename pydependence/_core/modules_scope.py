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
import warnings
from collections import defaultdict
from enum import Enum
from pathlib import Path
from typing import (
    DefaultDict,
    Dict,
    Iterable,
    Iterator,
    List,
    NamedTuple,
    Optional,
    Sequence,
    Set,
    Tuple,
    Union,
)

import networkx as nx

from pydependence._core.builtin import BUILTIN_MODULE_NAMES
from pydependence._core.module_data import ModuleMetadata
from pydependence._core.module_imports_ast import LocImportInfo
from pydependence._core.module_imports_loader import (
    DEFAULT_MODULE_IMPORTS_LOADER,
    ModuleImports,
)
from pydependence._core.utils import assert_valid_import_name

# ========================================================================= #
# MODULE GRAPH                                                              #
# ========================================================================= #


NODE_KEY_MODULE_INFO = "module_info"


class DuplicateModuleError(RuntimeError):
    pass


class _ModuleGraphNodeData(NamedTuple):
    module_info: "Optional[ModuleMetadata]"

    @classmethod
    def from_graph_node(cls, graph: "nx.DiGraph", node: str) -> "_ModuleGraphNodeData":
        return cls(module_info=graph.nodes[node].get(NODE_KEY_MODULE_INFO, None))


def _find_modules(
    search_paths: "Optional[Sequence[Path]]",
    package_paths: "Optional[Sequence[Path]]",
    tag: str,
    reachable_only: bool = False,
) -> "nx.DiGraph":
    """
    Construct a graph of all modules found in the search paths and package paths.
    Edges are added from each module to its parent package (if exists). E.g. may be
    missing if an `__init__.py` file is missing.
    """
    g = nx.DiGraph()

    # load all search paths
    if search_paths is not None:
        for search_path in search_paths:
            if not search_path.is_dir():
                raise NotADirectoryError(
                    f"Search path must be a directory, got: {search_path}"
                )
            for m in ModuleMetadata.yield_search_path_modules(search_path, tag=tag):
                if m.name in g:
                    dat = _ModuleGraphNodeData.from_graph_node(g, m.name)
                    raise DuplicateModuleError(
                        f"Duplicate module name: {repr(m.name)}, already exists as: {dat.module_info.path}, tried to add: {m.path}, from search path: {search_path}. "
                        f"These modules are incompatible and cannot be loaded together!"
                    )
                g.add_node(m.name, **{NODE_KEY_MODULE_INFO: m})

    # load all package paths
    if package_paths is not None:
        for package_path in package_paths:
            if not package_path.exists():
                raise FileNotFoundError(f"Package path does not exist: {package_path}")
            for m in ModuleMetadata.yield_package_modules(package_path, tag=tag):
                if m.name in g:
                    dat = _ModuleGraphNodeData.from_graph_node(g, m.name)
                    raise DuplicateModuleError(
                        f"Duplicate module name: {repr(m.name)}, already exists as: {dat.module_info.path}, tried to add: {m.path}, from package path: {package_path}. "
                        f"These modules are incompatible and cannot be loaded together!"
                    )
                g.add_node(m.name, **{NODE_KEY_MODULE_INFO: m})

    # add all connections to parent packages
    for node in g.nodes:
        parts = node.split(".")
        if len(parts) > 1:
            parent = ".".join(parts[:-1])
            if g.has_node(parent):
                g.add_edge(parent, node)

    # make sure there are no empty nodes, this is a bug!
    if "" in g.nodes:
        raise RuntimeError(f"[BUG] Empty module name found in graph: {g}")

    # reverse traverse from each node to the root to figure out which nodes are reachable, then filter them out.
    if reachable_only:
        reverse = g.reverse()
        for node in list(g.nodes):
            root = node.split(".")[0]
            if not nx.has_path(reverse, node, root):
                g.remove_node(node)

    # * DiGraph [ import_path -> Node(module_info) ]
    return g


# ========================================================================= #
# NAMED MODULE NAMESPACE                                                    #
# ========================================================================= #


class RestrictMode(str, Enum):
    EXACT = "EXACT"
    CHILDREN = "CHILDREN"
    ROOT_CHILDREN = "ROOT_CHILDREN"


class RestrictOp(str, Enum):
    LIMIT = "LIMIT"  # only include these
    EXCLUDE = "EXCLUDE"  # exclude these


class ModulesScope:

    def __init__(self):
        self._module_graph = nx.DiGraph()
        self.__import_graph_strict = None
        self.__import_graph_lazy = None

    # ~=~=~ ADD MODULES ~=~=~ #

    def _merge_module_graph(self, graph: "nx.DiGraph") -> "ModulesScope":
        # 1. get all nodes that are in both search spaces
        nodes = set(self._module_graph.nodes) & set(graph.nodes)
        if nodes:
            raise DuplicateModuleError(f"Duplicate module names found: {sorted(nodes)}")
        # 2. add all nodes from the other search space
        self._module_graph = nx.compose(self._module_graph, graph)
        self.__import_graph_strict = None
        self.__import_graph_lazy = None
        return self

    def add_modules_from_scope(self, search_space: "ModulesScope") -> "ModulesScope":
        return self._merge_module_graph(graph=search_space._module_graph)

    def add_modules_from_raw_imports(
        self, imports: List[str], tag: str
    ) -> "ModulesScope":
        g = nx.DiGraph()
        for imp in imports:
            g.add_node(imp)
        return self._merge_module_graph(graph=g)

    def add_modules_from_search_path(
        self, search_path: Path, tag: Optional[str] = None
    ) -> "ModulesScope":
        if tag is None:
            tag = search_path.name
            warnings.warn(
                f"No tag provided for search path: {repr(search_path)}, using path name as tag: {repr(tag)}"
            )
        graph = _find_modules(search_paths=[search_path], package_paths=None, tag=tag)
        return self._merge_module_graph(graph=graph)

    def add_modules_from_package_path(
        self, package_path: Path, tag: Optional[str] = None
    ) -> "ModulesScope":
        if tag is None:
            tag = package_path.parent.name
            warnings.warn(
                f"No tag provided for package path: {repr(package_path)}, using parent name as tag: {repr(tag)}"
            )
        graph = _find_modules(search_paths=None, package_paths=[package_path], tag=tag)
        return self._merge_module_graph(graph=graph)

    # ~=~=~ MODULE INFO ~=~=~ #

    def iter_modules(self) -> "Iterator[str]":
        yield from self._module_graph.nodes

    def iter_module_items(self) -> "Iterator[Tuple[str, _ModuleGraphNodeData]]":
        for node in self._module_graph.nodes:
            yield node, _ModuleGraphNodeData.from_graph_node(self._module_graph, node)

    def has_module(self, module_name: str) -> bool:
        return module_name in self._module_graph

    def get_module_data(self, module_name: str) -> _ModuleGraphNodeData:
        return _ModuleGraphNodeData.from_graph_node(self._module_graph, module_name)

    # ~=~=~ SCOPE OPS ~=~=~ #

    def is_scope_parent_set(self, other: "ModulesScope") -> bool:
        return self._module_graph.nodes <= other._module_graph.nodes

    def is_scope_subset(self, other: "ModulesScope") -> bool:
        return self._module_graph.nodes >= other._module_graph.nodes

    def is_scope_conflicts(self, other: "ModulesScope") -> bool:
        return bool(self._module_graph.nodes & other._module_graph.nodes)

    def get_scope_conflicts(self, other: "ModulesScope") -> Set[str]:
        return set(self._module_graph.nodes & other._module_graph.nodes)

    # ~=~=~ FILTER MODULES ~=~=~ #

    def get_restricted_scope(
        self,
        imports: Iterable[str],
        *,
        mode: RestrictMode = RestrictMode.CHILDREN,
        op: RestrictOp = RestrictOp.LIMIT,
    ) -> "ModulesScope":
        assert not isinstance(imports, str)
        imports = set(map(assert_valid_import_name, imports))
        # copy the graph
        s = ModulesScope()
        s._module_graph = self._module_graph.copy()

        # allowed
        if mode == RestrictMode.ROOT_CHILDREN:
            allowed = {(i.split("."),) for i in imports}
        elif mode in (RestrictMode.EXACT, RestrictMode.CHILDREN):
            allowed = {tuple(i.split(".")) for i in imports}
        else:
            raise ValueError(f"Invalid mode: {mode}")

        # filter the graph
        for node in list(s._module_graph.nodes):
            node_parts = tuple(node.split("."))
            # get the limited set of nodes
            if mode == RestrictMode.EXACT:
                remove = node_parts not in allowed
            elif mode == RestrictMode.ROOT_CHILDREN:
                remove = node_parts[:1] not in allowed
            elif mode == RestrictMode.CHILDREN:
                remove = not any(
                    node_parts[: i + 1] in allowed for i in range(len(node_parts))
                )
            else:
                raise ValueError(f"Invalid mode: {mode}")
            # apply the operation
            if op == RestrictOp.LIMIT:
                remove = remove
            elif op == RestrictOp.EXCLUDE:
                remove = not remove
            else:
                raise ValueError(f"Invalid operation: {op}")
            # remove the node
            if remove:
                s._module_graph.remove_node(node)
        # done!
        return s


# ========================================================================= #
# END                                                                       #
# ========================================================================= #


__all__ = (
    "DuplicateModuleError",
    "ModulesScope",
    "RestrictMode",
    "RestrictOp",
)
