"""
Data Transformer for JobTracker.

Transforms raw BLS and O*NET data into Typesense document format.
"""

import logging
from datetime import datetime
from typing import Any, Optional

import pandas as pd

from .onet_client import OccupationDetails, Skill, TechnologySkill

logger = logging.getLogger(__name__)


class DataTransformer:
    """
    Transforms raw data from BLS and O*NET into Typesense document format.
    """

    @staticmethod
    def _safe_float(value: Any, default: float = 0.0) -> float:
        """Safely convert value to float."""
        if pd.isna(value) or value in ("*", "**", "#"):
            return default
        try:
            return float(value)
        except (ValueError, TypeError):
            return default

    @staticmethod
    def _safe_int(value: Any, default: int = 0) -> int:
        """Safely convert value to int."""
        if pd.isna(value) or value in ("*", "**", "#"):
            return default
        try:
            return int(float(value))
        except (ValueError, TypeError):
            return default

    @staticmethod
    def _normalize_soc_code(soc_code: str) -> str:
        """Normalize SOC code format (e.g., '151252' -> '15-1252')."""
        soc = str(soc_code).replace("-", "").replace(".", "").strip()
        if len(soc) >= 6:
            return f"{soc[:2]}-{soc[2:6]}"
        return soc_code

    def transform_occupation(
        self,
        bls_data: dict[str, Any],
        onet_data: Optional[OccupationDetails] = None,
    ) -> dict[str, Any]:
        """
        Transform BLS and O*NET data into occupation document.

        Args:
            bls_data: Dictionary from BLS OEWS data
            onet_data: Optional O*NET occupation details

        Returns:
            Typesense document dictionary
        """
        soc_code = self._normalize_soc_code(bls_data.get("OCC_CODE", ""))
        onet_code = f"{soc_code}.00"

        doc = {
            "id": soc_code,
            "soc_code": soc_code,
            "onet_code": onet_code,
            "title": bls_data.get("OCC_TITLE", ""),
            "occupation_group": bls_data.get("O_GROUP", "detailed"),
            # Employment data
            "national_employment": self._safe_int(bls_data.get("TOT_EMP")),
            # Wage data
            "national_mean_wage": self._safe_float(bls_data.get("A_MEAN")),
            "national_median_wage": self._safe_float(bls_data.get("A_MEDIAN")),
            "hourly_mean_wage": self._safe_float(bls_data.get("H_MEAN")),
            "hourly_median_wage": self._safe_float(bls_data.get("H_MEDIAN")),
            # Wage percentiles
            "wage_pct_10": self._safe_float(bls_data.get("A_PCT10")),
            "wage_pct_25": self._safe_float(bls_data.get("A_PCT25")),
            "wage_pct_75": self._safe_float(bls_data.get("A_PCT75")),
            "wage_pct_90": self._safe_float(bls_data.get("A_PCT90")),
            # Hourly percentiles
            "hourly_pct_10": self._safe_float(bls_data.get("H_PCT10")),
            "hourly_pct_25": self._safe_float(bls_data.get("H_PCT25")),
            "hourly_pct_75": self._safe_float(bls_data.get("H_PCT75")),
            "hourly_pct_90": self._safe_float(bls_data.get("H_PCT90")),
            # Metadata
            "last_updated": int(datetime.now().timestamp()),
        }

        # Add O*NET data if available
        if onet_data:
            doc.update(self._transform_onet_data(onet_data))

        return doc

    def _transform_onet_data(self, onet_data: OccupationDetails) -> dict[str, Any]:
        """Transform O*NET data into document fields."""
        return {
            "description": onet_data.description,
            "job_zone": onet_data.job_zone,
            "bright_outlook": onet_data.bright_outlook,
            # Skills as nested objects
            "skills": [self._transform_skill(s) for s in onet_data.skills],
            "knowledge_areas": [self._transform_skill(k) for k in onet_data.knowledge],
            "abilities": [self._transform_skill(a) for a in onet_data.abilities],
            # Technology skills as string array
            "technology_skills": [t.name for t in onet_data.technology_skills],
            "hot_technologies": [
                t.name for t in onet_data.technology_skills if t.hot_technology
            ],
            # Tasks as string array
            "tasks": [t.description for t in onet_data.tasks[:20]],  # Limit to top 20
            # Flat arrays for faceting
            "skill_names": [s.name for s in onet_data.skills],
            "knowledge_names": [k.name for k in onet_data.knowledge],
            "ability_names": [a.name for a in onet_data.abilities],
            # Education info
            "education_level": self._extract_education_level(onet_data.education),
            "experience_required": self._extract_experience(onet_data),
        }

    def _transform_skill(self, skill: Skill) -> dict[str, Any]:
        """Transform a skill object to dictionary."""
        return {
            "id": skill.id,
            "name": skill.name,
            "description": skill.description,
            "importance": skill.importance,
            "level": skill.level or 0.0,
            "category": skill.category,
        }

    def _extract_education_level(self, education: Optional[dict[str, Any]]) -> str:
        """Extract primary education level from O*NET education data."""
        if not education:
            return "Not specified"

        # Try to find the most common education level
        levels = education.get("level", [])
        if not levels:
            return "Not specified"

        # Sort by percentage and return highest
        sorted_levels = sorted(
            levels, key=lambda x: x.get("percentage", 0), reverse=True
        )
        if sorted_levels:
            return sorted_levels[0].get("name", "Not specified")

        return "Not specified"

    def _extract_experience(self, onet_data: OccupationDetails) -> str:
        """Extract experience requirement based on job zone."""
        job_zone_experience = {
            1: "None required",
            2: "Some prior experience helpful",
            3: "Previous work experience required",
            4: "Considerable work experience",
            5: "Extensive work experience required",
        }
        return job_zone_experience.get(onet_data.job_zone, "Not specified")

    def transform_wage_by_location(
        self,
        wage_data: dict[str, Any],
        area_type: str = "state",
    ) -> dict[str, Any]:
        """
        Transform location-based wage data into document.

        Args:
            wage_data: Dictionary from BLS state/metro data
            area_type: Type of area ('state' or 'metro')

        Returns:
            Typesense document dictionary
        """
        soc_code = self._normalize_soc_code(wage_data.get("OCC_CODE", ""))
        area_code = str(wage_data.get("AREA", ""))

        # Create unique ID
        doc_id = f"{soc_code}_{area_code}"

        return {
            "id": doc_id,
            "soc_code": soc_code,
            "occupation_title": wage_data.get("OCC_TITLE", ""),
            # Location data
            "area_type": area_type,
            "area_code": area_code,
            "area_title": wage_data.get("AREA_TITLE", ""),
            "state_code": self._extract_state_code(area_code, area_type),
            "state_name": self._extract_state_name(wage_data, area_type),
            # Employment data
            "employment": self._safe_int(wage_data.get("TOT_EMP")),
            "employment_per_1000": self._safe_float(wage_data.get("JOBS_1000")),
            "location_quotient": self._safe_float(wage_data.get("LOC_QUOTIENT")),
            # Hourly wages
            "hourly_mean_wage": self._safe_float(wage_data.get("H_MEAN")),
            "hourly_median_wage": self._safe_float(wage_data.get("H_MEDIAN")),
            "hourly_pct_10": self._safe_float(wage_data.get("H_PCT10")),
            "hourly_pct_25": self._safe_float(wage_data.get("H_PCT25")),
            "hourly_pct_75": self._safe_float(wage_data.get("H_PCT75")),
            "hourly_pct_90": self._safe_float(wage_data.get("H_PCT90")),
            # Annual wages
            "annual_mean_wage": self._safe_float(wage_data.get("A_MEAN")),
            "annual_median_wage": self._safe_float(wage_data.get("A_MEDIAN")),
            "annual_pct_10": self._safe_float(wage_data.get("A_PCT10")),
            "annual_pct_25": self._safe_float(wage_data.get("A_PCT25")),
            "annual_pct_75": self._safe_float(wage_data.get("A_PCT75")),
            "annual_pct_90": self._safe_float(wage_data.get("A_PCT90")),
            # Metadata
            "data_year": datetime.now().year,
            "last_updated": int(datetime.now().timestamp()),
        }

    def _extract_state_code(self, area_code: str, area_type: str) -> str:
        """Extract state code from area code."""
        if area_type == "state" and len(area_code) >= 2:
            return area_code[:2]
        return ""

    def _extract_state_name(self, wage_data: dict[str, Any], area_type: str) -> str:
        """Extract state name from wage data."""
        if area_type == "state":
            return wage_data.get("AREA_TITLE", "")
        # For metro areas, try to extract state from title
        title = wage_data.get("AREA_TITLE", "")
        # Metro titles often end with state abbreviation
        return ""

    def transform_skill_document(
        self,
        skill_id: str,
        skill_name: str,
        skill_type: str,
        description: str,
        related_occupations: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        Transform aggregated skill data into document.

        Args:
            skill_id: Unique skill identifier
            skill_name: Name of the skill
            skill_type: Type (skill, knowledge, ability)
            description: Skill description
            related_occupations: List of occupations using this skill

        Returns:
            Typesense document dictionary
        """
        # Calculate averages
        importances = [
            occ.get("importance", 0) for occ in related_occupations if occ.get("importance")
        ]
        levels = [
            occ.get("level", 0) for occ in related_occupations if occ.get("level")
        ]

        avg_importance = sum(importances) / len(importances) if importances else 0.0
        avg_level = sum(levels) / len(levels) if levels else 0.0

        # Categorize skill
        category = self._categorize_skill(skill_id)

        return {
            "id": skill_id,
            "skill_id": skill_id,
            "skill_name": skill_name,
            "skill_type": skill_type,
            "description": description,
            "category": category,
            "related_occupations": related_occupations[:50],  # Limit for storage
            "occupation_count": len(related_occupations),
            "avg_importance": round(avg_importance, 2),
            "avg_level": round(avg_level, 2),
            "last_updated": int(datetime.now().timestamp()),
        }

    def _categorize_skill(self, skill_id: str) -> str:
        """Categorize skill based on O*NET taxonomy."""
        # O*NET skill IDs follow a pattern like 2.A.1.a
        if not skill_id or "." not in skill_id:
            return "General"

        prefix = skill_id.split(".")[0]

        categories = {
            "1": "Worker Characteristics",
            "2": "Worker Requirements",
            "3": "Experience Requirements",
            "4": "Occupational Requirements",
        }

        return categories.get(prefix, "General")

    def transform_bulk_occupations(
        self,
        bls_df: pd.DataFrame,
        onet_data: Optional[dict[str, OccupationDetails]] = None,
    ) -> list[dict[str, Any]]:
        """
        Transform bulk occupation data from DataFrame.

        Args:
            bls_df: DataFrame from BLS bulk download
            onet_data: Optional dict mapping SOC codes to O*NET details

        Returns:
            List of Typesense documents
        """
        documents = []
        onet_data = onet_data or {}

        for _, row in bls_df.iterrows():
            bls_dict = row.to_dict()
            soc_code = self._normalize_soc_code(bls_dict.get("OCC_CODE", ""))
            onet_code = f"{soc_code}.00"

            onet_details = onet_data.get(onet_code) or onet_data.get(soc_code)

            doc = self.transform_occupation(bls_dict, onet_details)
            documents.append(doc)

        logger.info(f"Transformed {len(documents)} occupation documents")
        return documents

    def transform_bulk_wages(
        self,
        wage_df: pd.DataFrame,
        area_type: str = "state",
    ) -> list[dict[str, Any]]:
        """
        Transform bulk wage data from DataFrame.

        Args:
            wage_df: DataFrame from BLS state/metro bulk download
            area_type: Type of area data

        Returns:
            List of Typesense documents
        """
        documents = []

        for _, row in wage_df.iterrows():
            wage_dict = row.to_dict()
            doc = self.transform_wage_by_location(wage_dict, area_type)
            documents.append(doc)

        logger.info(f"Transformed {len(documents)} {area_type} wage documents")
        return documents
