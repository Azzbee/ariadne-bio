"""Bounded public contracts for simultaneous provenance and record withdrawals."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.audit_schemas import AuditState
from app.provenance_schemas import GroupId
from app.schemas import Entity, ExtensibleResponse


class MixedAuditRequest(BaseModel):
    """Two separate budgets preserve the units of a joint evidence stress test."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    disease_id: str = Field(min_length=1, max_length=180)
    compound_id: str = Field(min_length=1, max_length=180)
    top_k: int = Field(default=10, ge=1, le=100, strict=True)
    group_budget: int = Field(default=1, ge=0, le=1, strict=True)
    edge_budget: int = Field(default=1, ge=0, le=1, strict=True)
    group_kind: Literal["source", "pubmed"] = "source"
    group_ids: list[GroupId] | None = Field(default=None, min_length=1, max_length=16)

    @model_validator(mode="after")
    def explicit_group_scope(self):
        """A selected annotation universe must be finite, typed and unambiguous."""
        if self.group_kind == "pubmed" and self.group_ids is None:
            raise ValueError("PubMed audits require an explicit selection of 1..16 groups")
        if self.group_ids is not None:
            if len(set(self.group_ids)) != len(self.group_ids):
                raise ValueError("Group identifiers must be unique")
            if any(not group.startswith(f"{self.group_kind}:") for group in self.group_ids):
                raise ValueError("All group identifiers must match the requested group kind")
        return self


class MixedAuditResponse(ExtensibleResponse):
    """Keep the complete sealed frontier; serialization cannot discard proof fields."""

    schema_version: Literal["1.0"]
    method: Literal["mixed-group-edge-envelope-v1"]
    disease: Entity
    compound: Entity
    top_k: int = Field(ge=1, le=100)
    group_budget: int = Field(ge=0, le=1)
    edge_budget: int = Field(ge=0, le=1)
    scope: dict[str, Any]
    identity: dict[str, Any]
    baseline: AuditState
    results: list[dict[str, Any]] = Field(min_length=1, max_length=4)
    proof: dict[str, Any]
    interpretation: str
    certificate_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
