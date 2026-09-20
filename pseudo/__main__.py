"""Uso: python -m pseudo archivo.pseudo [--ejecutar]   |   python -m pseudo --web"""
import argparse
import sys

from . import ErrorEjecucion, Interprete, analizar


def leer_fuente(ruta):
    with open(ruta, "rb") as f:
        datos = f.read()
    try:
        return datos.decode("utf-8-sig")
    except UnicodeDecodeError:
        return datos.decode("cp1252")   # archivos guardados con el Bloc de notas viejo


def plural(n, singular, plural_):
    return f"{n} {singular if n == 1 else plural_}"


def mostrar_diagnostico(ruta, d, lineas):
    print(f"{ruta}:{d.linea}:{d.col}: {d.nivel}: {d.mensaje}")
    if 0 < d.linea <= len(lineas):
        texto = lineas[d.linea - 1].rstrip("\r")
        margen = " " * len(str(d.linea))
        # Se conservan los tabs para que el '^' quede alineado.
        relleno = "".join(c if c == "\t" else " " for c in texto[:d.col - 1])
        print(f"  {d.linea} | {texto}")
        print(f"  {margen} | {relleno}^")


def entrada_con_eco():
    """Cuando la entrada viene de un archivo, se muestra lo leído para que la salida se entienda."""
    texto = input()
    if not sys.stdin.isatty():
        print(texto)
    return texto


def procesar(ruta, args):
    try:
        fuente = leer_fuente(ruta)
    except OSError as e:
        print(f"{ruta}: no se pudo abrir el archivo ({e.strerror})")
        return False

    resultado = analizar(fuente)
    diag = resultado.diagnosticos
    lineas = fuente.split("\n")
    for d in diag.ordenados():
        if d.nivel == "advertencia" and args.sin_advertencias:
            continue
        mostrar_diagnostico(ruta, d, lineas)

    errores, advertencias = len(diag.errores), len(diag.advertencias)
    if errores:
        print(f"{ruta}: {plural(errores, 'error', 'errores')}, "
              f"{plural(advertencias, 'advertencia', 'advertencias')}\n")
        return False
    if advertencias:
        print(f"{ruta}: sin errores, {plural(advertencias, 'advertencia', 'advertencias')}\n")
    else:
        print(f"{ruta}: sin errores ni advertencias ✓\n")

    if args.ejecutar:
        print("----- ejecución -----")
        interprete = Interprete(resultado.programa, entrada=entrada_con_eco,
                                max_pasos=args.max_pasos)
        try:
            interprete.ejecutar()
        except ErrorEjecucion as e:
            print(f"\n{ruta}:{e.linea}:{e.col}: error de ejecución: {e.mensaje}")
            return False
        except KeyboardInterrupt:
            print("\nejecución interrumpida")
            return False
        print("----- fin -----")
    return True


def main(argv=None):
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass

    ap = argparse.ArgumentParser(
        prog="python -m pseudo",
        description="Verifica (y opcionalmente ejecuta) programas escritos en el pseudocódigo "
                    "de la materia.")
    ap.add_argument("archivos", nargs="*", help="archivos a verificar")
    ap.add_argument("-e", "--ejecutar", action="store_true",
                    help="si no hay errores, ejecuta el programa")
    ap.add_argument("-q", "--sin-advertencias", action="store_true",
                    help="muestra solo los errores")
    ap.add_argument("--max-pasos", type=int, default=10_000_000,
                    help="corta la ejecución después de tantas instrucciones (bucles infinitos)")
    ap.add_argument("--web", action="store_true",
                    help="abre la página para escribir y ejecutar desde el navegador")
    ap.add_argument("--puerto", type=int, default=8000,
                    help="puerto del servidor de --web (por defecto 8000)")
    ap.add_argument("--empaquetar", nargs="?", const="sitio", metavar="CARPETA",
                    help="arma la carpeta lista para publicar la página (por defecto 'sitio')")
    args = ap.parse_args(argv)

    if args.web:
        from .servidor_web import servir
        return servir(args.puerto)
    if args.empaquetar:
        from .servidor_web import empaquetar
        return empaquetar(args.empaquetar)
    if not args.archivos:
        ap.error("indicá al menos un archivo, o usá --web para abrir la página")

    todo_ok = True
    for ruta in args.archivos:
        todo_ok = procesar(ruta, args) and todo_ok
    return 0 if todo_ok else 1


if __name__ == "__main__":
    sys.exit(main())
