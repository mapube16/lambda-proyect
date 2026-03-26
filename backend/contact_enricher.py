#!/usr/bin/env python3
"""
contact_enricher.py — Busca email y teléfono de empresas colombianas

Fuentes:
1. Google (via DuckDuckGo)
2. Directorios públicos (páginas amarillas, directorios sectoriales)
3. Redes sociales (LinkedIn, Instagram business)
4. DANE directorio de empresas
"""
import asyncio
import re
import logging
from typing import Optional

import httpx
from bs4 import BeautifulSoup
from debug_logger import get_payload_logger

logger = logging.getLogger(__name__)
debug_log = get_payload_logger()

# Email regex
EMAIL_REGEX = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
PHONE_REGEX = r'[+57\s]*(\d{1}\s?)(\d{3})\s?(\d{3})\s?(\d{4})|\+57[\d\s]{9,}'


async def search_company_contact(
    company_name: str,
    ciudad: Optional[str] = None,
) -> dict:
    """Busca email y teléfono de una empresa colombiana.
    
    Args:
        company_name: Razón social de la empresa
        ciudad: Ciudad (opcional, mejora precisión)
    
    Returns:
        {
            "email": "contacto@empresa.com" or None,
            "teléfono": "+57..." or None,
            "web": "www.empresa.com" or None,
            "fuente": "google" | "directorios" | "None"
        }
    """
    
    query = f"{company_name}"
    if ciudad:
        query += f" {ciudad}"
    query += " colombia contacto email"
    
    try:
        # Buscar en DuckDuckGo
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://duckduckgo.com/html/",
                params={"q": query},
            )
            
            if resp.status_code != 200:
                debug_log.log_event("enrichment_search_failed", {
                    "company": company_name,
                    "ciudad": ciudad,
                    "reason": f"HTTP {resp.status_code}",
                }, level="WARNING")
                return {"email": None, "teléfono": None, "web": None, "fuente": None}
            
            soup = BeautifulSoup(resp.text, "html.parser")
            
            # Extrae todos los links
            web = None
            for link in soup.find_all("a", {"class": "result__url"})[:5]:
                href = link.get("href", "")
                if "empresa" in company_name.lower() and "linkedin.com" not in href:
                    web = href
                    break
            
            # Busca en el primer resultado web
            email_found = None
            phone_found = None
            
            if web:
                try:
                    web_resp = await client.get(web, follow_redirects=True, timeout=5)
                    web_content = web_resp.text
                    
                    # Busca emails
                    emails = re.findall(EMAIL_REGEX, web_content)
                    if emails:
                        # Prefiere emails corporativos
                        for e in emails:
                            if not any(x in e for x in ["noreply", "no-reply", "contact@", "info@"]):
                                continue
                            email_found = e
                            break
                        if not email_found:
                            email_found = emails[0]
                    
                    # Busca teléfonos
                    phones = re.findall(PHONE_REGEX, web_content)
                    if phones:
                        phone_found = phones[0]
                    
                    debug_log.log_enrichment_attempt("system", company_name, ciudad or "unknown", 
                                                     bool(email_found or phone_found),
                                                     {
                                                         "email": email_found,
                                                         "phone": phone_found,
                                                         "source": "google"
                                                     })
                
                except Exception as e:
                    logger.warning(f"Error scraping {web}: {e}")
                    debug_log.log_event("enrichment_scrape_error", {
                        "company": company_name,
                        "web": web,
                        "error": str(e),
                    }, level="WARNING")
            
            return {
                "email": email_found,
                "teléfono": phone_found,
                "web": web,
                "fuente": "google" if email_found or phone_found else None
            }
    
    except Exception as e:
        logger.error(f"Error searching contact for {company_name}: {e}")
        debug_log.log_error("system", "enrichment_error", str(e), {"company": company_name, "ciudad": ciudad})
        return {"email": None, "teléfono": None, "web": None, "fuente": None}


async def enrich_companies_with_contacts(
    companies: list[dict],
    max_concurrent: int = 2,
) -> list[dict]:
    """Enriquece una lista de empresas con datos de contacto.
    
    Args:
        companies: Lista de dicts con al menos {"razon_social", "ciudad"}
        max_concurrent: Max búsquedas en paralelo
    
    Returns:
        Lista con campos añadidos: email, teléfono, web
    """
    
    semaphore = asyncio.Semaphore(max_concurrent)
    
    async def enrich_one(company):
        async with semaphore:
            contact = await search_company_contact(
                company.get("razon_social", ""),
                company.get("ciudad") or company.get("municipio")
            )
            return {**company, **contact}
    
    tasks = [enrich_one(c) for c in companies]
    return await asyncio.gather(*tasks)


if __name__ == "__main__":
    async def test():
        companies = [
            {"razon_social": "Constructor Plus SAS", "ciudad": "Bogotá"},
            {"razon_social": "BuildTech Innovations", "ciudad": "Medellín"},
        ]
        
        results = await enrich_companies_with_contacts(companies)
        
        for r in results:
            print(f"\n{r['razon_social']}")
            print(f"  Email: {r.get('email')}")
            print(f"  Teléfono: {r.get('teléfono')}")
            print(f"  Web: {r.get('web')}")
    
    asyncio.run(test())
