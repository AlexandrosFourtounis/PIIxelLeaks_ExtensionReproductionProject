# New Extension Proposals — Dataset-Driven Gap Analysis

> [!IMPORTANT]
> This analysis is based on studying the **Tranco top 50K**, **1,001 scam domains**, **100 malicious domains**, **20,472 active suspicious domains**, and all existing CrawlerOutputs.

---

## Dataset Key Findings

| Metric | Value |
|---|---|
| Top 10K domains that "found nothing" | **3,455 (34.5%)** |
| Top 10K timeouts | 2,239 |
| Top 10K invalid HTML (likely bot-blocked) | 1,468 |
| Scam domains WITH pixels | 443 / 1,001 (44%) |
| Active suspicious domains with NO pixels | ~20,300 / 20,472 (99%) |
| Dominant detection for legitimate sites | PIXEL_GTM |
| Dominant detection for scam sites | PIXEL_CORE (direct HTML) |

### Domains That SHOULD Have Pixels But Don't (Detection Gaps)

Major sites in `found_nothing.txt` that almost certainly use Meta tracking:
- **E-commerce**: amazon.com, shopify.com, ebay.com, walmart.com, target.com, nike.com, shein.com
- **News/Media**: bbc.com, washingtonpost.com, forbes.com, time.com
- **Streaming**: netflix.com, spotify.com, twitch.tv

These are missed due to **bot protection**, **non-GTM tag managers**, and **server-side tracking**.

---

## Proposed Extensions (Prioritized)

---

### 🔴 Extension 1: Anti-Bot-Detection for Headless Browser

**Priority: CRITICAL** — ~1,468 domains return invalid HTML because they detect our headless browser.

**Problem:** The crawler uses a vanilla Selenium ChromeDriver with only a user-agent string. Sites using Cloudflare, Akamai, or custom bot protection serve challenge pages instead of real content. The crawler silently records "found nothing."

**Current code:**
```python
chrome_options.add_argument('user-agent=Mozilla/5.0 ...')
# That's it — no anti-detection whatsoever
```

**Proposed addition:**
```python
# Anti-detection flags
chrome_options.add_argument('--disable-blink-features=AutomationControlled')
chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
chrome_options.add_experimental_option('useAutomationExtension', False)

# After driver creation — hide navigator.webdriver
driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
    "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
})
```

**Additionally — detect when we hit a challenge page:**
```python
page_title = driver.title.lower()
challenge_indicators = ['just a moment', 'attention required', 'checking your browser',
                        'access denied', 'please wait', 'ddos-guard', 'verification']
if any(ind in page_title for ind in challenge_indicators):
    return 'BLOCKED_BY_BOT_PROTECTION', None
```

**Expected impact:** Could recover hundreds of domains from `invalid_html` and `found_nothing`.

---

### 🔴 Extension 2: Non-GTM Tag Manager Detection (Tealium, Adobe Launch, Segment)

**Priority: CRITICAL** — The crawler has **ZERO** references to any tag manager other than GTM. Enterprise sites in Tranco top 50K heavily use Adobe Launch and Tealium.

**Problem:** When a pixel is deployed via Tealium (`utag.js`) or Adobe Launch (`assets.adobedtm.com`), the pixel ID lives inside the tag manager's config file, not in the page HTML. The crawler never fetches these config files.

**Evidence from datasets:** `nvidia.com` was detected via `PIXEL_IN_OTHER_TP` because its pixel happened to also appear in an inline script. But many Adobe Launch deployments ONLY load the pixel from the remote config.

**Proposed addition — new function `search_in_other_tag_managers()`:**
```python
def search_in_other_tag_managers(domain, html_content):
    """Fetch and scan Tealium, Adobe Launch, and Segment configs for FB pixel IDs."""
    soup = BeautifulSoup(html_content, 'html.parser')
    results = {}
    
    for script in soup.find_all('script', src=True):
        src = script.get('src', '')
        
        # Tealium
        if 'utag.js' in src or 'tealium.com' in src:
            try:
                resp = requests.get(src if src.startswith('http') else 'https:' + src, 
                                    timeout=5, verify=False)
                ids = extract_fb_pixel_id(resp.text)
                if ids:
                    results['tealium'] = ids
            except: pass
        
        # Adobe Launch / DTM
        if 'adobedtm.com' in src or 'launch-' in src:
            try:
                resp = requests.get(src if src.startswith('http') else 'https:' + src, 
                                    timeout=5, verify=False)
                ids = extract_fb_pixel_id(resp.text)
                if ids:
                    results['adobe_launch'] = ids
            except: pass
        
        # Segment
        if 'cdn.segment.com' in src or 'analytics.min.js' in src:
            try:
                resp = requests.get(src if src.startswith('http') else 'https:' + src, 
                                    timeout=5, verify=False)
                ids = extract_fb_pixel_id(resp.text)
                if ids:
                    results['segment'] = ids
            except: pass
    
    return results if results else None
```

**Integration point:** Call in `_process_single_domain()` after GTM check fails.

**Expected impact:** HIGH for Tranco top 50K. Many enterprise sites (finance, media, retail) use these.

---

### 🔴 Extension 3: WordPress / WooCommerce Plugin Detection

**Priority: HIGH** — WordPress powers ~40% of all websites. ZERO WP-specific detection exists.

**Problem:** WordPress Facebook Pixel plugins (PixelYourSite, Official Facebook for WordPress, Pixel Caffeine, WooCommerce Facebook Integration) inject pixel IDs using plugin-specific patterns that don't match the standard `fbq('init', ...)` regex.

**Evidence from datasets:** `stanford.edu` was detected via `PIXEL_IN_OTHER_TP` — it uses a custom WP plugin (`stanford-fb-pixel/pixel.js`).

**Proposed addition — WP-specific regex patterns:**
```python
wp_pixel_patterns = [
    r'pys_fb_pixel_id\s*[:=]\s*["\'](\d{15,16})["\']',           # PixelYourSite
    r'wc_facebook_pixel_id\s*[:=]\s*["\'](\d{15,16})["\']',      # WooCommerce FB
    r'pixel_coffee\s*[:=]\s*{[^}]*id\s*[:=]\s*["\'](\d{15,16})', # Pixel Caffeine  
    r'officialfacebookpixel.*?pixel_id.*?(\d{15,16})',            # Official FB for WP
    r'FacebookPixelPlugin.*?pixel_id\s*[:=]\s*["\'](\d{15,16})', # Generic FB WP Plugin
    r'wp-content/plugins/.*?facebook.*?pixel',                     # WP plugin path hint
]
```

**Integration point:** Add to `get_fb_patterns()` or as a new check in `_process_single_domain()`.

**Expected impact:** HIGH across both Tranco and scam datasets. Many scam stores run on WordPress/WooCommerce.

---

### 🟠 Extension 4: Base64 / Obfuscation Decoding

**Priority: HIGH for scam dataset** — Scam/malicious sites frequently obfuscate pixel configurations.

**Problem:** ZERO obfuscation handling exists. No references to `base64`, `atob`, `eval`, `encodeURI`, or any obfuscation detection. Scam sites use `atob('MTIzNDU2Nzg5MDEyMzQ1')` to hide pixel IDs.

**Proposed addition:**
```python
import base64

def decode_obfuscated_pixel_ids(content):
    """Decode base64-encoded and eval'd strings that might contain pixel IDs."""
    pixel_ids = []
    
    # Base64: atob('...') calls
    b64_pattern = r'atob\s*\(\s*["\']([A-Za-z0-9+/=]+)["\']\s*\)'
    for encoded in re.findall(b64_pattern, content):
        try:
            decoded = base64.b64decode(encoded).decode('utf-8', errors='ignore')
            ids = re.findall(r'\b(\d{15,16})\b', decoded)
            pixel_ids.extend(ids)
        except: pass
    
    # URL-encoded strings
    try:
        from urllib.parse import unquote
        decoded_content = unquote(content)
        if decoded_content != content:
            ids = re.findall(r'fbq\s*\(\s*["\']init["\']\s*,\s*["\'](\d{15,16})["\']', decoded_content)
            pixel_ids.extend(ids)
    except: pass
    
    return list(set(pixel_ids)) if pixel_ids else None
```

**Expected impact:** HIGH for scam/malicious datasets. LOW for Tranco.

---

### 🟠 Extension 5: `navigator.sendBeacon` Interception

**Priority: HIGH** — Modern tracking implementations increasingly use `sendBeacon()` for reliable event delivery. This is NOT captured by standard network logging.

**Problem:** `sendBeacon()` fires tracking events that may not appear in Chrome DevTools `Network.requestWillBeSent` logs.

**Proposed addition — inject monkey-patch BEFORE page load:**
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

Then later read intercepted calls:
```python
beacons = driver.execute_script("return window.__beaconCalls || []")
for b in beacons:
    if 'facebook.com' in b.get('url', ''):
        match = re.search(r'id=(\d+)', b['url'])
        if match:
            network_pixel_ids.append(match.group(1))
```

**Expected impact:** MEDIUM across both datasets.

---

### 🟠 Extension 6: Wix & Squarespace Platform Detection

**Priority: MEDIUM** — Both platforms have millions of active sites in Tranco lists.

**Wix** stores pixel configs in `window.warmupData`, `window.wixAnalytics`, or Wix's component model:
```python
# Wix detection
wix_ids = driver.execute_script("""
    var ids = [];
    try {
        if (window.warmupData) {
            var str = JSON.stringify(window.warmupData);
            var matches = str.match(/\\b\\d{15,16}\\b/g);
            if (matches) ids = ids.concat(matches);
        }
    } catch(e) {}
    try {
        if (window.wixDevelopersAnalytics) {
            var str = JSON.stringify(window.wixDevelopersAnalytics);
            var matches = str.match(/\\b\\d{15,16}\\b/g);
            if (matches) ids = ids.concat(matches);
        }
    } catch(e) {}
    return ids;
""")
```

**Squarespace** embeds pixel IDs in inline JSON:
```python
# Squarespace detection
squarespace_patterns = [
    r'"facebookPixelId"\s*:\s*"(\d{15,16})"',
    r'"fbPixelId"\s*:\s*"(\d{15,16})"',
]
```

**Expected impact:** MEDIUM for Tranco. LOW for scam dataset.

---

### 🟡 Extension 7: Additional Meta Network Endpoints

**Priority: LOW effort / MEDIUM impact** — Currently missing several Meta domains.

**Currently checked:**
- `facebook.com/tr`, `/events?`, `/.tr?`
- `graph.facebook.com`, `connect.facebook.net/signals/`, `pixel.facebook.com`

**Missing endpoints to add:**
```python
if ('facebook.com/tr' in url or '/events?' in url or '/.tr?' in url or
    'graph.facebook.com' in url or 'connect.facebook.net/signals/' in url or
    'pixel.facebook.com' in url or
    # NEW endpoints:
    'capig.facebook.com' in url or      # CAPI Gateway
    'web.facebook.com/tr' in url or     # Alternative regional domain
    'm.facebook.com/tr' in url or       # Mobile domain
    'business.facebook.com' in url):    # Business API
```

**Expected impact:** LOW additional pixels, but important for completeness.

---

### 🟡 Extension 8: First-Party Proxy Detection

**Priority: MEDIUM** — Growing trend where sites proxy `facebook.com/tr` through their own domain.

**Problem:** To avoid adblockers, some sites route tracking calls through `example.com/fb/tr?id=...` or `tracking.example.com/events?pixel_id=...`. These never hit `facebook.com` at all.

**Proposed heuristic:**
```python
# In network interception, also check for first-party proxy patterns
if re.search(r'/tr\?.*id=\d{15,16}', url) or re.search(r'/events\?.*pixel_id=\d{15,16}', url):
    match = re.search(r'(?:id|pixel_id)=(\d{15,16})', url)
    if match:
        network_pixel_ids.append(match.group(1))
```

---

### 🟡 Extension 9: `eval()` / `new Function()` Interception

**Priority: MEDIUM for scam sites** — Scam sites use eval-based loaders to construct pixel code at runtime.

```python
driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
    "source": """
        (function() {
            var origEval = window.eval;
            window.__evalCalls = [];
            window.eval = function(code) {
                if (typeof code === 'string' && 
                    (code.includes('fbq') || code.includes('facebook') || code.includes('pixel'))) {
                    window.__evalCalls.push(code.substring(0, 2000));
                }
                return origEval.call(window, code);
            };
        })();
    """
})
```

---

## Scam-Specific Insights

> [!NOTE]
> These findings are unique to the suspicious/scam dataset and may warrant specialized detection.

| Pattern | Finding |
|---|---|
| **Pixel density** | Scam sites load **10-38 pixel IDs per page** (vs 1-3 for legitimate). Sites with >5 IDs are almost certainly scam. |
| **Detection method** | Scam sites use `PIXEL_CORE` (direct HTML), NOT GTM. |
| **Runtime state** | Scam sites show `FBP` state_type, not GTM. |
| **Double-quoted IDs** | Template pattern: `"\"836386055474185\""` — fingerprint of specific scam templates. |
| **Key registrars** | NameCheap (37), Tucows (17), PDR (16), West263/Alibaba (28) |
| **Infrastructure** | Most hosted behind Cloudflare or on Shopify (23.227.38.x) |

---

## Summary — Priority Matrix

| # | Extension | Tranco 50K Impact | Scam Impact | Effort | Implement? |
|---|---|---|---|---|---|
| 1 | Anti-bot-detection flags | 🔴 Very High | 🟠 Medium | Very Low | ✅ Yes |
| 2 | Non-GTM tag managers (Tealium/Adobe/Segment) | 🔴 Very High | 🟡 Low | Medium | ✅ Yes |
| 3 | WordPress/WooCommerce plugin patterns | 🔴 Very High | 🟠 Medium | Low | ✅ Yes |
| 4 | Base64/obfuscation decoding | 🟡 Low | 🔴 Very High | Low | ✅ Yes |
| 5 | Beacon API interception | 🟠 Medium | 🟠 Medium | Low | ✅ Yes |
| 6 | Wix/Squarespace detection | 🟠 Medium | 🟡 Low | Medium | ? |
| 7 | Additional Meta endpoints | 🟡 Low | 🟡 Low | Very Low | ✅ Yes |
| 8 | First-party proxy detection | 🟠 Medium | 🟠 Medium | Low | ? |
| 9 | eval() interception | 🟡 Low | 🟠 Medium | Low | ? |

> [!IMPORTANT]
> **Which extensions should I implement?** Extensions 1-5 and 7 are recommended as high-value, low-to-medium effort. Extensions 6, 8, and 9 are optional and depend on your research scope.
