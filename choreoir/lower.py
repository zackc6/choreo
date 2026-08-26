"""Admit-gated lower to NVIDIA GPU or Ascend NPU. Classical. Not an LLM."""

from __future__ import annotations

from dataclasses import dataclass

from .ast import Kernel
from .check import Finding, check
from .knobs import YEAR1_KERNELS, ScheduleFacts, facts_from_kernel, target_family
from .print_ascend import print_ascend
from .print_triton import print_triton


@dataclass(frozen=True)
class Lowered:
    text: str
    facts: ScheduleFacts | None
    findings: tuple[Finding, ...]
    family: str

    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "error"]


def lower(kernel: Kernel, *, sla: bool = True) -> Lowered:
    """Lower a checked kernel to the NVIDIA or Ascend sink.

    Always required of this compiler object. Does not sell a compiler company:
    the text is source for Triton (GPU) or TileLang-Ascend (NPU). Cubin / NPU
    bin still need the device toolchain. Lintel conducts compiler evolution;
    this function is what those commits change.
    """
    findings = list(check(kernel))
    family = target_family(kernel.target)
    if not kernel.target.strip():
        findings.append(
            Finding("W", "error", "kernel", "named target required (cuda | cuda-sm* | ascend*)")
        )
    elif family is None:
        findings.append(Finding("W", "error", "kernel", f"unknown target {kernel.target!r}"))
    if sla and kernel.name not in YEAR1_KERNELS:
        names = ", ".join(sorted(YEAR1_KERNELS))
        findings.append(
            Finding(
                "W",
                "error",
                "kernel",
                f"year-1 SLA allowlists only {{{names}}}; got {kernel.name!r}",
            )
        )
    if any(f.severity == "error" for f in findings):
        return Lowered("", None, tuple(findings), family or "")
    facts = facts_from_kernel(kernel)
    if family == "ascend":
        text = print_ascend(kernel, facts)
    else:
        text = print_triton(kernel, facts)
    return Lowered(text, facts, tuple(findings), family or "")
