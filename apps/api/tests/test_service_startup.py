import subprocess
import sys

import pytest


@pytest.mark.parametrize(
    "module", ["app.main", "app.providers.inventory", "app.providers.fulfillment"]
)
def test_each_service_imports_in_a_fresh_process(module):
    # A shared pytest process can hide cyclic model registration imports.
    result = subprocess.run(
        [sys.executable, "-c", f"import {module}"],
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
