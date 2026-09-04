"""Pin serialized contracts while keeping prior candidate bytes readable."""
from dataclasses import fields
import json
from pathlib import Path

import qitos.tracing.trajectory as trajectory

ROOT = Path(__file__).resolve().parents[2]


def test_frozen_trajectory_contract_matches_public_wire_shapes():
    contract = json.loads((ROOT / 'tests/fixtures/s4/g5/frozen-trajectory-contract.json').read_text())
    assert contract['status'] == 'frozen'
    for name, value in contract['versions'].items():
        assert getattr(trajectory, name) == value
    for name, names in contract['fields'].items():
        assert [field.name for field in fields(getattr(trajectory, name))] == names
    for name, values in contract['enums'].items():
        assert [member.value for member in getattr(trajectory, name)] == values


def test_pre_freeze_consumer_trajectories_remain_exactly_readable():
    for name in ('coding', 'research'):
        path = ROOT / f'tests/fixtures/s4/g5/{name}-trajectory.json'
        document = json.loads(path.read_text())
        restored = trajectory.Trajectory.from_dict(document['trajectory'])
        assert restored.to_dict() == document['trajectory']
        assert all(record.validate_integrity() for record in restored.records)
