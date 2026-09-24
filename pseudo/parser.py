"""Analizador sintáctico: convierte la lista de tokens en un árbol (ver nodos.py).

Gramática (resumida):

    programa      := 'Programa' ID NL [bloque_var] subprograma* 'Inicio' NL sentencias 'Fin'
    bloque_var    := 'Var' NL (ID {',' ID} TIPO NL)*
    subprograma   := 'Funcion' ID '(' params ')' TIPO NL [bloque_var] 'Inicio' NL sentencias 'Fin'
                   | 'Procedimiento' ID '(' params ')' NL [bloque_var] 'Inicio' NL sentencias 'Fin'
    params        := [ ['Ref'] ID TIPO {',' ['Ref'] ID TIPO} ]
    sentencia     := asignacion | ID '(' args ')' | 'Mostrar' '(' args ')' | 'Leer' '(' ID {',' ID} ')'
                   | 'Si' '(' expr ')' ... {'Sino' 'Si' '(' expr ')' ...} ['Sino' ...] 'Fin' 'Si'
                   | 'Mientras' '(' expr ')' ... 'Fin' 'Mientras'
                   | 'Para' '(' asignacion ',' asignacion ',' expr ')' ... 'Fin' 'Para'
    asignacion    := ID '=' expr | ID ('+=' | '-=' | '*=' | '/=' | '%=') expr | ID ('++' | '--')
"""
from . import nodos as N
from .diagnosticos import ErrorSintaxis
from .indentacion import Sangria
from .lexer import CANONICO, COMPUESTOS, normalizar

COMPARADORES = ("==", "!=", "<", ">", "<=", ">=")

# Instrucciones que un alumno podría escribir con otra capitalización, con tilde
# o con el nombre de otro lenguaje, y la forma correcta.
SUGERENCIAS_SENTENCIA = {
    "si": "Si", "sino": "Sino", "fin": "Fin", "mientras": "Mientras", "para": "Para",
    "mostrar": "Mostrar", "leer": "Leer", "retornar": "Retornar",
    "inicio": "Inicio", "escribir": "Mostrar", "imprimir": "Mostrar", "print": "Mostrar",
    "input": "Leer",
}
INSTRUCCIONES_CON_BLOQUE = {"Si", "Mientras", "Para", "Mostrar", "Leer"}
PALABRAS_RETORNO ={"return", "devolver", "retorna", "devuelve", "regresar"}
# Instrucciones que existen en otros pseudocódigos pero no en este, con la alternativa.
INSTRUCCIONES_DE_OTRAS_NOTACIONES = {
    "repetir": "para repetir se usan 'Mientras(...)' o 'Para (...)'",
    "hacer": "para repetir se usan 'Mientras(...)' o 'Para (...)'",
    "mientrasque": "se escribe 'Mientras(condición)'",
    "segun": "no hay 'Segun'/'Casos': encadená 'Si' y 'Sino Si'",
    "casos": "no hay 'Segun'/'Casos': encadená 'Si' y 'Sino Si'",
}
# Operadores que son palabras: se escriben con mayúscula como el resto de las reservadas.
OPERADORES_PALABRA = {"y": "Y", "o": "O", "mod": "Mod"}
# Un nombre de tipo mal escrito -> el nombre válido más parecido. Los sinónimos en
# minúscula ('int') se corrigen a su propia forma ('Int'), no al nombre en castellano.
SUGERENCIAS_TIPO = {
    "entero": "Entero", "int": "Int", "integer": "Int",
    "flotante": "Real", "float": "Float", "real": "Real", "double": "Float",
    "decimal": "Real",
    "string": "String", "cadena": "Cadena", "texto": "String", "str": "String",
    "booleano": "Logico", "bool": "Bool", "boolean": "Bool", "logico": "Logico",
    "caracter": "Caracter", "char": "Char",
}
TIPOS_TEXTO = ("Entero (o Int), Real (o Float), String (o Cadena), Logico (o Bool) "
               "o Caracter (o Char)")
FORMA_PARA = "Para (i = 0, i++, i < 10)"
MENSAJE_MAYUSCULAS = "las palabras reservadas distinguen mayúsculas y no llevan tilde"


def describir(tok):
    if tok.tipo == "NL":
        return "el fin de la línea"
    if tok.tipo == "EOF":
        return "el fin del archivo"
    if tok.tipo == "CADENA":
        return f'el texto "{tok.valor}"'
    if tok.tipo == "KW":
        return f"la palabra reservada '{tok.valor}'"
    return f"'{tok.valor}'"


class Parser:
    def __init__(self, tokens, diag):
        self.tokens = tokens
        self.i = 0
        self.diag = diag
        # Cierres de bloque que están "abiertos" (para recuperarse cuando falta uno).
        self.abiertos = []
        # En qué nivel de anidación quedó cada línea, para verificar la sangría después.
        self.sangria = Sangria()
        # Nombres de subprogramas, para no confundirlos con instrucciones mal escritas.
        self.nombres_subs = {
            b.valor for a, b in zip(tokens, tokens[1:])
            if a.tipo == "KW" and a.valor in ("Funcion", "Procedimiento") and b.tipo == "ID"
        }

    # ------------------------------------------------------------ utilidades

    @property
    def act(self):
        return self.tokens[self.i]

    def ver(self, k=1):
        return self.tokens[min(self.i + k, len(self.tokens) - 1)]

    def avanzar(self):
        tok = self.tokens[self.i]
        if tok.tipo != "EOF":
            self.i += 1
        return tok

    def es_kw(self, *valores):
        return self.act.tipo == "KW" and self.act.valor in valores

    def es_op(self, *valores):
        return self.act.tipo == "OP" and self.act.valor in valores

    def error(self, mensaje, tok=None):
        tok = tok or self.act
        return ErrorSintaxis(mensaje, tok.linea, tok.col)

    def error_esperado(self, que, sugerido=None):
        tok = self.act
        mensaje = f"se esperaba {que}, pero se encontró {describir(tok)}"
        if (sugerido and tok.tipo == "ID"
                and normalizar(tok.valor) == normalizar(sugerido)):
            mensaje += f" (¿quisiste escribir '{sugerido}'? {MENSAJE_MAYUSCULAS})"
        return self.error(mensaje)

    def esperar_kw(self, valor, que=None):
        if self.es_kw(valor):
            return self.avanzar()
        raise self.error_esperado(que or f"'{valor}'", sugerido=valor)

    def esperar_op(self, valor, que=None):
        if self.es_op(valor):
            return self.avanzar()
        raise self.error_esperado(que or f"'{valor}'")

    def esperar_id(self, que):
        if self.act.tipo == "ID":
            return self.avanzar()
        raise self.error_esperado(que)

    def saltar_nl(self):
        while self.act.tipo == "NL":
            self.avanzar()

    def fin_linea(self):
        if self.act.tipo not in ("NL", "EOF"):
            raise self.error(f"sobra {describir(self.act)} al final de la línea")

    def fin_linea_tolerante(self):
        try:
            self.fin_linea()
        except ErrorSintaxis as e:
            self.diag.agregar(e)
            self.sincronizar()

    def sincronizar(self):
        """Descarta tokens hasta el final de la línea actual."""
        while self.act.tipo not in ("NL", "EOF"):
            self.avanzar()

    def marcar(self, tok, nivel):
        """Anota en qué nivel de anidación arranca la línea de este token.

        Lo usa indentacion.py: acá es el único lugar donde se sabe cuántos bloques hay
        abiertos, así que el nivel se registra al pasar y se verifica al final.
        """
        self.sangria.marcar(tok.linea, nivel)

    def cierre(self):
        """Si el token actual cierra un bloque, devuelve cuál ('Fin Si', 'Sino', ...)."""
        tok = self.act
        if tok.tipo != "KW":
            return None
        if tok.valor == "Fin":
            sig = self.ver()
            if sig.tipo == "KW" and sig.valor in ("Si", "Mientras", "Para"):
                return "Fin " + sig.valor
            return "Fin"
        if tok.valor == "Sino":
            return tok.valor
        return None

    # --------------------------------------------------------------- programa

    def parse(self):
        try:
            return self.parse_programa()
        except ErrorSintaxis as e:
            self.diag.agregar(e)
            return None

    def parse_programa(self):
        self.saltar_nl()
        inicio = self.esperar_kw("Programa", "'Programa <nombre>' en la primera línea")
        self.marcar(inicio, 0)
        nombre = self.esperar_id("el nombre del programa")
        self.fin_linea_tolerante()
        self.saltar_nl()

        variables = self.parse_bloque_var() if self.es_kw("Var") else []
        subprogramas = []
        while True:
            self.saltar_nl()
            if self.es_kw("Funcion", "Procedimiento"):
                subprogramas.append(self.parse_subprograma())
            elif self.es_kw("Var"):
                self.diag.error("la sección 'Var' del programa tiene que ir antes de las "
                                "funciones y procedimientos", self.act.linea, self.act.col)
                variables.extend(self.parse_bloque_var())
            elif self.act.tipo == "ID" and normalizar(self.act.valor) in ("funcion", "procedimiento"):
                correcto = "Funcion" if normalizar(self.act.valor) == "funcion" else "Procedimiento"
                raise self.error_esperado("'Funcion', 'Procedimiento' o 'Inicio'", correcto)
            elif self.act.tipo == "ID" and normalizar(self.act.valor) == "var":
                raise self.error(f"se escribe 'Var' con mayúscula, no '{self.act.valor}'")
            else:
                break

        ini = self.esperar_kw("Inicio", "'Inicio' del programa principal")
        self.marcar(ini, 0)
        self.fin_linea_tolerante()
        cuerpo = self.parse_bloque({"Fin"})
        self.saltar_nl()
        if self.cierre() == "Fin":
            self.avanzar()
            self.fin_linea_tolerante()
        else:
            self.diag.error(f"falta el 'Fin' del programa principal (que empieza en la "
                            f"línea {ini.linea})", self.act.linea, self.act.col)
        self.saltar_nl()
        if self.act.tipo != "EOF":
            self.diag.error("hay instrucciones después del 'Fin' del programa principal",
                            self.act.linea, self.act.col)
        return N.Programa(inicio.linea, inicio.col, nombre.valor, variables, subprogramas, cuerpo)

    def parse_bloque_var(self):
        self.marcar(self.avanzar(), 0)  # Var
        self.fin_linea_tolerante()
        declaraciones = []
        while True:
            self.saltar_nl()
            tok = self.act
            if tok.tipo in ("KW", "EOF"):
                break
            if tok.tipo == "ID" and normalizar(tok.valor) in ("inicio", "funcion", "procedimiento") \
                    and self.ver().tipo in ("NL", "EOF", "ID"):
                break
            try:
                if tok.tipo == "TIPO":
                    raise self.error("las declaraciones se escriben con los nombres primero y el "
                                     "tipo al final (ej: 'edad, altura Entero')")
                if tok.tipo != "ID":
                    raise self.error_esperado("una declaración de variables")
                self.marcar(tok, 1)      # las declaraciones van adentro del 'Var'
                declaraciones.extend(self.parse_declaracion())
            except ErrorSintaxis as e:
                self.diag.agregar(e)
                self.sincronizar()
        return declaraciones

    def parse_declaracion(self):
        nombres = [self.esperar_id("un nombre de variable")]
        while self.es_op(","):
            self.avanzar()
            nombres.append(self.esperar_id("un nombre de variable después de ','"))
        if self.act.tipo in ("NL", "EOF"):
            ultimo = nombres[-1].valor
            raise self.error(f"falta el tipo de dato de '{ultimo}' (ej: '{ultimo} Entero')")
        tipo = self.parse_tipo()
        self.fin_linea()
        return [N.DeclVar(t.linea, t.col, t.valor, tipo) for t in nombres]

    def parse_tipo(self):
        tok = self.act
        if tok.tipo == "TIPO":
            self.avanzar()
            return CANONICO.get(tok.valor, tok.valor)
        if tok.tipo == "ID" and normalizar(tok.valor) in SUGERENCIAS_TIPO:
            raise self.error(f"tipo de dato desconocido '{tok.valor}'; ¿quisiste decir "
                             f"'{SUGERENCIAS_TIPO[normalizar(tok.valor)]}'?")
        if tok.tipo == "ID":
            raise self.error(f"tipo de dato desconocido '{tok.valor}'; los tipos válidos son "
                             f"{TIPOS_TEXTO}")
        raise self.error_esperado(f"un tipo de dato ({TIPOS_TEXTO})")

    def parse_subprograma(self):
        inicio = self.avanzar()
        self.marcar(inicio, 0)
        es_funcion = inicio.valor == "Funcion"
        articulo = "la función" if es_funcion else "el procedimiento"
        nombre = self.esperar_id(f"el nombre de {articulo}")
        self.esperar_op("(", f"'(' después del nombre de {articulo} (aunque no tenga parámetros)")

        parametros = []
        if not self.es_op(")"):
            while True:
                ref = False
                if self.es_kw("Ref"):
                    self.avanzar()
                    ref = True
                elif (self.act.tipo == "ID" and normalizar(self.act.valor) == "ref"
                      and self.ver().tipo == "ID"):
                    # Sigue habiendo un nombre después, así que quiso escribir la palabra
                    # clave. Un parámetro que se llame 'ref' a secas es válido.
                    raise self.error(f"se escribe 'Ref' con mayúscula, no '{self.act.valor}'")
                p = self.esperar_id("el nombre del parámetro")
                if self.es_op(","):
                    raise self.error("cada parámetro necesita su propio tipo "
                                     "(ej: '(a Entero, b Entero)')")
                tipo = self.parse_tipo()
                parametros.append(N.Parametro(p.linea, p.col, p.valor, tipo, ref))
                if not self.es_op(","):
                    break
                self.avanzar()
        self.esperar_op(")", "')' o ',' en la lista de parámetros")

        tipo_retorno = None
        if es_funcion:
            if self.act.tipo in ("NL", "EOF"):
                raise self.error(f"falta el tipo de dato que devuelve la función "
                                 f"'{nombre.valor}' (va después del ')')")
            tipo_retorno = self.parse_tipo()
        elif self.act.tipo == "TIPO":
            raise self.error("un Procedimiento no devuelve ningún valor; si tiene que devolver "
                             f"un {self.act.valor}, usá 'Funcion'")
        self.fin_linea()
        self.saltar_nl()

        variables = self.parse_bloque_var() if self.es_kw("Var") else []
        self.saltar_nl()
        self.marcar(self.esperar_kw("Inicio", f"'Inicio' de {articulo} '{nombre.valor}'"), 0)
        self.fin_linea_tolerante()
        cuerpo = self.parse_bloque({"Fin"})
        if self.cierre() == "Fin":
            self.avanzar()
            self.fin_linea_tolerante()
        else:
            self.diag.error(f"falta el 'Fin' de {articulo} '{nombre.valor}' "
                            f"(línea {inicio.linea})", self.act.linea, self.act.col)
        return N.Subprograma(inicio.linea, inicio.col, nombre.valor, es_funcion, parametros,
                             tipo_retorno, variables, cuerpo)

    # ------------------------------------------------------------- sentencias

    def parse_bloque(self, permitidos):
        self.abiertos.append(permitidos)
        try:
            return self.parse_sentencias(permitidos)
        finally:
            self.abiertos.pop()

    def parse_sentencias(self, permitidos):
        sentencias = []
        while True:
            self.saltar_nl()
            tok = self.act
            if tok.tipo == "EOF":
                return sentencias
            if self.es_kw("Inicio", "Funcion", "Procedimiento", "Var", "Programa"):
                return sentencias
            cierre = self.cierre()
            if cierre is not None:
                if cierre in permitidos or any(cierre in a for a in self.abiertos):
                    # El cierre va un nivel más afuera que lo que encierra.
                    self.marcar(tok, len(self.abiertos) - 1)
                    return sentencias
                self.diag.error(self.mensaje_cierre_suelto(cierre), tok.linea, tok.col)
                self.sincronizar()
                continue
            try:
                self.marcar(tok, len(self.abiertos))
                sentencias.append(self.parse_sentencia())
            except ErrorSintaxis as e:
                self.diag.agregar(e)
                self.sincronizar()

    @staticmethod
    def mensaje_cierre_suelto(cierre):
        abridor = {"Fin Si": "Si", "Sino": "Si", "Fin Mientras": "Mientras",
                   "Fin Para": "Para"}[cierre]
        return f"'{cierre}' sin un '{abridor}' abierto"

    def parse_sentencia(self):
        tok = self.act
        if tok.tipo == "KW":
            metodo = {
                "Si": self.parse_si, "Mientras": self.parse_mientras, "Para": self.parse_para,
                "Mostrar": self.parse_mostrar,
                "Leer": self.parse_leer, "Retornar": self.parse_retornar,
            }.get(tok.valor)
            if metodo:
                return metodo()
            raise self.error(f"{describir(tok)} no puede ir al comienzo de una instrucción")

        if tok.tipo == "ID":
            sig = self.ver()
            clave = normalizar(tok.valor)
            if sig.tipo == "OP" and (sig.valor in ("=", "++", "--", "[")
                                     or sig.valor in COMPUESTOS):
                asignacion = self.parse_incremento()
                self.fin_linea()
                return asignacion
            if tok.valor not in self.nombres_subs:
                if clave in PALABRAS_RETORNO:
                    raise self.error(f"no existe '{tok.valor}': para devolver un valor se usa "
                                     "'Retornar' (ej: Retornar edad)")
                if clave in INSTRUCCIONES_DE_OTRAS_NOTACIONES:
                    raise self.error(f"no existe '{tok.valor}' en este pseudocódigo: "
                                     f"{INSTRUCCIONES_DE_OTRAS_NOTACIONES[clave]}")
                correcto = SUGERENCIAS_SENTENCIA.get(clave)
                if correcto and correcto != tok.valor:
                    mensaje = (f"'{tok.valor}' no es una instrucción válida; ¿quisiste escribir "
                               f"'{correcto}'? ({MENSAJE_MAYUSCULAS})")
                    if correcto not in INSTRUCCIONES_CON_BLOQUE:
                        raise self.error(mensaje)
                    # Se reporta y se sigue como si estuviera bien escrita, para no generar
                    # errores en cascada con el resto del bloque.
                    self.diag.error(mensaje, tok.linea, tok.col)
                    tok.tipo, tok.valor = "KW", correcto
                    return self.parse_sentencia()
            if sig.tipo == "OP" and sig.valor == "(":
                llamada = self.parse_llamada()
                self.fin_linea()
                return N.LlamadaProc(tok.linea, tok.col, llamada)
            if sig.tipo == "OP" and sig.valor == "==":
                raise self.error("para asignar se usa '=' (el '==' es para comparar)", sig)
            raise self.error(f"instrucción incompleta: después de '{tok.valor}' se esperaba "
                             "'=' (asignación) o '(' (llamada a un procedimiento)", sig)

        if tok.tipo == "TIPO":
            raise self.error("no se pueden declarar variables acá; declaralas en la sección "
                             "'Var' antes de 'Inicio'")
        raise self.error_esperado("una instrucción")

    def parse_cabecera(self, funcion):
        """Parsea la línea de apertura de un bloque; si falla, sigue con el cuerpo."""
        try:
            resultado = funcion()
            self.fin_linea()
            return resultado
        except ErrorSintaxis as e:
            self.diag.agregar(e)
            self.sincronizar()
            return None

    def parse_condicion(self, instruccion):
        if not self.es_op("("):
            raise self.error(f"la condición del '{instruccion}' va entre paréntesis: "
                             f"{instruccion}(condición)")
        return self.parse_expr()

    def cerrar(self, cierre, apertura, instruccion):
        if self.cierre() == cierre:
            self.avanzar()
            self.avanzar()
            self.fin_linea_tolerante()
        else:
            self.diag.error(f"falta '{cierre}' para cerrar el '{instruccion}' de la línea "
                            f"{apertura.linea}", self.act.linea, self.act.col)

    def parse_si(self):
        inicio = self.avanzar()
        condicion = self.parse_cabecera(lambda: self.parse_condicion("Si"))
        ramas = [(condicion, self.parse_bloque({"Fin Si", "Sino"}))]
        sino = None
        while self.cierre() == "Sino":
            tok_sino = self.avanzar()
            if self.es_kw("Si"):
                if sino is not None:
                    self.diag.error("no puede haber un 'Sino Si' después del 'Sino' final",
                                    tok_sino.linea, tok_sino.col)
                self.avanzar()
                condicion = self.parse_cabecera(lambda: self.parse_condicion("Sino Si"))
                ramas.append((condicion, self.parse_bloque({"Fin Si", "Sino"})))
            else:
                if sino is not None:
                    self.diag.error("un 'Si' solo puede tener un 'Sino' final",
                                    tok_sino.linea, tok_sino.col)
                self.fin_linea_tolerante()
                sino = self.parse_bloque({"Fin Si", "Sino"})
        self.cerrar("Fin Si", inicio, "Si")
        return N.Si(inicio.linea, inicio.col, ramas, sino)

    def parse_mientras(self):
        inicio = self.avanzar()
        condicion = self.parse_cabecera(lambda: self.parse_condicion("Mientras"))
        cuerpo = self.parse_bloque({"Fin Mientras"})
        self.cerrar("Fin Mientras", inicio, "Mientras")
        return N.Mientras(inicio.linea, inicio.col, condicion, cuerpo)

    def parse_para(self):
        inicio = self.avanzar()

        def cabecera():
            if not self.es_op("("):
                raise self.error(f"la cabecera del 'Para' va entre paréntesis: {FORMA_PARA}")
            self.avanzar()
            inicializacion = self.parse_asignacion_suelta("la inicialización")
            self.esperar_op(",", f"',' ({FORMA_PARA})")
            incremento = self.parse_asignacion_suelta("el incremento")
            self.esperar_op(",", f"',' ({FORMA_PARA})")
            condicion = self.parse_expr()
            self.esperar_op(")", f"')' ({FORMA_PARA})")
            return inicializacion, incremento, condicion

        partes = self.parse_cabecera(cabecera) or (None, None, None)
        cuerpo = self.parse_bloque({"Fin Para"})
        self.cerrar("Fin Para", inicio, "Para")
        return N.Para(inicio.linea, inicio.col, *partes, cuerpo)

    def parse_asignacion_suelta(self, que):
        """Una asignación de la cabecera del 'Para' (sin fin de línea)."""
        asignacion = self.parse_incremento()
        if asignacion is None:
            raise self.error(f"{que} del 'Para' se escribe como una asignación: {FORMA_PARA}")
        return asignacion

    def parse_incremento(self):
        """'i++', 'i--', 'total += x' o 'i = expr'. Devuelve None si no es una asignación."""
        tok = self.act
        sig = self.ver()
        if tok.tipo != "ID" or sig.tipo != "OP":
            return None

        # Destino con posición: 'mi_texto[3] = 'S''. Los corchetes se guardan aparte del
        # nombre para que el día que haya arreglos el destino ya esté representado.
        if sig.valor == "[":
            self.avanzar()
            indices = []
            while self.es_op("["):
                corchete = self.avanzar()
                indices.append(self.parse_expr())
                self.esperar_op("]", f"']' para cerrar el '[' de la columna {corchete.col}")
            if self.act.tipo == "OP" and (self.act.valor in ("++", "--")
                                          or self.act.valor in COMPUESTOS):
                raise self.error(f"'{self.act.valor}' no se puede usar sobre una posición; "
                                 f"escribilo con '=' (ej: {tok.valor}[1] = 'a')")
            self.esperar_op("=", "'=' para darle un valor a esa posición")
            return N.Asignacion(tok.linea, tok.col, tok.valor, self.parse_expr(), indices)

        variable = N.Variable(tok.linea, tok.col, tok.valor)

        if sig.valor in ("++", "--"):
            self.avanzar()
            self.avanzar()
            # i++ es lo mismo que i = i + 1
            uno = N.Literal(tok.linea, tok.col, 1, "Entero")
            op = "+" if sig.valor == "++" else "-"
            asignacion = N.Asignacion(tok.linea, tok.col, tok.valor,
                                      N.Binaria(sig.linea, sig.col, op, variable, uno))
            asignacion.operador_incremento = sig.valor
            return asignacion

        if sig.valor in COMPUESTOS:
            self.avanzar()
            self.avanzar()
            # total += x es lo mismo que total = total + x
            expr = N.Binaria(sig.linea, sig.col, COMPUESTOS[sig.valor], variable, self.parse_expr())
            expr.operador_compuesto = sig.valor   # para que los errores digan '+=' y no '+'
            return N.Asignacion(tok.linea, tok.col, tok.valor, expr)

        if sig.valor == "=":
            self.avanzar()
            self.avanzar()
            return N.Asignacion(tok.linea, tok.col, tok.valor, self.parse_expr())
        return None

    def parse_argumentos(self, instruccion):
        if not self.es_op("("):
            raise self.error(f"'{instruccion}' lleva paréntesis: {instruccion}(...)")
        self.avanzar()
        args = []
        if not self.es_op(")"):
            args.append(self.parse_expr())
            while self.es_op(","):
                self.avanzar()
                args.append(self.parse_expr())
        self.esperar_op(")", "')' o ','")
        return args

    def parse_mostrar(self):
        inicio = self.avanzar()
        args = self.parse_argumentos("Mostrar")
        self.fin_linea()
        return N.Mostrar(inicio.linea, inicio.col, args)

    def parse_retornar(self):
        inicio = self.avanzar()
        if self.act.tipo in ("NL", "EOF"):
            raise self.error("a 'Retornar' le falta el valor que devuelve la función "
                             "(ej: Retornar edad)")
        expr = self.parse_expr()
        self.fin_linea()
        return N.Retornar(inicio.linea, inicio.col, expr)

    def parse_leer(self):
        inicio = self.avanzar()
        args = self.parse_argumentos("Leer")
        if not args:
            raise self.error("Leer necesita al menos una variable: Leer(variable)", inicio)
        for a in args:
            if not isinstance(a, N.Variable):
                raise ErrorSintaxis("Leer(...) solo acepta nombres de variables; para mostrar un "
                                    "mensaje usá Mostrar(...) antes", a.linea, a.col)
        self.fin_linea()
        return N.Leer(inicio.linea, inicio.col, args)

    def parse_llamada(self):
        nombre = self.avanzar()
        args = self.parse_argumentos(nombre.valor)
        return N.Llamada(nombre.linea, nombre.col, nombre.valor, args)

    # ------------------------------------------------------------ expresiones

    def parse_expr(self):
        izq = self.parse_o()
        # Terminada la expresión, un nombre suelto donde iba un operador es casi seguro
        # un 'Y', 'O' o 'Mod' escrito en minúscula. Sin esto el error hablaría del
        # paréntesis que falta, que no es lo que el estudiante hizo mal.
        if self.act.tipo == "ID":
            correcto = OPERADORES_PALABRA.get(normalizar(self.act.valor))
            if correcto:
                raise self.error(f"se escribe '{correcto}' con mayúscula, "
                                 f"no '{self.act.valor}'")
        return izq

    def parse_o(self):
        izq = self.parse_y()
        while self.es_kw("O"):
            op = self.avanzar()
            izq = N.Binaria(op.linea, op.col, "O", izq, self.parse_y())
        return izq

    def parse_y(self):
        izq = self.parse_negacion()
        while self.es_kw("Y"):
            op = self.avanzar()
            izq = N.Binaria(op.linea, op.col, "Y", izq, self.parse_negacion())
        return izq

    def parse_negacion(self):
        if self.es_op("!"):
            op = self.avanzar()
            return N.Unaria(op.linea, op.col, "!", self.parse_negacion())
        # Quien escribe 'No' viene de otra notación: acá se niega con '!'. Se mira el
        # token siguiente para no pisar una variable que se llame 'no'.
        siguiente = self.ver()
        if (self.act.tipo == "ID" and normalizar(self.act.valor) == "no"
                and (siguiente.tipo in ("ID", "ENTERO", "FLOTANTE", "CADENA", "CARACTER", "KW")
                     or (siguiente.tipo == "OP" and siguiente.valor == "("))):
            raise self.error(f"para negar se usa '!', no '{self.act.valor}' "
                             "(ej: !(edad >= 18))")
        return self.parse_comparacion()

    def parse_comparacion(self):
        izq = self.parse_suma()
        if self.es_op(*COMPARADORES):
            op = self.avanzar()
            izq = N.Binaria(op.linea, op.col, op.valor, izq, self.parse_suma())
            if self.es_op(*COMPARADORES):
                raise self.error("no se pueden encadenar comparaciones como 'a < b < c'; "
                                 "escribí 'a < b Y b < c'")
        if self.es_op("="):
            raise self.error("para comparar se usa '==' (el '=' solo sirve para asignar)")
        return izq

    def parse_suma(self):
        izq = self.parse_mult()
        while self.es_op("+", "-"):
            op = self.avanzar()
            izq = N.Binaria(op.linea, op.col, op.valor, izq, self.parse_mult())
        return izq

    def parse_mult(self):
        izq = self.parse_unario()
        while True:
            # 'Mod' es otra forma de escribir '%': se traduce acá y el resto del
            # verificador no se entera de la diferencia.
            if self.es_kw("Mod"):
                op = self.avanzar()
                izq = N.Binaria(op.linea, op.col, "%", izq, self.parse_unario())
                continue
            if self.es_op("*", "/", "%"):
                op = self.avanzar()
                izq = N.Binaria(op.linea, op.col, op.valor, izq, self.parse_unario())
                continue
            # Donde se esperaba un operador, un nombre parecido a 'Mod' es casi seguro
            # un 'Mod' mal escrito; sin esto el error diría solo que 'sobra' algo.
            if self.act.tipo == "ID" and normalizar(self.act.valor) == "mod":
                raise self.error(f"se escribe 'Mod' con mayúscula, no '{self.act.valor}'")
            return izq

    def parse_unario(self):
        if self.es_op("-", "+"):
            op = self.avanzar()
            return N.Unaria(op.linea, op.col, op.valor, self.parse_unario())
        return self.parse_primario()

    def parse_primario(self):
        tok = self.act
        literales = {"ENTERO": "Entero", "FLOTANTE": "Real", "CADENA": "String",
                     "CARACTER": "Caracter"}
        if tok.tipo in literales:
            self.avanzar()
            return self.parse_indices(N.Literal(tok.linea, tok.col, tok.valor,
                                                literales[tok.tipo]))
        if self.es_kw("Verdadero", "Falso"):
            self.avanzar()
            return N.Literal(tok.linea, tok.col, tok.valor == "Verdadero", "Logico")
        if tok.tipo == "TIPO" and self.ver().tipo == "OP" and self.ver().valor == "(":
            return self.parse_indices(self.parse_conversion())
        if tok.tipo == "ID":
            if self.ver().tipo == "OP" and self.ver().valor == "(":
                return self.parse_indices(self.parse_llamada())
            self.avanzar()
            return self.parse_indices(N.Variable(tok.linea, tok.col, tok.valor))
        if self.es_op("("):
            self.avanzar()
            expr = self.parse_expr()
            self.esperar_op(")", f"')' para cerrar el '(' de la columna {tok.col}")
            return self.parse_indices(expr)
        raise self.error_esperado("un valor o una expresión")

    def parse_conversion(self):
        """Entero(x), Cadena(x)...: el nombre de un tipo usado como función."""
        tipo = self.avanzar()
        self.avanzar()      # (
        if self.es_op(")"):
            raise self.error(f"a '{tipo.valor}()' le falta el valor que hay que convertir "
                             f"(ej: {tipo.valor}(edad))")
        expr = self.parse_expr()
        if self.es_op(","):
            raise self.error(f"'{tipo.valor}(...)' convierte un solo valor")
        self.esperar_op(")", f"')' para cerrar '{tipo.valor}('")
        return N.Conversion(tipo.linea, tipo.col, CANONICO.get(tipo.valor, tipo.valor),
                            expr, tipo.valor)

    def parse_indices(self, base):
        """Los '[...]' que vengan pegados: base[i], y más adelante base[i][j].

        Se encadenan acá y no en cada lugar donde aparece un nombre, para que agregar
        arreglos no obligue a tocar el resto del parser.
        """
        while self.es_op("["):
            corchete = self.avanzar()
            indice = self.parse_expr()
            self.esperar_op("]", f"']' para cerrar el '[' de la columna {corchete.col}")
            base = N.Indice(corchete.linea, corchete.col, base, indice)
        return base
