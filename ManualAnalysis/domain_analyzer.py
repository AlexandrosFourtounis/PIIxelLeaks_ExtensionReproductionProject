#!/usr/bin/env python3
"""
Domain Analyzer — visit a list of domains and record:
  - HTTP status code
  - Redirection chain (if any)
  - Final HTML content

Outputs are saved inside ManualAnalysis/<run_name>/:
  - summary.json          — per-domain results (status, redirects, file references)
  - html/<domain>.html    — raw HTML for each domain that returned a body
"""

import os
import sys
import json
import asyncio
import aiohttp
import socket
import time
from urllib.parse import urlparse
from pathlib import Path


# ── config ──────────────────────────────────────────────────────────────────

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "DNT": "1",
    "Connection": "close",
    "Upgrade-Insecure-Requests": "1",
}

TIMEOUT_SECONDS = 45
MAX_REDIRECTS = 20         # aiohttp default; keep explicit
CONCURRENCY = 10            # simultaneous requests


# ── helpers ─────────────────────────────────────────────────────────────────

def ensure_url(domain: str) -> str:
    """Prepend https:// if the domain has no scheme."""
    if not domain.startswith(("http://", "https://")):
        return "https://" + domain
    return domain


def extract_base_domain(url: str) -> str:
    """Return the netloc (host) from a URL, stripping port if present."""
    parsed = urlparse(url)
    host = parsed.netloc or parsed.path  # fallback for bare domains
    if ":" in host:
        host = host.split(":")[0]
    return host


def sanitise_filename(domain: str) -> str:
    """Turn a domain into a safe filename."""
    return domain.replace("/", "_").replace(":", "_").replace("?", "_")


# ── core async fetch ────────────────────────────────────────────────────────

async def _try_fetch(session: aiohttp.ClientSession, url: str):
    """
    Attempt one GET request.  Returns (redirect_history, final_url, status_code, html_content).
    Raises on any error (caller handles fallback).
    """
    redirect_history = []

    async with session.get(url, allow_redirects=True, max_redirects=MAX_REDIRECTS) as resp:
        for hist in resp.history:
            redirect_history.append({
                "url": str(hist.url),
                "status": hist.status,
                "location": hist.headers.get("Location", ""),
            })

        final_url = str(resp.url)
        status = resp.status
        html = None

        if status == 200:
            try:
                html = await resp.text()
            except UnicodeDecodeError:
                raw = await resp.read()
                html = raw.decode("utf-8", errors="replace")
            except Exception:
                html = "(binary body — could not decode)"

    return redirect_history, final_url, status, html


def _is_retryable_conn_error(exc: Exception) -> bool:
    """Return True if the exception looks like an SSL / connection error worth retrying on HTTP."""
    msg = str(exc).lower()
    # aiohttp wraps OS-level SSL errors inside ClientConnectorError
    return any(kw in msg for kw in [
        "ssl", "certificate", "handshake", "tls", "cannot connect", "connection refused",
    ])


async def fetch_domain(session: aiohttp.ClientSession, domain: str, idx: int):
    """
    Fetch a single domain — HTTPS first, with HTTP fallback on connect/SSL errors.
    Returns a dict with:
      original_domain, final_url, status_code, redirect_chain, html_file, error
    """
    base = extract_base_domain(ensure_url(domain))

    result = {
        "index": idx,
        "original_domain": domain,
        "base_domain": base,
        "final_url": None,
        "status_code": None,
        "redirect_chain": [],
        "html_file": None,
        "error": None,
    }

    # 1. DNS check (synchronous, run in thread)
    try:
        await asyncio.to_thread(socket.gethostbyname, base)
    except socket.gaierror:
        result["error"] = "DNS_PROBE_FINISHED_NXDOMAIN"
        print(f"  [{idx:>4}] DNS FAIL  {domain}")
        return result

    # 2. Try HTTPS, then HTTP on connect/SSL failures
    tried_urls = []
    if domain.startswith("http://"):
        tried_urls.append(domain)                       # user explicitly asked for http
    elif domain.startswith("https://"):
        tried_urls.append(domain)                       # user explicitly asked for https
    else:
        tried_urls = [f"https://{domain}", f"http://{domain}"]

    last_error = None

    for attempt, url in enumerate(tried_urls):
        try:
            redirect_history, final_url, status, html = await _try_fetch(session, url)

            result["redirect_chain"] = redirect_history
            result["final_url"] = final_url
            result["status_code"] = status
            result["html_content"] = html

            n_redir = len(redirect_history)
            redir_str = f" ({n_redir} hop{'s' if n_redir != 1 else ''})" if n_redir else ""
            fallback_tag = " [fallback HTTP]" if attempt == 1 else ""
            print(f"  [{idx:>4}] {status}  {domain} -> {final_url}{redir_str}{fallback_tag}")
            return result

        except aiohttp.ClientConnectorError as e:
            last_error = e
            if attempt < len(tried_urls) - 1 and _is_retryable_conn_error(e):
                continue  # try next scheme
            result["error"] = f"Connection error: {e}"
            print(f"  [{idx:>4}] CONN_ERR {domain}  {e}")
            return result

        except asyncio.TimeoutError:
            last_error = "Timeout"
            if attempt < len(tried_urls) - 1:
                continue
            result["error"] = "Timeout"
            print(f"  [{idx:>4}] TIMEOUT  {domain}")
            return result

        except aiohttp.TooManyRedirects:
            result["error"] = "Too many redirects"
            print(f"  [{idx:>4}] REDIR_LOOP {domain}")
            return result

        except aiohttp.ClientError as e:
            last_error = e
            if attempt < len(tried_urls) - 1 and _is_retryable_conn_error(e):
                continue
            result["error"] = f"Client error: {e}"
            print(f"  [{idx:>4}] CLIENT_ERR {domain}  {e}")
            return result

        except Exception as e:
            result["error"] = f"Unexpected: {e}"
            print(f"  [{idx:>4}] UNEXPECTED {domain}  {e}")
            return result

    # Exhausted all attempts
    result["error"] = f"All schemes failed, last error: {last_error}"
    print(f"  [{idx:>4}] ALL_FAIL {domain}  {last_error}")
    return result


# ── main orchestrator ───────────────────────────────────────────────────────

async def analyse_domains(domains: list, output_dir: Path):
    """Run the analysis for all domains and write outputs."""
    output_dir.mkdir(parents=True, exist_ok=True)
    html_dir = output_dir / "html"
    html_dir.mkdir(parents=True, exist_ok=True)

    connector = aiohttp.TCPConnector(limit=CONCURRENCY, limit_per_host=2, ssl=False)
    timeout = aiohttp.ClientTimeout(total=TIMEOUT_SECONDS)

    results = []

    async with aiohttp.ClientSession(
        timeout=timeout,
        connector=connector,
        headers=HEADERS,
    ) as session:
        tasks = []
        for i, domain in enumerate(domains):
            tasks.append(fetch_domain(session, domain, i + 1))

        # Gather with return_exceptions so one failure doesn't kill the batch
        gathered = await asyncio.gather(*tasks, return_exceptions=True)

    # Process results
    for item in gathered:
        if isinstance(item, Exception):
            results.append({"error": f"Task crashed: {item}"})
        else:
            # Write HTML to file if present
            html_content = item.pop("html_content", None)
            if html_content:
                fname = sanitise_filename(item["base_domain"]) + ".html"
                html_path = html_dir / fname
                html_path.write_text(html_content, encoding="utf-8", errors="replace")
                item["html_file"] = str(html_path.relative_to(output_dir))
            results.append(item)

    # ── summary.json ────────────────────────────────────────────────────
    summary_path = output_dir / "summary.json"
    summary_path.write_text(
        json.dumps(results, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # ── stats ───────────────────────────────────────────────────────────
    total = len(results)
    ok = sum(1 for r in results if r.get("status_code") == 200)
    redirected = sum(1 for r in results if r.get("redirect_chain"))
    errors = sum(1 for r in results if r.get("error"))
    other_status = total - ok - errors

    print(f"\n{'='*60}")
    print(f"Done. {total} domains processed.")
    print(f"  200 OK:       {ok}")
    print(f"  Other status: {other_status}")
    print(f"  Errors:       {errors}")
    print(f"  Redirected:   {redirected}")
    print(f"Output → {output_dir.resolve()}")
    print(f"Summary → {summary_path.name}")
    print(f"HTML    → {html_dir.name}/")


# ── CLI entrypoint ──────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print("Usage: python domain_analyzer.py <domains.txt> [run_name]")
        print()
        print("  domains.txt — one domain per line")
        print("  run_name    — optional folder name (default: timestamped)")
        sys.exit(1)

    domain_file = Path(sys.argv[1])
    if not domain_file.exists():
        print(f"File not found: {domain_file}")
        sys.exit(1)

    run_name = sys.argv[2] if len(sys.argv) > 2 else time.strftime("run_%Y%m%d_%H%M%S")
    output_dir = Path(__file__).resolve().parent / run_name

    domains = [line.strip() for line in domain_file.read_text().splitlines() if line.strip()]
    print(f"Loaded {len(domains)} domains from {domain_file}")
    print(f"Output directory: {output_dir}")
    print()

    asyncio.run(analyse_domains(domains, output_dir))


if __name__ == "__main__":
    main()
