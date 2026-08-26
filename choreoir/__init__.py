"""Choreo IR: Lintel's L4 compiler object — construct, check, simulate, lower to NVIDIA GPU and Ascend NPU."""

from .ast import (
    COMPILER_VER,
    Barrier,
    Buffer,
    Copy,
    Kernel,
    Layout,
    Mma,
    Param,
    Partition,
    Pipeline,
    Reduce,
    Yield,
)
from .check import Finding, check
from .interp import check_value, simulate, simulate_copy
from .jsonio import kernel_from_dict, kernel_to_dict, load_kernel_doc
from .knobs import YEAR1_KERNELS, ScheduleFacts, facts_from_kernel
from .lower import Lowered, adapter_id, find_ccec, find_nvcc, lower, materialize
from .pin import FACE_ADAPTER_ID, cache_key_errors, sink_id, unspecified_graph_hash
from .propose import adapter_proposal
from .print_ascend import print_ascend
from .print_ascendc import print_ascendc
from .print_cuda import print_cuda
from .print_triton import print_triton
from .toolchain import ensure_ccec, ensure_nvcc, find_cann

try:
    from importlib.metadata import version as _pkg_version

    __version__ = _pkg_version("choreoir")
except Exception:  # pragma: no cover
    __version__ = COMPILER_VER

__all__ = [
    "COMPILER_VER",
    "Barrier",
    "Buffer",
    "Copy",
    "Finding",
    "Kernel",
    "Layout",
    "Lowered",
    "Mma",
    "Param",
    "Partition",
    "Pipeline",
    "Reduce",
    "ScheduleFacts",
    "YEAR1_KERNELS",
    "Yield",
    "__version__",
    "check",
    "check_value",
    "facts_from_kernel",
    "kernel_from_dict",
    "kernel_to_dict",
    "load_kernel_doc",
    "lower",
    "materialize",
    "adapter_proposal",
    "adapter_id",
    "find_nvcc",
    "find_ccec",
    "find_cann",
    "ensure_nvcc",
    "ensure_ccec",
    "print_ascend",
    "print_ascendc",
    "print_cuda",
    "print_triton",
    "simulate",
    "simulate_copy",
    "sink_id",
    "FACE_ADAPTER_ID",
    "cache_key_errors",
    "unspecified_graph_hash",
]
