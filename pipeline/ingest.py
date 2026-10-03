"""Ingest paczek BDL (`Nadlesnictwa/`) do DuckDB + GeoParquet (spec E §2–3).

Wynik: `pipeline/data/bdl.duckdb` (tabele `district`, `subarea`, `storey_species`,
`arod_storey`, `g_subarea`), `pipeline/data/stands.parquet` (geometrie wydzieleń w EPSG:4326)
i `pipeline/data/nadlesnictwa.geojson` (obrysy nadleśnictw z `G_INSPECTORATE`).
Baza budowana od zera przy każdym uruchomieniu.
"""
import argparse
import io
import re
import sys
import time
import zipfile
from pathlib import Path

import duckdb
import geopandas as gpd
import pandas as pd
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

def find_packages(root: Path) -> dict[str, Path]:
    """`RR-NN` → wybrana paczka. Duplikaty: najpóźniejsza data wytworzenia, przy remisie
    bez sufiksu `(1)`, dalej zip przed katalogiem."""
    candidates: dict[str, list[tuple]] = {}
    for p in sorted(Path(root).iterdir()):
        m = PKG_RE.match(p.name)
        if not m or not (p.is_dir() or p.suffix.lower() == ".zip"):
            continue
        prefix = f"{m.group(1)}-{m.group(2)}"
        try:
            produced = read_metadata(p)["produced_at"] or ""
        except PackageError:
            produced = ""
        key = (produced, m.group(5) is None, p.is_file())
        candidates.setdefault(prefix, []).append((key, p))
    return {prefix: max(c, key=lambda kv: kv[0])[1] for prefix, c in sorted(candidates.items())}


# --- wczytanie jednej paczki ---------------------------------------------------------------

def _with_columns(df: pd.DataFrame, cols: list[str], prefix: str) -> pd.DataFrame:
    out = pd.DataFrame({c: df[c] if c in df.columns else None for c in cols}, dtype=object)
    out.insert(0, "prefix", prefix)
    return out


def load_package(prefix: str, pkg: Path) -> dict:
    meta = read_metadata(pkg)
    tables = {}
    for table, (fname, cols) in TABLES.items():
        tables[table] = _with_columns(read_table(pkg, fname), cols, prefix)

    try:
        g = pyogrio.read_dataframe(_gdal_path(pkg, "G_SUBAREA.shp"), columns=G_SUBAREA_COLS)
        insp = pyogrio.read_dataframe(_gdal_path(pkg, "G_INSPECTORATE.shp"))
    except PackageError:
        raise
    except Exception as exc:  # noqa: BLE001 - błąd GDAL = uszkodzona paczka
        raise PackageError(f"nie można odczytać shapefile: {exc}") from exc
    if g.crs is None:
        g = g.set_crs(2180)
    if insp.crs is None:
        insp = insp.set_crs(2180)

    g = g[g.geometry.notna()].copy()
    g["prefix"] = prefix
    g["id"] = g["adr_for"].astype(str).map(lambda v: re.sub(r"\s+", "", v))
    g["a_i_num"] = g["a_i_num"].astype("int64")
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
    geo = gpd.GeoDataFrame(g[["a_i_num", "id", "prefix"]], geometry=g.geometry.values,
                           crs=g.crs).to_crs(4326)

    name = meta["name"]
    if not name and "i_name" in insp.columns and len(insp):
        name = _strip(insp["i_name"].iloc[0])
    outline = gpd.GeoDataFrame({"prefix": [prefix], "name": [name]},
                               geometry=[insp.to_crs(4326).geometry.union_all()], crs=4326)
    district = {"prefix": prefix, "name": name, "source": "package",
                "produced_at": meta["produced_at"], "package": pkg.name}
    return {"district": district, "tables": tables, "g_subarea": attrs, "geo": geo,
            "outline": outline}


def _strip(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    s = str(v).strip()
    return s or None


# --- zapis ---------------------------------------------------------------------------------

def _write_db(db_path: Path, parts: list[dict]) -> None:
    tmp = db_path.with_name(db_path.name + ".tmp")
    tmp.unlink(missing_ok=True)
    con = duckdb.connect(str(tmp))
    try:
        district = pd.DataFrame([p["district"] for p in parts])
        con.register("district_df", district)
        con.execute("CREATE TABLE district AS SELECT prefix, name, source, "
                    "CAST(produced_at AS DATE) AS produced_at, package FROM district_df")
        for table in TABLES:
            df = pd.concat([p["tables"][table] for p in parts], ignore_index=True)
            con.register("t_df", df)
            con.execute(f"CREATE TABLE {table} AS SELECT * REPLACE "
                        f"(CAST(arodes_int_num AS BIGINT) AS arodes_int_num) FROM t_df")
            con.unregister("t_df")
        gs = pd.concat([p["g_subarea"] for p in parts], ignore_index=True)
        con.register("g_df", gs)
        con.execute("CREATE TABLE g_subarea AS SELECT * FROM g_df")
    finally:
        con.close()
    db_path.unlink(missing_ok=True)
    Path(str(db_path) + ".wal").unlink(missing_ok=True)
    tmp.replace(db_path)


def ingest(root: Path, db_path: Path, parquet_path: Path, outline_path: Path) -> dict:
    """Wczytuje wszystkie paczki z `root`; zwraca statystyki per prefix (tylko wczytane)."""
    parts, stats = [], {}
    for prefix, pkg in find_packages(Path(root)).items():
        try:
            part = load_package(prefix, pkg)
        except PackageError as exc:
            warn(f"{prefix} ({pkg.name}) pominięte: {exc}")
            continue
        sub = part["tables"]["subarea"]
        stats[prefix] = {
            "name": part["district"]["name"],
            "package": pkg.name,
            "produced_at": part["district"]["produced_at"],
            "subareas": len(sub),
            "d_stan": int((sub["area_type_cd"] == "D-STAN").sum()),
            "geometries": len(part["geo"]),
        }
        parts.append(part)
    if not parts:
        return stats

    for path in (db_path, parquet_path, outline_path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    _write_db(Path(db_path), parts)
    geo = pd.concat([p["geo"] for p in parts], ignore_index=True)
    gpd.GeoDataFrame(geo, geometry="geometry", crs=4326).to_parquet(parquet_path, index=False)
    outline = pd.concat([p["outline"] for p in parts], ignore_index=True)
    outline_path = Path(outline_path)
    outline_path.unlink(missing_ok=True)
    gpd.GeoDataFrame(outline, geometry="geometry", crs=4326).to_file(outline_path,
                                                                     driver="GeoJSON")
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
    FROM ss LEFT JOIN dom USING (prefix, arodes_int_num)
    WHERE ss.storey_cd IS DISTINCT FROM dom.storey_cd OR ss.rnk IS DISTINCT FROM 1
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
    partners = [_partners(v) for v in df["partners"]]
    sp_admix = [tuple(dict.fromkeys(p[0] for p in ps if p[0] != m))
                for ps, m in zip(partners, sp_main)]
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
