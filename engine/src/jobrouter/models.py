"""Explicit contracts: unknown facts never silently become passes."""
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import math


def now():
    return datetime.now(timezone.utc).isoformat()


class Verdict(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"


@dataclass
class Evidence:
    url: str
    observed_at: str
    quote: str
    field: str
    digest: str
    expires_at: str | None = None

    @classmethod
    def from_text(cls, url, text, quote, field, observed_at=None):
        if not quote or quote not in text:
            raise ValueError("Evidence must be an exact nonempty substring")
        return cls(url, observed_at or now(), quote, field,
                   hashlib.sha256(text.encode()).hexdigest())


@dataclass
class Job:
    provider: str
    board: str
    external_id: str
    title: str
    company: str
    url: str
    description: str
    location: str = ""
    arrangement: str = "unknown"
    employment: str = "unknown"
    countries: list[str] = field(default_factory=list)
    salary_min: float | None = None
    salary_max: float | None = None
    currency: str | None = None
    salary_period: str | None = None
    salary_type: str = "unknown"
    hours_min: float | None = None
    hours_max: float | None = None
    experience_min: float | None = None
    required_skills: list[str] = field(default_factory=list)
    sector: str = "unknown"
    sponsorship: str = "unknown"
    observed_at: str = field(default_factory=now)
    published_at: str | None = None
    deadline: str | None = None
    availability: str = "unverified"
    apply_url: str | None = None
    evidence: list[Evidence] = field(default_factory=list)

    @property
    def identity(self):
        return f"{self.provider.lower()}:{self.board.lower()}:{self.external_id}"

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        data = dict(data)
        data["evidence"] = [Evidence(**x) if isinstance(x, dict) else x for x in data.get("evidence", [])]
        return cls(**data)


@dataclass
class Brief:
    prompt: str
    role_families: list[str] = field(default_factory=list)
    locations: list[str] = field(default_factory=list)
    country: str | None = None
    arrangements: list[str] = field(default_factory=list)
    employment_types: list[str] = field(default_factory=list)
    minimum_base: float | None = None
    currency: str = "USD"
    minimum_hours: float | None = None
    maximum_experience: float | None = None
    excluded_sectors: list[str] = field(default_factory=list)
    excluded_required_skills: list[str] = field(default_factory=list)
    needs_sponsorship: bool = False
    profile: dict | None = None
    count: int = 10
    unresolved: list[str] = field(default_factory=list)
    requirements: list[dict] = field(default_factory=list)
    preferences: list[str] = field(default_factory=list)

    def validate(self):
        if not isinstance(self.prompt, str) or not self.prompt.strip():
            raise ValueError("A search prompt is required")
        if isinstance(self.count, bool) or not isinstance(self.count, int) or not 1 <= self.count <= 100:
            raise ValueError("count must be between 1 and 100")
        for name in ("minimum_base", "minimum_hours", "maximum_experience"):
            value = getattr(self, name)
            if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0):
                raise ValueError(f"Invalid {name}")
        for name in ("role_families", "locations", "arrangements", "employment_types",
                     "excluded_sectors", "excluded_required_skills", "unresolved", "preferences"):
            value = getattr(self, name)
            if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
                raise ValueError(f"{name} must be a list of nonempty strings")
        if not isinstance(self.requirements, list):
            raise ValueError("requirements must be a list")
        if self.profile is not None and not isinstance(self.profile, dict):
            raise ValueError("profile must be an object or null")
        if self.country is not None and (not isinstance(self.country, str) or not self.country.strip()):
            raise ValueError("country must be a nonempty string or null")
        if not isinstance(self.currency, str) or not self.currency.strip():
            raise ValueError("currency must be a nonempty string")
        if not isinstance(self.needs_sponsorship, bool):
            raise ValueError("needs_sponsorship must be boolean")
        ids = set()
        profile_text = json.dumps(self.profile, ensure_ascii=False, sort_keys=True) if self.profile is not None else ""
        for requirement in self.requirements:
            if not isinstance(requirement, dict) or any(not isinstance(requirement.get(key), str) or not requirement[key].strip() for key in ("id", "description", "source_quote")) or requirement["id"] in ids:
                raise ValueError("Generic requirements need unique identities and descriptions")
            source = self.prompt if requirement.get("source") == "prompt" else profile_text if requirement.get("source") == "profile" else ""
            if not requirement.get("source_quote") or requirement["source_quote"] not in source:
                raise ValueError("Generic requirement lacks input provenance")
            ids.add(requirement["id"])
        return self

    @property
    def digest(self):
        return hashlib.sha256(json.dumps(asdict(self), sort_keys=True).encode()).hexdigest()


@dataclass
class Check:
    criterion: str
    verdict: Verdict
    reason: str


@dataclass
class Decision:
    identity: str
    category: str
    score: float
    checks: list[Check]
    reasons: list[str]
    model: str | None = None
    reviewed: bool = False

    def to_dict(self):
        return asdict(self)
