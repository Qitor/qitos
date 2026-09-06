"""JSON tool arguments must be inspected as data, not JSON escape syntax."""
import json

import pytest

from qitos.core.session import (
    SnapshotComponent, SnapshotComponentCodec, SnapshotComponentRegistry, SessionContractError,
)


CODEC = SnapshotComponentCodec(
    slot="encoded_probe", owner="tests.encoded", schema_version="tests.encoded/v1",
    required=True, encode=dict, decode=dict,
)


@pytest.mark.parametrize("field", ["tool_arguments", "state_source"])
def test_python_file_handle_before_json_newline_is_not_a_windows_path(field):
    value = json.dumps({"command": "with open('results.csv') as f:\n    print(f.read())\n"})
    component = SnapshotComponent.from_value(CODEC, {field: value})
    assert component.decode(SnapshotComponentRegistry([CODEC])) == {field: value}


@pytest.mark.parametrize("private", [r"C:\Users\private\file", r"F:\new\file",
                                   "/home/private/file", "Bearer PRIVATE_VALUE",
                                   "password=PRIVATE_VALUE"])
@pytest.mark.parametrize("depth", [0, 1, 2])
def test_encoded_real_private_material_is_still_rejected_without_echo(private, depth):
    value = private
    for _ in range(depth):
        value = json.dumps({"payload": value})
    with pytest.raises(SessionContractError) as caught:
        SnapshotComponent.from_value(CODEC, {"value": value})
    assert "PRIVATE_VALUE" not in str(caught.value)
    assert private not in str(caught.value)
