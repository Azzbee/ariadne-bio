"""Read-only source/citation catalogue, correlated audit and certificate replay."""

from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, Request

from app.audit_schemas import AuditVerificationRequest, AuditVerificationResponse
from app.provenance_schemas import ProvenanceAuditRequest, ProvenanceAuditResponse

router = APIRouter(prefix="/api/provenance", tags=["Shared evidence dependencies"])


def _auditor(request: Request, *, require_model=True):
    service = request.app.state.service
    if require_model and service.engine.model is None:
        raise HTTPException(503, "Run make evaluate to create the fitted model before auditing")
    return service.provenance_auditor


@router.get("/groups")
def groups(
    request: Request,
    kind: Literal["source", "pubmed"] = "source",
    q: Annotated[str, Query(max_length=240)] = "",
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict:
    """Inventory observed binding-record labels, without asserting source independence."""
    return _auditor(request, require_model=False).catalog(kind, q, limit, offset)


@router.post("/audit", response_model=ProvenanceAuditResponse)
def audit(request: Request, payload: ProvenanceAuditRequest):
    """Enumerate correlated group withdrawals, including effects on every competitor."""
    return _auditor(request).audit(
        payload.disease_id,
        payload.compound_id,
        top_k=payload.top_k,
        budget=payload.budget,
        group_kind=payload.group_kind,
        group_ids=payload.group_ids,
        protected_group_ids=payload.protected_group_ids,
    )


@router.post("/audit/verify", response_model=AuditVerificationResponse)
def verify_audit(request: Request, payload: AuditVerificationRequest):
    """Reconstruct the declared group universe, exact claims and actual matrix edits."""
    return _auditor(request).verify(payload.certificate)
