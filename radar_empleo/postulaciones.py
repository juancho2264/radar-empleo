"""
Seguimiento de postulaciones con botones de Telegram.

Cada oferta que te manda el radar trae botones "Me postulé" y "No me interesa".
No hay un servidor escuchando: en cada corrida (cada 3 horas) el radar le pregunta a
Telegram qué botones tocaste desde la última vez, y lo registra.

A los 7 días de una postulación te pregunta si te respondieron. Si no, te propone
un mensaje de seguimiento para el reclutador (mucha gente consigue la entrevista así).

PRIVACIDAD: el repo es público, y a qué empresas te postulás es información tuya.
Por eso este archivo se guarda CIFRADO (datos/postulaciones.enc), con una clave que sale
de tu token de Telegram, que es secreto. Sin el token, el archivo es ilegible.
"""

from __future__ import annotations

import base64
import hashlib
import html
import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from .modelos import Oferta

DIAS_PARA_SEGUIMIENTO = 7
DIAS_A_GUARDAR = 90

# Acciones de los botones (callback_data de Telegram, máximo 64 bytes)
POSTULE, NO_ME_INTERESA = "p", "n"
ENTREVISTA, SIN_RESPUESTA, RECHAZO = "r", "s", "x"
NADA = "-"  # botón informativo que ya no hace nada


def clave_de(oferta_id: str) -> str:
    """Id corto y fijo para una oferta: los ids originales pueden pasar el límite de 64 bytes de Telegram."""
    return hashlib.sha1(oferta_id.encode()).hexdigest()[:12]


@dataclass
class Accion:
    """Algo que hay que hacer en Telegram como consecuencia de un botón o un comando."""

    tipo: str                         # "editar_botones" | "responder_boton" | "mensaje"
    texto: str = ""
    mensaje_id: int | None = None
    callback_id: str = ""
    teclado: list = field(default_factory=list)


class Postulaciones:
    def __init__(self, ruta: str | Path, secreto: str):
        self.ruta = Path(ruta)
        self._fernet = Fernet(base64.urlsafe_b64encode(hashlib.sha256(f"radar-postulaciones:{secreto}".encode()).digest()))
        self.datos = {"offset": 0, "ofertas": {}, "estados": {}}
        self.ilegible = False
        # El cifrado da un resultado distinto cada vez: si guardáramos siempre, habría un commit por hora sin cambios
        self.cambio = not self.ruta.exists()
        if self.ruta.exists():
            try:
                self.datos = json.loads(self._fernet.decrypt(self.ruta.read_bytes()))
            except InvalidToken:
                # Cambió el token de Telegram: el archivo viejo no se puede abrir. Empezamos de cero.
                self.ilegible = True

    # ---------- Guardar ----------

    def guardar(self, hoy: date) -> None:
        if not (self.cambio or self.ilegible):
            return
        limite = (hoy - timedelta(days=DIAS_A_GUARDAR)).isoformat()
        estados = self.datos["estados"]
        # Se olvidan las ofertas viejas que nunca tocaste; las que tienen estado se conservan
        self.datos["ofertas"] = {k: o for k, o in self.datos["ofertas"].items() if k in estados or o["enviada"] >= limite}
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        self.ruta.write_bytes(self._fernet.encrypt(json.dumps(self.datos, ensure_ascii=False).encode()))

    # ---------- Ofertas enviadas ----------

    def registrar_enviada(self, oferta: Oferta, hoy: date) -> str:
        clave = clave_de(oferta.id)
        self.cambio = True
        self.datos["ofertas"].setdefault(clave, {
            "titulo": oferta.titulo, "empresa": oferta.empresa, "url": oferta.url,
            "fuente": oferta.fuente.replace(" (alerta)", ""), "enviada": hoy.isoformat(),
        })
        return clave

    @staticmethod
    def teclado_oferta(clave: str, url: str) -> list:
        return [[("Ver oferta ↗", url)],
                [("✅ Me postulé", f"{POSTULE}:{clave}"), ("🚫 No me interesa", f"{NO_ME_INTERESA}:{clave}")]]

    @staticmethod
    def teclado_alertas(claves: list[str]) -> list:
        """Para el mensaje compacto de alertas: botones numerados, dos ofertas por fila."""
        botones = [b for n, c in enumerate(claves, 1) for b in ((f"✅ {n}", f"{POSTULE}:{c}"), (f"🚫 {n}", f"{NO_ME_INTERESA}:{c}"))]
        return [botones[i:i + 4] for i in range(0, len(botones), 4)]

    # ---------- Procesar lo que tocaste ----------

    @property
    def offset(self) -> int:
        return self.datos["offset"]

    def procesar(self, actualizaciones: list[dict], chat_id: str, hoy: date) -> list[Accion]:
        acciones: list[Accion] = []
        if actualizaciones:
            self.cambio = True
        for act in actualizaciones:
            self.datos["offset"] = max(self.datos["offset"], act["update_id"] + 1)
            if "callback_query" in act:
                acciones += self._boton(act["callback_query"], chat_id, hoy)
            elif "message" in act:
                acciones += self._comando(act["message"], chat_id)
        return acciones

    def _boton(self, consulta: dict, chat_id: str, hoy: date) -> list[Accion]:
        mensaje = consulta.get("message") or {}
        if str((mensaje.get("chat") or {}).get("id")) != str(chat_id):
            return []  # solo aceptamos botones de tu chat
        accion, _, clave = (consulta.get("data") or "").partition(":")
        oferta = self.datos["ofertas"].get(clave)
        if accion == NADA or not oferta:
            return [Accion("responder_boton", callback_id=consulta["id"], texto="")]

        estado = self.datos["estados"].setdefault(clave, {})
        if accion == POSTULE:
            estado.update(estado="postulado", fecha=hoy.isoformat())
            texto, boton = "Registrado: te postulaste", f"✅ Te postulaste · {oferta['titulo'][:30]}"
        elif accion == NO_ME_INTERESA:
            estado.update(estado="descartado", fecha=hoy.isoformat())
            texto, boton = "Listo, descartada", f"🚫 Descartada · {oferta['titulo'][:30]}"
        elif accion in (ENTREVISTA, SIN_RESPUESTA, RECHAZO):
            resultado = {ENTREVISTA: "entrevista", SIN_RESPUESTA: "sin_respuesta", RECHAZO: "rechazado"}[accion]
            estado.update(seguimiento=resultado, fecha_seguimiento=hoy.isoformat())
            texto, boton = {"entrevista": ("¡Bien ahí! 🎉", "🎉 Te llamaron"),
                            "sin_respuesta": ("Anotado", "⏳ Sin respuesta"),
                            "rechazado": ("Anotado. A la próxima", "❌ No quedó")}[resultado]
        else:
            return [Accion("responder_boton", callback_id=consulta["id"], texto="")]

        acciones = [Accion("responder_boton", callback_id=consulta["id"], texto=texto)]
        # En el mensaje compacto de alertas hay botones de varias ofertas: no los reemplazamos
        if mensaje.get("message_id") and not (mensaje.get("text") or "").startswith("📬"):
            acciones.append(Accion("editar_botones", mensaje_id=mensaje["message_id"],
                                   teclado=[[("Ver oferta ↗", oferta["url"])], [(boton, f"{NADA}:{clave}")]]))
        if accion == SIN_RESPUESTA:
            acciones.append(Accion("mensaje", texto=mensaje_de_seguimiento(oferta)))
        return acciones

    def _comando(self, mensaje: dict, chat_id: str) -> list[Accion]:
        if str((mensaje.get("chat") or {}).get("id")) != str(chat_id):
            return []
        if (mensaje.get("text") or "").strip().lower().startswith("/postulaciones"):
            return [Accion("mensaje", texto=self.listado())]
        return []

    # ---------- Seguimiento y listados ----------

    def pendientes_de_seguimiento(self, hoy: date) -> list[tuple[str, dict]]:
        """Postulaciones de hace 7 días o más a las que todavía no les preguntamos."""
        limite = (hoy - timedelta(days=DIAS_PARA_SEGUIMIENTO)).isoformat()
        return [(clave, self.datos["ofertas"][clave]) for clave, est in self.datos["estados"].items()
                if est.get("estado") == "postulado" and est.get("fecha", "9999") <= limite
                and not est.get("preguntado") and clave in self.datos["ofertas"]]

    def marcar_preguntado(self, clave: str) -> None:
        self.datos["estados"][clave]["preguntado"] = True
        self.cambio = True

    @staticmethod
    def teclado_seguimiento(clave: str) -> list:
        return [[("🎉 Me llamaron", f"{ENTREVISTA}:{clave}")],
                [("⏳ Sin respuesta", f"{SIN_RESPUESTA}:{clave}"), ("❌ No quedé", f"{RECHAZO}:{clave}")]]

    def postulaciones_entre(self, desde: date, hasta: date) -> int:
        return sum(1 for est in self.datos["estados"].values()
                   if est.get("estado") == "postulado" and desde.isoformat() <= est.get("fecha", "") <= hasta.isoformat())

    def listado(self) -> str:
        filas = sorted(((self.datos["ofertas"].get(c), e) for c, e in self.datos["estados"].items()
                        if e.get("estado") == "postulado" and c in self.datos["ofertas"]),
                       key=lambda par: par[1].get("fecha", ""), reverse=True)
        if not filas:
            return "📋 Todavía no marcaste ninguna postulación. Usá el botón ✅ Me postulé en cada oferta."
        iconos = {"entrevista": "🎉", "sin_respuesta": "⏳", "rechazado": "❌"}
        lineas = [f"📋 <b>Tus postulaciones ({len(filas)})</b>"]
        for oferta, est in filas[:25]:
            icono = iconos.get(est.get("seguimiento"), "📨")
            empresa = f" · {_e(oferta['empresa'])}" if oferta.get("empresa") else ""
            lineas.append(f'{icono} {est["fecha"][8:10]}/{est["fecha"][5:7]} · <a href="{html.escape(oferta["url"], quote=True)}">{_e(oferta["titulo"])}</a>{empresa}')
        return "\n".join(lineas)


def mensaje_pregunta_seguimiento(oferta: dict) -> str:
    empresa = f" en {_e(oferta['empresa'])}" if oferta.get("empresa") else ""
    return (f"📌 Hace una semana te postulaste a <b>{_e(oferta['titulo'])}</b>{empresa} ({_e(oferta['fuente'])}).\n"
            "¿Te respondieron?")


def mensaje_de_seguimiento(oferta: dict) -> str:
    """Un mensaje modelo para escribirle al reclutador cuando no hubo respuesta."""
    empresa = oferta.get("empresa") or "la empresa"
    return ("💡 <b>Tip:</b> buscá en LinkedIn a quien publicó la oferta (o a alguien de RR. HH. de "
            f"{_e(empresa)}) y mandale algo así:\n\n"
            f"<i>Hola, ¿cómo estás? La semana pasada me postulé a {_e(oferta['titulo'])}. "
            "Quería contarte que me interesa mucho la posición: hice TurnoBot, una aplicación con Java, "
            "Spring Boot y React que está online (juancho2264.github.io/turnobot). "
            "Si te sirve, te paso más información. ¡Gracias!</i>")


def _e(texto: str) -> str:
    return html.escape(texto or "", quote=False)
