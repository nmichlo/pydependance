import os
from sys import path

from foo.bar import asdf

from .package import sub_module


def test_func():
    import json
    import sys

    from asdf.fdsa import foo as bar


asdf = lazy_import("buzz")
fdsa = lazy_callable("bazz")
foo = lazy_inheritable("bar")
