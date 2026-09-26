"""Selectable demo identities, not authentication or filesystem protection.

Future retrieval must build its index from authorized_documents(), so restricted
text never enters scoring, snippets, or model context for a technician.
"""

from types import MappingProxyType
from typing import Literal

from dealer_evidence_agent.corpus import PolicyDocument

Role = Literal["technician", "manager"]
IDENTITY_ROLES = MappingProxyType({"tech_demo": "technician", "manager_demo": "manager"})
ROLE_VISIBILITIES = MappingProxyType(
    {"technician": frozenset({"shared"}), "manager": frozenset({"shared", "manager_only"})}
)


class AuthorizationError(ValueError):
    """Unknown identities and roles have no access."""


def resolve_role(identity: str) -> Role:
    if not isinstance(identity, str) or identity not in IDENTITY_ROLES:
        raise AuthorizationError("Unknown demo identity.")
    return IDENTITY_ROLES[identity]


def can_access(role: Role, visibility: str) -> bool:
    """Unknown roles and visibility labels fail closed, including at runtime."""
    if not isinstance(role, str) or not isinstance(visibility, str):
        return False
    return visibility in ROLE_VISIBILITIES.get(role, frozenset())


def authorized_documents(
    documents: tuple[PolicyDocument, ...], identity: str
) -> tuple[PolicyDocument, ...]:
    role = resolve_role(identity)
    return tuple(doc for doc in documents if can_access(role, doc.visibility))
