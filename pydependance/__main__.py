# ============================================================================== #
# MIT License                                                                    #
#                                                                                #
# Copyright (c) 2022 Nathan                                                      #
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

import os.path
from pathlib import Path
from typing import Dict, List, Literal, Optional, Union

import tomlkit
from pydantic import BaseModel, Extra, Field, root_validator, validator
from tomlkit import TOMLDocument
from tomlkit.items import Array, Table

from pydependance._core import ModuleNamespace

# ========================================================================= #
# Configs                                                                   #
# ========================================================================= #


class CfgBase(BaseModel):
    class Config:
        extra = Extra.forbid


class CfgRestrict(CfgBase):
    # restrict the loaded namespace
    restrict: Optional[List[str]] = None
    restrict_mode: str = "children"
    restrict_depth: int = -1
    restrict_depth_mode: str = "children"


class CfgNamespace(CfgRestrict):
    name: str
    # discover the namespace
    pkg_roots: List[str] = Field(default_factory=list)
    pkg_search: List[str] = Field(default_factory=list)
    parents: List[str] = Field(default_factory=list)

    @root_validator()
    def _validate_parents(cls, values):
        if not (values["pkg_roots"] or values["pkg_search"], values["parents"]):
            raise ValueError(
                "must specify at least one of: [pkg_roots, pkg_search, parents]"
            )
        return values


class CfgOutput_CmdRequirements(CfgBase):
    mode: Literal["requirements"]
    namespace: str
    required: Optional[List[str]] = None
    optional: Optional[List[str]] = None
    path: Optional[Union[str, List[str]]] = None
    allow_files_as_modules: bool = True


class CfgOutput_CmdImportsAll(CfgBase):
    mode: Literal["imports_all"]
    namespace: str


# union of all commands
CfgOutput = Union[CfgOutput_CmdRequirements, CfgOutput_CmdImportsAll]


class Config(CfgBase):
    root: str
    namespaces: List[CfgNamespace] = Field(default_factory=list)
    outputs: List[CfgOutput] = Field(default_factory=list)
    import_map: Dict[str, str] = Field(default_factory=dict)
    versions: Dict[str, Optional[str]] = Field(default_factory=dict)

    @validator("root")
    def _validate_root(cls, root):
        if not os.path.isabs(root):
            raise ValueError("root must be an absolute path")
        return root

    @root_validator()
    def _validate_paths(cls, values):
        # update all relative paths to use the root
        root = values["root"]
        for namespace in values["namespaces"]:
            namespace.pkg_roots = [os.path.join(root, p) for p in namespace.pkg_roots]
            namespace.pkg_search = [os.path.join(root, p) for p in namespace.pkg_search]
        return values

    @root_validator()
    def _validate_deps(cls, values):
        def _check(name: str):
            if name.lower() != name:
                raise ValueError(
                    f"package name should be lowercase. PYPI is case insensitive. {repr(name)} -> {repr(name.lower())}"
                )
            if "-" in name:
                raise ValueError(
                    f'package name should use underscores instead of dashes, PYPI is dash-unserscore insensitive. {repr(name)} -> {repr(name.replace("-", "_"))}'
                )
            if not str.isidentifier(name):
                raise ValueError(
                    f"package name is not a valid python identifier: {repr(name)}"
                )

        # check
        # for name, version in values.get('import_map', {}).items():
        #     _check(name)
        for name, version in values.get("versions", {}).items():
            _check(name)
        # done!
        return values

    @root_validator()
    def _validate_namespaces(cls, values):
        namespaces = set()
        # 1. make sure namespace names are unique, and that parent namespaces exist
        for namespace in values.get("namespaces", []):
            if namespace.name in namespaces:
                raise ValueError(
                    f"namespace has duplicate name: {repr(namespace.name)}"
                )
            for parent in namespace.parents:
                if parent not in namespaces:
                    raise KeyError(
                        f"namespace: {repr(namespace.name)} has parent that does not yet exist: {repr(parent)}"
                    )
            namespaces.add(namespace.name)
        # 2. make sure that outputs have valid namespaces references
        for output in values.get("outputs", []):
            if output.namespace not in namespaces:
                raise KeyError(
                    f"output source namespace does not exist: {repr(output.namespace)}"
                )
            # if (output.resolve_against is not None) and (output.resolve_against not in namespaces):
            #     raise KeyError(f'output resolve_against namespace does not exist: {repr(output.resolve_against)}')
        # done!
        return values


# ========================================================================= #
# Runner                                                                    #
# ========================================================================= #


class Runner:
    def __init__(self, config: Config):
        self._config = config
        self._namespaces = self._load_namespaces(config)

    @classmethod
    def from_path(cls, path: Union[Path, str]):
        path = os.path.abspath(path)
        # handle loading the different file types
        if path.endswith(".toml"):
            import toml

            with open(path, "r") as fp:
                config = toml.load(fp)
            config = config.get("tool", {}).get("pydependance", {})
        elif path.endswith(".yaml") or path.endswith(".yml"):
            import yaml

            with open(path, "r") as fp:
                config = yaml.safe_load(fp)
        else:
            raise RuntimeError(f"unsupported path type: {path}")
        # - root is by default the parent folder of the config
        #   this affects all relative paths in the config itself
        config["root"] = os.path.abspath(
            os.path.join(path, "..", config.get("root", "."))
        )
        # done!
        return cls(Config(**config))

    # --- loading from config --- #

    @classmethod
    def _load_namespaces(cls, config: Config) -> Dict[str, ModuleNamespace]:
        # load the namespaces in order
        namespaces = {}
        for cfg_namespace in config.namespaces:
            namespaces[cfg_namespace.name] = cls._namespace_load(
                namespaces, config, cfg_namespace
            )
        return namespaces

    @classmethod
    def _namespace_load(
        cls,
        namespaces: Dict[str, ModuleNamespace],
        config: Config,
        cfg_namespace: CfgNamespace,
    ):
        # at this point, everything is already validated! all references should exist!
        namespace = ModuleNamespace()
        # 1. load individual packages -- add root to path if need
        if cfg_namespace.pkg_roots:
            namespace.add_modules_from_packages(
                os.path.join(config.root, path) for path in cfg_namespace.pkg_roots
            )
        # 2. load packages by searching, like for PYTHONPATH -- add root to path if need
        if cfg_namespace.pkg_search:
            namespace.add_modules_from_python_paths(
                os.path.join(config.root, path) for path in cfg_namespace.pkg_search
            )
        # 3. add existing namespaces to this namespace
        if cfg_namespace.parents:
            for parent_name in cfg_namespace.parents:
                modules = list(namespaces[parent_name].modules())
                namespace.add_modules(modules)
        # 4. restrict the namespace
        namespace = cls._namespace_restrict(cfg_namespace, namespace)
        return namespace

    @classmethod
    def _namespace_restrict(
        cls, cfg_namespace: CfgNamespace, namespace: ModuleNamespace
    ) -> ModuleNamespace:
        if cfg_namespace.restrict:
            namespace = namespace.restrict(
                imports=cfg_namespace.restrict, mode=cfg_namespace.restrict_mode
            )
        if cfg_namespace.restrict_depth >= 0:
            namespace = namespace.restrict_depth(
                depth=cfg_namespace.restrict_depth,
                mode=cfg_namespace.restrict_depth_mode,
            )
        return namespace

    def run(self):
        for output in self._config.outputs:
            fn = _COMMANDS[output.mode]
            fn(self._config, output, self._namespaces[output.namespace])


# ========================================================================= #
# Requirement Writers                                                       #
# ========================================================================= #


class ReqWriter:
    def __init__(self, path: Optional[str]):
        self.path = path
        self.load()

    def write_deps(self, deps, modules, diff):
        raise NotImplementedError

    def write_optional(self, module, deps, diff, already_included):
        raise NotImplementedError

    def load(self):
        raise NotImplementedError

    def save(self):
        raise NotImplementedError

    def print(self):
        raise NotImplementedError


class ReqWriterToml(ReqWriter):
    def write_deps(self, deps, modules, diff):
        self._fill_list(self.rdeps, deps)
        if deps:
            self.rdeps.comment(
                f"[{', '.join(sorted(modules))}]"
                + (f" -> [{', '.join(sorted(diff))}]" if diff else "")
            )

    def write_optional(self, module, deps, diff, already_included):
        self.odeps.add(tomlkit.ws("\n"))
        self.odeps.add(tomlkit.comment(f"{module} -> [{', '.join(sorted(diff))}]"))
        if already_included:
            self.odeps.add(
                tomlkit.comment(
                    f"- already included: {', '.join(sorted(already_included))}"
                )
            )
        self.odeps.append(module, self._fill_list(tomlkit.array(), deps))

    def _fill_list(self, array: Array, items):
        items = list(items)
        array.clear()
        if items:
            for r in items:
                array.add_line(r)
            array.add_line(indent="")
        return array

    def load(self):
        # load pyproject.toml
        if self.path and os.path.exists(self.path):
            with open(self.path, "r") as fp:
                self.pyproject: TOMLDocument = tomlkit.load(fp)
        else:
            self.pyproject = TOMLDocument()
        # load dependencies
        self.project: Table = self.pyproject.setdefault("project", {})
        self.project["dependencies"] = []
        self.project["optional-dependencies"] = {}
        self.rdeps: Array = self.project["dependencies"]
        self.odeps: Table = self.project["optional-dependencies"]

    def save(self):
        if self.path:
            with open(self.path, "w") as fp:
                tomlkit.dump(self.pyproject, fp)

    def print(self):
        print(tomlkit.dumps(self.pyproject))


class ReqWriterTxt(ReqWriter):
    def write_deps(self, deps, modules, diff):
        self.lines.append(
            f"# DEPENDENCIES: [{', '.join(sorted(modules))}]"
            + (f" -> [{', '.join(sorted(diff))}]" if diff else "")
        )
        self.lines.extend(deps)

    def write_optional(self, module, deps, diff, already_included):
        self.lines.append("")
        self.lines.append(f"# OPTIONAL: {module} -> [{', '.join(sorted(diff))}]")
        self.lines.append(
            f"# - already included: {', '.join(sorted(already_included))}"
        )
        self.lines.extend(f"# | {d}" for d in deps)

    def load(self):
        self.lines = []

    def save(self):
        with open(self.path, "w") as fp:
            fp.writelines(f"{l}\n" for l in self.lines)

    def print(self):
        for line in self.lines:
            print(line)


# ========================================================================= #
# COMMANDS                                                                  #
# ========================================================================= #


def _command_requirements_collect(
    output: CfgOutput_CmdRequirements, namespace: ModuleNamespace
):
    # 1. all imports are required by default
    required = output.required
    if required is None:
        required = set(
            module.import_path
            for module in namespace.modules_roots()
            if (module.is_package or output.allow_files_as_modules)
        )

    # 2. all remaining imports are optional by default
    optional = output.optional
    if optional is None:
        optional = set(
            module.import_path
            for module in namespace.modules_roots()
            if (module.is_package or output.allow_files_as_modules) and (module.import_path not in required)
        )

    # 3. collect all the children imports in the modules
    def _get_imports(module: str):
        ns = namespace.restrict([module], mode="children")
        orig = set(ns.imports_unique(roots=True, builtin=False))
        resolved = set(
            ns.imports_resolved(
                against=namespace, roots=True, builtin=False, mode="children"
            )
        )
        return orig, resolved

    required = {module: _get_imports(module) for module in sorted(required)}
    optional = {module: _get_imports(module) for module in sorted(optional)}
    return required, optional


def _command_requirements_write(
    writer: ReqWriter, config: Config, required: dict, optional: dict
):
    def _replace(import_: str):
        # import_ = import_.replace('-', '_').lower()
        import_ = config.import_map.get(import_, import_)
        version = config.versions.get(import_, None)
        return f"{import_}{version}" if version else f"{import_}"

    # 1. get the required deps
    required_modules = set(required.keys())
    required_orig = set(k for orig, resolved in required.values() for k in orig)
    required_resolved = set(k for orig, resolved in required.values() for k in resolved)
    required_diff = required_orig - required_resolved
    required_deps = sorted(set(map(_replace, required_resolved)))
    # - generate the required deps output
    writer.write_deps(required_deps, required_modules, required_diff)

    # 2. add the optional items
    for module, (mo, mr) in optional.items():
        # remove required from orig and resolved
        module_orig = mo - required_resolved
        module_resolved = mr - required_resolved
        # output
        module_diff = module_orig - module_resolved
        module_deps = sorted(set(map(_replace, module_resolved)))
        already_included = mr & required_resolved
        # update
        writer.write_optional(module, module_deps, module_diff, already_included)


def _command_requirements(
    config: Config, output: CfgOutput_CmdRequirements, namespace: ModuleNamespace
):
    # normalize
    paths = output.path
    if paths is None:
        return
    elif isinstance(paths, str):
        paths = [paths]

    # collect requirements
    required, optional = _command_requirements_collect(output, namespace)

    for path in paths:
        # add root to path if needed
        path = os.path.join(config.root, path)
        if path.endswith(".toml"):
            writer = ReqWriterToml(path)
        elif path.endswith(".txt") or path.endswith(".in"):
            writer = ReqWriterTxt(path)
        else:
            raise RuntimeError(
                f"unsupported requirements file type, for file: {Path(path).name}"
            )

        # print seperator
        print(f'\n# {"="*77} #\n# {path}\n# {"="*77} #\n')

        # load, write, save
        writer.load()    
        _command_requirements_write(writer, config, required, optional)
        writer.print()
        writer.save()


_COMMANDS = {"requirements": _command_requirements}


# ========================================================================= #
# ENTRY                                                                     #
# ========================================================================= #


if __name__ == "__main__":

    def cli():
        import argparse

        parser = argparse.ArgumentParser()
        parser.add_argument("-c", "--config", type=str, required=True)
        args = parser.parse_args()

        runner = Runner.from_path(args.config)

        try:
            runner.run()
        except Exception as e:
            print(f"error: {e} for config: {repr(args.config)}")
            raise e

    cli()
