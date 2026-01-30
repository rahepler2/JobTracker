"""
Occupations API router.
"""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from api.models import (
    ErrorResponse,
    FacetCount,
    OccupationDetail,
    OccupationSearchResult,
    OccupationSummary,
)
from src.typesense_loader import TypesenseLoader

router = APIRouter(prefix="/occupations", tags=["Occupations"])

# Initialize loader (will be dependency injected in production)
loader = TypesenseLoader()


def _parse_facets(facet_counts: list) -> dict[str, list[FacetCount]]:
    """Parse facet counts from Typesense response."""
    facets = {}
    for facet in facet_counts:
        field = facet.get("field_name", "")
        counts = [
            FacetCount(value=c["value"], count=c["count"])
            for c in facet.get("counts", [])
        ]
        facets[field] = counts
    return facets


@router.get(
    "",
    response_model=OccupationSearchResult,
    summary="Search occupations",
    description="Search for occupations by title, description, or skills",
)
def search_occupations(
    q: str = Query(default="*", description="Search query"),
    job_zone: Optional[int] = Query(default=None, ge=1, le=5, description="Job zone filter (1-5)"),
    education_level: Optional[str] = Query(default=None, description="Education level filter"),
    bright_outlook: Optional[bool] = Query(default=None, description="Filter by bright outlook"),
    min_wage: Optional[float] = Query(default=None, description="Minimum annual median wage"),
    max_wage: Optional[float] = Query(default=None, description="Maximum annual median wage"),
    technology: Optional[str] = Query(default=None, description="Filter by technology skill"),
    skill: Optional[str] = Query(default=None, description="Filter by skill name"),
    sort_by: str = Query(
        default="national_employment:desc",
        description="Sort field and order",
    ),
    per_page: int = Query(default=20, ge=1, le=100, description="Results per page"),
    page: int = Query(default=1, ge=1, description="Page number"),
):
    """
    Search occupations with filters.

    Supports searching by:
    - Title and description
    - Required skills and technologies
    - Job characteristics (job zone, education level)
    - Wage ranges

    Returns occupation summaries with faceted counts.
    """
    # Build filter expression
    filters = []

    if job_zone is not None:
        filters.append(f"job_zone:={job_zone}")
    if education_level:
        filters.append(f"education_level:={education_level}")
    if bright_outlook is not None:
        filters.append(f"bright_outlook:={str(bright_outlook).lower()}")
    if min_wage is not None:
        filters.append(f"national_median_wage:>={min_wage}")
    if max_wage is not None:
        filters.append(f"national_median_wage:<={max_wage}")
    if technology:
        filters.append(f"technology_skills:={technology}")
    if skill:
        filters.append(f"skill_names:={skill}")

    filter_by = " && ".join(filters) if filters else None

    try:
        results = loader.search_occupations(
            query=q,
            filter_by=filter_by,
            sort_by=sort_by,
            per_page=per_page,
            page=page,
        )

        occupations = []
        for hit in results.get("hits", []):
            doc = hit["document"]
            occupations.append(
                OccupationSummary(
                    soc_code=doc.get("soc_code", ""),
                    title=doc.get("title", ""),
                    description=doc.get("description"),
                    national_employment=doc.get("national_employment"),
                    national_median_wage=doc.get("national_median_wage"),
                    job_zone=doc.get("job_zone"),
                    bright_outlook=doc.get("bright_outlook"),
                )
            )

        facets = _parse_facets(results.get("facet_counts", []))

        return OccupationSearchResult(
            found=results.get("found", 0),
            page=page,
            per_page=per_page,
            occupations=occupations,
            facets=facets,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/{soc_code}",
    response_model=OccupationDetail,
    responses={404: {"model": ErrorResponse}},
    summary="Get occupation by SOC code",
    description="Get detailed information for a specific occupation",
)
def get_occupation(soc_code: str):
    """
    Get detailed occupation information by SOC code.

    Returns complete occupation data including:
    - Employment statistics
    - Wage information (mean, median, percentiles)
    - Job characteristics (job zone, education, experience)
    - Skills, knowledge, and abilities with importance ratings
    - Technology skills and tasks
    """
    try:
        doc = loader.get_document("occupations", soc_code)

        if doc is None:
            raise HTTPException(
                status_code=404,
                detail=f"Occupation with SOC code {soc_code} not found",
            )

        return OccupationDetail(**doc)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/{soc_code}/skills",
    summary="Get skills for occupation",
    description="Get skills, knowledge, and abilities for an occupation",
)
def get_occupation_skills(
    soc_code: str,
    skill_type: Optional[str] = Query(
        default=None,
        description="Filter by type: skill, knowledge, or ability",
    ),
    min_importance: Optional[float] = Query(
        default=None,
        ge=0,
        le=5,
        description="Minimum importance score",
    ),
):
    """
    Get skills, knowledge areas, and abilities for an occupation.

    Skills are returned with importance (1-5) and level (0-7) ratings.
    """
    try:
        doc = loader.get_document("occupations", soc_code)

        if doc is None:
            raise HTTPException(
                status_code=404,
                detail=f"Occupation with SOC code {soc_code} not found",
            )

        result = {}

        if skill_type is None or skill_type == "skill":
            skills = doc.get("skills", [])
            if min_importance:
                skills = [s for s in skills if s.get("importance", 0) >= min_importance]
            result["skills"] = skills

        if skill_type is None or skill_type == "knowledge":
            knowledge = doc.get("knowledge_areas", [])
            if min_importance:
                knowledge = [k for k in knowledge if k.get("importance", 0) >= min_importance]
            result["knowledge"] = knowledge

        if skill_type is None or skill_type == "ability":
            abilities = doc.get("abilities", [])
            if min_importance:
                abilities = [a for a in abilities if a.get("importance", 0) >= min_importance]
            result["abilities"] = abilities

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/{soc_code}/technologies",
    summary="Get technologies for occupation",
    description="Get technology skills and tools used in an occupation",
)
def get_occupation_technologies(soc_code: str):
    """
    Get technology skills for an occupation.

    Returns lists of:
    - All technology skills (software, tools, equipment)
    - Hot technologies (in-demand tools)
    """
    try:
        doc = loader.get_document("occupations", soc_code)

        if doc is None:
            raise HTTPException(
                status_code=404,
                detail=f"Occupation with SOC code {soc_code} not found",
            )

        return {
            "soc_code": soc_code,
            "title": doc.get("title", ""),
            "technology_skills": doc.get("technology_skills", []),
            "hot_technologies": doc.get("hot_technologies", []),
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/by-skill/{skill_name}",
    response_model=OccupationSearchResult,
    summary="Find occupations by skill",
    description="Find all occupations that require a specific skill",
)
def find_by_skill(
    skill_name: str,
    per_page: int = Query(default=20, ge=1, le=100),
    page: int = Query(default=1, ge=1),
):
    """
    Find occupations that require a specific skill.

    Searches across:
    - Skills
    - Knowledge areas
    - Abilities
    - Technology skills
    """
    try:
        results = loader.search_occupations(
            query=skill_name,
            sort_by="national_employment:desc",
            per_page=per_page,
            page=page,
        )

        occupations = []
        for hit in results.get("hits", []):
            doc = hit["document"]
            occupations.append(
                OccupationSummary(
                    soc_code=doc.get("soc_code", ""),
                    title=doc.get("title", ""),
                    description=doc.get("description"),
                    national_employment=doc.get("national_employment"),
                    national_median_wage=doc.get("national_median_wage"),
                    job_zone=doc.get("job_zone"),
                    bright_outlook=doc.get("bright_outlook"),
                )
            )

        facets = _parse_facets(results.get("facet_counts", []))

        return OccupationSearchResult(
            found=results.get("found", 0),
            page=page,
            per_page=per_page,
            occupations=occupations,
            facets=facets,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/compare/{soc_code_1}/{soc_code_2}",
    summary="Compare two occupations",
    description="Compare two occupations side by side",
)
def compare_occupations(soc_code_1: str, soc_code_2: str):
    """
    Compare two occupations side by side.

    Returns comparison of:
    - Wages and employment
    - Job requirements
    - Skills overlap and differences
    """
    try:
        doc1 = loader.get_document("occupations", soc_code_1)
        doc2 = loader.get_document("occupations", soc_code_2)

        if doc1 is None:
            raise HTTPException(
                status_code=404,
                detail=f"Occupation {soc_code_1} not found",
            )
        if doc2 is None:
            raise HTTPException(
                status_code=404,
                detail=f"Occupation {soc_code_2} not found",
            )

        # Find skill overlaps
        skills1 = set(doc1.get("skill_names", []))
        skills2 = set(doc2.get("skill_names", []))
        shared_skills = list(skills1 & skills2)
        unique_to_1 = list(skills1 - skills2)
        unique_to_2 = list(skills2 - skills1)

        # Find technology overlaps
        tech1 = set(doc1.get("technology_skills", []))
        tech2 = set(doc2.get("technology_skills", []))
        shared_tech = list(tech1 & tech2)

        return {
            "occupation_1": {
                "soc_code": doc1.get("soc_code"),
                "title": doc1.get("title"),
                "national_median_wage": doc1.get("national_median_wage"),
                "national_employment": doc1.get("national_employment"),
                "job_zone": doc1.get("job_zone"),
                "education_level": doc1.get("education_level"),
            },
            "occupation_2": {
                "soc_code": doc2.get("soc_code"),
                "title": doc2.get("title"),
                "national_median_wage": doc2.get("national_median_wage"),
                "national_employment": doc2.get("national_employment"),
                "job_zone": doc2.get("job_zone"),
                "education_level": doc2.get("education_level"),
            },
            "skill_comparison": {
                "shared_skills": shared_skills,
                "unique_to_occupation_1": unique_to_1,
                "unique_to_occupation_2": unique_to_2,
                "overlap_percentage": (
                    len(shared_skills) / max(len(skills1 | skills2), 1) * 100
                ),
            },
            "shared_technologies": shared_tech,
            "wage_difference": (
                (doc1.get("national_median_wage") or 0)
                - (doc2.get("national_median_wage") or 0)
            ),
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
