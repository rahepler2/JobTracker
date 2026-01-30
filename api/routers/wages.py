"""
Wages API router.
"""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from api.models import FacetCount, WageByLocation, WageSearchResult
from src.typesense_loader import TypesenseLoader

router = APIRouter(prefix="/wages", tags=["Wages"])

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
    response_model=WageSearchResult,
    summary="Search wage data by location",
    description="Search wage data across states and metro areas",
)
def search_wages(
    q: str = Query(default="*", description="Search query"),
    soc_code: Optional[str] = Query(default=None, description="Filter by SOC code"),
    area_type: Optional[str] = Query(
        default=None,
        description="Filter by area type: state or metro",
    ),
    state_code: Optional[str] = Query(default=None, description="Filter by state code"),
    min_wage: Optional[float] = Query(default=None, description="Minimum annual median wage"),
    max_wage: Optional[float] = Query(default=None, description="Maximum annual median wage"),
    sort_by: str = Query(
        default="annual_median_wage:desc",
        description="Sort field and order",
    ),
    per_page: int = Query(default=50, ge=1, le=250, description="Results per page"),
    page: int = Query(default=1, ge=1, description="Page number"),
):
    """
    Search wage data by location.

    Filter by:
    - Occupation (SOC code)
    - Area type (state or metro)
    - State code
    - Wage range

    Returns wage data with location quotients and percentiles.
    """
    try:
        results = loader.search_wages_by_location(
            query=q,
            soc_code=soc_code,
            area_type=area_type,
            state_code=state_code,
            sort_by=sort_by,
            per_page=per_page,
            page=page,
        )

        wages = []
        for hit in results.get("hits", []):
            doc = hit["document"]

            # Apply additional wage filters
            median_wage = doc.get("annual_median_wage", 0)
            if min_wage and median_wage < min_wage:
                continue
            if max_wage and median_wage > max_wage:
                continue

            wages.append(WageByLocation(**doc))

        facets = _parse_facets(results.get("facet_counts", []))

        return WageSearchResult(
            found=results.get("found", 0),
            page=page,
            per_page=per_page,
            wages=wages,
            facets=facets,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/by-occupation/{soc_code}",
    response_model=WageSearchResult,
    summary="Get wages by occupation",
    description="Get all location-based wage data for an occupation",
)
def get_wages_by_occupation(
    soc_code: str,
    area_type: Optional[str] = Query(
        default=None,
        description="Filter by area type: state or metro",
    ),
    sort_by: str = Query(
        default="annual_median_wage:desc",
        description="Sort field",
    ),
    per_page: int = Query(default=100, ge=1, le=250),
    page: int = Query(default=1, ge=1),
):
    """
    Get wage data for an occupation across all locations.

    Returns state and metro area wage data including:
    - Employment and concentration
    - Hourly and annual wages
    - Wage percentiles
    """
    try:
        results = loader.search_wages_by_location(
            query="*",
            soc_code=soc_code,
            area_type=area_type,
            sort_by=sort_by,
            per_page=per_page,
            page=page,
        )

        wages = [WageByLocation(**hit["document"]) for hit in results.get("hits", [])]
        facets = _parse_facets(results.get("facet_counts", []))

        return WageSearchResult(
            found=results.get("found", 0),
            page=page,
            per_page=per_page,
            wages=wages,
            facets=facets,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/by-state/{state_code}",
    response_model=WageSearchResult,
    summary="Get wages by state",
    description="Get wage data for all occupations in a state",
)
def get_wages_by_state(
    state_code: str,
    q: str = Query(default="*", description="Search occupation titles"),
    min_wage: Optional[float] = Query(default=None, description="Minimum annual median wage"),
    sort_by: str = Query(
        default="annual_median_wage:desc",
        description="Sort field",
    ),
    per_page: int = Query(default=50, ge=1, le=250),
    page: int = Query(default=1, ge=1),
):
    """
    Get wage data for all occupations in a state.

    Filter by:
    - Occupation search term
    - Minimum wage

    Useful for:
    - State-level career exploration
    - Comparing opportunities across occupations
    """
    try:
        results = loader.search_wages_by_location(
            query=q,
            state_code=state_code,
            area_type="state",
            sort_by=sort_by,
            per_page=per_page,
            page=page,
        )

        wages = []
        for hit in results.get("hits", []):
            doc = hit["document"]
            median_wage = doc.get("annual_median_wage", 0)
            if min_wage and median_wage < min_wage:
                continue
            wages.append(WageByLocation(**doc))

        facets = _parse_facets(results.get("facet_counts", []))

        return WageSearchResult(
            found=results.get("found", 0),
            page=page,
            per_page=per_page,
            wages=wages,
            facets=facets,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/top-paying",
    response_model=WageSearchResult,
    summary="Get top paying occupations",
    description="Get highest paying occupations nationally or by location",
)
def get_top_paying(
    area_type: Optional[str] = Query(
        default="state",
        description="Area type: state or metro",
    ),
    state_code: Optional[str] = Query(default=None, description="Filter by state"),
    limit: int = Query(default=25, ge=1, le=100, description="Number of results"),
):
    """
    Get top paying occupations.

    Returns occupations sorted by median wage with:
    - Employment numbers
    - Location quotient (concentration)
    - Wage percentiles
    """
    try:
        results = loader.search_wages_by_location(
            query="*",
            area_type=area_type,
            state_code=state_code,
            sort_by="annual_median_wage:desc",
            per_page=limit,
            page=1,
        )

        wages = [WageByLocation(**hit["document"]) for hit in results.get("hits", [])]
        facets = _parse_facets(results.get("facet_counts", []))

        return WageSearchResult(
            found=results.get("found", 0),
            page=1,
            per_page=limit,
            wages=wages,
            facets=facets,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/highest-employment",
    response_model=WageSearchResult,
    summary="Get occupations with highest employment",
    description="Get occupations with the most jobs in a location",
)
def get_highest_employment(
    area_type: Optional[str] = Query(
        default="state",
        description="Area type: state or metro",
    ),
    state_code: Optional[str] = Query(default=None, description="Filter by state"),
    limit: int = Query(default=25, ge=1, le=100, description="Number of results"),
):
    """
    Get occupations with highest employment.

    Useful for understanding:
    - Job market size
    - Career opportunities by volume
    - Regional economic focus
    """
    try:
        results = loader.search_wages_by_location(
            query="*",
            area_type=area_type,
            state_code=state_code,
            sort_by="employment:desc",
            per_page=limit,
            page=1,
        )

        wages = [WageByLocation(**hit["document"]) for hit in results.get("hits", [])]
        facets = _parse_facets(results.get("facet_counts", []))

        return WageSearchResult(
            found=results.get("found", 0),
            page=1,
            per_page=limit,
            wages=wages,
            facets=facets,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/compare-states/{soc_code}",
    summary="Compare wages across states",
    description="Compare wage data for an occupation across multiple states",
)
def compare_wages_across_states(
    soc_code: str,
    states: str = Query(
        description="Comma-separated state codes (e.g., CA,TX,NY)",
    ),
):
    """
    Compare wages for an occupation across multiple states.

    Returns side-by-side comparison of:
    - Median and mean wages
    - Employment numbers
    - Location quotients
    - Wage percentiles
    """
    state_list = [s.strip().upper() for s in states.split(",")]

    if len(state_list) > 10:
        raise HTTPException(
            status_code=400,
            detail="Maximum 10 states can be compared at once",
        )

    try:
        comparisons = []

        for state_code in state_list:
            results = loader.search_wages_by_location(
                query="*",
                soc_code=soc_code,
                area_type="state",
                state_code=state_code,
                per_page=1,
                page=1,
            )

            hits = results.get("hits", [])
            if hits:
                doc = hits[0]["document"]
                comparisons.append({
                    "state_code": state_code,
                    "state_name": doc.get("area_title", ""),
                    "annual_median_wage": doc.get("annual_median_wage"),
                    "annual_mean_wage": doc.get("annual_mean_wage"),
                    "employment": doc.get("employment"),
                    "location_quotient": doc.get("location_quotient"),
                    "annual_pct_10": doc.get("annual_pct_10"),
                    "annual_pct_90": doc.get("annual_pct_90"),
                })
            else:
                comparisons.append({
                    "state_code": state_code,
                    "state_name": "Not found",
                    "annual_median_wage": None,
                })

        # Calculate statistics
        wages = [c["annual_median_wage"] for c in comparisons if c.get("annual_median_wage")]
        avg_wage = sum(wages) / len(wages) if wages else 0
        max_wage_state = max(comparisons, key=lambda x: x.get("annual_median_wage") or 0)
        min_wage_state = min(comparisons, key=lambda x: x.get("annual_median_wage") or float('inf'))

        return {
            "soc_code": soc_code,
            "states_compared": len(state_list),
            "comparisons": comparisons,
            "summary": {
                "average_median_wage": round(avg_wage, 2),
                "highest_paying_state": max_wage_state["state_code"],
                "lowest_paying_state": min_wage_state["state_code"],
                "wage_range": (
                    (max_wage_state.get("annual_median_wage") or 0)
                    - (min_wage_state.get("annual_median_wage") or 0)
                ),
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
