"""Tests del lector de alertas por mail, con mails de ejemplo (sin conexión a Gmail)."""

from datetime import date
from email.message import EmailMessage
from pathlib import Path

from radar_empleo import antiestafa
from radar_empleo.evaluador import evaluar
from radar_empleo.fuentes.alertas_mail import SITIOS, ofertas_del_html, ofertas_del_mail
from radar_empleo.modelos import Perfil

PERFIL = Perfil.desde_yaml(Path(__file__).parent.parent / "perfil.yaml")
LINKEDIN = next(s for s in SITIOS if s.nombre == "LinkedIn")
BUMERAN = next(s for s in SITIOS if s.nombre == "Bumeran")

HTML_LINKEDIN = """
<table>
  <tr><td><a href="https://www.linkedin.com/comm/jobs/view/3912345678/?trackingId=abc&amp;refId=x"><img src="logo.png"></a></td>
      <td><a href="https://www.linkedin.com/comm/jobs/view/3912345678/?trackingId=abc">Desarrollador Java Junior</a><br>Acme · Buenos Aires</td></tr>
  <tr><td><a href="https://www.linkedin.com/comm/jobs/view/3998765432/?trackingId=def">Senior .NET Developer</a></td></tr>
  <tr><td><a href="https://www.linkedin.com/comm/jobs/view/3955555555/">Ver empleo</a></td></tr>
  <tr><td><a href="https://www.linkedin.com/comm/jobs/search/?keywords=java">Ver todas las ofertas</a></td></tr>
  <tr><td><a href="https://www.linkedin.com/help">Ayuda</a></td></tr>
</table>
"""


def test_saca_las_ofertas_de_un_mail_de_linkedin():
    ofertas = ofertas_del_html(HTML_LINKEDIN, LINKEDIN, date(2026, 11, 14))
    assert [o.titulo for o in ofertas] == ["Desarrollador Java Junior", "Senior .NET Developer"]
    java = ofertas[0]
    assert java.id == "linkedin:3912345678"                      # logo + título = una sola oferta
    assert java.url == "https://www.linkedin.com/comm/jobs/view/3912345678/"   # sin datos de rastreo
    assert java.solo_titulo and java.fuente == "LinkedIn (alerta)"


def test_botones_sin_titulo_y_links_que_no_son_avisos_se_ignoran():
    ids = {o.id for o in ofertas_del_html(HTML_LINKEDIN, LINKEDIN)}
    assert "linkedin:3955555555" not in ids   # solo tenía un botón "Ver empleo", sin título


def test_bumeran():
    html = '<a href="https://www.bumeran.com.ar/empleos/desarrollador-java-jr-acme-1116543210.html">Desarrollador Java Jr</a>'
    [oferta] = ofertas_del_html(html, BUMERAN)
    assert oferta.id == "bumeran:1116543210"


def test_lee_un_mail_completo():
    mail = EmailMessage()
    mail["From"] = "LinkedIn <jobalerts-noreply@linkedin.com>"
    mail["Date"] = "Sat, 14 Nov 2026 09:00:00 -0300"
    mail.set_content("Versión texto")
    mail.add_alternative(HTML_LINKEDIN, subtype="html")
    ofertas = ofertas_del_mail(mail, LINKEDIN)
    assert len(ofertas) == 2 and ofertas[0].publicada == date(2026, 11, 14)


def test_oferta_de_alerta_se_evalua_por_el_titulo():
    java, net = ofertas_del_html(HTML_LINKEDIN, LINKEDIN, date(2026, 11, 14))
    ev = evaluar(java, PERFIL, date(2026, 11, 14))
    assert ev.sirve, ev.descartada_por
    assert antiestafa.revisar(java, date(2026, 11, 14)) == []   # sin descripción no salta "descripción vaga"
    assert not evaluar(net, PERFIL, date(2026, 11, 14)).sirve    # senior y .NET
