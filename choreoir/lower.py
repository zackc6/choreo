"""Admit-gated lower to NVIDIA GPU or Ascend NPU. Classical. Not an LLM."""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .ast import Kernel
from .check import Finding, check
from .knobs import YEAR1_KERNELS, ScheduleFacts, facts_from_kernel, ident, target_family
from .print_ascend import print_ascend
from .print_ascendc import print_ascendc
from .print_cuda import print_cuda
from .print_triton import print_triton
from .toolchain import ccec_env, find_ccec, find_nvcc, nvcc_include_dir


def adapter_id(family: str, artifact_kind: str, toolchain: str = "") -> str:
    """Sink id Lintel freezes in %k. Not a second live face."""
    if artifact_kind == "cubin":
        return "nvcc.cubin"
    if artifact_kind == "npu-bin":
        if "tilelang" in toolchain and "ccec" not in toolchain:
            return "tilelang.cann"
        return "ccec.aicore"
    if family == "ascend":
        return "ascendc.cce"
    return "cuda.cxx"


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
    triton_text: str = ""
    compiler_ver: str = ""
    artifact_sha256: str = ""
    toolchain: str = ""
    kernel_name: str = ""
    tilelang_text: str = ""

    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "error"]

    def as_k(self) -> dict:
        """Payload Lintel freezes as %k. This tree does not freeze, land, or serve F."""
        target = self.facts.target if self.facts else ""
        return {
            "kernel": self.kernel_name,
            "target": target,
            "family": self.family,
            "compiler_ver": self.compiler_ver,
            "source_sha256": self.source_sha256,
            "artifact_sha256": self.artifact_sha256 or None,
            "artifact_kind": self.artifact_kind,
            "adapter_id": adapter_id(self.family, self.artifact_kind, self.toolchain),
            "isa": self.facts.isa if self.facts else None,
            "arch": self.facts.arch if self.facts else None,
            "graph_hash": None,
        }

    def as_manifest(self) -> dict:
        return {
            "kernel": self.kernel_name,
            "family": self.family,
            "artifact_kind": self.artifact_kind,
            "artifact_path": self.artifact_path,
            "source_sha256": self.source_sha256,
            "artifact_sha256": self.artifact_sha256,
            "compiler_ver": self.compiler_ver,
            "toolchain": self.toolchain,
            "adapter_id": adapter_id(self.family, self.artifact_kind, self.toolchain),
            "k": self.as_k(),
            "facts": self.facts.as_dict() if self.facts else None,
            "findings": [f.as_dict() for f in self.findings],
        }


def lower(kernel: Kernel, *, sla: bool = True) -> Lowered:
    """Lower a checked kernel to NVIDIA or Ascend *source* (year-1 stand-in).

    L5 cubin / NPU-bin ISA is later design. CUDA family fills `cuda_text`;
    Ascend fills CCE as `text` and TileLang as `tilelang_text`.
    Device binaries need `materialize(..., emit='cubin'|'npu-bin')` and a toolchain.
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
        return Lowered(
            "",
            None,
            tuple(findings),
            family or "",
            compiler_ver=kernel.compiler_ver,
            kernel_name=kernel.name,
        )
    facts = facts_from_kernel(kernel)
    cuda_text = ""
    triton_text = ""
    tilelang_text = ""
    if family == "ascend":
        text = print_ascendc(kernel, facts)
        tilelang_text = print_ascend(kernel, facts)
    else:
        cuda_text = print_cuda(kernel, facts)
        triton_text = print_triton(kernel, facts)
        text = cuda_text  # cubin-bound source of record; Triton is M2 sidecar
    digest = hashlib.sha256(text.encode()).hexdigest()
    return Lowered(
        text,
        facts,
        tuple(findings),
        family or "",
        "source",
        None,
        digest,
        cuda_text,
        triton_text,
        kernel.compiler_ver,
        kernel_name=kernel.name,
        tilelang_text=tilelang_text,
    )


def materialize(
    kernel: Kernel,
    out_dir: Path,
    *,
    emit: str = "source",
    sla: bool = True,
) -> Lowered:
    """Write sink source and, if emit is cubin/npu-bin, try the device toolchain.

    Missing nvcc / ccec is a *warning* finding, not a silent success.
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
    artifact_sha256 = ""
    toolchain = ""

    src_path = out_dir / f"{name}.{'cce' if result.family == 'ascend' else 'cu'}"
    src_path.write_text(result.text)
    if result.triton_text:
        (out_dir / f"{name}.triton.py").write_text(result.triton_text)
    if result.tilelang_text:
        (out_dir / f"{name}.npu.py").write_text(result.tilelang_text)
    if result.cuda_text and result.family == "cuda" and src_path.suffix != ".cu":
        (out_dir / f"{name}.cu").write_text(result.cuda_text)

    if emit == "cubin":
        if result.family != "cuda":
            findings.append(
                Finding("W", "error", "kernel", f"emit=cubin requires cuda* target, got {kernel.target!r}")
            )
            return _with_findings(result, findings)
        cubin = out_dir / f"{name}.cubin"
        cu = out_dir / f"{name}.cu"
        extra, ok, nvcc_path = _try_nvcc(
            cu, cubin, result.facts.arch if result.facts else "sm_80"
        )
        findings.extend(extra)
        if ok:
            artifact_kind, artifact_path = "cubin", str(cubin)
            artifact_sha256 = _sha256_file(cubin)
            toolchain = nvcc_path or "nvcc"
        else:
            artifact_path = str(out_dir / f"{name}.cu")
            toolchain = nvcc_path or "nvcc-missing"
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
        dest = out_dir / f"{name}.npu.bin"
        extra, ok, ccec_path = _try_ccec(src_path, dest)
        findings.extend(extra)
        if ok:
            artifact_kind, artifact_path = "npu-bin", str(dest)
            artifact_sha256 = _sha256_file(dest)
            toolchain = ccec_path or "ccec"
        else:
            artifact_path = str(src_path)
            toolchain = ccec_path or "ccec-missing"
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
        result.triton_text,
        result.compiler_ver,
        artifact_sha256,
        toolchain,
        result.kernel_name,
        result.tilelang_text,
    )
    (out_dir / "manifest.json").write_text(json.dumps(out.as_manifest(), indent=2) + "\n")
    (out_dir / "pin.json").write_text(json.dumps(out.as_k(), indent=2) + "\n")
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
        result.triton_text,
        result.compiler_ver,
        result.artifact_sha256,
        result.toolchain,
        result.kernel_name,
        result.tilelang_text,
    )


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _try_nvcc(cu: Path, cubin: Path, arch: str) -> tuple[list[Finding], bool, str]:
    nvcc = find_nvcc()
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
            "",
        )
    cmd = [nvcc]
    inc = nvcc_include_dir(nvcc)
    if inc is not None:
        cmd += ["-I", str(inc)]
    cmd += [f"-arch={arch}", "-cubin", "-o", str(cubin), str(cu)]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
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
            nvcc,
        )
    return [], True, nvcc


def _try_ccec(src: Path, dest: Path) -> tuple[list[Finding], bool, str]:
    ccec = find_ccec()
    if ccec is None:
        return (
            [
                Finding(
                    "W",
                    "warning",
                    "kernel",
                    f"ccec missing; wrote {src.name} (NPU-bin sink, no binary)",
                )
            ],
            False,
            "",
        )
    cmd = [ccec, "--cce-aicore-only", "-c", "-o", str(dest), str(src)]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False, env=ccec_env(ccec))
    if proc.returncode != 0 or not dest.is_file():
        err = (proc.stderr or proc.stdout or "").strip()[:400]
        return (
            [
                Finding(
                    "W",
                    "warning",
                    "kernel",
                    f"ccec failed ({proc.returncode}): {err}",
                )
            ],
            False,
            ccec,
        )
    magic = dest.read_bytes()[:4]
    if magic != b"\x7fELF":
        dest.unlink(missing_ok=True)
        return (
            [
                Finding(
                    "W",
                    "warning",
                    "kernel",
                    "ccec wrote a non-ELF object; refusing to pin a fake NPU bin",
                )
            ],
            False,
            ccec,
        )
    return [], True, ccec


# find_nvcc re-exported for tests / CLI
__all__ = ["Lowered", "adapter_id", "find_ccec", "find_nvcc", "lower", "materialize"]
