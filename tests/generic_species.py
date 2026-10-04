"""Gatunki z species.yaml z borowikiem w wersji sprzed specu L (bez wag partnerów i własnego runa/zadrzewienia).

Testy mechaniki siedliska używają borowika jako typowego gatunku; jego nowe, eksperckie parametry (spec L §1b)
mają osobne testy w test_habitat.py.
"""
import dataclasses

from forecast.species import load_species


def generic_species():
    s = load_species()
    defaults = s["podgrzybek"].factors  # podgrzybek ma domyślne veg/density
    b = s["borowik"]
    s["borowik"] = dataclasses.replace(
        b, partner_weights={},
        factors={**b.factors, "veg": defaults["veg"], "density": defaults["density"]})
    return s
