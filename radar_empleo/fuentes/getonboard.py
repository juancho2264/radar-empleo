"""
Get on Board (getonbrd.com): portal de empleo tech de Latinoamérica, con API pública.

La API devuelve el formato JSON:API: { "data": [ { "id", "attributes": {...}, "links": {...} } ] }.
Leemos cada campo con .get() y valores por defecto: si la API cambia un detalle, la fuente
no se rompe entera (a lo sumo, ese dato queda vacío).
"""

from __future__ import annotations

import json
import urllib.parse
from datetime import datetime, timezone

from ..modelos import Oferta
from .base import html_a_texto, obtener_json

NOMBRE = "Get on Board"
URL = "https://www.getonbrd.com/api/v0/search/jobs"
BUSQUEDAS = ["java", "spring", "react", "javascript", "python", "junior", "trainee"]


def buscar(busquedas: list[str] | None = None) -> list[Oferta]:
    ofertas: dict[str, Oferta] = {}
    for termino in busquedas or BUSQUEDAS:
        parametros = urllib.parse.urlencode({"query": termino, "per_page": 50, "expand": json.dumps(["company"])})
        datos = obtener_json(f"{URL}?{parametros}")
        for item in datos.get("data", []):
            oferta = convertir(item)
            ofertas[oferta.id] = oferta  # el dict evita duplicados entre búsquedas
    return list(ofertas.values())


def convertir(item: dict) -> Oferta:
    a = item.get("attributes", {})
    partes = [a.get("description"), a.get("projects"), a.get("functions"), a.get("desirable"), a.get("benefits")]
    descripcion = "\n".join(html_a_texto(p) for p in partes if p)

    empresa = (((a.get("company") or {}).get("data") or {}).get("attributes") or {})
    paises = a.get("countries") or ([a["country"]] if a.get("country") else [])
    modalidad = (a.get("remote_modality") or "").replace("_", " ")

    return Oferta(
        id=f"getonboard:{item.get('id')}",
        fuente=NOMBRE,
        titulo=a.get("title", "").strip(),
        empresa=empresa.get("name", ""),
        descripcion=descripcion,
        url=(item.get("links") or {}).get("public_url") or f"https://www.getonbrd.com/jobs/{item.get('id')}",
        ubicacion=", ".join(str(p) for p in paises) or modalidad,
        remoto=bool(a.get("remote")) or "remote" in modalidad,
        publicada=_fecha(a.get("published_at")),
        salario=_salario(a.get("min_salary"), a.get("max_salary")),
        sitio_empresa=empresa.get("web", "") or "",
    )


def _fecha(valor) -> datetime.date | None:
    """La API manda la fecha como número (segundos desde 1970) o como texto ISO."""
    if valor in (None, ""):
        return None
    try:
        if isinstance(valor, (int, float)):
            return datetime.fromtimestamp(valor, tz=timezone.utc).date()
        return datetime.fromisoformat(str(valor).replace("Z", "+00:00")).date()
    except (ValueError, OSError):
        return None


def _salario(minimo, maximo) -> str:
    if minimo and maximo:
        return f"USD {minimo}–{maximo}"
    if minimo or maximo:
        return f"USD {minimo or maximo}"
    return ""
