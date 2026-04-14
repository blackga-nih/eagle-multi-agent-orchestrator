"""Tests for app.aws_session — credential path selection, singleton behaviour,
and reset_shared_session().

Run: pytest server/tests/test_aws_session.py -v
"""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

_server_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
if _server_dir not in sys.path:
    sys.path.insert(0, _server_dir)


@pytest.fixture(autouse=True)
def reset_session():
    from app import aws_session

    aws_session.reset_shared_session()
    yield
    aws_session.reset_shared_session()


class TestGetSharedSession:
    def test_no_profile_uses_default_chain(self):
        with patch.dict(os.environ, {}, clear=True), patch(
            "app.aws_session.boto3.Session"
        ) as mock_session:
            from app.aws_session import get_shared_session

            sess = get_shared_session()
            mock_session.assert_called_once_with()
            assert sess is not None

    def test_known_profile_uses_profile_session(self):
        with patch.dict(os.environ, {"AWS_PROFILE": "eagle"}), patch(
            "app.aws_session._profile_exists", return_value=True
        ), patch("app.aws_session.boto3.Session") as mock_session:
            from app.aws_session import get_shared_session

            get_shared_session()
            mock_session.assert_called_once_with(profile_name="eagle")

    def test_unknown_profile_falls_through_to_default(self):
        with patch.dict(os.environ, {"AWS_PROFILE": "nonexistent"}), patch(
            "app.aws_session._profile_exists", return_value=False
        ), patch("app.aws_session.boto3.Session") as mock_session:
            from app.aws_session import get_shared_session

            get_shared_session()
            mock_session.assert_called_once_with()  # no profile_name

    def test_singleton_returns_same_object(self):
        # Clear AWS_PROFILE so _profile_exists() doesn't fire its own
        # boto3.Session() probe and inflate the call count.
        with patch.dict(os.environ, {}, clear=True), patch(
            "app.aws_session.boto3.Session"
        ) as mock_session:
            mock_session.return_value = MagicMock()
            from app.aws_session import get_shared_session

            s1 = get_shared_session()
            s2 = get_shared_session()
            assert s1 is s2
            mock_session.assert_called_once()

    def test_reset_forces_reinit(self):
        with patch.dict(os.environ, {}, clear=True), patch(
            "app.aws_session.boto3.Session"
        ) as mock_session:
            mock_session.return_value = MagicMock()
            from app.aws_session import get_shared_session, reset_shared_session

            get_shared_session()
            reset_shared_session()
            get_shared_session()
            assert mock_session.call_count == 2
