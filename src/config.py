"""
Configuration management for JobTracker.

Supports environment variables and YAML configuration files.
"""

import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class BLSSettings(BaseSettings):
    """BLS API configuration."""

    api_key: str = Field(default="", alias="BLS_API_KEY")
    base_url: str = "https://api.bls.gov/publicAPI/v2/"
    bulk_download_base: str = "https://www.bls.gov/oes/special-requests/"
    rate_limit_delay: float = 0.5
    max_series_per_request: int = 50
    max_years: int = 20
    timeout: int = 30


class ONetSettings(BaseSettings):
    """O*NET API configuration."""

    username: str = Field(default="", alias="ONET_USERNAME")
    app_key: str = Field(default="", alias="ONET_APP_KEY")
    base_url: str = "https://services.onetcenter.org/ws/"
    bulk_download_url: str = "https://www.onetcenter.org/dl_files/database/"
    rate_limit_delay: float = 0.2
    timeout: int = 30


class TypesenseSettings(BaseSettings):
    """Typesense configuration."""

    host: str = Field(default="localhost", alias="TYPESENSE_HOST")
    port: int = Field(default=8108, alias="TYPESENSE_PORT")
    protocol: str = Field(default="http", alias="TYPESENSE_PROTOCOL")
    api_key: str = Field(default="", alias="TYPESENSE_API_KEY")
    connection_timeout: int = 10
    num_retries: int = 3
    retry_interval: float = 1.0
    batch_size: int = 100


class APISettings(BaseSettings):
    """API server configuration."""

    host: str = Field(default="0.0.0.0", alias="API_HOST")
    port: int = Field(default=8000, alias="API_PORT")
    debug: bool = Field(default=False, alias="API_DEBUG")
    title: str = "JobTracker API"
    description: str = "BLS Jobs Data API - Access occupational data, wages, and skills"
    version: str = "0.1.0"
    docs_url: str = "/docs"
    redoc_url: str = "/redoc"


class MCPSettings(BaseSettings):
    """MCP server configuration."""

    server_name: str = Field(default="jobtracker", alias="MCP_SERVER_NAME")
    server_version: str = Field(default="0.1.0", alias="MCP_SERVER_VERSION")


class DataSettings(BaseSettings):
    """Data configuration."""

    year: int = Field(default=2024, alias="DATA_YEAR")
    cache_dir: str = Field(default="./cache", alias="CACHE_DIR")
    projections_period: str = "2024-34"


class Settings(BaseSettings):
    """Main settings class combining all configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    bls: BLSSettings = Field(default_factory=BLSSettings)
    onet: ONetSettings = Field(default_factory=ONetSettings)
    typesense: TypesenseSettings = Field(default_factory=TypesenseSettings)
    api: APISettings = Field(default_factory=APISettings)
    mcp: MCPSettings = Field(default_factory=MCPSettings)
    data: DataSettings = Field(default_factory=DataSettings)

    @classmethod
    def from_yaml(cls, yaml_path: Optional[str] = None) -> "Settings":
        """Load settings from YAML file and merge with environment variables."""
        if yaml_path is None:
            yaml_path = os.environ.get(
                "JOBTRACKER_CONFIG",
                str(Path(__file__).parent.parent / "config" / "settings.yaml")
            )

        yaml_config = {}
        if Path(yaml_path).exists():
            with open(yaml_path) as f:
                yaml_config = yaml.safe_load(f) or {}

        # Build nested settings from YAML
        bls_config = yaml_config.get("bls", {})
        onet_config = yaml_config.get("onet", {})
        typesense_config = yaml_config.get("typesense", {})
        api_config = yaml_config.get("api", {})
        data_config = yaml_config.get("data", {})

        return cls(
            bls=BLSSettings(**bls_config),
            onet=ONetSettings(**onet_config),
            typesense=TypesenseSettings(**typesense_config),
            api=APISettings(**api_config),
            data=DataSettings(**data_config),
        )


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings.from_yaml()
