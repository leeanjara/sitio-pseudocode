"use strict";

// Panel de referencia del lenguaje. El contenido no está acá: vive en referencia.json,
// que además un test de Python verifica (que no falte ninguna palabra reservada, que
// todos los ejemplos compilen de verdad y que muestren lo que dice su "salida"). Acá
// solo se dibuja y se busca.
//
// Se ve una categoría por vez: la barra lateral elige cuál, y mientras hay algo escrito
// en el buscador el contenido muestra los resultados en su lugar.

(function () {
  const CLAVE = "pseudo:referencia";
  const MOD = /Mac|iPhone|iPad/.test(navigator.platform) ? "⌘" : "Ctrl";

  // Lo que se propone cuando una búsqueda no encuentra nada. Tienen que dar resultados.
  const SUGERENCIAS = ["resto de una división", "leer un número", "convertir a texto",
                       "repetir n veces", "largo de un texto"];

  // Palabras que no ayudan a buscar ("cómo leer un número" busca "leer número"). No
  // están "y", "o", "si", "no" ni "para": son palabras del lenguaje.
  const VACIAS = new Set(["de", "del", "la", "las", "el", "los", "un", "una", "unos", "unas",
                          "a", "al", "en", "con", "por", "se", "es", "que", "como", "mi",
                          "lo", "le", "hacer", "quiero", "necesito", "puedo", "cual"]);

  let datos = null;
  let panel = null;
  let ultimoFoco = null;
  let partes = null;          // las piezas del panel que se tocan después de armarlo
  let vista = null;           // la categoría que se está viendo, o "novedades"
  let elegido = null;         // el último tema al que se fue a propósito
  let indice = null;          // lo que recorre la búsqueda, armado una sola vez
  let palabrasClave = null;   // contra lo que se comparan los errores de tipeo
  let resultados = [];
  let marcado = -1;           // el resultado elegido con las flechas
  let enResultados = false;   // si el contenido muestra resultados o una categoría

  async function cargar() {
    if (datos) return datos;
    const url = new URL("referencia.json", document.baseURI);
    const r = await fetch(url, { cache: "no-store" });
    if (!r.ok) throw new Error(`no se pudo leer referencia.json (${r.status})`);
    datos = await r.json();
    return datos;
  }

  // ---------------------------------------------------------------- piezas sueltas

  function crear(etiqueta, clase, texto) {
    const nodo = document.createElement(etiqueta);
    if (clase) nodo.className = clase;
    if (texto !== undefined) nodo.textContent = texto;
    return nodo;
  }

  const TRAZOS = {
    libro: '<path d="M2 4h6a4 4 0 0 1 4 4v13a3 3 0 0 0-3-3H2zM22 4h-6a4 4 0 0 0-4 4v13a3 3 0 0 1 3-3h7z"/>',
    lupa: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
    cerrar: '<path d="M6 6l12 12M18 6 6 18"/>',
    copiar: '<rect x="9" y="9" width="12" height="12" rx="2"/>' +
            '<path d="M5 15H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v1"/>',
    listo: '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
    lamparita: '<path d="M9 18h6M10 21h4M12 3a6 6 0 0 0-3.6 10.8c.6.5 1 1.2 1.1 2V16h5' +
               'v-.2c.1-.8.5-1.5 1.1-2A6 6 0 0 0 12 3z"/>',
    volver: '<path d="M19 12H5M11 6l-6 6 6 6"/>',
  };

  function icono(nombre) {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("class", "icono");
    svg.innerHTML = TRAZOS[nombre];
    return svg;
  }

  function seccionPorId(id) {
    return datos.secciones.find((s) => s.id === id);
  }

  function temaPorId(id) {
    for (const seccion of datos.secciones) {
      const tema = seccion.temas.find((t) => t.id === id);
      if (tema) return { seccion, tema };
    }
    return null;
  }

  function menosMovimiento() {
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  }

  // Para lectores de pantalla: lo que cambió sin que se mueva el foco.
  function anunciar(texto) {
    partes.anuncio.textContent = "";
    requestAnimationFrame(() => { partes.anuncio.textContent = texto; });
  }

  // ------------------------------------------------------------------- un tema

  // Pinta un ejemplo con el mismo modo que usa el editor. Mientras Python carga, ese
  // modo ya existe pero está vacío (todavía no llegó el vocabulario del lexer), así que
  // el ejemplo sale sin colores; modoListo() lo vuelve a pintar cuando llegan.
  function pintar(codigo) {
    const pre = document.createElement("pre");
    pre.className = "ayuda-codigo CodeMirror";
    if (window.CodeMirror && CodeMirror.runMode && CodeMirror.modes.pseudo) {
      CodeMirror.runMode(codigo, "pseudo", pre);
    } else {
      pre.textContent = codigo;
    }
    return pre;
  }

  // Lo que muestra el ejemplo, como lo mostraría la consola: los datos que se escriben
  // para Leer van con "› " y en otro color.
  function crearSalida(texto) {
    const pre = crear("pre", "ayuda-salida");
    texto.split("\n").forEach((linea, i) => {
      if (i) pre.append("\n");
      pre.appendChild(crear("span", linea.startsWith("› ") ? "eco" : null, linea));
    });
    return pre;
  }

  function botonCopiar(texto, pre) {
    const boton = crear("button", "ayuda-copiar");
    boton.type = "button";
    boton.dataset.ayuda = "Copiar el ejemplo";
    boton.dataset.ayudaLado = "izquierda";
    let espera = null;

    const reposo = () => {
      boton.classList.remove("hecho");
      boton.replaceChildren(icono("copiar"), crear("span", "oculto", "Copiar el ejemplo"));
    };
    reposo();

    boton.addEventListener("click", async () => {
      let copiado = false;
      try {
        await navigator.clipboard.writeText(texto);
        copiado = true;
      } catch (_) {
        // Sin permiso, o una página sin HTTPS: queda seleccionado para copiarlo a mano.
        const rango = document.createRange();
        rango.selectNodeContents(pre);
        const seleccion = window.getSelection();
        seleccion.removeAllRanges();
        seleccion.addRange(rango);
      }
      const aviso = copiado ? "Copiado" : `Seleccionado: ${MOD}+C para copiar`;
      boton.classList.add("hecho");
      boton.replaceChildren(icono(copiado ? "listo" : "copiar"),
                            crear("span", "ayuda-copiar-texto", aviso));
      anunciar(copiado ? "Ejemplo copiado" : aviso);
      clearTimeout(espera);
      espera = setTimeout(reposo, copiado ? 2000 : 4000);
    });
    return boton;
  }

  // Lo imprescindible a la vista (resumen, sintaxis, ejemplo, resultado y la regla que
  // no hay que olvidar); el resto de los detalles, plegado.
  function crearTema(tema) {
    const art = crear("article", "ayuda-tema");
    art.id = "tema-" + tema.id;
    art.appendChild(crear("h3", null, tema.titulo));

    if (tema.experimental) {
      const aviso = crear("p", "ayuda-experimental");
      aviso.append(crear("span", "ayuda-etiqueta", "Experimental"), " " + tema.experimental);
      art.appendChild(aviso);
    }
    art.appendChild(crear("p", "ayuda-resumen", tema.resumen));

    art.append(crear("h4", null, "Sintaxis"), pintar(tema.sintaxis));

    const ejemplo = pintar(tema.ejemplo);
    const rotulo = crear("div", "ayuda-rotulo");
    rotulo.append(crear("h4", null, "Ejemplo"), botonCopiar(tema.ejemplo, ejemplo));
    art.append(rotulo, ejemplo);

    if (tema.salida) art.append(crear("h4", null, "Resultado"), crearSalida(tema.salida));

    if (tema.recorda) {
      const recorda = crear("aside", "ayuda-recorda");
      const titulo = crear("p", "ayuda-recorda-titulo");
      titulo.append(icono("lamparita"), "Recordá");
      recorda.append(titulo, crear("p", null, tema.recorda));
      art.appendChild(recorda);
    }

    if (tema.notas && tema.notas.length) {
      const detalles = crear("details", "ayuda-detalles");
      detalles.appendChild(crear("summary", null, "Más detalles"));
      const ul = crear("ul", "ayuda-notas");
      for (const nota of tema.notas) ul.appendChild(crear("li", null, nota));
      detalles.appendChild(ul);
      art.appendChild(detalles);
    }
    return art;
  }

  function crearPie() {
    const pie = crear("footer", "ayuda-pie");
    const version = window.PseudoLab && window.PseudoLab.version;
    pie.append(crear("p", null, datos.bajada),
               crear("p", null, "PseudoLab · Hecho para Programación Lógica" +
                                (version ? " · " + version : "")));
    return pie;
  }

  // ------------------------------------------------------------------ las vistas

  function vistaGuardada() {
    try {
      return localStorage.getItem(CLAVE);
    } catch (_) {
      return null;
    }
  }

  function guardarVista(id) {
    try {
      localStorage.setItem(CLAVE, id);
    } catch (_) { /* sin memoria, vale para esta sesión igual */ }
  }

  function vistaInicial() {
    const guardada = vistaGuardada();
    return guardada && seccionPorId(guardada) ? guardada : datos.secciones[0].id;
  }

  // Si hay algo en el buscador, arriba de todo queda el camino de vuelta a los resultados.
  function empezarVista(titulo) {
    enResultados = false;
    const c = partes.contenido;
    c.replaceChildren();
    const consulta = partes.buscador.value.trim();
    if (consulta) {
      const volver = crear("button", "ayuda-volver");
      volver.type = "button";
      volver.append(icono("volver"), `Resultados para «${consulta}»`);
      volver.addEventListener("click", () => {
        mostrarResultados();
        partes.buscador.focus();
      });
      c.appendChild(volver);
    }
    c.appendChild(crear("h2", "ayuda-categoria-titulo", titulo));
    actualizarCombobox();
  }

  function mostrarCategoria(id, temaId, { abrirDetalles = false } = {}) {
    const seccion = seccionPorId(id) || datos.secciones[0];
    vista = seccion.id;
    elegido = temaId || null;
    guardarVista(seccion.id);

    empezarVista(seccion.titulo);
    const c = partes.contenido;
    for (const tema of seccion.temas) c.appendChild(crearTema(tema));
    c.appendChild(crearPie());
    marcarCategoria(seccion.id);

    const art = temaId && c.querySelector("#tema-" + CSS.escape(temaId));
    if (!art) {
      c.scrollTop = 0;
      seguirLectura();
      return;
    }
    if (abrirDetalles) {
      const detalles = art.querySelector("details");
      if (detalles) detalles.open = true;
    }
    // El primer tema ya está arriba: bajar hasta él escondería el título de la categoría.
    if (art === c.querySelector(".ayuda-tema")) c.scrollTop = 0;
    else bajarHasta(art, false);
    marcarTema(temaId);
    destacar(art);
  }

  function mostrarNovedades() {
    vista = "novedades";
    elegido = null;
    empezarVista("Novedades");
    const c = partes.contenido;
    for (const novedad of datos.novedades) {
      const art = crear("article", "ayuda-novedad");
      art.append(crear("p", "ayuda-novedad-fecha", fechaLegible(novedad.fecha)),
                 crear("h3", null, novedad.titulo),
                 crear("p", "ayuda-resumen", novedad.texto));
      const lugar = novedad.tema && temaPorId(novedad.tema);
      if (lugar) {
        const ver = crear("a", "ayuda-novedad-tema",
                          `Ver en la Referencia: ${lugar.tema.titulo}`);
        ver.href = "#tema-" + novedad.tema;
        ver.addEventListener("click", (e) => {
          e.preventDefault();
          ir(novedad.tema);
        });
        art.appendChild(ver);
      }
      c.appendChild(art);
    }
    c.appendChild(crearPie());
    marcarCategoria("novedades");
    c.scrollTop = 0;
  }

  function fechaLegible(iso) {
    const [anio, mes, dia] = String(iso).split("-");
    return dia ? `${dia}/${mes}/${anio}` : iso;
  }

  function mostrarVista() {
    if (vista === "novedades") mostrarNovedades();
    else mostrarCategoria(vista || vistaInicial());
  }

  // destino: un tema ("arreglos"), una categoría ("operadores") o "novedades".
  function ir(destino) {
    const lugar = temaPorId(destino);
    if (lugar) mostrarCategoria(lugar.seccion.id, lugar.tema.id);
    else if (destino === "novedades") mostrarNovedades();
    else mostrarCategoria(seccionPorId(destino) ? destino : vistaInicial());
  }

  function irATema(seccionId, temaId) {
    if (vista !== seccionId || enResultados) {
      mostrarCategoria(seccionId, temaId);
      return;
    }
    const art = partes.contenido.querySelector("#tema-" + CSS.escape(temaId));
    if (!art) return;
    elegido = temaId;
    bajarHasta(art, true);
    marcarTema(temaId);
  }

  function bajarHasta(nodo, suave) {
    const c = partes.contenido;
    const arriba = nodo.getBoundingClientRect().top - c.getBoundingClientRect().top;
    c.scrollTo({ top: c.scrollTop + arriba - 12,
                 behavior: suave && !menosMovimiento() ? "smooth" : "auto" });
  }

  function destacar(nodo) {
    nodo.classList.remove("destacado");
    void nodo.offsetWidth;            // para que la animación arranque de nuevo
    nodo.classList.add("destacado");
    setTimeout(() => nodo.classList.remove("destacado"), 1600);
  }

  // ----------------------------------------------------------- barra lateral

  function crearIndice(ref) {
    const nav = crear("nav", "ayuda-indice");
    nav.setAttribute("aria-label", "Categorías");
    for (const grupo of ref.grupos) {
      const bloque = crear("div", "ayuda-grupo");
      bloque.appendChild(crear("p", "ayuda-grupo-titulo", grupo.titulo));
      const lista = crear("ul");
      for (const seccion of ref.secciones.filter((s) => s.grupo === grupo.id)) {
        lista.appendChild(crearEntradaIndice(seccion));
      }
      bloque.appendChild(lista);
      nav.appendChild(bloque);
    }
    if (ref.novedades && ref.novedades.length) {
      const bloque = crear("div", "ayuda-grupo");
      const boton = crear("button", "ayuda-categoria", "Novedades");
      boton.type = "button";
      boton.dataset.seccion = "novedades";
      boton.addEventListener("click", mostrarNovedades);
      bloque.appendChild(boton);
      nav.appendChild(bloque);
    }
    return nav;
  }

  function crearEntradaIndice(seccion) {
    const li = crear("li");
    const boton = crear("button", "ayuda-categoria", seccion.titulo);
    boton.type = "button";
    boton.dataset.seccion = seccion.id;
    li.appendChild(boton);

    // Una categoría de un solo tema no despliega nada: repetiría su propio nombre.
    if (seccion.temas.length < 2) {
      boton.addEventListener("click", () => mostrarCategoria(seccion.id));
      return li;
    }

    const temas = crear("ul", "ayuda-temas");
    temas.id = "ayuda-temas-" + seccion.id;
    temas.hidden = true;
    boton.setAttribute("aria-expanded", "false");
    boton.setAttribute("aria-controls", temas.id);
    boton.addEventListener("click", () => {
      if (vista === seccion.id && !enResultados) {
        // La que ya se está viendo solo se pliega o se despliega.
        const abierta = boton.getAttribute("aria-expanded") === "true";
        boton.setAttribute("aria-expanded", String(!abierta));
        temas.hidden = abierta;
      } else {
        mostrarCategoria(seccion.id);
      }
    });
    for (const tema of seccion.temas) {
      const item = crear("li");
      const enlace = crear("a", null, tema.corto || tema.titulo);
      enlace.href = "#tema-" + tema.id;
      enlace.dataset.tema = tema.id;
      enlace.addEventListener("click", (e) => {
        e.preventDefault();
        irATema(seccion.id, tema.id);
      });
      item.appendChild(enlace);
      temas.appendChild(item);
    }
    li.appendChild(temas);
    return li;
  }

  // En pantallas angostas la barra lateral no entra: la reemplaza una lista desplegable.
  function crearSelector(ref) {
    const selector = crear("select", "ayuda-selector");
    selector.setAttribute("aria-label", "Categoría");
    for (const grupo of ref.grupos) {
      const opciones = document.createElement("optgroup");
      opciones.label = grupo.titulo;
      for (const seccion of ref.secciones.filter((s) => s.grupo === grupo.id)) {
        opciones.appendChild(new Option(seccion.titulo, seccion.id));
      }
      selector.appendChild(opciones);
    }
    if (ref.novedades && ref.novedades.length) {
      selector.appendChild(new Option("Novedades", "novedades"));
    }
    selector.addEventListener("change", () => {
      if (selector.value === "novedades") mostrarNovedades();
      else mostrarCategoria(selector.value);
    });
    return selector;
  }

  // Cambia la selección sin mover la barra lateral: como mucho, la acomoda para que la
  // categoría activa se vea (cuando se llegó desde una búsqueda).
  function marcarCategoria(id) {
    for (const boton of partes.indice.querySelectorAll(".ayuda-categoria")) {
      const activa = boton.dataset.seccion === id;
      boton.classList.toggle("activa", activa);
      if (activa) boton.setAttribute("aria-current", "true");
      else boton.removeAttribute("aria-current");
      const temas = boton.nextElementSibling;
      if (temas) {
        temas.hidden = !activa;
        boton.setAttribute("aria-expanded", String(activa));
      }
    }
    const activa = partes.indice.querySelector(".ayuda-categoria.activa");
    if (activa) activa.scrollIntoView({ block: "nearest" });
    partes.selector.value = id;
  }

  function marcarTema(id) {
    for (const enlace of partes.indice.querySelectorAll("a[data-tema]")) {
      const actual = enlace.dataset.tema === id;
      enlace.classList.toggle("actual", actual);
      if (actual) enlace.setAttribute("aria-current", "location");
      else enlace.removeAttribute("aria-current");
    }
  }

  function visible(nodo) {
    const caja = partes.contenido.getBoundingClientRect();
    const r = nodo.getBoundingClientRect();
    return r.top < caja.bottom && r.bottom > caja.top;
  }

  // Mientras se baja por una categoría, la barra lateral marca el tema que se está leyendo.
  function seguirLectura() {
    const c = partes.contenido;
    const temas = [...c.querySelectorAll(".ayuda-tema")];
    if (!temas.length) return;
    const arriba = c.getBoundingClientRect().top;
    let actual = temas[0];
    for (const art of temas) {
      if (art.getBoundingClientRect().top - arriba <= 100) actual = art;
    }
    // Los temas del final nunca llegan arriba de todo. Al fondo gana el que se eligió
    // (si se ve), o el último.
    if (c.scrollTop > 0 && c.scrollTop + c.clientHeight >= c.scrollHeight - 4) {
      const art = elegido && c.querySelector("#tema-" + CSS.escape(elegido));
      actual = art && visible(art) ? art : temas[temas.length - 1];
    }
    marcarTema(actual.id.slice("tema-".length));
  }

  // -------------------------------------------------------------------- búsqueda

  // Minúsculas y sin tildes, letra por letra: así cada posición del texto "plano" es la
  // misma que en el original, y se puede resaltar lo encontrado.
  function plano(texto) {
    let r = "";
    for (let i = 0; i < texto.length; i++) {
      r += texto[i].normalize("NFD")[0].toLowerCase()[0];
    }
    return r;
  }

  const esPalabra = (token) => /^[a-z0-9_]/.test(token);

  // "divisiones" también encuentra "división".
  function variantes(token) {
    const v = [token];
    if (token.length > 4 && token.endsWith("es")) v.push(token.slice(0, -2));
    if (token.length > 3 && token.endsWith("s")) v.push(token.slice(0, -1));
    return v;
  }

  function armarIndice() {
    const campo = (peso, texto) => {
      const p = plano(texto);
      return { peso, texto: p, palabras: p.match(/[a-z0-9_]+/g) || [] };
    };
    indice = [];
    for (const seccion of datos.secciones) {
      for (const tema of seccion.temas) {
        indice.push({
          seccion,
          tema,
          campos: [
            campo(10, [tema.titulo, tema.corto || "", ...(tema.cubre || [])].join(" · ")),
            campo(8, (tema.buscar || []).join(" · ")),
            campo(4, tema.resumen),
            campo(3, tema.recorda || ""),
            campo(2, (tema.notas || []).join(" · ")),
            campo(1, tema.sintaxis + "\n" + tema.ejemplo),
          ],
          exactos: new Set([tema.corto || tema.titulo, ...(tema.cubre || [])].map(plano)),
          frases: (tema.buscar || []).map(plano),
        });
      }
    }
  }

  // 1 si la palabra está entera, 0.85 si algo empieza con ella, 0 si no está. Los
  // símbolos (%, ++, !=) se buscan tal cual, en cualquier lugar.
  function coincide(token, campo) {
    if (!esPalabra(token)) return campo.texto.includes(token) ? 1 : 0;
    let mejor = 0;
    for (const v of variantes(token)) {
      for (const palabra of campo.palabras) {
        if (palabra === v) return 1;
        if (palabra.startsWith(v)) mejor = 0.85;
      }
    }
    return mejor;
  }

  // Cada palabra de la búsqueda tiene que estar en algún campo; vale más cuanto más
  // importante es el campo donde está.
  function puntuar(entrada, tokens, consulta) {
    let total = 0;
    let enNotas = false;
    for (const token of tokens) {
      let mejor = 0;
      let peso = 0;
      for (const campo of entrada.campos) {
        const valor = coincide(token, campo) * campo.peso;
        if (valor > mejor) {
          mejor = valor;
          peso = campo.peso;
        }
      }
      if (!mejor) return null;
      if (peso === 2) enNotas = true;
      total += mejor;
    }
    if (entrada.exactos.has(consulta)) total += 30;
    else if (entrada.frases.includes(consulta)) total += 20;
    else if (tokens.length > 1 && entrada.frases.some((f) => f.includes(consulta))) total += 10;
    // Si algo solo aparece en los detalles, se abren al llegar.
    return { ...entrada, puntaje: total, abrirDetalles: enNotas };
  }

  function buscar(texto) {
    const consulta = plano(texto).trim().replace(/\s+/g, " ");
    let tokens = consulta.match(/[a-z0-9_]+|[^\sa-z0-9_]+/g) || [];
    const utiles = tokens.filter((t) => !VACIAS.has(t));
    if (utiles.length) tokens = utiles;
    const lista = [];
    for (const entrada of indice) {
      const r = puntuar(entrada, tokens, consulta);
      if (r) lista.push(r);
    }
    lista.sort((a, b) => b.puntaje - a.puntaje);   // a igual puntaje, el orden de la referencia
    return { tokens, lista };
  }

  function distancia(a, b) {
    if (Math.abs(a.length - b.length) > 2) return Infinity;
    let previa = Array.from({ length: b.length + 1 }, (_, j) => j);
    for (let i = 1; i <= a.length; i++) {
      const fila = [i];
      for (let j = 1; j <= b.length; j++) {
        fila[j] = Math.min(previa[j] + 1, fila[j - 1] + 1,
                           previa[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
      }
      previa = fila;
    }
    return previa[b.length];
  }

  // "mientars" -> "mientras": se compara contra los nombres y las frases de búsqueda,
  // no contra los ejemplos (ahí hay nombres de variables que no ayudan).
  function quisisteDecir(tokens) {
    if (!palabrasClave) {
      palabrasClave = new Set();
      for (const entrada of indice) {
        for (const campo of entrada.campos) {
          if (campo.peso < 8) continue;
          for (const p of campo.palabras) if (p.length >= 3) palabrasClave.add(p);
        }
      }
    }
    let cambio = false;
    const arreglados = tokens.map((token) => {
      if (!esPalabra(token) || token.length < 3) return token;
      if (indice.some((e) => e.campos.some((c) => coincide(token, c)))) return token;
      let mejor = null;
      let menor = (token.length <= 5 ? 1 : 2) + 1;
      for (const palabra of palabrasClave) {
        const d = distancia(token, palabra);
        if (d < menor) {
          menor = d;
          mejor = palabra;
        }
      }
      if (!mejor) return token;
      cambio = true;
      return mejor;
    });
    if (!cambio) return null;
    const sugerida = arreglados.join(" ");
    return buscar(sugerida).lista.length ? sugerida : null;
  }

  function resaltar(texto, tokens) {
    const p = plano(texto);
    const marcas = [];
    for (const token of tokens) {
      const simbolo = !esPalabra(token);
      for (const v of simbolo ? [token] : variantes(token)) {
        for (let i = p.indexOf(v); i !== -1; i = p.indexOf(v, i + 1)) {
          const fin = i + v.length;
          const empieza = simbolo || i === 0 || !/[a-z0-9_]/.test(p[i - 1]);
          // Una letra suelta ("y", "o") solo se marca si es una palabra entera.
          const termina = v.length > 1 || fin === p.length || !/[a-z0-9_]/.test(p[fin]);
          if (empieza && termina) marcas.push([i, fin]);
        }
      }
    }
    const fragmento = document.createDocumentFragment();
    marcas.sort((a, b) => a[0] - b[0]);
    let pos = 0;
    for (const [desde, hasta] of marcas) {
      if (hasta <= pos) continue;
      const inicio = Math.max(desde, pos);
      if (inicio > pos) fragmento.append(texto.slice(pos, inicio));
      fragmento.appendChild(crear("mark", null, texto.slice(inicio, hasta)));
      pos = hasta;
    }
    fragmento.append(texto.slice(pos));
    return fragmento;
  }

  function mostrarResultados() {
    enResultados = true;
    const consulta = partes.buscador.value.trim();
    const { tokens, lista } = buscar(consulta);
    resultados = lista;
    marcado = resultados.length ? 0 : -1;

    const c = partes.contenido;
    c.replaceChildren();
    c.scrollTop = 0;
    if (!resultados.length) {
      c.appendChild(crearSinResultados(consulta, tokens));
      actualizarCombobox();
      anunciar("Sin resultados");
      return;
    }
    const cuenta = `${resultados.length} ${resultados.length === 1 ? "resultado" : "resultados"}`;
    c.appendChild(crear("p", "ayuda-cuenta", cuenta));
    const ul = crear("ul", "ayuda-resultados");
    ul.id = "ayuda-resultados";
    ul.setAttribute("role", "listbox");
    ul.setAttribute("aria-label", "Resultados de la búsqueda");
    resultados.forEach((r, i) => {
      const li = crear("li", "ayuda-resultado");
      li.id = "ayuda-resultado-" + i;
      li.setAttribute("role", "option");
      const titulo = crear("span", "ayuda-resultado-titulo");
      titulo.appendChild(resaltar(r.tema.titulo, tokens));
      const resumen = crear("span", "ayuda-resultado-resumen");
      resumen.appendChild(resaltar(r.tema.resumen, tokens));
      li.append(crear("span", "ayuda-resultado-donde", r.seccion.titulo), titulo, resumen);
      li.addEventListener("click", () => abrirResultado(i));
      ul.appendChild(li);
    });
    c.appendChild(ul);
    marcar(marcado);
    anunciar(cuenta);
  }

  function crearSinResultados(consulta, tokens) {
    const caja = crear("div", "ayuda-vacio");
    caja.appendChild(crear("p", "ayuda-vacio-titulo", `No encontramos nada para «${consulta}».`));
    const sugerida = quisisteDecir(tokens);
    if (sugerida) {
      const p = crear("p", null, "¿Quisiste decir ");
      const boton = crear("button", "ayuda-enlace", sugerida);
      boton.type = "button";
      boton.addEventListener("click", () => buscarTexto(sugerida));
      p.append(boton, "?");
      caja.appendChild(p);
    }
    caja.appendChild(crear("p", null, "Probá con otras palabras, por ejemplo:"));
    const chips = crear("div", "ayuda-sugerencias");
    for (const s of SUGERENCIAS) {
      const chip = crear("button", "ayuda-chip", s);
      chip.type = "button";
      chip.addEventListener("click", () => buscarTexto(s));
      chips.appendChild(chip);
    }
    const borrar = crear("button", "ayuda-borrar-busqueda", "Borrar búsqueda");
    borrar.type = "button";
    borrar.addEventListener("click", borrarBusqueda);
    caja.append(chips, borrar);
    return caja;
  }

  function marcar(i) {
    marcado = i;
    for (const li of partes.contenido.querySelectorAll(".ayuda-resultado")) {
      const este = li.id === "ayuda-resultado-" + i;
      li.classList.toggle("marcado", este);
      li.setAttribute("aria-selected", String(este));
      if (este) li.scrollIntoView({ block: "nearest" });
    }
    actualizarCombobox();
  }

  function actualizarCombobox() {
    const b = partes.buscador;
    const abierto = enResultados && resultados.length > 0;
    b.setAttribute("aria-expanded", String(abierto));
    if (abierto && marcado >= 0) b.setAttribute("aria-activedescendant", "ayuda-resultado-" + marcado);
    else b.removeAttribute("aria-activedescendant");
  }

  // La búsqueda queda escrita: desde el tema se puede volver a los resultados.
  function abrirResultado(i) {
    const r = resultados[i];
    if (!r) return;
    mostrarCategoria(r.seccion.id, r.tema.id, { abrirDetalles: r.abrirDetalles });
  }

  function buscarTexto(texto) {
    partes.buscador.value = texto;
    partes.borrar.hidden = false;
    mostrarResultados();
    partes.buscador.focus();
  }

  function limpiarBusqueda() {
    partes.buscador.value = "";
    partes.borrar.hidden = true;
  }

  function borrarBusqueda() {
    limpiarBusqueda();
    if (enResultados) {
      mostrarVista();
    } else {
      const volver = partes.contenido.querySelector(".ayuda-volver");
      if (volver) volver.remove();
      actualizarCombobox();
    }
    partes.buscador.focus();
  }

  function alEscribir() {
    partes.borrar.hidden = !partes.buscador.value;
    if (partes.buscador.value.trim()) mostrarResultados();
    else if (enResultados) mostrarVista();
  }

  function alTecladoBuscador(e) {
    const hayConsulta = partes.buscador.value.trim() !== "";
    if ((e.key === "ArrowDown" || e.key === "ArrowUp") && hayConsulta) {
      e.preventDefault();
      if (!enResultados) {
        mostrarResultados();
      } else if (resultados.length) {
        const paso = e.key === "ArrowDown" ? 1 : -1;
        marcar((marcado + paso + resultados.length) % resultados.length);
      }
    } else if (e.key === "Enter" && enResultados && marcado >= 0) {
      e.preventDefault();
      abrirResultado(marcado);
    }
  }

  // ------------------------------------------------------------------- el panel

  function construir(ref) {
    const caja = crear("div", "ayuda-caja");
    caja.setAttribute("role", "dialog");
    caja.setAttribute("aria-modal", "true");
    caja.setAttribute("aria-labelledby", "ayuda-titulo");

    // --- encabezado
    const cab = crear("header", "ayuda-cabecera");
    const titulo = crear("h2", "ayuda-titulo");
    titulo.id = "ayuda-titulo";
    titulo.append(icono("libro"), ref.titulo);
    const cerrar = crear("button", "ayuda-cerrar");
    cerrar.type = "button";
    cerrar.setAttribute("aria-label", "Cerrar la referencia");
    cerrar.appendChild(icono("cerrar"));
    cerrar.addEventListener("click", ocultar);
    cab.append(titulo, crear("span", "ayuda-subtitulo", ref.subtitulo || ""), cerrar);

    // --- buscador
    const campo = crear("div", "ayuda-campo");
    const buscador = crear("input", "ayuda-buscador");
    buscador.type = "text";
    buscador.placeholder = "¿Qué necesitás hacer?";
    buscador.autocomplete = "off";
    buscador.spellcheck = false;
    buscador.enterKeyHint = "search";
    buscador.setAttribute("role", "combobox");
    buscador.setAttribute("aria-autocomplete", "list");
    buscador.setAttribute("aria-expanded", "false");
    buscador.setAttribute("aria-controls", "ayuda-resultados");
    buscador.setAttribute("aria-label", "Buscar en la referencia");
    const borrar = crear("button", "ayuda-borrar", "Borrar");
    borrar.type = "button";
    borrar.hidden = true;
    borrar.setAttribute("aria-label", "Borrar la búsqueda");
    borrar.addEventListener("click", borrarBusqueda);
    const tecla = crear("kbd", "ayuda-tecla", "Esc");
    tecla.setAttribute("aria-hidden", "true");
    campo.append(icono("lupa"), buscador, borrar, tecla);
    // Toda la caja del buscador lleva al campo, no solo el texto.
    campo.addEventListener("mousedown", (e) => {
      if (!e.target.closest("button, input")) {
        e.preventDefault();
        buscador.focus();
      }
    });
    const busqueda = crear("div", "ayuda-busqueda");
    busqueda.appendChild(campo);

    // --- categorías y contenido
    const cuerpo = crear("div", "ayuda-cuerpo");
    const indiceNav = crearIndice(ref);
    const contenido = crear("div", "ayuda-contenido");
    cuerpo.append(indiceNav, contenido);
    const selector = crearSelector(ref);

    const anuncio = crear("p", "oculto");
    anuncio.setAttribute("aria-live", "polite");

    caja.append(cab, busqueda, selector, cuerpo, anuncio);
    partes = { buscador, borrar, selector, indice: indiceNav, contenido, anuncio };

    buscador.addEventListener("input", alEscribir);
    buscador.addEventListener("keydown", alTecladoBuscador);
    let cuadroPedido = false;
    contenido.addEventListener("scroll", () => {
      if (cuadroPedido) return;
      cuadroPedido = true;
      requestAnimationFrame(() => {
        cuadroPedido = false;
        if (!enResultados && vista !== "novedades") seguirLectura();
      });
    });
    return caja;
  }

  // Esc primero borra lo que hay escrito en el buscador; con el buscador vacío, cierra.
  function alTeclado(e) {
    if (e.key !== "Escape" || !panel || panel.hidden) return;
    e.preventDefault();
    if (partes && e.target === partes.buscador && partes.buscador.value) {
      borrarBusqueda();
      return;
    }
    ocultar();
  }

  function ocultar() {
    if (!panel) return;
    panel.hidden = true;
    document.removeEventListener("keydown", alTeclado);
    if (ultimoFoco) ultimoFoco.focus();
  }

  // destino: un tema ("arreglos"), una categoría ("operadores") o "novedades". Sin
  // destino, vuelve a donde se dejó.
  async function abrir(destino) {
    ultimoFoco = document.activeElement;
    if (!panel) {
      panel = crear("div", "ayuda-fondo");
      panel.addEventListener("click", (e) => { if (e.target === panel) ocultar(); });
      document.body.appendChild(panel);
    }
    if (!partes) {
      try {
        panel.replaceChildren(construir(await cargar()));
        armarIndice();
      } catch (e) {
        partes = null;
        panel.textContent = "No se pudo abrir la referencia: " + e.message;
        panel.hidden = false;
        return;
      }
    }
    // Visible antes de elegir la vista: para bajar hasta un tema hay que poder medirlo.
    panel.hidden = false;
    document.addEventListener("keydown", alTeclado);
    if (typeof destino === "string") {
      limpiarBusqueda();
      ir(destino);
    } else if (!vista) {
      ir(vistaInicial());
    }
    partes.buscador.focus({ preventScroll: true });
    partes.buscador.select();
  }

  // app.js avisa cuando el modo del editor quedó armado, para repintar los ejemplos
  // que se hayan dibujado antes en texto plano.
  function modoListo() {
    if (!partes || enResultados) return;
    for (const art of partes.contenido.querySelectorAll(".ayuda-tema")) {
      const lugar = temaPorId(art.id.slice("tema-".length));
      if (!lugar) continue;
      const nuevo = crearTema(lugar.tema);
      const detalles = art.querySelector("details");
      if (detalles && detalles.open) nuevo.querySelector("details").open = true;
      art.replaceWith(nuevo);
    }
  }

  // El nombre de un tema, o null si no existe o la referencia no se pudo cargar. app.js lo
  // usa para ofrecer, al lado de un error, el tema que lo explica.
  function titulo(id) {
    const lugar = datos && temaPorId(id);
    return lugar ? lugar.tema.titulo : null;
  }

  // cargar: el aviso de novedades de app.js usa los mismos datos, sin volver a pedirlos.
  window.Ayuda = { abrir, ocultar, modoListo, cargar, titulo };
})();
