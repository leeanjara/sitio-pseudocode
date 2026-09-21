"""Nodos del árbol sintáctico que produce el parser."""
from dataclasses import dataclass, field


@dataclass
class Nodo:
    linea: int
    col: int


# ---------------------------------------------------------------- Expresiones

@dataclass
class Literal(Nodo):
    valor: object
    tipo: str


@dataclass
class Variable(Nodo):
    nombre: str


@dataclass
class Llamada(Nodo):
    nombre: str
    args: list


@dataclass
class Binaria(Nodo):
    op: str
    izq: Nodo
    der: Nodo


@dataclass
class Indice(Nodo):
    """Acceso por posición: base[indice].

    Hoy la base solo puede ser texto, pero el nodo no lo sabe: cuando existan los
    arreglos sirve igual, y 'base' puede ser a su vez otro Indice.
    """
    base: Nodo
    indice: Nodo


@dataclass
class Unaria(Nodo):
    op: str
    operando: Nodo


# ------------------------------------------------------------------ Sentencias

@dataclass
class Asignacion(Nodo):
    nombre: str
    expr: Nodo
    # Posiciones entre corchetes del destino: vacío en 'x = 1', un elemento en
    # 'texto[3] = ...'. Es una lista para que 'arreglo[i][j]' entre sin cambiar el nodo.
    indices: list = field(default_factory=list)


@dataclass
class LlamadaProc(Nodo):
    llamada: Llamada


@dataclass
class Mostrar(Nodo):
    args: list


@dataclass
class Leer(Nodo):
    variables: list


@dataclass
class Si(Nodo):
    ramas: list          # [(condicion, cuerpo)] -> el Si y cada Sino Si
    sino: list | None


@dataclass
class Mientras(Nodo):
    condicion: Nodo
    cuerpo: list


@dataclass
class Para(Nodo):
    """Para (inicializacion, incremento, condicion) ... Fin Para"""
    inicializacion: Asignacion
    incremento: Asignacion
    condicion: Nodo
    cuerpo: list


# ------------------------------------------------------------- Declaraciones

@dataclass
class DeclVar(Nodo):
    nombre: str
    tipo: str


@dataclass
class Parametro(Nodo):
    nombre: str
    tipo: str
    ref: bool


@dataclass
class Subprograma(Nodo):
    nombre: str
    es_funcion: bool
    parametros: list
    tipo_retorno: str | None
    variables: list
    cuerpo: list


@dataclass
class Programa(Nodo):
    nombre: str
    variables: list
    subprogramas: list
    cuerpo: list
