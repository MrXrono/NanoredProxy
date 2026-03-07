import pytest
from fastapi import HTTPException

from app.core.security import create_access_token, verify_token


def test_token_roundtrip():
    token = create_access_token('admin')
    payload = verify_token(token)
    assert payload['sub'] == 'admin'


def test_invalid_token_raises():
    with pytest.raises(HTTPException):
        verify_token('bad-token')
