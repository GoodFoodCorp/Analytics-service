"""The authenticated caller, read from the auth-service JWT."""

from __future__ import annotations

from dataclasses import dataclass, field

ROLE_ADMIN = "admin"
ROLE_MANAGER = "manager"


@dataclass(frozen=True)
class Actor:
    user_id: str
    tenant_id: str = ""
    role_slugs: tuple[str, ...] = field(default_factory=tuple)
    token: str = ""

    def has_role(self, slug: str) -> bool:
        return slug in self.role_slugs

    @property
    def is_admin(self) -> bool:
        return self.has_role(ROLE_ADMIN)

    @property
    def is_manager(self) -> bool:
        return self.has_role(ROLE_MANAGER)
