"""
Punto de entrada:  python -m radar_empleo [--simular] [--muestra]

  (sin opciones)  busca ofertas nuevas, las evalúa y te avisa por Telegram.
  --simular       hace todo igual pero imprime los mensajes en pantalla en vez de mandarlos.
  --muestra       imprime cómo llegan los datos crudos de cada fuente (para diagnosticar).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
from collections import Counter
from datetime import date
from pathlib import Path

from . import telegram
from .evaluador import evaluar
from .estado import Vistos
from .fuentes import getonboard, remotive
from .fuentes.base import obtener_json
from .modelos import Oferta, Perfil

RAIZ = Path(__file__).resolve().parent.parent
FUENTES = {"Get on Board": getonboard.buscar, "Remotive": remotive.buscar}


def main() -> int:
    args = _argumentos()
    if args.muestra:
        return _muestra()

    perfil = Perfil.desde_yaml(RAIZ / "perfil.yaml")
    vistos = Vistos(RAIZ / "datos" / "vistos.json")
    hoy = date.today()

    ofertas, errores = _buscar_todas()
    nuevas = [o for o in ofertas if not vistos.ya_visto(o.id)]
    evaluaciones = [evaluar(o, perfil, hoy) for o in nuevas]

    utiles = sorted((ev for ev in evaluaciones if ev.sirve), key=lambda ev: -ev.porcentaje)
    a_enviar = utiles[: perfil.maximo_por_aviso]
    descartes = Counter(_categoria(ev.descartada_por) for ev in evaluaciones if not ev.sirve)

    mensajes = [(telegram.mensaje_oferta(ev), [("Ver oferta ↗", ev.oferta.url)]) for ev in a_enviar]
    resumen = telegram.mensaje_resumen(len(nuevas), len(utiles), dict(descartes), errores)
    if len(utiles) > len(a_enviar):
        resumen += f"\nTe muestro las {len(a_enviar)} mejores; el resto llega en el próximo aviso."
    mensajes.append((resumen, []))

    if args.simular:
        for texto, botones in mensajes:
            print(texto, *(f"[{t}] {u}" for t, u in botones), sep="\n", end="\n\n")
    else:
        token, chat_id = os.environ.get("TELEGRAM_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
        if not token or not chat_id:
            print("Faltan TELEGRAM_TOKEN o TELEGRAM_CHAT_ID (ver README).", file=sys.stderr)
            return 1
        for texto, botones in mensajes:
            telegram.enviar(token, chat_id, texto, botones)

    # Las que no se mostraron por el límite quedan sin marcar: salen en el próximo aviso
    no_mostradas = {ev.oferta.id for ev in utiles[perfil.maximo_por_aviso:]}
    for ev in evaluaciones:
        if ev.oferta.id not in no_mostradas:
            vistos.marcar(ev.oferta.id, hoy)
    if not args.simular:
        vistos.guardar(hoy)

    # En los registros de GitHub (que son públicos) solo dejamos números, nada de detalle
    print(f"Ofertas: {len(ofertas)} · nuevas: {len(nuevas)} · útiles: {len(utiles)} · enviadas: {len(a_enviar)}")
    return 0


def _buscar_todas() -> tuple[list[Oferta], list[str]]:
    """Consulta cada fuente por separado: si una falla, las otras siguen funcionando."""
    ofertas: dict[str, Oferta] = {}
    errores: list[str] = []
    for nombre, buscar in FUENTES.items():
        try:
            for oferta in buscar():
                ofertas.setdefault(oferta.id, oferta)
        except Exception as error:  # noqa: BLE001 — queremos seguir con las demás fuentes
            errores.append(f"No pude consultar {nombre}: {type(error).__name__}")
    return list(ofertas.values()), errores


def _categoria(motivo: str) -> str:
    """Agrupa los motivos de descarte para el resumen ("por nivel", "sospechosas"…)."""
    if motivo.startswith("Sospechosa"):
        return "sospechosas"
    if motivo.startswith("Pide nivel"):
        return "por nivel"
    if motivo.startswith(("Solo para", "Presencial")):
        return "por ubicación"
    if motivo.startswith("Menciona"):
        return "por palabras excluidas"
    return "por baja compatibilidad"


def _muestra() -> int:
    """Muestra las claves y un ejemplo de cada fuente. Sirve para ver si una API cambió su formato."""
    expand = urllib.parse.quote('["company"]')
    pruebas = {
        "Get on Board (solo query)": getonboard.URL + "?query=java",
        "Get on Board (per_page)": getonboard.URL + "?query=java&per_page=2",
        "Get on Board (expand)": getonboard.URL + f"?query=java&per_page=2&expand={expand}",
        "Remotive": remotive.URL,
    }
    for nombre, url in pruebas.items():
        print(f"===== {nombre} =====")
        try:
            datos = obtener_json(url)
            print(json.dumps(_recortar(datos), indent=2, ensure_ascii=False)[:3000])
        except urllib.error.HTTPError as error:
            # El cuerpo del error suele explicar qué parámetro no le gustó
            print(f"ERROR HTTP {error.code}: {error.read().decode('utf-8', 'replace')[:500]}")
        except Exception as error:  # noqa: BLE001
            print(f"ERROR: {type(error).__name__}: {error}")
    return 0


def _recortar(valor, profundidad: int = 0):
    """Acorta textos largos para que la muestra sea legible."""
    if isinstance(valor, dict):
        return {k: _recortar(v, profundidad + 1) for k, v in valor.items()}
    if isinstance(valor, list):
        return [_recortar(v, profundidad + 1) for v in valor[:2]]
    if isinstance(valor, str) and len(valor) > 80:
        return valor[:80] + "…"
    return valor


def _argumentos() -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="radar_empleo", description="Busca ofertas de trabajo y te avisa por Telegram.")
    p.add_argument("--simular", action="store_true", help="imprime los mensajes en vez de mandarlos")
    p.add_argument("--muestra", action="store_true", help="muestra los datos crudos de cada fuente")
    return p.parse_args()


if __name__ == "__main__":
    sys.exit(main())
