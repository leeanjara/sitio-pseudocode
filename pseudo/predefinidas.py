"""Funciones que el lenguaje ya trae definidas.

Para agregar una nueva alcanza con una línea más en la tabla del final: la firma
(nombre, parámetros y tipo que devuelve) la usa el verificador, y la función de
Python que va al lado es la que se ejecuta.

Los parámetros se escriben como (nombre, tipo, es_ref). A los parámetros 'ref' la
implementación los recibe como una Celda: se les asigna el resultado con `celda.valor = ...`.

Ojo: en este pseudocódigo los caracteres se numeran desde 1, así que las posiciones
que se devuelven van corridas en uno respecto de los índices de Python.
"""
from dataclasses import dataclass
from typing import Callable

from . import nodos as N


@dataclass
class Predefinida:
    sub: N.Subprograma
    implementacion: Callable


def _instr(buscar, donde, posicion):
    """Cantidad de veces que aparece 'buscar' en 'donde'; deja en 'posicion' dónde empieza
    la primera (1 = primer caracter, 0 = no aparece)."""
    if not buscar:
        posicion.valor = 0
        return 0
    posicion.valor = donde.find(buscar) + 1
    return donde.count(buscar)


def _firma(nombre, parametros, tipo_retorno, implementacion):
    sub = N.Subprograma(
        0, 0, nombre, True,
        [N.Parametro(0, 0, n, t, ref) for n, t, ref in parametros],
        tipo_retorno, [], [])
    return nombre, Predefinida(sub, implementacion)


PREDEFINIDAS = dict([
    _firma("Len", [("texto", "String", False)], "Entero", len),
    _firma("Upper", [("texto", "String", False)], "String", str.upper),
    _firma("Lower", [("texto", "String", False)], "String", str.lower),
    _firma("InStr", [("buscar", "String", False),
                     ("donde", "String", False),
                     ("posicion", "Entero", True)], "Entero", _instr),
])
