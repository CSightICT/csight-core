"""External dependency ports used by application services."""

from app.ports.hashing import FileDigest, HashingPort
from app.ports.identity import IdentityRepository
from app.ports.llm import LLMProvider
from app.ports.message_queue import MessageQueue
from app.ports.observability import CompensationFailureObserver, CompensationStep
from app.ports.readiness import (
    DependencyProbe,
    ProbeResult,
    ProbeStatus,
    ReadinessReport,
    ReadinessService,
)
from app.ports.repository import Repository
from app.ports.security import (
    AccessTokenClaims,
    AccessTokenCodec,
    ExpiredTokenError,
    InvalidTokenError,
    PasswordHasher,
    SecurityError,
)
from app.ports.storage import ObjectStorage, StoredObject
from app.ports.vector_store import VectorMatch, VectorStore
from app.ports.vision import VisionProvider

__all__ = [
    "AccessTokenClaims",
    "AccessTokenCodec",
    "CompensationFailureObserver",
    "CompensationStep",
    "DependencyProbe",
    "ExpiredTokenError",
    "FileDigest",
    "HashingPort",
    "IdentityRepository",
    "InvalidTokenError",
    "LLMProvider",
    "MessageQueue",
    "ObjectStorage",
    "PasswordHasher",
    "ProbeResult",
    "ProbeStatus",
    "ReadinessReport",
    "ReadinessService",
    "Repository",
    "SecurityError",
    "StoredObject",
    "VectorMatch",
    "VectorStore",
    "VisionProvider",
]
