"""
Memoria del radar: qué ofertas ya revisó, para no avisarte dos veces lo mismo.

Se guarda en datos/vistos.json como { "id_de_oferta": "fecha en que se vio" }.
GitHub Actions lo vuelve a subir al repo después de cada corrida.
Solo guarda ids de avisos públicos: nada personal.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

DIAS_DE_MEMORIA = 90  # después de esto se olvida (los avisos viejos ya no aparecen)


class Vistos:
    def __init__(self, ruta: str | Path):
        self.ruta = Path(ruta)
        self.datos: dict[str, str] = json.loads(self.ruta.read_text()) if self.ruta.exists() else {}

    def ya_visto(self, oferta_id: str) -> bool:
        return oferta_id in self.datos

    def marcar(self, oferta_id: str, hoy: date) -> None:
        self.datos[oferta_id] = hoy.isoformat()

    def guardar(self, hoy: date) -> None:
        limite = (hoy - timedelta(days=DIAS_DE_MEMORIA)).isoformat()
        self.datos = {k: v for k, v in self.datos.items() if v >= limite}
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        self.ruta.write_text(json.dumps(self.datos, indent=0, sort_keys=True) + "\n")
