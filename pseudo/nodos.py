"""Nodos del árbol sintáctico que produce el parser."""
from dataclasses import dataclass


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
class Unaria(Nodo):
    op: str
    operando: Nodo


# ------------------------------------------------------------------ Sentencias

@dataclass
class Asignacion(Nodo):
    nombre: str
    expr: Nodo


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


@dataclass
class Repetir(Nodo):
    cuerpo: list
    condicion: Nodo


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
