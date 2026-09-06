"""Selective instructions and application-requested forgetting are lossless."""
import pytest

from qitos.core.memory import MemoryRecord
from qitos.kit.memory.memdir_memory import MemdirMemory
from qitos.kit.skill.injector import SkillInjector
from qitos.kit.skill.manifest import SkillManifest


def test_selected_instructions_are_not_silently_truncated():
    body = 'Use the evidence.\n' * 120 + 'MANDATORY_FINAL_CHECK'
    skill = SkillManifest(name='audit', description='Evidence audit', instructions=body)
    injector = SkillInjector()
    assert body in injector.build_system_prompt('Research', [skill])
    assert 'MANDATORY_FINAL_CHECK' not in injector.build_catalog([skill])
    assert 'Evidence audit' in injector.build_catalog([skill])


def test_forgetting_is_scoped_and_visible_to_reopened_consumer(tmp_path):
    first = MemdirMemory(str(tmp_path / 'one'), create=True)
    other = MemdirMemory(str(tmp_path / 'two'), create=True)
    for memory in (first, other):
        memory.append(MemoryRecord('user', 'old preference', 0, record_id='preference'))
    first.append(MemoryRecord('user', 'new preference', 1, record_id='preference'))
    assert len(first.retrieve()) == 1
    assert first.delete('preference') is True
    assert first.delete('preference') is False
    assert MemdirMemory(str(tmp_path / 'one')).retrieve() == []
    assert other.retrieve()[0].content == 'old preference'
    assert 'preference' not in first.summarize()
    with pytest.raises(ValueError):
        first.delete('../two')
