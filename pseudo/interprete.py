"""Intérprete: ejecuta un programa que ya pasó el análisis sin errores."""
import re
import sys

from . import nodos as N
from .predefinidas import PREDEFINIDAS

MAX_PROFUNDIDAD = 1000
# Lo que Entero("...") y Real("...") aceptan. Más estricto que int()/float() de Python,
# que también aceptarían "1_000", "1e5" o "inf".
NUMERO_ENTERO = re.compile(r"[+-]?\d+")
NUMERO_REAL = re.compile(r"[+-]?\d+(\.\d+)?")


class ErrorEjecucion(Exception):
    def __init__(self, mensaje, nodo):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.linea = nodo.linea
        self.col = nodo.col


class _Retorno(Exception):
    """Lo lanza 'Retornar' para salir de la función desde cualquier profundidad (dentro de
    un Para, de un Si...). No es un error: lo ataja la llamada a la función."""

    def __init__(self, valor):
        super().__init__()
        self.valor = valor


class Celda:
    """Lugar donde vive el valor de una variable (compartible por parámetros 'Ref').

    Un arreglo es una lista de Celdas, una por posición: así 'notas[3]' es un lugar propio
    que se puede pasar por Ref igual que una variable. En una matriz, cada posición guarda
    a su vez la lista de Celdas de su fila.
    """
    __slots__ = ("tipo", "valor")

    def __init__(self, tipo, valor=None):
        self.tipo = tipo
        self.valor = valor


def nueva_celda(tipo):
    """La celda de una variable recién declarada. Un arreglo nace con todas sus posiciones,
    vacías; cualquier otra cosa nace sin valor."""
    if isinstance(tipo, N.TipoArreglo):
        return Celda(tipo, [nueva_celda(tipo.elemento) for _ in range(tipo.tamanio)])
    return Celda(tipo)


def copiar(valor):
    """Un arreglo pasado sin Ref: el subprograma trabaja sobre su propia copia."""
    if isinstance(valor, list):
        return [Celda(c.tipo, copiar(c.valor)) for c in valor]
    return valor


def convertir(tipo, valor):
    if tipo == "Real" and type(valor) is int:
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
        self.globales = {d.nombre: nueva_celda(d.tipo) for d in programa.variables}

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
            valor = self.evaluar(s.expr, marco)
            if s.lugar is None:
                celda = self.celda(s.nombre, marco)
                celda.valor = convertir(celda.tipo, valor)
            else:
                self.guardar(s.lugar, valor, marco)
        elif isinstance(s, N.LlamadaProc):
            self.llamar(s.llamada, marco)
        elif isinstance(s, N.Mostrar):
            self.salida("".join(formatear(self.evaluar(a, marco)) for a in s.args))
        elif isinstance(s, N.Leer):
            for lugar in s.variables:
                celda, letras, nombre = self.ubicar(lugar, marco)
                if letras:
                    # Leer(texto[1]): una letra suelta.
                    letra = self.leer_valor("Caracter", lugar, nombre)
                    celda.valor = self.cambiar_posicion(celda.valor, letras, letra, marco, nombre)
                else:
                    celda.valor = self.leer_valor(celda.tipo, lugar, nombre)
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
        elif isinstance(s, N.Para):
            self.para(s, marco)
        elif isinstance(s, N.Retornar):
            raise _Retorno(self.evaluar(s.expr, marco))

    def para(self, s, marco):
        self.sentencia(s.inicializacion, marco)
        while self.evaluar(s.condicion, marco):
            self.contar_paso(s)
            self.bloque(s.cuerpo, marco)
            self.sentencia(s.incremento, marco)

    # ----------------------------------------------------------- conversiones

    def convertir_explicito(self, e, valor):
        """Entero(x), Cadena(x)... El análisis ya garantizó que la conversión existe."""
        destino, origen, escrito = e.destino, e.origen, e.escrito
        if destino == "String":
            return formatear(valor)
        if destino == "Entero":
            if origen == "Real":
                return int(valor)               # trunca hacia cero, como la división
            if origen == "Caracter":
                # El dígito, no el código: Entero('7') da 7.
                if not "0" <= valor <= "9":
                    raise ErrorEjecucion(f"{escrito}('{valor}'): solo se convierte un caracter "
                                         "que sea un dígito, de '0' a '9'", e)
                return int(valor)
            if origen == "String":
                if not NUMERO_ENTERO.fullmatch(valor.strip()):
                    raise ErrorEjecucion(f'{escrito}("{valor}"): ese texto no es un número '
                                         "entero", e)
                return int(valor.strip())
            return valor
        if destino == "Real":
            if origen == "String":
                limpio = valor.strip().replace(",", ".")
                if not NUMERO_REAL.fullmatch(limpio):
                    raise ErrorEjecucion(f'{escrito}("{valor}"): ese texto no es un número', e)
                return float(limpio)
            return float(valor)
        if destino == "Caracter":
            if origen == "Entero":
                # El dígito, no el código: Caracter(7) da '7'. Un número de más de una
                # cifra no entra en un solo caracter; para eso está String(x).
                if not 0 <= valor <= 9:
                    raise ErrorEjecucion(f"{escrito}({valor}): solo se convierte un número de "
                                         "una cifra, de 0 a 9 (para más cifras usá "
                                         "String(x))", e)
                return str(valor)
            if origen == "String" and len(valor) != 1:
                raise ErrorEjecucion(f'{escrito}("{valor}"): el texto tiene que tener un solo '
                                     f"caracter, y tiene {len(valor)}", e)
            return valor
        return valor

    # ------------------------------------------------------------- posiciones

    def posicion(self, contenedor, expr, marco, nodo, nombre):
        """Traduce la posición del pseudocódigo (desde 1) a la de Python (desde 0)."""
        i = self.evaluar(expr, marco)
        cuantos = len(contenedor)
        if 1 <= i <= cuantos:
            return i - 1
        if isinstance(contenedor, list):
            raise ErrorEjecucion(f"la posición {i} no existe: '{nombre}' tiene {cuantos} "
                                 f"{'posición' if cuantos == 1 else 'posiciones'}, de la 1 a "
                                 f"la {cuantos}", nodo)
        raise ErrorEjecucion(f"la posición {i} no existe: hay {cuantos} "
                             f"{'caracter' if cuantos == 1 else 'caracteres'} y se "
                             f"numeran desde 1", nodo)

    def ubicar(self, lugar, marco):
        """La celda donde vive un lugar: 'x', 'notas[3]', 'm[2][1]'.

        Baja por los arreglos hasta la celda de esa posición. Devuelve (celda, accesos que
        sobran, nombre para los mensajes). Sobran accesos solo al llegar a un texto, porque
        sus letras no son celdas: en 'nombres[2][1]' la celda es la de 'nombres[2]' y queda
        el '[1]', que es una letra de ese texto.
        """
        raiz, accesos = N.desarmar(lugar)
        celda, nombre = self.celda(raiz.nombre, marco), raiz.nombre
        while accesos and isinstance(celda.tipo, N.TipoArreglo):
            acceso = accesos.pop(0)
            i = self.posicion(celda.valor, acceso.indice, marco, acceso, nombre)
            celda, nombre = celda.valor[i], f"{nombre}[{i + 1}]"
        return celda, accesos, nombre

    def guardar(self, lugar, valor, marco):
        celda, letras, nombre = self.ubicar(lugar, marco)
        if letras:
            celda.valor = self.cambiar_posicion(celda.valor, letras, valor, marco, nombre)
        else:
            celda.valor = convertir(celda.tipo, valor)

    def leer_posicion(self, e, marco):
        """El valor de 'base[i]', sea una posición de un arreglo o una letra de un texto."""
        if not N.es_lugar(e):
            # La posición de algo que no es una variable: Upper(t)[1]. Solo puede ser texto.
            base = self.evaluar(e.base, marco)
            return base[self.posicion(base, e.indice, marco, e, None)]
        celda, letras, nombre = self.ubicar(e, marco)
        valor = celda.valor
        if valor is None:
            que = f"la posición {nombre}" if "[" in nombre else f"la variable '{nombre}'"
            raise ErrorEjecucion(f"{que} se usa antes de tener un valor", e)
        for acceso in letras:
            valor = valor[self.posicion(valor, acceso.indice, marco, acceso, nombre)]
        return valor

    def cambiar_posicion(self, texto, accesos, letra, marco, nombre):
        """Devuelve el texto con una letra cambiada.

        Devuelve uno nuevo en vez de modificarlo porque los textos de Python no se pueden
        modificar en el lugar. (Los arreglos sí: ahí se cambia la celda de la posición.)
        """
        if texto is None:
            raise ErrorEjecucion(f"'{nombre}' todavía no tiene un valor: no se puede "
                                 "cambiarle una posición", accesos[0])
        i = self.posicion(texto, accesos[0].indice, marco, accesos[0], nombre)
        if len(accesos) > 1:
            letra = self.cambiar_posicion(texto[i], accesos[1:], letra, marco, nombre)
        return texto[:i] + letra + texto[i + 1:]

    def leer_valor(self, tipo, nodo, nombre):
        try:
            texto = self.entrada()
        except EOFError:
            raise ErrorEjecucion(f"Leer({nombre}): no hay más datos de entrada", nodo)
        limpio = texto.strip()
        try:
            if tipo == "Entero":
                return int(limpio)
            if tipo == "Real":
                return float(limpio.replace(",", "."))
        except ValueError:
            raise ErrorEjecucion(f"Leer({nombre}): se esperaba un número {tipo}, pero se "
                                 f"ingresó '{texto}'", nodo)
        if tipo == "Logico":
            if limpio.lower() in ("verdadero", "falso"):
                return limpio.lower() == "verdadero"
            raise ErrorEjecucion(f"Leer({nombre}): se esperaba Verdadero o Falso, pero se "
                                 f"ingresó '{texto}'", nodo)
        if tipo == "Caracter" and len(texto) != 1:
            raise ErrorEjecucion(f"Leer({nombre}): se esperaba un solo caracter, pero se "
                                 f"ingresó '{texto}'", nodo)
        return texto

    # ------------------------------------------------------------ expresiones

    def llamar(self, llamada, marco):
        predefinida = PREDEFINIDAS.get(llamada.nombre)
        if predefinida is not None:
            # A los parámetros 'Ref' se les pasa la celda, para que puedan devolver un valor.
            valores = [self.ubicar(arg, marco)[0] if p.ref else self.evaluar(arg, marco)
                       for p, arg in zip(predefinida.sub.parametros, llamada.args)]
            return predefinida.implementacion(*valores)

        sub = self.subprogramas[llamada.nombre]
        nuevo = {}
        for p, arg in zip(sub.parametros, llamada.args):
            if p.ref:
                # La misma celda de afuera: una variable o una posición de un arreglo.
                nuevo[p.nombre] = self.ubicar(arg, marco)[0]
            else:
                valor = convertir(p.tipo, self.evaluar(arg, marco))
                nuevo[p.nombre] = Celda(p.tipo, copiar(valor))
        for d in sub.variables:
            nuevo[d.nombre] = nueva_celda(d.tipo)
        if sub.es_funcion:
            nuevo[sub.nombre] = Celda(sub.tipo_retorno)

        self.profundidad += 1
        if self.profundidad > MAX_PROFUNDIDAD:
            raise ErrorEjecucion(f"más de {MAX_PROFUNDIDAD} llamadas anidadas; ¿hay una recursión "
                                 "que nunca termina?", llamada)
        try:
            self.bloque(sub.cuerpo, nuevo)
        except _Retorno as r:
            # Retornar = darle el valor al nombre de la función + salir.
            nuevo[sub.nombre].valor = convertir(sub.tipo_retorno, r.valor)
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
        if isinstance(e, N.Conversion):
            return self.convertir_explicito(e, self.evaluar(e.expr, marco))
        if isinstance(e, N.Indice):
            return self.leer_posicion(e, marco)
        if isinstance(e, N.Unaria):
            v = self.evaluar(e.operando, marco)
            return {"!": lambda: not v, "-": lambda: -v, "+": lambda: v}[e.op]()

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
