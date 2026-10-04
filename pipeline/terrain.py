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


# --- część druga: kafle GLO-30, okna rastra, statystyki dla wydzieleń, CLI ---

import argparse  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import sys  # noqa: E402
from pathlib import Path  # noqa: E402

import geopandas as gpd  # noqa: E402
import pandas as pd  # noqa: E402
import pyarrow as pa  # noqa: E402
import pyarrow.parquet as pq  # noqa: E402
import requests  # noqa: E402
from rasterio import features  # noqa: E402
from rasterio.transform import rowcol  # noqa: E402
from rasterio.merge import merge  # noqa: E402
from rasterio.warp import Resampling, reproject  # noqa: E402
from shapely.geometry import box  # noqa: E402

DATA_DIR = Path(__file__).resolve().parent / "data"
DEM_URL = ("https://copernicus-dem-30m.s3.amazonaws.com/Copernicus_DSM_COG_10_N{lat:02d}_00_E{lon:03d}_00_DEM/"
           "Copernicus_DSM_COG_10_N{lat:02d}_00_E{lon:03d}_00_DEM.tif")
DEFAULT_OUT = DATA_DIR / "terrain.parquet"
DEFAULT_CACHE = DATA_DIR / "raw" / "dem"
BUFFER_M = 2000
CRS = "EPSG:2180"


def tile_names(bounds: tuple[float, float, float, float]) -> list[tuple[int, int]]:
    """(lat, lon) kafli 1°×1° przecinających bbox (minx, miny, maxx, maxy) w stopniach."""
    minx, miny, maxx, maxy = bounds
    return [(la, lo) for la in range(math.floor(miny), math.ceil(maxy))
            for lo in range(math.floor(minx), math.ceil(maxx))]


def download_tiles(tiles, cache_dir: Path, *, refresh: bool = False, session=None) -> list[Path]:
    """Pobiera kafle do cache_dir/N<lat>_E<lon>.tif; brak kafla (404) -> pominięty z ostrzeżeniem."""
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    http = session or requests
    out = []
    for lat, lon in tiles:
        path = cache_dir / f"N{lat:02d}_E{lon:03d}.tif"
        if path.exists() and not refresh:
            out.append(path)
            continue
        r = http.get(DEM_URL.format(lat=lat, lon=lon), stream=True, timeout=120)
        if r.status_code == 404:
            print(f"Uwaga: brak kafla GLO-30 N{lat} E{lon}", file=sys.stderr)
            continue
        r.raise_for_status()
        part = path.with_suffix(".part")
        with part.open("wb") as fh:
            for chunk in r.iter_content(1 << 20):
                fh.write(chunk)
        part.replace(path)
        out.append(path)
    return out


def window_dem(paths: list[Path], bounds_2180: tuple[float, float, float, float]):
    """DEM w EPSG:2180, piksel 30 m, dla prostokąta bounds_2180; brak danych -> NODATA."""
    minx, miny, maxx, maxy = bounds_2180
    geo = gpd.GeoSeries([box(*bounds_2180)], crs=CRS).to_crs(4326).total_bounds
    src, src_tr = merge([str(p) for p in paths], bounds=tuple(geo), nodata=NODATA)
    w, h = int(math.ceil((maxx - minx) / PIXEL_M)), int(math.ceil((maxy - miny) / PIXEL_M))
    dst = np.full((h, w), NODATA, dtype=np.float64)
    tr = Affine(PIXEL_M, 0, minx, 0, -PIXEL_M, maxy)
    reproject(src[0].astype(np.float64), dst, src_transform=src_tr, src_crs="EPSG:4326",
              src_nodata=NODATA, dst_transform=tr, dst_crs=CRS, dst_nodata=NODATA,
              resampling=Resampling.bilinear)
    return dst, tr


def zonal(stands_2180: gpd.GeoDataFrame, twi: np.ndarray, slope: np.ndarray, aspect: np.ndarray,
          transform) -> pd.DataFrame:
    """Mediana TWI, średnie nachylenie i kołowa średnia wystawy dla wydzieleń.

    Raster etykiet (piksel należy do wydzielenia, którego poligon zawiera środek piksela);
    wydzielenie bez własnego piksela (mniejsze niż 30 m) dostaje wartości piksela pod swoim
    punktem reprezentatywnym. Piksele bez danych (nan) są pomijane."""
    n = len(stands_2180)
    shape = twi.shape
    labels = features.rasterize(((g, i + 1) for i, g in enumerate(stands_2180.geometry)),
                                out_shape=shape, transform=transform, fill=0, dtype="int32")
    rad = np.radians(aspect)
    valid = (labels > 0) & np.isfinite(twi) & np.isfinite(slope) & np.isfinite(aspect)
    df = pd.DataFrame({"l": labels[valid], "twi": twi[valid], "slope": slope[valid],
                       "sin": np.sin(rad[valid]), "cos": np.cos(rad[valid])})
    g = df.groupby("l")
    stats = pd.DataFrame({"twi": g["twi"].median(), "slope": g["slope"].mean(),
                          "sin": g["sin"].mean(), "cos": g["cos"].mean()})
    missing = [i for i in range(1, n + 1) if i not in stats.index]
    if missing:
        rows = []
        for i in missing:
            p = stands_2180.geometry.iloc[i - 1].representative_point()
            r, c = rowcol(transform, p.x, p.y)
            if 0 <= r < shape[0] and 0 <= c < shape[1] and np.isfinite(twi[r, c]):
                a = math.radians(aspect[r, c])
                rows.append((i, twi[r, c], slope[r, c], math.sin(a), math.cos(a)))
        if rows:
            extra = pd.DataFrame(rows, columns=["l", "twi", "slope", "sin", "cos"]).set_index("l")
            stats = pd.concat([stats, extra])
    idx = stats.index.to_numpy() - 1
    return pd.DataFrame({
        "prefix": stands_2180["prefix"].to_numpy()[idx],
        "a_i_num": stands_2180["a_i_num"].to_numpy()[idx],
        "twi": stats["twi"].to_numpy(),
        "slope": stats["slope"].to_numpy(),
        "aspect": [circular_mean_deg(s, c) for s, c in zip(stats["sin"], stats["cos"])],
    }).sort_values(["prefix", "a_i_num"]).reset_index(drop=True)


def terrain_for_tile(paths, core_2180, stands_2180: gpd.GeoDataFrame) -> pd.DataFrame:
    """Statystyki dla wydzieleń przypisanych do kafla (okno = kafel + BUFFER_M, żeby spływ
    z sąsiedztwa nie był ucięty)."""
    minx, miny, maxx, maxy = core_2180.bounds
    bounds = (minx - BUFFER_M, miny - BUFFER_M, maxx + BUFFER_M, maxy + BUFFER_M)
    dem, tr = window_dem(paths, bounds)
    slope, aspect = slope_aspect(dem, nodata=NODATA)
    t = twi(flow_accumulation(dem, nodata=NODATA), slope)
    return zonal(stands_2180, t, slope, aspect, tr)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    ap.add_argument("--parquet", type=Path, default=DATA_DIR / "stands.parquet")
    ap.add_argument("--area", type=Path, default=DATA_DIR / "obszar.geojson")
    args = ap.parse_args(argv)

    area = gpd.read_file(args.area).to_crs(4326)
    stands = gpd.read_parquet(args.parquet)[["prefix", "a_i_num", "geometry"]]
    stands = stands.drop_duplicates(["prefix", "a_i_num"]).reset_index(drop=True)
    pts = stands.geometry.to_crs(4326).representative_point()
    stands_2180 = stands.to_crs(CRS)
    shape = area.union_all()
    parts = []
    for lat, lon in tile_names(tuple(area.total_bounds)):
        core = box(lon, lat, lon + 1, lat + 1)
        if not core.intersects(shape):
            continue
        # kafel liczy wydzielenia, których punkt reprezentatywny leży w nim (każde dokładnie raz)
        sel = (pts.x >= lon) & (pts.x < lon + 1) & (pts.y >= lat) & (pts.y < lat + 1)
        if not sel.any():
            continue
        lats = range(lat - 1, lat + 2)
        lons = range(lon - 1, lon + 2)
        paths = download_tiles([(a, o) for a in lats for o in lons], args.cache, refresh=args.refresh)
        if not paths:
            continue
        core_2180 = gpd.GeoSeries([core], crs=4326).to_crs(CRS).iloc[0]
        print(f"teren: kafel N{lat} E{lon}, wydzieleń {int(sel.sum())}", file=sys.stderr)
        parts.append(terrain_for_tile(paths, core_2180, stands_2180[sel.to_numpy()].reset_index(drop=True)))
    df = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(
        columns=["prefix", "a_i_num", "twi", "slope", "aspect"])
    classes, terciles = twi_classes(df["twi"].to_numpy()) if len(df) else ([], (math.nan, math.nan))
    df["twi_class"] = classes
    df["exposure"] = [exposure_class(s, a) for s, a in zip(df["slope"], df["aspect"])]
    table = pa.Table.from_pandas(df, preserve_index=False)
    meta = {**(table.schema.metadata or {}),
            b"twi_terciles": json.dumps([round(t, 4) for t in terciles]).encode(), b"dem": b"GLO-30"}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.out.with_suffix(".tmp")
    pq.write_table(table.replace_schema_metadata(meta), tmp)
    tmp.replace(args.out)
    print(f"teren: {len(df)} z {len(stands)} wydzieleń ({len(df) / max(len(stands), 1):.1%}), "
          f"tercyle TWI {terciles}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
