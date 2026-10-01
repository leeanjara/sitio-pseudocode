"""Servidor local para probar la página web (python -m pseudo --web).

Sirve la raíz del proyecto, así la página encuentra tanto web/ como pseudo/, y manda
los encabezados COOP/COEP que hacen falta para que la consola interactiva funcione.
Al publicar en un hosting estático esos encabezados los pone web/coi.js.

Esto es solo para probar en tu máquina: los estudiantes entran a la página publicada
y no necesitan tener Python instalado.
"""
import http.server
import json
import shutil
import tempfile
import webbrowser
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

# Para hostings que sí dejan configurar encabezados (Netlify, Cloudflare Pages). Donde
# no se puede (GitHub Pages), los pone web/coi.js desde el navegador.
ENCABEZADOS = """/*
  Cross-Origin-Opener-Policy: same-origin
  Cross-Origin-Embedder-Policy: require-corp
  Cross-Origin-Resource-Policy: cross-origin
"""


MANIFIESTO = "modulos.json"


def listar_modulos():
    """Los módulos que la página tiene que copiar al Python del navegador.

    Se arma acá y no se escribe a mano en worker.js justamente para que agregar un
    archivo nuevo a pseudo/ no rompa la página sin que nadie se entere.
    """
    return sorted(p.stem for p in (RAIZ / "pseudo").glob("*.py"))


class Manejador(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(RAIZ), **kwargs)

    def do_GET(self):
        # Se arma al vuelo para que el servidor de desarrollo refleje al instante
        # cualquier archivo que agregues a pseudo/. La ruta se compara entera: si
        # respondiera a cualquiera terminada así, la página creería que pseudo/ está
        # en un lugar donde no está.
        if self.path.split("?")[0] == f"/pseudo/{MANIFIESTO}":
            cuerpo = json.dumps(listar_modulos()).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(cuerpo)))
            self.end_headers()
            self.wfile.write(cuerpo)
            return
        super().do_GET()

    def end_headers(self):
        self.send_header("Cross-Origin-Embedder-Policy", "require-corp")
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Resource-Policy", "cross-origin")
        # Sin caché: al editar pseudo/ o web/ alcanza con recargar.
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, formato, *args):
        pass    # no ensucia la consola con cada archivo pedido


# Lista de los archivos que armó la última corrida de --empaquetar. Con eso se puede
# borrar lo que ya no va sin tocar nada que no sea nuestro.
REGISTRO = ".pseudo-sitio.json"
CARPETA_POR_DEFECTO = RAIZ / "sitio"


def _armar(carpeta):
    """Arma el sitio completo en una carpeta vacía."""
    sin_cache = shutil.ignore_patterns("__pycache__", "*.pyc")
    shutil.copytree(RAIZ / "web", carpeta, dirs_exist_ok=True, ignore=sin_cache)
    shutil.copytree(RAIZ / "pseudo", carpeta / "pseudo", dirs_exist_ok=True, ignore=sin_cache)
    (carpeta / "pseudo" / MANIFIESTO).write_text(json.dumps(listar_modulos()), encoding="utf-8")
    (carpeta / "_headers").write_text(ENCABEZADOS, encoding="utf-8")
    # Sin esto, GitHub Pages pasa el sitio por Jekyll, que no publica los archivos que
    # empiezan con guion bajo: __init__.py y __main__.py darían 404 y la página no carga.
    (carpeta / ".nojekyll").write_text("", encoding="utf-8")


def _leer_registro(salida):
    """Lo que armamos la vez pasada en esta carpeta, o None si nunca escribimos acá."""
    registro = salida / REGISTRO
    if not registro.is_file():
        return None
    try:
        rutas = json.loads(registro.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    # Solo rutas que queden adentro de la carpeta: el registro nunca puede servir para
    # borrar algo de afuera, aunque alguien lo haya editado a mano.
    return {r for r in rutas if isinstance(r, str)
            and salida in (salida / r).resolve().parents}


def empaquetar(destino=None):
    """Arma la página lista para subir a cualquier hosting estático.

    Queda index.html en la raíz y pseudo/ adentro, así no depende de dónde se publique.
    Si la carpeta ya existe **no la borra**: reemplaza los archivos del sitio y solo
    elimina los que había generado una corrida anterior y ya no van. Así se puede apuntar
    directo a la carpeta de otro repositorio (el de GitHub Pages) sin tocar su .git ni
    nada que no sea del sitio.
    """
    salida = CARPETA_POR_DEFECTO if destino is None else Path(destino).expanduser().resolve()
    fuentes = (RAIZ / "pseudo", RAIZ / "web")
    if salida == RAIZ or any(salida == f or f in salida.parents for f in fuentes):
        print("La carpeta de destino no puede ser la raíz del proyecto ni estar dentro de "
              "pseudo/ o web/: el sitio se mezclaría con el código.")
        return 1
    if salida.exists() and not salida.is_dir():
        print(f"{salida} existe y no es una carpeta.")
        return 1

    anteriores = _leer_registro(salida) if salida.exists() else None
    ajena = anteriores is None and salida.exists() and any(salida.iterdir())

    with tempfile.TemporaryDirectory() as temporal:
        armado = Path(temporal)
        _armar(armado)
        nuevos = sorted(p.relative_to(armado).as_posix()
                        for p in armado.rglob("*") if p.is_file())

        salida.mkdir(parents=True, exist_ok=True)
        sobrantes = sorted((anteriores or set()) - set(nuevos))
        for rel in sobrantes:
            (salida / rel).unlink(missing_ok=True)
        # Las carpetas que quedaron vacías por lo que se borró, de la más honda a la más alta.
        carpetas = {(salida / rel).parent for rel in sobrantes}
        for carpeta in sorted(carpetas, key=lambda c: len(c.parts), reverse=True):
            while carpeta != salida and salida in carpeta.parents:
                try:
                    carpeta.rmdir()             # solo funciona si está vacía
                except OSError:
                    break
                carpeta = carpeta.parent

        for rel in nuevos:
            (salida / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(armado / rel, salida / rel)

    (salida / REGISTRO).write_text(json.dumps(nuevos, indent=1), encoding="utf-8")

    print(f"Sitio armado en {salida} ({len(nuevos)} archivos).")
    if len(sobrantes) == 1:
        print("Se borró 1 archivo de la vez anterior que ya no va.")
    elif sobrantes:
        print(f"Se borraron {len(sobrantes)} archivos de la vez anterior que ya no van.")
    if ajena:
        print("Esa carpeta ya tenía otras cosas: se reemplazaron los archivos del sitio y no se "
              "borró nada más. Si antes copiabas el sitio a mano, puede haber quedado algún "
              "archivo viejo; de ahora en adelante los que sobren se borran solos.")
    print("Acordate de volver a correrlo cada vez que cambies algo de pseudo/ o web/.")
    return 0


def servir(puerto=8000, abrir=True):
    direccion = f"http://localhost:{puerto}/web/"
    try:
        servidor = http.server.ThreadingHTTPServer(("127.0.0.1", puerto), Manejador)
    except OSError as e:
        print(f"No se pudo usar el puerto {puerto} ({e.strerror}). "
              f"Probá con otro: python -m pseudo --web --puerto {puerto + 1}")
        return 1

    with servidor:
        print(f"Página abierta en {direccion}")
        print("Ctrl+C para cortar.")
        if abrir:
            webbrowser.open(direccion)
        try:
            servidor.serve_forever()
        except KeyboardInterrupt:
            print("\nServidor cortado.")
    return 0
