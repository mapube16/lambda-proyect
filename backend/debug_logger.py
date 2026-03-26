"""
debug_logger.py — Sistema centralizado de logging y persistencia de payloads.

Registra:
- Payloads entrantes/salientes
- Transiciones de estado
- Resultados de búsqueda
- Llamadas de enrichment
- Errores y excepciones
- Tiempos de ejecución

Los logs se persisten en .logs/ como JSONLines para fácil inspección.
"""
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

# Crear directorio de logs
LOGS_DIR = Path(__file__).parent.parent / ".logs"
LOGS_DIR.mkdir(exist_ok=True)

logger = logging.getLogger(__name__)


class PayloadLogger:
    """Registra eventos estructurados con payloads completos."""
    
    def __init__(self, session_name: str = "whatsapp"):
        self.session_name = session_name
        self.log_file = LOGS_DIR / f"{session_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
        self.events = []
    
    def log_event(self, event_type: str, data: dict, level: str = "INFO") -> None:
        """
        Registra un evento estructurado.
        
        Args:
            event_type: Tipo de evento (e.g., "incoming_message", "search_results", "error")
            data: Diccionario con los detalles del evento
            level: Nivel de logging (INFO, DEBUG, WARNING, ERROR)
        """
        event = {
            "timestamp": datetime.now().isoformat(),
            "event_type": event_type,
            "level": level,
            **data
        }
        
        self.events.append(event)
        self._persist(event)
        
        # También loggear en logging estándar
        log_msg = f"[{event_type}] {json.dumps(data, ensure_ascii=False, default=str)}"
        if level == "DEBUG":
            logger.debug(log_msg)
        elif level == "WARNING":
            logger.warning(log_msg)
        elif level == "ERROR":
            logger.error(log_msg)
        else:
            logger.info(log_msg)
    
    def _persist(self, event: dict) -> None:
        """Persiste el evento en JSONL."""
        try:
            with open(self.log_file, "a") as f:
                f.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
        except Exception as e:
            logger.error(f"Failed to persist log event: {e}")
    
    def log_incoming_message(self, phone: str, text: str) -> None:
        """Registra mensaje entrante."""
        self.log_event("incoming_message", {
            "phone": phone,
            "text": text,
            "length": len(text)
        })
    
    def log_session_state(self, phone: str, old_state: str, new_state: str, context: dict) -> None:
        """Registra transición de estado."""
        self.log_event("state_transition", {
            "phone": phone,
            "old_state": old_state,
            "new_state": new_state,
            "context": context
        }, level="DEBUG")
    
    def log_search_query(self, phone: str, sector: str, ciudad: str, results_count: int) -> None:
        """Registra búsqueda en SECOP."""
        self.log_event("search_query", {
            "phone": phone,
            "sector": sector,
            "ciudad": ciudad,
            "results_count": results_count
        })
    
    def log_entity_filtering(self, phone: str, total: int, filtered_out: int, reason: str) -> None:
        """Registra filtrado de entidades."""
        self.log_event("entity_filtering", {
            "phone": phone,
            "total_before": total,
            "filtered_out": filtered_out,
            "total_after": total - filtered_out,
            "reason": reason
        })
    
    def log_enrichment_attempt(self, phone: str, company: str, ciudad: str, success: bool, result: dict) -> None:
        """Registra intento de enriquecimiento de contacto."""
        self.log_event("enrichment_attempt", {
            "phone": phone,
            "company": company,
            "ciudad": ciudad,
            "success": success,
            "email": result.get("email", "N/A"),
            "phone_number": result.get("phone", "N/A"),
            "source": result.get("source", "N/A")
        })
    
    def log_send_attempt(self, phone: str, company: str, channel: str, recipient: str, success: bool, error: Optional[str] = None) -> None:
        """Registra intento de envío."""
        self.log_event("send_attempt", {
            "phone": phone,
            "company": company,
            "channel": channel,
            "recipient": recipient,
            "success": success,
            "error": error
        }, level="WARNING" if not success else "INFO")
    
    def log_error(self, phone: str, error_type: str, error_msg: str, context: dict) -> None:
        """Registra errores."""
        self.log_event("error", {
            "phone": phone,
            "error_type": error_type,
            "error_message": str(error_msg),
            "context": context
        }, level="ERROR")


def get_payload_logger() -> PayloadLogger:
    """Factory para obtener el logger global."""
    if not hasattr(get_payload_logger, "_instance"):
        get_payload_logger._instance = PayloadLogger()
    return get_payload_logger._instance


def get_recent_logs(limit: int = 100) -> list[dict]:
    """Retorna los últimos eventos registrados."""
    all_events = []
    
    # Leer todos los archivos JSONL en orden de creación
    log_files = sorted(LOGS_DIR.glob("*.jsonl"), reverse=True)
    
    for log_file in log_files:
        try:
            with open(log_file, "r") as f:
                for line in f:
                    if line.strip():
                        all_events.append(json.loads(line))
        except Exception as e:
            logger.error(f"Failed to read log file {log_file}: {e}")
    
    # Retornar los últimos N eventos ordenados por timestamp descendente
    return sorted(all_events, key=lambda x: x["timestamp"], reverse=True)[:limit]


def get_logs_for_phone(phone: str, limit: int = 50) -> list[dict]:
    """Retorna eventos para un número de teléfono específico."""
    all_logs = get_recent_logs(limit=1000)
    return [log for log in all_logs if log.get("phone") == phone][:limit]


def get_log_summary(hours: int = 1) -> dict:
    """Genera resumen de logs en las últimas N horas."""
    from datetime import timedelta
    
    cutoff_time = datetime.now() - timedelta(hours=hours)
    recent_logs = get_recent_logs(limit=10000)
    
    filtered = [
        log for log in recent_logs 
        if datetime.fromisoformat(log["timestamp"]) > cutoff_time
    ]
    
    summary = {
        "time_range": f"Last {hours} hours",
        "total_events": len(filtered),
        "events_by_type": {},
        "errors": [],
        "phones": set(),
        "search_queries": [],
        "failed_sends": [],
    }
    
    for log in filtered:
        event_type = log.get("event_type")
        summary["events_by_type"][event_type] = summary["events_by_type"].get(event_type, 0) + 1
        
        if log.get("phone"):
            summary["phones"].add(log["phone"])
        
        if event_type == "error":
            summary["errors"].append({
                "timestamp": log["timestamp"],
                "phone": log.get("phone"),
                "error": log.get("error_message"),
            })
        
        if event_type == "search_query":
            summary["search_queries"].append({
                "timestamp": log["timestamp"],
                "phone": log.get("phone"),
                "sector": log.get("sector"),
                "ciudad": log.get("ciudad"),
                "results": log.get("results_count"),
            })
        
        if event_type == "send_attempt" and not log.get("success"):
            summary["failed_sends"].append({
                "timestamp": log["timestamp"],
                "phone": log.get("phone"),
                "company": log.get("company"),
                "error": log.get("error"),
            })
    
    summary["phones"] = list(summary["phones"])
    return summary
