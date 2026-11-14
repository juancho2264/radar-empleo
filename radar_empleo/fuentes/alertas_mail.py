"""
Alertas de empleo por mail (LinkedIn, Computrabajo, Bumeran, ZonaJobs, Indeed).

Esos sitios prohíben que un programa lea sus páginas, pero te mandan las ofertas nuevas
por mail si creás una alerta. El radar lee SOLO esos mails (filtra por remitente) y
saca de cada uno los links a avisos de empleo.

En vez de depender del diseño de cada mail (que cambia seguido), buscamos los links cuyo
formato identifica a un aviso: es más estable. El texto del link suele ser el título del puesto.

Se conecta por IMAP con una "contraseña de aplicación" de Gmail (ver README). Recomendado:
usar una cuenta de Gmail aparte, solo para alertas de empleo.
"""

from __future__ import annotations

import email
import email.policy
import html
import imaplib
import re
import urllib.parse
from dataclasses import dataclass
from datetime import date, timedelta
from email.message import EmailMessage

from ..modelos import Oferta
from .base import html_a_texto

NOMBRE = "Alertas por mail"
SERVIDOR = "imap.gmail.com"
DIAS_HACIA_ATRAS = 3


@dataclass(frozen=True)
class Sitio:
    nombre: str
    remitente: str            # parte del dominio del remitente
    patron_aviso: re.Pattern  # link que identifica un aviso; el grupo 1 es el id
    dominios: tuple[str, ...] = ()  # el link TIENE que ir a uno de estos dominios (seguridad)


SITIOS = [
    Sitio("LinkedIn", "linkedin.com", re.compile(r"linkedin\.com/(?:comm/)?jobs/view/(\d+)"), ("linkedin.com",)),
    Sitio("Computrabajo", "computrabajo", re.compile(r"computrabajo\.com[^\s\"'<>]*/ofertas-de-trabajo/[^\s\"'<>]*?([0-9A-F]{16,})", re.IGNORECASE),
          ("computrabajo.com", "computrabajo.com.ar")),
    Sitio("Bumeran", "bumeran", re.compile(r"bumeran\.com\.ar/empleos/[^\s\"'<>]*?-(\d{6,})\.html"), ("bumeran.com.ar",)),
    Sitio("ZonaJobs", "zonajobs", re.compile(r"zonajobs\.com\.ar/empleos/[^\s\"'<>]*?-(\d{6,})\.html"), ("zonajobs.com.ar",)),
    Sitio("Indeed", "indeed", re.compile(r"indeed\.com[^\s\"'<>]*?[?&](?:jk|vjk)=([0-9a-f]{12,})"), ("indeed.com", "indeed.com.ar")),
]


def va_al_sitio(url: str, sitio: Sitio) -> bool:
    """
    SEGURIDAD: el link tiene que llevar de verdad al sitio, mirando el dominio real.
    Sin esto, un mail falso con "sitio-trucho.com/?x=linkedin.com/jobs/view/1" pasaría
    como oferta de LinkedIn y te llegaría a Telegram un link a una página de phishing.
    """
    partes = urllib.parse.urlsplit(url)
    host = (partes.hostname or "").lower()
    return partes.scheme == "https" and any(host == d or host.endswith("." + d) for d in sitio.dominios)

ENLACE = re.compile(r"<a\s[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", re.IGNORECASE | re.DOTALL)
TEXTOS_QUE_NO_SON_TITULOS = {"ver empleo", "ver oferta", "postularme", "solicitar", "apply", "view job", "ver mas", "ver todas"}


def buscar(usuario: str, clave: str, hoy: date | None = None) -> list[Oferta]:
    hoy = hoy or date.today()
    desde = (hoy - timedelta(days=DIAS_HACIA_ATRAS)).strftime("%d-%b-%Y")
    ofertas: dict[str, Oferta] = {}

    with imaplib.IMAP4_SSL(SERVIDOR) as imap:
        imap.login(usuario, clave)
        imap.select("INBOX", readonly=True)  # solo lectura: no marca nada como leído
        for sitio in SITIOS:
            _, ids = imap.search(None, f'(SINCE {desde} FROM "{sitio.remitente}")')
            for numero in ids[0].split():
                _, partes = imap.fetch(numero, "(RFC822)")
                mensaje = email.message_from_bytes(partes[0][1], policy=email.policy.default)
                for oferta in ofertas_del_mail(mensaje, sitio):
                    ofertas.setdefault(oferta.id, oferta)
    return list(ofertas.values())


def ofertas_del_mail(mensaje: EmailMessage, sitio: Sitio) -> list[Oferta]:
    """Saca las ofertas de un mail de alertas. Se testea sin conexión, con mails de ejemplo."""
    cuerpo = mensaje.get_body(preferencelist=("html", "plain"))
    contenido = cuerpo.get_content() if cuerpo else ""
    fecha = mensaje["Date"].datetime.date() if mensaje["Date"] else None
    return ofertas_del_html(contenido, sitio, fecha)


def ofertas_del_html(contenido: str, sitio: Sitio, fecha: date | None = None) -> list[Oferta]:
    encontradas: dict[str, Oferta] = {}
    for url, texto in ENLACE.findall(contenido):
        url = html.unescape(url)
        coincidencia = sitio.patron_aviso.search(url)
        if not coincidencia or not va_al_sitio(url, sitio):
            continue
        titulo = html_a_texto(texto).split("\n")[0].strip()
        id_aviso = f"{sitio.nombre.lower()}:{coincidencia.group(1)}"
        anterior = encontradas.get(id_aviso)
        # El mismo aviso suele tener varios links (logo, título, botón): nos quedamos con el que tiene título
        if anterior and anterior.titulo:
            continue
        if titulo.lower() in TEXTOS_QUE_NO_SON_TITULOS or len(titulo) < 4:
            titulo = ""
        encontradas[id_aviso] = Oferta(
            id=id_aviso,
            fuente=f"{sitio.nombre} (alerta)",
            titulo=titulo,
            empresa="",
            descripcion="",
            url=url.split("?")[0] if sitio.nombre in ("LinkedIn", "Bumeran", "ZonaJobs") else url,
            publicada=fecha,
            solo_titulo=True,
        )
    return [o for o in encontradas.values() if o.titulo]
