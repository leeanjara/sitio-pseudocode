// Acá adentro corre Python. Va en un worker y no en la página por una razón puntual:
// 'Leer' tiene que FRENAR el programa hasta que el estudiante escriba algo, y si eso
// pasara en el hilo de la página, se congelaría toda la pantalla (incluido el cuadro
// donde tiene que escribir). Desde un worker podemos bloquear sin que se note.

const PYODIDE = "https://cdn.jsdelivr.net/pyodide/v0.29.5/full/";

// La lista de módulos NO se escribe acá: la arma Python (servidor_web.listar_modulos) y
// llega en este archivo. Así, agregar un módulo nuevo a pseudo/ no deja la página rota.
const MANIFIESTO = "pseudo/modulos.json";

// Según cómo se publique el sitio, pseudo/ puede quedar adentro (sitio empaquetado)
// o al lado (el repositorio tal cual).
const BASES = ["./", "../"];

let pyodide = null;
let puente = null;
let control = null;   // Int32Array: [0] = estado, [1] = cuántos bytes tiene el dato
let bytes = null;     // el texto que escribe el estudiante, en UTF-8
let precargada = null; // modo alternativo: datos escritos de antemano

const decodificador = new TextDecoder();

function avisar(tipo, datos = {}) {
  self.postMessage({ tipo, ...datos });
}

// Devuelve [base, lista de módulos]: de paso que busca dónde quedó pseudo/, se trae
// la lista de archivos que hay que copiar.
async function buscarModulos() {
  for (const base of BASES) {
    try {
      const url = new URL(base + MANIFIESTO, self.location.href);
      const r = await fetch(url, { cache: "no-store" });
      if (!r.ok) continue;
      // Algunos hostings contestan 200 con una página de error en vez de 404, así que
      // no alcanza con mirar el código: tiene que ser una lista de verdad.
      const modulos = JSON.parse(await r.text());
      if (Array.isArray(modulos) && modulos.length) return [base, modulos];
    } catch (_) { /* probamos la siguiente */ }
  }
  throw new Error(
    "No se encontró pseudo/modulos.json. Levantá la página con 'python -m pseudo --web', " +
    "o publicá la carpeta que arma 'python -m pseudo --empaquetar'.");
}

async function cargar() {
  avisar("progreso", { texto: "Descargando Python…" });
  importScripts(PYODIDE + "pyodide.js");
  pyodide = await loadPyodide({ indexURL: PYODIDE });

  avisar("progreso", { texto: "Cargando el verificador…" });
  const [base, modulos] = await buscarModulos();
  const fuentes = await Promise.all(modulos.map(async (m) => {
    const url = new URL(`${base}pseudo/${m}.py`, self.location.href);
    const r = await fetch(url, { cache: "no-store" });
    if (!r.ok) throw new Error(`No se pudo leer pseudo/${m}.py (${r.status})`);
    return [m, await r.text()];
  }));

  pyodide.FS.mkdirTree("/inicio/pseudo");
  for (const [m, texto] of fuentes) {
    pyodide.FS.writeFile(`/inicio/pseudo/${m}.py`, texto);
  }
  const puenteFuente = await (await fetch(new URL("puente.py", self.location.href),
                                          { cache: "no-store" })).text();
  pyodide.FS.writeFile("/inicio/puente.py", puenteFuente);

  pyodide.runPython('import sys; sys.path.insert(0, "/inicio")');
  puente = pyodide.pyimport("puente");

  const version = pyodide.runPython("import sys; sys.version.split()[0]");
  avisar("listo", { vocabulario: JSON.parse(puente.vocabulario()), version });
}

// ---------------------------------------------------------------- entrada

// Frena este worker hasta que la página escriba el dato en la memoria compartida.
// Devuelve null si el estudiante cortó la ejecución: el intérprete lo toma como
// "no hay más datos" y avisa con su mensaje de siempre.
function pedirEntrada() {
  if (precargada !== null) {
    if (!precargada.length) return null;
    const dato = precargada.shift();
    // Se muestra el dato consumido, igual que hace el CLI cuando la entrada viene de un
    // archivo: sin eso no se entiende qué valor le tocó a cada Leer.
    avisar("salida", { texto: "› " + dato, clase: "eco" });
    return dato;
  }
  Atomics.store(control, 0, 0);
  avisar("pide-entrada");
  Atomics.wait(control, 0, 0);
  if (Atomics.load(control, 0) === 2) return null;
  const largo = Atomics.load(control, 1);
  // El copiado no es opcional: TextDecoder rechaza las vistas sobre memoria compartida.
  return decodificador.decode(new Uint8Array(bytes.subarray(0, largo)));
}

function emitir(texto) {
  avisar("salida", { texto });
}

// ---------------------------------------------------------------- mensajes

self.onmessage = async (evento) => {
  const msg = evento.data;

  if (msg.tipo === "analizar") {
    if (!puente) return;
    avisar("diagnosticos", { id: msg.id, informe: JSON.parse(puente.analizar_fuente(msg.fuente)) });
    return;
  }

  if (msg.tipo === "ejecutar") {
    if (msg.memoria) {
      control = new Int32Array(msg.memoria, 0, 2);
      bytes = new Uint8Array(msg.memoria, 8);
      precargada = null;
    } else {
      // Sin memoria compartida no se puede frenar el worker, así que los datos
      // vienen todos juntos desde el principio. Se descarta el salto de línea final
      // para que no cuente como un dato vacío de más.
      const crudo = msg.precargada.replace(/\r/g, "").replace(/\n+$/, "");
      precargada = crudo === "" ? [] : crudo.split("\n");
    }
    let informe;
    try {
      informe = JSON.parse(puente.ejecutar_fuente(msg.fuente, pedirEntrada, emitir, msg.maxPasos));
    } catch (e) {
      informe = { estado: "falla_interna", mensaje: String(e) };
    }
    avisar("fin", { informe });
  }
};

cargar().catch((e) => avisar("falla", { mensaje: String(e.message || e) }));
