"""Tests del núcleo: compatibilidad, nivel, anti-estafas y sugerencias."""

from datetime import date
from pathlib import Path

import pytest

from radar_empleo import antiestafa
from radar_empleo.analisis import detectar_nivel, tecnologias_en
from radar_empleo.evaluador import evaluar
from radar_empleo.modelos import Oferta, Perfil

HOY = date(2026, 11, 14)
RELLENO = (" Ofrecemos obra social, capacitaciones, horario flexible y un equipo que acompaña tu crecimiento "
           "profesional dentro de una empresa de software con clientes en toda Latinoamérica.") * 2


@pytest.fixture(scope="module")
def perfil() -> Perfil:
    return Perfil.desde_yaml(Path(__file__).parent.parent / "perfil.yaml")


def oferta(titulo: str, descripcion: str, **extra) -> Oferta:
    datos = dict(id="test:1", fuente="test", titulo=titulo, empresa="Acme Software",
                 descripcion=descripcion + RELLENO, url="https://ejemplo.com/1", publicada=HOY, remoto=True)
    datos.update(extra)
    return Oferta(**datos)


# ---------- Ofertas que te sirven ----------

def test_oferta_java_junior_sirve_y_sugiere_turnobot(perfil):
    ev = evaluar(oferta("Desarrollador Java Junior",
                        "Buscamos dev con Java, Spring Boot, APIs REST, Git y SQL. Suma Docker."), perfil, HOY)
    assert ev.sirve, ev.descartada_por
    assert ev.porcentaje == 100
    assert ev.nivel == "junior"
    assert ev.sugerencias[0].startswith("Poné TurnoBot primero")


def test_sugiere_escribir_la_tecnologia_como_el_aviso(perfil):
    ev = evaluar(oferta("Backend Developer Trainee", "Stack: Java, Spring, Hibernate y servicios RESTful."), perfil, HOY)
    assert ev.sirve, ev.descartada_por
    # El CV dice "Spring Data JPA" pero no "Hibernate": conviene escribirlo como el aviso
    assert any("hibernate" in s for s in ev.sugerencias)
    # "Spring" ya aparece en el CV (dentro de "Spring Boot"): no hace falta sugerirlo
    assert not any("“spring”" in s for s in ev.sugerencias)


def test_lo_que_falta_se_avisa_pero_nunca_se_agrega(perfil):
    ev = evaluar(oferta("Desarrollador Java Jr", "Java, Spring Boot, SQL y Angular."), perfil, HOY)
    assert "angular" in ev.falta
    assert any("No lo agregues" in s for s in ev.sugerencias)


# ---------- Filtros ----------

def test_estafa_se_descarta(perfil):
    ev = evaluar(oferta("Trabajo desde casa",
                        "Ganá hasta $900.000 por mes con Java y React. Deberás abonar el kit de inicio. "
                        "Escribinos por WhatsApp."), perfil, HOY)
    assert not ev.sirve
    assert ev.descartada_por.startswith("Sospechosa")


def test_una_sola_senal_media_no_descarta(perfil):
    ev = evaluar(oferta("Desarrollador Java Junior", "Java, Spring Boot y SQL. Consultas por Telegram."), perfil, HOY)
    assert ev.sirve, ev.descartada_por
    assert len(ev.alertas) == 1


def test_dos_senales_medias_descartan(perfil):
    ev = evaluar(oferta("Desarrollador Java Junior", "Java, Spring Boot y SQL. Mandá tu CV por WhatsApp.",
                        empresa="Empresa confidencial"), perfil, HOY)
    assert not ev.sirve
    assert "Sospechosa" in ev.descartada_por


def test_frases_normales_no_disparan_alertas():
    o = oferta("Desarrollador Java Junior",
               "Se abonará un sueldo competitivo. Trabajarás con una reseña de código semanal.")
    assert antiestafa.revisar(o, HOY) == []


def test_aviso_viejo_genera_alerta():
    o = oferta("Desarrollador Java Junior", "Java y Spring Boot.", publicada=date(2026, 8, 1))
    assert any("45 días" in a.motivo for a in antiestafa.revisar(o, HOY))


def test_senior_se_descarta(perfil):
    ev = evaluar(oferta("Java Developer Sr", "Java, Spring Boot, microservicios."), perfil, HOY)
    assert ev.descartada_por == "Pide nivel senior"


def test_solo_otra_region_se_descarta(perfil):
    ev = evaluar(oferta("Junior Java Developer", "Java, Spring Boot, SQL. US only, must reside in Texas."), perfil, HOY)
    assert "otra región" in ev.descartada_por


def test_titulo_con_tecnologia_que_no_tenes_baja_el_puntaje(perfil):
    ev = evaluar(oferta("Desarrollador .NET Junior", "C#, .NET Core, SQL Server, Git y SQL."), perfil, HOY)
    assert ev.porcentaje <= 30
    assert not ev.sirve


# ---------- Nivel ----------

@pytest.mark.parametrize("titulo, descripcion, esperado", [
    ("Desarrollador Java", "Vas a trabajar junto a desarrolladores senior que te van a acompañar.", "sin especificar"),
    ("Desarrollador Java", "Buscamos un desarrollador semi senior.", "semi senior"),
    ("Desarrollador Java", "Requisito: 3 años de experiencia en Java.", "semi senior"),
    ("Desarrollador Java", "Al menos 5+ años de experiencia.", "senior"),
    ("Desarrollador Java", "Entre 1 y 2 años de experiencia.", "junior"),
    ("Pasante de desarrollo", "Java y SQL.", "trainee"),
    ("Desarrollador Java Semi Senior", "", "semi senior"),
])
def test_detecta_nivel(titulo, descripcion, esperado):
    assert detectar_nivel(oferta(titulo, descripcion)) == esperado


# ---------- Catálogo ----------

def test_java_no_coincide_con_javascript():
    assert tecnologias_en("Experiencia en JavaScript y React") == {"javascript", "react"}


def test_herramientas_parecidas_no_se_mezclan():
    # Saber Maven no significa saber Gradle: tienen que ser tecnologías distintas
    assert tecnologias_en("Gradle y Jenkins") == {"gradle", "jenkins"}


def test_simbolos_en_nombres():
    assert {"c#", ".net", "node"} <= tecnologias_en("C#, ASP.NET y Node.js")


# ---------- Idioma ----------

@pytest.mark.parametrize("descripcion", [
    "Java y Spring Boot. Inglés intermedio excluyente.",
    "Java y Spring Boot. Nivel de inglés: avanzado.",
    "Java y Spring Boot. Buscamos un perfil bilingüe.",
    "Java y Spring Boot. Excelente nivel de inglés: B2 o superior.",
])
def test_con_ingles_basico_descarta_si_piden_mas(perfil, descripcion):
    ev = evaluar(oferta("Desarrollador Java Junior", descripcion), perfil, HOY)
    assert ev.descartada_por == "Pide inglés intermedio o más"


def test_ingles_basico_no_descarta(perfil):
    ev = evaluar(oferta("Desarrollador Java Junior", "Java, Spring Boot y SQL. Inglés básico."), perfil, HOY)
    assert ev.sirve, ev.descartada_por


def test_aviso_en_ingles_se_descarta(perfil):
    texto = ("We are looking for a junior Java developer to join our team. You will work with Spring Boot "
             "and SQL, and you will collaborate with our engineers on the experience of our users. ")
    ev = evaluar(oferta("Junior Java Developer", texto, ubicacion="LATAM"), perfil, HOY)
    assert ev.descartada_por == "Aviso en inglés"


def test_si_el_perfil_sabe_ingles_no_descarta(perfil):
    from dataclasses import replace
    avanzado = replace(perfil, ingles="avanzado")
    ev = evaluar(oferta("Desarrollador Java Junior", "Java y Spring Boot. Inglés avanzado."), avanzado, HOY)
    assert ev.sirve, ev.descartada_por
