"""HTTP routes for the model's bounded global binding-record sensitivity audit."""

from fastapi import APIRouter, HTTPException, Request

from app.audit_schemas import (
    AuditRequest,
    AuditResponse,
    AuditVerificationRequest,
    AuditVerificationResponse,
)

router = APIRouter(prefix="/api", tags=["Decision audit"])


def _auditor(request: Request):
    service = request.app.state.service
    if service.engine.model is None:
        raise HTTPException(503, "Run make evaluate to create the fitted model before auditing")
    return service.auditor


@router.post("/audit", response_model=AuditResponse)
def audit(request: Request, payload: AuditRequest):
    """Certify worst supported rank for up to two binding withdrawals over the full graph."""
    return _auditor(request).audit(
        payload.disease_id, payload.compound_id, top_k=payload.top_k, budget=payload.budget
    )


@router.post("/audit/verify", response_model=AuditVerificationResponse)
def verify_audit(request: Request, payload: AuditVerificationRequest):
    """Recompute the complete claim and independently replay its concrete graph edits."""
    return _auditor(request).verify(payload.certificate)
