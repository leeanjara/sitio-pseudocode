"use strict";

// Panel de referencia del lenguaje. El contenido no está acá: vive en referencia.json,
// que además un test de Python verifica (que no falte ninguna palabra reservada y que
// todos los ejemplos compilen de verdad). Acá solo se dibuja.

(function () {
  let datos = null;
  let panel = null;
  let ultimoFoco = null;

  async function cargar() {
    if (datos) return datos;
    const url = new URL("referencia.json", document.baseURI);
    const r = await fetch(url, { cache: "no-store" });
    if (!r.ok) throw new Error(`no se pudo leer referencia.json (${r.status})`);
    datos = await r.json();
    return datos;
  }

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

  function crearTema(tema) {
    const art = document.createElement("article");
    art.className = "ayuda-tema";
    art.id = "tema-" + tema.id;

    const h3 = document.createElement("h3");
    h3.textContent = tema.titulo;
    art.appendChild(h3);

    const resumen = document.createElement("p");
    resumen.className = "ayuda-resumen";
    resumen.textContent = tema.resumen;
    art.appendChild(resumen);

    if (tema.sintaxis) {
      const rotulo = document.createElement("h4");
      rotulo.textContent = "Cómo se escribe";
      art.append(rotulo, pintar(tema.sintaxis));
    }

    const rotuloEj = document.createElement("h4");
    rotuloEj.textContent = "Ejemplo";
    art.append(rotuloEj, pintar(tema.ejemplo));

    if (tema.notas && tema.notas.length) {
      const ul = document.createElement("ul");
      ul.className = "ayuda-notas";
      for (const nota of tema.notas) {
        const li = document.createElement("li");
        li.textContent = nota;
        ul.appendChild(li);
      }
      art.appendChild(ul);
    }
    return art;
  }

  function construir(ref) {
    const caja = document.createElement("div");
    caja.className = "ayuda-caja";
    caja.setAttribute("role", "dialog");
    caja.setAttribute("aria-modal", "true");
    caja.setAttribute("aria-label", ref.titulo);

    // --- encabezado
    const cab = document.createElement("header");
    cab.className = "ayuda-cabecera";
    const titulo = document.createElement("h2");
    titulo.textContent = ref.titulo;
    const buscador = document.createElement("input");
    buscador.type = "search";
    buscador.className = "ayuda-buscador";
    buscador.placeholder = "Buscar (ej: Para, Mod, redondear…)";
    buscador.setAttribute("aria-label", "Buscar en la referencia");
    const cerrar = document.createElement("button");
    cerrar.className = "ayuda-cerrar";
    cerrar.textContent = "×";
    cerrar.setAttribute("aria-label", "Cerrar la referencia");
    cerrar.addEventListener("click", ocultar);
    cab.append(titulo, buscador, cerrar);

    // --- índice y contenido
    const cuerpo = document.createElement("div");
    cuerpo.className = "ayuda-cuerpo";
    const indice = document.createElement("nav");
    indice.className = "ayuda-indice";
    const contenido = document.createElement("div");
    contenido.className = "ayuda-contenido";

    const bajada = document.createElement("p");
    bajada.className = "ayuda-bajada";
    bajada.textContent = ref.bajada;
    contenido.appendChild(bajada);

    for (const seccion of ref.secciones) {
      const grupo = document.createElement("div");
      grupo.className = "ayuda-grupo";
      const rotulo = document.createElement("p");
      rotulo.className = "ayuda-grupo-titulo";
      rotulo.textContent = seccion.titulo;
      grupo.appendChild(rotulo);

      const bloque = document.createElement("section");
      bloque.className = "ayuda-seccion";
      bloque.id = "seccion-" + seccion.id;
      const h2 = document.createElement("h2");
      h2.textContent = seccion.titulo;
      bloque.appendChild(h2);

      for (const tema of seccion.temas) {
        const enlace = document.createElement("a");
        enlace.href = "#tema-" + tema.id;
        enlace.textContent = tema.titulo;
        enlace.dataset.tema = tema.id;
        enlace.addEventListener("click", (e) => {
          e.preventDefault();
          const destino = contenido.querySelector("#tema-" + CSS.escape(tema.id));
          if (destino) destino.scrollIntoView({ behavior: "smooth", block: "start" });
        });
        grupo.appendChild(enlace);
        bloque.appendChild(crearTema(tema));
      }
      indice.appendChild(grupo);
      contenido.appendChild(bloque);
    }

    cuerpo.append(indice, contenido);
    caja.append(cab, cuerpo);

    buscador.addEventListener("input", () => filtrar(caja, buscador.value));
    return caja;
  }

  function textoDeTema(tema) {
    return [tema.titulo, tema.resumen, tema.sintaxis, tema.ejemplo,
            (tema.notas || []).join(" "), (tema.cubre || []).join(" ")]
      .join(" ").toLowerCase();
  }

  function filtrar(caja, consulta) {
    const q = consulta.trim().toLowerCase();
    let visibles = 0;
    for (const seccion of datos.secciones) {
      let enSeccion = 0;
      for (const tema of seccion.temas) {
        const coincide = !q || textoDeTema(tema).includes(q);
        const art = caja.querySelector("#tema-" + CSS.escape(tema.id));
        const enlace = caja.querySelector(`[data-tema="${CSS.escape(tema.id)}"]`);
        if (art) art.hidden = !coincide;
        if (enlace) enlace.hidden = !coincide;
        if (coincide) { enSeccion++; visibles++; }
      }
      // Una sección sin temas visibles se esconde entera, título incluido.
      const bloque = caja.querySelector("#seccion-" + CSS.escape(seccion.id));
      if (bloque) bloque.hidden = enSeccion === 0;
      const grupo = bloque && caja.querySelectorAll(".ayuda-grupo")[
        datos.secciones.indexOf(seccion)];
      if (grupo) grupo.hidden = enSeccion === 0;
    }
    let aviso = caja.querySelector(".ayuda-sin-resultados");
    if (!aviso) {
      aviso = document.createElement("p");
      aviso.className = "ayuda-sin-resultados";
      aviso.textContent = "No hay nada con esa palabra.";
      caja.querySelector(".ayuda-contenido").appendChild(aviso);
    }
    aviso.hidden = visibles > 0;
  }

  function alTeclado(e) {
    if (e.key === "Escape" && panel && !panel.hidden) {
      e.preventDefault();
      ocultar();
    }
  }

  function ocultar() {
    if (!panel) return;
    panel.hidden = true;
    document.removeEventListener("keydown", alTeclado);
    if (ultimoFoco) ultimoFoco.focus();
  }

  async function abrir() {
    ultimoFoco = document.activeElement;
    if (!panel) {
      panel = document.createElement("div");
      panel.className = "ayuda-fondo";
      panel.addEventListener("click", (e) => { if (e.target === panel) ocultar(); });
      document.body.appendChild(panel);
    }
    if (!panel.firstChild) {
      panel.textContent = "Cargando la referencia…";
      try {
        panel.textContent = "";
        panel.appendChild(construir(await cargar()));
      } catch (e) {
        panel.textContent = "No se pudo abrir la referencia: " + e.message;
        panel.hidden = false;
        return;
      }
    }
    panel.hidden = false;
    document.addEventListener("keydown", alTeclado);
    const buscador = panel.querySelector(".ayuda-buscador");
    if (buscador) buscador.focus();
  }

  // app.js avisa cuando el modo del editor quedó armado, para repintar los ejemplos
  // que se hayan dibujado antes en texto plano.
  function modoListo() {
    if (!panel || !panel.firstChild || !datos) return;
    const contenido = panel.querySelector(".ayuda-contenido");
    for (const seccion of datos.secciones) {
      for (const tema of seccion.temas) {
        const art = contenido.querySelector("#tema-" + CSS.escape(tema.id));
        if (art) art.replaceWith(crearTema(tema));
      }
    }
  }

  window.Ayuda = { abrir, ocultar, modoListo };
})();
