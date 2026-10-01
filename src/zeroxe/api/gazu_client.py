"""Gazu / Kitsu API Client Module."""

import logging
from typing import Optional, Tuple
import gazu
from zeroxe.services.settings_service import SettingsService

logger = logging.getLogger(__name__)

# Default network timeout for Kitsu requests (in seconds) to prevent application hangs
DEFAULT_TIMEOUT = 3.0


def _ensure_session_timeout(client: gazu.client.KitsuClient = None, timeout: float = DEFAULT_TIMEOUT) -> None:
    """Ensure gazu client session has a default timeout to prevent hanging."""
    try:
        target_client = client or gazu.client.default_client
        session = getattr(target_client, "session", None)
        if session and not getattr(session, "_has_default_timeout", False):
            orig_request = session.request

            def timeout_request(*args, **kwargs):
                if "timeout" not in kwargs or kwargs["timeout"] is None:
                    kwargs["timeout"] = timeout
                return orig_request(*args, **kwargs)

            session.request = timeout_request
            session._has_default_timeout = True
    except Exception as e:
        logger.warning(f"Could not configure session timeout: {e}")


def init_kitsu(
    url: Optional[str] = None,
    email: Optional[str] = None,
    password: Optional[str] = None,
) -> Tuple[bool, str]:
    """Initializes the Gazu host and authenticates user.

    If parameters are not provided, loads them from SettingsService.
    Returns:
        Tuple[bool, str]: (Success status, human-readable status/error message)
    """
    _ensure_session_timeout()

    kitsu_url = (url if url is not None else SettingsService.get_kitsu_url()).strip()
    kitsu_email = (email if email is not None else SettingsService.get_kitsu_email()).strip()
    kitsu_password = password if password is not None else SettingsService.get_kitsu_password()

    if not kitsu_url:
        msg = "Kitsu URL is empty."
        logger.warning(msg)
        return False, msg

    kitsu_url = kitsu_url.rstrip("/")
    if not kitsu_url.endswith("/api"):
        kitsu_url = f"{kitsu_url}/api"

    try:
        gazu.set_host(kitsu_url)
    except Exception as e:
        msg = f"Failed to set Kitsu host '{kitsu_url}': {e}"
        logger.error(msg)
        return False, msg

    if not kitsu_email or not kitsu_password:
        msg = "Kitsu host configured, but email or password is missing."
        logger.warning(msg)
        return False, msg

    try:
        gazu.log_in(kitsu_email, kitsu_password)
        msg = f"Successfully logged in to Kitsu as {kitsu_email}"
        logger.info(msg)
        return True, msg
    except getattr(gazu.exception, "AuthFailedException", Exception) as e:
        msg = f"Kitsu authentication failed. Invalid email or password: {e}"
        logger.warning(msg)
        return False, msg
    except Exception as e:
        msg = f"Failed to connect to Kitsu host '{kitsu_url}': {e}"
        logger.warning(msg)
        return False, msg