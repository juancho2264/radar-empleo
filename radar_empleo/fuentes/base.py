"""Herramientas comunes a todas las fuentes de ofertas."""

from __future__ import annotations

import html
import json
import re
import urllib.request
from typing import Any

# Nos identificamos con un nombre genérico, sin datos personales
AGENTE = "radar-empleo/1.0 (+https://github.com)"


def obtener_json(url: str, timeout: int = 30) -> Any:
    pedido = urllib.request.Request(url, headers={"User-Agent": AGENTE, "Accept": "application/json"})
    with urllib.request.urlopen(pedido, timeout=timeout) as respuesta:
        return json.loads(respuesta.read().decode("utf-8"))


def html_a_texto(contenido: str | None) -> str:
    """Saca etiquetas HTML y deja texto plano: '<p>Hola&nbsp;mundo</p>' → 'Hola mundo'."""
    if not contenido:
        return ""
    sin_tags = re.sub(r"<(br|/p|/li|/h\d)\s*/?>", "\n", contenido, flags=re.IGNORECASE)
    sin_tags = re.sub(r"<[^>]+>", " ", sin_tags)
    texto = html.unescape(sin_tags)
    texto = re.sub(r"[ \t ]+", " ", texto)
    return re.sub(r" *\n *", "\n", texto).strip()  # sin espacios sueltos al principio o final de cada línea
