import json

import pytest
from usermeta import user_id_from_metadata


def test_the_user_comes_from_the_dispatch_metadata():
    assert user_id_from_metadata(json.dumps({"user_id": 3}), default=1) == 3


@pytest.mark.parametrize(
    "metadata",
    [None, "", "not json", "[]", "{}", '{"user_id": "abc"}', '{"user_id": 0}', '{"user_id": -4}', '{"user_id": true}',
     '{"user_id": 1.5}', '{"other": 2}'],
)
def test_anything_unusable_falls_back_to_the_configured_user(metadata):
    assert user_id_from_metadata(metadata, default=7) == 7


def test_a_numeric_string_is_accepted():
    assert user_id_from_metadata('{"user_id": "2"}', default=1) == 2
