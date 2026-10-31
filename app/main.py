"""FastAPI boundary for a read-only, reproducible biomedical investigator."""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from neo4j.exceptions import Neo4jError, ServiceUnavailable

from app import __version__
from app.agent import EvidenceAgent
from app.audit_routes import router as audit_router
from app.config import Settings
from app.schemas import (
    AgentRequest,
    AgentResponse,
    AssessmentResponse,
    ChallengeRequest,
    ChallengeResponse,
    DiseaseResponse,
    EvidenceResponse,
    HealthResponse,
    RankingResponse,
    parse_exclusions,
)
from app.service import EvidenceService

Limit = Annotated[int, Query(ge=1, le=100)]


# A factory binds independent route handlers as local functions.
# pylint: disable-next=too-many-locals
def create_app(settings=None, service=None, agent=None) -> FastAPI:
    """Application factory with injectable dependencies for meaningful API tests."""
    config = settings or Settings.from_env()
    config.validate()

    @asynccontextmanager
    async def lifespan(application):
        application.state.service = service or EvidenceService(config)
        application.state.agent = agent or EvidenceAgent(application.state.service, config)
        yield
        application.state.service.close()

    application = FastAPI(
        title="ARIADNE — Biomedical Evidence Investigator",
        description="Read-only graph evidence and retrospective research hypotheses. "
        "Scores are not clinical efficacy probabilities.",
        version=__version__,
        lifespan=lifespan,
    )

    @application.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

    @application.exception_handler(KeyError)
    async def missing_entity(_request, error):
        return JSONResponse(status_code=404, content={"detail": str(error).strip("'")})

    @application.exception_handler(ValueError)
    async def invalid_input(_request, error):
        return JSONResponse(status_code=422, content={"detail": str(error)})

    @application.exception_handler(Neo4jError)
    @application.exception_handler(ServiceUnavailable)
    async def database_error(_request, _error):
        return JSONResponse(
            status_code=503,
            content={
                "detail": "The graph query is unavailable or exceeded its resource budget. "
                "Retry a smaller query or check database health."
            },
        )

    def current(request):
        return request.app.state.service

    @application.get("/api/health", response_model=HealthResponse, tags=["Operations"])
    def health(request: Request):
        active = current(request)
        if active.repository:
            active.repository.verify(active.engine.manifest.get("dataset_sha256"))
        return {
            "status": "ok",
            "graph_backend": config.graph_backend,
            "dataset_ready": bool(active.engine.model),
            "agent_mode": (
                "llm"
                if config.llm_base_url and config.agent_mode != "deterministic"
                else "deterministic"
            ),
            "version": __version__,
        }

    @application.get("/api/stats", tags=["Evidence"])
    def stats(request: Request) -> dict:
        return current(request).engine.stats()

    @application.get("/api/diseases", response_model=DiseaseResponse, tags=["Evidence"])
    def diseases(
        request: Request,
        q: str = "",
        limit: Annotated[int, Query(ge=1, le=137)] = 30,
        offset: Annotated[int, Query(ge=0)] = 0,
    ):
        return current(request).engine.diseases(q, limit, offset)

    @application.get(
        "/api/rankings/{disease_id}", response_model=RankingResponse, tags=["Evidence"]
    )
    def rankings(
        request: Request,
        disease_id: str,
        exclude: str = "",
        limit: Limit = 20,
        offset: Annotated[int, Query(ge=0)] = 0,
    ):
        return current(request).engine.rankings(
            disease_id, parse_exclusions(exclude), limit, offset
        )

    @application.get(
        "/api/assessment/{disease_id}/{compound_id}",
        response_model=AssessmentResponse,
        tags=["Evidence"],
    )
    def assessment(request: Request, disease_id: str, compound_id: str, exclude: str = ""):
        """Explain one pair with exact model terms and complete supported ranks."""
        return current(request).engine.assessment(
            disease_id, compound_id, parse_exclusions(exclude)
        )

    @application.get(
        "/api/evidence/{disease_id}/{compound_id}",
        response_model=EvidenceResponse,
        tags=["Evidence"],
    )
    def evidence(
        request: Request,
        disease_id: str,
        compound_id: str,
        exclude: str = "",
        limit: Annotated[int, Query(ge=1, le=30)] = 12,
    ):
        return current(request).evidence(disease_id, compound_id, parse_exclusions(exclude), limit)

    @application.post("/api/challenge", response_model=ChallengeResponse, tags=["Evidence"])
    def challenge(request: Request, payload: ChallengeRequest):
        return current(request).engine.challenge(
            payload.disease_id, [item.value for item in payload.exclude], payload.limit
        )

    @application.get("/api/similar/{compound_id}", tags=["Graph algorithms"])
    def similar(
        request: Request,
        compound_id: str,
        limit: Limit = 10,
        algorithm: Literal["cypher", "gds"] = "cypher",
    ) -> dict:
        return current(request).similar(compound_id, limit, algorithm)

    @application.get("/api/algorithms/{disease_id}", tags=["Graph algorithms"])
    def algorithms(request: Request, disease_id: str, limit: Limit = 10) -> dict:
        return current(request).algorithms(disease_id, limit)

    @application.get("/api/evaluation", tags=["Reproducibility"])
    def evaluation(request: Request) -> dict:
        try:
            result = current(request).engine.evaluation()
        except FileNotFoundError as error:
            raise HTTPException(
                503, "Run make evaluate to generate the benchmark report"
            ) from error
        if not result:
            raise HTTPException(503, "Run make evaluate to generate the benchmark report")
        return result

    @application.get("/api/provenance", tags=["Reproducibility"])
    def provenance(request: Request) -> dict:
        return current(request).engine.provenance()

    @application.post("/api/agent", response_model=AgentResponse, tags=["Agent"])
    def investigate(request: Request, payload: AgentRequest):
        return request.app.state.agent.investigate(
            payload.question,
            payload.disease_id,
            [item.value for item in payload.exclude],
            compound_id=payload.compound_id,
        )

    application.include_router(audit_router)

    frontend = Path(__file__).resolve().parents[1] / "frontend"
    if (frontend / "index.html").exists():
        application.mount("/", StaticFiles(directory=frontend, html=True), name="frontend")
    return application


app = create_app()
