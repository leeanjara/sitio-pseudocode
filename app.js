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
    extraKeys: {
      "Ctrl-Enter": ejecutar,
      "Cmd-Enter": ejecutar,
      Tab: sangrar,
      "Shift-Tab": desangrar,
      Backspace: borrarSangria,
    },
  });
  editor.on("change", () => {
    localStorage.setItem("pseudo:programa", editor.getValue());
    clearTimeout(temporizador);
    temporizador = setTimeout(analizar, ESPERA_ANALISIS);
  });
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

function mostrarDiagnosticos(informe) {
  limpiarMarcas();
  elDiagnosticos.innerHTML = "";
  const lista = informe.diagnosticos || [];
  elDiagnosticos.hidden = lista.length === 0;

  for (const d of lista) {
    subrayar(d);
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
    elDiagnosticos.appendChild(fila);
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
    case "error_ejecucion":
      escribir(`✗ Error en la línea ${informe.linea}: ${informe.mensaje}`, "error");
      ponerEstado("Error de ejecución", "mal");
      break;
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
        ponerEstado(INTERACTIVO ? "Listo" : "Listo (modo datos precargados)", "bien");
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

// ------------------------------------------------------------------ inicio

btnEjecutar.addEventListener("click", ejecutar);
btnDetener.addEventListener("click", detener);
$("btn-limpiar").addEventListener("click", limpiarConsola);
$("btn-ayuda").addEventListener("click", () => window.Ayuda.abrir());

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
