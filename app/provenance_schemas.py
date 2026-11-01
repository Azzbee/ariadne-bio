"""Bounded contracts for correlated provenance-record withdrawal audits."""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.audit_schemas import AuditState
from app.schemas import Entity, ExtensibleResponse

GroupId = Annotated[str, Field(strict=True, min_length=1, max_length=240)]


class ProvenanceAuditRequest(BaseModel):
    """Declare the complete group universe and conditional protection assumptions."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    disease_id: str = Field(min_length=1, max_length=180)
    compound_id: str = Field(min_length=1, max_length=180)
    top_k: int = Field(default=10, ge=1, le=100, strict=True)
    budget: int = Field(default=2, ge=0, le=2, strict=True)
    group_kind: Literal["source", "pubmed"] = "source"
    group_ids: list[GroupId] | None = Field(default=None, min_length=1, max_length=16)
    protected_group_ids: list[GroupId] = Field(default_factory=list, max_length=16)

    @model_validator(mode="after")
    def explicit_group_scope(self):
        """Never silently substitute an unbounded citation universe or merge duplicates."""
        if self.group_kind == "pubmed" and self.group_ids is None:
            raise ValueError("PubMed audits require an explicit selection of 1..16 groups")
        for groups in (self.group_ids, self.protected_group_ids):
            if groups is None:
                continue
            if len(set(groups)) != len(groups):
                raise ValueError("Group identifiers must be unique")
            if any(not group.startswith(f"{self.group_kind}:") for group in groups):
                raise ValueError("All group identifiers must match the requested group kind")
        if self.group_ids is not None and not set(self.protected_group_ids).issubset(
            self.group_ids
        ):
            raise ValueError("Protected groups must belong to the selected group universe")
        return self


class ProvenanceAuditResponse(ExtensibleResponse):
    """Complete sealed claims; extra scientific fields retain their original values."""

    schema_version: Literal["1.0"]
    method: Literal["provenance-group-exhaustive-v1"]
    disease: Entity
    compound: Entity
    top_k: int = Field(ge=1, le=100)
    budget: int = Field(ge=0, le=2)
    scope: dict[str, Any]
    identity: dict[str, Any]
    baseline: AuditState
    results: list[dict[str, Any]] = Field(min_length=1, max_length=3)
    proof: dict[str, Any]
    interpretation: str
    certificate_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
