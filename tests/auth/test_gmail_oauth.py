"""
Tests for src/jd_matcher/auth/gmail_oauth.py
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from jd_matcher.auth.gmail_oauth import (
    OAuthTokenInvalid,
    SCOPES,
    get_credentials,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_valid_creds() -> MagicMock:
    creds = MagicMock()
    creds.valid = True
    creds.expired = False
    creds.refresh_token = "rt_fake"
    creds.to_json.return_value = json.dumps({"token": "fake", "scopes": SCOPES})
    return creds


def _make_expired_creds() -> MagicMock:
    creds = MagicMock()
    creds.valid = False
    creds.expired = True
    creds.refresh_token = "rt_fake_expired"
    creds.to_json.return_value = json.dumps({"token": "refreshed", "scopes": SCOPES})
    return creds


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestGetCredentialsFirstRun:
    def test_first_run_runs_loopback_flow_and_writes_token(self, tmp_path: Path) -> None:
        client_path = tmp_path / "credentials.json"
        client_path.write_text("{}", encoding="utf-8")
        token_path = tmp_path / "tokens.json"

        fresh_creds = _make_valid_creds()

        with patch(
            "jd_matcher.auth.gmail_oauth.InstalledAppFlow.from_client_secrets_file"
        ) as mock_flow_cls:
            mock_flow = MagicMock()
            mock_flow.run_local_server.return_value = fresh_creds
            mock_flow_cls.return_value = mock_flow

            with patch(
                "jd_matcher.auth.gmail_oauth.Credentials.from_authorized_user_file"
            ) as mock_load:
                # Simulate no stored token — from_authorized_user_file raises
                # FileNotFoundError only if the file doesn't exist; here we make
                # token_path not exist so the load branch is skipped.
                mock_load.side_effect = Exception("no token")

                result = get_credentials(client_path, token_path)

        mock_flow_cls.assert_called_once_with(str(client_path), SCOPES)
        mock_flow.run_local_server.assert_called_once_with(port=0)
        assert token_path.exists(), "token file should be written"
        assert result is fresh_creds


class TestGetCredentialsExistingToken:
    def test_uses_existing_valid_token_without_flow(self, tmp_path: Path) -> None:
        client_path = tmp_path / "credentials.json"
        token_path = tmp_path / "tokens.json"
        token_path.write_text("{}", encoding="utf-8")

        valid_creds = _make_valid_creds()

        with patch(
            "jd_matcher.auth.gmail_oauth.Credentials.from_authorized_user_file",
            return_value=valid_creds,
        ):
            with patch(
                "jd_matcher.auth.gmail_oauth.InstalledAppFlow.from_client_secrets_file"
            ) as mock_flow_cls:
                result = get_credentials(client_path, token_path)

        # Flow must NOT be invoked because the token is already valid.
        mock_flow_cls.assert_not_called()
        assert result is valid_creds


class TestGetCredentialsRefresh:
    def test_refreshes_expired_token(self, tmp_path: Path) -> None:
        client_path = tmp_path / "credentials.json"
        token_path = tmp_path / "tokens.json"
        token_path.write_text("{}", encoding="utf-8")

        expired_creds = _make_expired_creds()
        # After refresh, mark as valid.
        expired_creds.valid = False  # before refresh

        def do_refresh(_request: object) -> None:
            expired_creds.valid = True
            expired_creds.expired = False

        expired_creds.refresh.side_effect = do_refresh

        with patch(
            "jd_matcher.auth.gmail_oauth.Credentials.from_authorized_user_file",
            return_value=expired_creds,
        ):
            with patch("jd_matcher.auth.gmail_oauth.Request"):
                result = get_credentials(client_path, token_path)

        expired_creds.refresh.assert_called_once()
        assert result is expired_creds

    def test_oauth_token_invalid_surfaces_clearly(self, tmp_path: Path) -> None:
        client_path = tmp_path / "credentials.json"
        token_path = tmp_path / "tokens.json"
        token_path.write_text("{}", encoding="utf-8")

        expired_creds = _make_expired_creds()

        from google.auth.exceptions import RefreshError

        expired_creds.refresh.side_effect = RefreshError("Token has been expired or revoked.")

        with patch(
            "jd_matcher.auth.gmail_oauth.Credentials.from_authorized_user_file",
            return_value=expired_creds,
        ):
            with patch("jd_matcher.auth.gmail_oauth.Request"):
                with pytest.raises(OAuthTokenInvalid) as exc_info:
                    get_credentials(client_path, token_path)

        assert "re-authorize" in str(exc_info.value).lower()
