# PII_Hybrid_Crawler Code Comparison & Improvements

This document provides a detailed side-by-side comparison between the original `PII_Hybrid_Crawler.py` and the extended `PII_Hybrid_Crawler_Extension.py`. It proves exactly why the new methodology works better by addressing edge cases, bypassing obfuscation, and digging deeper into the browser state.

---

## 1. Static Parsing: Bug Fixes in Basecode Detection
**Why the extension works better:** The original static parsers (`identify_fbp_basecode` and `identify_fbp_basecode_in_the_wild`) contained a bug where the loop would `return` prematurely upon finding the *first* script containing an ID. If a website had multiple `<script>` tags, but the first one was malformed or missing the ID, it would exit the loop completely and miss the actual Pixel IDs lower down the page. The extension aggregates all IDs across *all* script tags.

**Original Code (`PII_Hybrid_Crawler.py`):**
```python
    for script in script_tags:
      script_content = str(script)
      if any(keyword in script_content for keyword in keywords):
        init_calls = re.findall(pattern_init, script_content)
        track_calls = re.findall(pattern_track, script_content)

        if init_calls or track_calls:
            pixels_found.append({"domain": domain, "init": init_calls})
            return pixels_found # ❌ Bug: Exits function on first match
```

**Extended Code (`PII_Hybrid_Crawler_Extension.py`):**
```python
    for script in script_tags:
      script_content = str(script)
      if any(keyword in script_content for keyword in keywords):
        init_calls = re.findall(pattern_init, script_content)
        track_calls = re.findall(pattern_track, script_content)

        if init_calls or track_calls:
            pixels_found.append({"domain": domain, "init": init_calls})
            # ✅ Fix: Removed early return. Accumulates all pixels!
            
    return pixels_found if pixels_found else None # Return after checking ALL scripts
```

---

## 2. Advanced Consent Wall Bypassing
**Why the extension works better:** Headless browsers often hit walls where tracking scripts (like Facebook Pixel) are strictly paused until the user explicitly accepts cookies (GDPR/CCPA compliance). The original crawler would just stare at the cookie banner and find nothing. The extended crawler executes JavaScript heuristics to aggressively seek out and click "Accept All" buttons (OneTrust, CookieBot, etc.) before checking for pixels.

**Original Code (`PII_Hybrid_Crawler.py`):**
```python
        print(f"Loading {domain}...")
        driver.get(domain)
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.TAG_NAME, 'body'))
        )
        print("Page loaded, checking for Facebook Pixel...")
        # ❌ Immediately begins searching for pixels. Tracking is blocked by CMP.
```

**Extended Code (`PII_Hybrid_Crawler_Extension.py`):**
```python
        # ✅ Automatically accept cookie consent banners to unleash trackers
        try:
            driver.execute_script("""
                const acceptKeywords = ['accept', 'allow', 'agree', 'got it', 'ok'];
                // Check OneTrust, CookieBot, and generic consent IDs
                const buttons = document.querySelectorAll('button, a, [role="button"]');
                for (let btn of buttons) {
                    let text = (btn.textContent || '').toLowerCase();
                    if (acceptKeywords.some(k => text.includes(k)) && 
                        (btn.id.includes('cookie') || btn.className.toLowerCase().includes('cookie') || 
                         btn.id.includes('onetrust') || btn.id.includes('cybot'))) {
                        btn.click();
                        break;
                    }
                }
            """)
            time.sleep(2) # Give pixels time to load after consent
        except Exception:
            pass
```

---

## 3. Resource Prefetching (`<link rel="preconnect">`)
**Why the extension works better:** Some modern sites delay loading the Pixel script until the user interacts with the page, but they expose their intent to track via HTML `<link>` prefetch hints. The original crawler missed these entirely. The extended crawler statically scans for prefetch hints indicating Meta endpoints. If found, it flags the domain for headless deep-inspection even if no standard scripts are found.

**Original Code (`PII_Hybrid_Crawler.py`):**
```python
        # ❌ No preconnect/dns-prefetch logic exists. 
```

**Extended Code (`PII_Hybrid_Crawler_Extension.py`):**
```python
        # ✅ Checks for early DNS resolution hints in the <head>
        prefetch_patterns = [
            r'<link[^>]+rel=["\'](?:preconnect|dns-prefetch)["\'][^>]+href=["\']https://connect\.facebook\.net',
            r'<link[^>]+href=["\']https://connect\.facebook\.net[^>]+rel=["\'](?:preconnect|dns-prefetch)["\']'
        ]
        if any(re.search(p, content) for p in prefetch_patterns):
            pixels_found[domain] = {'PIXEL_HINT': True}
            second_run_stateless.append(domain)
```

---

## 4. Comprehensive Network Interception (POST Bodies)
**Why the extension works better:** The original crawler *did* check network logs for GET requests, but only looked for `facebook.com/tr/` and only parsed the URL parameters (`id=\d+`). Modern Conversions API (CAPI) and advanced Pixel deployments use `POST` requests to `graph.facebook.com` or `/events` sending JSON bodies! The extended crawler parses both the URL *and* the POST data payloads for Pixel IDs.

**Original Code (`PII_Hybrid_Crawler.py`):**
```python
        # Network logging logic (simplified)
        url = request_data["url"]
        # ❌ Only checks GET parameters on specific endpoints
        if 'facebook.com/tr/' in url or '/events?' in url or '/.tr?' in url:
            match = re.search(r'id=(\d+)', url)
            if match:
                network_pixel_ids.append(match.group(1))
```

**Extended Code (`PII_Hybrid_Crawler_Extension.py`):**
```python
        url = request_data["url"]
        # ✅ Expanded endpoint list
        if ('facebook.com/tr' in url or '/events?' in url or '/.tr?' in url or
                'graph.facebook.com' in url or 'connect.facebook.net/signals/' in url or
                'pixel.facebook.com' in url):
            
            # Extract from URL GET params
            match = re.search(r'id=(\d+)', url)
            if match:
                network_pixel_ids.append(match.group(1))
                
            # ✅ Extract from POST body (CAPI payloads)
            post_data = request_data.get("postData", "")
            if post_data:
                post_ids = re.findall(r'(?:"id"|"pixel_id"|"pixelId")\s*[:"]\s*"?(\d{15,16})"?', post_data)
                network_pixel_ids.extend(post_ids)
```

---

## 5. Bypassing Namespace Obfuscation (`_fbq` and `fbq.queue`)
**Why the extension works better:** Sites often rename `window.fbq` to `window._fbq` to evade basic adblockers. Additionally, if the pixel fails to initialize fully, the IDs remain trapped inside the `fbq.queue` array and never materialize into `fbq.getState()`. The extended crawler checks the `_fbq` variant and parses the raw initialization queue.

**Original Code (`PII_Hybrid_Crawler.py`):**
```javascript
        // ❌ Only checks standard state
        if (typeof fbq !== 'undefined' && typeof fbq.getState === 'function') {
            const state = fbq.getState();
            if (state && state.pixels && state.pixels.length > 0) {
                return JSON.stringify(state);
            }
        }
```

**Extended Code (`PII_Hybrid_Crawler_Extension.py`):**
```javascript
        // ✅ Checks standard, underscore variant, and initialization queue
        if (typeof _fbq !== 'undefined' && typeof _fbq.getState === 'function') {
            const state = _fbq.getState(); // ... Extract state
        }
        
        if (typeof fbq !== 'undefined' && fbq.queue) {
            var queueStr = JSON.stringify(fbq.queue);
            var initMatch = queueStr.match(/init["'],\s*["'](\d{15,16})["']/g);
            if (initMatch && initMatch.length > 0) {
                // Extract directly from the initialization command queue
                return JSON.stringify({pixels: ids});
            }
        }
```

---

## 6. Multi-Cookie Detection
**Why the extension works better:** The original crawler only checked for the `_fbp` cookie. The extended crawler also checks for `_fbc` (Facebook Click ID) and `fr` (Facebook tracking), which are highly indicative of tracking behavior even if `_fbp` is blocked by a privacy extension.

**Original Code (`PII_Hybrid_Crawler.py`):**
```python
        # ❌ Only looks for _fbp
        cookies = driver.get_cookies()
        for cookie in cookies:
            if cookie['name'] == '_fbp':
                fbp_cookie_present = True
```

**Extended Code (`PII_Hybrid_Crawler_Extension.py`):**
```python
        # ✅ Checks comprehensive Meta cookie suite
        cookies = driver.get_cookies()
        fb_cookie_names = {'_fbp', '_fbc', 'fr'}
        for cookie in cookies:
            if cookie['name'] in fb_cookie_names:
                fbp_cookie_present = True
```

---

## 7. Deep Extraction Methods (The "Invisible" Trackers)
**Why the extension works better:** The most significant addition is the **Deep Extraction Suite**. If the crawler detects evidence of tracking (via cookies or network) but `fbq.getState()` returns nothing, the original crawler would give up. The extended crawler systematically tears down the browser environment to find where the configuration is hidden.

### 7.1 LocalStorage & SessionStorage
Many Shopify and third-party tracking apps store Pixel configs locally to survive page reloads and inject them via isolated background scripts.
```python
        # ✅ Scanning Storage APIs
        var results = [];
        for (var i = 0; i < localStorage.length; i++) {
            var key = localStorage.key(i);
            if (key.toLowerCase().includes('pixel') || key.toLowerCase().includes('fb')) {
                results.push(localStorage.getItem(key));
            }
        }
```

### 7.2 Google Tag Manager (GTM) `dataLayer`
GTM implementations often push the Pixel ID into the `window.dataLayer` object, which GTM uses internally without exposing it to the global `window` object.
```python
        # ✅ Scanning GTM DataLayer
        if (window.dataLayer && Array.isArray(window.dataLayer)) {
            var dlStr = JSON.stringify(window.dataLayer);
            if (dlStr.toLowerCase().includes('fbq')) {
                var matches = dlStr.match(/\b\d{15,16}\b/g);
            }
        }
```

### 7.3 SPA Framework States (Next.js, Nuxt)
Modern Single Page Applications hydrate their initial state from massive JSON objects injected into the DOM (e.g., `__NEXT_DATA__`). Tracking configs are often buried here.
```python
        # ✅ Scanning SPA Global States
        var globals = ['__NEXT_DATA__', '__NUXT__', '__initialData', '__APP_DATA__'];
        globals.forEach(function(g) {
            if (window[g]) {
                var str = JSON.stringify(window[g]);
                var matches = str.match(/\b\d{15,16}\b/g);
            }
        });
```

### 7.4 Shopify Web Pixels Sandboxes
Shopify's new "Web Pixels" API actively defeats standard scraping by running the tracking code inside a highly restricted, cross-domain `iframe` sandbox (`web-pixel-sandbox`).
```python
        # ✅ Extracting Sandbox Iframe Sources
        var iframes = document.querySelectorAll('iframe[id*="web-pixel"], iframe[src*="web-pixel"]');
        iframes.forEach(function(iframe) {
            var src = iframe.getAttribute('src') || '';
            var matches = src.match(/\b\d{15,16}\b/g); // Extracts ID straight from the Shopify payload URL
        });
```

---

## Conclusion
The original `PII_Hybrid_Crawler.py` relied on "happy path" deployments where the Pixel was injected conventionally and immediately available. 

The extended methodology assumes a hostile, heavily abstracted environment. By breaking through consent walls, decoding POST network logs, and ripping IDs directly out of browser memory structures (LocalStorage, DataLayers, and SPA Hydration states), the `PII_Hybrid_Crawler_Extension.py` proves vastly superior at uncovering obfuscated and highly complex tracking deployments.
