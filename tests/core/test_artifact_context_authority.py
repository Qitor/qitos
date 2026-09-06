"""Artifact metadata is user data, not a new privileged developer message."""
import hashlib

from qitos.core.artifact import ArtifactRef
from qitos.core.context import ArtifactRefContributor


def test_artifact_references_do_not_elevate_to_developer_instructions():
    body = b'evidence'
    ref = ArtifactRef(artifact_id='evidence', resolver_key='outputs',
                      sha256=hashlib.sha256(body).hexdigest(), byte_length=len(body),
                      media_type='text/plain')
    contribution = ArtifactRefContributor('files', (ref,)).contribute(None)[0]
    assert contribution.requested_placement == 'user'
    assert contribution.required
    assert contribution.content_value['artifacts'][0]['artifact_id'] == 'evidence'
