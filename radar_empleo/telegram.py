"""
Envío de mensajes por Telegram.

Usa la API HTTP de bots: https://core.telegram.org/bots/api
El token del bot y tu chat_id NO van en el código: se leen de variables de entorno,
que en GitHub se guardan como "secrets" (nadie los ve, ni en los registros).
"""

from __future__ import annotations

import html
import json
import urllib.request

from .estadisticas import Dia
from .modelos import Evaluacion

LIMITE_CARACTERES = 4000  # Telegram corta en 4096


def enviar(token: str, chat_id: str, texto: str, botones: list[tuple[str, str]] | None = None) -> None:
    cuerpo = {
        "chat_id": chat_id,
        "text": texto[:LIMITE_CARACTERES],
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if botones:
        # Botones con link: se abren en el navegador, no necesitan que el bot esté escuchando
        cuerpo["reply_markup"] = {"inline_keyboard": [[{"text": t, "url": u} for t, u in botones]]}

    pedido = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=json.dumps(cuerpo).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(pedido, timeout=30) as respuesta:
        resultado = json.loads(respuesta.read())
    if not resultado.get("ok"):
        raise RuntimeError(f"Telegram rechazó el mensaje: {resultado.get('description')}")


def plural(n: int, palabra: str, plural_de: str | None = None) -> str:
    """plural(1, "oferta") → "1 oferta" · plural(3, "oferta") → "3 ofertas"."""
    return f"{n} {palabra if n == 1 else (plural_de or palabra + 's')}"


def e(texto: str) -> str:
    """Escapa texto para el modo HTML de Telegram (si no, un "<" en un título rompe el mensaje)."""
    return html.escape(texto, quote=False)


def mensaje_oferta(ev: Evaluacion) -> str:
    o = ev.oferta
    color = "🟢" if ev.porcentaje >= 75 else "🟡"
    lugar = "Remoto" + (f" ({o.ubicacion})" if o.ubicacion else "") if o.remoto else (o.ubicacion or "Sin ubicación")
    lineas = [f"{color} <b>{ev.porcentaje}% · {e(o.titulo)}</b>"]
    if o.solo_titulo:
        lineas.append(f"📬 {e(o.fuente)}")
    else:
        lineas.append(f"🏢 {e(o.empresa or 'Empresa sin nombre')} · 📍 {e(lugar)} · {e(o.fuente)}")
    if ev.nivel != "sin especificar":
        lineas.append(f"🎯 Nivel: {e(ev.nivel)}")
    if o.salario:
        lineas.append(f"💵 {e(o.salario)}")
    if ev.tiene:
        lineas.append(f"✅ Tenés: {e(', '.join(ev.tiene))}")
    if ev.falta:
        lineas.append(f"❌ Te falta: {e(', '.join(ev.falta))}")
    for alerta in ev.alertas:
        lineas.append(f"⚠️ Ojo: {e(alerta.motivo)}")
    if o.solo_titulo:
        lineas.append("ℹ️ La alerta solo trae el título: leé la oferta completa antes de postularte.")
    if ev.sugerencias:
        lineas.append("\n📝 <b>Para tu CV:</b>")
        lineas.extend(f"• {e(s)}" for s in ev.sugerencias)
    return "\n".join(lineas)


def mensaje_alertas(evaluaciones: list[Evaluacion]) -> str:
    """
    Las ofertas de alertas por mail van todas juntas en un solo mensaje compacto:
    solo sabemos el título, así que son "para revisar", no avisos completos.
    """
    lineas = [f"📬 <b>{plural(len(evaluaciones), 'oferta')} de tus alertas para revisar</b>",
              "<i>Encaje calculado solo con el título: leé la oferta antes de postularte.</i>", ""]
    for ev in evaluaciones:
        o = ev.oferta
        lineas.append(f'🔵 {ev.porcentaje}% · <a href="{e(o.url)}">{e(o.titulo)}</a> · {e(o.fuente.replace(" (alerta)", ""))}')
        if ev.tiene:
            lineas.append(f"    ✅ {e(', '.join(ev.tiene))}" + (f" · ❌ {e(', '.join(ev.falta))}" if ev.falta else ""))
    return "\n".join(lineas)


def mensaje_resumen(revisadas: int, utiles: int, descartes: dict[str, int], errores: list[str]) -> str | None:
    """Resumen de la corrida. None = no hay nada que contar (no molestamos con un mensaje vacío)."""
    if utiles == 0 and not errores:
        return None
    lineas = [f"📡 <b>Radar de empleo</b>\nRevisé {plural(revisadas, 'oferta nueva', 'ofertas nuevas')}: "
              f"<b>{utiles} te {'sirve' if utiles == 1 else 'sirven'}</b>."]
    if descartes:
        detalle = ", ".join(f"{cantidad} {motivo}" for motivo, cantidad in sorted(descartes.items(), key=lambda x: -x[1]))
        lineas.append(f"Descarté {sum(descartes.values())}: {e(detalle)}.")
    for error in errores:
        lineas.append(f"⚠️ {e(error)}")
    return "\n".join(lineas)


def mensaje_diario(dia: Dia, errores: list[str]) -> str:
    """Resumen del día: llega siempre (una vez por día), para que sepas que el radar está activo."""
    lineas = [
        "📡 <b>Radar activo</b> · resumen del día",
        f"Revisé {plural(dia.revisadas, 'oferta nueva', 'ofertas nuevas')} en {plural(dia.corridas, 'pasada')}.",
        f"📬 Alertas por mail: {plural(dia.de_mail, 'oferta recibida', 'ofertas recibidas')}.",
    ]
    if dia.utiles:
        lineas.append(f"✅ <b>{plural(dia.utiles, 'encajó', 'encajaron')} con vos</b> (te las mandé durante el día).")
    else:
        lineas.append("Hoy no hubo nada para tu perfil. Mañana sigo buscando.")
    for error in errores:
        lineas.append(f"⚠️ {e(error)}")
    return "\n".join(lineas)
