"""
ETL Pipeline for JobTracker.

Orchestrates data extraction from BLS and O*NET, transformation,
and loading into Typesense.
"""

import logging
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from .bls_client import BLSClient
from .config import get_settings
from .data_transformer import DataTransformer
from .onet_client import ONetClient, OccupationDetails
from .typesense_loader import TypesenseLoader

logger = logging.getLogger(__name__)


class OccupationalDataPipeline:
    """
    Main ETL pipeline for occupational data.

    Orchestrates:
    1. BLS OEWS data extraction (wages, employment)
    2. O*NET data extraction (skills, knowledge, abilities)
    3. Data transformation
    4. Typesense loading
    """

    def __init__(
        self,
        bls_client: Optional[BLSClient] = None,
        onet_client: Optional[ONetClient] = None,
        typesense_loader: Optional[TypesenseLoader] = None,
        transformer: Optional[DataTransformer] = None,
    ):
        """Initialize the pipeline with optional client overrides."""
        self.settings = get_settings()
        self.bls = bls_client or BLSClient()
        self.onet = onet_client or ONetClient()
        self.typesense = typesense_loader or TypesenseLoader()
        self.transformer = transformer or DataTransformer()

        # Cache directory for downloaded data
        self.cache_dir = Path(self.settings.data.cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def run_full_refresh(
        self,
        drop_existing: bool = False,
        include_onet: bool = True,
        include_location_wages: bool = True,
    ) -> dict[str, Any]:
        """
        Run a complete data refresh.

        Args:
            drop_existing: Drop and recreate collections
            include_onet: Include O*NET skills data
            include_location_wages: Include state/metro wage data

        Returns:
            Summary of operations performed
        """
        logger.info("Starting full data refresh")
        start_time = datetime.now()
        results: dict[str, Any] = {"started": start_time.isoformat()}

        # Create collections
        self.typesense.create_all_collections(drop_existing=drop_existing)

        # Load BLS national data
        logger.info("Loading BLS national data")
        national_df = self.bls.get_national_data()
        results["bls_national_records"] = len(national_df)

        # Filter to detailed occupations
        if "O_GROUP" in national_df.columns:
            detailed_df = national_df[national_df["O_GROUP"] == "detailed"]
        else:
            detailed_df = national_df

        # Load O*NET data if enabled
        onet_data: dict[str, OccupationDetails] = {}
        if include_onet:
            logger.info("Loading O*NET data")
            onet_data = self._load_onet_data(detailed_df)
            results["onet_occupations_loaded"] = len(onet_data)

        # Transform and load occupations
        logger.info("Transforming and loading occupations")
        occupation_docs = self.transformer.transform_bulk_occupations(
            detailed_df, onet_data
        )
        occ_results = self.typesense.index_documents("occupations", occupation_docs)
        results["occupations_indexed"] = occ_results

        # Load location wage data if enabled
        if include_location_wages:
            logger.info("Loading state wage data")
            state_results = self._load_state_wages()
            results["state_wages_indexed"] = state_results

            logger.info("Loading metro wage data")
            metro_results = self._load_metro_wages()
            results["metro_wages_indexed"] = metro_results

        # Build and load skills collection
        if include_onet and onet_data:
            logger.info("Building skills collection")
            skills_results = self._build_skills_collection(onet_data)
            results["skills_indexed"] = skills_results

        end_time = datetime.now()
        results["completed"] = end_time.isoformat()
        results["duration_seconds"] = (end_time - start_time).total_seconds()

        logger.info(f"Full refresh completed in {results['duration_seconds']:.2f}s")
        return results

    def _load_onet_data(
        self,
        bls_df: pd.DataFrame,
        max_occupations: Optional[int] = None,
    ) -> dict[str, OccupationDetails]:
        """
        Load O*NET data for occupations in the BLS DataFrame.

        Args:
            bls_df: DataFrame with BLS occupations
            max_occupations: Maximum occupations to load (for testing)

        Returns:
            Dictionary mapping O*NET codes to OccupationDetails
        """
        onet_data = {}
        soc_codes = bls_df["OCC_CODE"].unique()

        if max_occupations:
            soc_codes = soc_codes[:max_occupations]

        total = len(soc_codes)

        for i, soc_code in enumerate(soc_codes):
            # Convert to O*NET format
            normalized = soc_code.replace("-", "").replace(".", "")
            if len(normalized) >= 6:
                onet_code = f"{normalized[:2]}-{normalized[2:6]}.00"
            else:
                continue

            try:
                logger.debug(f"Loading O*NET data for {onet_code} ({i + 1}/{total})")
                details = self.onet.get_complete_occupation(onet_code)
                onet_data[onet_code] = details
            except Exception as e:
                logger.warning(f"Failed to load O*NET data for {onet_code}: {e}")

            # Log progress every 50 occupations
            if (i + 1) % 50 == 0:
                logger.info(f"Loaded O*NET data for {i + 1}/{total} occupations")

        return onet_data

    def _load_state_wages(self) -> dict[str, int]:
        """Load state-level wage data."""
        try:
            state_df = self.bls.get_state_data()

            # Filter to detailed occupations
            if "O_GROUP" in state_df.columns:
                state_df = state_df[state_df["O_GROUP"] == "detailed"]

            state_docs = self.transformer.transform_bulk_wages(state_df, "state")
            return self.typesense.index_documents(
                "occupation_wages_by_location", state_docs
            )
        except Exception as e:
            logger.error(f"Failed to load state wages: {e}")
            return {"success": 0, "failed": 0, "error": str(e)}

    def _load_metro_wages(self) -> dict[str, int]:
        """Load metro area wage data."""
        try:
            metro_df = self.bls.get_metro_data()

            # Filter to detailed occupations
            if "O_GROUP" in metro_df.columns:
                metro_df = metro_df[metro_df["O_GROUP"] == "detailed"]

            metro_docs = self.transformer.transform_bulk_wages(metro_df, "metro")
            return self.typesense.index_documents(
                "occupation_wages_by_location", metro_docs
            )
        except Exception as e:
            logger.error(f"Failed to load metro wages: {e}")
            return {"success": 0, "failed": 0, "error": str(e)}

    def _build_skills_collection(
        self,
        onet_data: dict[str, OccupationDetails],
    ) -> dict[str, int]:
        """
        Build aggregated skills collection from O*NET data.

        Args:
            onet_data: Dictionary of O*NET occupation details

        Returns:
            Index results
        """
        # Aggregate skills across occupations
        skill_aggregator: dict[str, dict[str, Any]] = defaultdict(
            lambda: {
                "name": "",
                "description": "",
                "type": "",
                "occupations": [],
            }
        )

        for onet_code, details in onet_data.items():
            # Add skills
            for skill in details.skills:
                skill_aggregator[skill.id]["name"] = skill.name
                skill_aggregator[skill.id]["description"] = skill.description
                skill_aggregator[skill.id]["type"] = "skill"
                skill_aggregator[skill.id]["occupations"].append({
                    "code": onet_code,
                    "title": details.title,
                    "importance": skill.importance,
                    "level": skill.level,
                })

            # Add knowledge areas
            for knowledge in details.knowledge:
                skill_aggregator[knowledge.id]["name"] = knowledge.name
                skill_aggregator[knowledge.id]["description"] = knowledge.description
                skill_aggregator[knowledge.id]["type"] = "knowledge"
                skill_aggregator[knowledge.id]["occupations"].append({
                    "code": onet_code,
                    "title": details.title,
                    "importance": knowledge.importance,
                    "level": knowledge.level,
                })

            # Add abilities
            for ability in details.abilities:
                skill_aggregator[ability.id]["name"] = ability.name
                skill_aggregator[ability.id]["description"] = ability.description
                skill_aggregator[ability.id]["type"] = "ability"
                skill_aggregator[ability.id]["occupations"].append({
                    "code": onet_code,
                    "title": details.title,
                    "importance": ability.importance,
                    "level": ability.level,
                })

        # Transform to documents
        skill_docs = []
        for skill_id, data in skill_aggregator.items():
            doc = self.transformer.transform_skill_document(
                skill_id=skill_id,
                skill_name=data["name"],
                skill_type=data["type"],
                description=data["description"],
                related_occupations=data["occupations"],
            )
            skill_docs.append(doc)

        return self.typesense.index_documents("skills", skill_docs)

    def check_and_update_oews(self) -> dict[str, Any]:
        """
        Check for new OEWS data and update if available.

        Returns:
            Update results
        """
        logger.info("Checking for OEWS data updates")

        # Get current stats
        current_stats = self.typesense.get_collection_stats("occupations")
        current_count = current_stats.get("num_documents", 0)

        # Download fresh data
        try:
            national_df = self.bls.get_national_data()
            new_count = len(national_df[national_df.get("O_GROUP", "") == "detailed"])

            if new_count > 0:
                logger.info(f"Found {new_count} occupations in fresh data")

                # Transform and upsert
                if "O_GROUP" in national_df.columns:
                    detailed_df = national_df[national_df["O_GROUP"] == "detailed"]
                else:
                    detailed_df = national_df

                occupation_docs = self.transformer.transform_bulk_occupations(detailed_df)
                results = self.typesense.index_documents("occupations", occupation_docs)

                return {
                    "status": "updated",
                    "previous_count": current_count,
                    "new_count": new_count,
                    "index_results": results,
                }

        except Exception as e:
            logger.error(f"OEWS update check failed: {e}")
            return {"status": "error", "error": str(e)}

        return {"status": "no_update_needed"}

    def update_onet_data(
        self,
        soc_codes: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """
        Update O*NET data for specified occupations.

        Args:
            soc_codes: List of SOC codes to update, or None for all

        Returns:
            Update results
        """
        logger.info("Starting O*NET data update")

        if soc_codes is None:
            # Get all occupations from Typesense
            results = self.typesense.search_occupations("*", per_page=1000)
            soc_codes = [hit["document"]["soc_code"] for hit in results.get("hits", [])]

        updated_count = 0
        failed_count = 0

        for soc_code in soc_codes:
            onet_code = f"{soc_code}.00"

            try:
                details = self.onet.get_complete_occupation(onet_code)

                # Get existing document
                existing = self.typesense.get_document("occupations", soc_code)
                if existing:
                    # Merge O*NET data
                    onet_fields = self.transformer._transform_onet_data(details)
                    existing.update(onet_fields)
                    existing["last_updated"] = int(datetime.now().timestamp())

                    self.typesense.index_documents("occupations", [existing])
                    updated_count += 1

            except Exception as e:
                logger.warning(f"Failed to update O*NET data for {soc_code}: {e}")
                failed_count += 1

        return {
            "status": "completed",
            "updated": updated_count,
            "failed": failed_count,
        }

    def get_pipeline_status(self) -> dict[str, Any]:
        """Get current pipeline and data status."""
        stats = self.typesense.get_all_stats()

        return {
            "typesense_healthy": self.typesense.health_check(),
            "collections": stats,
            "data_year": self.settings.data.year,
            "last_check": datetime.now().isoformat(),
        }
