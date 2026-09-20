"""Puente entre la página web y el verificador.

Corre adentro de Pyodide (Python compilado a WebAssembly). No agrega ni cambia nada
del lenguaje: solo traduce entre el paquete 'pseudo' y JavaScript, y como JavaScript
no entiende los objetos de Python, todo lo que se devuelve va como texto JSON.

Las funciones 'pedir_entrada' y 'emitir' que recibe 'ejecutar_fuente' vienen de
JavaScript. Se aprovecha que el intérprete ya recibe la entrada y la salida por
parámetro, así que no hay que tocarlo para que lea del teclado de la página.
"""
import json

from pseudo import ErrorEjecucion, Interprete, analizar
from pseudo.lexer import PALABRAS_RESERVADAS, TIPOS
from pseudo.predefinidas import PREDEFINIDAS


def _como_dict(d):
    return {"nivel": d.nivel, "mensaje": d.mensaje, "linea": d.linea, "col": d.col}


def vocabulario():
    """Las palabras del lenguaje, para que el editor las pinte sin tener una copia propia."""
    return json.dumps({
        "reservadas": sorted(PALABRAS_RESERVADAS),
        "tipos": sorted(TIPOS),
        "predefinidas": sorted(PREDEFINIDAS),
    })


def analizar_fuente(fuente):
    resultado = analizar(fuente)
    diag = resultado.diagnosticos
    return json.dumps({
        "ok": resultado.ok,
        "errores": len(diag.errores),
        "advertencias": len(diag.advertencias),
        "diagnosticos": [_como_dict(d) for d in diag.ordenados()],
    })


def ejecutar_fuente(fuente, pedir_entrada, emitir, max_pasos):
    """Verifica y, si no hay errores, ejecuta. Devuelve cómo terminó."""
    resultado = analizar(fuente)
    diag = resultado.diagnosticos
    informe = {
        "errores": len(diag.errores),
        "advertencias": len(diag.advertencias),
        "diagnosticos": [_como_dict(d) for d in diag.ordenados()],
    }

    if not resultado.ok:
        return json.dumps({**informe, "estado": "no_compila"})

    def entrada():
        # JavaScript avisa que no hay más datos (o que cortaron la ejecución) devolviendo
        # null. Se compara por tipo y no con 'is None' a propósito: según la versión,
        # Pyodide convierte el null de JavaScript en None o en un objeto JsNull.
        texto = pedir_entrada()
        if not isinstance(texto, str):
            raise EOFError
        return texto

    interprete = Interprete(resultado.programa, entrada=entrada, salida=emitir,
                            max_pasos=max_pasos)
    try:
        interprete.ejecutar()
    except ErrorEjecucion as e:
        return json.dumps({**informe, "estado": "error_ejecucion", "mensaje": e.mensaje,
                           "linea": e.linea, "col": e.col})
    return json.dumps({**informe, "estado": "ok", "pasos": interprete.pasos})
