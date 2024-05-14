import dataclasses
from typing import List, Optional, Tuple

# ========================================================================= #
# REQUIREMENTS MAPPER                                                       #
# ========================================================================= #


@dataclasses.dataclass
class OutMappedRequirementSource:
    source_module: str

    @property
    def source_module_root(self):
        return self.source_module.split(".")[0]


@dataclasses.dataclass
class OutMappedRequirement:
    requirement: str
    sources: List[OutMappedRequirementSource]
    is_lazy: bool

    def get_source_names(
        self,
        enabled: bool = True,
        roots: bool = False,
    ) -> "List[str]":
        if enabled:
            return sorted(
                {
                    src.source_module_root if roots else src.source_module
                    for src in self.sources
                }
            )
        else:
            return []

    def get_sources_string(
        self,
        enabled: bool = True,
        roots: bool = False,
    ) -> str:
        return ", ".join(self.get_source_names(enabled=enabled, roots=roots))


@dataclasses.dataclass
class OutMappedRequirements:
    requirements: List[OutMappedRequirement]
    resolver_name: Optional[str] = None

    _AUTOGEN_NOTICE = "[AUTOGEN] by pydependence **DO NOT EDIT** [AUTOGEN]"
    _AUTOGEN_NOTICE_NAMED = "[AUTOGEN] by pydependence resolver {resolver_name} **DO NOT EDIT** [AUTOGEN]"

    @property
    def autogen_notice(self) -> str:
        if self.resolver_name is None:
            return self._AUTOGEN_NOTICE
        else:
            return self._AUTOGEN_NOTICE_NAMED.format(resolver_name=repr(self.resolver_name))

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
        indent_size: int = 4,
    ) -> str:
        lines = []
        if notice:
            lines.append(self.autogen_notice)
        for req in self.requirements:
            # add requirement
            lines.append(f"{req.requirement}")
            # add compact sources
            if sources:
                if sources_compact:
                    lines[-1] += f" # {req.get_sources_string(roots=sources_roots)}"
                else:
                    for src_name in req.get_source_names(roots=sources_roots):
                        lines.append(f"{' '*indent_size*1}# ← {src_name}")
        if self.requirements or notice:
            lines.append("")
        return "\n".join(lines)

    def as_toml_array(
        self,
        notice: bool = True,
        sources: bool = True,
        sources_compact: bool = False,
        sources_roots: bool = False,
        indent_size: int = 4,
    ):
        import tomlkit
        import tomlkit.items

        # create table
        array = tomlkit.array().multiline(True)
        if notice:
            array.add_line(
                indent=" " * (indent_size * 1),
                comment=self.autogen_notice,
            )
        for req in self.requirements:
            # add requirement & compact sources
            array.add_line(
                req.requirement,
                indent=" " * (indent_size * 1),
                comment=req.get_sources_string(
                    enabled=sources and sources_compact,
                    roots=sources_roots,
                ),
            )
            # add extended sources
            for src_name in req.get_source_names(
                enabled=sources and not sources_compact,
                roots=sources_roots,
            ):
                array.add_line(indent=" " * (indent_size * 2), comment=f"← {src_name}")
        if self.requirements or notice:
            array.add_line(indent="")
        # done!
        return array


# ========================================================================= #
# END                                                                       #
# ========================================================================= #
