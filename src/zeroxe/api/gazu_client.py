"""Gazu / Kitsu API Client Module."""

import logging
from typing import Optional, Tuple

import gazu
from zeroxe.services.settings_service import SettingsService

logger = logging.getLogger(__name__)


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

    if kitsu_email and kitsu_password:
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
            msg = f"Error during Kitsu authentication: {e}"
            logger.error(msg)
            return False, msg

    msg = "Kitsu host set, but credentials were not provided."
    logger.info(msg)
    return False, msg