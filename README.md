
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
    <!-- <a href="https://pypi.org/project/pydependence" target="_blank"> -->
    <!--     <img alt="python versions" src="https://img.shields.io/pypi/pyversions/pydependence?style=flat-square"/> -->
    <!-- </a> -->
    <a href="https://pypi.org/project/pydependence" target="_blank">
        <img alt="pypi version" src="https://img.shields.io/pypi/v/pydependence?style=flat-square&color=blue"/>
    </a>
    <!-- <a href="https://github.com/nmichlo/pydependence/actions?query=workflow%3Atest"> -->
    <!--     <img alt="tests status" src="https://img.shields.io/github/workflow/status/nmichlo/pydependence/test?label=tests&style=flat-square"/> -->
    <!-- </a> -->
    <!-- <a href="https://codecov.io/gh/nmichlo/pydependence/"> -->
    <!--     <img alt="code coverage" src="https://img.shields.io/codecov/c/gh/nmichlo/pydependence?token=86IZK3J038&style=flat-square"/> -->
    <!-- </a> -->
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
- [Usage](#usage)

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

### Usage - CLI

Manually invoke `pydependence `

```bash
# install
pip install pydependence

# manual invocation
python -m pydependence --help
```

----------------------

## Manual

### PYDEPENDENCE

pydependence is an AST imports analysis tool that is used to discover the imports of a
package and generate a dependency graph and requirements/pyproject sections.

pydependence is NOT a package manager or a dependency resolver.
This is left to the tool of your choice, e.g. `pip`, `poetry`, `pip-compile`, `uv`, etc.

### VERSION MAPPINGS

Versions are used to specify the version of a package that should be used when generating output requirements.
- If a version is not specified, an error will be raised.

Versions are also used to construct mappings between package names and import names.
- e.g. `Pillow` is imported as `PIL`, so the version mapping is `{package="pillow", version="*", import="PIL"}`

Resolving optional dependencies?

### SCOPES

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

#### SUBSCOPES

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

### RESOLVERS

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
