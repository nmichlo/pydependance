import sys
from collections import defaultdict

# check the python version
if sys.version_info < (3, 10):
    print("please use python >= 3.10")
    exit(1)

import ast
import sys
import warnings
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple, Union

# ========================================================================= #
# Load Builtin Packages                                                     #
# ========================================================================= #


BUILTIN_PKGS = {
    "__main__",
    *sys.builtin_module_names,
    *sys.stdlib_module_names,  # python 3.10
}


def import_get_root(import_: "ImportType") -> str:
    root = import_to_keys(import_, check=False)[0]
    return root


def import_is_builtin(import_: "ImportType") -> bool:
    root = import_get_root(import_)
    return root in BUILTIN_PKGS


# ========================================================================= #
# Ast Import Finder                                                         #
# ========================================================================= #


def ast_get_module_imports(path: Union[str, Path]) -> List[Tuple[List[str], bool]]:
    imports = []
    ast_node_stack = []
    is_eval_stack = [True]
    INDIRECT = {"FunctionDef"}

    class AstImportCollector(ast.NodeVisitor):

        # TODO: we should implement a basic interpreter to detect if imports are
        #       immediate or indirect, for example imports at the root of a module or
        #       inside a class would evaluate immediately, but imports inside a function
        #       will probably be lazily imported, and can be marked as such.

        def visit(self, node):
            # basic interpreter
            is_eval = is_eval_stack[-1] and (node.__class__.__name__ not in INDIRECT)
            ast_node_stack.append(node)
            is_eval_stack.append(is_eval)
            # continue recursion
            super().visit(node)
            # undo
            ast_node_stack.pop()
            is_eval_stack.pop()

        def visit_Import(self, node):
            # eg. import pkg.submodule
            imports.extend(
                (n.name.split("."), False, is_eval_stack[-1], tuple(ast_node_stack))
                for n in node.names
            )
            return node

        def visit_ImportFrom(self, node):
            assert node.level in (0, 1)  # node.names: from * import name, ...
            # eg: from . import ?
            # eg: from .submodule import ?
            # eg: from pkg.submodule import ?
            import_keys = node.module.split(".") if node.module else []
            is_relative = node.level != 0
            imports.append(
                (import_keys, is_relative, is_eval_stack[-1], tuple(ast_node_stack))
            )
            return node

    # collect import from file
    with open(path) as f:
        AstImportCollector().generic_visit(node=ast.parse(f.read()))
        return imports


# ========================================================================= #
# Module Helper                                                             #
# ========================================================================= #


INIT_PY = "__init__.py"


ImportKey = Tuple[str, ...]
ImportType = Union[str, ImportKey, "Import", "Module"]


def _import_to_keys(import_: ImportType) -> ImportKey:
    # split the import if needed
    if isinstance(import_, str):
        import_ = import_.split(".")
    elif isinstance(import_, Import):
        import_ = import_.target_keys
    elif isinstance(import_, Module):
        import_ = import_.import_keys
    return tuple(import_)


def import_to_keys(import_: ImportType, check: bool = True) -> ImportKey:
    import_keys, orig = _import_to_keys(import_), import_
    # check, all parts must be identifiers, and there must be at least one part
    if check:
        import_check_keys(import_keys, orig=orig)
    return import_keys


def import_check_keys(import_keys: ImportKey, orig=None) -> ImportKey:
    if orig is None:
        orig = import_keys
    if not import_keys:
        raise ValueError(
            f"import path must have at least one part for: {repr(import_keys)}"
        )
    if not isinstance(import_keys, tuple):
        raise TypeError(
            f"import keys must be a tuple, got: {type(import_keys)} for: {repr(orig)}"
        )
    for part in import_keys:
        if not isinstance(part, str):
            raise TypeError(
                f"import part: {repr(part)} is not a string, got type: {type(part)}, obtained from: {repr(import_keys)}"
            )
        if not part.isidentifier():
            warnings.warn(
                f"import part: {repr(part)} is not a valid identifier, obtained from: {repr(import_keys)}"
            )
    return import_keys


def normalize_imports_pipe(
    imports: Iterable[ImportType],
    roots: bool = False,
    builtin: bool = True,
    keys: bool = False,
) -> Union[Iterable[ImportKey], Iterable[str]]:
    imports = (import_to_keys(imp) for imp in imports)
    if not builtin:
        imports = (imp for imp in imports if imp[0] not in BUILTIN_PKGS)
    if roots:
        imports = (imp[0:1] for imp in imports)
    if not keys:
        imports = (".".join(imp) for imp in imports)
    return imports


def is_python_module(path: Path, validate_name: bool = False) -> bool:
    is_module = path.is_file() and path.name.endswith(".py")
    if validate_name:
        is_module = is_module and path.name[:-3].isidentifier()
    return is_module


def is_python_package(path: Path, validate_name: bool = False) -> bool:
    is_package = path.is_dir() and path.joinpath(INIT_PY).is_file()
    if validate_name:
        is_package = is_package and path.name.isidentifier()
    return is_package


def is_child_import(parent, child) -> bool:
    parent = import_to_keys(parent)
    child = import_to_keys(child)
    if len(child) < len(parent):
        return False
    return parent == child[: len(parent)]


def find_modules(
    root: Path,
    max_depth: int = -1,
    skip_root_files: bool = False,
):
    def _recurse(path: Path, parent_keys: ImportKey, depth: int):
        if depth > max_depth >= 0:
            return

        # eg. <module>.py
        if is_python_module(path):
            if skip_root_files and depth == 0:
                return
            assert path.name != INIT_PY
            yield path, (*parent_keys, path.name[:-3])

        # eg. <package>/__init__.py
        elif is_python_package(path):
            keys = (*parent_keys, path.name)
            yield path, keys
            # continue recursively, making sure to skip __init__.py files
            for p in path.iterdir():
                if p.name != INIT_PY:
                    yield from _recurse(p, parent_keys=keys, depth=depth + 1)

    root = Path(root)
    # make sure that if we skip root __init__.py files
    if root.name == INIT_PY:
        warnings.warn(
            f"root cannot be an {INIT_PY} file, returning no modules for: {root.resolve()}"
        )
        return
    # find values!
    yield from (
        Module(module_path, import_keys)
        for module_path, import_keys in _recurse(root, parent_keys=(), depth=0)
    )


def _yield_import_and_keys(
    node: Union["Module", "ModuleNamespace"],
    roots: bool = False,
    builtin: bool = True,
) -> Iterable[Tuple[str, "Import"]]:
    for import_ in node.imports(builtin=builtin):
        if roots:
            key = import_.target_root
        else:
            key = import_.target_path
        yield key, import_


def _yield_imports(
    node: Union["Module", "ModuleNamespace"],
    roots: bool = False,
    builtin: bool = True,
) -> Iterable[str]:
    visited = set()
    for key, import_ in _yield_import_and_keys(node, roots=roots, builtin=builtin):
        # return the result if it has not been seen
        if key not in visited:
            visited.add(key)
            yield key


def _group_imports(
    node: Union["Module", "ModuleNamespace"],
    roots: bool = False,
    builtin: bool = True,
) -> Dict[str, List["Import"]]:
    groups = defaultdict(list)
    for key, import_ in _yield_import_and_keys(node, roots=roots, builtin=builtin):
        groups[key].append(import_)
    return dict(groups)


def _group_imports_from_modules(
    node: Union["Module", "ModuleNamespace"],
    roots: bool = False,
    builtin: bool = True,
) -> Dict[str, Set["Module"]]:
    groups = defaultdict(set)
    for key, import_ in _yield_import_and_keys(node, roots=roots, builtin=builtin):
        groups[key].add(import_.source_module)
    return groups


# ========================================================================= #
# Data Structures                                                           #
# ========================================================================= #


class Import:
    @classmethod
    def from_module_perspective(
        cls,
        module: "Module",
        keys: Union[str, Sequence[str]],
        is_relative: bool,
        is_immediate_eval: bool,
        ast_parents: Tuple[ast.AST],
    ):
        orig = keys
        if isinstance(keys, str):
            keys = keys.split(".")
        keys = tuple(keys)
        if is_relative:
            keys = module.import_keys[:-1] + keys
        import_check_keys(keys, orig=orig)
        return Import(
            keys,
            source_module=module,
            is_immediate_eval=is_immediate_eval,
            ast_parents=ast_parents,
        )

    def __init__(
        self,
        target: Union[str, Sequence[str]],
        source_module: "Module",
        is_immediate_eval: Optional[bool] = None,
        ast_parents: Optional[Tuple[ast.AST]] = None,
    ):
        self._target_keys = import_to_keys(target)
        self._source_module = source_module
        self._is_immediate_eval = is_immediate_eval
        self._ast_parents = ast_parents

    def __repr__(self):
        return f"{self.__class__.__name__}<{self.target_path}>"

    @property
    def is_immediate_eval(self) -> Optional[bool]:
        return self._is_immediate_eval

    @property
    def ast_parents(self) -> Optional[Tuple[ast.AST, ...]]:
        return self._ast_parents

    @property
    def target_keys(self) -> ImportKey:
        return self._target_keys

    @property
    def target_path(self) -> str:
        return ".".join(self._target_keys)

    @property
    def target_root(self) -> str:
        return self.target_keys[0]

    @property
    def target_depth(self) -> int:
        return len(self.target_keys)

    @property
    def source_module(self) -> "Module":
        return self._source_module

    def __eq__(self, other):
        if isinstance(other, (Module, Import, str, tuple)):
            return self.target_keys == import_to_keys(other, check=False)
        return False

    def __lt__(self, other):
        return self.target_keys < other.target_keys

    def __hash__(self):
        return hash("<import>" + self.target_path)


class Module:
    def __init__(
        self,
        path: Union[str, Path],
        import_: Union[str, Sequence[str]],
        _load_: bool = True,
    ):
        # check the path
        path = Path(path)
        if is_python_module(path):
            self._is_package = path.name == INIT_PY
        elif is_python_package(path):
            self._is_package = True
            path = path.joinpath(INIT_PY)
        else:
            raise ValueError(f"not a valid python module or package: {path}")
        # initialize
        self._abs_path: Path = path.absolute()
        self._import_keys = import_to_keys(import_)
        # load imports
        if _load_:
            self._imports = [
                Import.from_module_perspective(
                    self,
                    keys=keys,
                    is_relative=is_relative,
                    is_immediate_eval=is_immediate_eval,
                    ast_parents=ast_parents,
                )
                for keys, is_relative, is_immediate_eval, ast_parents in ast_get_module_imports(
                    self.path
                )
            ]
        else:
            self._imports = []

    def __repr__(self):
        return f"{self.__class__.__name__}<{self.import_path}>"

    def __eq__(self, other):
        if isinstance(other, (Module, Import, str, tuple)):
            return self.import_keys == import_to_keys(other, check=False)
        return False

    def __lt__(self, other):
        return self.import_keys < other.import_keys

    def __hash__(self):
        return hash("<module>" + self.import_path)

    @property
    def is_package(self) -> bool:
        return self._is_package

    @property
    def is_root(self) -> bool:
        return self.import_depth == 1

    @property
    def path(self) -> Path:
        return self._abs_path

    @property
    def import_keys(self) -> ImportKey:
        return self._import_keys

    @property
    def import_path(self) -> str:
        return ".".join(self._import_keys)

    @property
    def import_root(self) -> str:
        return self.import_keys[0]

    @property
    def import_depth(self) -> int:
        return len(self.import_keys)

    def imports(self, builtin: bool = True) -> Iterable[Import]:
        if builtin:
            yield from self._imports
        else:
            yield from (
                imp for imp in self._imports if imp.target_root not in BUILTIN_PKGS
            )

    def imports_unique(
        self, roots: bool = False, builtin: bool = True
    ) -> Iterable[str]:
        yield from _yield_imports(self, roots=roots, builtin=builtin)

    def imports_grouped(
        self, roots: bool = False, builtin: bool = True
    ) -> Dict[str, List[Import]]:
        return _group_imports(self, roots=roots, builtin=builtin)

    def imports_ref_modules(
        self, roots: bool = False, builtin: bool = True
    ) -> Dict[str, Set["Module"]]:
        return _group_imports_from_modules(self, roots=roots, builtin=builtin)


class ModuleNamespace:

    _modules: Dict[ImportKey, Module]

    def __init__(self):
        self._modules = {}
        # cache used to help speed up some functions
        # this might use a lot of memory, so we make
        # sure to limit its size when used
        self._cache = None

    def copy(self) -> "ModuleNamespace":
        namespace = ModuleNamespace()
        namespace._modules = dict(self._modules)
        return namespace

    def __repr__(self):
        return f'{self.__class__.__name__}<{", ".join(".".join(k) for k in self._modules.keys() if len(k) == 1)}>'

    # ~=~=~=~=~=~=~ #
    # Add Imports   #
    # ~=~=~=~=~=~=~ #

    def _add_import_unchecked(self, import_: Import):
        module_keys = import_.source_module.import_keys
        module = self._modules.get(module_keys, None)
        # create the module if missing
        if module is None:
            module = Module(import_.source_module.path, module_keys, _load_=False)
            self._modules[module_keys] = module
        # add the import to the module
        module._imports.append(import_)

    # ~=~=~=~=~=~=~ #
    # Add Modules   #
    # ~=~=~=~=~=~=~ #

    def add_modules(self, modules: Sequence[Module]) -> "ModuleNamespace":
        for module in modules:
            if module.import_keys in self._modules:
                raise RuntimeError(
                    f"module {repr(module.import_path)} has already been added to namespace"
                )
        for module in modules:
            self._modules[module.import_keys] = module
        return self

    def add_modules_from_packages(
        self, roots: Iterable[Union[str, Path]]
    ) -> "ModuleNamespace":
        modules = [m for root in roots for m in find_modules(root)]
        self.add_modules(modules)
        return self

    def add_modules_from_python_paths(
        self, python_paths: Optional[Iterable[Union[str, Path]]]
    ) -> "ModuleNamespace":
        if python_paths is None:
            python_paths = sys.path
        paths = [
            path
            for python_path in python_paths
            for path in Path(python_path).iterdir()
            if is_python_package(path) or is_python_module(path)
        ]
        self.add_modules_from_packages(paths)
        return self

    # ~=~=~=~=~=~=~ #
    # Filtering     #
    # ~=~=~=~=~=~=~ #

    def filtered(
        self,
        *,
        keep: Callable[[Module], bool] = None,
        remove: Callable[[Module], bool] = None,
    ) -> "ModuleNamespace":
        result = self.copy()
        if keep:
            result._modules = {k: m for k, m in result._modules.items() if keep(m)}
        if remove:
            result._modules = {
                k: m for k, m in result._modules.items() if not remove(m)
            }
        return result

    def restrict(self, imports, mode: str = "exact"):
        if isinstance(imports, (str, tuple, Import, Module)):
            imports = [imports]
        imports = set(import_to_keys(imp) for imp in imports)
        # restrict based on the mode
        if mode == "exact":
            return self.filtered(keep=lambda m: m.import_keys in imports)
        elif mode == "children":
            return self.filtered(
                keep=lambda m: any(
                    is_child_import(parent=keys, child=m) for keys in imports
                )
            )
        elif mode == "root_children":
            return self.filtered(
                keep=lambda m: any(
                    is_child_import(parent=keys[0], child=m) for keys in imports
                )
            )
        else:
            raise KeyError(f"invalid restrict mode: {repr(mode)}")

    def restrict_depth(self, depth: int, mode: str = "exact"):
        if depth < 0:
            return self
        if mode == "exact":
            return self.filtered(keep=lambda m: len(m.import_keys) == depth)
        elif mode == "children":
            return self.filtered(keep=lambda m: len(m.import_keys) >= depth)
        else:
            raise KeyError(f"invalid restrict mode: {repr(mode)}")

    # ~=~=~=~=~=~=~ #
    # Getters       #
    # ~=~=~=~=~=~=~ #

    def __getitem__(self, import_: ImportType):
        import_ = import_to_keys(import_)
        return self._modules[import_]

    def __contains__(self, import_: ImportType):
        import_ = import_to_keys(import_)
        return import_ in self._modules

    def __iter__(self) -> Iterable[Module]:
        yield from self._modules.values()

    def modules(self) -> Iterable[Module]:
        yield from self._modules.values()

    def modules_roots(self) -> Iterable[Module]:
        for k, m in self._modules.items():
            if len(k) == 1:
                yield m

    def imports(self, builtin: bool = True) -> Iterable[Import]:
        for module in self._modules.values():
            yield from module.imports(builtin=builtin)

    def imports_unique(
        self, roots: bool = False, builtin: bool = True
    ) -> Iterable[str]:
        yield from _yield_imports(self, roots=roots, builtin=builtin)

    def imports_grouped(
        self, roots: bool = False, builtin: bool = True
    ) -> Dict[str, List[Import]]:
        return _group_imports(self, roots=roots, builtin=builtin)

    def imports_ref_modules(
        self, roots: bool = False, builtin: bool = True
    ) -> Dict[str, Set[Module]]:
        return _group_imports_from_modules(self, roots=roots, builtin=builtin)

    def imports_resolved(
        self,
        against: "ModuleNamespace" = None,
        roots: bool = False,
        builtin: bool = True,
        mode: str = "exact",
    ) -> Set[str]:
        if against is None:
            against = self
        # get the unique imports, and flatten imports
        # using keys in the specified namespace
        return against.resolve_imports(
            imports=self.imports_unique(roots=False, builtin=builtin),
            roots=roots,
            builtin=builtin,
            mode=mode,
        )

    # ~=~=~=~=~=~=~ #
    # Resolving     #
    # ~=~=~=~=~=~=~ #

    def resolve_imports(
        self,
        imports: Iterable[ImportType],
        roots: bool = False,
        builtin: bool = True,
        mode: str = "exact",
    ) -> Set[str]:
        """
        This function only resolved the specified imports based on the current
        namespace, by performing a BFS
        - This nice thing is that you can restrict adding entries based on the `mode`
          to the "exact" files visited, or you can be safe by adding all "children",
          or even the "root_children" of the visited imports

         ALGORITHM:
         * perform a bfs, replacing keys that are visited with the designation keys
           - keys can only be visited if they are in the current namespace
           - this can be re-written as 1. perform bfs 2. remove keys in namespace
        """
        resolved = self._resolve_imports(
            imports=imports,
            mode=mode,
            _restrict_cache_=None,
        )
        resolved = set(
            normalize_imports_pipe(
                resolved,
                roots=roots,
                builtin=builtin,
                keys=False,
            )
        )
        return resolved

    def _resolve_imports(
        self,
        imports: Iterable[ImportType],
        mode: str,
        _restrict_cache_: Optional[Dict[ImportKey, Set[ImportKey]]],
    ) -> Set[ImportKey]:
        if _restrict_cache_ is None:
            _restrict_cache_ = {}

        def get_restricted_imports(keys: ImportKey) -> Set[ImportKey]:
            unique = _restrict_cache_.get(keys, None)
            if unique is None:
                unique = set(
                    imp.target_keys
                    for imp in self.restrict(keys, mode=mode).imports(builtin=True)
                )
                _restrict_cache_[keys] = unique
            return unique

        # 1. BFS
        stack: List[ImportKey] = list(set(import_to_keys(i) for i in imports))
        visited: Set[ImportKey] = set()
        while stack:
            current = stack.pop()
            visited.add(current)
            for imp in get_restricted_imports(current):
                if imp in visited:
                    continue
                stack.append(imp)

        # 2. DELETE OLD RESULTS
        visited -= self._modules.keys()

        # convert the imports back to strings
        return visited

    def resolve(
        self,
        namespace: "ModuleNamespace" = None,
        roots: bool = False,
        builtin: bool = True,
        mode: str = "exact",
    ) -> Dict[str, Set[str]]:
        # multiple packages in the same project may depend on each other
        # - this function finds those imports and replaces them with
        #   the imports from the other package, effectively finding all
        #   required parent dependencies in the tree
        against = self
        if namespace is None:
            namespace = self

        # speed things up by reusing results
        _restrict_cache_ = {}

        # for each module, BFS all the imports
        # - this is not as efficient as doing everything in a pass
        #   over the actual imports and replacing everything as we
        #   go, but conceptually, this is much easier to manage!
        module_imports = {}
        for key, module in namespace._modules.items():
            module_imports[key] = against._resolve_imports(
                imports=module.imports(),
                mode=mode,
                _restrict_cache_=_restrict_cache_,
            )
            # update the cache based on the current results to improve future speed!
            # this is duplicating conversion...
            _restrict_cache_[module.import_keys] = module_imports[key]

        # normalize the final results
        module_imports = {
            ".".join(k): set(
                normalize_imports_pipe(
                    resolved,
                    roots=roots,
                    builtin=builtin,
                    keys=False,
                )
            )
            for k, resolved in module_imports.items()
        }

        return module_imports


# ========================================================================= #
# EXPORT                                                                    #
# ========================================================================= #

__all__ = (
    "Import",
    "Module",
    "ModuleNamespace",
    "import_get_root",
    "import_is_builtin",
    "import_to_keys",
)
