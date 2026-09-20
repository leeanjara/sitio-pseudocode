"""Verificación de la sangría.

La sangría es obligatoria: no importa si se usan 2 espacios, 4 o una tabulación, pero
tiene que ser siempre lo mismo y parejo en todo el archivo.

El que decide en qué nivel va cada línea es el parser, porque es el único que sabe qué
bloques hay abiertos en cada momento; acá solo se compara ese nivel contra los blancos
que la línea tiene de verdad. Por eso esto corre recién cuando la sintaxis está bien: si
el parser tuvo que recuperarse de un error, los niveles no son confiables.

La unidad (2, 4, un tab…) no se fija de antemano: se deduce de lo que más se repite en el
archivo. Así el estudiante usa el estilo que quiera y lo que se marca son las líneas que
se salen de *su propio* estilo.
"""
from collections import Counter

# Cambiar a "advertencia" si se prefiere que la sangría no impida ejecutar el programa.
NIVEL = "error"

UNIDAD_POR_DEFECTO = 4


class Sangria:
    """Anota, mientras el parser trabaja, en qué nivel de anidación quedó cada línea."""

    def __init__(self):
        self.niveles = {}

    def marcar(self, linea, nivel):
        # Si en una línea hay varias cosas, vale la primera que se haya visto.
        self.niveles.setdefault(linea, nivel)


def _blancos(texto):
    return texto[:len(texto) - len(texto.lstrip(" \t"))]


def _nombre(caracter, cantidad):
    if caracter == "\t":
        return f"{cantidad} tabulación" if cantidad == 1 else f"{cantidad} tabulaciones"
    return f"{cantidad} espacio" if cantidad == 1 else f"{cantidad} espacios"


def _recolectar(fuente, sangria):
    """(número de línea, nivel, blancos del principio) de cada línea con código."""
    lineas = fuente.split("\n")
    marcas = []
    for numero, nivel in sorted(sangria.niveles.items()):
        if not 0 < numero <= len(lineas):
            continue
        texto = lineas[numero - 1].rstrip("\r")
        if texto.strip():
            marcas.append((numero, nivel, _blancos(texto)))
    return marcas


def _revisar_mezcla(marcas, reportar):
    """Avisa si se mezclan tabulaciones y espacios. Devuelve False si hubo mezcla.

    Con las dos cosas mezcladas no tiene sentido medir anchos, porque cuánto ocupa un
    tab depende de con qué se abra el archivo.
    """
    mezcladas = [m for m in marcas if " " in m[2] and "\t" in m[2]]
    for numero, _, _ in mezcladas:
        reportar("la sangría de esta línea mezcla tabulaciones y espacios; usá siempre "
                 "lo mismo en todo el archivo", numero, 1)
    if mezcladas:
        return False

    con_tab = [m for m in marcas if m[2].startswith("\t")]
    con_espacio = [m for m in marcas if m[2].startswith(" ")]
    if not (con_tab and con_espacio):
        return True

    # Se marcan las menos, que son las que se salen del estilo del archivo.
    minoria_es_tab = len(con_tab) <= len(con_espacio)
    minoria = con_tab if minoria_es_tab else con_espacio
    usa, resto = ("tabulaciones", "espacios") if minoria_es_tab else ("espacios", "tabulaciones")
    for numero, _, _ in minoria:
        reportar(f"esta línea usa {usa} para la sangría y el resto del archivo usa "
                 f"{resto}; hay que elegir uno solo", numero, 1)
    return False


def _unidad(marcas):
    """Cuántos espacios (o tabs) ocupa un nivel, según lo que más se repite."""
    votos = Counter()
    for _, nivel, blancos in marcas:
        if nivel >= 1 and blancos and len(blancos) % nivel == 0:
            votos[len(blancos) // nivel] += 1
    if not votos:
        return UNIDAD_POR_DEFECTO
    # Ante un empate gana la unidad más chica, que es la interpretación más probable.
    return min(votos, key=lambda u: (-votos[u], u))


def verificar(fuente, sangria, diag):
    reportar = diag.error if NIVEL == "error" else diag.advertencia
    marcas = _recolectar(fuente, sangria)
    if not marcas or not _revisar_mezcla(marcas, reportar):
        return

    caracter = "\t" if any(b.startswith("\t") for _, _, b in marcas) else " "
    unidad = _unidad(marcas)

    for numero, nivel, blancos in marcas:
        esperado = nivel * unidad
        if len(blancos) == esperado:
            continue
        if esperado == 0:
            mensaje = ("esta línea no va adentro de ningún bloque, así que tiene que "
                       f"empezar pegada al margen, pero tiene {_nombre(caracter, len(blancos))}")
        else:
            bloques = "1 bloque" if nivel == 1 else f"{nivel} bloques"
            mensaje = (f"la sangría no corresponde: esta línea está adentro de {bloques}, "
                       f"así que tendría que empezar con {_nombre(caracter, esperado)}, "
                       f"pero empieza con {len(blancos)}")
        reportar(mensaje, numero, len(blancos) + 1)
