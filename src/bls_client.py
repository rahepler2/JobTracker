"""
BLS (Bureau of Labor Statistics) API Client.

Provides access to OEWS (Occupational Employment and Wage Statistics) data
through both the REST API and bulk data downloads.
"""

import io
import logging
import time
import zipfile
from dataclasses import dataclass
from typing import Any, Optional

import httpx
import pandas as pd
from tenacity import retry, stop_after_attempt, wait_exponential

from .config import BLSSettings, get_settings

logger = logging.getLogger(__name__)


@dataclass
class OEWSSeriesID:
    """OEWS Series ID builder following BLS format."""

    area_code: str = "0000000"  # National
    industry_code: str = "000000"  # Cross-industry
    occupation_code: str = "000000"  # All occupations
    data_type: str = "01"  # Employment

    # Data type codes
    EMPLOYMENT = "01"
    HOURLY_MEAN = "03"
    ANNUAL_MEAN = "04"
    HOURLY_MEDIAN = "08"
    ANNUAL_MEDIAN = "13"
    HOURLY_PCT_10 = "07"
    HOURLY_PCT_25 = "10"
    HOURLY_PCT_75 = "11"
    HOURLY_PCT_90 = "12"
    ANNUAL_PCT_10 = "14"
    ANNUAL_PCT_25 = "15"
    ANNUAL_PCT_75 = "16"
    ANNUAL_PCT_90 = "17"

    def build(self) -> str:
        """Build the complete series ID string."""
        return f"OEUM{self.area_code}{self.industry_code}{self.occupation_code}{self.data_type}"

    @classmethod
    def national_employment(cls, soc_code: str) -> str:
        """Get national employment series ID for an occupation."""
        occ_code = soc_code.replace("-", "").replace(".", "")[:6]
        return cls(occupation_code=occ_code, data_type=cls.EMPLOYMENT).build()

    @classmethod
    def national_wage(cls, soc_code: str, wage_type: str = "annual_median") -> str:
        """Get national wage series ID for an occupation."""
        occ_code = soc_code.replace("-", "").replace(".", "")[:6]
        type_map = {
            "annual_mean": cls.ANNUAL_MEAN,
            "annual_median": cls.ANNUAL_MEDIAN,
            "hourly_mean": cls.HOURLY_MEAN,
            "hourly_median": cls.HOURLY_MEDIAN,
        }
        return cls(occupation_code=occ_code, data_type=type_map.get(wage_type, cls.ANNUAL_MEDIAN)).build()


@dataclass
class BLSResponse:
    """Structured response from BLS API."""

    status: str
    series_data: list[dict[str, Any]]
    message: Optional[list[str]] = None

    @property
    def is_success(self) -> bool:
        return self.status == "REQUEST_SUCCEEDED"


class BLSClient:
    """
    Client for accessing BLS OEWS data.

    Supports both API calls and bulk data downloads.
    """

    def __init__(self, settings: Optional[BLSSettings] = None):
        """Initialize the BLS client."""
        self.settings = settings or get_settings().bls
        self._client: Optional[httpx.Client] = None

    @property
    def client(self) -> httpx.Client:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.Client(
                base_url=self.settings.base_url,
                timeout=self.settings.timeout,
            )
        return self._client

    def close(self) -> None:
        """Close the HTTP client."""
        if self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self) -> "BLSClient":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    def fetch_series(
        self,
        series_ids: list[str],
        start_year: int,
        end_year: int,
    ) -> BLSResponse:
        """
        Fetch time series data from BLS API.

        Args:
            series_ids: List of BLS series IDs (max 50 per request)
            start_year: Start year for data
            end_year: End year for data

        Returns:
            BLSResponse with series data
        """
        if len(series_ids) > self.settings.max_series_per_request:
            raise ValueError(
                f"Maximum {self.settings.max_series_per_request} series per request"
            )

        payload: dict[str, Any] = {
            "seriesid": series_ids,
            "startyear": str(start_year),
            "endyear": str(end_year),
        }

        if self.settings.api_key:
            payload["registrationkey"] = self.settings.api_key

        logger.debug(f"Fetching {len(series_ids)} series from BLS API")

        response = self.client.post("timeseries/data/", json=payload)
        response.raise_for_status()

        data = response.json()

        # Rate limiting
        time.sleep(self.settings.rate_limit_delay)

        return BLSResponse(
            status=data.get("status", "UNKNOWN"),
            series_data=data.get("Results", {}).get("series", []),
            message=data.get("message"),
        )

    def fetch_series_batched(
        self,
        series_ids: list[str],
        start_year: int,
        end_year: int,
    ) -> list[dict[str, Any]]:
        """
        Fetch multiple series in batches.

        Args:
            series_ids: List of all series IDs to fetch
            start_year: Start year
            end_year: End year

        Returns:
            Combined list of all series data
        """
        all_series = []
        batch_size = self.settings.max_series_per_request

        for i in range(0, len(series_ids), batch_size):
            batch = series_ids[i : i + batch_size]
            response = self.fetch_series(batch, start_year, end_year)

            if response.is_success:
                all_series.extend(response.series_data)
            else:
                logger.warning(f"Batch {i // batch_size} failed: {response.message}")

        return all_series

    def download_bulk_data(
        self,
        data_type: str = "national",
        year: Optional[int] = None,
    ) -> pd.DataFrame:
        """
        Download bulk OEWS data files.

        Args:
            data_type: Type of data - 'national', 'state', or 'metro'
            year: Data year (defaults to current year from settings)

        Returns:
            DataFrame with OEWS data
        """
        year = year or get_settings().data.year
        year_suffix = str(year)[2:]  # e.g., "24" for 2024

        file_map = {
            "national": f"oesm{year_suffix}nat.zip",
            "state": f"oesm{year_suffix}st.zip",
            "metro": f"oesm{year_suffix}ma.zip",
        }

        if data_type not in file_map:
            raise ValueError(f"Invalid data_type: {data_type}. Use 'national', 'state', or 'metro'")

        url = f"{self.settings.bulk_download_base}{file_map[data_type]}"
        logger.info(f"Downloading bulk data from {url}")

        response = httpx.get(url, timeout=120, follow_redirects=True)
        response.raise_for_status()

        # Extract Excel file from ZIP
        with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
            # Find the Excel file in the archive
            excel_files = [f for f in zf.namelist() if f.endswith(('.xlsx', '.xls'))]
            if not excel_files:
                raise ValueError("No Excel file found in ZIP archive")

            with zf.open(excel_files[0]) as excel_file:
                df = pd.read_excel(io.BytesIO(excel_file.read()))

        return df

    def get_national_data(self, year: Optional[int] = None) -> pd.DataFrame:
        """Get national-level OEWS data."""
        return self.download_bulk_data("national", year)

    def get_state_data(self, year: Optional[int] = None) -> pd.DataFrame:
        """Get state-level OEWS data."""
        return self.download_bulk_data("state", year)

    def get_metro_data(self, year: Optional[int] = None) -> pd.DataFrame:
        """Get metropolitan area OEWS data."""
        return self.download_bulk_data("metro", year)

    def get_all_occupations(self, year: Optional[int] = None) -> pd.DataFrame:
        """
        Get all occupations with national wages and employment.

        Returns:
            DataFrame with occupation data including:
            - OCC_CODE: SOC occupation code
            - OCC_TITLE: Occupation title
            - O_GROUP: Occupation group level
            - TOT_EMP: Total employment
            - A_MEAN: Annual mean wage
            - A_MEDIAN: Annual median wage
            - H_MEAN: Hourly mean wage
            - H_MEDIAN: Hourly median wage
            - Percentile columns
        """
        df = self.get_national_data(year)

        # Filter to detailed occupations only (not groups)
        if "O_GROUP" in df.columns:
            df = df[df["O_GROUP"] == "detailed"]

        return df

    def get_occupation_by_soc(
        self,
        soc_code: str,
        year: Optional[int] = None,
    ) -> Optional[dict[str, Any]]:
        """
        Get data for a specific occupation by SOC code.

        Args:
            soc_code: SOC occupation code (e.g., "15-1252")
            year: Data year

        Returns:
            Dictionary with occupation data or None if not found
        """
        df = self.get_national_data(year)

        # Normalize SOC code format
        soc_normalized = soc_code.replace(".", "")

        match = df[df["OCC_CODE"].str.replace(".", "", regex=False) == soc_normalized]

        if match.empty:
            return None

        return match.iloc[0].to_dict()

    def get_wages_by_state(
        self,
        soc_code: str,
        year: Optional[int] = None,
    ) -> pd.DataFrame:
        """
        Get wage data for an occupation across all states.

        Args:
            soc_code: SOC occupation code
            year: Data year

        Returns:
            DataFrame with state-level wage data
        """
        df = self.get_state_data(year)

        # Normalize SOC code
        soc_normalized = soc_code.replace(".", "")

        return df[df["OCC_CODE"].str.replace(".", "", regex=False) == soc_normalized]

    def get_wages_by_metro(
        self,
        soc_code: str,
        year: Optional[int] = None,
    ) -> pd.DataFrame:
        """
        Get wage data for an occupation across metropolitan areas.

        Args:
            soc_code: SOC occupation code
            year: Data year

        Returns:
            DataFrame with metro-level wage data
        """
        df = self.get_metro_data(year)

        # Normalize SOC code
        soc_normalized = soc_code.replace(".", "")

        return df[df["OCC_CODE"].str.replace(".", "", regex=False) == soc_normalized]

    def search_occupations(
        self,
        query: str,
        year: Optional[int] = None,
    ) -> pd.DataFrame:
        """
        Search occupations by title.

        Args:
            query: Search query string
            year: Data year

        Returns:
            DataFrame with matching occupations
        """
        df = self.get_all_occupations(year)

        # Case-insensitive search in title
        mask = df["OCC_TITLE"].str.lower().str.contains(query.lower(), na=False)

        return df[mask]
