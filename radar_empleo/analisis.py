"""
Compatibilidad entre una oferta y tu perfil.

Idea: buscamos en el aviso qué tecnologías pide (usando el catálogo de sinónimos)
y calculamos qué porcentaje de esas tenés vos. Las que aparecen en el TÍTULO
pesan el doble, porque suelen ser las importantes ("Desarrollador Java Jr").
"""

from __future__ import annotations

import re
import unicodedata
from functools import lru_cache

from .catalogo import NIVELES, TECNOLOGIAS
from .modelos import Oferta, Perfil


def normalizar(texto: str) -> str:
    """Minúsculas y sin tildes: "Programación" → "programacion"."""
    sin_tildes = unicodedata.normalize("NFD", texto)
    sin_tildes = "".join(c for c in sin_tildes if unicodedata.category(c) != "Mn")
    return sin_tildes.lower()


@lru_cache(maxsize=None)
def _patron(variante: str) -> re.Pattern[str]:
    # Palabra completa: "java" no debe coincidir con "javascript".
    # Usamos lookarounds en vez de \b porque variantes como "c#" o ".net" tienen símbolos.
    return re.compile(r"(?<![\w.#+])" + re.escape(variante) + r"(?![\w#+])")


def contiene(texto: str, variante: str) -> bool:
    return _patron(variante).search(texto) is not None


def tecnologias_en(texto: str) -> set[str]:
    """Devuelve los nombres canónicos de las tecnologías mencionadas en el texto."""
    t = normalizar(texto)
    return {nombre for nombre, variantes in TECNOLOGIAS.items() if any(contiene(t, v) for v in variantes)}


_PUESTO = r"(?:desarrollador|desarrolladora|developer|programador|programadora|ingeniero|engineer|perfil|analista)"
# Captura "3 años", "5+ años" y también rangos ("1 a 2 años", "1-2 años", "1 y 2 años"): se queda con el primero
_ANIOS = re.compile(r"(\d{1,2})(?:\s*(?:a|y|o|-|to)\s*\d{1,2})?\s*\+?\s*(?:anos|years)")


def _nivel_por_palabras(texto: str) -> str | None:
    # "semi senior" se revisa antes que "senior", si no se leería como senior
    for nivel in ("trainee", "junior", "semi senior", "senior"):
        if any(contiene(texto, palabra) for palabra in NIVELES[nivel]):
            return nivel
    return None


def _orden_de_aparicion(texto: str, tecnologias: set[str]) -> list[str]:
    t = normalizar(texto)

    def primera_posicion(tecnologia: str) -> int:
        posiciones = [m.start() for v in TECNOLOGIAS[tecnologia] if (m := _patron(v).search(t))]
        return min(posiciones, default=len(t))

    return sorted(tecnologias, key=lambda tec: (primera_posicion(tec), tec))


def detectar_nivel(oferta: Oferta) -> str:
    """
    El nivel que pide la oferta.
    - En el TÍTULO alcanza con la palabra ("Java Developer Sr").
    - En la DESCRIPCIÓN hay que ser más cuidadoso: "vas a trabajar con seniors" no hace senior
      al puesto. Ahí miramos los años de experiencia pedidos o frases como "desarrollador senior".
    """
    nivel_titulo = _nivel_por_palabras(normalizar(oferta.titulo))
    if nivel_titulo:
        return nivel_titulo

    desc = normalizar(oferta.descripcion)
    for nivel in ("trainee", "junior", "semi senior", "senior"):
        variantes = "|".join(re.escape(v) for v in NIVELES[nivel])
        if re.search(rf"{_PUESTO}\s+(?:\w+\s+){{0,2}}(?:{variantes})(?![\w])", desc) or \
           re.search(rf"(?<![\w])(?:{variantes})\s+{_PUESTO}", desc):
            return nivel

    anios = [int(n) for n in _ANIOS.findall(desc)]
    if anios:
        minimo = min(anios)  # "1 a 2 años" → 1
        if minimo >= 4:
            return "senior"
        if minimo >= 2:
            return "semi senior"
        return "junior"
    if any(contiene(desc, p) for p in NIVELES["trainee"]):
        return "trainee"
    return "sin especificar"


def compatibilidad(oferta: Oferta, perfil: Perfil) -> tuple[int, list[str], list[str]]:
    """
    Devuelve (porcentaje, tecnologías que tenés, tecnologías que te faltan).
    Si el aviso no menciona ninguna tecnología conocida, el porcentaje es 0:
    preferimos no avisarte antes que avisarte algo que no sabemos evaluar.
    """
    en_titulo = tecnologias_en(oferta.titulo)
    pedidas = en_titulo | tecnologias_en(oferta.descripcion)
    if not pedidas:
        return 0, [], []

    peso = {t: 2 if t in en_titulo else 1 for t in pedidas}
    # Ordenadas como aparecen en el aviso (título primero): lo importante suele ir antes
    orden = _orden_de_aparicion(f"{oferta.titulo}\n{oferta.descripcion}", pedidas)
    tiene = [t for t in orden if t in perfil.habilidades]
    falta = [t for t in orden if t not in perfil.habilidades]

    puntos = sum(peso[t] for t in tiene)
    total = sum(peso.values())
    porcentaje = round(100 * puntos / total)

    # Si el título pide algo central que no tenés (ej. "Desarrollador .NET"), la oferta no es para vos
    if en_titulo and not (en_titulo & perfil.habilidades):
        porcentaje = min(porcentaje, 30)
    return porcentaje, tiene, falta
