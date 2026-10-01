"""Nodos del árbol sintáctico que produce el parser."""
from dataclasses import dataclass


@dataclass
class Nodo:
    linea: int
    col: int


# ---------------------------------------------------------------------- Tipos
#
# Los tipos simples son textos: "Entero", "Real", "String"... Un arreglo no entra en un
# texto (tiene un tamaño y un tipo adentro), así que tiene su propia clase.

@dataclass(frozen=True)
class TipoArreglo:
    """'notas[10] Real' es TipoArreglo("Real", 10).

    Una matriz 'm[3][4] Entero' es un arreglo de 3 filas, cada una un arreglo de 4
    Enteros: TipoArreglo(TipoArreglo("Entero", 4), 3). Así m[i] da una fila y m[i][j] un
    Entero sin que nadie tenga que saber cuántas dimensiones hay.

    Es inmutable para que dos arreglos del mismo tipo sean iguales con ==, igual que dos
    "Entero".
    """
    elemento: object        # un tipo simple (str) u otro TipoArreglo
    tamanio: int

    def __str__(self):
        # Como se declara: 'arreglo Entero[3][4]'. Es lo que aparece en los mensajes.
        tamanios, tipo = "", self
        while isinstance(tipo, TipoArreglo):
            tamanios += f"[{tipo.tamanio}]"
            tipo = tipo.elemento
        return f"arreglo {tipo}{tamanios}"


def tipo_arreglo(tipo, tamanios):
    """'m[3][4] Entero' -> TipoArreglo(TipoArreglo("Entero", 4), 3). Sin tamaños, el tipo."""
    for tamanio in reversed(tamanios):
        tipo = TipoArreglo(tipo, tamanio)
    return tipo


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
    """Acceso por posición: base[indice], en un texto o en un arreglo.

    'base' puede ser a su vez otro Indice: m[i][j] es Indice(Indice(m, i), j).
    """
    base: Nodo
    indice: Nodo


def desarmar(lugar):
    """m[i][j] -> (Variable m, [Indice de m[i], Indice de m[i][j]]), de afuera hacia adentro.

    Con una variable suelta devuelve (variable, []).
    """
    accesos = []
    while isinstance(lugar, Indice):
        accesos.append(lugar)
        lugar = lugar.base
    return lugar, accesos[::-1]


def es_lugar(expr):
    """Si 'expr' es un lugar donde se puede guardar un valor: x, notas[i], m[i][j], t[1]."""
    raiz, _ = desarmar(expr)
    return isinstance(raiz, Variable)


@dataclass
class Conversion(Nodo):
    """Conversión explícita: Entero(x), Cadena(x), Char(x)...

    'destino' es el nombre interno del tipo ('Entero' aunque se haya escrito 'Int');
    'escrito' es como lo puso el estudiante, para que los errores hablen su idioma.
    """
    destino: str
    expr: Nodo
    escrito: str


@dataclass
class Unaria(Nodo):
    op: str
    operando: Nodo


# ------------------------------------------------------------------ Sentencias

@dataclass
class Asignacion(Nodo):
    nombre: str
    expr: Nodo
    # Cuando se le da valor a una posición ('notas[i] = 7', 'texto[1] = 'A'', 'm[i][j] = 0'),
    # el lugar completo como Indice. En 'x = 1' queda en None y alcanza con 'nombre'.
    lugar: Indice | None = None


@dataclass
class LlamadaProc(Nodo):
    llamada: Llamada


@dataclass
class Mostrar(Nodo):
    args: list


@dataclass
class Retornar(Nodo):
    """'Retornar valor': le da el valor a la función y la termina en ese momento.

    Convive con 'nombre_funcion = valor', que también le da el valor pero no la termina.
    """
    expr: Nodo


@dataclass
class Leer(Nodo):
    variables: list     # lugares: Variable o Indice (Leer(notas[i]))


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
    tipo: str | TipoArreglo


@dataclass
class Parametro(Nodo):
    nombre: str
    tipo: str | TipoArreglo
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
