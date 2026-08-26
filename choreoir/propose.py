"""Lintel adapter-proposal.v0: admit signals as CFG edges. Not freeze, land, or F."""

from __future__ import annotations

from .ast import Kernel
from .check import Finding, check
from .jsonio import PROPOSAL_SCHEMA, kernel_to_dict
from .knobs import nv_arch, target_family
from .pin import (
    FACE_ADAPTER_ID,
    graph_hash_of,
    hw_id_of,
    k_compiler_ver,
    sink_id,
)

GATES = ("W", "L", "S", "V")


def adapter_proposal(
    kernel: Kernel,
    findings: list[Finding] | None = None,
    *,
    enum_id: str | None = None,
    artifact_kind: str = "source",
    toolchain: str = "",
) -> dict:
    """Envelope Lintel copies onto adapter_gate. This tree does not walk the CFG."""
    if findings is None:
        findings = check(kernel)
    family = target_family(kernel.target) or ""
    arch = "davinci" if family == "ascend" else (nv_arch(kernel.target) if family == "cuda" else "")
    sink = sink_id(family, artifact_kind, toolchain)
    errors = [f for f in findings if f.severity == "error"]
    first = errors[0] if errors else None
    out: dict = {
        "schema": PROPOSAL_SCHEMA,
        "adapter_id": FACE_ADAPTER_ID,
        "graph_hash": graph_hash_of(kernel),
        "hw_id": hw_id_of(kernel, family, arch),
        "compiler_ver": k_compiler_ver(kernel.compiler_ver, sink),
        "enum_id": enum_id or kernel.attrs.get("enum_id") or kernel.name,
        "kernel": kernel_to_dict(kernel),
        "gates": list(GATES),
    }
    if first is not None:
        out["reject"] = {
            "ok": False,
            "where": first.gate,
            "hint": first.node,
            "reason": first.msg,
            "finding": first.as_lintel_dict(),
        }
    return out
