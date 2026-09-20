"""Intérprete: ejecuta un programa que ya pasó el análisis sin errores."""
import sys

from . import nodos as N
from .predefinidas import PREDEFINIDAS

MAX_PROFUNDIDAD = 1000


class ErrorEjecucion(Exception):
    def __init__(self, mensaje, nodo):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.linea = nodo.linea
        self.col = nodo.col


class Celda:
    """Lugar donde vive el valor de una variable (compartible por parámetros 'ref')."""
    __slots__ = ("tipo", "valor")

    def __init__(self, tipo, valor=None):
        self.tipo = tipo
        self.valor = valor


def convertir(tipo, valor):
    if tipo == "Flotante" and type(valor) is int:
        return float(valor)
    return valor


def formatear(valor):
    if isinstance(valor, bool):
        return "Verdadero" if valor else "Falso"
    if isinstance(valor, float):
        if valor.is_integer():
            return f"{valor:.1f}"
        texto = f"{valor:.10f}".rstrip("0")
        return texto + "0" if texto.endswith(".") else texto
    return str(valor)


def division_entera(a, b):
    """Division truncada hacia cero, como en C o Java."""
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b > 0) else -q


class Interprete:
    def __init__(self, programa, entrada=input, salida=print, max_pasos=10_000_000):
        self.programa = programa
        self.entrada = entrada
        self.salida = salida
        self.max_pasos = max_pasos
        self.pasos = 0
        self.profundidad = 0
        self.subprogramas = {s.nombre: s for s in programa.subprogramas}
        self.globales = {d.nombre: Celda(d.tipo) for d in programa.variables}

    def ejecutar(self):
        limite_previo = sys.getrecursionlimit()
        sys.setrecursionlimit(max(limite_previo, 50 * MAX_PROFUNDIDAD))
        try:
            self.bloque(self.programa.cuerpo, None)
        finally:
            sys.setrecursionlimit(limite_previo)

    def contar_paso(self, nodo):
        self.pasos += 1
        if self.pasos > self.max_pasos:
            raise ErrorEjecucion(f"se superó el límite de {self.max_pasos:,} pasos; "
                                 "¿hay un bucle infinito?", nodo)

    def celda(self, nombre, marco):
        if marco is not None and nombre in marco:
            return marco[nombre]
        return self.globales[nombre]

    # ------------------------------------------------------------- sentencias

    def bloque(self, sentencias, marco):
        for s in sentencias:
            self.sentencia(s, marco)

    def sentencia(self, s, marco):
        self.contar_paso(s)
        if isinstance(s, N.Asignacion):
            celda = self.celda(s.nombre, marco)
            celda.valor = convertir(celda.tipo, self.evaluar(s.expr, marco))
        elif isinstance(s, N.LlamadaProc):
            self.llamar(s.llamada, marco)
        elif isinstance(s, N.Mostrar):
            self.salida("".join(formatear(self.evaluar(a, marco)) for a in s.args))
        elif isinstance(s, N.Leer):
            for v in s.variables:
                celda = self.celda(v.nombre, marco)
                celda.valor = self.leer_valor(celda.tipo, v)
        elif isinstance(s, N.Si):
            for condicion, cuerpo in s.ramas:
                if self.evaluar(condicion, marco):
                    self.bloque(cuerpo, marco)
                    return
            if s.sino:
                self.bloque(s.sino, marco)
        elif isinstance(s, N.Mientras):
            while self.evaluar(s.condicion, marco):
                self.contar_paso(s)
                self.bloque(s.cuerpo, marco)
        elif isinstance(s, N.Repetir):
            while True:
                self.contar_paso(s)
                self.bloque(s.cuerpo, marco)
                if self.evaluar(s.condicion, marco):
                    break
        elif isinstance(s, N.Para):
            self.para(s, marco)

    def para(self, s, marco):
        self.sentencia(s.inicializacion, marco)
        while self.evaluar(s.condicion, marco):
            self.contar_paso(s)
            self.bloque(s.cuerpo, marco)
            self.sentencia(s.incremento, marco)

    def leer_valor(self, tipo, variable):
        try:
            texto = self.entrada()
        except EOFError:
            raise ErrorEjecucion(f"Leer({variable.nombre}): no hay más datos de entrada", variable)
        limpio = texto.strip()
        try:
            if tipo == "Entero":
                return int(limpio)
            if tipo == "Flotante":
                return float(limpio.replace(",", "."))
        except ValueError:
            raise ErrorEjecucion(f"Leer({variable.nombre}): se esperaba un número {tipo}, pero se "
                                 f"ingresó '{texto}'", variable)
        if tipo == "Booleano":
            if limpio.lower() in ("verdadero", "falso"):
                return limpio.lower() == "verdadero"
            raise ErrorEjecucion(f"Leer({variable.nombre}): se esperaba Verdadero o Falso, pero se "
                                 f"ingresó '{texto}'", variable)
        if tipo == "Caracter" and len(texto) != 1:
            raise ErrorEjecucion(f"Leer({variable.nombre}): se esperaba un solo caracter, pero se "
                                 f"ingresó '{texto}'", variable)
        return texto

    # ------------------------------------------------------------ expresiones

    def llamar(self, llamada, marco):
        predefinida = PREDEFINIDAS.get(llamada.nombre)
        if predefinida is not None:
            # A los parámetros 'ref' se les pasa la celda, para que puedan devolver un valor.
            valores = [self.celda(arg.nombre, marco) if p.ref else self.evaluar(arg, marco)
                       for p, arg in zip(predefinida.sub.parametros, llamada.args)]
            return predefinida.implementacion(*valores)

        sub = self.subprogramas[llamada.nombre]
        nuevo = {}
        for p, arg in zip(sub.parametros, llamada.args):
            if p.ref:
                nuevo[p.nombre] = self.celda(arg.nombre, marco)
            else:
                nuevo[p.nombre] = Celda(p.tipo, convertir(p.tipo, self.evaluar(arg, marco)))
        for d in sub.variables:
            nuevo[d.nombre] = Celda(d.tipo)
        if sub.es_funcion:
            nuevo[sub.nombre] = Celda(sub.tipo_retorno)

        self.profundidad += 1
        if self.profundidad > MAX_PROFUNDIDAD:
            raise ErrorEjecucion(f"más de {MAX_PROFUNDIDAD} llamadas anidadas; ¿hay una recursión "
                                 "que nunca termina?", llamada)
        try:
            self.bloque(sub.cuerpo, nuevo)
        finally:
            self.profundidad -= 1

        if sub.es_funcion:
            valor = nuevo[sub.nombre].valor
            if valor is None:
                raise ErrorEjecucion(f"la función '{sub.nombre}' terminó sin asignar su valor de "
                                     "retorno", llamada)
            return valor
        return None

    def evaluar(self, e, marco):
        if isinstance(e, N.Literal):
            return e.valor
        if isinstance(e, N.Variable):
            valor = self.celda(e.nombre, marco).valor
            if valor is None:
                raise ErrorEjecucion(f"la variable '{e.nombre}' se usa antes de tener un valor", e)
            return valor
        if isinstance(e, N.Llamada):
            return self.llamar(e, marco)
        if isinstance(e, N.Unaria):
            v = self.evaluar(e.operando, marco)
            return {"No": lambda: not v, "-": lambda: -v, "+": lambda: v}[e.op]()

        op = e.op
        if op == "Y":
            return bool(self.evaluar(e.izq, marco)) and bool(self.evaluar(e.der, marco))
        if op == "O":
            return bool(self.evaluar(e.izq, marco)) or bool(self.evaluar(e.der, marco))
        a = self.evaluar(e.izq, marco)
        b = self.evaluar(e.der, marco)
        if op in ("/", "%") and b == 0:
            raise ErrorEjecucion("división por cero", e)
        ambos_enteros = type(a) is int and type(b) is int
        if op == "/":
            return division_entera(a, b) if ambos_enteros else a / b
        if op == "%":
            return a - b * division_entera(a, b) if ambos_enteros else a % b
        return {
            "+": lambda: a + b, "-": lambda: a - b, "*": lambda: a * b,
            "==": lambda: a == b, "!=": lambda: a != b, "<": lambda: a < b,
            ">": lambda: a > b, "<=": lambda: a <= b, ">=": lambda: a >= b,
        }[op]()
