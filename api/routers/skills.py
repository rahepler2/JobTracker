"""
Skills API router.
"""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from api.models import FacetCount, SkillDetail, SkillSearchResult
from src.typesense_loader import TypesenseLoader

router = APIRouter(prefix="/skills", tags=["Skills"])

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
    response_model=SkillSearchResult,
    summary="Search skills",
    description="Search for skills, knowledge areas, or abilities",
)
def search_skills(
    q: str = Query(default="*", description="Search query"),
    skill_type: Optional[str] = Query(
        default=None,
        description="Filter by type: skill, knowledge, or ability",
    ),
    category: Optional[str] = Query(default=None, description="Filter by category"),
    min_occupation_count: Optional[int] = Query(
        default=None,
        description="Minimum number of occupations using this skill",
    ),
    sort_by: str = Query(
        default="occupation_count:desc",
        description="Sort field and order",
    ),
    per_page: int = Query(default=20, ge=1, le=100, description="Results per page"),
    page: int = Query(default=1, ge=1, description="Page number"),
):
    """
    Search skills, knowledge areas, and abilities.

    Filter by:
    - Skill type (skill, knowledge, ability)
    - Category
    - Minimum occupation count

    Returns skills with:
    - Average importance and level across occupations
    - Related occupations
    """
    try:
        results = loader.search_skills(
            query=q,
            skill_type=skill_type,
            category=category,
            per_page=per_page,
            page=page,
        )

        skills = []
        for hit in results.get("hits", []):
            doc = hit["document"]

            # Apply occupation count filter
            occ_count = doc.get("occupation_count", 0)
            if min_occupation_count and occ_count < min_occupation_count:
                continue

            skills.append(SkillDetail(**doc))

        facets = _parse_facets(results.get("facet_counts", []))

        return SkillSearchResult(
            found=results.get("found", 0),
            page=page,
            per_page=per_page,
            skills=skills,
            facets=facets,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/{skill_id}",
    response_model=SkillDetail,
    summary="Get skill by ID",
    description="Get detailed information for a specific skill",
)
def get_skill(skill_id: str):
    """
    Get detailed skill information by O*NET skill ID.

    Returns:
    - Skill name and description
    - Type and category
    - Related occupations with importance ratings
    - Average importance and level scores
    """
    try:
        doc = loader.get_document("skills", skill_id)

        if doc is None:
            raise HTTPException(
                status_code=404,
                detail=f"Skill with ID {skill_id} not found",
            )

        return SkillDetail(**doc)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/type/{skill_type}",
    response_model=SkillSearchResult,
    summary="Get skills by type",
    description="Get all skills of a specific type",
)
def get_skills_by_type(
    skill_type: str,
    sort_by: str = Query(
        default="occupation_count:desc",
        description="Sort field",
    ),
    per_page: int = Query(default=50, ge=1, le=100),
    page: int = Query(default=1, ge=1),
):
    """
    Get all skills of a specific type.

    Types:
    - skill: Developed capacities
    - knowledge: Sets of facts and principles
    - ability: Enduring attributes
    """
    if skill_type not in ["skill", "knowledge", "ability"]:
        raise HTTPException(
            status_code=400,
            detail="skill_type must be 'skill', 'knowledge', or 'ability'",
        )

    try:
        results = loader.search_skills(
            query="*",
            skill_type=skill_type,
            per_page=per_page,
            page=page,
        )

        skills = [SkillDetail(**hit["document"]) for hit in results.get("hits", [])]
        facets = _parse_facets(results.get("facet_counts", []))

        return SkillSearchResult(
            found=results.get("found", 0),
            page=page,
            per_page=per_page,
            skills=skills,
            facets=facets,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/most-common",
    response_model=SkillSearchResult,
    summary="Get most common skills",
    description="Get skills required by the most occupations",
)
def get_most_common_skills(
    skill_type: Optional[str] = Query(
        default=None,
        description="Filter by type: skill, knowledge, or ability",
    ),
    limit: int = Query(default=25, ge=1, le=100, description="Number of results"),
):
    """
    Get the most common skills across all occupations.

    These are foundational skills required by many occupations,
    useful for career planning and education.
    """
    try:
        results = loader.search_skills(
            query="*",
            skill_type=skill_type,
            per_page=limit,
            page=1,
        )

        skills = [SkillDetail(**hit["document"]) for hit in results.get("hits", [])]
        facets = _parse_facets(results.get("facet_counts", []))

        return SkillSearchResult(
            found=results.get("found", 0),
            page=1,
            per_page=limit,
            skills=skills,
            facets=facets,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/highest-importance",
    response_model=SkillSearchResult,
    summary="Get skills with highest importance",
    description="Get skills with highest average importance rating",
)
def get_highest_importance_skills(
    skill_type: Optional[str] = Query(
        default=None,
        description="Filter by type",
    ),
    limit: int = Query(default=25, ge=1, le=100),
):
    """
    Get skills with highest average importance ratings.

    Importance indicates how critical the skill is for
    job performance across occupations.
    """
    try:
        results = loader.search(
            collection_name="skills",
            query="*",
            query_by="skill_name,description",
            filter_by=f"skill_type:={skill_type}" if skill_type else None,
            sort_by="avg_importance:desc",
            per_page=limit,
            page=1,
        )

        skills = [SkillDetail(**hit["document"]) for hit in results.get("hits", [])]
        facets = _parse_facets(results.get("facet_counts", []))

        return SkillSearchResult(
            found=results.get("found", 0),
            page=1,
            per_page=limit,
            skills=skills,
            facets=facets,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/for-occupation/{soc_code}",
    summary="Get skills for occupation",
    description="Get all skills required for an occupation with importance ratings",
)
def get_skills_for_occupation(
    soc_code: str,
    min_importance: Optional[float] = Query(
        default=None,
        ge=1,
        le=5,
        description="Minimum importance score (1-5)",
    ),
):
    """
    Get skills required for a specific occupation.

    Returns skills, knowledge areas, and abilities
    with importance and level ratings.
    """
    try:
        # Get occupation document
        occ_doc = loader.get_document("occupations", soc_code)

        if occ_doc is None:
            raise HTTPException(
                status_code=404,
                detail=f"Occupation {soc_code} not found",
            )

        def filter_by_importance(items: list) -> list:
            if min_importance is None:
                return items
            return [i for i in items if i.get("importance", 0) >= min_importance]

        return {
            "soc_code": soc_code,
            "title": occ_doc.get("title", ""),
            "skills": filter_by_importance(occ_doc.get("skills", [])),
            "knowledge": filter_by_importance(occ_doc.get("knowledge_areas", [])),
            "abilities": filter_by_importance(occ_doc.get("abilities", [])),
            "technology_skills": occ_doc.get("technology_skills", []),
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/gap-analysis",
    summary="Analyze skill gaps between occupations",
    description="Find skills needed to transition between occupations",
)
def skill_gap_analysis(
    from_soc_code: str = Query(description="Current occupation SOC code"),
    to_soc_code: str = Query(description="Target occupation SOC code"),
):
    """
    Analyze skill gaps between two occupations.

    Useful for career transition planning:
    - Identifies skills to develop
    - Shows transferable skills
    - Highlights knowledge gaps
    """
    try:
        from_doc = loader.get_document("occupations", from_soc_code)
        to_doc = loader.get_document("occupations", to_soc_code)

        if from_doc is None:
            raise HTTPException(
                status_code=404,
                detail=f"Occupation {from_soc_code} not found",
            )
        if to_doc is None:
            raise HTTPException(
                status_code=404,
                detail=f"Occupation {to_soc_code} not found",
            )

        # Extract skill sets
        from_skills = {s["name"]: s for s in from_doc.get("skills", [])}
        to_skills = {s["name"]: s for s in to_doc.get("skills", [])}

        from_knowledge = {k["name"]: k for k in from_doc.get("knowledge_areas", [])}
        to_knowledge = {k["name"]: k for k in to_doc.get("knowledge_areas", [])}

        from_tech = set(from_doc.get("technology_skills", []))
        to_tech = set(to_doc.get("technology_skills", []))

        # Find gaps
        skill_gaps = []
        for name, skill in to_skills.items():
            if name not in from_skills:
                skill_gaps.append({
                    "name": name,
                    "importance": skill.get("importance", 0),
                    "type": "new_skill_needed",
                })
            else:
                # Check if target requires higher level
                from_level = from_skills[name].get("level", 0)
                to_level = skill.get("level", 0)
                if to_level > from_level:
                    skill_gaps.append({
                        "name": name,
                        "importance": skill.get("importance", 0),
                        "current_level": from_level,
                        "required_level": to_level,
                        "type": "skill_upgrade_needed",
                    })

        knowledge_gaps = []
        for name, knowledge in to_knowledge.items():
            if name not in from_knowledge:
                knowledge_gaps.append({
                    "name": name,
                    "importance": knowledge.get("importance", 0),
                })

        tech_gaps = list(to_tech - from_tech)
        transferable_tech = list(from_tech & to_tech)

        # Calculate gap score (higher = more training needed)
        gap_score = (
            len(skill_gaps) * 2
            + len(knowledge_gaps)
            + len(tech_gaps) * 0.5
        )

        return {
            "from_occupation": {
                "soc_code": from_soc_code,
                "title": from_doc.get("title", ""),
            },
            "to_occupation": {
                "soc_code": to_soc_code,
                "title": to_doc.get("title", ""),
            },
            "skill_gaps": sorted(
                skill_gaps, key=lambda x: x.get("importance", 0), reverse=True
            ),
            "knowledge_gaps": sorted(
                knowledge_gaps, key=lambda x: x.get("importance", 0), reverse=True
            ),
            "technology_gaps": tech_gaps,
            "transferable_skills": list(set(from_skills.keys()) & set(to_skills.keys())),
            "transferable_technologies": transferable_tech,
            "gap_score": round(gap_score, 1),
            "transition_difficulty": (
                "Easy" if gap_score < 5
                else "Moderate" if gap_score < 15
                else "Challenging" if gap_score < 30
                else "Significant training required"
            ),
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
