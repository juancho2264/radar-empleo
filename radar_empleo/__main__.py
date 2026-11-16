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
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from . import telegram
from .evaluador import evaluar
from .estadisticas import Estadisticas
from .estado import Vistos
from .fuentes import alertas_mail, getonboard, remotive
from .fuentes.base import obtener_json
from .modelos import Oferta, Perfil
from .postulaciones import Accion, Postulaciones, mensaje_pregunta_seguimiento

RAIZ = Path(__file__).resolve().parent.parent
FUENTES = {"Get on Board": getonboard.buscar, "Remotive": remotive.buscar}
MAXIMO_ALERTAS_POR_AVISO = 10
ZONA = ZoneInfo("America/Argentina/Buenos_Aires")


def _ahora() -> datetime:
    """Hora de Argentina. Los servidores de GitHub usan UTC: después de las 21 de acá ya es "mañana" para ellos."""
    return datetime.now(ZONA)


def _fuentes() -> dict:
    """Las fuentes fijas, más las alertas por mail si están configuradas (secretos GMAIL_*)."""
    fuentes = dict(FUENTES)
    usuario, clave = os.environ.get("GMAIL_USER"), os.environ.get("GMAIL_APP_PASSWORD")
    if usuario and clave:
        fuentes[alertas_mail.NOMBRE] = lambda: alertas_mail.buscar(usuario, clave)
    return fuentes


class _Salida:
    """Manda a Telegram, o imprime en pantalla con --simular. Así el resto del código no distingue."""

    def __init__(self, simular: bool, token: str | None, chat_id: str | None):
        self.simular, self.token, self.chat_id = simular, token, chat_id

    def enviar(self, texto: str, teclado: list | None = None) -> None:
        if self.simular:
            botones = [f"[{t}] {v}" for fila in (teclado or []) for t, v in fila]
            print(texto, *botones, sep="\n", end="\n\n")
        else:
            telegram.enviar(self.token, self.chat_id, texto, teclado)

    def ejecutar(self, accion: Accion) -> None:
        if accion.tipo == "mensaje":
            self.enviar(accion.texto)
        elif self.simular:
            return
        elif accion.tipo == "responder_boton":
            telegram.responder_boton(self.token, accion.callback_id, accion.texto)
        elif accion.tipo == "editar_botones":
            try:
                telegram.editar_botones(self.token, self.chat_id, accion.mensaje_id, accion.teclado)
            except Exception:  # noqa: BLE001 — un mensaje muy viejo ya no se puede editar: el registro vale igual
                pass


def main() -> int:
    args = _argumentos()
    if args.muestra:
        return _muestra()

    perfil = Perfil.desde_yaml(RAIZ / "perfil.yaml")
    vistos = Vistos(RAIZ / "datos" / "vistos.json")
    estadisticas = Estadisticas(RAIZ / "datos" / "estadisticas.json")
    ahora = _ahora()
    hoy = ahora.date()

    token, chat_id = os.environ.get("TELEGRAM_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not args.simular and not (token and chat_id):
        print("Faltan TELEGRAM_TOKEN o TELEGRAM_CHAT_ID (ver README).", file=sys.stderr)
        return 1
    salida = _Salida(args.simular, token, chat_id)
    postulaciones = Postulaciones(RAIZ / "datos" / "postulaciones.enc", token or "simulacion")
    errores: list[str] = []

    # 1. Lo que tocaste en Telegram desde la última pasada ("Me postulé", "No me interesa", /postulaciones…)
    if not args.simular:
        try:
            for accion in postulaciones.procesar(telegram.novedades(token, postulaciones.offset), chat_id, hoy):
                salida.ejecutar(accion)
        except Exception as error:  # noqa: BLE001
            errores.append(f"No pude leer los botones de Telegram: {type(error).__name__}. Reintento en el próximo aviso.")

    # Cada hora se leen los botones; las ofertas se buscan cada ~3 horas (o siempre, si lo corrés a mano)
    forzar = args.simular or os.environ.get("FORZAR") == "1"
    if not estadisticas.toca_buscar(ahora, forzar):
        if not args.simular:
            postulaciones.guardar(hoy)
        print(f"Pasada liviana: solo botones de Telegram (última búsqueda: {estadisticas.ultima_busqueda or 'nunca'})")
        return 0
    estadisticas.marcar_busqueda(ahora)

    # 2. Buscar y evaluar ofertas nuevas
    ofertas, errores_fuentes = _buscar_todas()
    errores += errores_fuentes
    nuevas = [o for o in ofertas if not vistos.ya_visto(o.id)]
    evaluaciones = [evaluar(o, perfil, hoy) for o in nuevas]
    utiles = sorted((ev for ev in evaluaciones if ev.sirve), key=lambda ev: -ev.porcentaje)
    descartes = Counter(_categoria(ev.descartada_por) for ev in evaluaciones if not ev.sirve)

    # Para el reporte semanal: qué piden las ofertas de TU nivel (aunque no te sirvan por ubicación o idioma).
    # Incluye las alertas de LinkedIn: de esas solo sabemos el título, pero es la fuente que más trae.
    estadisticas.registrar_mercado(hoy, [ev.tiene + ev.falta for ev in evaluaciones
                                         if ev.nivel in perfil.niveles_aceptados and (ev.tiene or ev.falta)])

    # 3. Mandar ofertas. Completas: una por mensaje. De alertas por mail (solo título): todas juntas.
    completas = [ev for ev in utiles if not ev.oferta.solo_titulo]
    de_alertas = [ev for ev in utiles if ev.oferta.solo_titulo]
    a_enviar = completas[: perfil.maximo_por_aviso]
    alertas_a_enviar = de_alertas[:MAXIMO_ALERTAS_POR_AVISO]
    no_mostradas = {ev.oferta.id for ev in completas[perfil.maximo_por_aviso:] + de_alertas[MAXIMO_ALERTAS_POR_AVISO:]}

    for ev in a_enviar:
        clave = postulaciones.registrar_enviada(ev.oferta, hoy)
        salida.enviar(telegram.mensaje_oferta(ev), Postulaciones.teclado_oferta(clave, ev.oferta.url))
    if alertas_a_enviar:
        claves = [postulaciones.registrar_enviada(ev.oferta, hoy) for ev in alertas_a_enviar]
        salida.enviar(telegram.mensaje_alertas(alertas_a_enviar), Postulaciones.teclado_alertas(claves))

    # 4. ¿Te respondieron? (postulaciones de hace una semana)
    for clave, oferta in postulaciones.pendientes_de_seguimiento(hoy):
        salida.enviar(mensaje_pregunta_seguimiento(oferta),
                      [[("Ver oferta ↗", oferta["url"])]] + Postulaciones.teclado_seguimiento(clave))
        postulaciones.marcar_preguntado(clave)

    # 5. Resúmenes
    dia = estadisticas.registrar(hoy, revisadas=len(nuevas), utiles=len(utiles),
                                 de_mail=sum(o.solo_titulo for o in nuevas), errores=len(errores))
    if estadisticas.toca_resumen_semanal(ahora):
        lunes = hoy - timedelta(days=hoy.weekday())
        salida.enviar(telegram.mensaje_semanal(estadisticas.mercado(hoy), perfil.habilidades,
                                               estadisticas.revisadas_en_semana(hoy),
                                               postulaciones.postulaciones_entre(lunes, hoy)))
        estadisticas.marcar_semanal(hoy)
    if estadisticas.toca_resumen_diario(ahora):
        # Una vez por día, aunque no haya nada: así sabés que el radar sigue funcionando
        salida.enviar(telegram.mensaje_diario(dia, errores))
        estadisticas.marcar_resumen(hoy)
    else:
        resumen = telegram.mensaje_resumen(len(nuevas), len(utiles), dict(descartes), errores)
        if resumen:
            if no_mostradas:
                resumen += f"\nQuedaron {len(no_mostradas)} para el próximo aviso."
            salida.enviar(resumen)

    # 6. Guardar memoria. Las que no se mostraron por el límite quedan sin marcar: salen en el próximo aviso.
    for ev in evaluaciones:
        if ev.oferta.id not in no_mostradas:
            vistos.marcar(ev.oferta.id, hoy)
    if not args.simular:
        vistos.guardar(hoy)
        estadisticas.guardar(hoy)
        postulaciones.guardar(hoy)

    # En los registros de GitHub (que son públicos) solo dejamos números, nada de detalle
    print(f"Ofertas: {len(ofertas)} · nuevas: {len(nuevas)} · útiles: {len(utiles)} · "
          f"enviadas: {len(a_enviar)} completas + {len(alertas_a_enviar)} de alertas")
    return 0


def _buscar_todas() -> tuple[list[Oferta], list[str]]:
    """Consulta cada fuente por separado: si una falla, las otras siguen funcionando."""
    ofertas: dict[str, Oferta] = {}
    errores: list[str] = []
    for nombre, buscar in _fuentes().items():
        try:
            for oferta in buscar():
                ofertas.setdefault(oferta.id, oferta)
        except Exception as error:  # noqa: BLE001 — queremos seguir con las demás fuentes
            codigo = f" {error.code}" if hasattr(error, "code") else ""
            errores.append(f"No pude consultar {nombre}: {type(error).__name__}{codigo}. Reintento en el próximo aviso.")
    return list(ofertas.values()), errores


def _categoria(motivo: str) -> str:
    """Agrupa los motivos de descarte para el resumen ("por nivel", "sospechosas"…)."""
    if motivo.startswith("Sospechosa"):
        return "sospechosas"
    if motivo.startswith("Pide nivel"):
        return "por nivel"
    if motivo.startswith(("Solo para", "Presencial")):
        return "por ubicación"
    if motivo.startswith(("Aviso en inglés", "Pide inglés")):
        return "por inglés"
    if motivo.startswith("Menciona"):
        return "por palabras excluidas"
    return "por baja compatibilidad"


def _muestra() -> int:
    """Muestra las claves y un ejemplo de cada fuente. Sirve para ver si una API cambió su formato."""
    expand = urllib.parse.quote('["company"]')
    pruebas = {
        "Get on Board (oferta de ejemplo)": getonboard.URL + f"?query=java&per_page=1&expand={expand}",
        "Remotive (oferta de ejemplo)": remotive.URL,
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

    print("===== Get on Board (niveles completos) =====")
    try:
        niveles = obtener_json("https://www.getonbrd.com/api/v0/seniorities").get("data", [])
        for n in sorted(niveles, key=lambda n: int(n["id"])):
            print(f"  {n['id']} = {n['attributes'].get('name')} ({n['attributes'].get('locale_key')})")
    except Exception as error:  # noqa: BLE001
        print(f"ERROR: {type(error).__name__}: {error}")

    # Alertas por mail: cuántos mails y ofertas encuentra por sitio (solo títulos de puestos, nada personal)
    usuario, clave = os.environ.get("GMAIL_USER"), os.environ.get("GMAIL_APP_PASSWORD")
    print("===== Alertas por mail =====")
    if not (usuario and clave):
        print("No configuradas (faltan los secretos GMAIL_USER y GMAIL_APP_PASSWORD).")
    else:
        try:
            ofertas_mail = alertas_mail.buscar(usuario, clave)
            for fuente, cantidad in Counter(o.fuente for o in ofertas_mail).items():
                titulos = [o.titulo for o in ofertas_mail if o.fuente == fuente][:5]
                print(f"  {fuente}: {cantidad} ofertas · ejemplos: {titulos}")
            if not ofertas_mail:
                print("  Conectó bien, pero no encontró ofertas en mails de alertas de los últimos días.")
        except Exception as error:  # noqa: BLE001
            print(f"ERROR: {type(error).__name__}: {error}")

    # Corrida real (sin Telegram): solo cantidades, nada de detalle (los registros son públicos)
    print("===== Corrida real sin Telegram =====")
    perfil = Perfil.desde_yaml(RAIZ / "perfil.yaml")
    ofertas, errores = _buscar_todas()
    evaluaciones = [evaluar(o, perfil) for o in ofertas]
    por_fuente = Counter(o.fuente for o in ofertas)
    print(f"Ofertas por fuente: {dict(por_fuente)} · errores: {errores}")
    print(f"Te sirven: {sum(ev.sirve for ev in evaluaciones)}")
    print(f"Descartes: {dict(Counter(_categoria(ev.descartada_por) for ev in evaluaciones if not ev.sirve))}")
    print(f"Niveles detectados: {dict(Counter(ev.nivel for ev in evaluaciones))}")

    # Qué tecnologías piden (en % de ofertas): todas y solo las de nivel trainee/junior
    print("===== Tecnologías más pedidas =====")
    completas = [ev for ev in evaluaciones if not ev.oferta.solo_titulo and (ev.tiene or ev.falta)]
    for nombre, grupo in (("todas", completas), ("trainee/junior", [ev for ev in completas if ev.nivel in ("trainee", "junior")])):
        conteo = Counter(t for ev in grupo for t in set(ev.tiene + ev.falta))
        top = ", ".join(f"{t} {round(100 * c / len(grupo))}%" for t, c in conteo.most_common(20)) if grupo else "-"
        print(f"[{nombre}] {len(grupo)} ofertas: {top}")
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
