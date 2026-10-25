import pytest

from supportpilot.security import make_auth


def test_empty_and_short_configuration_rejected():
    with pytest.raises(ValueError):
        make_auth({})
    with pytest.raises(ValueError):
        make_auth({"short": {"tenant": "demo", "user": "alice"}})


def test_unknown_role_rejected():
    with pytest.raises(ValueError):
        make_auth(
            {"valid-token-0000000000000000": {"tenant": "demo", "user": "alice", "role": "admin"}}
        )
