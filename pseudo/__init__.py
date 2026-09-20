"""Verificador e intérprete del pseudocódigo de la materia."""
from dataclasses import dataclass

from .diagnosticos import Diagnosticos
from .indentacion import verificar as verificar_sangria
from .interprete import ErrorEjecucion, Interprete
from .lexer import tokenizar
from .nodos import Programa
from .parser import Parser
from .semantico import Analizador

__all__ = ["analizar", "Resultado", "Interprete", "ErrorEjecucion"]


@dataclass
class Resultado:
    programa: Programa | None
    diagnosticos: Diagnosticos

    @property
    def ok(self):
        return self.programa is not None and not self.diagnosticos.errores


def analizar(fuente):
    """Analiza el texto de un programa y devuelve el árbol y los errores/advertencias.

    El análisis semántico (tipos, declaraciones, llamadas) y la verificación de la sangría
    solo corren si no hubo errores de sintaxis, para no reportar errores en cascada: con la
    sintaxis rota, los niveles de anidación que anotó el parser no son confiables.
    """
    diag = Diagnosticos()
    tokens = tokenizar(fuente, diag)
    parser = Parser(tokens, diag)
    programa = parser.parse()
    if programa is not None and not diag.errores:
        Analizador(diag).analizar(programa)
        verificar_sangria(fuente, parser.sangria, diag)
    return Resultado(programa, diag)
