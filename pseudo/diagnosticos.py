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
        self._vistos = set()

    def _sumar(self, diagnostico):
        # Un mismo aviso en el mismo lugar se guarda una sola vez. Pasa, por ejemplo, con
        # 'notas[i] += 1': la posición se revisa como destino y como valor que se suma.
        if diagnostico not in self._vistos:
            self._vistos.add(diagnostico)
            self.lista.append(diagnostico)

    def error(self, mensaje, linea, col):
        self._sumar(Diagnostico("error", mensaje, linea, col))

    def advertencia(self, mensaje, linea, col):
        self._sumar(Diagnostico("advertencia", mensaje, linea, col))

    def agregar(self, exc):
        self.error(exc.mensaje, exc.linea, exc.col)

    @property
    def errores(self):
        return [d for d in self.lista if d.nivel == "error"]

    @property
    def advertencias(self):
        return [d for d in self.lista if d.nivel == "advertencia"]

    def ordenados(self):
        return sorted(self.lista, key=lambda d: (d.linea, d.col))
