# Headless CAPI and Network Tracking Detection Methodology

## Overview
The traditional method of identifying the Facebook (Meta) Pixel relies on static code analysis (parsing HTML/JavaScript for the `fbq('init', '<pixel_id>')` pattern) or executing the page in a headless browser and polling the global `window.fbq.getState()` object. 

However, many websites, especially suspicious or scam domains, employ obfuscation techniques to hide their tracking pixels. To combat this and capture a wider net of tracking implementations, we have massively extended the `PII_Hybrid_Crawler` to include **12 Advanced Extensions**, focusing on **Network API Interception**, **First-Party Cookie Detection**, **Consent Wall Bypassing**, and exhaustive **Deep Extraction** of obfuscated IDs.

## The 12 Advanced Extensions

### 1. Static Detection Bug Fixes
Fixed early-return bugs in the basecode detection logic that caused the scanner to stop after finding the first script tag. The crawler now correctly accumulates results across *all* script tags, ensuring no secondary pixels are missed on pages with multiple tracker deployments.

### 2. Consent Wall Auto-Accept Engine
Before scanning for pixels, the headless browser now automatically searches for and interacts with Cookie Consent walls. It targets common consent management platforms (OneTrust, CookieBot) and generic "Accept All Cookies" or "I Agree" buttons using both CSS selectors and heuristic button-text matching. This ensures pixels that wait for user consent are triggered and captured.

### 3. `<link>` Prefetch Hinting
The static analysis phase now inspects `<head>` elements for `<link rel="preconnect">`, `dns-prefetch`, or `prefetch` tags pointing to `connect.facebook.net` or `fbevents`. If a website hints at loading Facebook resources but hides the actual script, the crawler flags it for headless execution, guaranteeing deeper inspection.

### 4. Advanced Network Log Interception & POST Body Inspection
The crawler parses Chrome performance logs (`Network.requestWillBeSent`) to intercept tracking requests in real-time. It no longer just inspects URL parameters (`?id=...`); it now extracts the **JSON POST bodies** of requests. This is critical for catching Conversions API (CAPI) events which transmit Pixel IDs securely within POST payloads.

### 5. Expanded Network Endpoints
Interception patterns have been broadened beyond `/tr/` and `/events?` to include `graph.facebook.com`, `connect.facebook.net/signals/`, and `pixel.facebook.com`, catching data routed through alternative Meta tracking endpoints.

### 6. `window._fbq` Variant Detection
Some websites attempt to evade scanners by initializing the tracker under an obfuscated, underscore-prefixed variable (`window._fbq`). The crawler now explicitly probes `typeof _fbq !== 'undefined'` and extracts the state identically to the standard object.

### 7. `fbq.queue` Inspection
If a page initializes a pixel but the network request hasn't fired or the state object isn't fully hydrated, the crawler now inspects the internal `fbq.queue` array for queued `init` commands, successfully extracting Pixel IDs before they are formally registered.

### 8. Multi-Cookie Detection (`_fbp`, `_fbc`, `fr`)
Meta's tracking infrastructure relies on first-party cookies. The crawler has expanded its cookie jar inspection beyond just `_fbp` (Facebook Pixel) to include `_fbc` (Click ID) and `fr` (Encrypted Facebook ID). The presence of any of these cookies strongly indicates tracking activity and triggers the CAPI/Network state flag.

### 9. SessionStorage Deep Extraction
Expanding upon our LocalStorage scan, the crawler now dumps and parses `window.sessionStorage`. Certain eCommerce plugins and tracking apps temporarily store their Facebook configurations in the session state rather than local storage.

### 10. `window.dataLayer` Inspection (GTM Pre-firing)
The crawler stringifies and inspects the Google Tag Manager `dataLayer` array. If keywords like "facebook", "fbq", or "pixel" are found inside the data layer events, it extracts 15-16 digit numbers. This catches Pixel IDs staged for Server-Side GTM firing before they ever hit the network.

### 11. SPA Framework State Extraction
Single Page Applications (React/Next.js, Vue/Nuxt) often hydrate their state with backend data upon load. The crawler now inspects global SPA state variables (`__NEXT_DATA__`, `__NUXT__`, `__initialData`, `__APP_DATA__`) to extract Pixel IDs embedded in the initial page payload by the server.

### 12. Shopify Web Pixels Sandbox Defeat
Shopify's new "Web Pixels" architecture runs tracking scripts inside isolated, sandboxed iframes to prevent third-party script conflicts. The crawler explicitly queries the DOM for these sandboxes (`iframe[id*="web-pixel"]`) and extracts the Pixel IDs directly from their `src` attributes.

## State Categorization (`CAPI_OR_NETWORK`)
If the crawler fails to find the traditional `window.fbq.getState()` object, but successfully intercepts Facebook network requests OR detects tracking cookies, it classifies the domain's tracking state as `CAPI_OR_NETWORK`. 

All IDs recovered via Deep Extraction (LocalStorage, dataLayer, SPA configs, etc.) are seamlessly integrated into the payload. The downstream `get_PII_from_configs.py` script validates these candidates against Meta's configuration endpoints (`connect.facebook.net/signals/config/{id}`) to definitively filter out false positives (like timestamps) and prove Advanced Matching PII leakage for heavily obfuscated domains.
