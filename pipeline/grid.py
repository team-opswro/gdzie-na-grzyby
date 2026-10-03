"""Weather grid generation with 0.1° cell resolution."""
import math
from typing import Iterable

STEP = 0.1


def cell_id(lat: float, lon: float) -> str:
    """Generate cell identifier from latitude and longitude.

    Uses 0.1° grid with cell indices derived from floor(round(coord*10, 6)).

    Args:
        lat: latitude in decimal degrees
        lon: longitude in decimal degrees

    Returns:
        Cell ID as "lat_idx_lon_idx"
    """
    lat_idx = math.floor(round(lat * 10, 6))
    lon_idx = math.floor(round(lon * 10, 6))
    return f"{lat_idx}_{lon_idx}"


def cell_center(cid: str) -> tuple[float, float]:
    """Get center coordinates of a cell.

    Cell center is at (idx + 0.5) * STEP for each axis, rounded to 2 decimals.

    Args:
        cid: Cell ID as "lat_idx_lon_idx"

    Returns:
        Tuple of (latitude, longitude) at cell center
    """
    lat_idx, lon_idx = map(int, cid.split("_"))
    lat = round((lat_idx + 0.5) * STEP, 2)
    lon = round((lon_idx + 0.5) * STEP, 2)
    return (lat, lon)


def build_grid(points: Iterable[tuple[float, float]]) -> dict:
    """Build a weather grid from a set of points.

    Creates a 0.1° grid covering the given points, returning unique sorted cells.

    Args:
        points: Iterable of (lat, lon) tuples

    Returns:
        Dict with structure {"step": 0.1, "cells": [{"id": ..., "lat": ..., "lon": ...}, ...]}
        Cells are unique and sorted by ID.
    """
    cells_dict = {}
    for lat, lon in points:
        cid = cell_id(lat, lon)
        if cid not in cells_dict:
            lat_center, lon_center = cell_center(cid)
            cells_dict[cid] = {
                "id": cid,
                "lat": lat_center,
                "lon": lon_center,
            }

    # Sort by cell ID
    sorted_cells = sorted(cells_dict.values(), key=lambda c: c["id"])

    return {
        "step": STEP,
        "cells": sorted_cells,
    }
