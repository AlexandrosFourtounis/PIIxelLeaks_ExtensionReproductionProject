# PII_Hybrid_Crawler: Extended Methodology -- Complete Guide

This document is the definitive reference for the **PII_Hybrid_Crawler_Extension.py**, the extended version of the original `PII_Hybrid_Crawler.py`. It enumerates every architectural, logical, and detection-related change made to transform a sequential, happy-path scanner into a parallelized, obfuscation-resistant crawler capable of defeating modern tracking evasion on both mainstream and adversarial domains.

The extensions are grouped into three categories:

1. **Architecture and Performance** (Extensions 1--2): Changes to the execution model.
2. **Static Detection Improvements** (Extensions 3--8): Changes to the HTML-parsing phase.
3. **Headless Detection Improvements** (Extensions 9--19): Changes to the browser-based phase.

Each section specifies the **state_type** label that appears in the output JSON files (`pixels_found.json` and `state_fbq.json`) so that results can be traced back to the exact detection method.

---

## Architecture and Performance

---

### Extension 1 -- Parallel Execution Model

**Output file:** N/A (architectural change)

The original crawler processed every domain sequentially: one static fetch, one GTM lookup, one headless browser session at a time. This made crawling 50,000 domains prohibitively slow.

The extension re-architects the pipeline using `concurrent.futures`. Static HTML fetches run inside a `ThreadPoolExecutor` (I/O-bound work benefits from threads), while headless browser sessions run inside a `ProcessPoolExecutor` (CPU-bound Selenium instances need separate processes to avoid the GIL).

**Original (`PII_Hybrid_Crawler.py`):**
```python
# Sequential static fetch -- one domain at a time
for i, domain in enumerate(domains):
    html_content = fetch_html(i, domain)
    # ... process domain ...

# Sequential headless browser -- one domain at a time
for domain in total_headless:
    process_domain(domain, chromedriver_path)
```

**Extension (`PII_Hybrid_Crawler_Extension.py`):**
```python
# Parallel static fetch via ThreadPoolExecutor
with ThreadPoolExecutor(max_workers=max_fetch_workers) as executor:
    futures = {executor.submit(_process_single_domain, args): args[1] for args in args_list}
    for future in as_completed(futures):
        result = future.result()
        # ... collect results ...

# Parallel headless browser via ProcessPoolExecutor
with ProcessPoolExecutor(max_workers=max_workers) as executor:
    futures = {executor.submit(process_domain, domain, chromedriver_path): domain
               for domain in domains}
    for future in as_completed(futures):
        # ... collect results ...
```

**Additional change -- event loop safety:**
The `fetch_html` wrapper was changed from a bare `asyncio.run()` call to an explicit `new_event_loop()` / `run_until_complete()` / `close()` pattern. This prevents "event loop already running" errors when called from worker threads.

```python
# Original
def fetch_html(i, domain):
    return asyncio.run(fetch_html_async(i, domain))

# Extension
def fetch_html(i, domain):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(fetch_html_async(i, domain))
    finally:
        loop.close()
```

**Additional change -- global timeout removal:**
An earlier draft of the extension added `timeout=300` to the `as_completed(futures)` call in the headless phase. This created a hard 5-minute kill-switch on the entire batch, causing legitimate domains to be dropped when batches ran long. The timeout was removed; per-domain timeouts inside Selenium (`set_page_load_timeout(60)`) remain as the safety net.

---

### Extension 2 -- GTM Tag Lookup Parallelization

**Output file:** `pixels_found.json` | **state_type:** `PIXEL_GTM`

When a domain contains multiple Google Tag Manager containers (e.g., both `GTM-XXXX` in a `<script>` tag and `GTM-YYYY` in a `<noscript>` tag), the original code fetched each remote GTM configuration file one after another. Since each fetch is a network round-trip, this was wasteful.

The extension wraps the per-tag lookups in an inner `ThreadPoolExecutor`.

**Original:**
```python
if base_code_gtm:
    for tag in base_code_gtm:
        print(f"Analyzing: {tag}")
        type_, fbps = search_for_pixel_in_gtm(domain, tag)
        if fbps:
            per_gtm_tag[domain]['found_flag'] = 1
            per_gtm_tag[domain]['base_code_type'] = type_
            per_gtm_tag[domain]['base_code_gtm'][tag] = fbps
```

**Extension:**
```python
# Build a list of (tag, bucket) pairs, then process in parallel
tasks = []
if base_code_gtm:
    for tag in base_code_gtm:
        tasks.append((tag, 'base'))
if lightweight_gtm:
    for tag in lightweight_gtm:
        if base_code_gtm and tag not in base_code_gtm:
            tasks.append((tag, 'light'))

with ThreadPoolExecutor(max_workers=min(len(tasks), 8)) as ex:
    futures = {ex.submit(_analyze_tag, tb): tb for tb in tasks}
    for future in as_completed(futures):
        tag, bucket, type_, fbps = future.result()
        if fbps:
            per_gtm_tag[domain]['found_flag'] = 1
            if bucket == 'base':
                per_gtm_tag[domain]['base_code_type'] = type_
                per_gtm_tag[domain]['base_code_gtm'][tag] = fbps
            else:
                per_gtm_tag[domain]['light_code_type'] = type_
                per_gtm_tag[domain]['lightweight_gtm'][tag] = fbps
```

**Additional change -- GTM regex expansion:**
A new regex pattern was added to detect GTM containers served through custom first-party domains (e.g., `tracking.example.com/gtm.js?id=GTM-XXXX`) rather than the standard `googletagmanager.com`:

```python
# Added to find_gtm_scripts()
r'(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}/gtm\.js\?id=(GTM-[A-Z0-9]+)'
```

**Additional change -- `extract_tags_array` return type:**
The original function returned a raw JSON string, while `extract_macros_array` returned a parsed list. This inconsistency caused downstream code to handle the two arrays differently. The extension parses the string before returning it:

```python
# Original -- returns raw string
return tags_str

# Extension -- returns parsed list
return json.loads(tags_str)
```

---

## Static Detection Improvements

---

### Extension 3 -- Basecode Early-Return Bug Fix

**Output file:** `pixels_found.json` | **state_type:** `PIXEL_CORE`

The functions `identify_fbp_basecode` and `identify_fbp_basecode_in_the_wild` both contained an identical bug: a `return` statement inside the `for script in script_tags` loop caused the function to exit after finding the first matching `<script>` tag. If a page embedded two separate Pixel snippets (common on e-commerce sites that track multiple ad accounts), only the first one was ever recorded.

**Original (both functions):**
```python
for script in script_tags:
    script_content = str(script)
    if any(keyword in script_content for keyword in keywords):
        init_calls = re.findall(pattern_init, script_content)
        track_calls = re.findall(pattern_track, script_content)
        if init_calls or track_calls:
            pixels_found.append({
                "domain": domain,
                "init": init_calls,
                "track": track_calls
            })
            return pixels_found  # <-- exits after first match

return None
```

**Extension (both functions):**
```python
for script in script_tags:
    script_content = str(script)
    if any(keyword in script_content for keyword in keywords):
        init_calls = re.findall(pattern_init, script_content)
        track_calls = re.findall(pattern_track, script_content)
        if init_calls or track_calls:
            pixels_found.append({
                "domain": domain,
                "init": init_calls,
                "track": track_calls
            })
            # No return here -- continue scanning remaining scripts

return pixels_found if pixels_found else None
```

---

### Extension 4 -- Base64 and URL-Encoding Obfuscation Decoding

**Output file:** `pixels_found.json` (static phase) or `state_fbq.json` (headless phase) | **state_type:** `PIXEL_OBFUSCATED` (static) or `DEEP_EXTRACTION_OBFUSCATED` (headless)

The original crawler performed no obfuscation handling whatsoever. Scam domains frequently hide their pixel initialization inside `atob()` calls or URL-encoded strings so that the literal text `fbq('init', ...)` never appears in plaintext HTML.

The extension adds a dedicated `decode_obfuscated_pixel_ids()` function that is called in both the static and headless phases:

```python
def decode_obfuscated_pixel_ids(content):
    """Decode base64-encoded and URL-encoded strings that might contain pixel IDs."""
    pixel_ids = []

    # Base64: atob('...') calls
    b64_pattern = r'atob\s*\(\s*["\'](A-Za-z0-9+/=]+)["\']\s*\)'
    for encoded in re.findall(b64_pattern, content):
        try:
            decoded = base64.b64decode(encoded).decode('utf-8', errors='ignore')
            ids = re.findall(r'\b(\d{15,16})\b', decoded)
            pixel_ids.extend(ids)
        except Exception:
            pass

    # URL-encoded strings
    try:
        decoded_content = unquote(content)
        if decoded_content != content:
            ids = re.findall(
                r'fbq\s*\(\s*["\']init["\']\s*,\s*["\'](\d{15,16})["\']',
                decoded_content
            )
            pixel_ids.extend(ids)
    except Exception:
        pass

    return list(set(pixel_ids)) if pixel_ids else None
```

This required adding `import base64` and `from urllib.parse import unquote` to the imports.

---

### Extension 5 -- Non-GTM Tag Manager Detection (Tealium, Adobe Launch, Segment)

**Output file:** `pixels_found.json` | **state_type:** `PIXEL_TEALIUM`, `PIXEL_ADOBE_LAUNCH`, or `PIXEL_SEGMENT`

The original crawler only knew about Google Tag Manager. Enterprise sites in the Tranco top 50K frequently use Tealium iQ, Adobe Launch (DTM), or Segment to deploy their Facebook Pixel. When the pixel is loaded exclusively through one of these platforms, the ID exists only inside the remote tag manager configuration file, not in the page HTML.

The extension adds `search_in_other_tag_managers()`, which scans `<script src="...">` tags for known tag manager URLs, fetches the remote configuration, and extracts pixel IDs from the response body:

```python
def search_in_other_tag_managers(domain, html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    results = {}

    for script in soup.find_all('script', src=True):
        src = script.get('src', '')

        # Tealium iQ
        if 'utag.js' in src or 'tealium.com' in src or 'tiqcdn.com' in src:
            try:
                resp = requests.get(src if src.startswith('http') else 'https:' + src,
                                    timeout=5, verify=False)
                ids = extract_fb_pixel_id(resp.text)
                if ids:
                    results['tealium'] = ids
            except Exception:
                pass

        # Adobe Launch / DTM
        if 'adobedtm.com' in src or 'launch-' in src:
            # ... same pattern ...

        # Segment analytics.js
        if 'cdn.segment.com' in src:
            # ... same pattern ...

    return results if results else None
```

This function is called in the static phase after the standard GTM check and the third-party script check both return empty.

---

### Extension 6 -- WordPress and WooCommerce Plugin Detection

**Output file:** `pixels_found.json` | **state_type:** `PIXEL_WORDPRESS`

WordPress powers roughly 40% of all websites. Its ecosystem includes several dedicated Facebook Pixel plugins (PixelYourSite, WooCommerce Facebook Integration, Pixel Caffeine, Official Facebook for WordPress) that inject pixel IDs using plugin-specific variable names and patterns that do not match the standard `fbq('init', ...)` regex.

The extension adds a set of plugin-specific regex patterns and a function that also follows `<script>` tags pointing to `wp-content/plugins/` directories to fetch and scan the remote JavaScript:

```python
wp_pixel_patterns = [
    r'pys_fb_pixel_id\s*[:=]\s*["\'](\d{15,16})["\']',           # PixelYourSite
    r'wc_facebook_pixel_id\s*[:=]\s*["\'](\d{15,16})["\']',      # WooCommerce FB
    r'pixel_coffee\s*[:=]\s*\{[^}]*id\s*[:=]\s*["\'](\d{15,16})', # Pixel Caffeine
    r'officialfacebookpixel.*?pixel_id.*?(\d{15,16})',            # Official FB for WP
    r'FacebookPixelPlugin.*?pixel_id\s*[:=]\s*["\'](\d{15,16})', # Generic FB WP Plugin
    r'"facebookPixelId"\s*:\s*"(\d{15,16})"',                     # JSON config
    r'"fbPixelId"\s*:\s*"(\d{15,16})"',                           # JSON config variant
]

def search_wordpress_pixel_plugins(domain, html_content):
    all_ids = []
    for pattern in wp_pixel_patterns:
        matches = re.findall(pattern, html_content)
        if matches:
            all_ids.extend(matches)

    # Also follow WP plugin script URLs and scan the remote JS
    if 'wp-content/plugins/' in html_content:
        soup = BeautifulSoup(html_content, 'html.parser')
        for script in soup.find_all('script', src=True):
            src = script.get('src', '')
            if 'wp-content/plugins/' in src and ('facebook' in src.lower() or 'pixel' in src.lower()):
                try:
                    resp = requests.get(
                        src if src.startswith('http') else 'https://' + domain + src,
                        timeout=5, verify=False
                    )
                    ids = extract_fb_pixel_id(resp.text)
                    if ids:
                        all_ids.extend(ids)
                except Exception:
                    pass

    return list(set(all_ids)) if all_ids else None
```

---

### Extension 7 -- Resource Prefetch Hinting

**Output file:** N/A (triggers headless fallback) | **state_type:** Causes domain to enter `second_run` headless queue

Some sites delay loading the Pixel script until user interaction, but they expose their intent to track via HTML `<link>` prefetch hints (e.g., `<link rel="preconnect" href="https://connect.facebook.net">`). The original crawler ignored these entirely.

The extension scans `<link>` elements for `preconnect`, `dns-prefetch`, or `prefetch` relations pointing to Meta endpoints. If found, the domain is flagged for headless deep-inspection even when no standard scripts are detected.

```python
# At the end of the static detection cascade, before declaring "found_nothing"
fb_link_hint = False
try:
    link_soup = BeautifulSoup(content, 'html.parser')
    for link in link_soup.find_all('link', rel=True):
        rel = ' '.join(link.get('rel', []))
        href = link.get('href', '')
        if ('preconnect' in rel or 'dns-prefetch' in rel or 'prefetch' in rel):
            if ('facebook' in href or 'fbevents' in href or 'connect.facebook.net' in href):
                fb_link_hint = True
                break
except:
    pass

if len(check_website_facebook(content)) > 0 or fb_link_hint:
    result['second_run'] = True  # send to headless phase
else:
    result['found_nothing'] = True
```

---

### Extension 8 -- Static Detection Cascade Order

**Output file:** `pixels_found.json` | **state_type:** Varies by method

The original static phase tried: basecode, then wild basecode, then GTM, then third-party scripts, then gave up. The extension inserts the new detection methods into the cascade so that every domain passes through the full pipeline before being declared empty:

```
1. identify_fbp_basecode            --> PIXEL_CORE
2. identify_fbp_basecode_in_the_wild --> PIXEL_WILD
3. search_in_gtm                    --> PIXEL_GTM
4. find_fbp_on_other_thirdparties   --> PIXEL_IN_OTHER_TP
5. search_in_other_tag_managers     --> PIXEL_TEALIUM / PIXEL_ADOBE_LAUNCH / PIXEL_SEGMENT
6. search_wordpress_pixel_plugins   --> PIXEL_WORDPRESS
7. decode_obfuscated_pixel_ids      --> PIXEL_OBFUSCATED
8. Link prefetch hint check         --> (sends to headless queue)
```

Steps 5, 6, and 7 are entirely new and do not exist in the original crawler.

---

## Headless Detection Improvements

---

### Extension 9 -- Bot-Protection Evasion

**Output file:** `state_fbq.json` | **state_type:** Reduces `BLOCKED_BY_BOT_PROTECTION` count

Headless Chrome is trivially detected by Web Application Firewalls (Cloudflare, Akamai, PerimeterX). The original crawler used a user-agent string and nothing else. Sites returned challenge pages or 403 Forbidden responses, causing the crawler to silently record "found nothing."

The extension strips all automation indicators:

**Original:**
```python
chrome_options.add_argument("--headless=new")
chrome_options.add_argument("--no-sandbox")
# No anti-detection measures
```

**Extension:**
```python
chrome_options.add_argument("--headless=new")
chrome_options.add_argument("--no-sandbox")

# Strip automation signals from Chrome
chrome_options.add_argument('--disable-blink-features=AutomationControlled')
chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
chrome_options.add_experimental_option('useAutomationExtension', False)

# After driver creation -- hide navigator.webdriver via CDP
driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
    "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
})
```

Additionally, the extension now explicitly detects when a challenge page has been served and labels the domain accordingly:

```python
page_title = driver.title.lower() if driver.title else ''
challenge_indicators = ['just a moment', 'attention required', 'checking your browser',
                        'access denied', 'please wait', 'ddos-guard', 'verification',
                        'you are being redirected', 'security check']
if any(ind in page_title for ind in challenge_indicators):
    return 'BLOCKED_BY_BOT_PROTECTION', None
```

---

### Extension 10 -- Consent Wall Auto-Accept

**Output file:** `state_fbq.json` | **state_type:** Enables standard detection (`FBP`, `GTM`, `HTML`)

GDPR/CCPA cookie consent banners block tracking scripts from loading until the user explicitly accepts. The original crawler never interacted with these banners, so any site using a Consent Management Platform returned empty results.

The extension implements a two-pass consent dismissal strategy:

1. **CSS selector pass:** targets known consent platform IDs (OneTrust, CookieBot, Usercentrics, generic classes).
2. **Text matching pass:** falls back to scanning all `<button>` elements for common acceptance phrases.

```python
# Pass 1: known selectors
consent_selectors = [
    '#onetrust-accept-btn-handler',
    '#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll',
    '#CybotCookiebotDialogBodyButtonAccept',
    '[data-testid="uc-accept-all-button"]',
    '.cc-accept', '.cc-allow', '.cc-dismiss',
    '#accept-cookies', '#cookie-accept', '#acceptAll',
    'button[data-action="accept"]',
    '.gdpr-accept', '.cookie-consent-accept',
]
for selector in consent_selectors:
    try:
        btn = driver.find_element(By.CSS_SELECTOR, selector)
        if btn.is_displayed():
            btn.click()
            break
    except:
        pass

# Pass 2: button text matching
consent_texts = ['accept all', 'accept cookies', 'i agree', 'agree', 'allow all',
                 'accept', 'ok', 'got it', 'allow cookies', 'consent']
buttons = driver.find_elements(By.TAG_NAME, 'button')
for btn in buttons:
    btn_text = btn.text.strip().lower()
    if btn_text and any(ct == btn_text for ct in consent_texts) and btn.is_displayed():
        btn.click()
        break

time.sleep(2)  # wait for trackers to load after consent
```

---

### Extension 11 -- Namespace Obfuscation Defeat (`_fbq` and `fbq.queue`)

**Output file:** `state_fbq.json` | **state_type:** `FBP`

Sites sometimes rename the global tracker from `window.fbq` to `window._fbq` to evade adblockers. Additionally, if the pixel initializes but the network request has not yet fired, the IDs remain trapped inside the internal `fbq.queue` array and never appear in `fbq.getState()`.

**Original -- only checks standard `fbq`:**
```javascript
if (typeof fbq !== 'undefined' && typeof fbq.getState === 'function') {
    const state = fbq.getState();
    if (state && state.pixels && state.pixels.length > 0) {
        return JSON.stringify(state);
    }
}
return null;
```

**Extension -- checks `_fbq` variant and parses initialization queue:**
```javascript
// Standard check
if (typeof fbq !== 'undefined' && typeof fbq.getState === 'function') {
    try {
        const state = fbq.getState();
        if (state && state.pixels && state.pixels.length > 0) {
            return JSON.stringify(state);
        }
    } catch (e) {}
}
// Underscore variant
if (typeof _fbq !== 'undefined' && typeof _fbq.getState === 'function') {
    try {
        const state = _fbq.getState();
        if (state && state.pixels && state.pixels.length > 0) {
            return JSON.stringify(state);
        }
    } catch (e) {}
}
// Initialization queue
if (typeof fbq !== 'undefined' && fbq.queue) {
    try {
        var queueStr = JSON.stringify(fbq.queue);
        var initMatch = queueStr.match(/init["'],\s*["'](\d{15,16})["']/g);
        if (initMatch && initMatch.length > 0) {
            var ids = initMatch.map(function(m) {
                var id = m.match(/(\d{15,16})/);
                return id ? {id: id[1]} : null;
            }).filter(Boolean);
            if (ids.length > 0) return JSON.stringify({pixels: ids});
        }
    } catch (e) {}
}
return null;
```

---

### Extension 12 -- Expanded Network Interception and CAPI POST Body Inspection

**Output file:** `state_fbq.json` | **state_type:** `CAPI_OR_NETWORK`

The original crawler intercepted Chrome performance logs and checked for GET requests to `facebook.com/tr/`, extracting the pixel ID from URL parameters. Modern Conversions API (CAPI) implementations use POST requests to `graph.facebook.com` with JSON payloads containing the pixel ID. These were entirely invisible to the original crawler.

The extension makes three changes:

1. **Expanded endpoint list:** adds `graph.facebook.com`, `connect.facebook.net/signals/`, `pixel.facebook.com`, `capig.facebook.com` (CAPI Gateway), regional variants (`web.facebook.com`, `m.facebook.com`), and `business.facebook.com`.
2. **First-party proxy detection:** adds a regex catch for any URL matching `/tr?...id=<15-16 digits>`, which catches domains that proxy Facebook tracking calls through their own infrastructure.
3. **POST body parsing:** extracts pixel IDs from the `postData` field of intercepted requests.

**Original:**
```python
if 'facebook.com/tr/' in url or '/events?' in url or '/.tr?' in url:
    match = re.search(r'id=(\d+)', url)
    if match:
        network_pixel_ids.append(match.group(1))
```

**Extension:**
```python
if ('facebook.com/tr' in url or '/events?' in url or '/.tr?' in url or
        'graph.facebook.com' in url or 'connect.facebook.net/signals/' in url or
        'pixel.facebook.com' in url or
        'capig.facebook.com' in url or
        'web.facebook.com/tr' in url or
        'm.facebook.com/tr' in url or
        'business.facebook.com' in url or
        re.search(r'/tr\?.*id=\d{15,16}', url)):
    # Extract from URL GET params
    match = re.search(r'id=(\d+)', url)
    if match:
        network_pixel_ids.append(match.group(1))
    # Extract pixel_id param (first-party proxies)
    match_pid = re.search(r'pixel_id=(\d{15,16})', url)
    if match_pid:
        network_pixel_ids.append(match_pid.group(1))
    # Extract from POST body (CAPI payloads)
    post_data = request_data.get("postData", "")
    if post_data:
        post_ids = re.findall(
            r'(?:"id"|"pixel_id"|"pixelId")\s*[:"]\s*"?(\d{15,16})"?',
            post_data
        )
        network_pixel_ids.extend(post_ids)
```

Enabling performance logging itself required adding `DesiredCapabilities`:
```python
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
# ...
chrome_options.set_capability("goog:loggingPrefs", {"performance": "ALL"})
```

---

### Extension 13 -- Multi-Cookie Detection

**Output file:** `state_fbq.json` | **state_type:** Triggers the deep extraction cascade

The original crawler only checked for the `_fbp` (Facebook Pixel browser) cookie. The extension also checks for `_fbc` (Facebook Click ID, set when a user arrives via a Facebook ad click) and `fr` (Facebook's encrypted tracking cookie). Any of these cookies indicates active Meta tracking and triggers the deep extraction cascade even when `fbq.getState()` returns nothing.

**Original:**
```python
for cookie in cookies:
    if cookie['name'] == '_fbp':
        fbp_cookie_present = True
```

**Extension:**
```python
fb_cookie_names = {'_fbp', '_fbc', 'fr'}
for cookie in cookies:
    if cookie['name'] in fb_cookie_names:
        fbp_cookie_present = True
        break
```

---

### Extension 14 -- Deep Extraction: LocalStorage and SessionStorage

**Output file:** `state_fbq.json` | **state_type:** `DEEP_EXTRACTION_LOCALSTORAGE` or `DEEP_EXTRACTION_SESSIONSTORAGE`

Many Shopify apps (Parkour, Trekkie) and third-party tracking managers store pixel configurations in the browser's Web Storage APIs to survive page reloads and inject the pixel via isolated background scripts. These values never appear in the page source or in `fbq.getState()`.

The extension dumps both `localStorage` and `sessionStorage`, filters for keys containing tracking-related keywords, and scans the values for 15--16 digit numbers:

```javascript
// localStorage scan
var results = [];
for (var i = 0; i < localStorage.length; i++) {
    var key = localStorage.key(i);
    if (key.toLowerCase().includes('pixel') || key.toLowerCase().includes('facebook') ||
        key.toLowerCase().includes('fb') || key.toLowerCase().includes('parkour') ||
        key.toLowerCase().includes('trekkie')) {
        results.push(localStorage.getItem(key));
    }
}
return results;
```

The `sessionStorage` scan uses the same logic.

---

### Extension 15 -- Deep Extraction: Shopify Analytics Objects

**Output file:** `state_fbq.json` | **state_type:** `DEEP_EXTRACTION_SHOPIFY`

Shopify exposes `window.ShopifyAnalytics` and `window.trekkie` objects that contain pixel configurations used by the platform's built-in tracking system. These are distinct from the standard `fbq` global and are never checked by the original crawler:

```javascript
var ids = [];
try {
    var sa = JSON.stringify(window.ShopifyAnalytics);
    var matches = sa.match(/\b\d{15,16}\b/g);
    if (matches) ids = ids.concat(matches);
} catch(e) {}
try {
    var tr = JSON.stringify(window.trekkie);
    var matches = tr.match(/\b\d{15,16}\b/g);
    if (matches) ids = ids.concat(matches);
} catch(e) {}
return ids;
```

---

### Extension 16 -- Deep Extraction: GTM DataLayer, SPA Hydration States, and Web Pixel Sandboxes

**Output file:** `state_fbq.json` | **state_type:** `DEEP_EXTRACTION_DATALAYER`, `DEEP_EXTRACTION_SPA`, or `DEEP_EXTRACTION_WEBPIXELS`

Three related extraction methods that target platform-specific data structures:

**GTM DataLayer:** Google Tag Manager pushes events and configuration data into the `window.dataLayer` array. Pixel IDs staged for server-side GTM firing live here before they ever hit the network:

```javascript
if (window.dataLayer && Array.isArray(window.dataLayer)) {
    var dlStr = JSON.stringify(window.dataLayer);
    if (dlStr.toLowerCase().includes('facebook') || dlStr.toLowerCase().includes('fbq') ||
        dlStr.toLowerCase().includes('pixel')) {
        var matches = dlStr.match(/\b\d{15,16}\b/g);
        if (matches) ids = matches;
    }
}
```

**SPA Hydration States:** React (Next.js), Vue (Nuxt), and other SPA frameworks serialize their server-rendered state into global variables (`__NEXT_DATA__`, `__NUXT__`, `__initialData__`, `__APP_DATA__`) that are injected into the DOM during hydration. Tracking configs are often buried inside these massive JSON objects:

```javascript
var globals = ['__NEXT_DATA__', '__NUXT__', '__initialData', '__APP_DATA__'];
globals.forEach(function(g) {
    if (window[g]) {
        var str = JSON.stringify(window[g]);
        if (str.toLowerCase().includes('facebook') || str.toLowerCase().includes('pixel')) {
            var matches = str.match(/\b\d{15,16}\b/g);
            if (matches) ids = ids.concat(matches);
        }
    }
});
```

**Shopify Web Pixel Sandboxes:** Shopify's "Web Pixels" architecture runs tracking scripts inside isolated, sandboxed `<iframe>` elements (`web-pixel-sandbox-*`) to prevent third-party script conflicts. The pixel ID is embedded directly in the iframe's `src` URL:

```javascript
var iframes = document.querySelectorAll(
    'iframe[id*="web-pixel"], iframe[src*="web-pixel"], iframe[src*="myshopify.com"]'
);
iframes.forEach(function(iframe) {
    var src = iframe.getAttribute('src') || '';
    var matches = src.match(/\b\d{15,16}\b/g);
    if (matches) ids = ids.concat(matches);
});
```

---

### Extension 17 -- SendBeacon API Interception

**Output file:** `state_fbq.json` | **state_type:** `DEEP_EXTRACTION_BEACON`

Modern tracking implementations increasingly use `navigator.sendBeacon()` for reliable event delivery because it survives page unloads. These calls may not appear in Chrome DevTools network logs.

The extension injects a monkey-patch *before* the page loads (via CDP `Page.addScriptToEvaluateOnNewDocument`) that captures all beacon calls:

```python
driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
    "source": """
        (function() {
            var origBeacon = navigator.sendBeacon;
            window.__beaconCalls = [];
            navigator.sendBeacon = function(url, data) {
                window.__beaconCalls.push({url: url, data: data ? data.toString() : ''});
                return origBeacon.apply(navigator, arguments);
            };
        })();
    """
})
```

After the page loads, intercepted calls are read back and scanned:

```python
beacons = driver.execute_script("return window.__beaconCalls || []")
for b in beacons:
    beacon_url = b.get('url', '')
    beacon_data = b.get('data', '')
    if 'facebook.com' in beacon_url or 'fbevents' in beacon_url:
        match = re.search(r'id=(\d{15,16})', beacon_url)
        if match:
            deep_extracted_ids.append(match.group(1))
```

---

### Extension 18 -- `eval()` and `new Function()` Interception

**Output file:** `state_fbq.json` | **state_type:** `DEEP_EXTRACTION_EVAL`

Scam sites use `eval()`-based loaders to dynamically construct pixel initialization code at runtime, making it invisible to both static analysis and standard network interception. The extension injects a monkey-patch that captures any `eval()` call whose argument contains Facebook-related keywords:

```python
driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
    "source": """
        (function() {
            var origEval = window.eval;
            window.__evalCalls = [];
            window.eval = function(code) {
                if (typeof code === 'string' &&
                    (code.includes('fbq') || code.includes('facebook') || code.includes('pixel'))) {
                    window.__evalCalls.push(code.substring(0, 3000));
                }
                return origEval.call(window, code);
            };
        })();
    """
})
```

After the page loads, the captured code fragments are scanned for 15--16 digit pixel IDs:

```python
eval_calls = driver.execute_script("return window.__evalCalls || []")
for code in eval_calls:
    if code:
        ids = re.findall(r'\b(\d{15,16})\b', str(code))
        if ids:
            deep_extracted_ids.extend(ids)
```

---

### Extension 19 -- Wix and Squarespace Platform Detection

**Output file:** `state_fbq.json` | **state_type:** `DEEP_EXTRACTION_WIX` or `DEEP_EXTRACTION_SQUARESPACE`

Both platforms have millions of active sites in the Tranco lists and use proprietary data structures to store pixel configurations.

**Wix** stores pixel configs in `window.warmupData`, `window.wixDevelopersAnalytics`, and `window.wixAnalytics`:

```javascript
var ids = [];
try {
    if (window.warmupData) {
        var str = JSON.stringify(window.warmupData);
        if (str.toLowerCase().includes('facebook') || str.toLowerCase().includes('pixel')) {
            var matches = str.match(/\b\d{15,16}\b/g);
            if (matches) ids = ids.concat(matches);
        }
    }
} catch(e) {}
// Similar blocks for window.wixDevelopersAnalytics and window.wixAnalytics
```

**Squarespace** embeds pixel IDs in inline JSON config blocks:

```python
sq_patterns = [
    r'"facebookPixelId"\s*:\s*"(\d{15,16})"',
    r'"fbPixelId"\s*:\s*"(\d{15,16})"',
    r'"facebook_pixel_id"\s*:\s*"(\d{15,16})"',
]
for pattern in sq_patterns:
    matches = re.findall(pattern, page_source)
    sq_ids.extend(matches)
```

---

## State Type Quick Reference

The following table maps each `state_type` to the extension that produces it and the output file where it appears.

| state_type | Output File | Extension | Phase |
|---|---|---|---|
| `PIXEL_CORE` | `pixels_found.json` | 3 (bug fix) | Static |
| `PIXEL_WILD` | `pixels_found.json` | -- (original) | Static |
| `PIXEL_GTM` | `pixels_found.json` | 2 (parallelized) | Static |
| `PIXEL_IN_OTHER_TP` | `pixels_found.json` | -- (original) | Static |
| `PIXEL_TEALIUM` | `pixels_found.json` | 5 | Static |
| `PIXEL_ADOBE_LAUNCH` | `pixels_found.json` | 5 | Static |
| `PIXEL_SEGMENT` | `pixels_found.json` | 5 | Static |
| `PIXEL_WORDPRESS` | `pixels_found.json` | 6 | Static |
| `PIXEL_OBFUSCATED` | `pixels_found.json` | 4 | Static |
| `BLOCKED_BY_BOT_PROTECTION` | `state_fbq.json` | 9 (detection) | Headless |
| `FBP` | `state_fbq.json` | 11 (enhanced) | Headless |
| `GTM` | `state_fbq.json` | -- (original) | Headless |
| `HTML` | `state_fbq.json` | -- (original) | Headless |
| `CAPI_OR_NETWORK` | `state_fbq.json` | 12 | Headless |
| `DEEP_EXTRACTION_LOCALSTORAGE` | `state_fbq.json` | 14 | Headless |
| `DEEP_EXTRACTION_SESSIONSTORAGE` | `state_fbq.json` | 14 | Headless |
| `DEEP_EXTRACTION_SHOPIFY` | `state_fbq.json` | 15 | Headless |
| `DEEP_EXTRACTION_SOURCE` | `state_fbq.json` | -- (full source scan) | Headless |
| `DEEP_EXTRACTION_INLINE` | `state_fbq.json` | -- (inline script scan) | Headless |
| `DEEP_EXTRACTION_DATALAYER` | `state_fbq.json` | 16 | Headless |
| `DEEP_EXTRACTION_SPA` | `state_fbq.json` | 16 | Headless |
| `DEEP_EXTRACTION_WEBPIXELS` | `state_fbq.json` | 16 | Headless |
| `DEEP_EXTRACTION_BEACON` | `state_fbq.json` | 17 | Headless |
| `DEEP_EXTRACTION_EVAL` | `state_fbq.json` | 18 | Headless |
| `DEEP_EXTRACTION_WIX` | `state_fbq.json` | 19 | Headless |
| `DEEP_EXTRACTION_SQUARESPACE` | `state_fbq.json` | 19 | Headless |
| `DEEP_EXTRACTION_OBFUSCATED` | `state_fbq.json` | 4 | Headless |

---

## Validation Pipeline

All pixel IDs recovered by the extensions (whether from static HTML, CAPI POST bodies, localStorage, or eval interception) are passed to the downstream `get_PII_from_configs.py` script. This script validates each candidate ID against Meta's configuration endpoint (`connect.facebook.net/signals/config/{id}`). IDs that do not return a valid configuration (such as timestamps that happen to be 15--16 digits) are automatically filtered out. Only validated IDs proceed to the PII parameter analysis.
