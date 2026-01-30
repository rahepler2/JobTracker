"""
JobTracker MCP Server.

A Model Context Protocol (MCP) server that provides AI assistants
with access to BLS occupational data, wages, and skills information.

This enables AI assistants to:
- Search for occupations by title, skills, or requirements
- Look up wage data by location
- Analyze skill requirements and career transitions
- Compare occupations and identify skill gaps
"""

import asyncio
import json
import logging
from typing import Any, Sequence

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    GetPromptResult,
    Prompt,
    PromptArgument,
    PromptMessage,
    Resource,
    TextContent,
    Tool,
)

from src.config import get_settings
from src.typesense_loader import TypesenseLoader

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize server and loader
app = Server("jobtracker")
settings = get_settings()
loader = TypesenseLoader()


# ============================================================================
# Tools
# ============================================================================


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools for querying occupational data."""
    return [
        Tool(
            name="search_occupations",
            description="""Search for occupations by title, description, or skills.
            Returns occupation details including employment numbers, wages, and required skills.
            Useful for career exploration and finding jobs that match certain criteria.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (title, skill, or keyword)",
                    },
                    "job_zone": {
                        "type": "integer",
                        "description": "Job zone filter (1-5, where 5 requires most preparation)",
                        "minimum": 1,
                        "maximum": 5,
                    },
                    "min_wage": {
                        "type": "number",
                        "description": "Minimum annual median wage",
                    },
                    "bright_outlook": {
                        "type": "boolean",
                        "description": "Filter to occupations with bright outlook (growing fields)",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum results to return (default 10)",
                        "default": 10,
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="get_occupation_details",
            description="""Get detailed information about a specific occupation by SOC code.
            Returns comprehensive data including wages, employment, skills, knowledge areas,
            abilities, technology skills, and typical tasks.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "soc_code": {
                        "type": "string",
                        "description": "SOC occupation code (e.g., '15-1252' for Software Developers)",
                    },
                },
                "required": ["soc_code"],
            },
        ),
        Tool(
            name="get_wages_by_location",
            description="""Get wage data for an occupation across different locations.
            Returns state or metro area wage data including median, mean, and percentile wages.
            Useful for comparing earning potential in different geographic areas.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "soc_code": {
                        "type": "string",
                        "description": "SOC occupation code",
                    },
                    "area_type": {
                        "type": "string",
                        "enum": ["state", "metro"],
                        "description": "Type of geographic area",
                        "default": "state",
                    },
                    "state_code": {
                        "type": "string",
                        "description": "Filter by specific state code (e.g., 'CA', 'TX')",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum results (default 20)",
                        "default": 20,
                    },
                },
                "required": ["soc_code"],
            },
        ),
        Tool(
            name="search_skills",
            description="""Search for skills, knowledge areas, or abilities.
            Returns skills with their importance ratings and related occupations.
            Useful for understanding what skills are in demand and which careers require them.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Skill name or keyword to search",
                    },
                    "skill_type": {
                        "type": "string",
                        "enum": ["skill", "knowledge", "ability"],
                        "description": "Filter by skill type",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum results (default 10)",
                        "default": 10,
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="analyze_skill_gap",
            description="""Analyze the skill gap between two occupations.
            Identifies skills needed to transition from one career to another,
            including transferable skills and gaps that need to be filled.
            Useful for career transition planning and education guidance.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "from_soc_code": {
                        "type": "string",
                        "description": "Current occupation SOC code",
                    },
                    "to_soc_code": {
                        "type": "string",
                        "description": "Target occupation SOC code",
                    },
                },
                "required": ["from_soc_code", "to_soc_code"],
            },
        ),
        Tool(
            name="compare_occupations",
            description="""Compare two occupations side by side.
            Shows differences in wages, employment, skills, and requirements.
            Useful for career decision-making.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "soc_code_1": {
                        "type": "string",
                        "description": "First occupation SOC code",
                    },
                    "soc_code_2": {
                        "type": "string",
                        "description": "Second occupation SOC code",
                    },
                },
                "required": ["soc_code_1", "soc_code_2"],
            },
        ),
        Tool(
            name="get_top_paying_occupations",
            description="""Get the highest paying occupations overall or in a specific state.
            Returns occupations sorted by median wage with employment numbers.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "state_code": {
                        "type": "string",
                        "description": "Optional state code to filter by (e.g., 'CA')",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Number of results (default 25)",
                        "default": 25,
                    },
                },
            },
        ),
        Tool(
            name="find_occupations_by_skill",
            description="""Find occupations that require a specific skill or technology.
            Useful for exploring career options based on existing skills or interests.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "skill": {
                        "type": "string",
                        "description": "Skill or technology name (e.g., 'Python', 'Project Management')",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum results (default 15)",
                        "default": 15,
                    },
                },
                "required": ["skill"],
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> Sequence[TextContent]:
    """Execute a tool and return results."""
    try:
        if name == "search_occupations":
            result = await search_occupations(**arguments)
        elif name == "get_occupation_details":
            result = await get_occupation_details(**arguments)
        elif name == "get_wages_by_location":
            result = await get_wages_by_location(**arguments)
        elif name == "search_skills":
            result = await search_skills(**arguments)
        elif name == "analyze_skill_gap":
            result = await analyze_skill_gap(**arguments)
        elif name == "compare_occupations":
            result = await compare_occupations(**arguments)
        elif name == "get_top_paying_occupations":
            result = await get_top_paying_occupations(**arguments)
        elif name == "find_occupations_by_skill":
            result = await find_occupations_by_skill(**arguments)
        else:
            result = {"error": f"Unknown tool: {name}"}

        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    except Exception as e:
        logger.error(f"Tool {name} failed: {e}")
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]


# Tool implementations
async def search_occupations(
    query: str,
    job_zone: int | None = None,
    min_wage: float | None = None,
    bright_outlook: bool | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    """Search occupations."""
    filters = []
    if job_zone:
        filters.append(f"job_zone:={job_zone}")
    if min_wage:
        filters.append(f"national_median_wage:>={min_wage}")
    if bright_outlook is not None:
        filters.append(f"bright_outlook:={str(bright_outlook).lower()}")

    filter_by = " && ".join(filters) if filters else None

    results = loader.search_occupations(
        query=query,
        filter_by=filter_by,
        per_page=limit,
        page=1,
    )

    occupations = []
    for hit in results.get("hits", []):
        doc = hit["document"]
        occupations.append({
            "soc_code": doc.get("soc_code"),
            "title": doc.get("title"),
            "description": doc.get("description", "")[:200] + "..." if doc.get("description") else "",
            "national_employment": doc.get("national_employment"),
            "national_median_wage": doc.get("national_median_wage"),
            "job_zone": doc.get("job_zone"),
            "education_level": doc.get("education_level"),
            "bright_outlook": doc.get("bright_outlook"),
        })

    return {
        "found": results.get("found", 0),
        "occupations": occupations,
    }


async def get_occupation_details(soc_code: str) -> dict[str, Any]:
    """Get detailed occupation information."""
    doc = loader.get_document("occupations", soc_code)

    if doc is None:
        return {"error": f"Occupation {soc_code} not found"}

    # Get top skills by importance
    top_skills = sorted(
        doc.get("skills", []),
        key=lambda x: x.get("importance", 0),
        reverse=True,
    )[:10]

    return {
        "soc_code": doc.get("soc_code"),
        "title": doc.get("title"),
        "description": doc.get("description"),
        "wages": {
            "national_median": doc.get("national_median_wage"),
            "national_mean": doc.get("national_mean_wage"),
            "percentile_10": doc.get("wage_pct_10"),
            "percentile_90": doc.get("wage_pct_90"),
        },
        "employment": doc.get("national_employment"),
        "job_zone": doc.get("job_zone"),
        "education_level": doc.get("education_level"),
        "experience_required": doc.get("experience_required"),
        "bright_outlook": doc.get("bright_outlook"),
        "top_skills": [
            {"name": s["name"], "importance": s["importance"]}
            for s in top_skills
        ],
        "technology_skills": doc.get("technology_skills", [])[:15],
        "hot_technologies": doc.get("hot_technologies", []),
    }


async def get_wages_by_location(
    soc_code: str,
    area_type: str = "state",
    state_code: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Get wages by location."""
    results = loader.search_wages_by_location(
        query="*",
        soc_code=soc_code,
        area_type=area_type,
        state_code=state_code,
        sort_by="annual_median_wage:desc",
        per_page=limit,
        page=1,
    )

    wages = []
    for hit in results.get("hits", []):
        doc = hit["document"]
        wages.append({
            "area_title": doc.get("area_title"),
            "area_type": doc.get("area_type"),
            "annual_median_wage": doc.get("annual_median_wage"),
            "annual_mean_wage": doc.get("annual_mean_wage"),
            "employment": doc.get("employment"),
            "location_quotient": doc.get("location_quotient"),
        })

    return {
        "soc_code": soc_code,
        "found": results.get("found", 0),
        "wages_by_location": wages,
    }


async def search_skills(
    query: str,
    skill_type: str | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    """Search skills."""
    results = loader.search_skills(
        query=query,
        skill_type=skill_type,
        per_page=limit,
        page=1,
    )

    skills = []
    for hit in results.get("hits", []):
        doc = hit["document"]
        skills.append({
            "skill_name": doc.get("skill_name"),
            "skill_type": doc.get("skill_type"),
            "description": doc.get("description"),
            "occupation_count": doc.get("occupation_count"),
            "avg_importance": doc.get("avg_importance"),
        })

    return {
        "found": results.get("found", 0),
        "skills": skills,
    }


async def analyze_skill_gap(
    from_soc_code: str,
    to_soc_code: str,
) -> dict[str, Any]:
    """Analyze skill gaps between occupations."""
    from_doc = loader.get_document("occupations", from_soc_code)
    to_doc = loader.get_document("occupations", to_soc_code)

    if from_doc is None:
        return {"error": f"Occupation {from_soc_code} not found"}
    if to_doc is None:
        return {"error": f"Occupation {to_soc_code} not found"}

    # Extract skills
    from_skills = {s["name"]: s for s in from_doc.get("skills", [])}
    to_skills = {s["name"]: s for s in to_doc.get("skills", [])}

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

    tech_gaps = list(to_tech - from_tech)
    transferable_skills = list(set(from_skills.keys()) & set(to_skills.keys()))
    transferable_tech = list(from_tech & to_tech)

    return {
        "from_occupation": {
            "soc_code": from_soc_code,
            "title": from_doc.get("title"),
        },
        "to_occupation": {
            "soc_code": to_soc_code,
            "title": to_doc.get("title"),
        },
        "skill_gaps": sorted(skill_gaps, key=lambda x: x["importance"], reverse=True)[:10],
        "technology_gaps": tech_gaps[:15],
        "transferable_skills": transferable_skills[:10],
        "transferable_technologies": transferable_tech[:10],
        "wage_difference": (
            (to_doc.get("national_median_wage") or 0)
            - (from_doc.get("national_median_wage") or 0)
        ),
    }


async def compare_occupations(
    soc_code_1: str,
    soc_code_2: str,
) -> dict[str, Any]:
    """Compare two occupations."""
    doc1 = loader.get_document("occupations", soc_code_1)
    doc2 = loader.get_document("occupations", soc_code_2)

    if doc1 is None:
        return {"error": f"Occupation {soc_code_1} not found"}
    if doc2 is None:
        return {"error": f"Occupation {soc_code_2} not found"}

    skills1 = set(doc1.get("skill_names", []))
    skills2 = set(doc2.get("skill_names", []))

    return {
        "occupation_1": {
            "soc_code": soc_code_1,
            "title": doc1.get("title"),
            "median_wage": doc1.get("national_median_wage"),
            "employment": doc1.get("national_employment"),
            "job_zone": doc1.get("job_zone"),
            "education": doc1.get("education_level"),
        },
        "occupation_2": {
            "soc_code": soc_code_2,
            "title": doc2.get("title"),
            "median_wage": doc2.get("national_median_wage"),
            "employment": doc2.get("national_employment"),
            "job_zone": doc2.get("job_zone"),
            "education": doc2.get("education_level"),
        },
        "wage_difference": (
            (doc1.get("national_median_wage") or 0)
            - (doc2.get("national_median_wage") or 0)
        ),
        "shared_skills_count": len(skills1 & skills2),
        "skill_overlap_percentage": (
            len(skills1 & skills2) / max(len(skills1 | skills2), 1) * 100
        ),
    }


async def get_top_paying_occupations(
    state_code: str | None = None,
    limit: int = 25,
) -> dict[str, Any]:
    """Get top paying occupations."""
    if state_code:
        results = loader.search_wages_by_location(
            query="*",
            area_type="state",
            state_code=state_code,
            sort_by="annual_median_wage:desc",
            per_page=limit,
            page=1,
        )
        occupations = [
            {
                "soc_code": hit["document"].get("soc_code"),
                "title": hit["document"].get("occupation_title"),
                "annual_median_wage": hit["document"].get("annual_median_wage"),
                "employment": hit["document"].get("employment"),
            }
            for hit in results.get("hits", [])
        ]
    else:
        results = loader.search_occupations(
            query="*",
            sort_by="national_median_wage:desc",
            per_page=limit,
            page=1,
        )
        occupations = [
            {
                "soc_code": hit["document"].get("soc_code"),
                "title": hit["document"].get("title"),
                "annual_median_wage": hit["document"].get("national_median_wage"),
                "employment": hit["document"].get("national_employment"),
            }
            for hit in results.get("hits", [])
        ]

    return {
        "state": state_code or "National",
        "top_paying_occupations": occupations,
    }


async def find_occupations_by_skill(
    skill: str,
    limit: int = 15,
) -> dict[str, Any]:
    """Find occupations requiring a skill."""
    results = loader.search_occupations(
        query=skill,
        sort_by="national_employment:desc",
        per_page=limit,
        page=1,
    )

    occupations = []
    for hit in results.get("hits", []):
        doc = hit["document"]
        occupations.append({
            "soc_code": doc.get("soc_code"),
            "title": doc.get("title"),
            "national_median_wage": doc.get("national_median_wage"),
            "national_employment": doc.get("national_employment"),
            "job_zone": doc.get("job_zone"),
        })

    return {
        "skill_searched": skill,
        "found": results.get("found", 0),
        "occupations": occupations,
    }


# ============================================================================
# Resources
# ============================================================================


@app.list_resources()
async def list_resources() -> list[Resource]:
    """List available data resources."""
    return [
        Resource(
            uri="jobtracker://overview",
            name="JobTracker Data Overview",
            description="Overview of available occupational data",
            mimeType="application/json",
        ),
        Resource(
            uri="jobtracker://job-zones",
            name="Job Zone Descriptions",
            description="Descriptions of O*NET job zones (1-5)",
            mimeType="application/json",
        ),
    ]


@app.read_resource()
async def read_resource(uri: str) -> str:
    """Read a resource by URI."""
    if uri == "jobtracker://overview":
        stats = loader.get_all_stats()
        return json.dumps({
            "name": "JobTracker - BLS Occupational Data",
            "description": "Comprehensive U.S. occupational data from BLS and O*NET",
            "data_sources": {
                "BLS OEWS": "Employment and wage statistics for 800+ occupations",
                "O*NET": "Skills, knowledge, abilities, and technology requirements",
            },
            "collections": stats,
            "coverage": "National, state, and metropolitan area data",
        }, indent=2)

    elif uri == "jobtracker://job-zones":
        return json.dumps({
            "job_zones": [
                {
                    "zone": 1,
                    "name": "Little or No Preparation Needed",
                    "education": "High school diploma or less",
                    "experience": "Little or no previous work experience",
                    "training": "Short demonstration to several months",
                },
                {
                    "zone": 2,
                    "name": "Some Preparation Needed",
                    "education": "High school diploma",
                    "experience": "Some previous work experience may be helpful",
                    "training": "A few months to one year",
                },
                {
                    "zone": 3,
                    "name": "Medium Preparation Needed",
                    "education": "Vocational training or associate's degree",
                    "experience": "Previous work experience required",
                    "training": "One to two years",
                },
                {
                    "zone": 4,
                    "name": "Considerable Preparation Needed",
                    "education": "Bachelor's degree",
                    "experience": "Considerable work experience required",
                    "training": "Several years",
                },
                {
                    "zone": 5,
                    "name": "Extensive Preparation Needed",
                    "education": "Graduate or professional degree",
                    "experience": "Extensive work experience required",
                    "training": "Many years",
                },
            ]
        }, indent=2)

    return json.dumps({"error": f"Unknown resource: {uri}"})


# ============================================================================
# Prompts
# ============================================================================


@app.list_prompts()
async def list_prompts() -> list[Prompt]:
    """List available prompts."""
    return [
        Prompt(
            name="career_exploration",
            description="Explore career options based on interests or skills",
            arguments=[
                PromptArgument(
                    name="interest",
                    description="Career interest or skill area",
                    required=True,
                ),
            ],
        ),
        Prompt(
            name="career_transition",
            description="Plan a career transition between occupations",
            arguments=[
                PromptArgument(
                    name="current_occupation",
                    description="Current job title or SOC code",
                    required=True,
                ),
                PromptArgument(
                    name="target_occupation",
                    description="Target job title or SOC code",
                    required=True,
                ),
            ],
        ),
        Prompt(
            name="salary_research",
            description="Research salaries for an occupation",
            arguments=[
                PromptArgument(
                    name="occupation",
                    description="Job title or SOC code",
                    required=True,
                ),
                PromptArgument(
                    name="location",
                    description="State or city (optional)",
                    required=False,
                ),
            ],
        ),
    ]


@app.get_prompt()
async def get_prompt(name: str, arguments: dict[str, str] | None) -> GetPromptResult:
    """Get a specific prompt."""
    arguments = arguments or {}

    if name == "career_exploration":
        interest = arguments.get("interest", "technology")
        return GetPromptResult(
            description=f"Explore careers related to {interest}",
            messages=[
                PromptMessage(
                    role="user",
                    content=TextContent(
                        type="text",
                        text=f"""I'm interested in careers related to "{interest}".

Please use the JobTracker tools to:
1. Search for occupations matching this interest
2. Show me the top 5 options with their median wages and job outlook
3. Identify the key skills needed for these careers
4. Suggest which might be best based on job growth and compensation

Focus on occupations with bright outlook designations when possible.""",
                    ),
                ),
            ],
        )

    elif name == "career_transition":
        current = arguments.get("current_occupation", "")
        target = arguments.get("target_occupation", "")
        return GetPromptResult(
            description=f"Plan transition from {current} to {target}",
            messages=[
                PromptMessage(
                    role="user",
                    content=TextContent(
                        type="text",
                        text=f"""I want to transition from "{current}" to "{target}".

Please use the JobTracker tools to:
1. Get details on both occupations
2. Analyze the skill gap between them
3. Identify what skills I need to develop
4. Compare the wage and employment outlook
5. Suggest a learning path for the transition

Provide practical recommendations for making this career change.""",
                    ),
                ),
            ],
        )

    elif name == "salary_research":
        occupation = arguments.get("occupation", "")
        location = arguments.get("location")
        location_text = f" in {location}" if location else " across different locations"
        return GetPromptResult(
            description=f"Research salaries for {occupation}",
            messages=[
                PromptMessage(
                    role="user",
                    content=TextContent(
                        type="text",
                        text=f"""I want to research salaries for "{occupation}"{location_text}.

Please use the JobTracker tools to:
1. Find the occupation details and national wage data
2. Show wage variations by location (top 10 highest and lowest paying areas)
3. Explain the wage percentiles (10th, 25th, 75th, 90th)
4. Compare to similar occupations
5. Identify factors that might affect salary (experience, certifications, etc.)

Provide insights on earning potential and career growth.""",
                    ),
                ),
            ],
        )

    return GetPromptResult(
        description="Unknown prompt",
        messages=[
            PromptMessage(
                role="user",
                content=TextContent(type="text", text=f"Unknown prompt: {name}"),
            ),
        ],
    )


# ============================================================================
# Main
# ============================================================================


async def main():
    """Run the MCP server."""
    logger.info("Starting JobTracker MCP Server")

    # Check Typesense connection
    if loader.health_check():
        logger.info("Connected to Typesense")
    else:
        logger.warning("Typesense not connected - some features may be limited")

    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
