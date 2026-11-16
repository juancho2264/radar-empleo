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

HORA_DESDE, HORA_HASTA = 8, 24              # se buscan ofertas entre las 8 y las 24 (hora de Argentina)
ENTRE_BUSQUEDAS = timedelta(hours=2, minutes=40)  # "cada 3 horas", con margen por si GitHub se atrasa
HORA_RESUMEN_DIARIO = 20  # el primer aviso desde las 20 hs (de Argentina) incluye el resumen del día
DIA_RESUMEN_SEMANAL = 6   # domingo (lunes = 0)
DIAS_A_GUARDAR = 30
SEMANAS_A_GUARDAR = 8


def semana_de(fecha: date) -> str:
    """"2026-W46": el año y número de semana ISO (las semanas empiezan el lunes)."""
    anio, semana, _ = fecha.isocalendar()
    return f"{anio}-W{semana:02d}"


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
        # Mercado: por semana, cuántas ofertas de tu nivel se vieron y cuántas pedían cada tecnología
        self.semanas: dict[str, dict] = datos.get("semanas", {})
        self.ultimo_semanal: str = datos.get("ultimo_semanal", "")
        self.ultima_busqueda: str = datos.get("ultima_busqueda", "")

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

    def toca_buscar(self, ahora: datetime, forzar: bool = False) -> bool:
        """
        El radar se despierta cada hora (GitHub saltea corridas programadas cuando está cargado,
        así que pedir más seguido asegura el ritmo), pero busca ofertas solo cada ~3 horas y de día.
        """
        if forzar:
            return True
        if not HORA_DESDE <= ahora.hour < HORA_HASTA:
            return False
        return not self.ultima_busqueda or ahora - datetime.fromisoformat(self.ultima_busqueda) >= ENTRE_BUSQUEDAS

    def marcar_busqueda(self, ahora: datetime) -> None:
        self.ultima_busqueda = ahora.isoformat(timespec="minutes")

    def toca_resumen_diario(self, ahora: datetime) -> bool:
        """True en la primera corrida desde las 20 hs de cada día (GitHub a veces se atrasa: no exigimos hora exacta)."""
        return ahora.hour >= HORA_RESUMEN_DIARIO and self.ultimo_resumen != ahora.date().isoformat()

    def marcar_resumen(self, fecha: date) -> None:
        self.ultimo_resumen = fecha.isoformat()

    # ---------- Mercado (para el reporte semanal) ----------

    def registrar_mercado(self, fecha: date, tecnologias_por_oferta: list[list[str]]) -> None:
        """Recibe, por cada oferta de tu nivel, la lista de tecnologías que pide."""
        semana = self.semanas.setdefault(semana_de(fecha), {"ofertas": 0, "tecnologias": {}})
        for tecnologias in tecnologias_por_oferta:
            semana["ofertas"] += 1
            for t in set(tecnologias):
                semana["tecnologias"][t] = semana["tecnologias"].get(t, 0) + 1

    def mercado(self, fecha: date) -> dict:
        return self.semanas.get(semana_de(fecha), {"ofertas": 0, "tecnologias": {}})

    def toca_resumen_semanal(self, ahora: datetime) -> bool:
        return (ahora.weekday() == DIA_RESUMEN_SEMANAL and ahora.hour >= HORA_RESUMEN_DIARIO
                and self.ultimo_semanal != semana_de(ahora.date()))

    def marcar_semanal(self, fecha: date) -> None:
        self.ultimo_semanal = semana_de(fecha)

    def revisadas_en_semana(self, fecha: date) -> int:
        semana = semana_de(fecha)
        return sum(d.revisadas for f, d in self.dias.items() if semana_de(date.fromisoformat(f)) == semana)

    def guardar(self, hoy: date) -> None:
        limite = (hoy - timedelta(days=DIAS_A_GUARDAR)).isoformat()
        semanas = dict(sorted(self.semanas.items())[-SEMANAS_A_GUARDAR:])
        datos = {
            "ultimo_resumen": self.ultimo_resumen,
            "ultimo_semanal": self.ultimo_semanal,
            "ultima_busqueda": self.ultima_busqueda,
            "dias": {f: asdict(d) for f, d in sorted(self.dias.items()) if f >= limite},
            "semanas": semanas,
        }
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        self.ruta.write_text(json.dumps(datos, indent=1) + "\n")
