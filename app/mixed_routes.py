"""Exact, bounded joint audits and independent certificate replay over HTTP."""

from fastapi import APIRouter, HTTPException, Request

from app.audit_schemas import AuditVerificationRequest, AuditVerificationResponse
from app.mixed_schemas import MixedAuditRequest, MixedAuditResponse

router = APIRouter(prefix="/api/mixed", tags=["Joint evidence audit"])


def _auditor(request: Request):
    service = request.app.state.service
    if service.engine.model is None:
        raise HTTPException(503, "Run make evaluate to create the fitted model before auditing")
    return service.mixed_auditor


@router.post("/audit", response_model=MixedAuditResponse)
def audit(request: Request, payload: MixedAuditRequest):
    """Condition on group withdrawals, then optimize a surviving record withdrawal."""
    return _auditor(request).audit(**payload.model_dump())


@router.post("/audit/verify", response_model=AuditVerificationResponse)
def verify_audit(request: Request, payload: AuditVerificationRequest):
    """Recompute the whole frontier and replay the reported graph edits separately."""
    return _auditor(request).verify(payload.certificate)
