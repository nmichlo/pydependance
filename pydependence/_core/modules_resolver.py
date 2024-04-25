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

import warnings
from collections import defaultdict
from typing import Dict, Iterable, List, NamedTuple, Optional, Set, Tuple

import networkx as nx

from pydependence._core.builtin import BUILTIN_MODULE_NAMES
from pydependence._core.module_data import ModuleMetadata
from pydependence._core.module_imports_ast import LocImportInfo
from pydependence._core.module_imports_loader import (
    DEFAULT_MODULE_IMPORTS_LOADER,
    ModuleImports,
)
from pydependence._core.modules_scope import NODE_KEY_MODULE_INFO, ModulesScope

# ========================================================================= #
# IMPORT GRAPH                                                              #
# ========================================================================= #


NODE_KEY_MODULE_IMPORTS = "module_imports"
EDGE_KEY_IMPORTS = "imports"


class _ImportsGraphNodeData(NamedTuple):
    module_info: "Optional[ModuleMetadata]"
    module_imports: "Optional[ModuleImports]"

    @classmethod
    def from_graph_node(cls, graph: "nx.DiGraph", node: str) -> "_ImportsGraphNodeData":
        return cls(
            module_info=graph.nodes[node].get(NODE_KEY_MODULE_INFO, None),
            module_imports=graph.nodes[node].get(NODE_KEY_MODULE_IMPORTS, None),
        )


class _ImportsGraphEdgeData(NamedTuple):
    imports: "List[LocImportInfo]"

    @classmethod
    def from_graph_edge(
        cls, graph: "nx.DiGraph", src: str, dst: str
    ) -> "_ImportsGraphEdgeData":
        edge_data = graph.edges[src, dst]
        imports = edge_data.get(EDGE_KEY_IMPORTS, [])
        return cls(imports=imports)

    @property
    def all_lazy(self) -> bool:
        return all(imp.is_lazy for imp in self.imports)


def _construct_module_import_graph(
    scope: "ModulesScope",
    *,
    visit_lazy: bool,
) -> "nx.DiGraph":
    """
    Supports same interface as `find_modules` but edges are instead constructed
    from the module imports.

    This is the direct graph where nodes are modules, and edges represent their imports.
    """
    g = nx.DiGraph()
    for node, node_data in scope.iter_module_items():
        if node_data.module_info is None:
            warnings.warn(f"Module info not found for: {repr(node)}, skipping...")
            continue
        # get module info
        node_imports: ModuleImports = DEFAULT_MODULE_IMPORTS_LOADER.load_module_imports(
            module_info=node_data.module_info
        )
        # construct nodes & edges between nodes based on imports
        # - edges don't always exist, so can't just rely on them to add all nodes.
        g.add_node(
            node,
            **{NODE_KEY_MODULE_INFO: node_data, NODE_KEY_MODULE_IMPORTS: node_imports},
        )
        for imp, imports in node_imports.module_imports.items():
            # filter out lazy, or skip
            if not visit_lazy:
                imports = [imp for imp in imports if not imp.is_lazy]
            # add edge
            if imports:
                g.add_edge(
                    node,
                    imp,
                    **{EDGE_KEY_IMPORTS: imports},
                )
    return g


# ========================================================================= #
# MODULE GRAPH                                                              #
# ========================================================================= #


class ScopeNotASubsetError(ValueError):
    pass


def _resolve_scope_imports(
    scope: "ModulesScope",
    start_scope: "Optional[ModulesScope]",
    visit_lazy: bool,
) -> "Tuple[List[LocImportInfo], Set[str]]":
    if start_scope is None:
        start_scope = scope
    if not scope.is_scope_subset(start_scope):
        raise ScopeNotASubsetError("Start scope must be a subset of the parent scope!")

    # 1. construct
    # - if all imports are lazy, then we don't need to traverse them! (depending on mode)
    # - we have to filter BEFORE the bfs otherwise we will traverse wrong nodes.
    import_graph = _construct_module_import_graph(scope=scope, visit_lazy=visit_lazy)

    # 2. now resolve imports from the starting point!
    # - dfs along edges to get all imports MUST do ALL edges
    # - this is why we don't use `dfs_edges` which visits nodes, and may skip edges.
    # - each edge contains all imports along that edge, these should
    #   be added to the set of imports so that we can track all imports
    visited = set()
    imports = []
    for src, dst in nx.edge_dfs(import_graph, source=start_scope.iter_modules()):
        edge_data = _ImportsGraphEdgeData.from_graph_edge(import_graph, src, dst)
        imports.extend(edge_data.imports)
        visited.update([src, dst])

    # 3. convert to datatype
    # NOTE: ideally later on we would group these imports by `dst` or `target`. It is
    #       just easier to work with them this way for now.
    return imports, visited


class ScopeResolvedImports:

    def __init__(
        self,
        scope: "ModulesScope",
        start_scope: "ModulesScope",
        imports: "List[LocImportInfo]",
        visited: "Set[str]",
    ):
        self._scope = scope
        self._start_scope = start_scope
        self._imports = imports
        self._visited = visited  # visited modules

    @classmethod
    def from_scope(
        cls,
        scope: "ModulesScope",
        start_scope: "Optional[ModulesScope]" = None,
        visit_lazy: bool = True,
    ):
        if start_scope is None:
            start_scope = scope

        imports, visited = _resolve_scope_imports(
            scope=scope,
            start_scope=start_scope,
            visit_lazy=visit_lazy,
        )

        return cls(
            scope=scope,
            start_scope=start_scope,
            imports=imports,
            visited=visited,
        )

    def get_filtered(
        self,
        exclude_unvisited: bool = True,
        exclude_in_search_space: bool = True,
        exclude_builtins: bool = True,
    ) -> "ScopeResolvedImports":

        def _keep(imp: LocImportInfo) -> bool:
            if exclude_builtins and imp.target in BUILTIN_MODULE_NAMES:
                return False
            if exclude_in_search_space and self._scope.has_module(imp.target):
                return False
            if exclude_unvisited and imp.source_name not in self._visited:
                return False
            return True

        return self.__class__(
            scope=self._scope,
            start_scope=self._start_scope,
            imports=[imp for imp in self._imports if _keep(imp)],
            visited=set(self._visited),
        )

    def get_imports(self) -> "List[LocImportInfo]":
        return list(self._imports)

    # ~=~=~ debug ~=~=~ #

    def _get_targets_sources_counts(self) -> "Dict[str, Dict[str, int]]":
        # used for debugging / testing
        trg_src_imps = defaultdict(lambda: defaultdict(list))
        for imp in self._imports:
            trg_src_imps[imp.target][imp.source_name].append(imp)
        return {
            trg: {src: len(imps) for src, imps in src_imps.items()}
            for trg, src_imps in trg_src_imps.items()
        }


# ========================================================================= #
# END                                                                       #
# ========================================================================= #
