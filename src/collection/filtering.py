from urllib.parse import urlparse

TRUSTED_DOMAINS = {
    "laliga.com",
    "as.com",
    "marca.com",
    "sport.es",
    "mundodeportivo.com",
    "relevo.com",
    "cope.es",
    # Regional daily (Vocento group) with a public news sitemap and
    # no bot blocking: adds discovery breadth without extra scraping.
    "estadiodeportivo.com",
    # Public radio: publishes full press-conference transcripts.
    "rtve.es",
}

def get_domain(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")

def is_allowed_source(url: str) -> bool:
    domain = get_domain(url)
    return any(
        domain == allowed or domain.endswith("." + allowed)
        for allowed in TRUSTED_DOMAINS
    )
