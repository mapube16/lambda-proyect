"""
test_scrape.py — Phase 20: Scraping Improvements.

Requirement areas:
  SCRAPE-01: Scraper uses curl_cffi AsyncSession(impersonate="chrome131") instead of httpx
  SCRAPE-02: Scraped HTML converts to compressed Markdown via Crawl4AI before LLM analysis
  SCRAPE-03: DIRECTORY_DOMAINS blocklist filters aggregator sites from Serper results before scraping
  SCRAPE-04: extract_homepage(url) normalizes blog/directory URLs to company homepages

All stubs use strict=False so CI never blocks on unimplemented features.
Heavy imports (curl_cffi, crawl4ai) are placed INSIDE test bodies (lazy) so collection
succeeds before those modules exist.
"""
import pytest


# ── SCRAPE-01: curl_cffi Chrome131 TLS impersonation ─────────────────────────

@pytest.mark.xfail(
    reason="SCRAPE-01: curl_cffi not installed; scrape_url still uses httpx",
    strict=False,
)
async def test_curl_cffi_scraper_bypasses_bot_detection():
    """
    scrape_url uses curl_cffi AsyncSession(impersonate='chrome131') which returns
    real page HTML on Cloudflare-protected sites where a plain httpx request
    would return a bot-detection / CAPTCHA page.

    Verifies:
    - curl_cffi is importable
    - scrape_url no longer instantiates httpx.AsyncClient
    - A mock curl_cffi session call returns HTML (not a [SCRAPING_ERROR:...] string)
    """
    from unittest.mock import AsyncMock, patch, MagicMock

    # curl_cffi must be importable after it's added to requirements.txt
    import curl_cffi.requests as curl_requests  # noqa: F401 — import check

    # Verify scrape_url uses curl_cffi, not httpx, by checking it doesn't
    # instantiate httpx.AsyncClient when curl_cffi is available.
    import prospector
    import inspect
    source = inspect.getsource(prospector.scrape_url)
    assert "curl_cffi" in source or "impersonate" in source, (
        "scrape_url must use curl_cffi impersonation — httpx is not enough"
    )

    # Functional: mock curl_cffi session returning real HTML for a protected URL
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.text = "<html><body><h1>Empresa Real S.A.</h1><p>Somos una empresa colombiana...</p></body></html>"

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.get = AsyncMock(return_value=fake_response)

    with patch("prospector.curl_cffi.requests.AsyncSession", return_value=mock_session):
        result = await prospector.scrape_url("https://cloudflare-protected.com.co")

    assert "[SCRAPING_ERROR" not in result
    assert "Empresa Real" in result


# ── SCRAPE-02: Crawl4AI HTML → Markdown compression ──────────────────────────

@pytest.mark.xfail(
    reason="SCRAPE-02: crawl4ai not installed; scrape_url does not compress HTML to Markdown yet",
    strict=False,
)
async def test_crawl4ai_compresses_html_to_markdown():
    """
    scrape_url (or a helper it calls) passes scraped HTML through Crawl4AI which
    produces a Markdown string with at least 70% fewer characters than the original
    HTML, while still containing all key company text content.

    Verifies:
    - crawl4ai is importable
    - The text returned by scrape_url for a real HTML input is Markdown (not raw HTML soup)
    - Character count reduction is at least 70%
    - Key textual content survives the compression
    """
    # crawl4ai must be importable after it's added to requirements.txt
    import crawl4ai  # noqa: F401 — import check

    # Build a realistic HTML page with lots of boilerplate (nav/scripts/styles)
    html_content = """<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <title>Empresa Logística Colombia S.A.S.</title>
  <style>body { font-family: Arial; } .nav { background: #333; } /* 500 chars of CSS here */</style>
  <script>
    // 1000 chars of JS analytics boilerplate
    window.dataLayer = window.dataLayer || [];
    function gtag(){{ dataLayer.push(arguments); }}
    gtag('js', new Date());
    gtag('config', 'UA-XXXXXX');
  </script>
</head>
<body>
  <nav class="nav">
    <ul><li><a href="/">Inicio</a></li><li><a href="/servicios">Servicios</a></li>
    <li><a href="/nosotros">Nosotros</a></li><li><a href="/contacto">Contacto</a></li></ul>
  </nav>
  <header>
    <h1>Empresa Logística Colombia S.A.S.</h1>
    <p>Líderes en transporte de carga a nivel nacional con más de 20 años de experiencia.</p>
  </header>
  <main>
    <section class="services">
      <h2>Nuestros Servicios</h2>
      <ul>
        <li>Transporte terrestre de carga</li>
        <li>Logística de última milla en Bogotá</li>
        <li>Almacenamiento y distribución</li>
        <li>Gestión de cadena de suministro</li>
      </ul>
    </section>
    <section class="about">
      <h2>¿Quiénes Somos?</h2>
      <p>Somos una empresa mediana con 150 empleados, cobertura nacional y presencia en Bogotá, Medellín y Cali.</p>
      <p>Usamos SAP para gestión de flota y estamos buscando mejorar nuestra eficiencia operacional.</p>
    </section>
    <section class="contact">
      <h2>Contacto</h2>
      <p>Email: <a href="mailto:gerencia@empresalogistica.com.co">gerencia@empresalogistica.com.co</a></p>
      <p>Tel: +57 601 234 5678</p>
    </section>
  </main>
  <footer>
    <p>© 2024 Empresa Logística Colombia S.A.S. Todos los derechos reservados.</p>
    <ul><li><a href="/privacidad">Privacidad</a></li><li><a href="/terminos">Términos</a></li></ul>
  </footer>
</body>
</html>"""

    original_len = len(html_content)

    # The compress_html_to_markdown helper (to be implemented in prospector.py or scraper.py)
    import prospector
    markdown = await prospector.compress_html_to_markdown(html_content)

    compressed_len = len(markdown)
    reduction_pct = (original_len - compressed_len) / original_len

    assert reduction_pct >= 0.70, (
        f"Expected ≥70% reduction, got {reduction_pct:.1%} "
        f"(original={original_len} chars, compressed={compressed_len} chars)"
    )
    # Key content must survive compression
    assert "Empresa Logística Colombia" in markdown
    assert "transporte" in markdown.lower() or "carga" in markdown.lower()
    assert "SAP" in markdown or "eficiencia" in markdown.lower()


# ── SCRAPE-03: DIRECTORY_DOMAINS blocklist ────────────────────────────────────

@pytest.mark.xfail(
    reason="SCRAPE-03: DIRECTORY_DOMAINS blocklist not yet applied to Serper results in prospector.py",
    strict=False,
)
async def test_directory_domains_filtered_from_serper_results():
    """
    When discover_via_serper returns results that include directory domain URLs
    (e.g. ciencuadras.com, computrabajo.com), those entries are filtered out
    before any HTTP request is made to scrape them. Zero scraping requests are
    made to DIRECTORY_DOMAINS entries.

    Verifies:
    - DIRECTORY_DOMAINS constant exists in prospector.py (or scraper module)
    - ciencuadras.com and computrabajo.com are in DIRECTORY_DOMAINS
    - discover_companies filters results with DIRECTORY_DOMAINS before returning
    - analyze_company is never called for a DIRECTORY_DOMAINS URL
    """
    from unittest.mock import AsyncMock, patch
    import prospector

    # DIRECTORY_DOMAINS must be exported from prospector (or scraper module)
    assert hasattr(prospector, "DIRECTORY_DOMAINS"), (
        "prospector.py must define DIRECTORY_DOMAINS blocklist"
    )
    directory_domains = prospector.DIRECTORY_DOMAINS
    assert "ciencuadras.com" in directory_domains, "ciencuadras.com must be in DIRECTORY_DOMAINS"
    assert "computrabajo.com" in directory_domains, "computrabajo.com must be in DIRECTORY_DOMAINS"

    # Serper returns a mix of valid companies and directory domains
    mixed_serper_results = [
        {"title": "Empresa Real S.A.", "url": "https://empresareal.com.co", "phone": "", "address": "", "source": "serper"},
        {"title": "Ciencuadras Listing", "url": "https://ciencuadras.com/empresa/xyz", "phone": "", "address": "", "source": "serper"},
        {"title": "Computrabajo Jobs", "url": "https://www.computrabajo.com.co/empresas/real-estate", "phone": "", "address": "", "source": "serper"},
        {"title": "Transportadora Andina", "url": "https://transportadoraandina.com.co", "phone": "", "address": "", "source": "serper"},
    ]

    scrape_calls = []

    async def mock_scrape_url(url: str, **kwargs):
        scrape_calls.append(url)
        return "<html><body>OK</body></html>"

    with patch("prospector.discover_via_serper", new=AsyncMock(return_value=mixed_serper_results)), \
         patch("prospector.scrape_url", new=mock_scrape_url):
        results = await prospector.discover_companies(
            industria="inmobiliaria",
            ciudad="Bogotá",
            max_results=10,
            gmaps_key="",
        )

    # Only non-directory-domain results should come through
    result_urls = [r["url"] for r in results]
    assert not any("ciencuadras.com" in url for url in result_urls), (
        "ciencuadras.com must not appear in discovery results"
    )
    assert not any("computrabajo.com" in url for url in result_urls), (
        "computrabajo.com must not appear in discovery results"
    )
    # Valid companies must survive
    assert any("empresareal.com.co" in url or "transportadoraandina.com.co" in url for url in result_urls)

    # Scrape must not be called for directory domains
    assert not any("ciencuadras.com" in url for url in scrape_calls), (
        "scrape_url must not be called for ciencuadras.com"
    )
    assert not any("computrabajo.com" in url for url in scrape_calls), (
        "scrape_url must not be called for computrabajo.com"
    )


# ── SCRAPE-04: extract_homepage URL normalization ─────────────────────────────

@pytest.mark.xfail(
    reason="SCRAPE-04: extract_homepage() not yet implemented in prospector.py",
    strict=False,
)
def test_extract_homepage_normalizes_blog_url():
    """
    extract_homepage(url) takes a URL (potentially a blog post, article, or
    directory listing) and returns the company root domain homepage URL, or
    None if the URL is from a directory domain (not a company homepage).

    Verifies:
    - extract_homepage is importable from prospector (or scraper module)
    - blog.acme.com/article/123 → https://acme.com
    - acme.com/blog/post-title → https://acme.com (strips blog path)
    - ciencuadras.com/listing/company → None (directory domain — no homepage)
    - computrabajo.com/empresa/xyz → None (job board — no homepage)
    - https://empresareal.com.co/quienes-somos → https://empresareal.com.co (already a homepage path)
    - https://empresareal.com.co → https://empresareal.com.co (already root — unchanged)
    """
    import prospector

    assert hasattr(prospector, "extract_homepage"), (
        "prospector.py must define extract_homepage(url) function"
    )
    extract = prospector.extract_homepage

    # Blog subdomain → root domain
    assert extract("https://blog.acme.com/article/product-launch-2024") == "https://acme.com"

    # Blog path on root domain → root domain
    assert extract("https://acme.com/blog/tips-for-logistics") == "https://acme.com"

    # Article path → root domain
    assert extract("https://www.transportesandinos.com.co/articulos/novedad-2024") == "https://www.transportesandinos.com.co"

    # Directory domain → None (should not be scraped as a company)
    assert extract("https://ciencuadras.com/empresa/transportes-xyz") is None
    assert extract("https://computrabajo.com.co/empresas/real-estate-bogota") is None

    # Already a homepage → return normalized https root
    assert extract("https://empresareal.com.co") == "https://empresareal.com.co"
    assert extract("https://empresareal.com.co/quienes-somos") == "https://empresareal.com.co"

    # www prefix preserved
    assert extract("https://www.logisticacol.com.co") == "https://www.logisticacol.com.co"
