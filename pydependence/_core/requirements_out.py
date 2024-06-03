import dataclasses
from collections import defaultdict
from typing import List, NamedTuple, Optional, Tuple

# ========================================================================= #
# REQUIREMENTS MAPPER                                                       #
# ========================================================================= #


@dataclasses.dataclass
class OutMappedRequirementSource:
    source_module: str
    is_lazy: bool
    is_manual: bool

    @property
    def source_module_root(self):
        return self.source_module.split(".")[0]


class SrcInfo(NamedTuple):
    name: str
    comment: str

    @property
    def anno_str(self) -> str:
        if self.comment:
            return f"← {self.comment} {self.name}"
        else:
            return f"← {self.name}"


@dataclasses.dataclass
class OutMappedRequirement:
    requirement: str
    sources: List[OutMappedRequirementSource]

    @property
    def all_lazy(self) -> bool:
        return all(src.is_lazy for src in self.sources)

    @property
    def any_manual(self) -> bool:
        return any(src.is_manual for src in self.sources)

    def get_source_info(
        self,
        enabled: bool = True,
        roots: bool = False,
        annotate: bool = True,
    ) -> "List[SrcInfo]":
        if enabled:
            if roots:
                r = defaultdict(lambda: True)
                for src in self.sources:
                    r[src.source_module_root] &= src.is_lazy
                return [
                    SrcInfo(name=k, comment="[L]" if annotate and r[k] else "")
                    for k in sorted(r.keys())
                ]
            else:
                return [
                    SrcInfo(
                        name=src.source_module,
                        comment=f"[L]" if annotate and src.is_lazy else "",
                    )
                    for src in self.sources
                ]
        else:
            return []

    def get_sources_string(
        self,
        enabled: bool = True,
        roots: bool = False,
    ) -> str:
        return ", ".join(
            i.name
            for i in self.get_source_info(enabled=enabled, roots=roots, annotate=False)
        )

    def get_annotations_string(
        self,
        enabled: bool = True,
        comment: bool = False,
    ) -> str:
        items = []
        if enabled:
            if self.all_lazy:
                items.append("L")
            if self.any_manual:
                items.append("M")
        items = "".join(items)
        if items:
            return f" # [{items}]" if comment else f"[{items}]"
        return ""


@dataclasses.dataclass
class OutMappedRequirements:
    requirements: List[OutMappedRequirement]
    resolver_name: Optional[str] = None

    _AUTOGEN_NOTICE = "[AUTOGEN] by pydependence **DO NOT EDIT** [AUTOGEN]"
    _AUTOGEN_NOTICE_NAMED = (
        "[AUTOGEN] by pydependence resolver {resolver_name} **DO NOT EDIT** [AUTOGEN]"
    )

    @property
    def autogen_notice(self) -> str:
        if self.resolver_name is None:
            return self._AUTOGEN_NOTICE
        else:
            return self._AUTOGEN_NOTICE_NAMED.format(
                resolver_name=repr(self.resolver_name)
            )

    def _get_debug_struct(self) -> "List[Tuple[str, List[str]]]":
        return [
            (req.requirement, [src.source_module for src in req.sources])
            for req in self.requirements
        ]

    def as_requirements_txt(
        self,
        notice: bool = True,
        sources: bool = True,
        sources_compact: bool = False,
        sources_roots: bool = False,
        sources_annotations: bool = True,
        indent_size: int = 4,
    ) -> str:
        lines = []
        if notice:
            lines.append(self.autogen_notice)
        for req in self.requirements:
            # add requirement
            lines.append(f"{req.requirement}")
            # add annotations
            lines[
                -1
            ] += f"{req.get_annotations_string(enabled=sources_annotations, comment=True)}"
            # add compact sources
            if sources:
                if sources_compact:
                    lines[-1] += f" # {req.get_sources_string(roots=sources_roots)}"
                else:
                    for src_info in req.get_source_info(roots=sources_roots):
                        lines.append(f"{' '*indent_size*1}# {src_info.anno_str}")
        if self.requirements or notice:
            lines.append("")
        return "\n".join(lines)

    def as_toml_array(
        self,
        notice: bool = True,
        sources: bool = True,
        sources_compact: bool = False,
        sources_roots: bool = False,
        sources_annotations: bool = True,
        indent_size: int = 4,
    ):
        import tomlkit
        import tomlkit.container
        import tomlkit.items

        # create table
        array = tomlkit.array().multiline(True)
        if notice:
            array.add_line(
                indent=" " * (indent_size * 1),
                comment=self.autogen_notice,
            )
        for req in self.requirements:
            comment = ""
            comment += req.get_annotations_string(
                enabled=sources_annotations,
                comment=False,
            )
            comment += req.get_sources_string(
                enabled=sources and sources_compact,
                roots=sources_roots,
            )
            # add requirement & compact sources
            array.add_line(
                req.requirement,
                indent=" " * (indent_size * 1),
                comment=comment,
            )
            # add extended sources
            for src_info in req.get_source_info(
                enabled=sources and not sources_compact,
                roots=sources_roots,
            ):
                # Add line has a bug where it doesn't add the correct indentation before the comment
                # - so we instead add padding after the `#`
                # `array.add_line(indent=f"{' ' * (indent_size * 1)}, comment=f"{src_info.anno_str}")`
                array.add_line(
                    indent="", comment=f"{' ' * (indent_size * 1)}{src_info.anno_str}"
                )
                # NOTE: While this does not properly handle commas between lines ...
                # array.append(tomlkit.items.Comment(tomlkit.container.Trivia(
                #     indent=" " * (indent_size * 1),
                #     comment_ws="",
                #     comment=f"# {src_info.anno_str}\n",
                #     trail="",
                # )))

        if self.requirements or notice:
            array.add_line(indent="")
        # done!
        return array


# ========================================================================= #
# END                                                                       #
# ========================================================================= #
