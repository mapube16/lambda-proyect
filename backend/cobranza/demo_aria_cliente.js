/*!
 * AriaDemo — cliente de voz, sin interfaz.
 *
 * Habla el MISMO protocolo media-stream de Twilio que usa el motor de voz en
 * produccion: {"event":"media", media:{payload:<base64 mulaw 8 kHz>}}. Por eso
 * la demo no duplica nada del motor — misma voz, mismo prompt, misma persona.
 *
 *   <script src="https://TU-BACKEND/demo/aria/cliente.js"></script>
 *   <script>
 *     var s = AriaDemo.conectar({ nombre: "Juan", code: "..." });
 *     s.onEstado    = function(e){ ... };            // ver ESTADOS
 *     s.onSubtitulo = function(quien, txt){ ... };   // "aria" | "visitante"
 *     s.onError     = function(motivo){ ... };
 *     boton.onclick = function(){ s.colgar(); };
 *   </script>
 *
 * ESTADOS: "microfono" -> "conectando" -> "hablando" -> "fin"
 */
(function (global) {
  "use strict";

  // De donde salio este script: asi el cliente sabe a que backend conectarse
  // aunque la landing viva en otro dominio.
  var BASE = (function () {
    var s = document.currentScript;
    try { return new URL(".", s.src).href; } catch (e) { return "/demo/aria/"; }
  })();

  // ── G.711 mu-law, el formato de la linea telefonica ──────────────────────
  var BIAS = 0x84, CLIP = 32635;
  var EXPLUT = [0,0,1,1,2,2,2,2,3,3,3,3,3,3,3,3,
  4,4,4,4,4,4,4,4,4,4,4,4,4,4,4,4,
  5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,
  6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,
  6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,6,
  7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,
  7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,
  7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,
  7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7,7];

  function enc(s) {                       // int16 -> mu-law
    var sign = (s >> 8) & 0x80;
    if (sign) s = -s;
    if (s > CLIP) s = CLIP;
    s += BIAS;
    var e = EXPLUT[(s >> 7) & 0xff];
    var m = (s >> (e + 3)) & 0x0f;
    return (~(sign | (e << 4) | m)) & 0xff;
  }

  var DEC = new Int16Array(256);          // mu-law -> int16 (tabla, una vez)
  for (var i = 0; i < 256; i++) {
    var u = ~i & 0xff;
    var t = (((u & 0x0f) << 3) + BIAS) << ((u & 0x70) >> 4);
    DEC[i] = (u & 0x80) ? (BIAS - t) : (t - BIAS);
  }

  function conectar(opts) {
    opts = opts || {};
    var base = opts.base || BASE;
    var ses = {
      estado: "microfono",
      onEstado: null, onSubtitulo: null, onError: null,
      colgar: colgar
    };

    var ws = null, ctx = null, mic = null, proc = null, pista = null;
    var fuentes = [], proximo = 0, sonando = false, cerrado = false;

    function avisar(e) {
      ses.estado = e;
      if (ses.onEstado) { try { ses.onEstado(e); } catch (x) {} }
    }
    function fallar(motivo) {
      if (cerrado) return;
      if (ses.onError) { try { ses.onError(motivo); } catch (x) {} }
      limpiar();
      avisar("fin");
    }

    function reproducir(b64) {
      var bin = atob(b64), n = bin.length;
      var buf = ctx.createBuffer(1, n, 8000), ch = buf.getChannelData(0);
      for (var k = 0; k < n; k++) ch[k] = DEC[bin.charCodeAt(k)] / 32768;
      var src = ctx.createBufferSource();
      src.buffer = buf;
      src.connect(ctx.destination);
      // +0.12 s de colchon: el audio llega en rafaga y sin esto se entrecorta.
      var t = Math.max(ctx.currentTime + 0.12, proximo);
      src.start(t);
      proximo = t + buf.duration;
      fuentes.push(src);
      src.onended = function () {
        var j = fuentes.indexOf(src);
        if (j >= 0) fuentes.splice(j, 1);
      };
    }

    function vaciar() {
      for (var k = 0; k < fuentes.length; k++) { try { fuentes[k].stop(); } catch (x) {} }
      fuentes = [];
      proximo = 0;
    }

    function limpiar() {
      if (cerrado) return;
      cerrado = true;
      vaciar();
      try { if (proc) { proc.onaudioprocess = null; proc.disconnect(); } } catch (x) {}
      try { if (mic) mic.disconnect(); } catch (x) {}
      try { pista.getTracks().forEach(function (t) { t.stop(); }); } catch (x) {}
      try { ctx.close(); } catch (x) {}
    }

    function colgar() {
      try { ws.send(JSON.stringify({ event: "stop" })); } catch (x) {}
      try { ws.close(); } catch (x) {}
    }

    if (!navigator.mediaDevices || !global.WebSocket) {
      setTimeout(function () { fallar("navegador-no-soportado"); }, 0);
      return ses;
    }

    navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true }
    }).then(function (stream) {
      pista = stream;
      avisar("conectando");

      // ponytail: un solo AudioContext a 8 kHz y no hace falta remuestrear.
      // Techo conocido: un navegador que rechace esa tasa necesitaria
      // resampleo manual (no pasa en Chrome/Edge/Safari/Firefox actuales).
      try {
        ctx = new (global.AudioContext || global.webkitAudioContext)({ sampleRate: 8000 });
      } catch (x) {
        return fallar("audio-8khz-no-soportado");
      }
      ctx.resume();

      var q = new URLSearchParams({ nombre: opts.nombre || "" });
      if (opts.code) q.set("code", opts.code);
      var u = new URL("ws", base);
      u.protocol = (u.protocol === "https:") ? "wss:" : "ws:";
      u.search = q.toString();
      ws = new WebSocket(u.href);

      ws.onopen = function () {
        mic = ctx.createMediaStreamSource(stream);
        proc = ctx.createScriptProcessor(512, 1, 1);   // 64 ms @ 8 kHz
        proc.onaudioprocess = function (ev) {
          if (!ws || ws.readyState !== 1) return;
          var f = ev.inputBuffer.getChannelData(0), s = "";
          for (var k = 0; k < f.length; k++) {
            var v = f[k] * 32768;
            v = v > 32767 ? 32767 : (v < -32768 ? -32768 : v);
            s += String.fromCharCode(enc(v | 0));
          }
          ws.send(JSON.stringify({ event: "media", media: { payload: btoa(s) } }));
        };
        var mudo = ctx.createGain();
        mudo.gain.value = 0;
        mic.connect(proc);
        proc.connect(mudo);
        mudo.connect(ctx.destination);
      };

      ws.onmessage = function (e) {
        var m = JSON.parse(e.data);
        if (m.event === "media") {
          if (!sonando) { sonando = true; avisar("hablando"); }
          reproducir(m.media.payload);
        } else if (m.event === "clear") {
          vaciar();                      // barge-in: el visitante interrumpio
        } else if (m.event === "transcript") {
          if (ses.onSubtitulo) {
            try { ses.onSubtitulo(m.role === "agent" ? "aria" : "visitante", m.text); }
            catch (x) {}
          }
        } else if (m.event === "mark") {
          // Twilio devuelve el mark cuando TERMINO de sonar; aqui, cuando se
          // vacia la cola. El motor lo usa para colgar recien tras la despedida.
          var ms = Math.max(0, (proximo - ctx.currentTime) * 1000);
          setTimeout(function () {
            if (ws && ws.readyState === 1) ws.send(e.data);
          }, ms);
        }
      };

      ws.onclose = function (ev) {
        if (ev.code === 1013) return fallar(ev.reason || "ocupado");
        if (ev.code === 1008) return fallar(ev.reason || "rechazado");
        limpiar();
        avisar("fin");
      };
      ws.onerror = function () { fallar("conexion"); };
    }).catch(function () {
      fallar("sin-microfono");
    });

    return ses;
  }

  global.AriaDemo = global.AriaDemo || {};
  global.AriaDemo.conectar = conectar;
  global.AriaDemo.base = BASE;
})(window);
