"""Lintel cache-key.v0 handshake. This tree emits the key; Lintel freezes it.

%k = hash(graph, hw, compiler, adapter, policy). Not in the key: model_id,
enum_id, Kernel.target. The Kernel AST is the value at the key, not a key field.
Year-1 has no L2 graph: default graph_hash is a well-formed unspecified digest
that Lintel overwrites. Do not hash the Kernel JSON into graph_hash.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from .ast import Kernel
from .knobs import nv_arch, target_family

FACE_ADAPTER_ID = "choreo.v0"
POLICY_ID_DEFAULT = "lintel.specialize.v0"
GRAPH_UNSPECIFIED = "lintel.graph.unspecified"
CACHE_KEY_SCHEMA = "cache-key.v0"
PIN_SCHEMA = "choreo-pin.v1"
GRAPH_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
CACHE_KEY_FIELDS = (
    "schema_version",
    "graph_hash",
    "hw_id",
    "compiler_ver",
    "adapter_id",
    "policy_id",
)


def sink_id(family: str, artifact_kind: str, toolchain: str = "") -> str:
    """Device sink id. Lives in cache_key.compiler_ver and pin.sink_id, not as adapter_id."""
    if artifact_kind == "cubin":
        return "nvcc.cubin"
    if artifact_kind == "npu-bin":
        if "tilelang" in toolchain and "ccec" not in toolchain:
            return "tilelang.cann"
        return "ccec.aicore"
    if family == "ascend":
        return "ascendc.cce"
    return "cuda.cxx"


def adapter_id(family: str, artifact_kind: str, toolchain: str = "") -> str:
    """Deprecated name for sink_id. Lintel adapter_id is always choreo.v0."""
    return sink_id(family, artifact_kind, toolchain)


def digest_sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def unspecified_graph_hash() -> str:
    return digest_sha256(GRAPH_UNSPECIFIED.encode())


def normalize_graph_hash(raw: str | None) -> str | None:
    if raw is None:
        return None
    text = raw.strip()
    if not text:
        return None
    if GRAPH_HASH_RE.fullmatch(text):
        return text
    if HEX64_RE.fullmatch(text):
        return "sha256:" + text
    return None


def graph_hash_of(kernel: Kernel) -> str:
    stamped = normalize_graph_hash(kernel.attrs.get("graph_hash"))
    return stamped or unspecified_graph_hash()


def policy_id_of(kernel: Kernel) -> str:
    raw = kernel.attrs.get("policy_id", "").strip()
    return raw or POLICY_ID_DEFAULT


def hw_id_of(kernel: Kernel, family: str = "", arch: str = "") -> str:
    stamped = kernel.attrs.get("hw_id", "").strip()
    if stamped:
        return stamped
    fam = family or target_family(kernel.target) or ""
    if fam == "ascend":
        return "ascend.davinci"
    use_arch = arch
    if not use_arch and fam == "cuda":
        use_arch = nv_arch(kernel.target)
    if use_arch.startswith("sm_"):
        return f"nvidia.{use_arch}"
    if fam == "cuda":
        return "nvidia.gpu"
    return "unspecified"


def k_compiler_ver(choreoir_ver: str, sink: str) -> str:
    """Lintel cache_key.compiler_ver names both choreoir and the sink."""
    return f"choreoir=={choreoir_ver};{sink}"


def cache_key(
    *,
    graph_hash: str,
    hw_id: str,
    compiler_ver: str,
    policy_id: str,
    adapter_id: str = FACE_ADAPTER_ID,
) -> dict[str, str]:
    return {
        "schema_version": CACHE_KEY_SCHEMA,
        "graph_hash": graph_hash,
        "hw_id": hw_id,
        "compiler_ver": compiler_ver,
        "adapter_id": adapter_id,
        "policy_id": policy_id,
    }


def cache_key_errors(obj: Any) -> list[str]:
    """Structural check against Lintel cache-key.v0 (additionalProperties: false)."""
    if not isinstance(obj, dict):
        return ["cache_key must be an object"]
    errs: list[str] = []
    extra = sorted(set(obj) - set(CACHE_KEY_FIELDS))
    missing = [k for k in CACHE_KEY_FIELDS if k not in obj]
    if extra:
        errs.append("additional properties: " + ", ".join(extra))
    if missing:
        errs.append("missing: " + ", ".join(missing))
    if obj.get("schema_version") != CACHE_KEY_SCHEMA:
        errs.append(f"schema_version must be {CACHE_KEY_SCHEMA!r}")
    gh = obj.get("graph_hash")
    if not isinstance(gh, str) or not GRAPH_HASH_RE.fullmatch(gh):
        errs.append("graph_hash must match sha256:<64 hex>")
    for field in ("hw_id", "compiler_ver", "adapter_id", "policy_id"):
        val = obj.get(field)
        if not isinstance(val, str) or not val:
            errs.append(f"{field} must be a non-empty string")
    return errs


def extract_cache_key(doc: Any) -> dict | None:
    if not isinstance(doc, dict):
        return None
    inner = doc.get("cache_key")
    if isinstance(inner, dict):
        return inner
    if doc.get("schema_version") == CACHE_KEY_SCHEMA:
        return doc
    return None


def apply_pin_stamps(
    kernel: Kernel,
    *,
    graph_hash: str | None = None,
    hw_id: str | None = None,
    policy_id: str | None = None,
) -> list[str]:
    """Stamp Lintel-owned pin fields onto Kernel.attrs. Returns warning messages."""
    warns: list[str] = []
    if graph_hash is not None:
        norm = normalize_graph_hash(graph_hash)
        if norm is None:
            warns.append(f"invalid graph_hash {graph_hash!r}; using unspecified digest")
        else:
            kernel.attrs["graph_hash"] = norm
    if hw_id is not None:
        text = hw_id.strip()
        if text:
            kernel.attrs["hw_id"] = text
        else:
            warns.append("empty hw_id stamp ignored")
    if policy_id is not None:
        text = policy_id.strip()
        if text:
            kernel.attrs["policy_id"] = text
        else:
            warns.append("empty policy_id stamp ignored")
    return warns
