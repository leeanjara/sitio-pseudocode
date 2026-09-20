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


def empaquetar(destino="sitio"):
    """Arma una carpeta lista para subir a cualquier hosting estático.

    Queda index.html en la raíz y pseudo/ adentro, así no depende de dónde se publique.
    """
    salida = (RAIZ / destino).resolve()
    if salida == RAIZ or RAIZ in salida.parents and salida.name == "":
        print("Elegí una carpeta de destino distinta de la raíz del proyecto.")
        return 1

    if salida.exists():
        shutil.rmtree(salida)
    shutil.copytree(RAIZ / "web", salida)
    shutil.copytree(RAIZ / "pseudo", salida / "pseudo",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    (salida / "pseudo" / MANIFIESTO).write_text(json.dumps(listar_modulos()), encoding="utf-8")
    (salida / "_headers").write_text(ENCABEZADOS, encoding="utf-8")
    # Sin esto, GitHub Pages pasa el sitio por Jekyll, que no publica los archivos que
    # empiezan con guion bajo: __init__.py y __main__.py darían 404 y la página no carga.
    (salida / ".nojekyll").write_text("", encoding="utf-8")

    print(f"Sitio armado en {salida}")
    print("Subí el contenido de esa carpeta a GitHub Pages, Netlify o Cloudflare Pages.")
    print("Acordate de volver a correrlo cada vez que cambies algo de pseudo/.")
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
