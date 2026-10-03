"""Teren z Copernicus DEM GLO-30 (spec I): TWI, nachylenie i wystawa dla wydzieleń -> terrain.parquet.

Część pierwsza: czyste funkcje rastrowe (numpy + pysheds), testowane na syntetycznych DEM.
"""
import numpy as np

# pysheds 0.5 używa np.in1d, usuniętego w numpy 2.x — nakładka zgodności przed importem.
if not hasattr(np, "in1d"):
    np.in1d = np.isin

from affine import Affine  # noqa: E402
from pysheds.grid import Grid  # noqa: E402
from pysheds.sview import Raster, ViewFinder  # noqa: E402

PIXEL_M = 30.0
MIN_SLOPE_DEG = 0.1
STEEP_DEG = 10.0
SOUTH = (135.0, 225.0)
NODATA = -9999.0


def _masked(dem: np.ndarray, nodata: float | None) -> np.ndarray:
    a = np.asarray(dem, dtype=np.float64).copy()
    if nodata is not None:
        a[a == nodata] = np.nan
    return a


def slope_aspect(dem: np.ndarray, pixel: float = PIXEL_M,
                 nodata: float | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Nachylenie (°) i wystawa (0–360°, 0 = N, zgodnie z ruchem wskazówek); wiersz 0 = północ."""
    z = _masked(dem, nodata)
    dz_drow, dz_dcol = np.gradient(z, pixel)
    dz_east, dz_north = dz_dcol, -dz_drow
    slope = np.degrees(np.arctan(np.hypot(dz_east, dz_north)))
    # kierunek spadku: wektor -grad; kąt od północy zgodnie z ruchem wskazówek
    aspect = (np.degrees(np.arctan2(-dz_east, -dz_north)) + 360.0) % 360.0
    return slope, aspect


def flow_accumulation(dem: np.ndarray, nodata: float | None = None) -> np.ndarray:
    """Akumulacja spływu D8 (liczba komórek powyżej) po wypełnieniu zagłębień; NoData -> nan."""
    z = _masked(dem, nodata)
    mask = np.isnan(z)
    filled_in = np.where(mask, NODATA, z)
    vf = ViewFinder(affine=Affine(PIXEL_M, 0, 0, 0, -PIXEL_M, PIXEL_M * z.shape[0]),
                    shape=z.shape, nodata=np.float64(NODATA))
    grid = Grid(viewfinder=vf)
    r = Raster(filled_in, vf)
    flat = grid.resolve_flats(grid.fill_depressions(grid.fill_pits(r)))
    acc = np.asarray(grid.accumulation(grid.flowdir(flat)), dtype=np.float64)
    acc[mask] = np.nan
    return acc


def twi(acc: np.ndarray, slope_deg: np.ndarray, pixel: float = PIXEL_M) -> np.ndarray:
    """TWI = ln(a / tan β), a = (akumulacja + 1) × piksel; tan β ograniczone od dołu."""
    a = (acc + 1.0) * pixel
    tanb = np.maximum(np.tan(np.radians(slope_deg)), np.tan(np.radians(MIN_SLOPE_DEG)))
    with np.errstate(invalid="ignore"):
        return np.log(a / tanb)


def circular_mean_deg(sin_mean: float, cos_mean: float) -> float:
    return float((np.degrees(np.arctan2(sin_mean, cos_mean)) + 360.0) % 360.0)


def twi_classes(values: np.ndarray) -> tuple[list[str], tuple[float, float]]:
    """Klasy DRY/MID/WET wg tercyli (≤ t1 -> DRY, > t2 -> WET) i progi (t1, t2)."""
    v = np.asarray(values, dtype=np.float64)
    t1, t2 = (float(x) for x in np.nanquantile(v, [1 / 3, 2 / 3]))
    classes = ["DRY" if x <= t1 else "WET" if x > t2 else "MID" for x in v]
    return classes, (t1, t2)


def exposure_class(slope_deg: float, aspect_deg: float) -> str:
    """S_STEEP: stromy (> 10°) stok południowy (wystawa 135–225°)."""
    if slope_deg > STEEP_DEG and SOUTH[0] <= aspect_deg <= SOUTH[1]:
        return "S_STEEP"
    return "OTHER"
