"""
Señales de que una oferta puede ser trucha, una búsqueda falsa o un intento de juntar datos.

Cada regla mira la oferta y, si encuentra algo raro, devuelve una Alerta:
- "grave": una sola alcanza para descartar (ej. te piden plata).
- "media": una sola no descarta, pero dos o más sí (ej. contacto solo por WhatsApp + empresa anónima).

Ninguna regla es perfecta: por eso las "medias" no descartan solas. Si una oferta buena
queda afuera, se ajusta la regla y se agrega un test con ese caso.
"""

from __future__ import annotations

import re
from datetime import date

from .analisis import contiene, normalizar
from .modelos import Alerta, Oferta

# Frases típicas de estafas y búsquedas falsas (ya normalizadas: minúsculas y sin tildes)
# Frases completas, no palabras sueltas: "abonar" solo aparece también en
# "se abonará un sueldo competitivo", que es una oferta normal.
PIDE_PLATA = [
    "deberas abonar", "debes abonar", "tenes que abonar", "tendras que abonar", "abonar una inscripcion",
    "costo de inscripcion", "pagar el curso", "pagar la capacitacion", "curso pago", "capacitacion paga",
    "kit de inicio", "inversion inicial", "cuota de ingreso", "transferencia previa", "pago por adelantado",
]
PIDE_DATOS_SENSIBLES = [
    "cbu", "cvu", "numero de tarjeta", "datos bancarios", "clave fiscal", "foto del dni",
    "foto de tu dni", "dni frente y dorso", "codigo de seguridad",
]
PROMESAS_IRREALES = [
    "gana hasta", "ganar dinero facil", "ingresos ilimitados", "sin experiencia y gana",
    "trabaja desde casa y gana", "libertad financiera", "se tu propio jefe", "dinero rapido",
]
CONTACTO_INFORMAL = ["whatsapp", "wsp", "telegram", "escribime al", "mandame un mensaje"]
CORREO_PERSONAL = re.compile(r"[\w.+-]+@(gmail|hotmail|outlook|yahoo|live)\.com", re.IGNORECASE)
EMPRESA_ANONIMA = {"", "confidencial", "empresa confidencial", "importante empresa", "reconocida empresa", "anonimo"}

DIAS_AVISO_VIEJO = 45
LARGO_MINIMO_DESCRIPCION = 250


def revisar(oferta: Oferta, hoy: date | None = None) -> list[Alerta]:
    """Devuelve todas las alertas que encuentra en la oferta (lista vacía = parece legítima)."""
    hoy = hoy or date.today()
    texto = normalizar(f"{oferta.titulo} {oferta.descripcion}")
    alertas: list[Alerta] = []

    # contiene() busca palabras completas: "sena" no coincide dentro de "resena"
    if any(contiene(texto, frase) for frase in PIDE_PLATA):
        alertas.append(Alerta("grave", "Pide que pagues algo para acceder al trabajo"))
    if any(contiene(texto, frase) for frase in PIDE_DATOS_SENSIBLES):
        alertas.append(Alerta("grave", "Pide datos bancarios o de identidad antes de una entrevista"))
    if any(contiene(texto, frase) for frase in PROMESAS_IRREALES):
        alertas.append(Alerta("grave", "Promete ganancias fáciles o ilimitadas"))

    if any(contiene(texto, palabra) for palabra in CONTACTO_INFORMAL):
        alertas.append(Alerta("media", "El contacto es por WhatsApp o Telegram, no por un canal de la empresa"))
    if CORREO_PERSONAL.search(oferta.descripcion):
        alertas.append(Alerta("media", "Usa un mail personal (Gmail, Hotmail…) en vez de uno de la empresa"))
    # Las alertas por mail traen solo el título: no sabemos la empresa ni la descripción,
    # así que esas dos reglas no aplican (si no, saltarían siempre)
    if not oferta.solo_titulo:
        if normalizar(oferta.empresa).strip() in EMPRESA_ANONIMA:
            alertas.append(Alerta("media", "No dice qué empresa es"))
        if len(oferta.descripcion) < LARGO_MINIMO_DESCRIPCION:
            alertas.append(Alerta("media", "La descripción es muy corta o vaga"))
    if oferta.publicada and (hoy - oferta.publicada).days > DIAS_AVISO_VIEJO:
        alertas.append(Alerta("media", f"Publicada hace más de {DIAS_AVISO_VIEJO} días: puede ser una búsqueda que ya no está activa"))

    return alertas


def veredicto(alertas: list[Alerta]) -> str:
    """Motivo de descarte, o "" si la oferta puede mostrarse."""
    graves = [a for a in alertas if a.gravedad == "grave"]
    medias = [a for a in alertas if a.gravedad == "media"]
    if graves:
        return f"Sospechosa: {graves[0].motivo.lower()}"
    if len(medias) >= 2:
        return "Sospechosa: " + " y ".join(a.motivo.lower() for a in medias[:2])
    return ""
