"""Check a Lintel tree against the year-1 consume contract.

This is a face/handshake checker, not freeze / land / serving F. Lintel stays
the control plane. Year-1 live paths are docs + schemas + examples (no src/).
``examples/later/`` is skipped (attn / knobs stay degenerate).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .ast import COMPILER_VER
from .knobs import YEAR1_KERNELS
from .pin import (
    FACE_ADAPTER_ID,
    PIN_SCHEMA,
    cache_key_digest,
    cache_key_errors,
    launch_errors,
    pin_doc_errors,
)

KERNEL_AST_FIELDS = ("name", "buffers", "partitions", "body")
FINDING_KEYS = ("gate", "severity", "node", "msg", "partition", "thread", "element")
FINDING_REQUIRED = ("gate", "severity", "node", "msg")
SESSION_REJECT_KEYS = ("where", "hint", "reason")
WHERE = frozenset({"W", "L", "S", "V"})
SKIP_DIR_NAMES = frozenset({".git", "later", "__pycache__", ".venv"})
REQUIRED_PATHS = (
    "schemas/cache-key.v0.schema.json",
    "schemas/adapter-proposal.v0.schema.json",
    "schemas/session-event.v0.schema.json",
    "schemas/admit-record.v0.schema.json",
    "examples/admit-record.json",
    "examples/session-log.jsonl",
)
PROPOSAL_SCHEMA = "lintel.adapter_proposal.v0"
DEVICE_KINDS = frozenset({"cubin", "npu-bin"})


def consume_check(root: Path) -> list[str]:
    """Return handshake errors for a Lintel checkout. Empty list means ok."""
    root = Path(root)
    if not root.is_dir():
        return [f"{root}: not a directory"]
    errors: list[str] = []
    if (root / "src").exists():
        errors.append("year-1 forbids src/ (docs + schemas + examples only)")
    for rel in REQUIRED_PATHS:
        if not (root / rel).is_file():
            errors.append(f"missing {rel}")
    examples = root / "examples"
    if examples.is_dir():
        for path in sorted(_iter_live_files(examples)):
            errors.extend(_check_file(root, path))
    return errors


def _iter_live_files(examples: Path) -> list[Path]:
    out: list[Path] = []
    for path in examples.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix not in {".json", ".jsonl"}:
            continue
        rel_parts = path.relative_to(examples).parts
        if any(part in SKIP_DIR_NAMES for part in rel_parts):
            continue
        out.append(path)
    return out


def _check_file(root: Path, path: Path) -> list[str]:
    rel = path.relative_to(root).as_posix()
    errors: list[str] = []
    text = path.read_text()
    if path.suffix == ".jsonl":
        for i, line in enumerate(text.splitlines(), 1):
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                errors.append(f"{rel}:{i}: invalid JSON ({exc.msg})")
                continue
            errors.extend(_walk(obj, f"{rel}:{i}", rel))
        return errors
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as exc:
        return [f"{rel}: invalid JSON ({exc.msg})"]
    errors.extend(_walk(obj, rel, rel))
    return errors


def _walk(obj: Any, loc: str, rel: str) -> list[str]:
    if isinstance(obj, list):
        errors: list[str] = []
        for i, item in enumerate(obj):
            errors.extend(_walk(item, f"{loc}[{i}]", rel))
        return errors
    if not isinstance(obj, dict):
        return []
    schema_version = obj.get("schema_version")
    if schema_version == "admit-record.v0":
        return _admit_record_errors(obj, loc, rel)
    if obj.get("schema") == PROPOSAL_SCHEMA:
        return _proposal_errors(obj, loc)
    if schema_version == PIN_SCHEMA:
        return _pin_file_errors(obj, loc)
    if schema_version == "session-event.v0":
        return _session_event_errors(obj, loc)
    return _generic_errors(obj, loc, rel)


def _generic_errors(obj: dict, loc: str, rel: str) -> list[str]:
    errors: list[str] = []
    skip: set[str] = set()
    if "enum_id" in obj:
        errors.extend(_enum_id_errors(obj.get("enum_id"), f"{loc}.enum_id"))
        skip.add("enum_id")
    if "adapter_id" in obj:
        errors.extend(_adapter_id_errors(obj.get("adapter_id"), f"{loc}.adapter_id"))
        skip.add("adapter_id")
    cv = obj.get("compiler_ver")
    if isinstance(cv, str):
        errors.extend(_triton_sink_errors(cv, f"{loc}.compiler_ver"))
        skip.add("compiler_ver")
    if isinstance(obj.get("kernel"), dict):
        errors.extend(_kernel_ast_errors(obj["kernel"], f"{loc}.kernel"))
        skip.add("kernel")
    elif _looks_like_kernel(obj):
        errors.extend(_kernel_ast_errors(obj, loc))
    if isinstance(obj.get("cache_key"), dict) or "cache_key_digest" in obj:
        errors.extend(_cache_key_blob_errors(obj, loc, require_digest=False))
        skip.update({"cache_key", "cache_key_digest"})
    if "launch" in obj:
        errors.extend(_launch_blob_errors(obj.get("launch"), obj.get("cache_key"), f"{loc}.launch"))
        skip.add("launch")
    if isinstance(obj.get("finding"), dict):
        errors.extend(_finding_errors(obj["finding"], f"{loc}.finding"))
        skip.add("finding")
    for key, val in obj.items():
        if key in skip:
            continue
        errors.extend(_walk(val, f"{loc}.{key}", rel))
    return errors


def _looks_like_kernel(obj: dict) -> bool:
    return all(k in obj for k in KERNEL_AST_FIELDS)


def _enum_id_errors(val: Any, loc: str) -> list[str]:
    if not isinstance(val, str) or not val:
        return [f"{loc}: enum_id must be a non-empty string"]
    if val not in YEAR1_KERNELS:
        return [f"{loc}: {val!r} is not a year-1 SLA slot (copy|gemm_tile)"]
    return []


def _adapter_id_errors(val: Any, loc: str) -> list[str]:
    if not isinstance(val, str) or not val:
        return [f"{loc}: adapter_id must be a non-empty string"]
    if val != FACE_ADAPTER_ID:
        return [f"{loc}: year-1 live face is {FACE_ADAPTER_ID!r}, got {val!r}"]
    return []


def _triton_sink_errors(compiler_ver: str, loc: str) -> list[str]:
    if "triton" in compiler_ver.lower():
        return [f"{loc}: year-1 live must not use Triton as the sink ({compiler_ver!r})"]
    return []


def _kernel_ast_errors(obj: Any, loc: str) -> list[str]:
    if not isinstance(obj, dict):
        return [f"{loc}: kernel must be an object (full AST, not a name stub)"]
    errors: list[str] = []
    missing = [k for k in KERNEL_AST_FIELDS if k not in obj]
    if missing:
        errors.append(f"{loc}: kernel stub missing {', '.join(missing)}")
        return errors
    name = obj.get("name")
    if isinstance(name, str) and name and name not in YEAR1_KERNELS:
        errors.append(f"{loc}.name: {name!r} is not a year-1 SLA kernel")
    cv = obj.get("compiler_ver")
    if cv is not None and str(cv) != COMPILER_VER:
        errors.append(f"{loc}.compiler_ver: must be {COMPILER_VER!r}, got {cv!r}")
    return errors


def _finding_errors(obj: Any, loc: str) -> list[str]:
    if not isinstance(obj, dict):
        return [f"{loc}: finding must be an object"]
    errors: list[str] = []
    extra = sorted(set(obj) - set(FINDING_KEYS))
    if extra:
        errors.append(f"{loc}: unexpected keys {', '.join(extra)}")
    if "where" in obj:
        errors.append(f"{loc}: finding must not repeat where")
    missing = [k for k in FINDING_REQUIRED if k not in obj]
    if missing:
        errors.append(f"{loc}: missing {', '.join(missing)}")
    gate = obj.get("gate")
    if gate not in WHERE:
        errors.append(f"{loc}.gate: must be W|L|S|V, got {gate!r}")
    return errors


def _cache_key_blob_errors(obj: dict, loc: str, *, require_digest: bool) -> list[str]:
    errors: list[str] = []
    key = obj.get("cache_key")
    if not isinstance(key, dict):
        if "cache_key" in obj:
            errors.append(f"{loc}.cache_key: must be an object")
        elif require_digest:
            errors.append(f"{loc}: missing cache_key")
        return errors
    for err in cache_key_errors(key):
        errors.append(f"{loc}.cache_key: {err}")
    if "adapter_id" in key:
        errors.extend(_adapter_id_errors(key.get("adapter_id"), f"{loc}.cache_key.adapter_id"))
    cv = key.get("compiler_ver")
    if isinstance(cv, str):
        errors.extend(_triton_sink_errors(cv, f"{loc}.cache_key.compiler_ver"))
    stored = obj.get("cache_key_digest")
    if isinstance(stored, str) and stored:
        want = cache_key_digest(key)
        if stored != want:
            errors.append(f"{loc}: cache_key_digest mismatch: stored {stored}, canonical {want}")
    elif require_digest:
        errors.append(f"{loc}: missing cache_key_digest")
    return errors


def _launch_family_errors(launch: dict, cache_key: Any, loc: str) -> list[str]:
    if not isinstance(cache_key, dict):
        return []
    errors: list[str] = []
    hw = cache_key.get("hw_id")
    block = launch.get("block")
    num_warps = launch.get("num_warps")
    if isinstance(hw, str) and hw.startswith("nvidia."):
        if isinstance(num_warps, int) and not isinstance(num_warps, bool) and isinstance(block, int):
            want = max(num_warps * 32, 32)
            if block != want:
                errors.append(f"{loc}: CUDA block must be num_warps×32 ({want}), got {block}")
    if isinstance(hw, str) and hw.startswith("ascend") and isinstance(block, int) and block != 1:
        errors.append(f"{loc}: Ascend year-1 block must be 1, got {block}")
    return errors


def _launch_blob_errors(launch: Any, cache_key: Any, loc: str) -> list[str]:
    errors = [f"{loc}: {err}" for err in launch_errors(launch)]
    if isinstance(launch, dict):
        errors.extend(_launch_family_errors(launch, cache_key, loc))
    return errors


def _pin_file_errors(doc: dict, loc: str) -> list[str]:
    errors = [f"{loc}: {err}" for err in pin_doc_errors(doc)]
    key = doc.get("cache_key")
    if isinstance(doc.get("launch"), dict):
        errors.extend(_launch_family_errors(doc["launch"], key, f"{loc}.launch"))
    cv = key.get("compiler_ver") if isinstance(key, dict) else None
    if isinstance(cv, str):
        errors.extend(_triton_sink_errors(cv, f"{loc}.cache_key.compiler_ver"))
    if isinstance(key, dict) and "adapter_id" in key:
        errors.extend(_adapter_id_errors(key.get("adapter_id"), f"{loc}.cache_key.adapter_id"))
    stored = doc.get("cache_key_digest")
    if not isinstance(stored, str) or not stored:
        errors.append(f"{loc}: missing cache_key_digest")
    return errors


def _proposal_errors(doc: dict, loc: str) -> list[str]:
    errors: list[str] = []
    errors.extend(_adapter_id_errors(doc.get("adapter_id"), f"{loc}.adapter_id"))
    errors.extend(_enum_id_errors(doc.get("enum_id"), f"{loc}.enum_id"))
    errors.extend(_kernel_ast_errors(doc.get("kernel"), f"{loc}.kernel"))
    cv = doc.get("compiler_ver")
    if isinstance(cv, str):
        errors.extend(_triton_sink_errors(cv, f"{loc}.compiler_ver"))
    rej = doc.get("reject")
    if isinstance(rej, dict):
        where = rej.get("where")
        if where not in WHERE:
            errors.append(f"{loc}.reject.where: must be W|L|S|V, got {where!r}")
        finding = rej.get("finding")
        if finding is None:
            errors.append(f"{loc}.reject: adapter-proposal must nest finding")
        else:
            errors.extend(_finding_errors(finding, f"{loc}.reject.finding"))
    return errors


def _session_event_errors(ev: dict, loc: str) -> list[str]:
    payload = ev.get("payload")
    if not isinstance(payload, dict):
        return [f"{loc}.payload: must be an object"]
    kind = ev.get("kind")
    errors: list[str] = []
    if kind == "propose":
        errors.extend(_enum_id_errors(payload.get("enum_id"), f"{loc}.payload.enum_id"))
        errors.extend(_adapter_id_errors(payload.get("adapter_id"), f"{loc}.payload.adapter_id"))
        errors.extend(_kernel_ast_errors(payload.get("kernel"), f"{loc}.payload.kernel"))
        if "finding" in payload:
            errors.extend(_finding_errors(payload.get("finding"), f"{loc}.payload.finding"))
        rej = payload.get("reject")
        if isinstance(rej, dict) and "finding" in rej:
            errors.append(f"{loc}.payload.reject: session reject must not nest finding")
    elif kind == "gate":
        errors.extend(_adapter_gate_errors(payload, loc))
    elif kind == "freeze":
        errors.extend(_cache_key_blob_errors(payload, f"{loc}.payload", require_digest=True))
        artifact_kind = payload.get("kind")
        if artifact_kind not in DEVICE_KINDS:
            errors.append(
                f"{loc}.payload.kind: freeze artifact must be cubin or npu-bin, got {artifact_kind!r}"
            )
        if payload.get("launch") is None:
            errors.append(f"{loc}.payload: freeze missing launch")
        else:
            errors.extend(
                _launch_blob_errors(payload.get("launch"), payload.get("cache_key"), f"{loc}.payload.launch")
            )
    elif kind in ("admit", "fallback"):
        errors.extend(_cache_key_blob_errors(payload, f"{loc}.payload", require_digest=True))
        if "enum_id" in payload:
            errors.extend(_enum_id_errors(payload.get("enum_id"), f"{loc}.payload.enum_id"))
    elif kind == "session.start":
        if "adapter_id" in payload:
            errors.extend(_adapter_id_errors(payload.get("adapter_id"), f"{loc}.payload.adapter_id"))
        cv = payload.get("compiler_ver")
        if isinstance(cv, str):
            errors.extend(_triton_sink_errors(cv, f"{loc}.payload.compiler_ver"))
    return errors


def _adapter_gate_errors(payload: dict, loc: str) -> list[str]:
    if payload.get("seam") != "adapter" or payload.get("passed") is not False:
        return []
    errors: list[str] = []
    if "finding" not in payload:
        errors.append(f"{loc}.payload: adapter-fail finding must be a sibling of reject")
    else:
        errors.extend(_finding_errors(payload.get("finding"), f"{loc}.payload.finding"))
    rej = payload.get("reject")
    if not isinstance(rej, dict):
        errors.append(f"{loc}.payload: adapter-fail missing reject")
        return errors
    if "finding" in rej:
        errors.append(f"{loc}.payload.reject: session reject must not nest finding")
    extra = sorted(set(rej) - set(SESSION_REJECT_KEYS))
    if extra:
        errors.append(f"{loc}.payload.reject: extra keys {', '.join(extra)}")
    where = rej.get("where")
    if where not in WHERE:
        errors.append(f"{loc}.payload.reject.where: adapter reject must be W|L|S|V, got {where!r}")
    return errors


def _admit_record_errors(doc: dict, loc: str, rel: str) -> list[str]:
    errors: list[str] = []
    pins = doc.get("pins") if isinstance(doc.get("pins"), dict) else {}
    if "adapter_id" in pins:
        errors.extend(_adapter_id_errors(pins.get("adapter_id"), f"{loc}.pins.adapter_id"))
    pin_cv = pins.get("compiler_ver")
    if isinstance(pin_cv, str):
        errors.extend(_triton_sink_errors(pin_cv, f"{loc}.pins.compiler_ver"))
    errors.extend(_cache_key_blob_errors(doc, loc, require_digest=True))
    actions = doc.get("actions")
    if isinstance(actions, list):
        for i, action in enumerate(actions):
            if not isinstance(action, dict):
                errors.append(f"{loc}.actions[{i}]: must be an object")
                continue
            errors.extend(_enum_id_errors(action.get("enum_id"), f"{loc}.actions[{i}].enum_id"))
            if "kernel" in action:
                errors.extend(_kernel_ast_errors(action.get("kernel"), f"{loc}.actions[{i}].kernel"))
    artifact = doc.get("artifact") if isinstance(doc.get("artifact"), dict) else {}
    kind = artifact.get("kind")
    decision = doc.get("decision")
    if kind in DEVICE_KINDS:
        if artifact.get("launch") is None:
            errors.append(f"{loc}.artifact: cubin/npu-bin freeze payload missing launch")
        else:
            errors.extend(
                _launch_blob_errors(artifact.get("launch"), doc.get("cache_key"), f"{loc}.artifact.launch")
            )
    if kind == "triton_kernel":
        errors.append(f"{loc}.artifact.kind: year-1 freeze is cubin/npu-bin, not triton_kernel")
    if decision == "freeze" and kind not in DEVICE_KINDS:
        errors.append(f"{loc}.artifact.kind: freeze must be cubin or npu-bin, got {kind!r}")
    key = doc.get("cache_key") if isinstance(doc.get("cache_key"), dict) else {}
    sink = _sink_suffix(key.get("compiler_ver"))
    if rel == "examples/admit-record.json":
        want = f"choreoir=={COMPILER_VER};nvcc.cubin"
        if key.get("compiler_ver") != want:
            errors.append(
                f"{loc}.cache_key.compiler_ver: NVIDIA land must be {want!r}, got {key.get('compiler_ver')!r}"
            )
        if kind != "cubin":
            errors.append(f"{loc}.artifact.kind: NVIDIA land must be cubin, got {kind!r}")
        if sink != "nvcc.cubin":
            errors.append(f"{loc}: NVIDIA land sink must be nvcc.cubin")
    if rel == "examples/admit-record.npu.json":
        want = f"choreoir=={COMPILER_VER};ccec.aicore"
        if key.get("compiler_ver") != want:
            errors.append(
                f"{loc}.cache_key.compiler_ver: Ascend sibling must be {want!r}, got {key.get('compiler_ver')!r}"
            )
        if kind != "npu-bin":
            errors.append(f"{loc}.artifact.kind: Ascend sibling must be npu-bin, got {kind!r}")
    return errors


def _sink_suffix(compiler_ver: Any) -> str:
    if not isinstance(compiler_ver, str) or ";" not in compiler_ver:
        return ""
    return compiler_ver.split(";", 1)[1]
