import json

import pytest
import yaml

from pipeline import species_info
from pipeline.species_info import CONTENT_PATH, OUT_PATH, SPECIES_PATH, build_info, format_season

SPECIES = {"species": {
    "b": {"name": "B", "partners": ["SO", "BRZ"], "age": {"min": 30},
          "habitat": {"preferred": ["BSW"], "adjacent": ["LMWYZW"]},
          "season": {"start": "07-01", "end": "10-31"}},
    "a": {"name": "A", "partners": ["SW"], "age": {"min": 5},
          "habitat": {"preferred": ["BMSW"], "adjacent": []},
          "season": {"start": "06-01", "end": "11-30"}},
}}
CONTENT = {
    "reviewed": False,
    "codes": {"trees": {"SO": "sosna", "SW": "świerk", "BRZ": "brzoza"},
              "habitats": {"BSW": "bór świeży", "BMSW": "bór mieszany świeży",
                           "LMWYZW": "las mieszany wyżynny wilgotny"}},
    "species": {
        "a": {"latin": "La", "wiki": "https://pl.wikipedia.org/wiki/A", "description": "Da.",
              "lookalikes": []},
        "b": {"latin": "Lb", "wiki": "https://pl.wikipedia.org/wiki/B", "description": "Db.",
              "lookalikes": [{"name": "X", "latin": "Lx", "risk": "trujący", "how": "H."}]},
    },
}


def test_format_season():
    assert format_season("07-01", "10-31") == "1 lip – 31 paź"
    assert format_season("01-05", "12-09") == "5 sty – 9 gru"


def test_build_info_translates_and_keeps_order():
    out = build_info(SPECIES, CONTENT)
    assert out["reviewed"] is False
    assert [s["key"] for s in out["species"]] == ["b", "a"]
    b = out["species"][0]
    assert b == {
        "key": "b", "name": "B", "latin": "Lb",
        "season": {"start": "07-01", "end": "10-31"},
        "partners": ["sosna", "brzoza"],
        "habitats_preferred": ["bór świeży"],
        "habitats_adjacent": ["las mieszany wyżynny wilgotny"],
        "age_min": 30, "description": "Db.",
        "lookalikes": [{"name": "X", "latin": "Lx", "risk": "trujący", "how": "H."}],
        "wiki": "https://pl.wikipedia.org/wiki/B",
    }


def test_build_info_missing_code_raises():
    content = json.loads(json.dumps(CONTENT))
    del content["codes"]["habitats"]["LMWYZW"]
    with pytest.raises((KeyError, ValueError), match="LMWYZW"):
        build_info(SPECIES, content)
    content = json.loads(json.dumps(CONTENT))
    del content["codes"]["trees"]["BRZ"]
    with pytest.raises((KeyError, ValueError), match="BRZ"):
        build_info(SPECIES, content)


def test_build_info_missing_species_content_raises():
    content = json.loads(json.dumps(CONTENT))
    del content["species"]["a"]
    with pytest.raises((KeyError, ValueError), match="brak treści gatunku: a"):
        build_info(SPECIES, content)


@pytest.mark.parametrize("field", ["name", "latin", "risk", "how"])
def test_build_info_rejects_empty_lookalike_field(field):
    content = json.loads(json.dumps(CONTENT))
    content["species"]["b"]["lookalikes"][0][field] = " "
    with pytest.raises(ValueError, match=f"b: .*{field}"):
        build_info(SPECIES, content)


def test_build_info_rejects_missing_lookalike_field():
    content = json.loads(json.dumps(CONTENT))
    del content["species"]["b"]["lookalikes"][0]["how"]
    with pytest.raises(ValueError, match="b: .*how"):
        build_info(SPECIES, content)


def test_build_info_rejects_bad_risk():
    content = json.loads(json.dumps(CONTENT))
    content["species"]["b"]["lookalikes"][0]["risk"] = "groźny"
    with pytest.raises(ValueError, match="groźny"):
        build_info(SPECIES, content)


def _load(path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_content_covers_constraints():
    content = _load(CONTENT_PATH)
    assert isinstance(content["reviewed"], bool)
    sp = content["species"]
    assert sp["borowik"]["latin"] == "Boletus edulis"
    assert sp["podgrzybek"]["latin"] == "Imleria badia"
    assert sp["kurka"]["latin"] == "Cantharellus cibarius"
    assert sp["kozlarz"]["latin"] == "Leccinum scabrum"
    assert sp["maslak"]["latin"] == "Suillus luteus"
    assert sp["rydz"]["latin"] == "Lactarius deliciosus"
    latins = {k: {lk["latin"] for lk in v["lookalikes"]} for k, v in sp.items()}
    assert {"Tylopilus felleus", "Rubroboletus satanas"} <= latins["borowik"]
    assert "Tylopilus felleus" in latins["podgrzybek"]
    assert "Tylopilus felleus" in latins["kozlarz"]
    assert "Hygrophoropsis aurantiaca" in latins["kurka"]
    assert "Lactarius torminosus" in latins["rydz"]
    assert sp["maslak"]["lookalikes"] == []
    for v in sp.values():
        assert v["wiki"].startswith("https://pl.wikipedia.org/wiki/")


def test_generated_file_is_up_to_date():
    expected = build_info(_load(SPECIES_PATH), _load(CONTENT_PATH))
    assert json.loads(OUT_PATH.read_text(encoding="utf-8")) == expected


def test_main_writes_file(tmp_path):
    out = tmp_path / "g.json"
    assert species_info.main(["--out", str(out)]) == 0
    assert json.loads(out.read_text(encoding="utf-8"))["species"][0]["key"] == "borowik"
