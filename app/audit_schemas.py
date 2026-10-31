"""Public contracts for bounded, frozen-model binding-record rank audits."""

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, field_validator

from app.schemas import Entity, ExtensibleResponse


class AuditRequest(BaseModel):
    """The public budget is deliberately bounded; no arbitrary graph edits are accepted."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    disease_id: str = Field(min_length=1, max_length=180)
    compound_id: str = Field(min_length=1, max_length=180)
    top_k: int = Field(default=10, ge=1, le=100, strict=True)
    budget: int = Field(default=2, ge=0, le=2, strict=True)


class AuditState(ExtensibleResponse):
    """Supported ranks and diagnostic scores remain distinct under record withdrawal."""

    supported: bool
    rank: int | None = Field(ge=1)
    score: FiniteFloat = Field(ge=0, le=1)
    logit: FiniteFloat
    counts: dict[str, int]
    evidence_count: int = Field(ge=0)


class AuditWitness(ExtensibleResponse):
    """A concrete attaining graph edit with provenance, never an assertion of falsity."""

    removed_edge_ids: list[str] = Field(max_length=2)
    removed_records: list[dict[str, Any]] = Field(max_length=2)
    deletions_used: int = Field(ge=0, le=2)
    focus: AuditState
    changed_compounds: list[dict[str, Any]] = Field(max_length=2)


class BudgetAudit(ExtensibleResponse):
    """The exact supported-rank maximum and attainable loss of support are separate."""

    budget: int = Field(ge=0, le=2)
    worst_supported_rank: int | None = Field(ge=1)
    unsupported_attainable: bool
    top_k_robust: bool
    focus_only_worst_rank: int | None = Field(ge=1)
    focus_only_unsupported_attainable: bool
    competitor_rank_gap: int | None = Field(ge=0)
    rank_witness: AuditWitness | None
    unsupported_witness: AuditWitness | None


class AuditResponse(ExtensibleResponse):
    """A versioned, hashed scientific payload whose claims can be recomputed."""

    schema_version: Literal["1.0"]
    method: Literal["binding-envelope-v1"]
    disease: Entity
    compound: Entity
    top_k: int = Field(ge=1, le=100)
    budget: int = Field(ge=0, le=2)
    scope: dict[str, Any]
    identity: dict[str, Any]
    baseline: AuditState
    results: list[BudgetAudit] = Field(min_length=1, max_length=3)
    minimum_failure_budget: int | None = Field(ge=0, le=2)
    robust_through_budget: int | None = Field(ge=0, le=2)
    proof: dict[str, Any]
    interpretation: str
    certificate_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class AuditVerificationRequest(BaseModel):
    """Accept an exported object, with a bounded size and no execution instructions."""

    model_config = ConfigDict(extra="forbid")
    certificate: dict[str, Any]

    @field_validator("certificate")
    @classmethod
    def bound_certificate(cls, value):
        """Reject oversized or nonfinite payloads before invoking graph calculations."""
        try:
            encoded = json.dumps(value, allow_nan=False, ensure_ascii=False).encode("utf-8")
        except (ValueError, TypeError) as error:
            raise ValueError("Certificate must contain finite JSON values") from error
        if len(encoded) > 262_144:
            raise ValueError("Certificate exceeds the 256 KiB verification limit")
        return value


class AuditVerificationResponse(ExtensibleResponse):
    """Report rechecked claims and witness replay without implying clinical validation."""

    status: Literal["verified", "invalid"]
    valid: bool
    checks: list[str]
    errors: list[str]
    verification_method: str
