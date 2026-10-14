"use strict";

// El programa con el que arranca la página.
const EJEMPLO = `Programa saludo
Var
    nombre String
    veces, i Entero
Inicio
    Mostrar("¿Cómo te llamás?")
    Leer(nombre)
    Mostrar("¿Cuántas veces te saludo?")
    Leer(veces)

    Para (i = 1, i++, i <= veces)
        Mostrar("Hola ", nombre, "! (", i, " de ", veces, ")")
    Fin Para
Fin
`;

const MAX_PASOS = 5000000;
const ESPERA_ANALISIS = 400;   // ms sin tipear antes de revisar

const $ = (id) => document.getElementById(id);
const elEstado = $("estado");
const elConsola = $("consola");
const elDiagnosticos = $("diagnosticos");
const elResumen = $("resumen");
const btnEjecutar = $("btn-ejecutar");
const btnDetener = $("btn-detener");

// Sin memoria compartida no podemos frenar al worker en el Leer, así que la página
// cae sola al modo de datos precargados en vez de quedar inservible.
const INTERACTIVO = self.crossOriginIsolated && typeof SharedArrayBuffer !== "undefined";

let worker = null;
let editor = null;
let estado = "cargando";        // cargando | listo | ejecutando | esperando-entrada | roto
let marcas = [];
let contadorAnalisis = 0;
let temporizador = null;
let detenidoPorUsuario = false;
// Si ya usaba la página antes de esta visita. Se mira acá, al arrancar, antes de que el
// editor escriba nada en el navegador; las novedades solo se le muestran a quien venía.
const VENIA_DE_ANTES = (() => {
  try {
    return localStorage.getItem("pseudo:programa") !== null ||
           localStorage.getItem("pseudo:archivo") !== null;
  } catch (_) {
    return false;
  }
})();
let avisosDesplegados = (() => {
  try { return localStorage.getItem("pseudo:advertencias") === "1"; } catch (_) { return false; }
})();

let memoria = null, control = null, bytes = null;
if (INTERACTIVO) {
  memoria = new SharedArrayBuffer(8 + 8192);
  control = new Int32Array(memoria, 0, 2);
  bytes = new Uint8Array(memoria, 8);
}

// ------------------------------------------------------------------ editor

function definirModo(vocab) {
  const reservadas = new Set(vocab.reservadas);
  const tipos = new Set(vocab.tipos);
  const predefinidas = new Set(vocab.predefinidas);
  const LETRA = /[A-Za-z_À-ɏ]/;
  const PALABRA = /^[A-Za-z0-9_À-ɏ]+/;

  CodeMirror.defineMode("pseudo", () => ({
    token(stream) {
      if (stream.eatSpace()) return null;
      if (stream.match("//")) { stream.skipToEnd(); return "comment"; }

      const c = stream.peek();
      if (c === "\"" || c === "'") {
        stream.next();
        while (!stream.eol() && stream.next() !== c) { /* hasta la comilla de cierre */ }
        return "string";
      }
      if (c >= "0" && c <= "9") {
        stream.match(/^[0-9]+(\.[0-9]+)?/);
        return "number";
      }
      if (LETRA.test(c)) {
        stream.match(PALABRA);
        const palabra = stream.current();
        if (tipos.has(palabra)) return "type";
        if (reservadas.has(palabra)) return "keyword";
        if (predefinidas.has(palabra)) return "builtin";
        return "variable";
      }
      stream.next();
      return "operator";
    },
  }));
}

// Con qué está sangrado el programa que hay escrito: tabulaciones o espacios, y de a
// cuántos. La unidad se toma de la sangría más chica que aparezca.
function estiloDeSangria(cm) {
  let tabs = 0, espacios = 0, minimo = 0;
  cm.eachLine((linea) => {
    const blancos = (linea.text.match(/^[ \t]+/) || [""])[0];
    if (!blancos) return;
    if (blancos[0] === "\t") { tabs++; return; }
    espacios++;
    if (!minimo || blancos.length < minimo) minimo = blancos.length;
  });
  const conTabs = tabs > espacios;
  // 'unidad' va en columnas, no en caracteres, porque así mide CodeMirror al sangrar y
  // des-sangrar. Una tabulación ocupa tabSize columnas: decir 1 haría que al des-sangrar
  // quedara un resto en espacios, o sea una mezcla.
  return { conTabs, unidad: conTabs ? cm.getOption("tabSize") : (minimo || 4) };
}

function aplicarEstilo(cm) {
  // La tecla Tab sigue al documento, no al revés: el verificador acepta tabulaciones o
  // cualquier cantidad de espacios, pero uno solo por archivo. Si el editor impusiera
  // su estilo, fabricaría justo los archivos mezclados que después marca como error.
  const estilo = estiloDeSangria(cm);
  cm.setOption("indentWithTabs", estilo.conTabs);
  cm.setOption("indentUnit", estilo.unidad);
  return estilo;
}

function sangrar(cm) {
  const { conTabs, unidad } = aplicarEstilo(cm);
  if (cm.somethingSelected()) return cm.indentSelection("add");
  if (conTabs) return cm.replaceSelection("\t");
  // Completa hasta la próxima parada, para que no se desalinee al tabular a mitad de línea.
  const columna = cm.getCursor().ch;
  cm.replaceSelection(" ".repeat(unidad - (columna % unidad)));
}

function desangrar(cm) {
  aplicarEstilo(cm);
  cm.indentSelection("subtract");
}

// Si Tab pone un nivel entero, Backspace tiene que sacar un nivel entero: borrar cuatro
// veces para deshacer un Tab es la clase de fricción que hace que el editor estorbe.
function borrarSangria(cm) {
  if (cm.somethingSelected()) return CodeMirror.Pass;
  const cursor = cm.getCursor();
  const antes = cm.getLine(cursor.line).slice(0, cursor.ch);
  // Solo dentro de la sangría; en medio del texto, Backspace es el de siempre.
  if (!antes || antes.trim() !== "") return CodeMirror.Pass;
  const { conTabs, unidad } = estiloDeSangria(cm);
  if (conTabs) return CodeMirror.Pass;     // una tabulación ya es un solo caracter
  const borrar = ((cursor.ch - 1) % unidad) + 1;
  cm.replaceRange("", { line: cursor.line, ch: cursor.ch - borrar }, cursor);
}

function crearEditor() {
  editor = CodeMirror($("editor"), {
    value: localStorage.getItem("pseudo:programa") || EJEMPLO,
    lineNumbers: true,
    indentUnit: 4,
    indentWithTabs: false,
    gutters: ["CodeMirror-linenumbers", "marcas"],
    // Ctrl+Enter (ejecutar) lo atiende el documento, para que ande con el foco en
    // cualquier parte de la página y no solo dentro del editor.
    extraKeys: {
      Tab: sangrar,
      "Shift-Tab": desangrar,
      Backspace: borrarSangria,
    },
  });
  editor.on("change", () => {
    localStorage.setItem("pseudo:programa", editor.getValue());
    clearTimeout(temporizador);
    temporizador = setTimeout(analizar, ESPERA_ANALISIS);
    actualizarTitulo();
  });
  // Un archivo soltado sobre el editor lo maneja el documento (ver más abajo), que lo abre
  // en vez de pegar su texto en el medio del programa, que es lo que haría CodeMirror.
  editor.on("drop", (cm, e) => {
    if (hayArchivos(e)) e.codemirrorIgnore = true;
  });
  restaurarArchivo();
  actualizarTitulo();
}

// ------------------------------------------------------------ diagnósticos

function limpiarMarcas() {
  marcas.forEach((m) => m.clear());
  marcas = [];
  editor.clearGutter("marcas");
}

function subrayar(d) {
  const linea = d.linea - 1;
  if (linea < 0 || linea >= editor.lineCount()) return;
  const texto = editor.getLine(linea);
  const desde = Math.max(0, Math.min(d.col - 1, texto.length));
  // Se subraya la palabra entera, no un solo caracter: se ve mucho mejor.
  const resto = texto.slice(desde);
  const palabra = resto.match(/^[A-Za-z0-9_À-ɏ]+|^\S/);
  const hasta = desde + (palabra ? palabra[0].length : 1);
  marcas.push(editor.markText({ line: linea, ch: desde }, { line: linea, ch: hasta },
                              { className: `subrayado-${d.nivel}` }));

  const punto = document.createElement("span");
  punto.className = `marca marca-${d.nivel}`;
  punto.title = d.mensaje;
  editor.setGutterMarker(linea, "marcas", punto);
}

function irA(d) {
  const linea = Math.max(0, d.linea - 1);
  editor.setCursor({ line: linea, ch: Math.max(0, d.col - 1) });
  editor.scrollIntoView({ line: linea, ch: 0 }, 120);
  editor.focus();
}

const ICONO_LIBRO = '<svg class="icono" viewBox="0 0 24 24" aria-hidden="true"><path ' +
  'd="M2 4h6a4 4 0 0 1 4 4v13a3 3 0 0 0-3-3H2zM22 4h-6a4 4 0 0 0-4 4v13a3 3 0 0 1 3-3h7z"/></svg>';

// Un botón que abre la Referencia en el tema que explica un error. Solo si el error dice
// cuál es y la referencia está cargada: sin ella no hay adónde ir.
function botonReferencia(tema) {
  const titulo = tema && window.Ayuda && window.Ayuda.titulo(tema);
  if (!titulo) return null;
  const boton = document.createElement("button");
  boton.type = "button";
  boton.title = `Ver «${titulo}» en la Referencia`;
  boton.addEventListener("click", () => window.Ayuda.abrir(tema));
  return boton;
}

function crearFila(d) {
  const fila = document.createElement("button");
  fila.className = `diagnostico ${d.nivel}`;
  const donde = document.createElement("span");
  donde.className = "donde";
  donde.textContent = `${d.linea}:${d.col}`;
  const texto = document.createElement("span");
  texto.className = "texto";
  texto.textContent = d.mensaje;
  fila.append(donde, texto);
  fila.addEventListener("click", () => irA(d));

  // El botón de la Referencia va al lado y no adentro: un botón no puede ir dentro de otro.
  const ayuda = botonReferencia(d.tema);
  if (!ayuda) return fila;
  ayuda.className = "diagnostico-ayuda";
  ayuda.setAttribute("aria-label", ayuda.title);
  ayuda.innerHTML = ICONO_LIBRO;
  const contenedor = document.createElement("div");
  contenedor.className = "fila-diagnostico";
  contenedor.append(fila, ayuda);
  return contenedor;
}

function mostrarDiagnosticos(informe) {
  limpiarMarcas();
  elDiagnosticos.innerHTML = "";
  const lista = informe.diagnosticos || [];
  elDiagnosticos.hidden = lista.length === 0;

  // Las marcas en el código se ponen siempre, para errores y advertencias por igual:
  // ahí no estorban, porque están al lado de la línea de la que hablan.
  for (const d of lista) subrayar(d);

  // Las advertencias hablan del programa terminado ("esta variable no se usa"), así que
  // mientras se escribe son casi todas falsas alarmas: se pliegan detrás de una línea.
  // Va primera y pegada al borde de arriba, para que no haya que bajar entre los errores
  // para encontrarla.
  const avisos = lista.filter((d) => d.nivel === "advertencia");
  if (avisos.length) {
    const cuantas = `${avisos.length} ${avisos.length === 1 ? "advertencia" : "advertencias"}`;
    const control = document.createElement("button");
    control.className = "diagnostico plegado";
    control.textContent = `${cuantas}. ${avisosDesplegados ? "Ocultar" : "Mostrar"}`;
    control.addEventListener("click", () => {
      avisosDesplegados = !avisosDesplegados;
      try {
        localStorage.setItem("pseudo:advertencias", avisosDesplegados ? "1" : "0");
      } catch (_) { /* sin memoria, vale para esta sesión igual */ }
      mostrarDiagnosticos(informe);
    });
    elDiagnosticos.appendChild(control);
  }

  for (const d of lista) {
    if (d.nivel === "error" || avisosDesplegados) elDiagnosticos.appendChild(crearFila(d));
  }

  const errores = informe.errores || 0;
  const advertencias = informe.advertencias || 0;
  const partes = [];
  if (errores) partes.push(`${errores} ${errores === 1 ? "error" : "errores"}`);
  if (advertencias) {
    partes.push(`${advertencias} ${advertencias === 1 ? "advertencia" : "advertencias"}`);
  }
  elResumen.textContent = partes.length ? partes.join(" · ") : "sin errores ✓";
  elResumen.className = "resumen " + (errores ? "mal" : advertencias ? "aviso" : "bien");
}

function analizar() {
  if (!worker || estado === "cargando" || estado === "roto") return;
  if (estado === "ejecutando" || estado === "esperando-entrada") return;  // el worker está ocupado
  worker.postMessage({ tipo: "analizar", id: ++contadorAnalisis, fuente: editor.getValue() });
}

// ----------------------------------------------------------------- consola

function limpiarConsola() {
  elConsola.innerHTML = "";
}

function escribir(texto, clase = "") {
  const vacio = elConsola.querySelector(".vacio");
  if (vacio) vacio.remove();
  const linea = document.createElement("div");
  linea.className = `linea ${clase}`;
  linea.textContent = texto;
  elConsola.appendChild(linea);
  elConsola.scrollTop = elConsola.scrollHeight;
  return linea;
}

function pedirEntradaAlUsuario() {
  estado = "esperando-entrada";
  ponerEstado("Esperando que escribas un dato…", "espera");

  const vacio = elConsola.querySelector(".vacio");
  if (vacio) vacio.remove();

  // Es un <form> de un solo campo a propósito: así el Enter lo maneja el navegador
  // (anda también con teclado de celular, donde la tecla dice "Ir").
  const fila = document.createElement("form");
  fila.className = "linea entrada";
  const flecha = document.createElement("span");
  flecha.className = "flecha";
  flecha.textContent = "›";
  const campo = document.createElement("input");
  campo.type = "text";
  campo.spellcheck = false;
  campo.autocomplete = "off";
  campo.setAttribute("aria-label", "Dato para el programa");
  // Botón invisible: con un botón de envío presente, que Enter mande el formulario
  // deja de depender del navegador y pasa a estar garantizado.
  const enviar = document.createElement("button");
  enviar.type = "submit";
  enviar.className = "oculto";
  enviar.textContent = "Enviar";
  fila.append(flecha, campo, enviar);
  elConsola.appendChild(fila);
  elConsola.scrollTop = elConsola.scrollHeight;
  campo.focus();

  let respondido = false;
  fila.addEventListener("submit", (e) => {
    e.preventDefault();
    if (respondido) return;        // por las dudas: un solo dato por Leer
    respondido = true;
    const texto = campo.value;
    const eco = document.createElement("div");
    eco.className = "linea eco";
    eco.textContent = "› " + texto;
    fila.replaceWith(eco);
    responder(texto);
  });
}

function responder(texto) {
  const datos = new TextEncoder().encode(texto);
  const largo = Math.min(datos.length, bytes.length);
  bytes.set(datos.subarray(0, largo));
  Atomics.store(control, 1, largo);
  Atomics.store(control, 0, 1);
  Atomics.notify(control, 0);
  estado = "ejecutando";
  ponerEstado("Ejecutando…", "trabajando");
}

// -------------------------------------------------------------- ejecución

function ponerEstado(texto, clase = "") {
  elEstado.textContent = texto;
  elEstado.className = `estado ${clase}`;
}

function ejecutar() {
  if (estado !== "listo") return;
  limpiarConsola();
  detenidoPorUsuario = false;
  estado = "ejecutando";
  ponerEstado("Ejecutando…", "trabajando");
  btnEjecutar.hidden = true;
  btnDetener.hidden = false;

  worker.postMessage({
    tipo: "ejecutar",
    fuente: editor.getValue(),
    maxPasos: MAX_PASOS,
    memoria,
    precargada: INTERACTIVO ? "" : $("datos").value,
  });
}

function detener() {
  detenidoPorUsuario = true;
  if (estado === "esperando-entrada") {
    // Está frenado esperando un dato: lo soltamos avisándole que no hay más.
    const fila = elConsola.querySelector(".entrada");
    if (fila) fila.remove();
    Atomics.store(control, 0, 2);
    Atomics.notify(control, 0);
    return;
  }
  // Está calculando y no nos escucha: no queda otra que cortarlo y volver a levantarlo.
  worker.terminate();
  escribir("⏹ Ejecución interrumpida.", "aviso");
  terminarEjecucion();
  estado = "cargando";
  ponerEstado("Reiniciando…", "trabajando");
  btnEjecutar.disabled = true;
  arrancarWorker();
}

function terminarEjecucion() {
  estado = "listo";
  btnEjecutar.hidden = false;
  btnDetener.hidden = true;
}

function informarFin(informe) {
  mostrarDiagnosticos(informe);
  terminarEjecucion();

  if (detenidoPorUsuario && informe.estado === "error_ejecucion") {
    escribir("⏹ Ejecución interrumpida.", "aviso");
    ponerEstado("Interrumpido", "");
    return;
  }

  switch (informe.estado) {
    case "ok":
      escribir("✓ El programa terminó.", "fin");
      ponerEstado("Listo", "bien");
      break;
    case "no_compila":
      escribir("No se ejecutó: hay errores que corregir. Mirá la lista debajo del programa.",
               "error");
      ponerEstado("Hay errores", "mal");
      break;
    case "error_ejecucion": {
      const linea = escribir(`✗ Error en la línea ${informe.linea}: ${informe.mensaje}`,
                             "error");
      const ayuda = botonReferencia(informe.tema);
      if (ayuda) {
        ayuda.className = "consola-ayuda";
        ayuda.textContent = "Ver en la Referencia";
        linea.append(" ", ayuda);
      }
      ponerEstado("Error de ejecución", "mal");
      break;
    }
    default:
      escribir("✗ " + (informe.mensaje || "Algo falló."), "error");
      ponerEstado("Error", "mal");
  }
}

// ------------------------------------------------------------------ worker

function arrancarWorker() {
  worker = new Worker("worker.js");
  worker.onmessage = ({ data }) => {
    switch (data.tipo) {
      case "progreso":
        ponerEstado(data.texto, "trabajando");
        break;
      case "listo":
        definirModo(data.vocabulario);
        editor.setOption("mode", "pseudo");
        // La referencia pinta sus ejemplos con este mismo modo.
        if (window.Ayuda) window.Ayuda.modoListo();
        estado = "listo";
        btnEjecutar.disabled = false;
        ponerEstado(textoListo(), "bien");
        analizar();
        break;
      case "diagnosticos":
        if (data.id === contadorAnalisis) mostrarDiagnosticos(data.informe);
        break;
      case "salida":
        escribir(data.texto, data.clase || "");
        break;
      case "pide-entrada":
        pedirEntradaAlUsuario();
        break;
      case "fin":
        informarFin(data.informe);
        break;
      case "falla":
        estado = "roto";
        ponerEstado("No se pudo cargar", "mal");
        escribir("✗ " + data.mensaje, "error");
        break;
    }
  };
}

// --------------------------------------------------------- abrir y guardar

const TIPOS_DE_ARCHIVO = [{
  description: "Programa de pseudocódigo",
  accept: { "text/plain": [".txt", ".pseudo"] },
}];
const TAMANIO_MAXIMO = 1000000;     // un programa de verdad no llega ni cerca

// Chrome y Edge dejan escribir sobre un archivo, así que Guardar puede pisar el mismo una
// y otra vez. En los demás (Firefox, Safari, navegadores embebidos) lo único posible es
// descargar, y el navegador nunca pisa lo que ya está en Descargas: cada guardado sería
// una copia nueva, archivo(1).txt, archivo(2).txt... Ahí el botón dice lo que hace,
// "Descargar", y Ctrl+S no descarga: el programa ya queda guardado en el navegador.
const PUEDE_SOBRESCRIBIR = typeof window.showSaveFilePicker === "function";

// El archivo con el que se está trabajando: { nombre, handle }. 'handle' existe cuando el
// navegador deja escribir sobre el archivo (Chrome, Edge); si no, guardar es descargar.
let archivo = null;
let generacionGuardada = -1;

function textoListo() {
  return INTERACTIVO ? "Listo" : "Listo (modo datos precargados)";
}

function avisar(texto, clase = "bien", duracion = 2500) {
  ponerEstado(texto, clase);
  setTimeout(() => {
    if (elEstado.textContent === texto && estado === "listo") ponerEstado(textoListo(), "bien");
  }, duracion);
}

function hayCambios() {
  return !editor.isClean(generacionGuardada);
}

// Antes de reemplazar el programa (Abrir, Nuevo): si hay algo sin guardar, pregunta.
function puedeDescartar(accion) {
  return !hayCambios() || window.confirm(
    `Tu programa tiene cambios que no guardaste en un archivo. ¿${accion} igual? Lo que ` +
    "no guardaste se pierde.");
}

// Con lo mínimo para arrancar. El nombre queda seleccionado para escribir encima.
const PLANTILLA_NUEVO = "Programa mi_programa\nVar\n\nInicio\n\nFin\n";

function nuevo() {
  if (estado === "ejecutando" || estado === "esperando-entrada") {
    avisar("Detené el programa que está corriendo antes de empezar uno nuevo", "mal");
    return;
  }
  if (!puedeDescartar("Empezar un programa nuevo")) return;
  editor.setValue(PLANTILLA_NUEVO);
  editor.clearHistory();
  // Sin archivo: el próximo Guardar vuelve a preguntar dónde, en vez de pisar el anterior.
  archivo = null;
  generacionGuardada = editor.changeGeneration();
  recordarArchivo();                // que el desvínculo sobreviva a una recarga
  limpiarConsola();
  actualizarTitulo();
  editor.setSelection({ line: 0, ch: 9 }, { line: 0, ch: 20 });   // "mi_programa"
  editor.focus();
}

function nombreDelPrograma() {
  const m = /^\s*Programa\s+(\S+)/m.exec(editor.getValue());
  return m ? m[1] : null;
}

function nombreSugerido() {
  // Sin los caracteres que Windows no acepta en un nombre de archivo.
  const nombre = (nombreDelPrograma() || "programa").replace(/[\\/:*?"<>|]/g, "_");
  return nombre + ".txt";
}

function actualizarTitulo() {
  const programa = nombreDelPrograma();
  // El punto de "sin guardar" solo tiene sentido si hay un archivo: sin archivo, el
  // programa igual queda guardado en el navegador.
  const sucio = archivo !== null && hayCambios();
  document.title = (sucio ? "• " : "") +
                   (programa ? programa + " — PseudoLab" : "PseudoLab");
  $("archivo").textContent = archivo ? archivo.nombre + (sucio ? " •" : "") : "";
  $("archivo").title = sucio ? "Hay cambios sin guardar en el archivo" : "";
}

function hayArchivos(e) {
  return !!e.dataTransfer && Array.from(e.dataTransfer.types || []).includes("Files");
}

async function leerTexto(file) {
  const bytes = await file.arrayBuffer();
  try {
    return new TextDecoder("utf-8", { fatal: true }).decode(bytes);
  } catch (_) {
    // Lo guardado con el Bloc de notas viejo no es UTF-8; el CLI hace lo mismo.
    return new TextDecoder("windows-1252").decode(bytes);
  }
}

async function cargarArchivo(file, handle = null) {
  if (file.size > TAMANIO_MAXIMO) {
    avisar(`"${file.name}" es demasiado grande para ser un programa`, "mal");
    return;
  }
  if (!puedeDescartar(`Abrir "${file.name}"`)) return;
  const texto = (await leerTexto(file)).replace(/\r\n?/g, "\n");
  editor.setValue(texto);
  editor.clearHistory();          // que deshacer no vuelva al programa anterior
  archivo = { nombre: file.name, handle };
  generacionGuardada = editor.changeGeneration();
  recordarArchivo();
  actualizarTitulo();
  editor.focus();
  avisar(`Abierto: ${file.name}`);
}

async function abrir() {
  if (!window.showOpenFilePicker) {
    $("selector-archivo").click();    // sigue en el evento "change" del selector
    return;
  }
  let handle;
  try {
    [handle] = await window.showOpenFilePicker({ types: TIPOS_DE_ARCHIVO, multiple: false });
  } catch (e) {
    if (e.name !== "AbortError") avisar(`No se pudo abrir: ${e.message}`, "mal");
    return;
  }
  await cargarArchivo(await handle.getFile(), handle);
}

function descargar(texto, nombre) {
  const url = URL.createObjectURL(new Blob([texto], { type: "text/plain;charset=utf-8" }));
  const enlace = document.createElement("a");
  enlace.href = url;
  enlace.download = nombre;
  document.body.appendChild(enlace);
  enlace.click();
  enlace.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// comoNuevo: pide dónde guardar aunque ya haya un archivo (Ctrl+Shift+S).
async function guardar(comoNuevo = false) {
  // Lo que se va a escribir, tomado antes de esperar al diálogo y al disco. Si se edita
  // mientras tanto, esa edición no está en el archivo y tiene que seguir marcada como
  // sin guardar: por eso no se mira el editor recién al terminar.
  const texto = editor.getValue();
  const generacion = editor.changeGeneration();
  const nombre = (!comoNuevo && archivo) ? archivo.nombre : nombreSugerido();
  try {
    let handle = (!comoNuevo && archivo) ? archivo.handle : null;
    // Un archivo abierto con Abrir viene con permiso solo para leerlo: la primera vez que
    // se guarda, el navegador pregunta. Si no se da, se pregunta dónde guardar.
    if (handle && !(await permisoParaEscribir(handle))) handle = null;
    if (!handle && window.showSaveFilePicker) {
      handle = await window.showSaveFilePicker({ suggestedName: nombre, types: TIPOS_DE_ARCHIVO });
    }
    if (handle) {
      // Escribe sobre el mismo archivo, como un editor de escritorio.
      const escritura = await handle.createWritable();
      await escritura.write(texto);
      await escritura.close();
      archivo = { nombre: handle.name, handle };
    } else {
      // Firefox y Safari no dejan escribir sobre un archivo: queda en Descargas.
      descargar(texto, nombre);
      archivo = { nombre, handle: null };
    }
  } catch (e) {
    if (e.name !== "AbortError") avisar(`No se pudo guardar: ${e.message}`, "mal");
    return;
  }
  generacionGuardada = generacion;
  recordarArchivo(texto);
  actualizarTitulo();
  avisar(archivo.handle ? `Guardado en ${archivo.nombre}` : `Descargado como ${archivo.nombre}`);
}

async function permisoParaEscribir(handle) {
  if (typeof handle.queryPermission !== "function") return true;
  const modo = { mode: "readwrite" };
  try {
    if ((await handle.queryPermission(modo)) === "granted") return true;
    return (await handle.requestPermission(modo)) === "granted";
  } catch (_) {
    return false;
  }
}

// ------------------------------------------------- recordar el archivo al recargar

// Sin esto, al recargar la página el programa vuelve (lo guarda el navegador), pero se
// pierde de qué archivo era y que estaba guardado, y Nuevo y Abrir preguntarían por nada.
// Se recuerda el nombre y el texto tal como quedó guardado.
//
// El archivo en sí NO se recuerda, a propósito: guardarlo en IndexedDB permitiría seguir
// escribiéndolo después de recargar, pero en Edge (probado en la versión 153) leerlo de
// vuelta cierra la pestaña. Como eso pasaría al cargar la página, PseudoLab quedaría
// inutilizable en Edge. El costo de no hacerlo es chico: después de recargar, el primer
// Guardar vuelve a abrir el diálogo, con el mismo nombre ya puesto.
const CLAVE_ARCHIVO = "pseudo:archivo";

// texto: lo que quedó en el archivo (por defecto, lo que hay en el editor).
function recordarArchivo(texto = editor.getValue()) {
  try {
    if (archivo) {
      localStorage.setItem(CLAVE_ARCHIVO, JSON.stringify({ nombre: archivo.nombre, texto }));
    } else {
      localStorage.removeItem(CLAVE_ARCHIVO);
    }
  } catch (_) { /* sin memoria del navegador, vale solo para esta sesión */ }
}

function archivoRecordado() {
  try {
    const dato = JSON.parse(localStorage.getItem(CLAVE_ARCHIVO));
    return dato && typeof dato.nombre === "string" && typeof dato.texto === "string" ? dato : null;
  } catch (_) {
    return null;
  }
}

// Al arrancar: ¿el programa que volvió del navegador estaba guardado en un archivo?
function restaurarArchivo() {
  const inicial = editor.getValue();
  const recordado = archivoRecordado();
  if (recordado) {
    // Sin el archivo en sí (ver arriba): Guardar lo pide de nuevo, con este nombre.
    archivo = { nombre: recordado.nombre, handle: null };
    // Si se cambió después de guardar, sigue vinculado al archivo pero con cambios.
    generacionGuardada = recordado.texto === inicial ? editor.changeGeneration() : -1;
  } else {
    // El ejemplo y el esqueleto de Nuevo se pueden volver a obtener: no hay nada que
    // perder. Cualquier otra cosa es un programa tuyo que no está en ningún archivo.
    generacionGuardada = (inicial === EJEMPLO || inicial === PLANTILLA_NUEVO)
      ? editor.changeGeneration() : -1;
  }
}

// ----------------------------------------------------------------- versión

// version.json lo escribe --empaquetar. En la versión local (python -m pseudo --web) no
// existe, y se dice eso.
function textoVersion(v) {
  if (!v || !v.commit) return "Versión local, sin publicar";
  const [anio, mes, dia] = String(v.fecha || "").split("-");
  let texto = `Versión ${v.commit}` + (dia ? ` del ${dia}/${mes}/${anio}` : "");
  if (v.rama && v.rama !== "main") texto += ` (rama ${v.rama})`;
  if (v.sin_commitear) texto += ", con cambios sin commitear";
  return texto;
}

fetch("version.json", { cache: "no-store" })
  .then((r) => (r.ok ? r.json() : null))
  .catch(() => null)
  .then((v) => {
    const texto = textoVersion(v);
    window.PseudoLab = { version: texto };
    $("logo").title = "PseudoLab · " + texto;
  });

// --------------------------------------------------------------- novedades

// Las novedades están en referencia.json, de la más nueva a la más vieja. Quien vuelve
// después de un cambio ve una vez un aviso con la más nueva; después ya no. Quien entra
// por primera vez no lo ve: para esa persona todo es nuevo, no hay nada que avisarle.
const CLAVE_NOVEDADES = "pseudo:novedades";

function anotarNovedadesVistas(id) {
  try { localStorage.setItem(CLAVE_NOVEDADES, id); } catch (_) { /* se vuelve a mostrar */ }
}

function mostrarNovedades(lista) {
  if (!lista.length) return;
  const ultima = lista[0];
  let vista = null;
  try { vista = localStorage.getItem(CLAVE_NOVEDADES); } catch (_) { return; }
  if (vista === ultima.id) return;
  if (!VENIA_DE_ANTES) {
    anotarNovedadesVistas(ultima.id);
    return;
  }
  // Cuántas no vio: las que están antes de la última que vio (o todas, si nunca vio una).
  const indiceVista = lista.findIndex((n) => n.id === vista);
  const sinVer = indiceVista === -1 ? lista.length : indiceVista;

  const aviso = document.createElement("aside");
  aviso.className = "novedad";
  aviso.setAttribute("role", "status");
  const cerrar = () => {
    anotarNovedadesVistas(ultima.id);
    aviso.remove();
  };

  const icono = document.createElement("img");
  icono.src = "icono.svg";
  icono.alt = "";
  icono.className = "novedad-icono";
  const cuerpo = document.createElement("div");
  const titulo = document.createElement("p");
  titulo.className = "novedad-titulo";
  titulo.textContent = ultima.titulo;
  const texto = document.createElement("p");
  texto.className = "novedad-texto";
  texto.textContent = ultima.texto;
  const acciones = document.createElement("div");
  acciones.className = "novedad-acciones";
  const entendido = document.createElement("button");
  entendido.textContent = "Entendido";
  entendido.addEventListener("click", cerrar);
  const todas = document.createElement("button");
  todas.className = "enlace";
  todas.textContent = sinVer > 1
    ? `Ver las ${sinVer} novedades` : "Ver todas las novedades";
  todas.addEventListener("click", () => {
    cerrar();
    window.Ayuda.abrir("novedades");
  });
  acciones.append(entendido, todas);
  cuerpo.append(titulo, texto, acciones);

  const x = document.createElement("button");
  x.className = "novedad-cerrar";
  x.setAttribute("aria-label", "Cerrar el aviso");
  x.textContent = "×";
  x.addEventListener("click", cerrar);

  aviso.append(icono, cuerpo, x);
  document.body.appendChild(aviso);
}

// ------------------------------------------------------------------ inicio

btnEjecutar.addEventListener("click", ejecutar);
btnDetener.addEventListener("click", detener);
$("btn-limpiar").addEventListener("click", limpiarConsola);
$("btn-ayuda").addEventListener("click", () => window.Ayuda.abrir());
$("btn-nuevo").addEventListener("click", nuevo);
$("btn-abrir").addEventListener("click", abrir);
$("btn-guardar").addEventListener("click", () => guardar());
// Los atajos van en los tooltips y se arman acá porque dependen del sistema (Ctrl o ⌘)
// y del navegador (en Firefox, Ctrl+S no descarga). Solo los que no chocan con atajos
// del propio navegador: por eso Nuevo no tiene (Ctrl+N abre una ventana).
const MOD = /Mac|iPhone|iPad/.test(navigator.platform) ? "⌘" : "Ctrl";

function conAtajo(boton, atajo) {
  boton.dataset.ayuda += "\n" + atajo;
}

conAtajo(btnEjecutar, `${MOD}+Enter`);
conAtajo($("btn-abrir"), `${MOD}+O`);
if (PUEDE_SOBRESCRIBIR) {
  conAtajo($("btn-guardar"), `${MOD}+S`);
} else {
  const boton = $("btn-guardar");
  boton.classList.add("descarga");            // cambia el ícono
  boton.querySelector(".etiqueta").textContent = "Descargar";
  boton.dataset.ayuda = "Descarga una copia del programa como archivo .txt";
  conAtajo(boton, `${MOD}+Shift+S`);
}
$("selector-archivo").addEventListener("change", (e) => {
  const file = e.target.files[0];
  e.target.value = "";                // para poder volver a elegir el mismo archivo
  if (file) cargarArchivo(file);
});

// Ctrl+S, Ctrl+Shift+S y Ctrl+O (Cmd en Mac), estés donde estés en la página. Va en el
// documento y no en el editor para que funcione también con el foco en la consola.
document.addEventListener("keydown", (e) => {
  if (!(e.ctrlKey || e.metaKey) || e.altKey) return;
  const tecla = e.key.toLowerCase();
  if (tecla === "s") {
    e.preventDefault();               // si no, el navegador ofrece guardar la página
    if (PUEDE_SOBRESCRIBIR || e.shiftKey) {
      guardar(e.shiftKey);
    } else {
      // Ctrl+Shift+S sí descarga: ahí la copia nueva es lo que se está pidiendo.
      avisar("Ya está guardado en este navegador. Para tenerlo en un archivo, usá " +
             "Descargar.", "bien", 5000);
    }
  } else if (tecla === "o") {
    e.preventDefault();
    abrir();
  } else if (e.key === "Enter") {
    e.preventDefault();
    ejecutar();                       // si ya hay algo corriendo, no hace nada
  }
});

// Soltar un archivo en cualquier parte de la página lo abre. Sin esto el navegador se
// iría de la página para mostrar el archivo, y se perdería lo que no estuviera guardado.
document.addEventListener("dragover", (e) => {
  if (hayArchivos(e)) e.preventDefault();
});
document.addEventListener("drop", (e) => {
  if (!hayArchivos(e)) return;
  e.preventDefault();
  if (e.dataTransfer.files[0]) cargarArchivo(e.dataTransfer.files[0]);
});

// Si el programa está esperando un dato, hacer clic en cualquier parte del resultado
// devuelve el cursor al campo: es lo que uno intenta cuando lo perdió.
elConsola.addEventListener("click", () => {
  const campo = elConsola.querySelector(".entrada input");
  if (campo && !String(window.getSelection())) campo.focus();
});

if (!INTERACTIVO) {
  $("precarga").hidden = false;
}

// El editor se crea sin colores y se le ponen cuando el worker manda el vocabulario;
// así se puede escribir desde el primer segundo, sin esperar la descarga de Python.
definirModo({ reservadas: [], tipos: [], predefinidas: [] });
crearEditor();
arrancarWorker();
window.Ayuda.cargar()
  .then((datos) => mostrarNovedades(datos.novedades || []))
  .catch(() => { /* sin referencia no hay novedades que mostrar */ });
