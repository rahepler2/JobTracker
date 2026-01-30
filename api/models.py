"""
Pydantic models for the JobTracker API.
"""

from typing import Any, Optional

from pydantic import BaseModel, Field


# Skill models
class SkillBase(BaseModel):
    """Base skill model."""

    id: str
    name: str
    description: str = ""
    importance: float = Field(ge=0, le=5)
    level: float = Field(default=0, ge=0, le=7)
    category: str = "skill"


class SkillSummary(BaseModel):
    """Summary skill info for occupation results."""

    name: str
    importance: float


# Occupation models
class OccupationBase(BaseModel):
    """Base occupation model."""

    soc_code: str
    title: str
    description: Optional[str] = None


class OccupationSummary(OccupationBase):
    """Summary occupation info."""

    national_employment: Optional[int] = None
    national_median_wage: Optional[float] = None
    job_zone: Optional[int] = None
    bright_outlook: Optional[bool] = None


class OccupationDetail(OccupationBase):
    """Detailed occupation with all fields."""

    onet_code: Optional[str] = None
    occupation_group: str = "detailed"

    # Employment
    national_employment: Optional[int] = None

    # Wages
    national_mean_wage: Optional[float] = None
    national_median_wage: Optional[float] = None
    hourly_mean_wage: Optional[float] = None
    hourly_median_wage: Optional[float] = None

    # Wage percentiles
    wage_pct_10: Optional[float] = None
    wage_pct_25: Optional[float] = None
    wage_pct_75: Optional[float] = None
    wage_pct_90: Optional[float] = None

    # Job characteristics
    job_zone: Optional[int] = None
    education_level: Optional[str] = None
    experience_required: Optional[str] = None
    bright_outlook: Optional[bool] = None

    # Skills and competencies
    skills: list[dict[str, Any]] = Field(default_factory=list)
    knowledge_areas: list[dict[str, Any]] = Field(default_factory=list)
    abilities: list[dict[str, Any]] = Field(default_factory=list)
    technology_skills: list[str] = Field(default_factory=list)
    hot_technologies: list[str] = Field(default_factory=list)
    tasks: list[str] = Field(default_factory=list)

    # Facet arrays
    skill_names: list[str] = Field(default_factory=list)
    knowledge_names: list[str] = Field(default_factory=list)
    ability_names: list[str] = Field(default_factory=list)

    last_updated: Optional[int] = None


# Wage by location models
class WageByLocation(BaseModel):
    """Wage data for a specific location."""

    soc_code: str
    occupation_title: str
    area_type: str
    area_code: str
    area_title: str
    state_code: Optional[str] = None
    state_name: Optional[str] = None

    employment: Optional[int] = None
    employment_per_1000: Optional[float] = None
    location_quotient: Optional[float] = None

    hourly_mean_wage: Optional[float] = None
    hourly_median_wage: Optional[float] = None
    annual_mean_wage: Optional[float] = None
    annual_median_wage: Optional[float] = None

    annual_pct_10: Optional[float] = None
    annual_pct_25: Optional[float] = None
    annual_pct_75: Optional[float] = None
    annual_pct_90: Optional[float] = None

    data_year: Optional[int] = None
    last_updated: Optional[int] = None


# Skill models
class SkillDetail(BaseModel):
    """Detailed skill information."""

    skill_id: str
    skill_name: str
    skill_type: str
    description: str
    category: str
    occupation_count: int
    avg_importance: float
    avg_level: float
    related_occupations: list[dict[str, Any]] = Field(default_factory=list)
    last_updated: Optional[int] = None


# Search and response models
class SearchQuery(BaseModel):
    """Search query parameters."""

    q: str = Field(description="Search query")
    filter_by: Optional[str] = Field(default=None, description="Filter expression")
    sort_by: Optional[str] = Field(default=None, description="Sort expression")
    per_page: int = Field(default=10, ge=1, le=100)
    page: int = Field(default=1, ge=1)


class FacetCount(BaseModel):
    """Facet count for a value."""

    value: str
    count: int


class FacetResult(BaseModel):
    """Facet results for a field."""

    field_name: str
    counts: list[FacetCount]


class SearchResult(BaseModel):
    """Generic search result."""

    found: int
    page: int
    per_page: int
    hits: list[dict[str, Any]]
    facet_counts: list[FacetResult] = Field(default_factory=list)


class OccupationSearchResult(BaseModel):
    """Occupation search results."""

    found: int
    page: int
    per_page: int
    occupations: list[OccupationSummary]
    facets: dict[str, list[FacetCount]] = Field(default_factory=dict)


class WageSearchResult(BaseModel):
    """Wage search results."""

    found: int
    page: int
    per_page: int
    wages: list[WageByLocation]
    facets: dict[str, list[FacetCount]] = Field(default_factory=dict)


class SkillSearchResult(BaseModel):
    """Skill search results."""

    found: int
    page: int
    per_page: int
    skills: list[SkillDetail]
    facets: dict[str, list[FacetCount]] = Field(default_factory=dict)


# Health and status models
class HealthStatus(BaseModel):
    """API health status."""

    status: str
    typesense_connected: bool
    version: str


class CollectionStats(BaseModel):
    """Statistics for a collection."""

    name: str
    num_documents: int
    num_fields: int = 0


class PipelineStatus(BaseModel):
    """Pipeline status information."""

    typesense_healthy: bool
    collections: dict[str, CollectionStats]
    data_year: int
    last_check: str


# Error models
class ErrorResponse(BaseModel):
    """Error response."""

    detail: str
    code: Optional[str] = None
