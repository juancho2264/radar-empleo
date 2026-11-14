"""
Junta todo: para cada oferta decide si te sirve, cuánto encaja y qué ajustar del CV.

El orden de los filtros importa: primero lo barato y seguro (palabras excluidas,
estafas, nivel, ubicación) y al final la compatibilidad.
"""

from __future__ import annotations

import re
from datetime import date

from . import antiestafa
from .analisis import compatibilidad, contiene, detectar_nivel, normalizar
from .catalogo import TECNOLOGIAS
from .modelos import Evaluacion, Oferta, Perfil

# Señales de que la oferta es solo para otra región (típico en avisos remotos internacionales)
SOLO_OTRA_REGION = ["us only", "usa only", "u.s. only", "united states only", "us citizens", "eu only",
                    "europe only", "uk only", "canada only", "must be located in the us", "must reside in"]
PALABRAS_EN_INGLES = {"the", "and", "with", "you", "will", "our", "for", "experience", "team", "we", "are", "your"}


def evaluar(oferta: Oferta, perfil: Perfil, hoy: date | None = None) -> Evaluacion:
    porcentaje, tiene, falta = compatibilidad(oferta, perfil)
    nivel = detectar_nivel(oferta)
    alertas = antiestafa.revisar(oferta, hoy)
    ev = Evaluacion(oferta, porcentaje, tiene, falta, nivel, alertas)

    ev.descartada_por = _motivo_de_descarte(ev, perfil)
    if ev.sirve:
        ev.sugerencias = sugerencias_cv(ev, perfil)
    return ev


def _motivo_de_descarte(ev: Evaluacion, perfil: Perfil) -> str:
    texto = normalizar(f"{ev.oferta.titulo} {ev.oferta.descripcion}")
    excluida = next((p for p in perfil.excluir if contiene(texto, normalizar(p))), None)
    if excluida:
        return f"Menciona “{excluida}”"

    sospecha = antiestafa.veredicto(ev.alertas)
    if sospecha:
        return sospecha

    if ev.nivel not in perfil.niveles_aceptados:
        return f"Pide nivel {ev.nivel}"

    region = _fuera_de_zona(ev.oferta, perfil)
    if region:
        return region

    if ev.porcentaje < perfil.compatibilidad_minima:
        return f"Compatibilidad baja ({ev.porcentaje}%)"
    return ""


# Regiones de un trabajo remoto que te incluyen
REGIONES_ABIERTAS = ["worldwide", "anywhere", "global", "remote", "remoto", "americas", "latam", "latin america",
                     "latinoamerica", "south america", "sudamerica", "argentina"]


def _fuera_de_zona(oferta: Oferta, perfil: Perfil) -> str:
    lugar = normalizar(f"{oferta.ubicacion} {oferta.descripcion}")
    if any(frase in lugar for frase in SOLO_OTRA_REGION):
        return "Solo para candidatos de otra región"

    ubicacion = normalizar(oferta.ubicacion)
    if not ubicacion:
        return ""
    te_incluye = any(u in ubicacion for u in perfil.ubicaciones) or any(r in ubicacion for r in REGIONES_ABIERTAS)
    if te_incluye:
        return ""
    # Remoto pero solo para ciertos países (ej. "USA"), o presencial en otro lugar
    return f"Solo para candidatos de {oferta.ubicacion}" if oferta.remoto else f"Presencial en {oferta.ubicacion}"


def esta_en_ingles(oferta: Oferta) -> bool:
    palabras = re.findall(r"[a-z]+", oferta.descripcion.lower())
    if len(palabras) < 30:
        return False
    return sum(p in PALABRAS_EN_INGLES for p in palabras) / len(palabras) > 0.08


# ---------------------------------------------------------------------------
# Sugerencias para ajustar el CV. Reordenan y destacan lo que YA tenés: nunca inventan.
# ---------------------------------------------------------------------------

def sugerencias_cv(ev: Evaluacion, perfil: Perfil) -> list[str]:
    sugerencias: list[str] = []
    pedidas = set(ev.tiene) | set(ev.falta)

    # 1. Qué proyecto poner primero: el que muestra más de lo que pide el aviso
    mejor, coincidencias = max(
        ((nombre, techs & pedidas) for nombre, techs in perfil.proyectos.items()),
        key=lambda par: len(par[1]),
        default=(None, set()),
    )
    if mejor and coincidencias:
        en_orden = [t for t in ev.tiene if t in coincidencias]
        sugerencias.append(f"Poné {mejor} primero en Proyectos: muestra {_lista(en_orden[:4])}, que pide el aviso.")

    # 2. Orden de habilidades: primero las que pide el aviso
    if len(ev.tiene) >= 2:
        sugerencias.append(f"En Habilidades, empezá por {_lista(ev.tiene[:5])}.")

    # 3. Escribir la tecnología como la escribe el aviso (los filtros buscan coincidencias exactas)
    #    Solo si tu CV no lo dice ya de esa forma.
    texto_aviso = normalizar(f"{ev.oferta.titulo} {ev.oferta.descripcion}")
    texto_cv = normalizar(perfil.cv_texto)
    for tecnologia in ev.tiene:
        variantes_en_aviso = [v for v in TECNOLOGIAS[tecnologia] if contiene(texto_aviso, v)]
        if not variantes_en_aviso or any(contiene(texto_cv, v) for v in variantes_en_aviso):
            continue
        como_lo_dice = max(variantes_en_aviso, key=len)
        sugerencias.append(f"El aviso dice “{como_lo_dice}”: escribilo igual en tu CV (es lo mismo que {tecnologia}).")
        if len(sugerencias) >= 5:
            break

    # 4. Lo que falta: avisar, nunca agregar
    if ev.falta:
        sugerencias.append(f"Te falta {_lista(ev.falta[:4])}. No lo agregues si no lo usaste: en la entrevista decí que lo estás aprendiendo.")

    if esta_en_ingles(ev.oferta):
        sugerencias.append("El aviso está en inglés: seguramente pidan inglés intermedio.")
    return sugerencias


def _lista(items: list[str]) -> str:
    items = [str(i) for i in items]
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " y " + items[-1]
