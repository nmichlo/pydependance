
<p align="center">
    <h1 align="center">🕵️ PyDependence 🐍</h1>
    <p align="center">
        <i>Python local package dependency discovery and resolution</i>
    </p>
</p>

<p align="center">
    <a href="https://choosealicense.com/licenses/mit/" target="_blank">
        <img alt="license" src="https://img.shields.io/github/license/nmichlo/pydependence?style=flat-square&color=lightgrey"/>
    </a>
    <a href="https://pypi.org/project/pydependence" target="_blank">
        <img alt="python versions" src="https://img.shields.io/pypi/pyversions/pydependence?style=flat-square"/>
    </a>
    <a href="https://pypi.org/project/pydependence" target="_blank">
        <img alt="pypi version" src="https://img.shields.io/pypi/v/pydependence?style=flat-square&color=blue"/>
    </a>
    <a href="https://github.com/nmichlo/pydependence/actions/workflows/python-test.yml">
        <img alt="tests status" src="https://img.shields.io/github/actions/workflow/status/nmichlo/pydependence/python-test.yml?branch=main&label=tests&style=flat-square"/>
    </a>
    <a href="https://codecov.io/gh/nmichlo/pydependence">
        <!-- <img src="https://codecov.io/gh/nmichlo/pydependence/graph/badge.svg?token=DOMMIVWZQF"/> -->
        <img src="https://img.shields.io/codecov/c/github/nmichlo/pydependence?style=flat-square&color=green">
    </a>
</p>

<p align="center">
    <p align="center">
        <a href="https://github.com/nmichlo/pydependence/issues/new/choose">Contributions</a> are welcome!
    </p>
</p>

----------------------

## Table Of Contents

- [Overview](#overview)
  + [Why](#Why)
  + [How This Works](#how-this-works)
- [Configuration](#configuration)
- [Usage](#usage)
  + [Usage - Pre-Commit](#usage---pre-commit)
  + [Usage - CLI](#usage---cli)
- [Help](#help)
  + [Version Mapping](#version-mapping)
  + [Scopes](#scopes)
    * [Sub-Scopes](#sub-scopes)
  + [Output Resolvers](#output-resolvers)
  + [Example](#example)

----------------------

## Overview

If multiple dependencies are listed in a project, only some of them may actually be required!
This project finds those dependencies!

### Why

This project was created for multiple reasons
- Find missing dependencies
- Generate optional dependencies lists, eg. for pyproject.toml
- Create minimal dockerfiles with only the dependencies that are needed for
  a specific entrypoint 

### How This Works

1. Specify root python packages to search through (we call this the _namespace_)
   - This can either be modules under a folder, similar to PYTHONPATH
   - Or actual paths to modules
2. The AST of each python file is parsed, and import statements are found
3. Finally, dependencies are resolved using graph traversal and flattened.
   - imports that redirect to modules within the current scope
     are flattened and replaced with imports not in the scope.

----------------------

## Configuration

_Check the [pyproject.toml](./pyproject.toml) for detailed explanations of various config options and a working example of `pydependence` applied to itself._

It is recommended to specify the config inside your projects existing `pyproject.toml`
file, however, pydepedence will override whatever is specified here if a `.pydependence.cfg`
file exists in the same folder. (This behavior is needed if for example a project is still using a
`setup.py` file, or migrating from this.)

Configuration using the `pyproject.toml` should be placed under the `[tool.pydependence]` table,
while configuration for the `.pydependence.cfg` should be placed under the root table.

Here is a minimal example:

```toml
# ... rest of pyproject.toml file ...

[tool.pydependence]  # exclude table definition if inside `.pydependence.cfg`, place all attributes at root instead.
versions = ["tomlkit>=0.12,<1"]
scopes = [{name = "pydependence", pkg_paths = "./pydependence"}]
resolvers = [
    {strict_requirements_map=false, scope='pydependence', output_mode='dependencies'},
    {strict_requirements_map=false, scope='pydependence', output_mode='optional-dependencies', output_name='all', visit_lazy=true},
]

# ... rest of pyproject.toml file ...
```

----------------------

## Usage

`pydependence` can be triggered from both the CLI and using pre-commit, and
currently requires `python>=3.8`, however, it should still be able to run in
a virtual environment over legacy python code.


### Usage - Pre-Commit

Add a pre-commit entry pointing to your pyproject.toml file or configuration file.

```yaml
  - repo: https://github.com/nmichlo/pydependence
    rev: v0.5.0
    hooks:
      - id: pydependence
        args: ["pyproject.toml"]
```

### Usage - CLI

Manually invoke `pydependence `

```bash
# install
pip install pydependence

# manual invocation - help
python -m pydependence --help

# manual invocation
python -m pydependence <path_to_config.toml>
```

----------------------

## Help

pydependence is an AST imports analysis tool that is used to discover the imports of a
package and generate a dependency graph and requirements/pyproject sections.

pydependence is NOT a package manager or a dependency resolver.
This is left to the tool of your choice, e.g. `pip`, `poetry`, `pip-compile`, `uv`, etc.

_Check the [pyproject.toml](./pyproject.toml) for detailed explanations of various config options and a working example of `pydependence` applied to itself._

### Version Mapping

Versions are used to specify the version of a package that should be used when generating output requirements.
- If a version is not specified, an error will be raised.

Versions are also used to construct mappings between package names and import names.
- e.g. `Pillow` is imported as `PIL`, so the version mapping is `{package="pillow", version="*", import="PIL"}`


### Scopes

A scope is a logical collection of packages.
It is a way to group packages together for the purpose of dependency resolution.
- NOTE: there cannot be conflicting module imports within a scope.

Scopes can inherit from other scopes.
Scopes can have filters applied to them, include & exclude.
Scopes must have unique names.

The order of constructing a single scope is important.
   1. `parents`, `search_paths`, `pkg_paths`
      - `parents`: inherit all modules from the specified scopes
      - `search_paths`: search for packages inside the specified paths (like PYTHONPATH)
      - `pkg_paths`: add the packages at the specified paths
   2. `limit`, `include`, `exclude`
      - `limit`: limit the search space to children of the specified packages
      - `include`: include packages that match the specified patterns
      - `exclude`: exclude packages that match the specified patterns

The order of evaluation when constucting multiple scopes is important, and can
be used to create complex dependency resolution strategies.
   - all scopes are constructed in order of definition

#### Sub-Scopes

A subscope is simply an alias for constructing a new scope, where:
- the parent scope is the current scope
- a filter is applied to limit the packages

e.g.
```toml
[[tool.pydependence.scopes]]
name = "my_pkg"
pkg_paths = ["my_pkg"]
subscopes = {mySubPkg="my_pkg.my_sub_pkg"}
```

is the same as:
```toml
[[tool.pydependence.scopes]]
name = "my_pkg"
pkg_paths = ["my_pkg"]

[[tool.pydependence.scopes]]
name = "mySubPkg"
parents = ["my_pkg"]
limit = ["my_pkg.my_sub_pkg"]
```

why?
- This simplifies syntax for the common pattern of when you want to resolve optional dependencies
  across an entire package, but only want to traverse starting from the subscope.

### Output Resolvers

Resolvers are used to specify how to resolve dependencies, and where to output the results.

options:
* `scope`:
  - is used to determine the search space for the resolver.
* `start_scope`:
  - is used to determine the starting point for the resolver, i.e. BFS across all imports occurs from this point.
* `env`
  - used to select a specific set of `versions` that are tagged with the same `env` key when resolving.
* `raw`
  - manually specify requirements and versions to output, overwriting what was resolved if conflicting.
* `output_mode`:
  - is used to determine where to output the results.
  - valid options are: `dependencies`, `optional-dependencies`, or `requirements`
* `output_file`:
  - is used to specify the file to output the results to, by default this is the current `pyproject.toml` file.
    this usually only needs to be specified when outputting to a different file like `requirements.txt`
* `output_name`
  - only applied if using `output_mode="optional-dependencies"`, specifies the extras group name.

Note: We can have multiple resolvers to construct different sets of outputs. For example if you have a library
      with core dependencies and optional dependencies, you can construct a resolver for each. And limit the results
      for the optional dependencies to only output the optional dependencies for that resolver.

### Example

```toml
# general settings / overrides
# * [tool.pydependence] in pyproject.toml
# * [pydependence] in a standalone config file
[tool.pydependence]

# defaults [don't need to specifiy in practice, unless you want different default behavior]:
# - if a relative path, then relative to the *parent* of this file
# - the resolved root is prepended to all relative paths in the rest of this config.
#   e.g. for the `pydependence` repo, with files `pydependence/pyproject.toml` and `pydependence/pydependence`, then
#        * ".." would mean relative files need to be references from the parent of the repo root e.g. "pydependence/pydependence/__main__.py",
#          this is useful when resolving across multiple repos.
#        * "." would mean relative files need to be reference from the repo root e.g. "pydependence/__main__.py",
#          this is more useful when resolving across a single repo (default).
default_root = "."

# defaults [don't need to specifiy in practice]:
# - these settings can be overridden on individual output resolvers.
# * visit_lazy:
#   | If true, then vist all the lazy imports. Usually the lazy imports are removed from
#   | the import graph and we don't traverse these edges. This on the other-hand allows
#   | all these edges to be traversed. This is often useful if you want to create
#   | packages that only require some minimal set of requirements, and everything else
#   | that you define should be optional. Also useful if you want to generate a minimal
#   | dependencies list, and then in optional dependency lists you want to create a full
#   | set of requirements for everything!
# * re_add_lazy: [A.K.A. shallow_include_lazy]
#   | only applicable when `visit_lazy=False`, then in this case we re-add the lazy
#   | imports that are directly referenced in all the traversed files, i.e. it is a
#   | shallow include of lazy imports without continuing to traverse them. This means
#   | that we add the lazy imports but we don't continue traversing. This is often not
#   | useful with complex lazy import graphs that continue to reference more module
#   | within the same scope as this could cause missing imports, rather specify
#   | `visit_lazy=True` in this case.
# * exclude_unvisited:
#   | If true, then exclude imports that were not encountered as we traversed the import
#   | graph. [NOTE]: this is probably useful if you don't want to include all imports
#   | below a specific scope, but only want to resolve what is actually encountered.
#   | Not entirely sure this has much of an effect?
# * exclude_in_search_space:
#   | If true, then exclude all imports that are part of the current scope. This usually
#   | should not have any effect because imports are replaced as we traverse the graph
#   | through the current scope, [NOTE] thus not entirely sure that this has any effect,
#   | should it be a bug if we encounter any of these?
# * exclude_builtins:
#   | If true, then exclude all the python builtin package names from being output in
#   | the requirements files. This usually should be true unless you are trying to debug
#   | as this would generate invalid requirements list as these would not exist on pypi.
# * strict_requirements_map:
#   | Check that generated imports and requirements have entries in the versions list.
#   | If strict mode is enabled, then an error is thrown if a version entry is missing.
#   | If strict mode is disabled, then a warning should be given, and the root import
#   | name is used instead of the requirement name, which may or may not match up
#   | to an actual python package.
default_resolve_rules = {visit_lazy=false, re_add_lazy=false, exclude_unvisited=true, exclude_in_search_space=true, exclude_builtins=true, strict_requirements_map=true}

# defaults [don't need to specifiy in practice, unless you want different default behavior]:
# - these settings can be overridden on individual scopes.
# * unreachable_mode
#   | Specify how to handle modules that are unreachable, e.g. if there is no `__init__.py`
#   | file in all the parents leading up to importing this module. If this is the case
#   | then the module/package does not correctly follow python/PEP convention and is
#   | technically invalid. By default, for `error`, we raise an exception and do not allow
#   | the scope to be created, but this can be relaxed to `skip` or `keep` these files.
default_scope_rules = {unreachable_mode="error"}

# map requirements and resolved imports to specific packages and version requirements.
# - to generate dependency lists for conflicting package versions you can specify
#   requirements more than once as long as you add a unique `env` entry. In the
#   corresponding resolver, you can then reference this `env` entry to switch out the
#   version you are after. If no `env` is set, then by default the env="default".
versions = [
    "pydantic>=2.0.0",
    {requirement="pydependence", scope="pydependence"},
]

# Output resolvers define the resolution and generation of output requirements by
#   1. traversing a scope's directed module and import graph
#   2. collecting all imports and mapping these using the version list above to specific pypi requirements.
# Note that the starting point can be set to some subset of the scope
#   e.g. if you script that you want to generate requirements for uses the `main.py` file,
#        then you can generate requirements for this script specifically by setting it as
#        the starting point, instead of generating requirements for the entire scope. Then
#        only imports that this script uses and traverses to will actually be included in
#        the output.
# Note that by default lazy imports are not traversed or included.
#   * Lazy imports are imports that are contained inside functions, methods or TYPE_CHECKING blocks.
#     This means that some coding convention has to be followed when pydependence is used within
#     projects to generate minimal requirements as it is expected that these imports should not be
#     called at import time, instead possibly only at runtime if specific features of the library or
#     framework are requested.
# Note that by default we use a strict requirements mapping mode
#   * if resolved imports and requirements do not have a corresponding `versions` entry, then an error will
#     be thrown in this case. This is to ensure that devs know exactly what versions are being used within their
#     program.
resolvers = [
    {                   output_mode='dependencies',          scope='pydependence', visit_lazy=false, strict_requirements_map=false},
    {output_name='all', output_mode='optional-dependencies', scope='pydependence', visit_lazy=true,  strict_requirements_map=false},
]

# Scopes represent graphs of modules (nodes) and their interconnecting
# import statements (directed edges) that reference themselves or other modules.
# - scopes are traversed by the resolvers in different ways to generate lists of requirements.
# - scopes can be constructed from various different sources.
#   * `pkg_paths` / `search_paths`
# - scopes can inherit from eachother with `parents`
# - scopes can be filtered down with `limit`
# - scopes cannot have conflicting module names, each module name should have a one to one mapping to a specific file.
scopes = [
    {name = "pydependence", pkg_paths = "./pydependence"},
]
```
