/*!
 * AriaDemo.montar — interfaz lista para pegar en cualquier landing.
 *
 * Se sirve en /demo/aria/widget.js, que YA INCLUYE el cliente: un solo script.
 *
 *   <div id="aria"></div>
 *   <script src="https://TU-BACKEND/demo/aria/widget.js"></script>
 *   <script>AriaDemo.montar("#aria", { code: "..." });</script>
 *
 * Opciones: code, titulo, subtitulo, etiqueta, boton, nota.
 * Todo el CSS vive bajo .aria-demo y usa variables, asi que la landing puede
 * reestilizarlo sin tocar este archivo:
 *   .aria-demo { --aria-azul:#000; --aria-verde:#0f0; }
 * Si necesitas control total del diseno, usa cliente.js y dibuja tu propia UI.
 */
(function (global) {
  "use strict";

  var CSS = [
    ".aria-demo{--aria-azul:#1d3056;--aria-verde:#3baa98;--aria-tinta:#1a1a2e;",
    "--aria-gris:#6b7280;--aria-borde:#e5e7eb;--aria-fondo:#fff;",
    "font:16px/1.5 system-ui,-apple-system,'Segoe UI',sans-serif;color:var(--aria-tinta);",
    "background:var(--aria-fondo);border:1px solid var(--aria-borde);border-radius:14px;",
    "padding:20px;box-sizing:border-box}",
    ".aria-demo *{box-sizing:border-box}",
    ".aria-demo h3{font-size:20px;margin:0 0 4px}",
    ".aria-demo .aria-sub{color:var(--aria-gris);margin:0 0 18px;font-size:14px}",
    ".aria-demo label{display:block;font-size:13px;font-weight:600;margin:0 0 6px}",
    ".aria-demo input{width:100%;padding:11px 13px;border:1px solid var(--aria-borde);",
    "border-radius:9px;font-size:16px;font-family:inherit}",
    ".aria-demo input:focus{outline:2px solid var(--aria-verde);outline-offset:-1px;border-color:transparent}",
    ".aria-demo button{width:100%;margin-top:14px;padding:13px;border:0;border-radius:9px;",
    "background:var(--aria-azul);color:#fff;font-size:16px;font-weight:600;font-family:inherit;cursor:pointer}",
    ".aria-demo button[disabled]{opacity:.5;cursor:default}",
    ".aria-demo button.aria-colgar{background:#b91c1c}",
    ".aria-demo .aria-estado{display:flex;align-items:center;gap:9px;margin-top:14px;",
    "font-size:14px;color:var(--aria-gris)}",
    ".aria-demo .aria-punto{width:9px;height:9px;border-radius:50%;background:#cbd5e1;flex:none}",
    ".aria-demo .aria-punto.on{background:var(--aria-verde);",
    "box-shadow:0 0 0 0 rgba(59,170,152,.6);animation:aria-pulso 1.6s infinite}",
    "@keyframes aria-pulso{70%{box-shadow:0 0 0 9px rgba(59,170,152,0)}",
    "100%{box-shadow:0 0 0 0 rgba(59,170,152,0)}}",
    ".aria-demo .aria-chat{margin-top:16px;display:flex;flex-direction:column;gap:9px;",
    "max-height:46vh;overflow-y:auto}",
    ".aria-demo .aria-t{padding:9px 13px;border-radius:13px;max-width:82%;font-size:15px;",
    "white-space:pre-wrap}",
    ".aria-demo .aria-t.aria-ella{background:#eef6f4;color:var(--aria-azul);align-self:flex-start;",
    "border-bottom-left-radius:4px}",
    ".aria-demo .aria-t.aria-yo{background:var(--aria-azul);color:#fff;align-self:flex-end;",
    "border-bottom-right-radius:4px}",
    ".aria-demo .aria-nota{margin:16px 0 0;font-size:12px;color:var(--aria-gris);text-align:center}"
  ].join("");

  var ERRORES = {
    "sin-microfono": "No pudimos acceder al microfono.",
    "ocupado": "La demo esta ocupada. Intente en un minuto.",
    // Textos que manda el backend al cerrar (1008 y 1013).
    "demo ocupada": "La demo esta ocupada. Intente en un minuto.",
    "cupo diario agotado": "La demo alcanzo su limite de hoy. Vuelva manana.",
    "origen no autorizado": "Esta pagina no esta autorizada para la demo.",
    "codigo invalido": "El codigo de acceso no es valido.",
    "rechazado": "La demo rechazo la conexion.",
    "conexion": "Error de conexion.",
    "audio-8khz-no-soportado": "Su navegador no soporta el audio de la demo.",
    "navegador-no-soportado": "Su navegador no soporta la demo."
  };

  function css() {
    if (document.getElementById("aria-demo-css")) return;
    var e = document.createElement("style");
    e.id = "aria-demo-css";
    e.textContent = CSS;
    document.head.appendChild(e);
  }

  function montar(sel, opts) {
    opts = opts || {};
    var raiz = (typeof sel === "string") ? document.querySelector(sel) : sel;
    if (!raiz) throw new Error("AriaDemo.montar: no encontre " + sel);
    css();
    raiz.classList.add("aria-demo");
    raiz.innerHTML =
      '<h3></h3><p class="aria-sub"></p>' +
      '<div class="aria-form"><label></label><input type="text" autocomplete="given-name">' +
      '<button class="aria-ir"></button></div>' +
      '<div class="aria-estado"><span class="aria-punto"></span><span class="aria-txt"></span></div>' +
      '<div class="aria-chat"></div><p class="aria-nota"></p>';

    var $ = function (c) { return raiz.querySelector(c); };
    $("h3").textContent = opts.titulo || "Hablar con Aria";
    $(".aria-sub").textContent = opts.subtitulo ||
      "Demostracion. Aria lo llama por una cuota pendiente que es ficticia.";
    $("label").textContent = opts.etiqueta || "¿Como se llama?";
    $("input").placeholder = opts.placeholder || "Su nombre";
    $(".aria-ir").textContent = opts.boton || "Hablar con Aria";
    $(".aria-nota").textContent = opts.nota ||
      "Necesita microfono. Use audifonos para evitar eco.";
    $(".aria-txt").textContent = "Listo";

    var sesion = null, ultimo = null;

    function estado(txt, on) {
      $(".aria-txt").textContent = txt;
      $(".aria-punto").classList.toggle("on", !!on);
    }

    function burbuja(quien, texto) {
      var chat = $(".aria-chat");
      if (quien === ultimo && chat.lastChild) {
        chat.lastChild.textContent += " " + texto;
      } else {
        var d = document.createElement("div");
        d.className = "aria-t " + (quien === "aria" ? "aria-ella" : "aria-yo");
        d.textContent = texto;
        chat.appendChild(d);
        ultimo = quien;
      }
      chat.scrollTop = chat.scrollHeight;
    }

    function reposo() {
      var b = raiz.querySelector(".aria-colgar");
      if (b) b.remove();
      $(".aria-form").style.display = "";
      $(".aria-ir").disabled = false;
      sesion = null;
    }

    function arrancar() {
      var nombre = $("input").value.trim();
      if (!nombre) { $("input").focus(); return; }
      $(".aria-ir").disabled = true;
      ultimo = null;
      $(".aria-chat").innerHTML = "";
      estado("Pidiendo microfono...");

      sesion = global.AriaDemo.conectar({ nombre: nombre, code: opts.code, base: opts.base });

      sesion.onEstado = function (e) {
        if (e === "conectando") {
          estado("Conectando con Aria...", true);
          $(".aria-form").style.display = "none";
          var b = document.createElement("button");
          b.textContent = "Colgar";
          b.className = "aria-colgar";
          b.onclick = function () { sesion.colgar(); };
          $(".aria-form").parentNode.insertBefore(b, $(".aria-form").nextSibling);
        } else if (e === "hablando") {
          estado("En linea con Aria", true);
        } else if (e === "fin") {
          if ($(".aria-txt").textContent.indexOf("No ") !== 0) estado("Llamada terminada");
          reposo();
        }
      };
      sesion.onSubtitulo = burbuja;
      sesion.onError = function (motivo) {
        estado(ERRORES[motivo] || "No se pudo iniciar la demo.");
        reposo();
      };
    }

    $(".aria-ir").onclick = arrancar;
    $("input").addEventListener("keydown", function (e) {
      if (e.key === "Enter") arrancar();
    });

    return { arrancar: arrancar, colgar: function () { if (sesion) sesion.colgar(); } };
  }

  global.AriaDemo = global.AriaDemo || {};
  global.AriaDemo.montar = montar;
})(window);
