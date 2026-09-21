"""Análisis semántico: declaraciones, alcance, tipos y llamadas."""
import difflib

from . import nodos as N
from .lexer import PALABRAS_RESERVADAS, TIPOS, normalizar
from .predefinidas import PREDEFINIDAS

# Palabra reservada escrita de cualquier forma -> cómo se escribe de verdad. Sirve para
# que 'verdadero' o 'falso' no se reporten como una variable que falta declarar.
RESERVADAS_POR_FORMA = {normalizar(p): p for p in PALABRAS_RESERVADAS | TIPOS}

NUMERICOS = {"Entero", "Real"}
TEXTO = {"String", "Caracter"}
# Qué se puede indexar con [ ] y qué tipo sale de adentro. Hoy solo el texto; cuando
# existan los arreglos se agregan acá y ni el parser ni el intérprete cambian.
ELEMENTO_DE = {"String": "Caracter"}
COMPARADORES = {"==", "!=", "<", ">", "<=", ">="}
SUBPROGRAMAS = ("funcion", "procedimiento")


def asignable(destino, origen):
    if destino is None or origen is None or destino == origen:
        return True
    return (destino, origen) in {("Real", "Entero"), ("String", "Caracter")}


def articulo(sub):
    return "la función" if sub.es_funcion else "el procedimiento"


class Simbolo:
    def __init__(self, nombre, clase, tipo, nodo, sub=None):
        self.nombre = nombre
        self.clase = clase        # variable | parametro | funcion | procedimiento
        self.tipo = tipo
        self.nodo = nodo
        self.sub = sub
        self.usado = False
        self.leido = False
        self.asignado = clase == "parametro"


class Analizador:
    def __init__(self, diag):
        self.diag = diag
        self.globales = {}
        self.locales = None
        self.actual = None            # subprograma que se está analizando
        self.asigna_retorno = False
        self.avisos_global = set()
        self.no_declarados = set()
        self.predefinidas = {
            nombre: Simbolo(nombre, "funcion", p.sub.tipo_retorno, p.sub, sub=p.sub)
            for nombre, p in PREDEFINIDAS.items()
        }

    def analizar(self, programa):
        for d in programa.variables:
            self.declarar(self.globales, Simbolo(d.nombre, "variable", d.tipo, d))
        for s in programa.subprogramas:
            clase = "funcion" if s.es_funcion else "procedimiento"
            self.declarar(self.globales, Simbolo(s.nombre, clase, s.tipo_retorno, s, sub=s))

        for s in programa.subprogramas:
            self.analizar_subprograma(s)

        self.actual, self.locales = None, None
        self.bloque(programa.cuerpo)
        self.reportar_sin_uso(self.globales.values())

    # --------------------------------------------------------------- símbolos

    def declarar(self, tabla, simbolo):
        previo = tabla.get(simbolo.nombre)
        nodo = simbolo.nodo
        if simbolo.nombre in PREDEFINIDAS:
            self.diag.error(f"'{simbolo.nombre}' ya es una función predefinida del lenguaje; "
                            "usá otro nombre", nodo.linea, nodo.col)
            return
        if previo is not None:
            self.diag.error(f"'{simbolo.nombre}' ya fue declarado en la línea {previo.nodo.linea}",
                            nodo.linea, nodo.col)
            return
        if not simbolo.nombre.isascii():
            self.diag.advertencia(f"el nombre '{simbolo.nombre}' tiene tildes o 'ñ'; conviene "
                                  "evitarlas en los nombres", nodo.linea, nodo.col)
        tabla[simbolo.nombre] = simbolo

    def declarar_local(self, simbolo):
        nodo = simbolo.nodo
        if simbolo.nombre == self.actual.nombre:
            self.diag.error(f"'{simbolo.nombre}' no puede llamarse igual que "
                            f"{articulo(self.actual)} que lo contiene", nodo.linea, nodo.col)
            return
        g = self.globales.get(simbolo.nombre)
        if g is not None and g.clase in SUBPROGRAMAS:
            self.diag.error(f"'{simbolo.nombre}' ya es el nombre de {articulo(g.sub)}",
                            nodo.linea, nodo.col)
            return
        self.declarar(self.locales, simbolo)

    def buscar(self, nombre):
        """Devuelve (simbolo, es_variable_global_usada_desde_un_subprograma)."""
        if self.locales is not None and nombre in self.locales:
            return self.locales[nombre], False
        s = self.globales.get(nombre)
        if s is None:
            return self.predefinidas.get(nombre), False
        return s, self.locales is not None and s.clase == "variable"

    def no_declarado(self, nombre, nodo, que):
        clave = (self.actual.nombre if self.actual else None, nombre)
        if clave in self.no_declarados:
            return
        self.no_declarados.add(clave)

        # Si el nombre es en realidad una palabra reservada mal escrita, decirlo: mandarlo
        # a declarar una variable llamada 'verdadero' lo mandaría para el lado contrario.
        reservada = RESERVADAS_POR_FORMA.get(normalizar(nombre))
        if reservada is not None and reservada != nombre:
            self.diag.error(f"'{nombre}' no es una variable: es la palabra reservada "
                            f"'{reservada}', que se escribe así", nodo.linea, nodo.col)
            return

        visibles = list(self.globales) + list(self.locales or {}) + list(PREDEFINIDAS)
        parecidos = [v for v in visibles if v.lower() == nombre.lower()]
        parecidos += difflib.get_close_matches(nombre, visibles, n=1, cutoff=0.75)
        mensaje = f"{que} '{nombre}' no está declarada"
        if parecidos:
            mensaje += f"; ¿quisiste decir '{parecidos[0]}'?"
        self.diag.error(mensaje, nodo.linea, nodo.col)

    def resolver_variable(self, nombre, nodo, escritura):
        simbolo, global_en_sub = self.buscar(nombre)
        if simbolo is None:
            self.no_declarado(nombre, nodo, "la variable")
            return None
        if simbolo.clase in SUBPROGRAMAS:
            return simbolo
        simbolo.usado = True
        if escritura:
            simbolo.asignado = True
        else:
            simbolo.leido = True
        if global_en_sub and nombre not in self.avisos_global:
            self.avisos_global.add(nombre)
            self.diag.advertencia(f"{articulo(self.actual)} '{self.actual.nombre}' usa la "
                                  f"variable global '{nombre}'; lo recomendable es pasarla como "
                                  "parámetro", nodo.linea, nodo.col)
        return simbolo

    def reportar_sin_uso(self, simbolos):
        for s in simbolos:
            n = s.nodo
            if s.clase == "variable" and not s.usado:
                self.diag.advertencia(f"la variable '{s.nombre}' se declara pero nunca se usa",
                                      n.linea, n.col)
            elif s.clase == "variable" and s.leido and not s.asignado:
                self.diag.advertencia(f"la variable '{s.nombre}' se usa pero nunca recibe un valor "
                                      "(ni con una asignación ni con Leer)", n.linea, n.col)
            elif s.clase == "parametro" and not s.usado:
                self.diag.advertencia(f"el parámetro '{s.nombre}' no se usa", n.linea, n.col)
            elif s.clase in SUBPROGRAMAS and not s.usado:
                self.diag.advertencia(f"{articulo(s.sub)} '{s.nombre}' se declara pero nunca se "
                                      "llama", n.linea, n.col)

    # ----------------------------------------------------------- subprogramas

    def analizar_subprograma(self, sub):
        self.actual, self.locales = sub, {}
        self.asigna_retorno = False
        self.avisos_global = set()
        for p in sub.parametros:
            self.declarar_local(Simbolo(p.nombre, "parametro", p.tipo, p))
        for d in sub.variables:
            self.declarar_local(Simbolo(d.nombre, "variable", d.tipo, d))

        self.bloque(sub.cuerpo)

        if sub.es_funcion and not self.asigna_retorno:
            self.diag.error(f"la función '{sub.nombre}' nunca devuelve un valor: falta asignar "
                            f"'{sub.nombre} = ...' en su cuerpo", sub.linea, sub.col)
        self.reportar_sin_uso(self.locales.values())

    # ------------------------------------------------------------- sentencias

    def bloque(self, sentencias):
        for s in sentencias:
            self.sentencia(s)

    def sentencia(self, s):
        if isinstance(s, N.Asignacion):
            self.asignacion(s)
        elif isinstance(s, N.LlamadaProc):
            self.llamada(s.llamada, como_expresion=False)
        elif isinstance(s, N.Mostrar):
            for a in s.args:
                self.tipo(a)
        elif isinstance(s, N.Leer):
            for v in s.variables:
                simbolo = self.resolver_variable(v.nombre, v, escritura=True)
                if simbolo is not None and simbolo.clase in SUBPROGRAMAS:
                    self.diag.error(f"Leer necesita una variable, pero '{v.nombre}' es "
                                    f"{articulo(simbolo.sub)}", v.linea, v.col)
        elif isinstance(s, N.Si):
            for i, (condicion, cuerpo) in enumerate(s.ramas):
                self.condicion(condicion, "Si" if i == 0 else "Sino Si")
                self.bloque(cuerpo)
            if s.sino:
                self.bloque(s.sino)
        elif isinstance(s, N.Mientras):
            self.condicion(s.condicion, "Mientras")
            self.bloque(s.cuerpo)
        elif isinstance(s, N.Para):
            self.para(s)

    def asignacion(self, s):
        operador = getattr(s, "operador_incremento", None)
        if operador is not None:
            self.incremento(s, operador)
            return
        nombre = s.nombre
        if self.actual is not None and nombre == self.actual.nombre:
            tipo = self.tipo(s.expr)
            if not self.actual.es_funcion:
                self.diag.error(f"un procedimiento no devuelve valor: no se puede asignar a "
                                f"'{nombre}'", s.linea, s.col)
                return
            self.asigna_retorno = True
            self.verificar_asignable(self.actual.tipo_retorno, tipo, s.expr,
                                     f"el valor que devuelve '{nombre}'")
            return

        # Cambiar una posición no es darle su primer valor a la variable: el texto ya tiene
        # que existir. Por eso cuenta como lectura, y así se conserva el aviso de "se usa
        # pero nunca recibe un valor" para quien escriba t[1] = 'a' sin haber armado t.
        simbolo = self.resolver_variable(nombre, s, escritura=not s.indices)
        tipo = self.tipo(s.expr)
        if simbolo is None:
            return
        if simbolo.clase == "funcion":
            self.diag.error(f"no se puede asignar a la función '{nombre}' desde afuera; su valor "
                            "de retorno solo se asigna dentro de la propia función",
                            s.linea, s.col)
            return
        if simbolo.clase == "procedimiento":
            self.diag.error(f"no se puede asignar a '{nombre}' porque es un procedimiento",
                            s.linea, s.col)
            return
        if s.indices:
            self.asignacion_por_posicion(s, simbolo, tipo)
            return
        self.verificar_asignable(simbolo.tipo, tipo, s.expr, f"la variable '{nombre}'")

    def asignacion_por_posicion(self, s, simbolo, tipo_del_valor):
        """'texto[3] = 'S'': cambia una posición, no la variable entera."""
        contenedor = simbolo.tipo
        for indice in s.indices:
            self.verificar_posicion(indice, s)
            if contenedor is None:
                return
            if contenedor not in ELEMENTO_DE:
                self.diag.error(f"no se puede usar [ ] sobre un {contenedor}: por ahora solo "
                                "el texto tiene posiciones", s.linea, s.col)
                return
            contenedor = ELEMENTO_DE[contenedor]
        self.verificar_asignable(contenedor, tipo_del_valor, s.expr,
                                 f"la posición de '{s.nombre}'")

    def para(self, s):
        if s.inicializacion is not None:
            self.asignacion(s.inicializacion)
        if s.incremento is not None:
            self.asignacion(s.incremento)
        if s.condicion is not None:
            self.condicion(s.condicion, "Para")
        self.bloque(s.cuerpo)

    def incremento(self, s, operador):
        """'i++' o 'i--' (que el parser ya tradujo a 'i = i + 1')."""
        simbolo = self.resolver_variable(s.nombre, s, escritura=True)
        if simbolo is None:
            return
        simbolo.leido = True
        if simbolo.clase in SUBPROGRAMAS:
            self.diag.error(f"'{s.nombre}' no es una variable", s.linea, s.col)
        elif simbolo.tipo not in NUMERICOS:
            self.diag.error(f"'{operador}' solo se aplica a números, pero '{s.nombre}' es "
                            f"{simbolo.tipo}", s.linea, s.col)

    def condicion(self, condicion, instruccion):
        tipo = self.tipo(condicion)
        if tipo not in (None, "Logico"):
            self.diag.error(f"la condición del '{instruccion}' tiene que ser una comparación o una "
                            f"expresión lógica, pero es de tipo {tipo}",
                            condicion.linea, condicion.col)

    def verificar_asignable(self, destino, origen, nodo, que):
        if asignable(destino, origen):
            return
        extra = " (se perdería la parte decimal)" if (destino, origen) == ("Entero", "Real") else ""
        self.diag.error(f"{que} es {destino}, pero se le quiere dar un valor {origen}{extra}",
                        nodo.linea, nodo.col)

    # ------------------------------------------------------------ expresiones

    def tipo(self, e):
        if isinstance(e, N.Literal):
            return e.tipo
        if isinstance(e, N.Variable):
            return self.tipo_variable(e)
        if isinstance(e, N.Llamada):
            return self.llamada(e, como_expresion=True)
        if isinstance(e, N.Unaria):
            return self.tipo_unaria(e)
        if isinstance(e, N.Binaria):
            return self.tipo_binaria(e)
        if isinstance(e, N.Indice):
            return self.tipo_indice(e)
        return None

    def tipo_indice(self, e):
        """Tipo de 'base[i]'. Devuelve el tipo del elemento, o None si no se puede."""
        base = self.tipo(e.base)
        self.verificar_posicion(e.indice, e)
        if base is None:
            return None
        if base not in ELEMENTO_DE:
            self.diag.error(f"no se puede usar [ ] sobre un {base}: por ahora solo el texto "
                            "tiene posiciones", e.linea, e.col)
            return None
        return ELEMENTO_DE[base]

    def verificar_posicion(self, expr, nodo):
        tipo = self.tipo(expr)
        if tipo not in (None, "Entero"):
            self.diag.error(f"la posición entre corchetes tiene que ser un Entero, no un "
                            f"{tipo}", nodo.linea, nodo.col)

    def tipo_variable(self, e):
        simbolo = self.resolver_variable(e.nombre, e, escritura=False)
        if simbolo is None:
            return None
        if simbolo.clase == "funcion":
            if self.actual is simbolo.sub:
                self.diag.error(f"dentro de la función, '{e.nombre}' solo se usa para asignarle el "
                                "valor de retorno; para ir acumulando usá una variable local",
                                e.linea, e.col)
            else:
                self.diag.error(f"'{e.nombre}' es una función: para usarla hay que llamarla con "
                                f"paréntesis, ej: {e.nombre}(...)", e.linea, e.col)
            return simbolo.tipo
        if simbolo.clase == "procedimiento":
            self.diag.error(f"'{e.nombre}' es un procedimiento y no tiene un valor", e.linea, e.col)
            return None
        return simbolo.tipo

    def tipo_unaria(self, e):
        tipo = self.tipo(e.operando)
        if e.op == "!":
            if tipo not in (None, "Logico"):
                self.diag.error(f"'!' se aplica a condiciones (Logico), no a un {tipo}",
                                e.linea, e.col)
            return "Logico"
        if tipo not in (None, "Entero", "Real"):
            self.diag.error(f"el signo '{e.op}' solo se aplica a números, no a un {tipo}",
                            e.linea, e.col)
            return None
        return tipo

    def tipo_binaria(self, e):
        op = e.op
        a, b = self.tipo(e.izq), self.tipo(e.der)

        if op in ("Y", "O"):
            for tipo, lado in ((a, e.izq), (b, e.der)):
                if tipo not in (None, "Logico"):
                    self.diag.error(f"'{op}' une condiciones (Logico), pero de este lado hay un "
                                    f"{tipo}", lado.linea, lado.col)
            return "Logico"
        if a is None or b is None:
            return "Logico" if op in COMPARADORES else None

        if op in COMPARADORES:
            valido = ((a in NUMERICOS and b in NUMERICOS) or (a in TEXTO and b in TEXTO)
                      or (op in ("==", "!=") and a == b == "Logico"))
            if not valido:
                self.diag.error(f"no se puede comparar un {a} con un {b} usando '{op}'",
                                e.linea, e.col)
            return "Logico"
        if op == "+" and a in TEXTO and b in TEXTO:
            return "String"
        # Si viene de 'x += 1' los mensajes hablan de '+=', que es lo que escribió el alumno.
        escrito = getattr(e, "operador_compuesto", op)
        if op == "%":
            if a != "Entero" or b != "Entero":
                self.diag.error(f"el operador '{escrito}' (resto) solo funciona con Enteros, pero "
                                f"acá hay {a} y {b}", e.linea, e.col)
            return "Entero"
        if a in NUMERICOS and b in NUMERICOS:
            return "Real" if "Real" in (a, b) else "Entero"

        mensaje = f"no se puede usar '{escrito}' entre un {a} y un {b}"
        if escrito == "+" and (a in TEXTO or b in TEXTO):
            mensaje += "; para mostrar textos y números juntos separalos con comas en Mostrar(...)"
        self.diag.error(mensaje, e.linea, e.col)
        return None

    def llamada(self, e, como_expresion):
        simbolo, _ = self.buscar(e.nombre)
        if simbolo is None or simbolo.clase not in SUBPROGRAMAS:
            if simbolo is None:
                que = "la función" if como_expresion else "el procedimiento"
                self.no_declarado(e.nombre, e, que)
            else:
                self.diag.error(f"'{e.nombre}' es una variable, no una función ni un procedimiento",
                                e.linea, e.col)
            for a in e.args:
                self.tipo(a)
            return None

        simbolo.usado = True
        sub = simbolo.sub
        if como_expresion and not sub.es_funcion:
            self.diag.error(f"'{e.nombre}' es un procedimiento: no devuelve ningún valor, así que no "
                            "se puede usar dentro de una expresión", e.linea, e.col)
        if not como_expresion and sub.es_funcion:
            self.diag.advertencia(f"se llama a la función '{e.nombre}' pero se descarta el valor "
                                  "que devuelve", e.linea, e.col)
        self.verificar_argumentos(e, sub)
        return sub.tipo_retorno

    def verificar_argumentos(self, e, sub):
        esperados, recibidos = len(sub.parametros), len(e.args)
        if esperados != recibidos:
            self.diag.error(f"{articulo(sub)} '{sub.nombre}' espera {esperados} "
                            f"argumento{'s' if esperados != 1 else ''} pero recibe {recibidos}",
                            e.linea, e.col)
            for a in e.args:
                self.tipo(a)
            return

        for p, a in zip(sub.parametros, e.args):
            if not p.ref:
                self.verificar_asignable(p.tipo, self.tipo(a), a,
                                         f"el parámetro '{p.nombre}' de '{sub.nombre}'")
                continue
            if not isinstance(a, N.Variable):
                self.diag.error(f"el parámetro '{p.nombre}' de '{sub.nombre}' es por referencia "
                                "(Ref): hay que pasarle una variable, no una expresión",
                                a.linea, a.col)
                self.tipo(a)
                continue
            simbolo = self.resolver_variable(a.nombre, a, escritura=True)
            if simbolo is None:
                continue
            if simbolo.clase in SUBPROGRAMAS:
                self.diag.error(f"el parámetro '{p.nombre}' de '{sub.nombre}' es por referencia "
                                "(Ref): hay que pasarle una variable", a.linea, a.col)
                continue
            simbolo.leido = True
            if simbolo.tipo != p.tipo:
                self.diag.error(f"el parámetro por referencia '{p.nombre}' es {p.tipo}, pero la "
                                f"variable '{a.nombre}' es {simbolo.tipo}; con 'Ref' los tipos "
                                "tienen que coincidir exactamente", a.linea, a.col)
