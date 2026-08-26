"""CI can require official nvcc so cubin tests cannot silently skip on main."""

from __future__ import annotations

import os

import pytest


def pytest_sessionstart(session: pytest.Session) -> None:
    if os.environ.get("CHOREO_REQUIRE_NVCC") != "1":
        return
    from choreoir.toolchain import find_nvcc, nvcc_include_dir

    nvcc = find_nvcc()
    if nvcc is None or nvcc_include_dir(nvcc) is None:
        pytest.exit("CHOREO_REQUIRE_NVCC=1 but official nvcc is missing", returncode=1)
