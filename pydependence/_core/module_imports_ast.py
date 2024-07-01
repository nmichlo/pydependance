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


import ast
import dataclasses
import sys
import warnings
from collections import Counter, defaultdict
from enum import Enum
from typing import DefaultDict, Dict, List, Literal, NamedTuple, Optional, Tuple

from pydependence._core.module_data import ModuleMetadata
from pydependence._core.utils import assert_valid_import_name, assert_valid_module_path

# ========================================================================= #
# Polyfill                                                                  #
# ========================================================================= #


def ast_unparse(node: ast.AST) -> str:
    # if not python 3.8 then call ast.unparse, otherwise polyfill
    if hasattr(ast, "unparse"):
        return ast.unparse(node)
    else:
        warnings.warn(
            f"Current version of python: {sys.version_info} does not support `ast.unparse`"
        )
        return str(node)


# ========================================================================= #
# Allowed Nodes Leading To Imports                                          #
# ========================================================================= #

# PYTHON VERSION: 3.10
# every possible way to reach an import statement, or because we also choose to
# support plugins, all expressions should be reachable. We skip the AST nodes
# that do not matter in reaching these.
# - https://docs.python.org/3/library/ast.html
_DISALLOWED_IMPORT_STATEMENT_NODES = {
    #          -- the following expression can appear in assignment context
    #          | Name(identifier id, expr_context ctx)
    "Name",
    #     | Global(identifier* names)
    #     | Nonlocal(identifier* names)
    #     | Pass | Break | Continue
    #     | Constant(constant value, string? kind)
    "Global",
    "Nonlocal",
    "Pass",
    "Break",
    "Continue",
    "Constant",
    #     alias = (identifier name, identifier? asname)
    #              attributes (int lineno, int col_offset, int? end_lineno, int? end_col_offset)
    "alias"
    #     attributes (int lineno, int col_offset, int end_lineno, int end_col_offset)
    "attributes",
    #     type_ignore = TypeIgnore(int lineno, string tag)
    "TypeIgnore",
    # ================================================================================ #
    #     expr_context = Load | Store | Del
    "Load",
    "Store",
    "Del",
    #     boolop = And | Or
    "And",
    "Or",
    #     operator = Add | Sub | Mult | MatMult | Div | Mod | Pow | LShift
    #                  | RShift | BitOr | BitXor | BitAnd | FloorDiv
    "Add",
    "Sub",
    "Mult",
    "MatMult",
    "Div",
    "Mod",
    "Pow",
    "LShift",
    "RShift",
    "BitOr",
    "BitXor",
    "BitAnd",
    "FloorDiv",
    #     unaryop = Invert | Not | UAdd | USub
    "Invert",
    "Not",
    "UAdd",
    "USub",
    #     cmpop = Eq | NotEq | Lt | LtE | Gt | GtE | Is | IsNot | In | NotIn
    "Eq",
    "NotEq",
    "Lt",
    "LtE",
    "Gt",
    "GtE",
    "Is",
    "IsNot",
    "In",
    "NotIn",
}

# these nodes are considered to cause lazy evaluation of imports. Side effects
# on a module level for example should be considered unsupported behavior and should
# never be considered for triggering an import.
_IS_INDIRECT_NODE = {
    "FunctionDef",
    "AsyncFunctionDef",
}


# lazy import callables
_LAZY_IMPORT_CALLABLES = {
    "lazy_import",
}

# lazy attribute callables
_LAZY_ATTRIBUTE_CALLABLES = {
    "lazy_callable",
    "lazy_inheritable",
}

# lazy
_LAZY_CALLABLES = {*_LAZY_IMPORT_CALLABLES, *_LAZY_ATTRIBUTE_CALLABLES}


# ========================================================================= #
# AST IMPORT PARSER                                                         #
# ========================================================================= #


class ImportSourceEnum(str, Enum):
    import_ = "import_"
    import_from = "import_from"
    lazy_plugin = "lazy_plugin"
    # type_check = 'type_check'  # TODO


@dataclasses.dataclass
class BasicImportInfo:
    # target
    target: str
    source_name: str
    is_lazy: bool

    @property
    def root_target(self) -> str:
        return self.target.split(".")[0]


class ManualSource:
    def __init__(self, orig_name: str):
        self.orig_name = orig_name

    def __str__(self):
        return f"<manual: {self.orig_name}>"

    def __repr__(self):
        return f"{self.__class__.__name__}({self.orig_name})"

    def __eq__(self, other):
        if isinstance(other, str):
            return str(self) == other
        elif isinstance(other, ManualSource):
            return self.orig_name == other.orig_name
        return False

    def __lt__(self, other):
        if isinstance(other, str):
            return str(self) < other
        elif isinstance(other, ManualSource):
            return self.orig_name < other.orig_name
        else:
            raise TypeError(f"Invalid types: {type(self)} < {type(other)}")

    def __hash__(self):
        return hash(str(self))


@dataclasses.dataclass
class ManualImportInfo(BasicImportInfo):
    source_name: ManualSource
    is_lazy: Literal[False] = False

    @classmethod
    def from_target(cls, target: str) -> "ManualImportInfo":
        return cls(target=target, source_name=ManualSource(target))


@dataclasses.dataclass
class LocImportInfo(BasicImportInfo):
    # source, e.g. import statement or type check or lazy plugin
    source_name: str
    source_module_info: ModuleMetadata
    source_type: ImportSourceEnum
    # debug
    lineno: int
    col_offset: int
    stack_type_names: Tuple[str, ...]
    # relative import
    is_relative: bool

    @property
    def tagged_target(self) -> str:
        return f"{self.source_module_info.tag}:{self.target}"

    @property
    def tagged_name_and_target(self) -> str:
        return f"{self.source_module_info.tagged_name}:{self.target}"


class _AstImportsCollector(ast.NodeVisitor):

    def __init__(self, module_info: ModuleMetadata):
        self._module_info: ModuleMetadata = module_info
        self._imports: "DefaultDict[str, List[LocImportInfo]]" = defaultdict(list)
        self._stack_is_lazy: "List[bool]" = [False]
        self._stack_ast_kind: "List[str]" = []
        self._counter = Counter()

    # ~=~=~ WARN ~=~=~ #

    def _node_warn(self, node: ast.AST, message: str):
        warnings.warn_explicit(
            message=f"`{ast_unparse(node)}`: {message}",
            category=SyntaxWarning,
            filename=str(self._module_info.path),
            lineno=node.lineno,
        )

    # ~=~=~ STACK ~=~=~ #

    def _push_current_import(
        self,
        node: ast.AST,
        target: str,
        source_type: ImportSourceEnum,
        is_lazy: "Optional[bool]" = None,
        is_relative: bool = False,
    ):
        import_ = LocImportInfo(
            source_name=self._module_info.name,
            source_module_info=self._module_info,
            target=target,
            is_lazy=self._stack_is_lazy[-1] if (is_lazy is None) else is_lazy,
            lineno=node.lineno,
            col_offset=node.col_offset,
            source_type=source_type,
            stack_type_names=tuple(self._stack_ast_kind),
            is_relative=is_relative,
        )
        self._imports[target].append(import_)

    # ~=~=~ VISIT ~=~=~ #

    def visit(self, node):
        kind = node.__class__.__name__
        if kind in _DISALLOWED_IMPORT_STATEMENT_NODES:
            return
        # push - basic interpreter
        is_lazy = self._stack_is_lazy[-1] or (kind in _IS_INDIRECT_NODE)
        self._stack_ast_kind.append(kind)
        self._stack_is_lazy.append(is_lazy)
        # continue recursion
        try:
            getattr(self, "visit_" + kind, self.generic_visit)(node)
        finally:
            # pop
            self._stack_is_lazy.pop()
            self._stack_ast_kind.pop()

    def generic_visit_lazy(self, node):
        self._stack_is_lazy.append(True)
        try:
            self.generic_visit(node)
        finally:
            self._stack_is_lazy.pop()

    # >>> VISIT NODES <<< #

    def visit_FunctionDef(self, node):
        return self.generic_visit_lazy(node)

    def visit_AsyncFunctionDef(self, node):
        return self.generic_visit_lazy(node)

    def visit_Import(self, node: ast.Import):
        # eg. import pkg.submodule
        for alias in node.names:
            self._push_current_import(
                node=node,
                target=alias.name,
                source_type=ImportSourceEnum.import_,
            )

    def visit_ImportFrom(self, node: ast.ImportFrom):
        assert node.level in (0, 1)  # node.names: from * import name, ...
        # eg: from . import ?
        # eg: from .submodule import ?
        # eg: from pkg.submodule import ?
        is_relative = node.level != 0
        if is_relative:
            _parts = self._module_info.name.split(".")
            if not self._module_info.ispkg:
                _parts.pop()
            _parts.append(node.module)
            target = ".".join(_parts)
            assert_valid_import_name(target)
        else:
            target = node.module
        self._push_current_import(
            node=node,
            target=target,
            source_type=ImportSourceEnum.import_from,
            is_relative=is_relative,
        )

    # >>> CUSTOM LAZY IMPORT LIBRARY

    def visit_If(self, node: ast.If):
        """
        check name is `TYPE_CHECKING` or attr is `typing.TYPE_CHECKING`:
        - WE DON'T SUPPORT ANY OTHER VARIATIONS
        - WE ASSUME THE VARIABLE IS NEVER RENAMED
        """
        # check if this is a type checking block
        is_type_checking = False
        if isinstance(node.test, ast.Attribute):
            if (
                isinstance(node.test.value, ast.Name)
                and node.test.value.id == "typing"
                and node.test.attr == "TYPE_CHECKING"
            ):
                is_type_checking = True
        elif isinstance(node.test, ast.Name):
            if node.test.id == "TYPE_CHECKING":
                is_type_checking = True
        # recurse
        if not is_type_checking:
            return self.generic_visit(node)
        else:
            return self.generic_visit_lazy(node)

    def visit_Call(self, node: ast.Call):
        """
        we don't implement an interpreter, we only handle lazy imports with an
        exact function name and a single string argument. These functions should
        be defined by the user. We do not provide any default functions.
          e.g. `lazy_import("os.path")`
        we don't support attribute access or any deviation from the above
          e.g. `util.lazy_import("os.path.join")`

        - the function names must be one of:
          * `lazy_import("os.path")`
          * `lazy_callable("pathlib.Attr")`  # final .Path is excluded, import is `pathlib`
          * `lazy_inheritable("pathlib.Attr")`  # final .Path is excluded, import is `pathlib`
          - WE DON'T SUPPORT ANY OTHER VARIATIONS
          - WE ASSUME THE VARIABLE IS NEVER RENAMED
        """
        # - check the call is directly on a name e.g. `lazy_import(...)` and not `util.lazy_import(...)` or `util['lazy_import'](...)`
        if not isinstance(node.func, ast.Name):
            return
        # - check the function name is one of the lazy import functions
        name = node.func.id
        if name not in _LAZY_CALLABLES:
            return
        # - make sure no keyword arguments are used, these invalidate the import.
        if node.keywords:
            self._node_warn(node, f"should not have keyword arguments.")
            return
        # - make sure that the function is called with a single string argument
        if not len(node.args) == 1:
            self._node_warn(
                node, f"called with {len(node.args)} arguments, expected: 1"
            )
            return
        [arg] = node.args
        # - make sure that the argument is a string
        if not isinstance(arg, ast.Constant) or not isinstance(arg.value, str):
            self._node_warn(
                node, f"called with non-string argument: `{ast_unparse(arg)}`"
            )
            return
        # - validate the import string
        import_ = arg.value
        try:
            assert_valid_import_name(import_)
        except Exception as e:
            self._node_warn(node, f"called with invalid import path: {e}")
            return
        # - check if the import path includes an attribute and strip it
        if name in _LAZY_ATTRIBUTE_CALLABLES:
            _parts = import_.rsplit(".", maxsplit=1)
            if len(_parts) < 2:
                self._node_warn(
                    node, f"called with invalid import path to an attribute: {import_}"
                )
                return
            import_ = _parts[0]
        # - add the import
        self._push_current_import(
            node=node,
            target=import_,
            source_type=ImportSourceEnum.lazy_plugin,
            is_lazy=True,
        )

    # >>> PRETTY PRINT <<< #

    @classmethod
    def _ast_to_dict(cls, n):
        if isinstance(n, ast.AST):
            return {f: cls._ast_to_dict(getattr(n, f)) for f in n._fields}
        elif isinstance(n, list):
            return [cls._ast_to_dict(i) for i in n]
        else:
            return n

    @classmethod
    def load_imports_from_module_info(
        cls, module_info: ModuleMetadata, *, debug: bool = False
    ) -> "Dict[str, List[LocImportInfo]]":
        # load the file & parse
        path = assert_valid_module_path(module_info.path)
        name = assert_valid_import_name(module_info.name)
        with open(path) as fp:
            _dat = fp.read()
            _ast = ast.parse(_dat)
        # collect imports
        _parser = _AstImportsCollector(module_info=module_info)
        _parser.visit(_ast)
        # debug
        if debug:
            total = sum(_parser._counter.values())
            top = _parser._counter.most_common(5)
            print(
                f"Visited {total} nodes, top 5: {top} for module: {repr(name)} file: {module_info.path}"
            )
        # done!
        return _parser._imports


def load_imports_from_module_info(
    module_info: ModuleMetadata,
) -> "Dict[str, List[LocImportInfo]]":
    return _AstImportsCollector.load_imports_from_module_info(module_info)


# ========================================================================= #
# END                                                                       #
# ========================================================================= #


__all__ = (
    "load_imports_from_module_info",
    "LocImportInfo",
    "ImportSourceEnum",
)


# PYTHON VERSION: 3.10
# {
#         #     mod = Module(stmt* body, type_ignore* type_ignores)
#         #         | Interactive(stmt* body)
#         #         | Expression(expr body)
#         #         | FunctionType(expr* argtypes, expr returns)
#         "Module",
#         "Interactive",
#         "Expression",
#         #     stmt = FunctionDef(identifier name, arguments args,
#         #                        stmt* body, expr* decorator_list, expr? returns,
#         #                        string? type_comment)
#         #           | AsyncFunctionDef(identifier name, arguments args,
#         #                              stmt* body, expr* decorator_list, expr? returns,
#         #                              string? type_comment)
#         #
#         "FunctionDef",
#         "AsyncFunctionDef",
#         #           | ClassDef(identifier name,
#         #              expr* bases,
#         #              keyword* keywords,
#         #              stmt* body,
#         #              expr* decorator_list)
#         #           | Return(expr? value)
#         "ClassDef",
#         "Return",
#         #           | Delete(expr* targets)
#         #           | Assign(expr* targets, expr value, string? type_comment)
#         #           | AugAssign(expr target, operator op, expr value)
#         "Delete",
#         "Assign",
#         "AugAssign",
#         #           -- 'simple' indicates that we annotate simple name without parens
#         #           | AnnAssign(expr target, expr annotation, expr? value, int simple)
#         "AnnAssign",
#         #           -- use 'orelse' because else is a keyword in target languages
#         #           | For(expr target, expr iter, stmt* body, stmt* orelse, string? type_comment)
#         #           | AsyncFor(expr target, expr iter, stmt* body, stmt* orelse, string? type_comment)
#         #           | While(expr test, stmt* body, stmt* orelse)
#         #           | If(expr test, stmt* body, stmt* orelse)
#         #           | With(withitem* items, stmt* body, string? type_comment)
#         #           | AsyncWith(withitem* items, stmt* body, string? type_comment)
#         "For",
#         "AsyncFor",
#         "While",
#         "If",
#         "With",
#         "AsyncWith",
#         #           | Match(expr subject, match_case* cases)  # stmt
#         "Match",
#         #           | Raise(expr? exc, expr? cause)
#         #           | Try(stmt* body, excepthandler* handlers, stmt* orelse, stmt* finalbody)
#         #           | TryStar(stmt* body, excepthandler* handlers, stmt* orelse, stmt* finalbody)
#         #           | Assert(expr test, expr? msg)
#         "Raise",
#         "Try",
#         "TryStar",
#         "Assert",
#         #           | Import(alias* names)
#         #           | ImportFrom(identifier? module, alias* names, int? level)
#         "Import",
#         "ImportFrom",
#         #           | Global(identifier* names)
#         #           | Nonlocal(identifier* names)
#         #           | Expr(expr value)
#         #           | Pass | Break | Continue
#         #
#         #           -- col_offset is the byte offset in the utf8 string the parser uses
#         #           attributes (int lineno, int col_offset, int? end_lineno, int? end_col_offset)
#         "Global",
#         "Nonlocal",
#         "Expr",
#         "Pass",
#         "Break",
#         "Continue",
#         #           -- BoolOp() can use left & right?
#         #     expr = BoolOp(boolop op, expr* values)
#         #          | NamedExpr(expr target, expr value)
#         #          | BinOp(expr left, operator op, expr right)
#         #          | UnaryOp(unaryop op, expr operand)
#         "BoolOp",
#         "NamedExpr",
#         "BinOp",
#         "UnaryOp",
#         #          | Lambda(arguments args, expr body)
#         #          | IfExp(expr test, expr body, expr orelse)
#         #          | Dict(expr* keys, expr* values)
#         #          | Set(expr* elts)
#         #          | ListComp(expr elt, comprehension* generators)
#         #          | SetComp(expr elt, comprehension* generators)
#         #          | DictComp(expr key, expr value, comprehension* generators)
#         #          | GeneratorExp(expr elt, comprehension* generators)
#         "Lambda",
#         "IfExp",
#         "Dict",
#         "Set",
#         "ListComp",
#         "SetComp",
#         "DictComp",
#         "GeneratorExp",
#         #          -- the grammar constrains where yield expressions can occur
#         #          | Await(expr value)
#         #          | Yield(expr? value)
#         #          | YieldFrom(expr value)
#         "Await",
#         "Yield",
#         "YieldFrom",
#         #          -- need sequences for compare to distinguish between
#         #          -- x < 4 < 3 and (x < 4) < 3
#         #          | Compare(expr left, cmpop* ops, expr* comparators)
#         #          | Call(expr func, expr* args, keyword* keywords)
#         #          | FormattedValue(expr value, int conversion, expr? format_spec)
#         #          | JoinedStr(expr* values)
#         #          | Constant(constant value, string? kind)
#         "Compare",
#         "Call",
#         "FormattedValue",
#         "JoinedStr",
#         "Constant",
#         #          -- the following expression can appear in assignment context
#         #          | Attribute(expr value, identifier attr, expr_context ctx)
#         #          | Subscript(expr value, expr slice, expr_context ctx)
#         #          | Starred(expr value, expr_context ctx)
#         #          | Name(identifier id, expr_context ctx)
#         #          | List(expr* elts, expr_context ctx)
#         #          | Tuple(expr* elts, expr_context ctx)
#         "Attribute",
#         "Subscript",
#         "Starred",
#         "Name",
#         "List",
#         "Tuple",
#         #          -- can appear only in Subscript
#         #          | Slice(expr? lower, expr? upper, expr? step)
#         "Slice",
#         #           -- col_offset is the byte offset in the utf8 string the parser uses
#         #           attributes (int lineno, int col_offset, int? end_lineno, int? end_col_offset)
#         #
#         #     expr_context = Load | Store | Del
#         "Load",
#         "Store",
#         "Del",
#         #     boolop = And | Or
#         "And",
#         "Or",
#         #     operator = Add | Sub | Mult | MatMult | Div | Mod | Pow | LShift
#         #                  | RShift | BitOr | BitXor | BitAnd | FloorDiv
#         "Add",
#         "Sub",
#         "Mult",
#         "MatMult",
#         "Div",
#         "Mod",
#         "Pow",
#         "LShift",
#         "RShift",
#         "BitOr",
#         "BitXor",
#         "BitAnd",
#         "FloorDiv",
#         #     unaryop = Invert | Not | UAdd | USub
#         "Invert",
#         "Not",
#         "UAdd",
#         "USub",
#         #     cmpop = Eq | NotEq | Lt | LtE | Gt | GtE | Is | IsNot | In | NotIn
#         "Eq",
#         "NotEq",
#         "Lt",
#         "LtE",
#         "Gt",
#         "GtE",
#         "Is",
#         "IsNot",
#         "In",
#         "NotIn",

#         #     comprehension = (expr target, expr iter, expr* ifs, int is_async)
#         "comprehension",
#         #     excepthandler = ExceptHandler(expr? type, identifier? name, stmt* body)
#         #                     attributes (int lineno, int col_offset, int? end_lineno, int? end_col_offset)
#         "ExceptHandler",
#         #     arguments = (arg* posonlyargs, arg* args, arg? vararg, arg* kwonlyargs,
#         #                  expr* kw_defaults, arg? kwarg, expr* defaults)
#         "arguments",
#         #     arg = (identifier arg, expr? annotation, string? type_comment)
#         #            attributes (int lineno, int col_offset, int? end_lineno, int? end_col_offset)
#         "arg",
#         #     -- keyword arguments supplied to call (NULL identifier for **kwargs)
#         #     keyword = (identifier? arg, expr value)
#         #                attributes (int lineno, int col_offset, int? end_lineno, int? end_col_offset)
#         "keyword",
#         #     -- import name with optional 'as' alias.
#         #     alias = (identifier name, identifier? asname)
#         #              attributes (int lineno, int col_offset, int? end_lineno, int? end_col_offset)
#         "alias",
#         #     withitem = (expr context_expr, expr? optional_vars)
#         "withitem",
#         #     match_case = (pattern pattern, expr? guard, stmt* body)
#         "matchcase",
#         #     pattern = MatchValue(expr value)
#         #             | MatchSingleton(constant value)
#         #             | MatchSequence(pattern* patterns)
#         #             | MatchMapping(expr* keys, pattern* patterns, identifier? rest)
#         #             | MatchClass(expr cls, pattern* patterns, identifier* kwd_attrs, pattern* kwd_patterns)
#         "MatchValue",
#         "MatchSingleton",
#         "MatchSequence",
#         "MatchMapping",
#         "MatchClass",
#         #             | MatchStar(identifier? name)
#         #             -- The optional "rest" MatchMapping parameter handles capturing extra mapping keys
#         "MatchStar",
#         #             | MatchAs(pattern? pattern, identifier? name)
#         #             | MatchOr(pattern* patterns)
#         "MatchAs",
#         "MatchOr",
#         #              attributes (int lineno, int col_offset, int end_lineno, int end_col_offset)
#         "attributes",
#         #     type_ignore = TypeIgnore(int lineno, string tag)
#         "TypeIgnore",
#
#         # visit methods for deprecated nodes
#         "ExtSlice",
#         "Index",
#         "Suite",
#         "AugLoad",
#         "AugStore",
#         "Param",
#         "Num",
#         "Str",
#         "Bytes",
#         "NameConstant",
#         "Ellipsis",
#     }
