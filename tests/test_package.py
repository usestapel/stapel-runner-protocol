"""Package-level contracts: lazy import stays light; __all__ resolves."""

from __future__ import annotations

import subprocess
import sys

import stapel_runner_protocol


def test_all_names_resolve():
    for name in stapel_runner_protocol.__all__:
        assert getattr(stapel_runner_protocol, name) is not None


def test_unknown_attribute_raises():
    import pytest

    with pytest.raises(AttributeError):
        stapel_runner_protocol.does_not_exist


def test_bare_import_does_not_pull_heavy_deps():
    # PEP 562 laziness: importing the package must not import jsonschema,
    # websockets, or claude_agent_sdk until a symbol needs them.
    code = (
        "import sys, stapel_runner_protocol; "
        "heavy = [m for m in ('jsonschema', 'websockets', 'claude_agent_sdk') "
        "if m in sys.modules]; "
        "assert not heavy, heavy"
    )
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_bare_import_is_django_free():
    code = "import stapel_runner_protocol, sys; assert 'django' not in sys.modules"
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_version_exposed():
    assert stapel_runner_protocol.__version__ == "0.1.0"
