# Propuesta — Aria Asistencias para DPG Seguros

> Extensión del bot de cobranza (Aria) a un canal de **atención de asistencias**: el asegurado
> escribe o llama, Aria lo identifica, le dice qué póliza tiene, con qué aseguradora, y a qué
> número debe llamar para pedir la asistencia. Además le da recomendaciones prácticas antes de
> que llame.
>
> Fecha: 2026-09-05 · Cliente: DPG Seguros · Preparado por: Landa

---

## 1. El problema que resuelve

Hoy cuando un asegurado de DPG tiene un siniestro o necesita una asistencia (grúa, cerrajero,
plomero, asistencia médica en viaje, etc.) suele llamar a DPG en vez de a la aseguradora.
El equipo de DPG gasta tiempo en una tarea repetitiva: buscar la póliza, decirle con qué
compañía está y darle el teléfono. Fuera de horario, el asegurado no tiene a quién acudir.

Aria ya conoce a esos asegurados (la cartera sincronizada de Softseguros) y ya atiende
llamadas y WhatsApp para cobranza. El salto a asistencias es pequeño y reutiliza todo lo
construido.

## 2. Qué va a poder hacer el asegurado

**Canales:** llamada telefónica y WhatsApp. Mismo número de Aria que hoy usa cobranza.

**Flujo tipo:**

1. El asegurado llama o escribe: "necesito una grúa" / "tengo una emergencia".
2. Aria le pide el número de documento (por teclado en llamada, por texto en WhatsApp).
   Nunca identifica por el número de teléfono desde el que llama, igual que hoy en cobranza.
3. Aria busca sus pólizas vigentes. Si tiene varias, le pregunta cuál (autos, hogar, vida…).
4. Aria le informa: aseguradora, ramo, número de póliza, y **la línea de asistencia de esa
   aseguradora** (nacional, celular, WhatsApp si existe).
5. Aria le da recomendaciones según el tipo de asistencia:
   - Tener a la mano el número de póliza y la cédula.
   - Tomar fotos del vehículo, los daños, la placa o el lugar.
   - No mover el vehículo si hay heridos; llamar primero a emergencias.
   - Guardar facturas o soportes si va a haber reembolso.
6. En WhatsApp, Aria envía además el número como contacto o enlace para marcar con un toque.
7. Si el asegurado lo pide, o si Aria no logra identificarlo, **escala a un asesor de DPG**
   con un resumen del caso (igual que hoy escala en cobranza).

**Lo que Aria NO hace en esta fase:** no radica el siniestro ante la aseguradora, no promete
coberturas ni montos, no interpreta condiciones de la póliza. Solo informa y orienta. Esto
evita responsabilidad legal para DPG y mantiene el alcance acotado.

## 3. Ejemplo de conversación

**WhatsApp**

> Asegurado: Hola, se me varó el carro en la autopista, necesito grúa.
>
> Aria: Hola, soy Aria de DPG Seguros. Con gusto te ayudo. Para ubicar tu póliza, ¿me
> confirmas tu número de cédula?
>
> Asegurado: 1020304050
>
> Aria: Gracias, Carlos. Tu póliza de autos está con **Seguros Bolívar**, póliza
> **AUT-123456**, vigente hasta el 15 de marzo de 2027.
> Para pedir la grúa llama a la línea de asistencia de Bolívar: **#322** desde celular o
> **01 8000 123 322**. Aquí te dejo el contacto para que marques directo.
> Antes de llamar te recomiendo:
> • Tener a la mano tu cédula y el número de póliza AUT-123456.
> • Tomar fotos del carro, la placa y el sitio donde estás.
> • Si hay personas heridas, primero llama al 123.
> ¿Quieres que te comunique con un asesor de DPG?

**Llamada** — mismo contenido, más corto, con la opción de repetir el número o de que Aria
se lo envíe por WhatsApp al terminar la llamada.

## 4. Qué necesitamos de DPG

| Insumo | Para qué | Quién |
|---|---|---|
| Tabla de aseguradoras con líneas de asistencia (teléfono nacional, celular, WhatsApp, horario) | Es la respuesta central de Aria | DPG |
| Recomendaciones por tipo de asistencia (autos, hogar, salud, viaje…) en el tono de DPG | Contenido que Aria dice al asegurado | DPG, Landa propone borrador |
| Criterio de qué pólizas se consideran "vigentes" para asistencias | Evitar dar información de pólizas canceladas | DPG |
| Horario y canal de escalamiento a asesor (WhatsApp interno, extensión) | Fase de escalamiento | DPG |
| Mensaje de descargo ("Aria informa, la cobertura la define la aseguradora") | Protección legal | DPG / jurídico |

## 5. Cómo se construye (anexo técnico)

Todo se apoya en piezas que ya existen en la plataforma:

- **Identificación por documento** — reutiliza el flujo de llamada entrante actual, que ya
  pide la cédula por teclado y resuelve la persona en la cartera sincronizada.
- **Datos de póliza** — la sincronización con Softseguros ya trae aseguradora, ramo, número
  de póliza, estado y vigencia. Hoy solo se sincroniza la cartera por cobrar; para
  asistencias se amplía a **todas las pólizas vigentes** del cliente (mismo endpoint, otro
  filtro).
- **Líneas de asistencia y recomendaciones** — se cargan como documentos en el RAG por
  tenant que ya usa Aria. DPG los puede actualizar sin desarrollo.
- **Voz y WhatsApp** — mismos canales de cobranza. Se agrega una "intención" nueva: si la
  persona habla de asistencia, emergencia o siniestro, Aria entra al flujo de asistencias
  en vez de cobranza.
- **Escalamiento y alertas** — mismo mecanismo actual de escalamiento a asesor y alertas
  al panel.
- **Registro** — cada asistencia queda guardada (quién, qué póliza, qué aseguradora, si se
  escaló) y aparece en el reporte diario que DPG ya recibe.

Cambios nuevos, de menor a mayor:

1. Colección de aseguradoras con líneas de asistencia por tenant (tabla editable desde el
   panel).
2. Sincronización de pólizas vigentes (no solo cuotas por cobrar).
3. Detección de intención "asistencia" en el orquestador de voz y WhatsApp.
4. Prompt y guion de Aria para asistencias (informar, recomendar, escalar; nunca prometer).
5. Envío de contacto/enlace tel: por WhatsApp y opción "te lo mando por WhatsApp" en llamada.
6. Reporte de asistencias atendidas.

## 6. Fases y tiempos

| Fase | Alcance | Duración estimada |
|---|---|---|
| 1. WhatsApp | Identificación, póliza, aseguradora, línea, recomendaciones, escalamiento | 2 semanas |
| 2. Voz | Mismo flujo por llamada, envío del número por WhatsApp al colgar | 1–2 semanas |
| 3. Reportes y ajustes | Reporte diario de asistencias, afinación con casos reales | 1 semana |

Se arranca en WhatsApp porque es más barato de probar, no consume minutos de voz y el
asegurado se queda con el número escrito.

## 7. Indicadores de éxito

- Asistencias atendidas por Aria sin intervención humana (meta inicial: 70 %).
- Tiempo desde que el asegurado escribe hasta que recibe el número: menos de 1 minuto.
- Llamadas de asistencia que llegan a asesores de DPG: reducción medible mes a mes.
- Atención fuera de horario: casos resueltos de noche y fines de semana.

## 8. Riesgos y cómo se manejan

- **Dar información equivocada de aseguradora** — Aria solo lee lo que dice Softseguros y
  siempre cita el número de póliza para que el asegurado verifique.
- **Póliza cancelada o vencida** — Aria lo dice claramente y ofrece pasar con un asesor.
- **Emergencia con heridos** — Aria antepone siempre la línea de emergencias (123) a la
  línea de la aseguradora.
- **Expectativa de cobertura** — descargo explícito: la cobertura la confirma la aseguradora.

## 9. Preguntas abiertas para DPG

1. ¿Las asistencias aplican a todos los ramos o solo a autos y hogar al inicio?
2. ¿Aria puede atender a personas que no aparecen en Softseguros (por ejemplo, un familiar
   que llama por el asegurado)?
3. ¿Se quiere que Aria envíe al asesor de DPG una notificación por cada asistencia, o solo
   cuando escala?
4. ¿Existe ya un documento interno con las líneas de asistencia por aseguradora?
