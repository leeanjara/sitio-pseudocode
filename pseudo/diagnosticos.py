"""Errores y advertencias que se le reportan al usuario."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Diagnostico:
    nivel: str      # "error" | "advertencia"
    mensaje: str
    linea: int
    col: int


class ErrorSintaxis(Exception):
    def __init__(self, mensaje, linea, col):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.linea = linea
        self.col = col


class Diagnosticos:
    def __init__(self):
        self.lista = []

    def error(self, mensaje, linea, col):
        self.lista.append(Diagnostico("error", mensaje, linea, col))

    def advertencia(self, mensaje, linea, col):
        self.lista.append(Diagnostico("advertencia", mensaje, linea, col))

    def agregar(self, exc):
        self.error(exc.mensaje, exc.linea, exc.col)

    @property
    def errores(self):
        return [d for d in self.lista if d.nivel == "error"]

    @property
    def advertencias(self):
        return [d for d in self.lista if d.nivel == "advertencia"]

    def ordenados(self):
        unicos = dict.fromkeys(self.lista)
        return sorted(unicos, key=lambda d: (d.linea, d.col))
