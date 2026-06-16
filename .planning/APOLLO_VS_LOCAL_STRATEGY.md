# Apollo.io: Inspiración vs Consumo - Análisis para Mercado Colombiano

## Resumen Ejecutivo

**Conclusión:** Consumir Apollo.io como servicio es mala idea para Colombia. Construir un equivalente LOCAL inspirado en Apollo es la estrategia correcta.

---

## ¿Por Qué Apollo.io NO Funciona en Colombia?

### 1. **Cobertura de Datos**
| Aspecto | Apollo.io | Colombia Local |
|--------|-----------|-----------------|
| **Enfoque** | US/Europa/tier-1 ciudades | Colombia urbana + ciudades intermedias |
| **Actualización** | Mensual/trimestral | Daily (Google Maps, directorios) |
| **Localidad** | Agregador global | Datos regionales frescos |
| **Cobertura legal** | GDPR compliance | Derecho colombiano |
| **Precio** | $49-900/mes persona | Custom (build vs buy) |

**Problema:** Apollo tiene cobertura muy baja en Colombia. Las empresas pequeñas/medianas (target de seguros) no están indexadas en Apollo.

### 2. **Modelo de Negocio Incompatible**
- **Apollo:** Vende subscripción a individuos ($49-900/mes)
- **Tú:** Necesitas leads BARATOS en volumen para brokers de seguros
- **Cálculo:** Si Apollo cobra $100/mes × 50 brokers = $5,000/mes costo fijo
- **ROI:** Broker necesita vender 1-2 pólizas/mes para justificar costo de data

**Problema:** No es económicamente viable pagarle a Apollo cuando puedes generar leads más baratos con data local.

### 3. **Fuentes de Datos Disponibles en Colombia (GRATIS o BARATO)**

```
TIER 1: Públicas + Legales
├─ RUES (Registro Único Empresarial)    [Gratis, API, actualizado diario]
├─ DIAN (Declarantes impuestos)         [Parcial, via terceros]
├─ Cámaras de Comercio                  [Gratis web, algunos cobran API]
├─ Google Maps / Serper                 [Ya lo usas]
├─ LinkedIn (scraping legal)            [Costo marginal]
└─ Directorios 411 colombianos          [Gratis, noisy]

TIER 2: Scrapeables (Legal)
├─ Finca Raíz / Metrocuadrado           [Arrendamiento]
├─ SECOP (compras gobierno)             [Empresas que venden a estado]
├─ Fincaraiz Empresarial                [Locales comerciales]
├─ Páginas amarillas Colombia           [Antiguas pero accesibles]
└─ Directorios sectoriales              [Por industria]

TIER 3: APIs + Observables
├─ Google Trends (intención de compra)  [Gratis]
├─ LinkedIn Job Postings (hiring signal) [Scrapeado]
└─ Tax records via terceros             [Bajo costo]
```

**Oportunidad:** Implementar un "Apollo equivalente" con datos colombianos = más relevante + más barato.

---

## Arquitectura Inspirada en Apollo (Pero Local)

### Apollo's Genius (Qué Copiar)

1. **Signal Aggregation Pipeline**
   ```
   Multiple Sources → Unified Schema → Deduplication → Enrichment → API
   ```

2. **Contact Enrichment Model**
   ```python
   Lead = {
      company: CompanyProfile,
      contacts: [ContactSignal],      # emails + names + titles
      signals: [BehaviorSignal],      # hiring, funding, tech stack
      metadata: EnrichmentMetadata,   # confidence scores + freshness
   }
   ```

3. **Matching Engine**
   ```
   User Query (sector, ciudad, tamaño) → Filter Leads → Rank by Relevance
   ```

---

## Estrategia: Construir Apollo Local Colombiano

### Phase A: Data Sources Colombianas (2 semanas)

**Objetivo:** Crear pipeline que integre 5 fuentes locales en un schema unificado

```
┌─ RUES Scraper (API → MongoDB)
│  └─ Daily cron: Empresa legalmente constitida + info DIAN
│
├─ Google Maps Enricher (usando Serper)
│  └─ Already doing this: contacto + ubicación + horarios
│
├─ Finca Raíz Scraper (para arrendamiento vertical)
│  └─ Inquilino actual → likely cobranza target
│
├─ LinkedIn Signal Extractor
│  └─ Job postings + employee growth = hiring signal
│
└─ Cámaras de Comercio Aggregator
   └─ Afiliación + certificados + historiales
```

**Output:** `SignalLead` unificado (igual que Apollo devuelve leads):

```python
@dataclass
class SignalLead:
    # Identidad
    empresa_id: str                    # RUES + Google ID
    razon_social: str
    nit: str
    
    # Ubicación
    ciudad: str
    direccion: str
    lat_lng: tuple
    
    # Decisores
    decisores: List[ContactSignal]     # name + email + title + confidence
    
    # Señales de relevancia
    tamaño_empresa: str                # 1-10, 11-50, 51-200, 200+
    sector_principal: str              # CIIU code + descripción
    ingresos_anuales: Optional[float]  # De DIAN si disponible
    estado_tributario: str             # Activo, Suspendido, etc
    
    # Señales de compra
    hiring_signal: Optional[bool]      # Has job postings in last 30 days
    tech_stack: Optional[List[str]]    # Observado en LinkedIn/web
    
    # Metadata
    fuentes: List[str]                 # ['RUES', 'Google', 'LinkedIn']
    confianza: float                   # 0-100
    fecha_actualizacion: datetime
    
    # Para seguros: datos relevantes
    tiene_empleados: bool              # Para desempleo
    tipo_propiedad: str                # Para arrendamiento
    actividad_comercial: str           # Para empresarial
```

---

## Costo-Beneficio: Build vs Buy Apollo

| Factor | Apollo.io | Build Local |
|--------|-----------|-------------|
| **Setup** | $0 | 2 semanas (1 dev) |
| **Costo mensual** | $5,000 (50 brokers × $100) | $200-500 (infra + scraping) |
| **Relevancia datos** | 30% en Colombia | 90%+ |
| **Actualización** | Mensual | Diaria |
| **Control** | 0% | 100% |
| **IP colombiano** | Sí | Sí |
| **Escala** | Limitado a Apollo | Ilimitado |
| **Diferenciación competitiva** | Ninguna (todos usan Apollo) | **Única ventaja local** |
| **Tiempo ROI** | Inmediato | 3-4 meses |

**Veredicto:** BUILD > BUY (en Colombia)

---

## Roadmap: Apollo Local Colombiano

### **Fase 1: Core Data Pipeline (2 semanas)**
1. RUES scraper + daily refresh
2. Google Maps enrichment (ya exists)
3. LinkedIn signal extraction
4. Unified `SignalLead` dataclass
5. Deduplication engine (same company, multiple sources)

### **Fase 2: Matching Engine (1 semana)**
1. Query builder: sector × ciudad × tamaño
2. Ranker: confidence score × freshness
3. API endpoint: `/api/signals/search?vertical=desempleo&ciudad=Bogota`

### **Fase 3: Integration en Architecture (1 semana)**
1. Wire signal sources into discovery cascade
2. Replace "Google Maps only" with "Google + RUES + signals"
3. Ranking logic: prefer RUES certified > Google > LinkedIn

### **Fase 4: Vertical-Specific Logic (1 semana)**
1. **Desempleo:** empresa_size >= 50 + hiring_signal = true
2. **Arrendamiento:** tipo_propiedad = 'local comercial' + activo
3. **Empresarial:** RUES data + ingresos + sector

---

## Inspiración de Apollo: Qué Llevar a tu Arquitectura

```python
# 1. Signal aggregation pattern
class SignalSourceRegistry:
    sources: Dict[str, SignalSource]  # 'rues', 'google', 'linkedin'
    
    async def aggregate(query: SearchQuery) -> List[SignalLead]:
        # Run all sources in parallel
        # Merge + deduplicate + rank
        # Return top N by relevance

# 2. Enrichment async pattern
class SignalEnricher:
    async def enrich_lead(lead_id: str) -> EnrichedLead:
        # Fetch from multiple sources
        # Validate contact info
        # Score confidence
        
# 3. Deduplication logic
class SignalDeduplicator:
    # Same company: match by NIT + razon_social_distance
    # Same contact: match by email + phone
    # Return canonical lead + source list
```

---

## Decisión: ¿Construyes o Compras Apollo?

**Si es DESEMPLEO vertical:**
- RUES data suficiente
- Google Maps señales
- LinkedIn hiring signals
- **BUILD = 2 semanas, ROI = 3-4 meses**

**Si es ARRENDAMIENTO vertical:**
- Finca Raíz scraper
- Google Maps
- Cámaras de Comercio
- **BUILD = 2 semanas, ROI = 2-3 meses**

**Si es EMPRESARIAL vertical:**
- RUES + DIAN data
- Tax records via terceros
- LinkedIn company intelligence
- **BUILD = 3 semanas, ROI = 3-4 meses**

**TU VENTAJA:** En 4 semanas tienes un "Apollo Colombiano" que:
- ✅ No tienes que pagar $100k/año a Apollo
- ✅ Datos más frescos que Apollo (diario vs mensual)
- ✅ IP local (cumples regulaciones colombianas)
- ✅ Diferenciación: "datos públicos colombianos" vs genéricos
- ✅ Escalable sin límites de seats de Apollo

---

## Recomendación Final

**No consumas Apollo. Inspírate en su arquitectura y construye tu propia "Signal Lead Pipeline" para Colombia.**

El diferenciador competitivo es: **Tienes fuentes de datos públicas colombianas que Apollo no tiene acceso.**

¿Quieres que diseñe el SPEC.md para "Phase: Signal Sources Colombianas"?
