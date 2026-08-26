"""Admit-gated lower to NVIDIA GPU or Ascend NPU. Classical. Not an LLM."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .ast import Kernel
from .check import Finding, check
from .knobs import YEAR1_KERNELS, ScheduleFacts, facts_from_kernel, ident, target_family
from .print_ascend import print_ascend
from .print_cuda import print_cuda
from .print_triton import print_triton


@dataclass(frozen=True)
class Lowered:
    text: str
    facts: ScheduleFacts | None
    findings: tuple[Finding, ...]
    family: str
    artifact_kind: str = "source"  # source | cubin | npu-bin
    artifact_path: str | None = None
    source_sha256: str = ""
    cuda_text: str = ""

    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "error"]

    def as_manifest(self) -> dict:
        return {
            "family": self.family,
            "artifact_kind": self.artifact_kind,
            "artifact_path": self.artifact_path,
            "source_sha256": self.source_sha256,
            "facts": self.facts.as_dict() if self.facts else None,
            "findings": [f.as_dict() for f in self.findings],
        }


def lower(kernel: Kernel, *, sla: bool = True) -> Lowered:
    """Lower a checked kernel to NVIDIA or Ascend *source*.

    CUDA family also fills `cuda_text` (the cubin-bound C++ sink). Device
    binaries need `materialize(..., emit='cubin'|'npu-bin')`.
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
    cuda_text = ""
    if family == "ascend":
        text = print_ascend(kernel, facts)
    else:
        text = print_triton(kernel, facts)
        cuda_text = print_cuda(kernel, facts)
    digest = hashlib.sha256(text.encode()).hexdigest()
    return Lowered(text, facts, tuple(findings), family or "", "source", None, digest, cuda_text)


def materialize(
    kernel: Kernel,
    out_dir: Path,
    *,
    emit: str = "source",
    sla: bool = True,
) -> Lowered:
    """Write sink source and, if emit is cubin/npu-bin, try the device toolchain.

    Missing nvcc / TileLang is a *warning* finding, not a silent success.
    Lintel freeze/%k can pin source_sha256 even when the bin is absent.
    """
    result = lower(kernel, sla=sla)
    if result.errors():
        return result
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    name = ident(kernel.name)
    findings = list(result.findings)
    artifact_kind = "source"
    artifact_path: str | None = None

    src_path = out_dir / f"{name}.{'npu.py' if result.family == 'ascend' else 'triton.py'}"
    src_path.write_text(result.text)
    if result.cuda_text:
        (out_dir / f"{name}.cu").write_text(result.cuda_text)

    if emit == "cubin":
        if result.family != "cuda":
            findings.append(
                Finding("W", "error", "kernel", f"emit=cubin requires cuda* target, got {kernel.target!r}")
            )
            return _with_findings(result, findings)
        cubin = out_dir / f"{name}.cubin"
        extra, ok = _try_nvcc(out_dir / f"{name}.cu", cubin, result.facts.arch if result.facts else "sm_80")
        findings.extend(extra)
        if ok:
            artifact_kind, artifact_path = "cubin", str(cubin)
        else:
            artifact_path = str(out_dir / f"{name}.cu")
    elif emit == "npu-bin":
        if result.family != "ascend":
            findings.append(
                Finding(
                    "W",
                    "error",
                    "kernel",
                    f"emit=npu-bin requires ascend* target, got {kernel.target!r}",
                )
            )
            return _with_findings(result, findings)
        extra, bin_path = _try_npu_bin(src_path, out_dir / f"{name}.npu.bin")
        findings.extend(extra)
        if bin_path:
            artifact_kind, artifact_path = "npu-bin", bin_path
        else:
            artifact_path = str(src_path)
    else:
        artifact_path = str(src_path)

    out = Lowered(
        result.text,
        result.facts,
        tuple(findings),
        result.family,
        artifact_kind,
        artifact_path,
        result.source_sha256,
        result.cuda_text,
    )
    (out_dir / "manifest.json").write_text(json.dumps(out.as_manifest(), indent=2) + "\n")
    return out


def _with_findings(result: Lowered, findings: list[Finding]) -> Lowered:
    return Lowered(
        result.text,
        result.facts,
        tuple(findings),
        result.family,
        result.artifact_kind,
        result.artifact_path,
        result.source_sha256,
        result.cuda_text,
    )


def _try_nvcc(cu: Path, cubin: Path, arch: str) -> tuple[list[Finding], bool]:
    nvcc = shutil.which("nvcc")
    if nvcc is None:
        return (
            [
                Finding(
                    "W",
                    "warning",
                    "kernel",
                    f"nvcc missing; wrote {cu.name} (cubin sink, no binary)",
                )
            ],
            False,
        )
    proc = subprocess.run(
        [nvcc, f"-arch={arch}", "-cubin", "-o", str(cubin), str(cu)],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return (
            [
                Finding(
                    "W",
                    "warning",
                    "kernel",
                    f"nvcc failed ({proc.returncode}): {proc.stderr.strip()[:400]}",
                )
            ],
            False,
        )
    return [], True


def _try_npu_bin(src: Path, dest: Path) -> tuple[list[Finding], str | None]:
    del dest
    try:
        __import__("tilelang")
    except ImportError:
        return (
            [
                Finding(
                    "W",
                    "warning",
                    "kernel",
                    f"tilelang/CANN missing; wrote {src.name} (NPU-bin sink, no binary)",
                )
            ],
            None,
        )
    return (
        [
            Finding(
                "W",
                "warning",
                "kernel",
                "tilelang imported but NPU compile is not wired in this pin; source only",
            )
        ],
        None,
    )
