"""Unit tests for DataExtractor — T031 (must FAIL before implementation)."""
import pytest

from src.ml.training.data_extractor import DataExtractor


@pytest.fixture
def extractor(tmp_path):
    return DataExtractor(
        telemetry_dir=str(tmp_path / "delta"),
        recommendations_dir=str(tmp_path / "recommendations"),
    )


@pytest.mark.asyncio
async def test_extract_telemetry_empty_dir_returns_empty_list(extractor):
    records = await extractor.extract_telemetry()
    assert isinstance(records, list)
    assert len(records) == 0


@pytest.mark.asyncio
async def test_extract_recommendations_empty_dir_returns_empty_list(extractor):
    records = await extractor.extract_recommendations()
    assert isinstance(records, list)
    assert len(records) == 0


@pytest.mark.asyncio
async def test_extract_telemetry_handles_corrupt_dir(tmp_path):
    extractor = DataExtractor(
        telemetry_dir=str(tmp_path / "nonexistent"),
        recommendations_dir=str(tmp_path / "nonexistent2"),
    )
    records = await extractor.extract_telemetry()
    assert records == []


@pytest.mark.asyncio
async def test_extract_returns_telemetry_record_objects(extractor):
    from src.ml.training.data_extractor import TelemetryRecord
    records = await extractor.extract_telemetry()
    for r in records:
        assert isinstance(r, TelemetryRecord)
