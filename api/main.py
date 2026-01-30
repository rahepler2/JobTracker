"""
JobTracker API - Main FastAPI Application.

A comprehensive REST API for accessing BLS occupational data,
wages, and O*NET skills information.
"""

import logging
from contextlib import asynccontextmanager
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.models import CollectionStats, HealthStatus, PipelineStatus
from api.routers import occupations_router, skills_router, wages_router
from src.config import get_settings
from src.pipeline import OccupationalDataPipeline
from src.typesense_loader import TypesenseLoader

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Settings
settings = get_settings()

# Global instances
loader: TypesenseLoader | None = None
pipeline: OccupationalDataPipeline | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    global loader, pipeline

    # Startup
    logger.info("Starting JobTracker API")
    loader = TypesenseLoader()
    pipeline = OccupationalDataPipeline()

    # Check Typesense connection
    if loader.health_check():
        logger.info("Connected to Typesense")
    else:
        logger.warning("Typesense connection failed - some features may be unavailable")

    yield

    # Shutdown
    logger.info("Shutting down JobTracker API")


# Create FastAPI application
app = FastAPI(
    title=settings.api.title,
    description="""
## JobTracker API

A comprehensive REST API for accessing U.S. Bureau of Labor Statistics (BLS)
occupational data combined with O*NET skills and competency information.

### Features

- **Occupations**: Search and explore 800+ occupations with employment and wage data
- **Skills**: Find skills, knowledge areas, and abilities required for occupations
- **Wages**: Compare wages across states and metropolitan areas
- **Career Tools**: Compare occupations and analyze skill gaps for career transitions

### Data Sources

- **BLS OEWS**: Employment counts and wage statistics
- **O*NET**: Skills, abilities, knowledge, and technology requirements

### Use Cases

- Career exploration and planning
- Education-to-career pathway mapping
- Labor market analysis
- Workforce development
- Microcredentialing alignment
    """,
    version=settings.api.version,
    docs_url=settings.api.docs_url,
    redoc_url=settings.api.redoc_url,
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(occupations_router)
app.include_router(wages_router)
app.include_router(skills_router)


# Root endpoints
@app.get("/", tags=["Root"])
def root() -> dict[str, Any]:
    """API root - returns basic information."""
    return {
        "name": "JobTracker API",
        "version": settings.api.version,
        "description": "BLS Jobs Data API - Access occupational data, wages, and skills",
        "documentation": "/docs",
        "endpoints": {
            "occupations": "/occupations",
            "wages": "/wages",
            "skills": "/skills",
            "health": "/health",
            "status": "/status",
        },
    }


@app.get("/health", response_model=HealthStatus, tags=["Health"])
def health_check() -> HealthStatus:
    """Check API health status."""
    typesense_connected = False
    if loader:
        typesense_connected = loader.health_check()

    return HealthStatus(
        status="healthy" if typesense_connected else "degraded",
        typesense_connected=typesense_connected,
        version=settings.api.version,
    )


@app.get("/status", response_model=PipelineStatus, tags=["Health"])
def pipeline_status() -> PipelineStatus:
    """Get detailed pipeline and data status."""
    if not pipeline:
        raise HTTPException(status_code=503, detail="Pipeline not initialized")

    status = pipeline.get_pipeline_status()

    collections = {}
    for name, stats in status.get("collections", {}).items():
        if isinstance(stats, dict) and "error" not in stats:
            collections[name] = CollectionStats(
                name=stats.get("name", name),
                num_documents=stats.get("num_documents", 0),
                num_fields=stats.get("num_fields", 0),
            )
        else:
            collections[name] = CollectionStats(name=name, num_documents=0)

    return PipelineStatus(
        typesense_healthy=status.get("typesense_healthy", False),
        collections=collections,
        data_year=status.get("data_year", settings.data.year),
        last_check=status.get("last_check", ""),
    )


@app.get("/stats", tags=["Health"])
def collection_stats() -> dict[str, Any]:
    """Get collection statistics."""
    if not loader:
        raise HTTPException(status_code=503, detail="Loader not initialized")

    return loader.get_all_stats()


# Admin endpoints
@app.post("/admin/refresh", tags=["Admin"])
def trigger_refresh(
    drop_existing: bool = False,
    include_onet: bool = True,
    include_location_wages: bool = True,
) -> dict[str, Any]:
    """
    Trigger a data refresh.

    **Warning**: This operation can take significant time and resources.
    """
    if not pipeline:
        raise HTTPException(status_code=503, detail="Pipeline not initialized")

    try:
        results = pipeline.run_full_refresh(
            drop_existing=drop_existing,
            include_onet=include_onet,
            include_location_wages=include_location_wages,
        )
        return {"status": "completed", "results": results}
    except Exception as e:
        logger.error(f"Refresh failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/admin/create-collections", tags=["Admin"])
def create_collections(drop_existing: bool = False) -> dict[str, str]:
    """Create Typesense collections."""
    if not loader:
        raise HTTPException(status_code=503, detail="Loader not initialized")

    try:
        loader.create_all_collections(drop_existing=drop_existing)
        return {"status": "collections created"}
    except Exception as e:
        logger.error(f"Collection creation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Error handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """Handle HTTP exceptions."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """Handle general exceptions."""
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


def run():
    """Run the API server."""
    uvicorn.run(
        "api.main:app",
        host=settings.api.host,
        port=settings.api.port,
        reload=settings.api.debug,
    )


if __name__ == "__main__":
    run()
