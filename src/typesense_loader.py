"""
Typesense Loader for JobTracker.

Manages Typesense collections and document indexing.
"""

import logging
from typing import Any, Optional

import typesense
from typesense.exceptions import ObjectAlreadyExists, ObjectNotFound

from .config import TypesenseSettings, get_settings

logger = logging.getLogger(__name__)


# Collection schemas
OCCUPATIONS_SCHEMA = {
    "name": "occupations",
    "fields": [
        {"name": "soc_code", "type": "string", "facet": True},
        {"name": "onet_code", "type": "string", "facet": True},
        {"name": "title", "type": "string"},
        {"name": "description", "type": "string", "optional": True},
        {"name": "occupation_group", "type": "string", "facet": True},
        # Employment data
        {"name": "national_employment", "type": "int32", "optional": True},
        # Wage data
        {"name": "national_mean_wage", "type": "float", "optional": True},
        {"name": "national_median_wage", "type": "float", "optional": True},
        {"name": "hourly_mean_wage", "type": "float", "optional": True},
        {"name": "hourly_median_wage", "type": "float", "optional": True},
        # Wage percentiles
        {"name": "wage_pct_10", "type": "float", "optional": True},
        {"name": "wage_pct_25", "type": "float", "optional": True},
        {"name": "wage_pct_75", "type": "float", "optional": True},
        {"name": "wage_pct_90", "type": "float", "optional": True},
        {"name": "hourly_pct_10", "type": "float", "optional": True},
        {"name": "hourly_pct_25", "type": "float", "optional": True},
        {"name": "hourly_pct_75", "type": "float", "optional": True},
        {"name": "hourly_pct_90", "type": "float", "optional": True},
        # Job characteristics
        {"name": "job_zone", "type": "int32", "facet": True, "optional": True},
        {"name": "education_level", "type": "string", "facet": True, "optional": True},
        {"name": "experience_required", "type": "string", "facet": True, "optional": True},
        {"name": "bright_outlook", "type": "bool", "facet": True, "optional": True},
        # Skills (nested objects)
        {"name": "skills", "type": "object[]", "optional": True},
        {"name": "knowledge_areas", "type": "object[]", "optional": True},
        {"name": "abilities", "type": "object[]", "optional": True},
        # Flat arrays for search/faceting
        {"name": "technology_skills", "type": "string[]", "facet": True, "optional": True},
        {"name": "hot_technologies", "type": "string[]", "facet": True, "optional": True},
        {"name": "tasks", "type": "string[]", "optional": True},
        {"name": "skill_names", "type": "string[]", "facet": True, "optional": True},
        {"name": "knowledge_names", "type": "string[]", "facet": True, "optional": True},
        {"name": "ability_names", "type": "string[]", "facet": True, "optional": True},
        # Metadata
        {"name": "last_updated", "type": "int64"},
    ],
    "default_sorting_field": "national_employment",
    "token_separators": ["-", "."],
}

WAGES_BY_LOCATION_SCHEMA = {
    "name": "occupation_wages_by_location",
    "fields": [
        {"name": "soc_code", "type": "string", "facet": True},
        {"name": "occupation_title", "type": "string"},
        # Location data
        {"name": "area_type", "type": "string", "facet": True},
        {"name": "area_code", "type": "string", "facet": True},
        {"name": "area_title", "type": "string"},
        {"name": "state_code", "type": "string", "facet": True, "optional": True},
        {"name": "state_name", "type": "string", "optional": True},
        # Employment data
        {"name": "employment", "type": "int32", "optional": True},
        {"name": "employment_per_1000", "type": "float", "optional": True},
        {"name": "location_quotient", "type": "float", "optional": True},
        # Hourly wages
        {"name": "hourly_mean_wage", "type": "float", "optional": True},
        {"name": "hourly_median_wage", "type": "float", "optional": True},
        {"name": "hourly_pct_10", "type": "float", "optional": True},
        {"name": "hourly_pct_25", "type": "float", "optional": True},
        {"name": "hourly_pct_75", "type": "float", "optional": True},
        {"name": "hourly_pct_90", "type": "float", "optional": True},
        # Annual wages
        {"name": "annual_mean_wage", "type": "float", "optional": True},
        {"name": "annual_median_wage", "type": "float", "optional": True},
        {"name": "annual_pct_10", "type": "float", "optional": True},
        {"name": "annual_pct_25", "type": "float", "optional": True},
        {"name": "annual_pct_75", "type": "float", "optional": True},
        {"name": "annual_pct_90", "type": "float", "optional": True},
        # Metadata
        {"name": "data_year", "type": "int32", "facet": True},
        {"name": "last_updated", "type": "int64"},
    ],
    "default_sorting_field": "employment",
}

SKILLS_SCHEMA = {
    "name": "skills",
    "fields": [
        {"name": "skill_id", "type": "string"},
        {"name": "skill_name", "type": "string"},
        {"name": "skill_type", "type": "string", "facet": True},
        {"name": "description", "type": "string"},
        {"name": "category", "type": "string", "facet": True},
        # Related occupations
        {"name": "related_occupations", "type": "object[]"},
        {"name": "occupation_count", "type": "int32"},
        # Averages
        {"name": "avg_importance", "type": "float"},
        {"name": "avg_level", "type": "float"},
        # Metadata
        {"name": "last_updated", "type": "int64"},
    ],
    "default_sorting_field": "occupation_count",
}


class TypesenseLoader:
    """
    Manages Typesense collections and document loading.
    """

    def __init__(self, settings: Optional[TypesenseSettings] = None):
        """Initialize the Typesense loader."""
        self.settings = settings or get_settings().typesense
        self._client: Optional[typesense.Client] = None

    @property
    def client(self) -> typesense.Client:
        """Get or create Typesense client."""
        if self._client is None:
            self._client = typesense.Client({
                "nodes": [
                    {
                        "host": self.settings.host,
                        "port": str(self.settings.port),
                        "protocol": self.settings.protocol,
                    }
                ],
                "api_key": self.settings.api_key,
                "connection_timeout_seconds": self.settings.connection_timeout,
                "num_retries": self.settings.num_retries,
                "retry_interval_seconds": self.settings.retry_interval,
            })
        return self._client

    def health_check(self) -> bool:
        """Check if Typesense is healthy."""
        try:
            health = self.client.operations.is_healthy()
            return health
        except Exception as e:
            logger.error(f"Typesense health check failed: {e}")
            return False

    def create_collection(
        self,
        schema: dict[str, Any],
        drop_existing: bool = False,
    ) -> dict[str, Any]:
        """
        Create a Typesense collection.

        Args:
            schema: Collection schema dictionary
            drop_existing: If True, drop existing collection first

        Returns:
            Created collection info
        """
        collection_name = schema["name"]

        if drop_existing:
            try:
                self.client.collections[collection_name].delete()
                logger.info(f"Dropped existing collection: {collection_name}")
            except ObjectNotFound:
                pass

        try:
            result = self.client.collections.create(schema)
            logger.info(f"Created collection: {collection_name}")
            return result
        except ObjectAlreadyExists:
            logger.info(f"Collection already exists: {collection_name}")
            return self.client.collections[collection_name].retrieve()

    def create_all_collections(self, drop_existing: bool = False) -> None:
        """Create all required collections."""
        schemas = [
            OCCUPATIONS_SCHEMA,
            WAGES_BY_LOCATION_SCHEMA,
            SKILLS_SCHEMA,
        ]

        for schema in schemas:
            self.create_collection(schema, drop_existing=drop_existing)

    def delete_collection(self, name: str) -> bool:
        """Delete a collection."""
        try:
            self.client.collections[name].delete()
            logger.info(f"Deleted collection: {name}")
            return True
        except ObjectNotFound:
            logger.warning(f"Collection not found: {name}")
            return False

    def index_documents(
        self,
        collection_name: str,
        documents: list[dict[str, Any]],
        batch_size: Optional[int] = None,
    ) -> dict[str, int]:
        """
        Index documents into a collection.

        Args:
            collection_name: Name of the collection
            documents: List of documents to index
            batch_size: Batch size for imports

        Returns:
            Dictionary with success/failure counts
        """
        batch_size = batch_size or self.settings.batch_size
        collection = self.client.collections[collection_name]

        total_success = 0
        total_failed = 0

        for i in range(0, len(documents), batch_size):
            batch = documents[i : i + batch_size]

            try:
                results = collection.documents.import_(
                    batch,
                    {"action": "upsert"},
                )

                # Count successes and failures
                for result in results:
                    if result.get("success"):
                        total_success += 1
                    else:
                        total_failed += 1
                        logger.warning(f"Failed to index document: {result.get('error')}")

            except Exception as e:
                logger.error(f"Batch import error: {e}")
                total_failed += len(batch)

        logger.info(
            f"Indexed {total_success} documents, {total_failed} failed in {collection_name}"
        )
        return {"success": total_success, "failed": total_failed}

    def get_document(
        self,
        collection_name: str,
        document_id: str,
    ) -> Optional[dict[str, Any]]:
        """Get a document by ID."""
        try:
            return self.client.collections[collection_name].documents[document_id].retrieve()
        except ObjectNotFound:
            return None

    def delete_document(
        self,
        collection_name: str,
        document_id: str,
    ) -> bool:
        """Delete a document by ID."""
        try:
            self.client.collections[collection_name].documents[document_id].delete()
            return True
        except ObjectNotFound:
            return False

    def search(
        self,
        collection_name: str,
        query: str,
        query_by: str,
        filter_by: Optional[str] = None,
        sort_by: Optional[str] = None,
        facet_by: Optional[str] = None,
        per_page: int = 10,
        page: int = 1,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Search a collection.

        Args:
            collection_name: Name of the collection
            query: Search query
            query_by: Fields to search
            filter_by: Filter expression
            sort_by: Sort expression
            facet_by: Fields to facet
            per_page: Results per page
            page: Page number

        Returns:
            Search results dictionary
        """
        search_params: dict[str, Any] = {
            "q": query,
            "query_by": query_by,
            "per_page": per_page,
            "page": page,
        }

        if filter_by:
            search_params["filter_by"] = filter_by
        if sort_by:
            search_params["sort_by"] = sort_by
        if facet_by:
            search_params["facet_by"] = facet_by

        search_params.update(kwargs)

        return self.client.collections[collection_name].documents.search(search_params)

    def search_occupations(
        self,
        query: str,
        filter_by: Optional[str] = None,
        sort_by: str = "national_employment:desc",
        per_page: int = 10,
        page: int = 1,
    ) -> dict[str, Any]:
        """Search occupations collection."""
        return self.search(
            collection_name="occupations",
            query=query,
            query_by="title,description,skill_names,technology_skills",
            filter_by=filter_by,
            sort_by=sort_by,
            facet_by="job_zone,education_level,bright_outlook",
            per_page=per_page,
            page=page,
        )

    def search_wages_by_location(
        self,
        query: str = "*",
        soc_code: Optional[str] = None,
        area_type: Optional[str] = None,
        state_code: Optional[str] = None,
        sort_by: str = "annual_median_wage:desc",
        per_page: int = 50,
        page: int = 1,
    ) -> dict[str, Any]:
        """Search wages by location collection."""
        filters = []
        if soc_code:
            filters.append(f"soc_code:={soc_code}")
        if area_type:
            filters.append(f"area_type:={area_type}")
        if state_code:
            filters.append(f"state_code:={state_code}")

        filter_by = " && ".join(filters) if filters else None

        return self.search(
            collection_name="occupation_wages_by_location",
            query=query,
            query_by="occupation_title,area_title",
            filter_by=filter_by,
            sort_by=sort_by,
            facet_by="area_type,state_code",
            per_page=per_page,
            page=page,
        )

    def search_skills(
        self,
        query: str,
        skill_type: Optional[str] = None,
        category: Optional[str] = None,
        per_page: int = 20,
        page: int = 1,
    ) -> dict[str, Any]:
        """Search skills collection."""
        filters = []
        if skill_type:
            filters.append(f"skill_type:={skill_type}")
        if category:
            filters.append(f"category:={category}")

        filter_by = " && ".join(filters) if filters else None

        return self.search(
            collection_name="skills",
            query=query,
            query_by="skill_name,description",
            filter_by=filter_by,
            sort_by="occupation_count:desc",
            facet_by="skill_type,category",
            per_page=per_page,
            page=page,
        )

    def get_collection_stats(self, collection_name: str) -> dict[str, Any]:
        """Get statistics for a collection."""
        try:
            collection = self.client.collections[collection_name].retrieve()
            return {
                "name": collection["name"],
                "num_documents": collection["num_documents"],
                "num_fields": len(collection["fields"]),
            }
        except ObjectNotFound:
            return {"error": f"Collection {collection_name} not found"}

    def get_all_stats(self) -> dict[str, Any]:
        """Get statistics for all collections."""
        return {
            "occupations": self.get_collection_stats("occupations"),
            "occupation_wages_by_location": self.get_collection_stats(
                "occupation_wages_by_location"
            ),
            "skills": self.get_collection_stats("skills"),
        }
