"""Errores y advertencias que se le reportan al usuario."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Diagnostico:
    nivel: str      # "error" | "advertencia"
    mensaje: str
    linea: int
    col: int
    # El tema de la referencia (web/referencia.json) que explica lo que está mal, para
    # que la página ofrezca ir a leerlo. None si no hay uno que ayude.
    tema: str | None = None


class ErrorSintaxis(Exception):
    def __init__(self, mensaje, linea, col, tema=None):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.linea = linea
        self.col = col
        self.tema = tema


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

    def error(self, mensaje, linea, col, tema=None):
        self._sumar(Diagnostico("error", mensaje, linea, col, tema))

    def advertencia(self, mensaje, linea, col, tema=None):
        self._sumar(Diagnostico("advertencia", mensaje, linea, col, tema))

    def agregar(self, exc):
        self.error(exc.mensaje, exc.linea, exc.col, exc.tema)

    @property
    def errores(self):
        return [d for d in self.lista if d.nivel == "error"]

    @property
    def advertencias(self):
        return [d for d in self.lista if d.nivel == "advertencia"]

    def ordenados(self):
        return sorted(self.lista, key=lambda d: (d.linea, d.col))
