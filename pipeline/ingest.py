"""Ingest paczek BDL (`Nadlesnictwa/`) do DuckDB + GeoParquet (spec E §2–3).

Wynik: `pipeline/data/bdl.duckdb` (tabele `district`, `subarea`, `storey_species`,
`arod_storey`, `g_subarea`), `pipeline/data/stands.parquet` (geometrie wydzieleń w EPSG:4326)
i `pipeline/data/nadlesnictwa.geojson` (obrysy nadleśnictw z `G_INSPECTORATE`).
Baza budowana od zera przy każdym uruchomieniu.
"""
import argparse
import io
import json
import re
import sys
import time
import zipfile
from pathlib import Path

import duckdb
import geopandas as gpd
import pandas as pd
import pyarrow.parquet as pq
import pyogrio

from pipeline.habitat import normalize_habitat, normalize_species_code

DATA_DIR = Path(__file__).resolve().parent / "data"
ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PACKAGES = ROOT / "Nadlesnictwa"
DEFAULT_DB = DATA_DIR / "bdl.duckdb"
DEFAULT_PARQUET = DATA_DIR / "stands.parquet"
DEFAULT_OUTLINE = DATA_DIR / "nadlesnictwa.geojson"

PKG_RE = re.compile(r"^BDL_(\d{2})_(\d{2})_(.+?)_(\d{4})\s*(\(\d+\))?(\.zip)?$", re.IGNORECASE)
PRODUCED_RE = re.compile(r"Data wytworzenia danych:\s*(\d{4}-\d{2}-\d{2})")
NAME_RE = re.compile(r"Nazwa nadle\S*:\s*(.+)")

TABLES = {
    "subarea": ("f_subarea", [
        "arodes_int_num", "a_year", "area_type_cd", "site_type_cd", "moisture_cd",
        "degradation_cd", "soil_subtype_cd", "plant_comm_cd", "stand_struct_cd",
        "forest_func_cd", "silviculture_cd", "rotation_age", "sub_area", "veg_cover_cd",
        "damage_degree", "cause_cd"]),
    "storey_species": ("f_storey_species", [
        "arodes_int_num", "a_year", "storey_cd", "sp_rank_order_act", "species_cd",
        "species_age", "part_cd_act", "site_class_cd", "height", "bhd", "volume"]),
    "arod_storey": ("f_arod_storey", [
        "arodes_int_num", "a_year", "density_cd", "mixture_cd", "standdensity_index",
        "tree_stock_cd", "st_rank_order_act", "storey_cd"]),
}
G_SUBAREA_COLS = ["a_i_num", "adr_for", "area_type", "site_type", "forest_fun",
                  "species_cd", "spec_age"]
PARTNER_STOREYS = ("DRZEW", "IP", "IIP")
MAIN_STOREYS = ("DRZEW", "IP")


class PackageError(Exception):
    """Paczka niekompletna lub uszkodzona."""


def warn(msg: str) -> None:
    print(f"UWAGA: {msg}", file=sys.stderr)


# --- dostęp do plików paczki (zip lub katalog) ---------------------------------------------

def _member(pkg: Path, filename: str) -> str:
    """Ścieżka pliku w paczce (zip: nazwa członka, katalog: ścieżka); szuka też w podfolderze."""
    want = filename.lower()
    if pkg.is_dir():
        hits = sorted(p for p in pkg.rglob("*") if p.is_file() and p.name.lower() == want)
        if hits:
            return str(hits[0])
    else:
        try:
            with zipfile.ZipFile(pkg) as zf:
                hits = sorted(n for n in zf.namelist() if n.rsplit("/", 1)[-1].lower() == want)
        except (zipfile.BadZipFile, OSError) as exc:
            raise PackageError(f"uszkodzony zip: {exc}") from exc
        if hits:
            return hits[0]
    raise PackageError(f"brak pliku {filename}")


def _read_bytes(pkg: Path, filename: str) -> bytes:
    member = _member(pkg, filename)
    if pkg.is_dir():
        return Path(member).read_bytes()
    try:
        with zipfile.ZipFile(pkg) as zf:
            return zf.read(member)
    except (zipfile.BadZipFile, OSError) as exc:
        raise PackageError(f"uszkodzony zip ({filename}): {exc}") from exc


def _gdal_path(pkg: Path, filename: str) -> str:
    member = _member(pkg, filename)
    return member if pkg.is_dir() else f"/vsizip/{pkg.resolve()}/{member}"


def read_table(pkg: Path, name: str) -> pd.DataFrame:
    """Czyta tabelę tekstową BDL (TAB, nagłówek, UTF-8); wartości obcięte, wszystko jako str,
    puste → None."""
    filename = name if name.lower().endswith(".txt") else f"{name}.txt"
    raw = _read_bytes(Path(pkg), filename)
    df = pd.read_csv(io.BytesIO(raw), sep="\t", dtype=str, keep_default_na=False,
                     encoding="utf-8-sig", quoting=3)
    df.columns = [c.strip() for c in df.columns]
    df = df.astype(object)
    for col in df.columns:
        s = df[col].str.strip()
        df[col] = s.where(s != "", None)
    return df


def read_metadata(pkg: Path) -> dict:
    text = _read_bytes(Path(pkg), "metadane.txt").decode("utf-8-sig", errors="replace")
    produced = PRODUCED_RE.search(text)
    name = NAME_RE.search(text)
    return {"produced_at": produced.group(1) if produced else None,
            "name": name.group(1).strip() if name else None}


# --- wybór paczek --------------------------------------------------------------------------

def find_candidates(root: Path) -> dict[str, list[Path]]:
    """`RR-NN` → paczki od najlepszej: najpóźniejsza data wytworzenia, przy remisie
    bez sufiksu `(1)`, dalej zip przed katalogiem."""
    candidates: dict[str, list[tuple]] = {}
    for p in sorted(Path(root).iterdir()):
        m = PKG_RE.match(p.name)
        if not m or not (p.is_dir() or p.suffix.lower() == ".zip"):
            continue
        prefix = f"{m.group(1)}-{m.group(2)}"
        try:
            produced = read_metadata(p)["produced_at"] or ""
        except Exception:  # noqa: BLE001 - uszkodzona paczka trafia na koniec listy
            produced = ""
        key = (produced, m.group(5) is None, p.is_file(), p.name)
        candidates.setdefault(prefix, []).append((key, p))
    return {prefix: [p for _, p in sorted(c, key=lambda kv: kv[0], reverse=True)]
            for prefix, c in sorted(candidates.items())}


def find_packages(root: Path) -> dict[str, Path]:
    """`RR-NN` → wybrana (najlepsza) paczka."""
    return {prefix: c[0] for prefix, c in find_candidates(root).items()}


# --- wczytanie jednej paczki ---------------------------------------------------------------

def _with_columns(df: pd.DataFrame, cols: list[str], prefix: str) -> pd.DataFrame:
    out = pd.DataFrame({c: df[c] if c in df.columns else None for c in cols}, dtype=object)
    out["arodes_int_num"] = pd.to_numeric(out["arodes_int_num"], errors="raise").astype("int64")
    out.insert(0, "prefix", prefix)
    return out


def _strip(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    s = str(v).strip()
    return s or None


def _dissolve_multipart(g: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Jedno wydzielenie = jeden rekord: obiekty o tym samym a_i_num łączone w jedną geometrię."""
    dup = g["a_i_num"].duplicated(keep=False)
    if not dup.any():
        return g
    merged = g[dup].dissolve(by="a_i_num", aggfunc="first", as_index=False)
    out = pd.concat([g[~dup], merged[g.columns]], ignore_index=True)
    return gpd.GeoDataFrame(out, geometry=g.geometry.name, crs=g.crs)


def _load_package(prefix: str, pkg: Path) -> dict:
    meta = read_metadata(pkg)
    tables = {table: _with_columns(read_table(pkg, fname), cols, prefix)
              for table, (fname, cols) in TABLES.items()}

    g = pyogrio.read_dataframe(_gdal_path(pkg, "G_SUBAREA.shp"), columns=G_SUBAREA_COLS)
    insp = pyogrio.read_dataframe(_gdal_path(pkg, "G_INSPECTORATE.shp"))
    if g.crs is None:
        g = g.set_crs(2180)
    if insp.crs is None:
        insp = insp.set_crs(2180)

    g = g[g.geometry.notna()].copy()
    g["a_i_num"] = g["a_i_num"].astype("int64")
    g = _dissolve_multipart(g)
    g["prefix"] = prefix
    g["id"] = g["adr_for"].astype(str).map(lambda v: re.sub(r"\s+", "", v))
    attrs = pd.DataFrame({
        "prefix": prefix,
        "a_i_num": g["a_i_num"].values,
        "id": g["id"].values,
        "area_type": [_strip(v) for v in g["area_type"]],
        "site_type": [_strip(v) for v in g["site_type"]],
        "forest_fun": [_strip(v) for v in g["forest_fun"]],
        "species_cd": [_strip(v) for v in g["species_cd"]],
        "spec_age": pd.array(pd.to_numeric(g["spec_age"], errors="coerce"), dtype="Int64"),
    })
    geo = gpd.GeoDataFrame(g[["a_i_num", "id", "prefix"]].reset_index(drop=True),
                           geometry=g.geometry.values, crs=g.crs).to_crs(4326)

    name = meta["name"]
    if not name and "i_name" in insp.columns and len(insp):
        name = _strip(insp["i_name"].iloc[0])
    outline = gpd.GeoDataFrame({"prefix": [prefix], "name": [name]},
                               geometry=[insp.to_crs(4326).geometry.union_all()], crs=4326)
    district = {"prefix": prefix, "name": name, "source": "package",
                "produced_at": meta["produced_at"], "package": pkg.name}
    return {"district": district, "tables": tables, "g_subarea": attrs, "geo": geo,
            "outline": outline}


def load_package(prefix: str, pkg: Path) -> dict:
    """Wczytuje paczkę; każdy błąd (brak pliku, zip, GDAL, wartości) → PackageError."""
    try:
        return _load_package(prefix, pkg)
    except PackageError:
        raise
    except Exception as exc:  # noqa: BLE001 - każdy błąd paczki = pominięcie
        raise PackageError(f"{type(exc).__name__}: {exc}") from exc


# --- zapis ---------------------------------------------------------------------------------

def _tmp(path: Path) -> Path:
    """Plik tymczasowy obok docelowego, z tym samym rozszerzeniem (wykrywanie sterownika)."""
    return path.with_name(f".{path.stem}.tmp{path.suffix}")


SCHEMA_SQL = ["CREATE TABLE district (prefix VARCHAR, name VARCHAR, source VARCHAR, "
              "produced_at DATE, package VARCHAR)"]
for _table, (_f, _cols) in TABLES.items():
    _defs = ", ".join(f"{c} BIGINT" if c == "arodes_int_num" else f"{c} VARCHAR" for c in _cols)
    SCHEMA_SQL.append(f"CREATE TABLE {_table} (prefix VARCHAR, {_defs})")
SCHEMA_SQL.append("CREATE TABLE g_subarea (prefix VARCHAR, a_i_num BIGINT, id VARCHAR, "
                  "area_type VARCHAR, site_type VARCHAR, forest_fun VARCHAR, "
                  "species_cd VARCHAR, spec_age INTEGER)")


def _insert_package(con, part: dict) -> None:
    con.execute("BEGIN TRANSACTION")
    try:
        d = part["district"]
        con.execute("INSERT INTO district VALUES (?, ?, ?, CAST(? AS DATE), ?)",
                    [d["prefix"], d["name"], d["source"], d["produced_at"], d["package"]])
        frames = dict(part["tables"], g_subarea=part["g_subarea"])
        for table, df in frames.items():
            con.register("pkg_df", df)
            con.execute(f"INSERT INTO {table} BY NAME SELECT * FROM pkg_df")
            con.unregister("pkg_df")
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise


class _GeoParquetWriter:
    """Dopisuje kolejne GeoDataFrame (EPSG:4326) do jednego pliku GeoParquet."""

    def __init__(self, path: Path):
        self.path = path
        self.writer = None
        self.schema = None

    def write(self, gdf: gpd.GeoDataFrame) -> None:
        buf = io.BytesIO()
        gdf.to_parquet(buf, index=False, write_covering_bbox=False)
        buf.seek(0)
        table = pq.read_table(buf)
        if self.writer is None:
            meta = dict(table.schema.metadata or {})
            geo = json.loads(meta[b"geo"])
            for col in geo["columns"].values():
                col.pop("bbox", None)
                col["geometry_types"] = []
            meta[b"geo"] = json.dumps(geo).encode()
            self.schema = table.schema.with_metadata(meta)
            self.writer = pq.ParquetWriter(self.path, self.schema)
        self.writer.write_table(table.cast(self.schema))

    def close(self) -> None:
        if self.writer is not None:
            self.writer.close()


def ingest(root: Path, db_path: Path, parquet_path: Path, outline_path: Path) -> dict:
    """Wczytuje wszystkie paczki z `root` paczka po paczce (zapis przyrostowy do DuckDB
    i GeoParquet); zwraca statystyki per prefix (tylko wczytane). Gdy wybrana paczka jest
    uszkodzona, próbuje kolejnego kandydata dla tego nadleśnictwa."""
    db_path, parquet_path, outline_path = Path(db_path), Path(parquet_path), Path(outline_path)
    for path in (db_path, parquet_path, outline_path):
        path.parent.mkdir(parents=True, exist_ok=True)
    tmp_db, tmp_pq, tmp_outline = _tmp(db_path), _tmp(parquet_path), _tmp(outline_path)
    for t in (tmp_db, Path(str(tmp_db) + ".wal"), tmp_pq, tmp_outline):
        t.unlink(missing_ok=True)

    stats, outlines = {}, []
    con = duckdb.connect(str(tmp_db))
    writer = _GeoParquetWriter(tmp_pq)
    try:
        for sql in SCHEMA_SQL:
            con.execute(sql)
        for prefix, candidates in find_candidates(root).items():
            for pkg in candidates:
                try:
                    part = load_package(prefix, pkg)
                    _insert_package(con, part)
                except Exception as exc:  # noqa: BLE001
                    warn(f"{prefix} ({pkg.name}) pominięte: {exc}")
                    continue
                writer.write(part["geo"])
                outlines.append(part["outline"])
                sub = part["tables"]["subarea"]
                stats[prefix] = {
                    "name": part["district"]["name"],
                    "package": pkg.name,
                    "produced_at": part["district"]["produced_at"],
                    "subareas": len(sub),
                    "d_stan": int((sub["area_type_cd"] == "D-STAN").sum()),
                    "geometries": len(part["geo"]),
                }
                del part
                break
    finally:
        con.close()
        writer.close()

    if not stats:
        for t in (tmp_db, tmp_pq):
            t.unlink(missing_ok=True)
        return stats

    gpd.GeoDataFrame(pd.concat(outlines, ignore_index=True), geometry="geometry",
                     crs=4326).to_file(tmp_outline, driver="GeoJSON")
    Path(str(db_path) + ".wal").unlink(missing_ok=True)
    tmp_db.replace(db_path)
    tmp_pq.replace(parquet_path)
    tmp_outline.replace(outline_path)
    return stats


# --- odczyt wydzieleń ----------------------------------------------------------------------

STANDS_SQL = f"""
WITH ss AS (
    SELECT prefix, arodes_int_num, storey_cd, species_cd, part_cd_act,
           TRY_CAST(sp_rank_order_act AS INTEGER) AS rnk,
           TRY_CAST(species_age AS INTEGER) AS age
    FROM storey_species
    WHERE storey_cd IN {PARTNER_STOREYS} AND species_cd IS NOT NULL
),
dom AS (
    SELECT prefix, arodes_int_num, storey_cd, species_cd, age FROM ss
    WHERE rnk = 1 AND storey_cd IN {MAIN_STOREYS}
    QUALIFY row_number() OVER (PARTITION BY prefix, arodes_int_num
                               ORDER BY CASE storey_cd WHEN 'DRZEW' THEN 0 ELSE 1 END) = 1
),
part AS (
    SELECT ss.prefix, ss.arodes_int_num,
           list(struct_pack(sp := ss.species_cd, share := ss.part_cd_act, age := ss.age)
                ORDER BY CASE ss.storey_cd WHEN 'DRZEW' THEN 0 WHEN 'IP' THEN 1 ELSE 2 END,
                         ss.rnk) AS partners
    FROM ss
    GROUP BY ALL
)
SELECT g.prefix, g.a_i_num,
       COALESCE(dom.species_cd, g.species_cd) AS sp_main,
       CASE WHEN dom.species_cd IS NOT NULL THEN dom.age ELSE g.spec_age END AS age,
       COALESCE(s.site_type_cd, g.site_type) AS hab,
       COALESCE(s.forest_func_cd, g.forest_fun) AS fun,
       CASE WHEN dom.species_cd IS NOT NULL THEN part.partners END AS partners
FROM g_subarea g
LEFT JOIN subarea s ON s.prefix = g.prefix AND s.arodes_int_num = g.a_i_num
LEFT JOIN dom ON dom.prefix = g.prefix AND dom.arodes_int_num = g.a_i_num
LEFT JOIN part ON part.prefix = g.prefix AND part.arodes_int_num = g.a_i_num
WHERE COALESCE(s.area_type_cd, g.area_type) = 'D-STAN'
  AND COALESCE(dom.species_cd, g.species_cd) IS NOT NULL
"""


def _partners(items) -> tuple:
    if items is None or items is pd.NA or isinstance(items, float):
        return ()
    out = []
    for it in items:
        age = it["age"]
        age = None if age is None or pd.isna(age) else int(age)
        out.append((normalize_species_code(it["sp"]), it["share"], age))
    return tuple(out)


def load_stands(db_path: Path, parquet_path: Path) -> gpd.GeoDataFrame:
    """Drzewostany (D-STAN z gatunkiem panującym) z bazy + geometrie; EPSG:4326.

    Kolumny: id, sp_main, sp_admix (kody partnerów bez panującego), partners
    (tuple[(gatunek, kod udziału, wiek|None)]), age, hab, fun, prefix, geometry.
    """
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        attrs = con.execute(STANDS_SQL).df()
    finally:
        con.close()
    geo = gpd.read_parquet(parquet_path)
    df = geo.merge(attrs, on=["prefix", "a_i_num"], how="inner")

    sp_main = df["sp_main"].map(normalize_species_code)
    # partnerzy bez żadnego wiersza gatunku panującego (w dowolnym piętrze)
    partners = [tuple(p for p in _partners(v) if p[0] != m)
                for v, m in zip(df["partners"], sp_main)]
    sp_admix = [tuple(dict.fromkeys(p[0] for p in ps)) for ps in partners]
    out = gpd.GeoDataFrame(
        {
            "id": df["id"].values,
            "sp_main": sp_main.values,
            "sp_admix": pd.Series(sp_admix, dtype=object).values,
            "partners": pd.Series(partners, dtype=object).values,
            "age": pd.array(pd.to_numeric(df["age"], errors="coerce"), dtype="Int64"),
            "hab": [normalize_habitat(None if v is None or pd.isna(v) else str(v))
                    for v in df["hab"]],
            "fun": pd.Series([None if v is None or pd.isna(v) else v for v in df["fun"]],
                             dtype=object).values,
            "prefix": df["prefix"].values,
        },
        geometry=df.geometry.values,
        crs=4326,
    )
    out = out[out["sp_main"] != ""]
    return out.drop_duplicates(subset="id").reset_index(drop=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--packages", type=Path, default=DEFAULT_PACKAGES)
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    ap.add_argument("--parquet", type=Path, default=DEFAULT_PARQUET)
    ap.add_argument("--outline", type=Path, default=DEFAULT_OUTLINE)
    args = ap.parse_args(argv)

    t0 = time.monotonic()
    stats = ingest(args.packages, args.db, args.parquet, args.outline)
    if not stats:
        print(f"BŁĄD: nie wczytano żadnej paczki z {args.packages}", file=sys.stderr)
        return 1
    for prefix, s in stats.items():
        print(f"{prefix} {s['name']}: {s['subareas']} wydzieleń, D-STAN {s['d_stan']}")
    total = sum(s["d_stan"] for s in stats.values())
    print(f"nadleśnictw: {len(stats)}, D-STAN: {total}, czas: {time.monotonic() - t0:.1f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
