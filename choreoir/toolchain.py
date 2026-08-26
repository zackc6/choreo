"""Device toolchains for cubin / NPU-bin. Not Lintel. Not a required pin."""

from __future__ import annotations

import os
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request
from pathlib import Path

_NVCC_URL = (
    "https://developer.download.nvidia.com/compute/cuda/redist/"
    "cuda_nvcc/linux-x86_64/cuda_nvcc-linux-x86_64-12.8.93-archive.tar.xz"
)
_CUDART_URL = (
    "https://developer.download.nvidia.com/compute/cuda/redist/"
    "cuda_cudart/linux-x86_64/cuda_cudart-linux-x86_64-12.8.90-archive.tar.xz"
)
_LOCAL_PREFIX = Path.home() / ".local" / "cuda-nvcc"
_LOCAL_CCEC = Path.home() / ".local" / "ascend" / "pkg" / "bisheng_compiler"


def find_nvcc() -> str | None:
    """Locate nvcc without requiring it in the Python pin. Missing is a warning, not a fake cubin."""
    candidates: list[str] = []
    for key in ("CHOREO_NVCC",):
        raw = os.environ.get(key)
        if raw:
            candidates.append(raw)
    which = shutil.which("nvcc")
    if which:
        candidates.append(which)
    for key in ("CUDA_HOME", "CUDA_PATH"):
        home = os.environ.get(key)
        if home:
            candidates.append(str(Path(home) / "bin" / "nvcc"))
    candidates.extend(
        (
            str(_LOCAL_PREFIX / "bin" / "nvcc"),
            str(Path.home() / ".local" / "cuda" / "bin" / "nvcc"),
            "/usr/local/cuda/bin/nvcc",
            "/usr/bin/nvcc",
        )
    )
    local = Path.home() / ".local"
    if local.is_dir():
        for path in sorted(local.glob("cuda*/bin/nvcc")):
            candidates.append(str(path))
    try:
        import nvidia.cuda_nvcc as nvcc_pkg

        for root in getattr(nvcc_pkg, "__path__", []):
            candidates.append(str(Path(root) / "bin" / "nvcc"))
    except ImportError:
        pass
    for path in candidates:
        if path and Path(path).is_file() and os.access(path, os.X_OK):
            return path
    return None


def nvcc_include_dir(nvcc: str) -> Path | None:
    inc = Path(nvcc).resolve().parent.parent / "include"
    if (inc / "cuda_runtime.h").is_file():
        return inc
    return None


def find_cann() -> str | None:
    """Ascend toolkit / bisheng. Missing is a warning, not a fake NPU bin."""
    which = shutil.which("bisheng")
    if which:
        return str(Path(which).resolve().parent.parent)
    ccec = find_ccec()
    if ccec:
        return str(Path(ccec).resolve().parent.parent)
    for key in ("ASCEND_HOME", "ASCEND_TOOLKIT_HOME", "ASCEND_AICPU_PATH", "CCE_HOME"):
        home = os.environ.get(key)
        if home and Path(home).is_dir():
            return home
    for path in (
        Path("/usr/local/Ascend/ascend-toolkit/latest"),
        Path.home() / "Ascend" / "ascend-toolkit" / "latest",
        _LOCAL_CCEC,
    ):
        if path.is_dir():
            return str(path)
    return None


def find_ccec() -> str | None:
    """Locate official Huawei `ccec`. Missing is a warning, not a fake NPU bin."""
    candidates: list[str] = []
    raw = os.environ.get("CHOREO_CCEC")
    if raw == "":
        return None
    if raw:
        candidates.append(raw)
    which = shutil.which("ccec")
    if which:
        candidates.append(which)
    for key in ("CCE_HOME", "ASCEND_HOME", "ASCEND_TOOLKIT_HOME", "ASCEND_HOME_PATH"):
        home = os.environ.get(key)
        if home:
            candidates.append(str(Path(home) / "bin" / "ccec"))
            candidates.append(str(Path(home) / "compiler" / "ccec_compiler" / "bin" / "ccec"))
            candidates.append(str(Path(home) / "tools" / "ccec_compiler" / "bin" / "ccec"))
    candidates.extend(
        (
            str(_LOCAL_CCEC / "bin" / "ccec"),
            str(Path.home() / ".local" / "Ascend" / "ascend-toolkit" / "latest" / "compiler" / "ccec_compiler" / "bin" / "ccec"),
            "/usr/local/Ascend/ascend-toolkit/latest/compiler/ccec_compiler/bin/ccec",
            "/usr/local/Ascend/latest/compiler/ccec_compiler/bin/ccec",
        )
    )
    local = Path.home() / ".local"
    if local.is_dir():
        for path in sorted(local.glob("ascend*/**/bin/ccec")):
            candidates.append(str(path))
        for path in sorted(local.glob("Ascend*/**/bin/ccec")):
            candidates.append(str(path))
    for path in candidates:
        if path and Path(path).is_file() and os.access(path, os.X_OK):
            return path
    return None


def ccec_env(ccec: str) -> dict[str, str]:
    """Env for a ccec subprocess: CCE_HOME + lib on LD_LIBRARY_PATH."""
    env = os.environ.copy()
    home = str(Path(ccec).resolve().parent.parent)
    env["CCE_HOME"] = home
    env["PATH"] = str(Path(ccec).resolve().parent) + os.pathsep + env.get("PATH", "")
    lib = Path(home) / "lib"
    if lib.is_dir():
        env["LD_LIBRARY_PATH"] = str(lib) + os.pathsep + env.get("LD_LIBRARY_PATH", "")
    return env


def ensure_ccec() -> str | None:
    """Discover ccec. Optional extract: CHOREO_BISHENG_RUN=/path/to/*.run.

    Not called from lower(). Does not download; Huawei packages are not a
    public CUDA-redist mirror. Environment install may point at a local .run.
    """
    found = find_ccec()
    if found:
        return found
    run = os.environ.get("CHOREO_BISHENG_RUN")
    if not run or not Path(run).is_file():
        return None
    dest = _LOCAL_CCEC
    if (dest / "bin" / "ccec").is_file():
        return str(dest / "bin" / "ccec")
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        return find_ccec()
    subprocess.run(
        ["bash", run, "--noexec", f"--extract={dest}"],
        capture_output=True,
        text=True,
        check=False,
    )
    return find_ccec()


def ensure_nvcc() -> str | None:
    """If CHOREO_FETCH_NVCC=1 and nvcc is missing, fetch NVIDIA cuda_nvcc + cudart redist.

    Not called from lower(). Environment install may opt in. Not a Python extra.
    """
    found = find_nvcc()
    if found and nvcc_include_dir(found):
        return found
    if os.environ.get("CHOREO_FETCH_NVCC") != "1":
        return found
    prefix = _LOCAL_PREFIX
    prefix.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        for url, label in ((_NVCC_URL, "nvcc"), (_CUDART_URL, "cudart")):
            archive = tmp_path / f"{label}.tar.xz"
            urllib.request.urlretrieve(url, archive)
            with tarfile.open(archive) as tar:
                tar.extractall(tmp_path, filter="data")
        for extracted in tmp_path.iterdir():
            if not extracted.is_dir() or extracted.name.endswith(".tar.xz"):
                continue
            for sub in ("bin", "include", "lib", "nvvm", "lib64"):
                src = extracted / sub
                if src.exists():
                    dest = prefix / sub
                    dest.mkdir(parents=True, exist_ok=True)
                    _copytree(src, dest)
    return find_nvcc()


def _copytree(src: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        target = dest / item.name
        if item.is_dir():
            _copytree(item, target)
        else:
            shutil.copy2(item, target)
