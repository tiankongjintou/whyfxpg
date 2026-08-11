"""Domain configuration store: access to domain profiles and taxonomies."""

from typing import Any

from whyfxpg.core.config_loader import DEFAULT_CONFIG_DIR, ConfigLoader


def _profile_to_dict(profile: Any) -> dict[str, Any]:
    if hasattr(profile, "to_dict"):
        return profile.to_dict()
    return profile.__dict__


class DomainConfigStore:
    """Read-only store for domain profiles and dimensions."""

    def __init__(self, config_dir: str | None = None):
        self.loader = ConfigLoader(config_dir) if config_dir else ConfigLoader(str(DEFAULT_CONFIG_DIR))

    def list_domains(self) -> list[dict[str, Any]]:
        """Return all configured domain profiles as dicts."""
        return [_profile_to_dict(profile) for profile in self.loader.typed_domains]

    def get_domain(self, domain_id: str) -> dict[str, Any] | None:
        """Return a specific domain profile by id."""
        for profile in self.loader.typed_domains:
            if getattr(profile, "domain_id", None) == domain_id:
                return _profile_to_dict(profile)
        return None

    def get_active_domain(self) -> dict[str, Any] | None:
        """Return the currently active domain profile."""
        active = self.loader.typed_active_domain
        if active is None:
            return None
        return _profile_to_dict(active)
