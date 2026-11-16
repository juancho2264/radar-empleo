"""Tests de conversión de las fuentes, mensajes de Telegram y una corrida completa simulada."""

import json
import sys
from datetime import date, datetime
from pathlib import Path

from radar_empleo import __main__ as radar
from radar_empleo import telegram
from radar_empleo.estado import Vistos
from radar_empleo.evaluador import evaluar
from radar_empleo.fuentes import getonboard, remotive
from radar_empleo.fuentes.base import html_a_texto
from radar_empleo.modelos import Perfil

PERFIL = Perfil.desde_yaml(Path(__file__).parent.parent / "perfil.yaml")

ITEM_GETONBOARD = {
    "id": "desarrollador-java-junior-acme",
    "type": "job",
    "attributes": {
        "title": "Desarrollador Java Junior",
        "description": "<p>Buscamos dev <b>Java</b> con Spring Boot, APIs REST y SQL.</p>",
        "functions": "<ul><li>Desarrollar microservicios</li><li>Escribir tests con JUnit</li></ul>",
        "desirable": "<p>Docker &amp; Git</p>",
        "benefits": "<p>Obra social, capacitaciones y horario flexible para estudiantes universitarios.</p>" * 3,
        "remote": True,
        "remote_modality": "fully_remote",
        "countries": ["Argentina"],
        "published_at": 1794571200,  # 2026-11-13 12:00 UTC
        "min_salary": 800,
        "max_salary": 1100,
        "seniority": {"data": {"id": 2, "type": "seniority"}},
        "company": {"data": {"id": "acme", "attributes": {"name": "Acme Software", "web": "https://acme.com"}}},
    },
    "links": {"public_url": "https://www.getonbrd.com/jobs/programming/desarrollador-java-junior-acme"},
}

ITEM_REMOTIVE = {
    "id": 1912345,
    "url": "https://remotive.com/remote-jobs/software-dev/junior-react-developer-1912345",
    "title": "Junior React Developer",
    "company_name": "Globex",
    "tags": ["react", "javascript", "typescript"],
    "publication_date": "2026-11-12T10:00:00",
    "candidate_required_location": "USA",
    "salary": "$50k",
    "description": "<p>We are looking for a junior React developer with JavaScript and TypeScript.</p>" * 4,
}


def test_convierte_getonboard():
    o = getonboard.convertir(ITEM_GETONBOARD)
    assert o.id == "getonboard:desarrollador-java-junior-acme"
    assert o.empresa == "Acme Software"
    assert o.remoto and o.ubicacion == "Argentina"
    assert o.publicada == date(2026, 11, 13)
    assert o.salario == "USD 800–1100"
    assert "<" not in o.descripcion and "Docker & Git" in o.descripcion
    assert o.url.startswith("https://www.getonbrd.com/jobs/")


def test_getonboard_usa_el_nivel_oficial():
    # Título sin nivel, pero Get on Board lo clasificó como Semi Senior (id 3): manda la fuente
    item = {**ITEM_GETONBOARD, "attributes": {**ITEM_GETONBOARD["attributes"], "title": "Desarrollador Java",
                                              "seniority": {"data": {"id": 3, "type": "seniority"}}}}
    ev = evaluar(getonboard.convertir(item), PERFIL, date(2026, 11, 14))
    assert ev.nivel == "semi senior" and ev.descartada_por == "Pide nivel semi senior"
    assert getonboard.convertir(ITEM_GETONBOARD).nivel == "junior"


def test_getonboard_tolera_campos_faltantes():
    o = getonboard.convertir({"id": "x", "attributes": {"title": "Dev"}})
    assert o.titulo == "Dev" and o.empresa == "" and o.publicada is None


def test_remotive_solo_usa_se_descarta():
    o = remotive.convertir(ITEM_REMOTIVE)
    assert o.publicada == date(2026, 11, 12)
    ev = evaluar(o, PERFIL, date(2026, 11, 14))
    assert ev.descartada_por == "Solo para candidatos de USA"


def test_html_a_texto():
    assert html_a_texto("<p>Hola&nbsp;<b>mundo</b></p><p>chau</p>") == "Hola mundo\nchau"


def test_mensaje_escapa_html_y_muestra_todo():
    o = getonboard.convertir(ITEM_GETONBOARD)
    o.titulo = "Dev <Java> & Spring"
    ev = evaluar(o, PERFIL, date(2026, 11, 14))
    texto = telegram.mensaje_oferta(ev)
    assert "Dev &lt;Java&gt; &amp; Spring" in texto       # un "<" sin escapar rompería el mensaje
    assert "✅ Tenés:" in texto and "📝 <b>Para tu CV:</b>" in texto
    assert "USD 800–1100" in texto


def test_memoria_olvida_lo_viejo(tmp_path):
    vistos = Vistos(tmp_path / "vistos.json")
    vistos.marcar("a", date(2026, 1, 1))
    vistos.marcar("b", date(2026, 11, 1))
    vistos.guardar(date(2026, 11, 14))
    assert json.loads((tmp_path / "vistos.json").read_text()) == {"b": "2026-11-01"}


def test_corrida_completa_simulada(monkeypatch, capsys, tmp_path):
    """Todo el flujo sin internet: fuentes falsas, una de ellas falla, y la salida va a la pantalla."""
    def falla():
        raise TimeoutError("sin respuesta")

    monkeypatch.setattr(radar, "FUENTES", {
        "Get on Board": lambda: [getonboard.convertir(ITEM_GETONBOARD)],
        "Remotive": falla,
    })
    monkeypatch.setattr(radar, "RAIZ", tmp_path)
    monkeypatch.setattr(radar, "_ahora", lambda: datetime(2026, 11, 14, 10, 0, tzinfo=radar.ZONA))  # a la mañana
    (tmp_path / "perfil.yaml").write_text((Path(__file__).parent.parent / "perfil.yaml").read_text())
    (tmp_path / "cv.txt").write_text("Java Spring Boot")
    monkeypatch.setattr(sys, "argv", ["radar_empleo", "--simular"])

    assert radar.main() == 0
    salida = capsys.readouterr().out
    assert "Desarrollador Java Junior" in salida
    assert "[Ver oferta ↗] https://www.getonbrd.com/jobs/" in salida
    assert "Revisé 1 oferta nueva: <b>1 te sirve</b>" in salida
    assert "No pude consultar Remotive: TimeoutError" in salida   # una fuente caída no frena a las demás


def test_reintenta_si_el_sitio_frena(monkeypatch):
    """Un 429 (demasiadas consultas) se reintenta; si después responde bien, no hay error."""
    import io
    import urllib.error
    from radar_empleo.fuentes import base

    respuestas = [urllib.error.HTTPError("u", 429, "Too Many Requests", {}, None), io.BytesIO(b'{"ok": true}')]

    class Respuesta:
        def __init__(self, cuerpo): self.cuerpo = cuerpo
        def __enter__(self): return self.cuerpo
        def __exit__(self, *a): return False

    def falso_urlopen(pedido, timeout):
        r = respuestas.pop(0)
        if isinstance(r, Exception):
            raise r
        return Respuesta(r)

    monkeypatch.setattr(base.urllib.request, "urlopen", falso_urlopen)
    monkeypatch.setattr(base.time, "sleep", lambda s: None)
    assert base.obtener_json("https://ejemplo.com") == {"ok": True}


def test_no_reintenta_errores_definitivos(monkeypatch):
    import urllib.error
    import pytest
    from radar_empleo.fuentes import base

    llamadas = []

    def falso_urlopen(pedido, timeout):
        llamadas.append(1)
        raise urllib.error.HTTPError("u", 404, "Not Found", {}, None)

    monkeypatch.setattr(base.urllib.request, "urlopen", falso_urlopen)
    with pytest.raises(urllib.error.HTTPError):
        base.obtener_json("https://ejemplo.com")
    assert len(llamadas) == 1


def _correr(monkeypatch, capsys, tmp_path, ofertas, hora):
    """Corre el radar (simulado) con ofertas dadas a una hora de Argentina dada. Devuelve lo impreso."""
    monkeypatch.setattr(radar, "FUENTES", {"Get on Board": lambda: list(ofertas)})
    monkeypatch.setattr(radar, "RAIZ", tmp_path)
    monkeypatch.setattr(radar, "_ahora", lambda: datetime(2026, 11, 14, hora, 30, tzinfo=radar.ZONA))
    if not (tmp_path / "perfil.yaml").exists():
        (tmp_path / "perfil.yaml").write_text((Path(__file__).parent.parent / "perfil.yaml").read_text())
    monkeypatch.setattr(sys, "argv", ["radar_empleo"])          # modo real, pero sin mandar nada:
    enviados = []
    monkeypatch.setattr(radar.telegram, "enviar", lambda token, chat, texto, teclado=None: enviados.append(texto))
    monkeypatch.setattr(radar.telegram, "novedades", lambda token, desde: [])   # nadie tocó botones
    monkeypatch.setenv("TELEGRAM_TOKEN", "x")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "1")
    assert radar.main() == 0
    capsys.readouterr()
    return enviados


def test_sin_novedades_a_la_manana_no_escribe(monkeypatch, capsys, tmp_path):
    assert _correr(monkeypatch, capsys, tmp_path, [], hora=11) == []


def test_resumen_diario_llega_una_sola_vez_aunque_no_haya_nada(monkeypatch, capsys, tmp_path):
    oferta = getonboard.convertir(ITEM_GETONBOARD)
    _correr(monkeypatch, capsys, tmp_path, [oferta], hora=11)        # a la mañana: manda la oferta
    [diario] = _correr(monkeypatch, capsys, tmp_path, [oferta], hora=20)  # ya vista: solo el resumen
    assert "Radar activo" in diario
    assert "Revisé 1 oferta nueva en 2 pasadas" in diario            # acumula las corridas del día
    assert "1 encajó con vos" in diario
    assert _correr(monkeypatch, capsys, tmp_path, [oferta], hora=23) == []   # no se repite el mismo día



def test_cada_hora_lee_botones_pero_busca_cada_3_horas(monkeypatch, capsys, tmp_path):
    llamadas = []

    def fuente():
        llamadas.append(1)
        return []

    oferta = getonboard.convertir(ITEM_GETONBOARD)
    _correr(monkeypatch, capsys, tmp_path, [oferta], hora=10)          # 10:30: busca
    monkeypatch.setattr(radar, "FUENTES", {"Get on Board": fuente})
    for hora in (11, 12):                                               # 11:30 y 12:30: solo botones
        monkeypatch.setattr(radar, "_ahora", lambda h=hora: datetime(2026, 11, 14, h, 30, tzinfo=radar.ZONA))
        assert radar.main() == 0
    assert llamadas == []
    monkeypatch.setattr(radar, "_ahora", lambda: datetime(2026, 11, 14, 13, 30, tzinfo=radar.ZONA))
    radar.main()                                                        # 13:30: pasaron 3 horas, busca
    assert llamadas == [1]


def test_de_madrugada_no_busca_pero_a_mano_si(monkeypatch, capsys, tmp_path):
    llamadas = []
    _correr(monkeypatch, capsys, tmp_path, [], hora=10)
    monkeypatch.setattr(radar, "FUENTES", {"Get on Board": lambda: llamadas.append(1) or []})
    monkeypatch.setattr(radar, "_ahora", lambda: datetime(2026, 11, 15, 3, 30, tzinfo=radar.ZONA))
    radar.main()
    assert llamadas == []                       # 3:30 de la mañana: no busca
    monkeypatch.setenv("FORZAR", "1")           # corrido a mano desde GitHub: busca siempre
    radar.main()
    assert llamadas == [1]


def test_postulaciones_no_se_reescriben_si_no_cambiaron(tmp_path):
    from radar_empleo.postulaciones import Postulaciones
    ruta = tmp_path / "p.enc"
    p = Postulaciones(ruta, "t")
    p.guardar(date(2026, 11, 14))
    antes = ruta.read_bytes()
    Postulaciones(ruta, "t").guardar(date(2026, 11, 14))   # sin cambios: no toca el archivo (no hay commit)
    assert ruta.read_bytes() == antes
