"""
Remotive (remotive.com): trabajos 100% remotos de todo el mundo, con API pública.

Sus condiciones piden no consultar más de unas pocas veces por día y enlazar al aviso
original: el radar corre dos veces por día y siempre manda el link de Remotive.
"""

from __future__ import annotations

from datetime import datetime

from ..modelos import Oferta
from .base import html_a_texto, obtener_json

NOMBRE = "Remotive"
URL = "https://remotive.com/api/remote-jobs?category=software-dev&limit=150"


def buscar() -> list[Oferta]:
    datos = obtener_json(URL)
    return [convertir(item) for item in datos.get("jobs", [])]


def convertir(item: dict) -> Oferta:
    etiquetas = ", ".join(item.get("tags") or [])
    return Oferta(
        id=f"remotive:{item.get('id')}",
        fuente=NOMBRE,
        titulo=(item.get("title") or "").strip(),
        empresa=item.get("company_name", ""),
        descripcion=html_a_texto(item.get("description")) + (f"\nTags: {etiquetas}" if etiquetas else ""),
        url=item.get("url", ""),
        ubicacion=item.get("candidate_required_location", ""),
        remoto=True,
        publicada=_fecha(item.get("publication_date")),
        salario=item.get("salary") or "",
    )


def _fecha(valor: str | None):
    if not valor:
        return None
    try:
        return datetime.fromisoformat(valor.replace("Z", "+00:00")).date()
    except ValueError:
        return None
