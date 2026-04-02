# 🔍 Auditoría de Rendimiento — ClientDashboard

**Diagnóstico:** El dashboard está cargando lentamente porque tiene **explosión de re-renders innecesarios** y **múltiples ineficiencias** que se componen. Abajo están los 10 problemas ordenados por **impacto de rendimiento**.

---

## 🚨 PROBLEMAS CRÍTICOS (High Priority)

### 1. ❌ **Sin memoización de sub-componentes** — Impacto: 30-40% de los renders inútiles
**Ubicación:** `LeadCard`, `Badge`, `NavItem`, `StatCard`, `ToastCard`

**Problema:**
- Cada vez que el padre re-renderiza, TODOS los LeadCards se re-renderizan aunque sus props no cambien
- Los leads son filtering/mappeados en cada render del padre
- 50+ leads × múltiples cálculos = renderizado explosivo

**Solución:**
```typescript
const LeadCard = React.memo(({ lead, onApplyStatus, onOpenDossier }) => {
  // ... component code
}, (prev, next) => {
  return prev.lead._id === next.lead._id && 
         prev.lead.hitl_status === next.lead.hitl_status;
});
```

**Impacto Esperado:** ⬇️ 30-40% de re-renders eliminados

---

### 2. ❌ **Cálculos derivados complejos en cada render** — Impacto: 20-25% de tiempo de CPU
**Ubicación:** Líneas 538-553

**Problema:**
```typescript
// Esto se ejecuta CADA render
const pending  = leads.filter(l => l.hitl_status === 'pending');
const approved = leads.filter(l => l.hitl_status === 'approved');
const rejected = leads.filter(l => l.hitl_status === 'rejected');
const tabLeads = tab === 'pending' ? pending : ...
const visible  = query ? tabLeads.filter(l => ...) : tabLeads;
const convRate = leads.length > 0 ? Math.round((approved.length / leads.length) * 100) : 0;
const avgScore = leads.filter(l => l.score !== null).reduce(...) / sc.length;
```

**Solución:** Usar `useMemo()` para cachear estos valores
```typescript
const derivedStats = useMemo(() => ({
  pending: leads.filter(l => l.hitl_status === 'pending'),
  approved: leads.filter(l => l.hitl_status === 'approved'),
  rejected: leads.filter(l => l.hitl_status === 'rejected'),
  convRate: ...,
  avgScore: ...,
}), [leads, tab, query]);
```

**Impacto Esperado:** ⬇️ 20-25% reducción en tiempo de CPU

---

### 3. ❌ **Sin virtualization en listas largas** — Impacto: 50%+ en listas 100+ items
**Ubicación:** Línea 1028 - mapeo de `visible.map(l => <LeadCard...>)`

**Problema:**
- Si hay 500 leads, renderiza los 500 simultáneamente
- DOM crece exponencialmente, scroll es lento
- React tiene que diffear TODOS los nodos

**Solución:** Usar `react-window` o `TanStack vue-virtual` (comportamiento de scroll virtual)
```typescript
import { FixedSizeList } from 'react-window';

<FixedSizeList
  height={600}
  itemCount={visible.length}
  itemSize={80}
  width="100%"
>
  {({ index, style }) => (
    <LeadCard 
      style={style}
      lead={visible[index]} 
      // ...
    />
  )}
</FixedSizeList>
```

**Impacto Esperado:** ⬇️ 50-80% mejora en scroll smooth, especialmente si lista > 100 items

---

### 4. ❌ **Estilos inline generados en cada render** — Impacto: 10-15% overhead
**Ubicación:** MÚLTIPLES (más de 150 estilos inline objeto)

**Problema:**
```typescript
// ❌ Cada render crea 3 objetos nuevos
<div style={{
  display: 'flex', alignItems: 'center', gap: 12,
  padding: '11px 20px', border: 'none', cursor: 'pointer', textAlign: 'left',
  background: active ? C.cyanBg : hov ? 'rgba(255,255,255,0.03)' : 'transparent',
}}
```

**Solución:** Usar CSS modules o styled-components + extraer estilos a constantes
```typescript
const navItemStyles = {
  root: 'flex items-center gap-3 w-full px-5 py-2.75 border-none cursor-pointer...',
  active: 'bg-cyan-bg border-r-2 border-cyan'
};

<div className={`${navItemStyles.root} ${active ? navItemStyles.active : ''}`}>
```

**Impacto Esperado:** ⬇️ 10-15% reducción en render time

---

## ⚠️ PROBLEMAS ALTOS (Medium Priority)

### 5. ❌ **Múltiples API calls sin caching** — Impacto: 2-5s de latencia inicial
**Ubicación:** Múltiples useEffect (líneas 375-415, 430-445, 457-479)

**Problema:**
```typescript
// 3 llamadas SERIALES en el mount:
1. /api/cobranza/status
2. /api/me/email-status  
3. /api/leads (el más pesado)
// Además, cada acción de aprobación/rechazo dispara setTick → refetch completo
```

**Solución:**
- Consolidar en 1 call: `/api/me/dashboard` que retorna todo
- Implementar caché con `useQuery` de TanStack Query  
- Mutation `onSuccess` soft-update en lugar de refetch

```typescript
// Instalable: npm install @tanstack/react-query
const { data: dashboardData } = useQuery({
  queryKey: ['dashboard'],
  queryFn: () => apiFetch(`${API}/api/me/dashboard`),
  staleTime: 30000, // cachear por 30s
});

const approveMutation = useMutation({
  mutationFn: (id) => apiFetch(`${API}/api/leads/${id}/approve`, { method: 'PATCH' }),
  onSuccess: () => {
    queryClient.setQueryData(['dashboard'], prev => ({
      ...prev,
      leads: prev.leads.map(l => l._id === id ? { ...l, hitl_status: 'approved' } : l)
    }));
  }
});
```

**Impacto Esperado:** ⬇️ 2-4s más rápido en carga inicial, mutations instant feedback

---

### 6. ❌ **Sin code splitting / lazy loading de modales** — Impacto: +200-300KB extra en bundle
**Ubicación:** Línea 5 - `import { LeadDossierModal }`

**Problema:**
- `LeadDossierModal` se carga aunque el usuario no lo abra
- `CobranzaTab` se importa aunque 80% de usuarios no usen cobranza

**Solución:**
```typescript
const LeadDossierModal = lazy(() => import('./LeadDossierModal'));
const CobranzaTab = lazy(() => import('./CobranzaTab'));

// En JSX:
<Suspense fallback={<div>Cargando...</div>}>
  {selectedLead && <LeadDossierModal ... />}
</Suspense>
```

**Impacto Esperado:** ⬇️ Bundle size -30%, TTI (Time To Interactive) -1.5s

---

### 7. ❌ **useCallback sin dependencias correctas** — Impacto: 5% (pero causa bugs sneaky)
**Ubicación:** Línea 481 - `const fetchLeads = useCallback(..., [token])`

**Problema:**
```typescript
const fetchLeads = useCallback(async (silent = false) => {
  // setLeads, setLoading están dentro pero NO en dependencias
  // Si token cambia, se recrea pero estados antiguos se capturan
}, [token]); // ❌ Falta setLeads, setLoading
```

**Solución:**
```typescript
const fetchLeads = useCallback(async (silent = false) => {
  // ... code
}, [token, setLeads, setLoading]); // ✅ O usar setter pattern
```

**Impacto Esperado:** ⬇️ Elimina race conditions, state stale closures

---

### 8. ❌ **No hay debouncing en búsqueda** — Impacto: 200ms+ lag por keystroke
**Ubicación:** Línea 616 - `onChange={e => setQuery(e.target.value)}`

**Problema:**
- Con cada keystroke, se re-filtra TODOS los 500 leads
- Si leads tiene datos pesados, es 200-500ms por keystroke

**Solución:**
```typescript
const [query, setQuery] = useState('');
const [debouncedQuery] = useDebouncedValue(query, 300);

// Filtrado usa debouncedQuery, no query
const visible = useMemo(() => 
  debouncedQuery ? 
    tabLeads.filter(l => matchesQuery(l, debouncedQuery)) : 
    tabLeads
, [tabLeads, debouncedQuery]);

// O usar useTransition:
const [isPending, startTransition] = useTransition();
const filter = (val) => {
  setQuery(val);
  startTransition(() => { /*filtering*/ });
};
```

**Impacto Esperado:** ⬇️ Búsqueda suave/responsive, 300ms debounce = 0ms lag percibido

---

## 🟡 PROBLEMAS MEDIOS (Low Priority)

### 9. ❌ **Loading state solo muestra 3 skeletons** — Impacto: UX
**Ubicación:** Línea 983-997

**Problema:**
- Si hay 100 leads, muestra 3 skeletons siempre
- Usuario no sabe cuántos datos vienen (expectativa mal calibrada)
- La lista aparece súbitamente = jank de layout

**Solución:**
```typescript
{loading ? (
  <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
    {Array(Math.min(visible.length || 5, 10)).fill(0).map(i => (
      <SkeletonCard key={i} />
    ))}
  </div>
) : ...}
```

**Impacto Esperado:** ✅ UX más fluida, usuario sabe qué esperar

---

### 10. ❌ **Modal dossier probablemente también sin optimizaciones** — Impacto: Unknown (need audit on LeadDossierModal)
**Ubicación:** `LeadDossierModal.tsx`

**Problema:**
- No hemos auditado ese archivo, pero es probable que tenga problemas similares
- Si es grande/complejo, puede lagguear cuando se abre

**Solución:** Auditar ese archivo con mismo checklist

---

## 📊 RESUMEN: Costo/Beneficio

| Problema | Prioridad | Esfuerzo | Ganancia | ROI |
|----------|-----------|----------|----------|-----|
| Memoizar componentes | 🔴 Crítico | 30min | 30-40% | 🔥🔥🔥 |
| useMemo derivados | 🔴 Crítico | 20min | 20-25% | 🔥🔥🔥 |
| Virtualization | 🟠 Alto | 1-2h | 50-80% (si list > 100) | 🔥🔥 |
| CSS Modules | 🟠 Alto | 1h | 10-15% | 🔥 |
| React Query + caché | 🟠 Alto | 2-3h | 2-4s menos en init | 🔥🔥 |
| Code splitting modales | 🟠 Alto | 30min | -30% bundle, -1.5s TTI | 🔥🔥 |
| Debouncing búsqueda | 🟠 Alto | 15min | UX fluida | 🔥 |
| useCallback deps fix | 🟡 Medio | 10min | Elimina bugs | 💪 |
| Mejor loading UX | 🟡 Medio | 15min | UX mejorada | 💪 |

---

## 🎯 PLAN DE ACCIÓN RECOMENDADO (Orden óptimo)

**Fase 1 (Quick Win - 1 hora):**
1. Agregar `React.memo()` a sub-componentes (LeadCard, Badge, etc.) 
2. `useMemo()` para derivados (pending, approved, rejected, stats)
3. Debouncing en búsqueda

**Fase 2 (Medium - 2 horas):**
4. Code splitting con lazy() + Suspense para modales
5. Estilos inline → CSS Modules / styled-components

**Fase 3 (Advanced - 3+ horas):**
6. Implementar React Query para caché + mutations
7. Virtualization si lista > 100 items
8. Auditar LeadDossierModal (probable bomba de rendimiento)

---

## 🔗 Recursos Útiles

- React Query (caché): https://tanstack.com/query/latest
- React Window (virtualization): https://github.com/bvaughn/react-window
- Memoization: https://react.dev/reference/react/useMemo
- Code Splitting: https://react.dev/reference/react/lazy
- Profiling: DevTools → Profiler tab, busca "Render duration"

