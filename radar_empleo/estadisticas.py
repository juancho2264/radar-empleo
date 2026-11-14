"""
Estadísticas del día: el radar corre varias veces por día y acá acumula los números
de todas las corridas, para mandarte un resumen diario aunque no haya ofertas.

Se guarda en datos/estadisticas.json (solo números, nada personal).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

HORA_RESUMEN_DIARIO = 20  # el primer aviso desde las 20 hs (de Argentina) incluye el resumen del día
DIAS_A_GUARDAR = 30


@dataclass
class Dia:
    corridas: int = 0
    revisadas: int = 0      # ofertas nuevas analizadas
    utiles: int = 0         # las que encajaron con vos
    de_mail: int = 0        # ofertas nuevas que llegaron por alertas de mail (sirvan o no)
    errores: int = 0


class Estadisticas:
    def __init__(self, ruta: str | Path):
        self.ruta = Path(ruta)
        datos = json.loads(self.ruta.read_text()) if self.ruta.exists() else {}
        self.dias: dict[str, Dia] = {f: Dia(**d) for f, d in datos.get("dias", {}).items()}
        self.ultimo_resumen: str = datos.get("ultimo_resumen", "")

    def dia(self, fecha: date) -> Dia:
        return self.dias.setdefault(fecha.isoformat(), Dia())

    def registrar(self, fecha: date, revisadas: int, utiles: int, de_mail: int, errores: int) -> Dia:
        d = self.dia(fecha)
        d.corridas += 1
        d.revisadas += revisadas
        d.utiles += utiles
        d.de_mail += de_mail
        d.errores += errores
        return d

    def toca_resumen_diario(self, ahora: datetime) -> bool:
        """True en la primera corrida desde las 20 hs de cada día (GitHub a veces se atrasa: no exigimos hora exacta)."""
        return ahora.hour >= HORA_RESUMEN_DIARIO and self.ultimo_resumen != ahora.date().isoformat()

    def marcar_resumen(self, fecha: date) -> None:
        self.ultimo_resumen = fecha.isoformat()

    def guardar(self, hoy: date) -> None:
        limite = (hoy - timedelta(days=DIAS_A_GUARDAR)).isoformat()
        datos = {
            "ultimo_resumen": self.ultimo_resumen,
            "dias": {f: asdict(d) for f, d in sorted(self.dias.items()) if f >= limite},
        }
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        self.ruta.write_text(json.dumps(datos, indent=1) + "\n")
