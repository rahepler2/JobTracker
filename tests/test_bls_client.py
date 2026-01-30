"""
Tests for BLS client.
"""

import pytest

from src.bls_client import BLSClient, OEWSSeriesID


class TestOEWSSeriesID:
    """Tests for OEWS Series ID generation."""

    def test_national_employment_series_id(self):
        """Test national employment series ID generation."""
        series_id = OEWSSeriesID.national_employment("15-1252")
        assert series_id == "OEUM0000000000000151252001"

    def test_national_wage_series_id(self):
        """Test national wage series ID generation."""
        series_id = OEWSSeriesID.national_wage("15-1252", "annual_median")
        assert series_id == "OEUM0000000000000151252013"

    def test_series_id_build(self):
        """Test custom series ID building."""
        series = OEWSSeriesID(
            area_code="5100000",
            occupation_code="151252",
            data_type="04",
        )
        assert series.build() == "OEUM5100000000000151252004"


class TestBLSClient:
    """Tests for BLS client functionality."""

    @pytest.fixture
    def client(self):
        """Create a BLS client instance."""
        return BLSClient()

    def test_client_initialization(self, client):
        """Test client initializes correctly."""
        assert client.settings is not None
        assert client.settings.base_url == "https://api.bls.gov/publicAPI/v2/"

    def test_search_occupations_returns_dataframe(self, client):
        """Test that search returns a DataFrame."""
        # This would require mocking the HTTP calls
        # For now, just test the interface exists
        assert hasattr(client, "search_occupations")
        assert callable(client.search_occupations)


# Integration tests (require network access)
class TestBLSClientIntegration:
    """Integration tests for BLS client (require network)."""

    @pytest.fixture
    def client(self):
        """Create a BLS client instance."""
        return BLSClient()

    @pytest.mark.skip(reason="Requires network access and valid API key")
    def test_fetch_national_data(self, client):
        """Test fetching national OEWS data."""
        df = client.get_national_data()
        assert not df.empty
        assert "OCC_CODE" in df.columns
        assert "OCC_TITLE" in df.columns
