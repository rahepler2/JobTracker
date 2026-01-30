"""
O*NET API Client.

Provides access to O*NET data including skills, knowledge, abilities,
tasks, and technology requirements for occupations.
"""

import base64
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from .config import ONetSettings, get_settings

logger = logging.getLogger(__name__)


@dataclass
class Skill:
    """Represents a skill with importance and level ratings."""

    id: str
    name: str
    description: str
    importance: float  # 1-5 scale
    level: Optional[float] = None  # 0-7 scale
    category: str = "skill"


@dataclass
class TechnologySkill:
    """Represents a technology/software skill."""

    name: str
    hot_technology: bool = False
    example_uses: list[str] = field(default_factory=list)


@dataclass
class Task:
    """Represents a work task for an occupation."""

    id: str
    description: str
    importance: float


@dataclass
class OccupationDetails:
    """Complete O*NET occupation details."""

    code: str
    title: str
    description: str
    job_zone: int
    skills: list[Skill]
    knowledge: list[Skill]
    abilities: list[Skill]
    technology_skills: list[TechnologySkill]
    tasks: list[Task]
    education: Optional[dict[str, Any]] = None
    experience: Optional[dict[str, Any]] = None
    bright_outlook: bool = False


class ONetClient:
    """
    Client for accessing O*NET Web Services API.

    Requires registration at https://services.onetcenter.org/developer/
    """

    def __init__(self, settings: Optional[ONetSettings] = None):
        """Initialize the O*NET client."""
        self.settings = settings or get_settings().onet
        self._client: Optional[httpx.Client] = None

    @property
    def _auth_header(self) -> str:
        """Build Basic Auth header."""
        credentials = f"{self.settings.username}:{self.settings.app_key}"
        encoded = base64.b64encode(credentials.encode()).decode()
        return f"Basic {encoded}"

    @property
    def client(self) -> httpx.Client:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.Client(
                base_url=self.settings.base_url,
                timeout=self.settings.timeout,
                headers={
                    "Authorization": self._auth_header,
                    "Accept": "application/json",
                },
            )
        return self._client

    def close(self) -> None:
        """Close the HTTP client."""
        if self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self) -> "ONetClient":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def _rate_limit(self) -> None:
        """Apply rate limiting between requests."""
        time.sleep(self.settings.rate_limit_delay)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    def _get(self, endpoint: str) -> dict[str, Any]:
        """Make a GET request to the O*NET API."""
        logger.debug(f"Fetching O*NET endpoint: {endpoint}")

        response = self.client.get(endpoint)
        response.raise_for_status()

        self._rate_limit()
        return response.json()

    def list_occupations(self, start: int = 1, end: int = 1000) -> list[dict[str, Any]]:
        """
        List all occupations in O*NET.

        Args:
            start: Starting index (1-based)
            end: Ending index

        Returns:
            List of occupation dictionaries with code and title
        """
        data = self._get(f"online/occupations?start={start}&end={end}")
        return data.get("occupation", [])

    def get_all_occupations(self) -> list[dict[str, Any]]:
        """
        Get all occupations from O*NET.

        Returns:
            Complete list of all occupations
        """
        all_occupations = []
        start = 1
        batch_size = 1000

        while True:
            batch = self.list_occupations(start, start + batch_size - 1)
            if not batch:
                break
            all_occupations.extend(batch)
            start += batch_size

        return all_occupations

    def get_occupation(self, code: str) -> dict[str, Any]:
        """
        Get basic occupation information.

        Args:
            code: O*NET occupation code (e.g., "15-1252.00")

        Returns:
            Occupation details dictionary
        """
        return self._get(f"online/occupations/{code}")

    def get_occupation_summary(self, code: str) -> dict[str, Any]:
        """
        Get occupation summary including description and job zone.

        Args:
            code: O*NET occupation code

        Returns:
            Summary dictionary
        """
        return self._get(f"mnm/careers/{code}/")

    def get_skills(self, code: str) -> list[Skill]:
        """
        Get skills for an occupation.

        Args:
            code: O*NET occupation code

        Returns:
            List of Skill objects
        """
        data = self._get(f"online/occupations/{code}/summary/skills")
        skills = []

        for item in data.get("element", []):
            # Get importance value
            importance = 0.0
            level = None

            if "score" in item:
                for score in item["score"]:
                    if score.get("scale", {}).get("id") == "IM":
                        importance = float(score.get("value", 0))
                    elif score.get("scale", {}).get("id") == "LV":
                        level = float(score.get("value", 0))

            skills.append(
                Skill(
                    id=item.get("id", ""),
                    name=item.get("name", ""),
                    description=item.get("description", ""),
                    importance=importance,
                    level=level,
                    category="skill",
                )
            )

        return skills

    def get_knowledge(self, code: str) -> list[Skill]:
        """
        Get knowledge areas for an occupation.

        Args:
            code: O*NET occupation code

        Returns:
            List of Skill objects (knowledge areas)
        """
        data = self._get(f"online/occupations/{code}/summary/knowledge")
        knowledge = []

        for item in data.get("element", []):
            importance = 0.0
            level = None

            if "score" in item:
                for score in item["score"]:
                    if score.get("scale", {}).get("id") == "IM":
                        importance = float(score.get("value", 0))
                    elif score.get("scale", {}).get("id") == "LV":
                        level = float(score.get("value", 0))

            knowledge.append(
                Skill(
                    id=item.get("id", ""),
                    name=item.get("name", ""),
                    description=item.get("description", ""),
                    importance=importance,
                    level=level,
                    category="knowledge",
                )
            )

        return knowledge

    def get_abilities(self, code: str) -> list[Skill]:
        """
        Get abilities for an occupation.

        Args:
            code: O*NET occupation code

        Returns:
            List of Skill objects (abilities)
        """
        data = self._get(f"online/occupations/{code}/summary/abilities")
        abilities = []

        for item in data.get("element", []):
            importance = 0.0
            level = None

            if "score" in item:
                for score in item["score"]:
                    if score.get("scale", {}).get("id") == "IM":
                        importance = float(score.get("value", 0))
                    elif score.get("scale", {}).get("id") == "LV":
                        level = float(score.get("value", 0))

            abilities.append(
                Skill(
                    id=item.get("id", ""),
                    name=item.get("name", ""),
                    description=item.get("description", ""),
                    importance=importance,
                    level=level,
                    category="ability",
                )
            )

        return abilities

    def get_technology_skills(self, code: str) -> list[TechnologySkill]:
        """
        Get technology skills (software/tools) for an occupation.

        Args:
            code: O*NET occupation code

        Returns:
            List of TechnologySkill objects
        """
        data = self._get(f"online/occupations/{code}/summary/technology_skills")
        tech_skills = []

        for category in data.get("category", []):
            for example in category.get("example", []):
                tech_skills.append(
                    TechnologySkill(
                        name=example.get("name", ""),
                        hot_technology=example.get("hot_technology", False),
                    )
                )

        return tech_skills

    def get_tasks(self, code: str) -> list[Task]:
        """
        Get tasks for an occupation.

        Args:
            code: O*NET occupation code

        Returns:
            List of Task objects
        """
        data = self._get(f"online/occupations/{code}/summary/tasks")
        tasks = []

        for item in data.get("task", []):
            importance = 0.0
            if "score" in item:
                for score in item["score"]:
                    if score.get("scale", {}).get("id") == "IM":
                        importance = float(score.get("value", 0))

            tasks.append(
                Task(
                    id=item.get("id", ""),
                    description=item.get("statement", ""),
                    importance=importance,
                )
            )

        return tasks

    def get_education(self, code: str) -> dict[str, Any]:
        """
        Get education requirements for an occupation.

        Args:
            code: O*NET occupation code

        Returns:
            Education requirements dictionary
        """
        return self._get(f"online/occupations/{code}/summary/education")

    def get_job_zone(self, code: str) -> dict[str, Any]:
        """
        Get job zone information for an occupation.

        Job zones range from 1 (little preparation) to 5 (extensive preparation).

        Args:
            code: O*NET occupation code

        Returns:
            Job zone dictionary
        """
        return self._get(f"online/occupations/{code}/summary/job_zone")

    def get_bright_outlook(self, code: str) -> bool:
        """
        Check if occupation has bright outlook designation.

        Args:
            code: O*NET occupation code

        Returns:
            True if occupation has bright outlook
        """
        try:
            data = self.get_occupation(code)
            tags = data.get("tags", {})
            return "bright_outlook" in tags or tags.get("bright_outlook", False)
        except Exception:
            return False

    def get_complete_occupation(self, code: str) -> OccupationDetails:
        """
        Get complete occupation details including all skills, knowledge, etc.

        Args:
            code: O*NET occupation code

        Returns:
            OccupationDetails object with all data
        """
        # Get basic info
        basic = self.get_occupation(code)
        job_zone_data = self.get_job_zone(code)

        # Get all skill types
        skills = self.get_skills(code)
        knowledge = self.get_knowledge(code)
        abilities = self.get_abilities(code)
        tech_skills = self.get_technology_skills(code)
        tasks = self.get_tasks(code)

        # Get education and check bright outlook
        try:
            education = self.get_education(code)
        except Exception:
            education = None

        bright_outlook = self.get_bright_outlook(code)

        return OccupationDetails(
            code=code,
            title=basic.get("title", ""),
            description=basic.get("description", ""),
            job_zone=job_zone_data.get("job_zone", {}).get("value", 0),
            skills=skills,
            knowledge=knowledge,
            abilities=abilities,
            technology_skills=tech_skills,
            tasks=tasks,
            education=education,
            bright_outlook=bright_outlook,
        )

    def search_occupations(self, keyword: str) -> list[dict[str, Any]]:
        """
        Search occupations by keyword.

        Args:
            keyword: Search keyword

        Returns:
            List of matching occupations
        """
        data = self._get(f"online/search?keyword={keyword}")
        return data.get("occupation", [])

    def get_related_occupations(self, code: str) -> list[dict[str, Any]]:
        """
        Get related occupations.

        Args:
            code: O*NET occupation code

        Returns:
            List of related occupations
        """
        data = self._get(f"online/occupations/{code}/summary/related_occupations")
        return data.get("occupation", [])
