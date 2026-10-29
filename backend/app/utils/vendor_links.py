from urllib.parse import parse_qs, quote_plus, unquote, urljoin, urlparse


def build_vendor_search_url(vendor_name: str, query: str) -> str:
    encoded_query = quote_plus(query)
    normalized_vendor = vendor_name.lower()

    if normalized_vendor == "amazon":
        return f"https://www.amazon.in/s?k={encoded_query}"
    if normalized_vendor == "croma":
        return f"https://www.croma.com/searchB?q={encoded_query}%3Arelevance&text={encoded_query}"
    if normalized_vendor == "electronicscomp":
        return f"https://www.electronicscomp.com/search?search={encoded_query}"
    if normalized_vendor == "flipkart":
        return f"https://www.flipkart.com/search?q={encoded_query}"
    if normalized_vendor == "global electronics":
        return f"https://www.globalelectronics.in/all-products?q={encoded_query}"
    if normalized_vendor == "ibo":
        return f"https://www.ibo.com/search?search_term={encoded_query}"
    if "invent" in normalized_vendor:
        return f"https://inventstore.in/?s={encoded_query}&post_type=product"
    if normalized_vendor == "moglix":
        return f"https://www.moglix.com/search?search_query={encoded_query}"
    if normalized_vendor == "poorvika":
        return f"https://www.google.com/search?q={quote_plus(f'site:poorvika.com {query}')}"
    if normalized_vendor == "reliance digital":
        return f"https://www.reliancedigital.in/products?q={encoded_query}"
    if normalized_vendor == "robu":
        return f"https://robu.in/?s={encoded_query}&post_type=product"
    if normalized_vendor == "vijay sales":
        return f"https://www.vijaysales.com/search?q={encoded_query}"
    return f"https://www.google.com/search?q={quote_plus(f'{vendor_name} {query}')}"


def resolve_vendor_url(vendor_name: str, product_url: str | None, query: str) -> str:
    fallback_url = build_vendor_search_url(vendor_name, query)
    if not product_url:
        return fallback_url

    parsed = urlparse(product_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return fallback_url

    path = parsed.path.lower()
    if "demo" in path:
        return fallback_url

    return product_url


def canonicalize_vendor_product_url(
    vendor_name: str,
    product_url: str,
    base_url: str,
) -> str:
    parsed = urlparse(product_url)
    normalized_vendor = vendor_name.lower()

    if normalized_vendor == "amazon":
        query_values = parse_qs(parsed.query)
        wrapped_url = query_values.get("url", [None])[0]
        if wrapped_url:
            target_url = urljoin(base_url, unquote(wrapped_url))
            target_parsed = urlparse(target_url)
            asin_parts = target_parsed.path.split("/dp/")
            if len(asin_parts) > 1:
                asin = asin_parts[1].split("/")[0]
                return f"{base_url}/dp/{asin}"
            return f"{base_url}{target_parsed.path}"
        asin_parts = parsed.path.split("/dp/")
        if len(asin_parts) > 1:
            asin = asin_parts[1].split("/")[0]
            return f"{base_url}/dp/{asin}"

    if normalized_vendor == "croma":
        query_values = parse_qs(parsed.query)
        wrapped_url = query_values.get("url", [None])[0]
        if wrapped_url:
            target_url = urljoin(base_url, unquote(wrapped_url))
            target_parsed = urlparse(target_url)
            return f"{base_url}{target_parsed.path}"

    if normalized_vendor in {
        "croma",
        "electronicscomp",
        "flipkart",
        "global electronics",
        "ibo",
        "moglix",
        "poorvika",
        "reliance digital",
        "robu",
        "vijay sales",
    }:
        return f"{base_url}{parsed.path}"

    return product_url
