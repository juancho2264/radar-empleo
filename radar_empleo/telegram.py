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

# Un teclado es una lista de filas; cada botón es (texto, valor).
# Si el valor es un link, el botón lo abre; si no, es una acción que el radar lee después ("p:abc123").
Teclado = list[list[tuple[str, str]]]


def llamar(token: str, metodo: str, cuerpo: dict) -> dict | list | bool:
    """Llama a un método de la API de bots (sendMessage, getUpdates, …) y devuelve su "result"."""
    pedido = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/{metodo}",
        data=json.dumps(cuerpo).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(pedido, timeout=30) as respuesta:
        resultado = json.loads(respuesta.read())
    if not resultado.get("ok"):
        raise RuntimeError(f"Telegram rechazó {metodo}: {resultado.get('description')}")
    return resultado["result"]


def armar_teclado(teclado: Teclado) -> dict:
    return {"inline_keyboard": [
        [{"text": texto, "url": valor} if valor.startswith("http") else {"text": texto, "callback_data": valor}
         for texto, valor in fila]
        for fila in teclado
    ]}


def enviar(token: str, chat_id: str, texto: str, teclado: Teclado | None = None) -> int:
    """Manda un mensaje y devuelve su id (sirve para editarle los botones después)."""
    cuerpo = {"chat_id": chat_id, "text": texto[:LIMITE_CARACTERES], "parse_mode": "HTML",
              "disable_web_page_preview": True}
    if teclado:
        cuerpo["reply_markup"] = armar_teclado(teclado)
    return llamar(token, "sendMessage", cuerpo)["message_id"]


def editar_botones(token: str, chat_id: str, mensaje_id: int, teclado: Teclado) -> None:
    llamar(token, "editMessageReplyMarkup",
           {"chat_id": chat_id, "message_id": mensaje_id, "reply_markup": armar_teclado(teclado)})


def responder_boton(token: str, callback_id: str, texto: str) -> None:
    """Le contesta a Telegram que recibimos el toque del botón. Si pasó mucho tiempo, Telegram ya no lo acepta: no importa."""
    try:
        llamar(token, "answerCallbackQuery", {"callback_query_id": callback_id, "text": texto})
    except Exception:  # noqa: BLE001 — "query is too old": el registro ya se hizo igual
        pass


def novedades(token: str, desde: int) -> list[dict]:
    """
    Botones tocados y mensajes recibidos desde la última vez (Telegram los guarda 24 horas).
    Como el radar corre cada 3 horas, no se pierde nada aunque no haya un servidor escuchando.
    """
    return llamar(token, "getUpdates", {"offset": desde, "timeout": 0,
                                        "allowed_updates": ["callback_query", "message"]})


def plural(n: int, palabra: str, plural_de: str | None = None) -> str:
    """plural(1, "oferta") → "1 oferta" · plural(3, "oferta") → "3 ofertas"."""
    return f"{n} {palabra if n == 1 else (plural_de or palabra + 's')}"


def e(texto: str) -> str:
    """Escapa texto para el modo HTML de Telegram (si no, un "<" en un título rompe el mensaje)."""
    return html.escape(texto, quote=False)


def link(url: str, texto: str) -> str:
    """Link seguro: la dirección escapada CON comillas (si no, un " en la URL podría inyectar formato)."""
    return f'<a href="{html.escape(url, quote=True)}">{e(texto)}</a>'


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
              "<i>Encaje calculado solo con el título: leé la oferta antes de postularte. "
              "Usá los botones con el número de cada una.</i>", ""]
    for n, ev in enumerate(evaluaciones, 1):  # numeradas: los botones ✅ 1 / 🚫 1 se refieren a estos números
        o = ev.oferta
        lineas.append(f'🔵 <b>{n}.</b> {ev.porcentaje}% · {link(o.url, o.titulo)} · {e(o.fuente.replace(" (alerta)", ""))}')
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


def mensaje_semanal(mercado: dict, habilidades: set[str], revisadas: int, postulaciones: int, top: int = 5) -> str:
    """
    Reporte del domingo: qué piden las ofertas de tu nivel, lo que te falta y lo que ya tenés.
    Sirve para decidir qué estudiar con datos reales, no por intuición.
    """
    total = mercado.get("ofertas", 0)
    lineas = ["📊 <b>Tu semana en el mercado</b>",
              f"Revisé {plural(revisadas, 'oferta nueva', 'ofertas nuevas')}; "
              f"{plural(total, 'era', 'eran')} de tu nivel y mencionaban tecnologías "
              "(en las alertas de LinkedIn, según el título)."]
    if total:
        ranking = sorted(mercado["tecnologias"].items(), key=lambda par: (-par[1], par[0]))
        falta = [(t, c) for t, c in ranking if t not in habilidades][:top]
        tiene = [(t, c) for t, c in ranking if t in habilidades][:top]
        formato = lambda pares: ", ".join(f"{e(t)} ({round(100 * c / total)}%)" for t, c in pares)
        if falta:
            lineas.append(f"\n📚 <b>Lo que más piden y no tenés:</b>\n{formato(falta)}")
            lineas.append(f"👉 Si tenés que elegir qué aprender, empezá por <b>{e(falta[0][0])}</b>.")
        if tiene:
            lineas.append(f"\n💪 <b>Lo que tenés y más piden:</b>\n{formato(tiene)}")
    else:
        lineas.append("No hubo suficientes ofertas de tu nivel para sacar conclusiones esta semana.")
    lineas.append(f"\n📨 Esta semana te postulaste a {plural(postulaciones, 'oferta')}. "
                  "Escribí /postulaciones para ver la lista.")
    return "\n".join(lineas)
