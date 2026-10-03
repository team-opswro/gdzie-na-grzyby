"""Tests for weather grid generation."""
from pipeline.grid import cell_id, cell_center, build_grid


def test_cell_id_basic():
    """Test cell_id for basic input."""
    assert cell_id(50.67, 17.93) == "506_179"


def test_cell_id_float_edge():
    """Test cell_id avoids floating-point errors."""
    assert cell_id(50.6, 17.9) == "506_179"


def test_cell_center():
    """Test cell_center returns center coordinates."""
    assert cell_center("506_179") == (50.65, 17.95)


def test_build_grid_unique_sorted():
    """Test build_grid returns unique sorted cells."""
    g = build_grid([(50.67, 17.93), (50.61, 17.99), (50.71, 17.93)])
    assert [c["id"] for c in g["cells"]] == ["506_179", "507_179"]
    assert g["step"] == 0.1
