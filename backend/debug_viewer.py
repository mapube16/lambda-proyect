#!/usr/bin/env python3
"""
debug_viewer.py — Interactive debugger for WhatsApp bot interactions.

Permite ver:
- Payloads completos de webhooks entrantes
- Transiciones de estado de sesión
- Resultados de búsquedas SECOP
- Intentos de enriquecimiento de contactos
- Intentos de envío
- Errores y excepciones
"""
import sys
from datetime import datetime, timedelta
from pathlib import Path

from debug_logger import get_recent_logs, get_logs_for_phone, get_log_summary


def print_header(title: str):
    """Imprime encabezado de sección."""
    print(f"\n{'─' * 80}")
    print(f"  {title}")
    print(f"{'─' * 80}\n")


def print_event(event: dict, indent: int = 0):
    """Imprime un evento de forma legible."""
    i = " " * indent
    
    ts = event.get("timestamp", "?")[:19]
    event_type = event.get("event_type", "?")
    level = event.get("level", "INFO")
    
    # Color por level
    level_colors = {
        "DEBUG": "\033[36m",    # cyan
        "INFO": "\033[32m",     # green
        "WARNING": "\033[33m",  # yellow
        "ERROR": "\033[31m",    # red
    }
    color = level_colors.get(level, "\033[0m")
    reset = "\033[0m"
    
    print(f"{i}{color}[{ts}] {event_type:30} {level:7}{reset}")
    
    # Mostrar campos relevantes
    for key, value in event.items():
        if key not in ("timestamp", "event_type", "level"):
            if isinstance(value, (list, dict)):
                print(f"{i}  {key}: {str(value)[:100]}...")
            else:
                print(f"{i}  {key}: {value}")


def view_recent(limit: int = 50):
    """Muestra los eventos más recientes."""
    print_header(f"📋 Últimos {limit} eventos")
    
    events = get_recent_logs(limit=limit)
    for event in events:
        print_event(event)
        print()


def view_phone(phone: str, limit: int = 50):
    """Muestra interacción completa de un número de teléfono."""
    print_header(f"📱 Conversación de {phone}")
    
    events = get_logs_for_phone(phone, limit=limit)
    
    if not events:
        print(f"❌ No hay eventos para {phone}\n")
        return
    
    print(f"✅ {len(events)} eventos encontrados\n")
    
    # Agrupar por tipo
    by_type = {}
    for event in events:
        event_type = event.get("event_type")
        if event_type not in by_type:
            by_type[event_type] = []
        by_type[event_type].append(event)
    
    # Mostrar resumen
    print("📊 Resumen por tipo de evento:")
    for event_type, evts in sorted(by_type.items()):
        print(f"  • {event_type}: {len(evts)} eventos")
    
    print("\n" + "─" * 80 + "\n")
    
    # Mostrar eventos en orden cronológico inverso (más recientes primero)
    for event in sorted(events, key=lambda x: x.get("timestamp", ""), reverse=True):
        print_event(event)
        print()


def view_summary(hours: int = 1):
    """Muestra resumen de actividad en las últimas N horas."""
    print_header(f"📊 Resumen últimas {hours} hora(s)")
    
    summary = get_log_summary(hours=hours)
    
    print(f"📈 Total eventos: {summary['total_events']}")
    print(f"📱 Números activos: {len(summary['phones'])}")
    if summary['phones']:
        print(f"   {', '.join(summary['phones'][:5])}")
    
    print(f"\n📌 Eventos por tipo:")
    for event_type, count in sorted(summary['events_by_type'].items(), key=lambda x: -x[1])[:10]:
        print(f"  • {event_type}: {count}")
    
    if summary['errors']:
        print(f"\n❌ Errores ({len(summary['errors'])}):")
        for error in summary['errors'][-5:]:
            ts = error['timestamp'][:16]
            phone = error.get('phone', '?')
            msg = error.get('error', '?')[:50]
            print(f"  [{ts}] {phone}: {msg}")
    
    if summary['failed_sends']:
        print(f"\n📤 Envíos fallidos ({len(summary['failed_sends'])}):")
        for send in summary['failed_sends'][-5:]:
            ts = send['timestamp'][:16]
            phone = send.get('phone', '?')
            company = send.get('company', '?')[:30]
            error = send.get('error', '?')
            print(f"  [{ts}] {phone}: {company} → {error}")
    
    if summary['search_queries']:
        print(f"\n🔍 Búsquedas ({len(summary['search_queries'])}):")
        for search in summary['search_queries'][-5:]:
            ts = search['timestamp'][:16]
            sector = search.get('sector', '?')
            ciudad = search.get('ciudad', '?')
            results = search.get('results', 0)
            print(f"  [{ts}] {sector} · {ciudad}: {results} resultados")


def interactive():
    """Menú interactivo."""
    while True:
        print("\n" + "=" * 80)
        print("  🤖 WhatsApp Bot Debug Viewer")
        print("=" * 80)
        print("""
  1. Ver últimos eventos (50)
  2. Ver eventos de un teléfono específico
  3. Ver resumen de actividad (última hora)
  4. Exportar logs a JSON
  5. Ver flujo completo de una conversación
  6. Salir
""")
        
        choice = input("Selecciona opción (1-6): ").strip()
        
        if choice == "1":
            view_recent(limit=50)
        
        elif choice == "2":
            phone = input("Teléfono (ej: +573123528153): ").strip()
            if phone:
                view_phone(phone, limit=100)
        
        elif choice == "3":
            hours_str = input("Horas (default 1): ").strip()
            hours = int(hours_str) if hours_str.isdigit() else 1
            view_summary(hours=hours)
        
        elif choice == "4":
            import json
            events = get_recent_logs(limit=10000)
            output_file = Path(".logs") / f"export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(output_file, "w") as f:
                json.dump(events, f, indent=2, ensure_ascii=False, default=str)
            print(f"\n✅ Exportado a {output_file}")
        
        elif choice == "5":
            phone = input("Teléfono de la conversación: ").strip()
            if phone:
                view_phone(phone, limit=200)
        
        elif choice == "6":
            print("\n👋 Hasta luego!\n")
            break
        
        else:
            print("❌ Opción inválida")


def cli():
    """Interfaz de línea de comandos."""
    if len(sys.argv) < 2:
        interactive()
        return
    
    command = sys.argv[1]
    
    if command == "recent":
        limit = int(sys.argv[2]) if len(sys.argv) > 2 else 50
        view_recent(limit=limit)
    
    elif command == "phone":
        if len(sys.argv) < 3:
            print("Uso: debug_viewer.py phone <+57...>")
            sys.exit(1)
        phone = sys.argv[2]
        limit = int(sys.argv[3]) if len(sys.argv) > 3 else 50
        view_phone(phone, limit=limit)
    
    elif command == "summary":
        hours = int(sys.argv[2]) if len(sys.argv) > 2 else 1
        view_summary(hours=hours)
    
    elif command == "interactive":
        interactive()
    
    else:
        print(f"Comando desconocido: {command}")
        print("""
Uso:
  python debug_viewer.py                          # Modo interactivo
  python debug_viewer.py recent [limit]           # Últimos N eventos
  python debug_viewer.py phone <+57...> [limit]   # Eventos de un teléfono
  python debug_viewer.py summary [hours]          # Resumen de actividad
  python debug_viewer.py interactive              # Menú interactivo
""")
        sys.exit(1)


if __name__ == "__main__":
    cli()
