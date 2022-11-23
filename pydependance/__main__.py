from pydependance import ModuleNamespace, is_builtin

# ========================================================================= #
# Ansi Colors                                                               #
# ========================================================================= #


RST = "\033[0m"

# dark colors
GRY = "\033[90m"
lRED = "\033[91m"
lGRN = "\033[92m"
lYLW = "\033[93m"
lBLU = "\033[94m"
lMGT = "\033[95m"
lCYN = "\033[96m"
WHT = "\033[97m"

# light colors
BLK = "\033[30m"
RED = "\033[31m"
GRN = "\033[32m"
YLW = "\033[33m"
BLU = "\033[34m"
MGT = "\033[35m"
CYN = "\033[36m"
lGRY = "\033[37m"


# ========================================================================= #
# Helper print                                                              #
# ========================================================================= #


def _print_module(against: ModuleNamespace, path: str, depth: int):
    if path in against:
        clr = MGT
    else:
        clr = RED
    print(f'{"  " * depth}{GRY}* {clr}{path}{RST}')


def _print_import(against: ModuleNamespace, path: str, depth: int):
    if is_builtin(path):
        clr = lGRY
    elif path in against:
        clr = lYLW
    else:
        clr = lRED
    print(f'{"  " * depth}{GRY}- {clr}{path}{RST}')


# ========================================================================= #
# Entrypoint                                                                #
# ========================================================================= #


def _create_parser():
    import argparse

    # root parser
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--package",
        "-p",
        dest="packages",
        action="append",
        type=str,
        help="Root python paths used to search for python packages.",
    )
    parser.add_argument(
        "--path",
        "-P",
        dest="paths",
        action="append",
        type=str,
        help="Roots of python packages themselves.",
    )
    parser.add_argument(
        "--restrict",
        "-r",
        action="append",
        type=str,
        help="Specific module paths to restrict the namespace to.",
    )
    parser.add_argument(
        "--restrict-mode",
        "-R",
        default="children",
        type=str,
        help="How to restrict the namespace, supports: [exact, children (default), root_children]",
    )
    parser.add_argument(
        "--print-namespace",
        action="store_true",
        help="Print items in the loaded namespace",
    )

    # add subcommands
    subparsers = parser.add_subparsers(
        dest="subparser", title="subcommands", description="valid subcommands"
    )

    # COMMAND: resolve
    command_resolve = subparsers.add_parser("resolve")
    command_resolve.add_argument(
        "--full",
        "-f",
        action="store_true",
        help="show the full import paths, not just the import roots in the output",
    )
    command_resolve.add_argument(
        "--builtin",
        "-b",
        action="store_true",
        help="show builtin dependencies, otherwise these are hidden",
    )
    command_resolve.add_argument(
        "--modules",
        "-m",
        action="store_true",
        help="show dependencies under each module",
    )

    # COMMAND: imports
    command_imports = subparsers.add_parser("imports")
    command_imports.add_argument(
        "--full",
        "-f",
        action="store_true",
        help="show the full import paths, not just the import roots in the output",
    )
    command_imports.add_argument(
        "--builtin",
        "-b",
        action="store_true",
        help="show builtin dependencies, otherwise these are hidden",
    )
    command_imports.add_argument(
        "--modules",
        "-m",
        action="store_true",
        help="show dependencies under each module",
    )

    return parser


def pydependance_cli():
    parser = _create_parser()
    args = parser.parse_args()

    # check arguments
    if not args.paths and not args.packages:
        print("please specify at least on of --paths or --packages")
        exit(1)

    # load namespace
    against = ModuleNamespace()
    if args.paths:
        against.add_modules_from_python_paths(args.paths)
    if args.packages:
        against.add_modules_from_packages(args.packages)

    # restrict the namespace for resolving
    namespace = against
    if args.restrict:
        namespace = namespace.restrict(imports=args.restrict, mode=args.restrict_mode)

    # print the original namespace
    if args.print_namespace:
        print("NAMESPACE (FULL):")
        for m in sorted(set(m.import_root for m in against)):
            print(f"- {m}")
        print()
        if args.restrict:
            print("NAMESPACE (RESTRICTED):")
            for m in sorted(set(m.import_root for m in namespace)):
                print(f"- {m}")
            print()

    # run the various commands on the namespace
    # TODO: clean this up
    # TODO: make arguments common between commands
    # TODO: better colourisation by searching pypi for packages
    # TODO: allow renaming packages eg --rename=cv2:opencv-python,sklearn:scikit-learn
    # TODO: support dependency versions
    # TODO: support various output modes
    #       - json
    #       - pretty
    # TODO: check imports against a specific python environment
    if args.subparser == "resolve":
        module_imports = against.resolve(
            namespace=namespace, roots=not args.full, builtin=args.builtin
        )
        if args.modules:
            for module, imports in module_imports.items():
                _print_module(against, path=module, depth=0)
                for target_path in sorted(imports):
                    _print_import(against, path=target_path, depth=1)
        else:
            for target_path in sorted(
                set(imp for imports in module_imports.values() for imp in imports)
            ):
                _print_import(against, path=target_path, depth=0)
    elif args.subparser == "imports":
        if args.modules:
            for module in namespace.modules():
                _print_module(against, path=module.import_path, depth=0)
                for target_path in sorted(
                    module.imports_unique(roots=not args.full, builtin=args.builtin)
                ):
                    _print_import(against, path=target_path, depth=1)
        else:
            for target_path in sorted(
                namespace.imports_unique(roots=not args.full, builtin=args.builtin)
            ):
                _print_import(against, path=target_path, depth=0)


# ========================================================================= #
# Entrypoint                                                                #
# ========================================================================= #


if __name__ == "__main__":
    pydependance_cli()
