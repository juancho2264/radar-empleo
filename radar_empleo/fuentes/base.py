"""Herramientas comunes a todas las fuentes de ofertas."""

from __future__ import annotations

import html
import json
import re
import time
import urllib.error
import urllib.request
from typing import Any

# Nos identificamos con un nombre genérico, sin datos personales
AGENTE = "radar-empleo/1.0 (+https://github.com)"


# Códigos con los que un sitio dice "esperá un poco": vale la pena reintentar
REINTENTABLES = {403, 429, 500, 502, 503, 504}


def obtener_json(url: str, timeout: int = 30, reintentos: int = 2, espera: float = 20) -> Any:
    """
    Pide un JSON. Si el sitio responde que está saturado o que nos frenó por exceso de consultas,
    espera y reintenta (20 s, después 40 s): es la forma educada de usar una API pública.
    """
    pedido = urllib.request.Request(url, headers={"User-Agent": AGENTE, "Accept": "application/json"})
    for intento in range(reintentos + 1):
        try:
            with urllib.request.urlopen(pedido, timeout=timeout) as respuesta:
                return json.loads(respuesta.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            if error.code not in REINTENTABLES or intento == reintentos:
                raise
            time.sleep(espera * (intento + 1))


def html_a_texto(contenido: str | None) -> str:
    """Saca etiquetas HTML y deja texto plano: '<p>Hola&nbsp;mundo</p>' → 'Hola mundo'."""
    if not contenido:
        return ""
    sin_tags = re.sub(r"<(br|/p|/li|/h\d)\s*/?>", "\n", contenido, flags=re.IGNORECASE)
    sin_tags = re.sub(r"<[^>]+>", " ", sin_tags)
    texto = html.unescape(sin_tags)
    texto = re.sub(r"[ \t ]+", " ", texto)
    return re.sub(r" *\n *", "\n", texto).strip()  # sin espacios sueltos al principio o final de cada línea
