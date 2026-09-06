"""Public consumer, separate processes and an independently installed wheel."""

import os
from pathlib import Path
import shutil
import subprocess

from test_docs_golden_paths import installed  # noqa: F401


def test_combined_installed_consumer(tmp_path, request):
    executable = os.environ.get("QITOS_R1_INSTALLED_PYTHON")
    if not executable:
        _, executable, _ = request.getfixturevalue("installed")
    consumer = Path(__file__).parents[2] / "examples/v5/r1_integration/consumer.py"
    shutil.copy2(consumer, tmp_path / "consumer.py")
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    for mode, name in [
        ("seed", "normal"),
        ("first", "normal"),
        ("restore", "normal"),
        ("namespace", "normal"),
        ("seed", "failure"),
        ("failure", "failure"),
        ("seed", "no-loss"),
        ("no-loss", "no-loss"),
    ]:
        result = subprocess.run(
            [str(executable), "-I", "consumer.py", mode, "--root", str(tmp_path / name)],
            cwd=tmp_path,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, result.stdout + result.stderr
