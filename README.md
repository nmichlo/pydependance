
<p align="center">
    <h1 align="center">🕵️ pydependence 🐍</h1>
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
- [Install](#install)
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
3. Finally, dependencies are resolved using breadth-first-search and flattened.
   - imports that redirect to modules within the current namespace
     are flattened and replaced with imports not in the namespace.


## Install

`pydependence` currently requires `python==3.10`, however,
it can still be run in a virtual environment over legacy python code

```bash
pip install pydependence
```

## Usage

```bash
python -m pydependence --help
```
