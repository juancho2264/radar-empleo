"""Tests del seguimiento de postulaciones y del reporte semanal."""

from datetime import date, datetime

from radar_empleo import telegram
from radar_empleo.estadisticas import Estadisticas
from radar_empleo.modelos import Oferta
from radar_empleo.postulaciones import Postulaciones, clave_de

HOY = date(2026, 11, 14)
CHAT = "12345"
OFERTA = Oferta(id="getonboard:" + "x" * 120, fuente="Get on Board", titulo="Desarrollador Java Junior",
                empresa="Acme", descripcion="", url="https://ejemplo.com/oferta")


def boton(dato: str, chat: str = CHAT, update_id: int = 10, texto_mensaje: str = "🟢 89% · Desarrollador Java") -> dict:
    return {"update_id": update_id, "callback_query": {
        "id": f"cb{update_id}", "data": dato,
        "message": {"message_id": 99, "chat": {"id": int(chat)}, "text": texto_mensaje}}}


def test_la_clave_entra_en_el_limite_de_telegram():
    teclado = Postulaciones.teclado_oferta(clave_de(OFERTA.id), OFERTA.url)
    assert all(len(v.encode()) <= 64 for fila in teclado for _, v in fila if not v.startswith("http"))


def test_el_archivo_queda_cifrado_y_se_puede_volver_a_abrir(tmp_path):
    ruta = tmp_path / "postulaciones.enc"
    p = Postulaciones(ruta, "token-secreto")
    p.registrar_enviada(OFERTA, HOY)
    p.guardar(HOY)
    assert b"Acme" not in ruta.read_bytes()                      # nadie lo puede leer en el repo público
    assert Postulaciones(ruta, "token-secreto").datos["ofertas"]  # con el token correcto, sí
    otro = Postulaciones(ruta, "otro-token")
    assert otro.ilegible and otro.datos["ofertas"] == {}          # con otro token, arranca de cero sin romperse


def test_me_postule_registra_y_actualiza_los_botones(tmp_path):
    p = Postulaciones(tmp_path / "p.enc", "t")
    clave = p.registrar_enviada(OFERTA, HOY)
    acciones = p.procesar([boton(f"p:{clave}")], CHAT, HOY)
    assert p.datos["estados"][clave]["estado"] == "postulado"
    assert p.offset == 11                                         # la próxima vez pide desde la siguiente
    editar = next(a for a in acciones if a.tipo == "editar_botones")
    assert editar.mensaje_id == 99 and "Te postulaste" in editar.teclado[1][0][0]


def test_ignora_botones_de_otros_chats(tmp_path):
    p = Postulaciones(tmp_path / "p.enc", "t")
    clave = p.registrar_enviada(OFERTA, HOY)
    assert p.procesar([boton(f"p:{clave}", chat="999")], CHAT, HOY) == []
    assert clave not in p.datos["estados"]


def test_en_el_mensaje_de_alertas_no_se_tocan_los_botones_de_las_otras(tmp_path):
    p = Postulaciones(tmp_path / "p.enc", "t")
    clave = p.registrar_enviada(OFERTA, HOY)
    acciones = p.procesar([boton(f"p:{clave}", texto_mensaje="📬 3 ofertas de tus alertas")], CHAT, HOY)
    assert not any(a.tipo == "editar_botones" for a in acciones)
    assert p.datos["estados"][clave]["estado"] == "postulado"


def test_seguimiento_a_los_7_dias_y_tip_si_no_respondieron(tmp_path):
    p = Postulaciones(tmp_path / "p.enc", "t")
    clave = p.registrar_enviada(OFERTA, date(2026, 11, 1))
    p.procesar([boton(f"p:{clave}")], CHAT, date(2026, 11, 1))
    assert p.pendientes_de_seguimiento(date(2026, 11, 7)) == []          # todavía no pasó una semana
    assert [c for c, _ in p.pendientes_de_seguimiento(HOY)] == [clave]
    p.marcar_preguntado(clave)
    assert p.pendientes_de_seguimiento(HOY) == []                        # se pregunta una sola vez

    acciones = p.procesar([boton(f"s:{clave}", update_id=20)], CHAT, HOY)
    assert p.datos["estados"][clave]["seguimiento"] == "sin_respuesta"
    tip = next(a for a in acciones if a.tipo == "mensaje")
    assert "Desarrollador Java Junior" in tip.texto and "turnobot" in tip.texto


def test_comando_postulaciones(tmp_path):
    p = Postulaciones(tmp_path / "p.enc", "t")
    clave = p.registrar_enviada(OFERTA, HOY)
    p.procesar([boton(f"p:{clave}")], CHAT, HOY)
    [accion] = p.procesar([{"update_id": 30, "message": {"chat": {"id": int(CHAT)}, "text": "/postulaciones"}}], CHAT, HOY)
    assert "Tus postulaciones (1)" in accion.texto and "Acme" in accion.texto


def test_reporte_semanal(tmp_path):
    est = Estadisticas(tmp_path / "e.json")
    est.registrar_mercado(HOY, [["java", "typescript"], ["java", "typescript", "aws"], ["react", "typescript"], ["java"]])
    domingo = datetime(2026, 11, 15, 20, 30)
    assert est.toca_resumen_semanal(domingo) and not est.toca_resumen_semanal(datetime(2026, 11, 14, 20, 30))
    texto = telegram.mensaje_semanal(est.mercado(HOY), {"java", "react"}, revisadas=40, postulaciones=2)
    assert "typescript (75%)" in texto and "empezá por <b>typescript</b>" in texto
    assert "java (75%)" in texto and "te postulaste a 2 ofertas" in texto
    est.marcar_semanal(domingo.date())
    assert not est.toca_resumen_semanal(datetime(2026, 11, 15, 23, 30))  # una vez por semana
