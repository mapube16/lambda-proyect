📄 Product Requirements Document (PRD): Plataforma de Agentes B2B (Lead Swarm SaaS)
1. Resumen Ejecutivo
Propósito: Desarrollar una plataforma SaaS B2B impulsada por un enjambre de agentes de IA (Aden Hive) que automatiza la prospección, el enriquecimiento de datos y la redacción de correos en frío hiper-personalizados.
Problema a resolver: La prospección manual es lenta, costosa y genérica. Los scrapers tradicionales fallan por bloqueos anti-bot o falta de contexto.
Solución: Un sistema multi-agente que utiliza búsqueda híbrida (Google Maps API + Scraping inteligente con Semantic Chunking), rutado dinámico de LLMs vía OpenRouter y validación humana (HITL) para garantizar leads de alta conversión con un costo operativo marginal.

2. Objetivos del Producto
Automatización de Extracción: Lograr extraer datos de contacto válidos y contexto de negocio del 70% de las empresas objetivo.

Eficiencia de Costos (Unit Economics): Mantener el costo de procesamiento por lead por debajo de un umbral rentable mediante Model Routing y RAG (Semantic Chunking).

Calidad y Seguridad: Cero fugas de información inter-cliente y bloqueo del 100% de los intentos de Prompt Injection.

3. Arquitectura y Stack Tecnológico
Para garantizar escalabilidad, velocidad de desarrollo y una experiencia fluida, el ecosistema se construirá sobre las siguientes tecnologías:

Frontend (Panel de Admin y Cliente): React + Vite. Interfaces rápidas para la visualización en tiempo real del trabajo de los agentes y la aprobación de leads.

Backend & Orquestación: Node.js, sirviendo como puente entre la interfaz, la base de datos y el motor de IA.

Motor Multi-Agente: Aden Hive Framework, encargado de coordinar los Worker Bees (Investigador, Enriquecedor, Redactor, Guardián).

Base de Datos: MongoDB. Su modelo documental (JSON) es ideal para guardar la configuración del enjambre por cliente, el historial de leads y los vectores de chunks semánticos (MongoDB Atlas Vector Search).

Capa de IA: OpenRouter (LiteLLM) para acceder a múltiples modelos (Claude 3.5 Haiku para tareas rápidas, Gemini 1.5 Pro / GPT-4o para razonamiento complejo).

Extracción de Datos: Google Maps Places API (Exploración) y Cheerio/Playwright (Extracción web profunda).

4. Flujo de Usuario y Casos de Uso Core
4.1. El Panel de Administración (Operativa Interna)
Onboarding de Cliente: El administrador llena un formulario con el ICP (Perfil de Cliente Ideal), geografía, competidores y propuesta de valor.

Generación del Enjambre: El sistema guarda este perfil en MongoDB, y la Queen Bee configura la estructura del agente específico para ese cliente.

QA y Staging: Como garantizar la calidad del producto final es innegociable antes de la entrega, los agentes corren un lote de 5 leads de prueba. El equipo de QA revisa la precisión del scraping y el tono del mensaje antes de pasarlo a producción.

4.2. El Panel del Cliente (La Entrega de Valor)
Modo HITL (Human-in-the-loop): El cliente entra a su dashboard, ve una lista de leads procesados con su respectivo borrador de correo hiper-personalizado. Tiene opciones binarias: "Aprobar y Enviar" o "Rechazar (con feedback)".

Dashboard de Métricas: Visualización del ROI (Tokens gastados vs. Leads válidos generados vs. Tasa de respuesta).

5. Requerimientos Funcionales
F1 - Agente Explorador: Capacidad de consultar la API de Google Maps manejando paginación para extraer un listado base de empresas (Nombre, Web, Teléfono).

F2 - Sistema RAG de Extracción: El texto de las webs visitadas debe convertirse a Markdown, dividirse semánticamente y almacenarse como vectores en MongoDB para su recuperación contextual.

F3 - Agente Redactor: Debe inyectar variables (Nombre, Empresa, "Gancho" extraído del blog) en plantillas dinámicas usando el modelo de mayor razonamiento asignado por OpenRouter.

F4 - Model Routing Dinámico: El sistema debe asignar la IA correcta según la tarea para optimizar costos.

6. Requerimientos No Funcionales (Seguridad y Rendimiento)
S1 - Prevención de Prompt Injection: Implementar un "Agente Guardián" en la puerta de entrada que evalúe y sanitice cualquier input manual para evitar manipulación de las instrucciones base.

S2 - Aislamiento de Datos (Multi-Tenant): Los agentes solo tendrán permisos de lectura/escritura en MongoDB limitados al client_id que están procesando en ese momento.

P1 - Resiliencia y Retries: El scraper web debe manejar rotación básica y lógicas de reintento ante errores de timeout (404, 503) sin bloquear el flujo principal.