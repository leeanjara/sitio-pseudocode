"""Analizador léxico: convierte el texto fuente en una lista de tokens."""
import unicodedata
from dataclasses import dataclass

PALABRAS_RESERVADAS = {
    "Programa", "Var", "Funcion", "Procedimiento", "Inicio", "Fin",
    "Si", "Sino", "Mientras", "Para",
    "Y", "O", "Mod", "Ref", "Verdadero", "Falso", "Mostrar", "Leer", "Retornar",
}
# Cada tipo con todos los nombres que acepta. El primero es el que se usa adentro del
# verificador; los otros son sinónimos. Se puede elegir cualquiera, pero en un mismo
# programa hay que usar siempre el mismo para cada tipo (ver _un_solo_nombre_por_tipo).
NOMBRES_DE_TIPO = {
    "Entero": ("Entero", "Int"),
    "Real": ("Real", "Float"),
    "String": ("String", "Cadena"),
    "Logico": ("Logico", "Bool"),
    "Caracter": ("Caracter", "Char"),
}
TIPOS = {nombre for nombres in NOMBRES_DE_TIPO.values() for nombre in nombres}
# Sinónimo -> nombre interno ('Int' -> 'Entero').
CANONICO = {nombre: canonico for canonico, nombres in NOMBRES_DE_TIPO.items()
            for nombre in nombres if nombre != canonico}

OPERADORES_DOBLES = {"==", "!=", "<=", ">=", "++", "--", "+=", "-=", "*=", "/=", "%="}
# Operadores de acumulación: 'total += 1' es lo mismo que 'total = total + 1'.
COMPUESTOS = {"+=": "+", "-=": "-", "*=": "*", "/=": "/", "%=": "%"}
OPERADORES_SIMPLES = set("<>=+-*/%(),![]")

# Símbolos de otros lenguajes: se reportan, pero se reemplazan por su equivalente
# para que el resto del análisis pueda continuar.
EQUIVALENTES = {
    "&&": ("KW", "Y", "usá 'Y' en lugar de '&&'"),
    "||": ("KW", "O", "usá 'O' en lugar de '||'"),
    "<>": ("OP", "!=", "usá '!=' en lugar de '<>'"),
}
PISTAS_SIMBOLOS = {
    ";": "no hace falta ';' al final de las líneas",
    ":": "no se usa ':'; el tipo va después del nombre, separado por un espacio (ej: 'edad Entero')",
    "{": "los bloques no usan llaves; se cierran con 'Fin', 'Fin Si', 'Fin Mientras', etc.",
    "}": "los bloques no usan llaves; se cierran con 'Fin', 'Fin Si', 'Fin Mientras', etc.",
}
# Palabras de cierre escritas todo junto.
PALABRAS_JUNTAS = {
    "finsi": ("Fin", "Si"),
    "finmientras": ("Fin", "Mientras"),
    "finpara": ("Fin", "Para"),
    "sinosi": ("Sino", "Si"),
}
# Palabra reservada seguida de otra escrita en minúscula (ej: "Fin si").
CORRECCIONES_TRAS = {
    "Fin": {"si": "Si", "mientras": "Mientras", "para": "Para"},
    "Sino": {"si": "Si"},
}


@dataclass
class Token:
    tipo: str       # ID KW TIPO ENTERO FLOTANTE CADENA CARACTER OP NL EOF
    valor: object
    linea: int
    col: int


def normalizar(texto):
    """Minúsculas y sin tildes, para detectar palabras reservadas mal escritas."""
    descompuesto = unicodedata.normalize("NFD", texto)
    return "".join(c for c in descompuesto if unicodedata.category(c) != "Mn").lower()


def _es_digito(c):
    return "0" <= c <= "9"


def _es_letra_id(c):
    return c.isalnum() or c == "_"


def tokenizar(fuente, diag):
    tokens = []
    i, n = 0, len(fuente)
    linea, inicio_linea = 1, 0

    def agregar(tipo, valor, col):
        tokens.append(Token(tipo, valor, linea, col))

    while i < n:
        c = fuente[i]
        col = i - inicio_linea + 1

        if c == "\n":
            agregar("NL", "\n", col)
            i += 1
            linea += 1
            inicio_linea = i
            continue
        if c in " \t\r﻿":
            i += 1
            continue
        if fuente.startswith("//", i):
            while i < n and fuente[i] != "\n":
                i += 1
            continue

        if _es_digito(c):
            j = i
            while j < n and _es_digito(fuente[j]):
                j += 1
            if j + 1 < n and fuente[j] == "." and _es_digito(fuente[j + 1]):
                j += 1
                while j < n and _es_digito(fuente[j]):
                    j += 1
                agregar("FLOTANTE", float(fuente[i:j]), col)
            else:
                agregar("ENTERO", int(fuente[i:j]), col)
            if j < n and (fuente[j].isalpha() or fuente[j] == "_"):
                k = j
                while k < n and _es_letra_id(fuente[k]):
                    k += 1
                diag.error(f"'{fuente[i:k]}' no es un nombre válido: los nombres no pueden "
                           "empezar con un número", linea, col)
                tokens.pop()
                agregar("ID", fuente[i:k], col)
                j = k
            i = j
            continue

        if c.isalpha() or c == "_":
            j = i
            while j < n and _es_letra_id(fuente[j]):
                j += 1
            palabra = fuente[i:j]
            junta = PALABRAS_JUNTAS.get(normalizar(palabra))
            if junta:
                diag.error(f"'{palabra}' se escribe separado: '{junta[0]} {junta[1]}'", linea, col)
                agregar("KW", junta[0], col)
                agregar("KW", junta[1], col + len(junta[0]))
            elif palabra in PALABRAS_RESERVADAS:
                agregar("KW", palabra, col)
            elif palabra in TIPOS:
                agregar("TIPO", palabra, col)
            else:
                agregar("ID", palabra, col)
            i = j
            continue

        if c == '"':
            j = i + 1
            while j < n and fuente[j] not in '"\n':
                j += 1
            agregar("CADENA", fuente[i + 1:j], col)
            if j < n and fuente[j] == '"':
                i = j + 1
            else:
                diag.error('texto sin cerrar: falta la comilla " del final', linea, col)
                i = j
            continue

        if c == "'":
            j = i + 1
            while j < n and fuente[j] not in "'\n":
                j += 1
            contenido = fuente[i + 1:j]
            if j < n and fuente[j] == "'":
                i = j + 1
            else:
                diag.error("caracter sin cerrar: falta la comilla ' del final", linea, col)
                i = j
            if len(contenido) == 1:
                agregar("CARACTER", contenido, col)
            else:
                diag.error("entre comillas simples va un solo caracter; para textos usá "
                           'comillas dobles ("...")', linea, col)
                agregar("CADENA", contenido, col)
            continue

        dos = fuente[i:i + 2]
        if dos in EQUIVALENTES:
            tipo, valor, pista = EQUIVALENTES[dos]
            diag.error(pista, linea, col)
            agregar(tipo, valor, col)
            i += 2
            continue
        if dos in OPERADORES_DOBLES:
            agregar("OP", dos, col)
            i += 2
            continue
        if c in OPERADORES_SIMPLES:
            agregar("OP", c, col)
            i += 1
            continue

        pista = PISTAS_SIMBOLOS.get(c)
        diag.error(f"símbolo no válido '{c}'" + (f": {pista}" if pista else ""), linea, col)
        i += 1

    col = i - inicio_linea + 1
    if not tokens or tokens[-1].tipo != "NL":
        agregar("NL", "\n", col)
    agregar("EOF", None, col)

    for a, b in zip(tokens, tokens[1:]):
        if a.tipo == "KW" and b.tipo == "ID" and a.linea == b.linea:
            correcto = CORRECCIONES_TRAS.get(a.valor, {}).get(normalizar(b.valor))
            if correcto:
                diag.error(f"se escribe '{a.valor} {correcto}' (con mayúscula)", b.linea, b.col)
                b.tipo, b.valor = "KW", correcto

    _un_solo_nombre_por_tipo(tokens, diag)
    return tokens


def _un_solo_nombre_por_tipo(tokens, diag):
    """Cada tipo acepta varios nombres ('Entero' o 'Int'), pero no se mezclan.

    Se respeta el que aparece primero: es el que el estudiante eligió, y así el programa
    queda parejo sin que el verificador imponga un nombre. La regla es por tipo: usar
    'Int' para los enteros y 'Real' para los reales está bien.
    """
    for nombres in NOMBRES_DE_TIPO.values():
        usos = {nombre: [t for t in tokens if t.tipo == "TIPO" and t.valor == nombre]
                for nombre in nombres}
        usados = [nombre for nombre in nombres if usos[nombre]]
        if len(usados) < 2:
            continue
        elegido = min(usados, key=lambda n: (usos[n][0].linea, usos[n][0].col))
        primero = usos[elegido][0]
        for nombre in usados:
            if nombre == elegido:
                continue
            for t in usos[nombre]:
                diag.error(f"este programa ya usa '{elegido}' (línea {primero.linea}): "
                           f"'{nombre}' y '{elegido}' son el mismo tipo, pero hay que elegir "
                           "uno solo y usarlo en todo el programa", t.linea, t.col)
