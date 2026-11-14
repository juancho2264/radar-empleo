"""Las estructuras de datos del radar. Son dataclasses: clases solo con datos, sin lógica."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import yaml


@dataclass
class Oferta:
    """Una oferta de trabajo, venga de la fuente que venga (todas se traducen a este formato)."""

    id: str                      # único: "fuente:id_original"
    fuente: str
    titulo: str
    empresa: str
    descripcion: str             # texto plano, sin HTML
    url: str
    ubicacion: str = ""
    remoto: bool = False
    publicada: date | None = None
    salario: str = ""            # tal cual lo informa la fuente
    sitio_empresa: str = ""
    nivel: str = ""              # si la fuente ya clasifica el nivel; si no, se deduce del texto


@dataclass
class Perfil:
    nombre: str
    habilidades: set[str]
    compatibilidad_minima: int
    niveles_aceptados: set[str]
    ubicaciones: list[str]
    excluir: list[str]
    proyectos: dict[str, set[str]]
    maximo_por_aviso: int = 5
    cv_texto: str = ""

    @classmethod
    def desde_yaml(cls, ruta: str | Path) -> "Perfil":
        ruta = Path(ruta)
        datos = yaml.safe_load(ruta.read_text(encoding="utf-8"))
        cv = ruta.parent / datos["cv"] if datos.get("cv") else None
        return cls(
            nombre=datos["nombre"],
            habilidades={h.lower() for h in datos["habilidades"]},
            compatibilidad_minima=int(datos.get("compatibilidad_minima", 50)),
            niveles_aceptados={n.lower() for n in datos.get("niveles_aceptados", [])},
            ubicaciones=[u.lower() for u in datos.get("ubicaciones", [])],
            excluir=[e.lower() for e in datos.get("excluir", [])],
            proyectos={nombre: {t.lower() for t in techs} for nombre, techs in datos.get("proyectos", {}).items()},
            maximo_por_aviso=int(datos.get("maximo_por_aviso", 5)),
            cv_texto=cv.read_text(encoding="utf-8") if cv and cv.exists() else "",
        )


@dataclass
class Alerta:
    """Una señal de que la oferta puede ser trucha."""

    gravedad: str   # "grave" (descarta sola) o "media" (dos o más descartan)
    motivo: str


@dataclass
class Evaluacion:
    """Todo lo que el radar concluye sobre una oferta."""

    oferta: Oferta
    porcentaje: int
    tiene: list[str]
    falta: list[str]
    nivel: str
    alertas: list[Alerta] = field(default_factory=list)
    sugerencias: list[str] = field(default_factory=list)
    descartada_por: str = ""   # vacío si la oferta pasa todos los filtros

    @property
    def sirve(self) -> bool:
        return not self.descartada_por
