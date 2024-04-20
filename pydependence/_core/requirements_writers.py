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

from pathlib import Path
from typing import List, Union

from pydependence._core.requirements_gen import (
    WriteMode,
    WriteRequirement,
    WriteRequirementSourceModule,
)
from pydependence._core.utils import is_absolute_path, load_toml_document

# ========================================================================= #
# WRITER - TOML                                                             #
# ========================================================================= #


def read_and_dump_toml_imports(
    *,
    file: "Union[str, Path]",
    keys: "List[str]",
    requirements: "List[WriteRequirement]",
):
    import tomlkit.items

    # load file
    file = Path(file)
    assert is_absolute_path(file), f"file must be an absolute path, got: {file}"
    toml = load_toml_document(file)

    # add sections if missing
    section = toml
    for i, k in enumerate(keys):
        if i < len(keys) - 1:
            section = section.setdefault(k, {})
            assert isinstance(section, tomlkit.items.Table)
        else:
            section = section.setdefault(k, [])
    assert isinstance(section, tomlkit.items.Array)

    # line writer
    def add_line(
        *line: str,
        indents: int = 1,
        comment: str = "",
        all_comment: bool = False,
        comment_after: bool = False,
    ):
        line = " ".join(line)
        if all_comment:
            items = [comment, f'"{line}"']
            if comment_after:
                items = items[::-1]
            items = [x for x in items if x]
            comment = " ".join(items) if items else None
            section.add_line(comment=comment, indent=" " * (4 * indents))
        else:
            line = [line] if line else []
            section.add_line(*line, comment=comment or None, indent=" " * (4 * indents))

    def str_modes_active(
        item: "Union[WriteRequirement, WriteRequirementSourceModule]", prefix: str = ""
    ):
        active = []
        if item.all_lazy:
            active.append("L")
        if item.any_source_in_start_scope:
            pass
        elif item.any_source_in_parent_scope:
            active.append("e")
        else:
            active.append("E")
        if item.is_builtin:
            active.append("B")
        string = f"[{''.join(active)}]" if active else ""
        if prefix and string:
            return f"{prefix} {string}" if prefix and string else f"{prefix}{string}"
        else:
            return f"{prefix}{string}"

    # 1. write imports as strings into array with new lines
    section.clear()
    if requirements:
        add_line(comment="[AUTOGEN] by pydependence **DO NOT EDIT** [AUTOGEN]")

    # if import source is in the base, but not the start, then collapse it to the root
    for req in requirements:
        # skip if needed
        if req.write_mode == WriteMode.exclude:
            continue
        # * write the requirement
        add_line(
            req.requirement,
            comment=str_modes_active(req),
            all_comment=req.write_mode == WriteMode.comment,
            comment_after=True,
        )
        # * write the sources
        for src in req.source_modules:
            if src.write_mode == WriteMode.exclude:
                continue
            # - write the source
            add_line(
                src.source_module,
                comment=str_modes_active(src, prefix=f"←"),
                all_comment=True,
                indents=2,
            )

    # add a new line
    if requirements:
        section.add_line(indent="")

    # write
    with open(file, "w") as fp:
        tomlkit.dump(toml, fp)


# ========================================================================= #
# END                                                                       #
# ========================================================================= #
