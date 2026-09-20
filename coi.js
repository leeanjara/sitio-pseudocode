/* Habilita la consola interactiva en hosting estático (GitHub Pages y parecidos).
 *
 * Por qué existe este archivo: para que 'Leer' pueda frenar el programa hasta que el
 * estudiante escriba, la página necesita SharedArrayBuffer, y los navegadores solo lo
 * dan si el servidor manda dos encabezados (COOP y COEP). GitHub Pages no deja
 * configurar encabezados, así que se instala un service worker que los agrega él mismo
 * a las respuestas y después recarga la página una vez.
 *
 * Si algo de esto falla (navegador viejo, file://, modo incógnito), no pasa nada malo:
 * app.js lo detecta y cambia solo al modo de datos precargados.
 *
 * Este mismo archivo corre en los dos lados; el 'if' de abajo distingue cuál es cuál.
 */

if (typeof document === "undefined") {
  // ----------------------------------------------- corriendo como service worker

  self.addEventListener("install", () => self.skipWaiting());
  self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));

  self.addEventListener("fetch", (evento) => {
    const pedido = evento.request;
    // Estas no se pueden reenviar sin romper la caché del navegador.
    if (pedido.cache === "only-if-cached" && pedido.mode !== "same-origin") return;

    evento.respondWith(
      fetch(pedido)
        .then((respuesta) => {
          if (respuesta.status === 0) return respuesta;   // opaca: no se puede modificar
          const encabezados = new Headers(respuesta.headers);
          encabezados.set("Cross-Origin-Embedder-Policy", "require-corp");
          encabezados.set("Cross-Origin-Opener-Policy", "same-origin");
          encabezados.set("Cross-Origin-Resource-Policy", "cross-origin");
          return new Response(respuesta.body, {
            status: respuesta.status,
            statusText: respuesta.statusText,
            headers: encabezados,
          });
        })
        .catch((e) => new Response(String(e), { status: 502 }))
    );
  });

} else if (!window.crossOriginIsolated && "serviceWorker" in navigator) {
  // ------------------------------------------------------ corriendo en la página

  const miUrl = document.currentScript.src;
  // Una sola recarga por pestaña: si igual no alcanza, se sigue sin memoria compartida.
  const YA = "pseudo:coi-recargado";

  const recargarUnaVez = () => {
    try {
      if (sessionStorage.getItem(YA)) return;
      sessionStorage.setItem(YA, "1");
    } catch (_) { return; }   // sin sessionStorage no arriesgamos un bucle de recargas
    window.location.reload();
  };

  // Recién instalado, el service worker todavía no controla esta pestaña: los
  // encabezados empiezan a aplicarse en la carga siguiente. Por eso se espera a que
  // tome el control (clients.claim() dispara 'controllerchange') y ahí se recarga.
  navigator.serviceWorker.addEventListener("controllerchange", recargarUnaVez);

  navigator.serviceWorker.register(miUrl).then((registro) => {
    // Ya estaba activo de una visita anterior pero no controla esta pestaña.
    if (registro.active && !navigator.serviceWorker.controller) recargarUnaVez();
  }).catch(() => { /* se sigue en modo datos precargados */ });
}
