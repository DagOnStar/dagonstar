"""Public FAIR declaration models; deliberately dependency-free."""
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any


@dataclass
class Agent:
    name: str
    orcid: Optional[str] = None
    ror: Optional[str] = None
    email: Optional[str] = None
    affiliation: Optional[str] = None


@dataclass
class AccessPolicy:
    metadata: str = "public"
    data: str = "local"
    embargo_until: Optional[str] = None
    access_url: Optional[str] = None


@dataclass
class Artifact:
    path: str
    name: Optional[str] = None
    description: Optional[str] = None
    media_type: Optional[str] = None
    license: Optional[str] = None
    identifier: Optional[str] = None
    semantic_type: Optional[str] = None
    access_policy: Optional[AccessPolicy] = None
    checksum: Optional[str] = None
    size_bytes: Optional[int] = None
    generated_by: Optional[str] = None
    used_by: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class FairProfile:
    title: str
    description: str
    creators: List[Agent]
    license: str
    keywords: List[str] = field(default_factory=list)
    access_policy: AccessPolicy = field(default_factory=AccessPolicy)
    strict: bool = False
    export: List[str] = field(default_factory=lambda: ["ro-crate", "prov-json", "html"])
    output_dir: Optional[str] = None
    capture_environment: List[str] = field(default_factory=list)
    redact_patterns: List[str] = field(default_factory=lambda: [
        "TOKEN", "SECRET", "PASSWORD", "PRIVATE_KEY", "AWS_", "GCP_", "AZURE_"
    ])

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)
