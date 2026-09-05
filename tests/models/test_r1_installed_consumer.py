"""Run the standalone proof in an explicitly supplied installed-wheel venv."""
import os
from pathlib import Path
import shutil
import subprocess

import pytest


def test_installed_multiround_consumer(tmp_path):
    executable = os.environ.get('QITOS_R1_INSTALLED_PYTHON')
    if not executable:
        pytest.skip('set QITOS_R1_INSTALLED_PYTHON to the independent wheel venv')
    source = Path(__file__).parents[2] / 'examples/v5/r1_a_model_io/consumer.py'
    shutil.copy2(source, tmp_path / 'consumer.py')
    environment = dict(os.environ)
    environment.pop('PYTHONPATH', None)
    result = subprocess.run([executable, 'consumer.py'], cwd=tmp_path, env=environment,
                            text=True, capture_output=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    assert '"requests": 3, "executions": 3' in result.stdout
    assert '"requests": 2, "executions": 2' in result.stdout
    assert '"final": "11"' in result.stdout
