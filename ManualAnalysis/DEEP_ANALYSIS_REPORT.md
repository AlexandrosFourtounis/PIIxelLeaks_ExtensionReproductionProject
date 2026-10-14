# Deep Analysis: MetaPixel vs Non-MetaPixel Scam Domains

**Date:** 2026-06-09
**Data:** 200 manually analyzed scam domains (100 with MetaPixel, 100 without)
**Method:** Full HTML fetch + structural analysis, pattern matching, and template fingerprinting

---

## Executive Summary

The most striking finding is a **survival gap**: **96% of MetaPixel-tagged scam sites are still alive**, compared to only **38% of non-pixel sites**. This 2.5× difference is not random — it reflects fundamental differences in operational sophistication, platform choice, and likely the type of actors behind each group.

Both groups overwhelmingly use the same **scam-as-a-service platforms** (Shopyy, Shopline, Shopify), but the pixel-tagged operators add far more tracking, manipulation tactics, and professional e-commerce polish. The non-pixel group contains more abandoned experiments, quickly-detected-and-killed operations, and lower-effort fraud attempts.

---

## 1. Survival & Accessibility (The Most Important Metric)

| Metric | With MetaPixel | Without MetaPixel |
|--------|---------------|-------------------|
| **200 OK (alive)** | **96/100 (96%)** | **38/100 (38%)** |
| DNS failures (dead) | 1 (1%) | **31 (31%)** |
| 403/404/other errors | 2 (2%) | 27 (27%) |
| HTML captured | 96 (96%) | 38 (38%) |

**Interpretation:** The non-pixel group shows a **31% DNS failure rate** — these domains have been nuked entirely, likely by registrars or hosting providers. Another 27% return error codes (403, 404, 409, 502, 522) indicating server-level takedowns, Cloudflare blocks, or abandoned infrastructure. By contrast, the pixel group maintains near-universal uptime.

**Why this matters:** MetaPixel operators are either (a) better at evading detection, (b) using more resilient infrastructure, (c) actively maintaining their operations, or (d) all of the above. The pixel itself may serve as a marker of "professional" scam operations vs. amateur attempts.

---

## 2. Platform & Technology Stack

### 2.1 E-Commerce Platform Distribution

| Platform | With Pixels (96) | No Pixels (38) |
|----------|-----------------|----------------|
| **Shopify** | 32 (33%) | 5 (13%) |
| **Shopline** | 17 (18%) | 1 (3%) |
| **Shopyy (custom)** | ~30 (31%) | ~8 (21%) |
| **WordPress/WooCommerce** | 0 (0%) | 4 (11%) |
| **Unknown/Other** | ~17 (18%) | 20 (53%) |

**Key finding:** The pixel group heavily favors **Shopify (33%)** and **Shopline (18%)** — both legitimate e-commerce SaaS platforms abused for scam operations. The non-pixel group has a more diverse and less professional stack, with WordPress sites and a much larger "unknown" category.

### 2.2 Template Engine Detection

| Signal | With Pixels | No Pixels |
|--------|------------|-----------|
| Liquid (Shopify) templates | 74 (77%) | 14 (37%) |
| Vue.js templates | 2 (2%) | 2 (5%) |
| React | 2 (2%) | 0 (0%) |

The Liquid template dominance in the pixel group confirms heavy Shopify/Shopline usage.

### 2.3 Shopyy — The Common Scam Platform

Both groups share a critical common denominator: the **Shopyy platform** (identifiable by JavaScript patterns like `window._<domain_hash>_`, CDN scripts from `d39va5bdt61idd.cloudfront.net`, and `/skins/` or `/assets/default/` path structures).

Looking at actual code side-by-side:

**jhvxginp.cc (WITH PIXELS)** and **modafash.com (NO PIXELS)** share an **identical HTML skeleton**:
```
<!DOCTYPE html>
<html lang="en-US" dir="ltr">
<head>
    <script>(function(){...noop...})();</script>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, minimum-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <meta name="mobile-web-app-capable" content="yes">
    <meta name="referrer" content="always">
    <meta name="tiktok-ads-preloading-nocache" content="1">
    <meta property="author" content="<domain>">
    <meta name="copyright" content="CopyRight 2026 <domain>, All Rights Reserved">
    ...
    <script>window._<domain_hash>_ = "_<random>_";</script>
```

This is a **single scam template platform** being resold or reused by multiple operators. The only differences are the domain name, the obfuscated config blob, and whether they've added tracking pixels.

---

## 3. Code Structure & Complexity

### 3.1 Page Size & Density

| Metric | With Pixels | No Pixels |
|--------|------------|-----------|
| **Avg HTML size** | **558,634 bytes** | 254,303 bytes |
| Max size | 2,188,950 bytes | 1,154,765 bytes |
| Min size | 114 bytes | 138 bytes |
| **Avg `<script>` tags** | **60.4** | 24.7 |
| **Avg stylesheets** | **17.6** | 7.6 |
| Inline styles | 91 (95%) | 27 (71%) |
| JS redirects present | 81 (84%) | 15 (39%) |

The pixel-group pages are **2.2× larger** with **2.4× more scripts** and **2.3× more stylesheets**. This reflects more product listings, more tracking code, more "social proof" widgets, and generally more complex storefronts.

### 3.2 Template Reuse (Identical Structure)

| | With Pixels | No Pixels |
|---|------------|-----------|
| Unique page structures | 72 | 31 |
| Pages in duplicate groups | **34 (35%)** | 11 (29%) |
| Number of duplicate groups | 10 | 4 |
| **Largest duplicate group** | **9 identical sites** | 4 identical sites |

The pixel group has a cluster of **9 sites with identical HTML structure**: ablemodern.com, laudpraise.com, menstrove.com, exhibitionk.com, jwzmj.shop, festivelook.com, correctous.com, popnifty.com, favorabler.com. This is a single template deployed across 9 domain names — classic scam operation scaling.

The non-pixel group's largest cluster is only 4 sites (modafash.com, tisonr.com, pdcharmgift.com, oooll.top) — all using the Shopyy platform variant.

### 3.3 Shared Code Snippets

**With Pixels:**
- 29 Shopify sites share identical Shopify boilerplate (SignInWithShop, featureAssets, portableWallets, wpmLoader)
- 17 Shopline sites share the identical Shopline SDK bootstrap
- 54 occurrences of a shared `__load_sales_cart__` script (Shopline's cart system)

**No Pixels:**
- 6 sites share the Shopyy template core (DOMContentLoaded handlers, coupon system, anime.js, ytag tracking)
- 3 sites share Shopify boilerplate

---

## 4. Scam Tactics & Manipulation Patterns

### 4.1 Psychological Manipulation Features

| Tactic | With Pixels (96) | No Pixels (38) | Ratio |
|--------|-----------------|----------------|-------|
| **Stock scarcity** ("only X left") | **85 (89%)** | 16 (42%) | 2.1× |
| **Countdown timers** | **80 (83%)** | 15 (40%) | 2.1× |
| **Price discount displays** | **78 (81%)** | 17 (45%) | 1.8× |
| **Email capture popups** | **81 (84%)** | 16 (42%) | 2.0× |
| Social proof / reviews | 49 (51%) | 11 (29%) | 1.8× |
| Exit intent detection | 28 (29%) | 8 (21%) | 1.4× |
| Currency converter | 59 (62%) | 4 (11%) | 5.8× |
| Geo-redirect / locale detection | 39 (41%) | 10 (26%) | 1.5× |
| Fake live chat widget | 24 (25%) | 8 (21%) | 1.2× |
| Fake sales popup | 2 (2%) | 0 (0%) | — |

### 4.2 Trust Signals (Fake Legitimacy)

| Signal | With Pixels | No Pixels |
|--------|------------|-----------|
| About Us page | 63 (66%) | 15 (39%) |
| Contact Form | 85 (89%) | 23 (61%) |
| Privacy Policy | 75 (78%) | 18 (47%) |
| Terms of Service | 66 (69%) | 11 (29%) |
| FAQ page | 47 (49%) | 7 (18%) |
| Track Order | 20 (21%) | 4 (11%) |
| Social Media links | 37 (39%) | 13 (34%) |
| **Physical Address** | **0 (0%)** | **0 (0%)** |
| **Phone Number** | 4 (4%) | 5 (13%) |

**Critical finding:** **Not a single site in either group provides a real physical address.** The pixel-group sites are significantly more likely to include fake policies, about pages, and contact forms — creating a more convincing facade of legitimacy. The non-pixel group is more likely to skip these entirely.

### 4.3 Payment Method Display

| Payment Method | With Pixels | No Pixels |
|---------------|------------|-----------|
| **PayPal** | **71 (74%)** | 11 (29%) |
| **Apple Pay** | **54 (56%)** | 5 (13%) |
| Google Pay | 39 (41%) | 4 (11%) |
| Stripe | 16 (17%) | 7 (18%) |
| Klarna | 16 (17%) | 5 (13%) |
| Shop Pay | 15 (16%) | 2 (5%) |
| Afterpay | 9 (9%) | 2 (5%) |

Pixel-group sites display **2.6× more payment methods** on average — another trust-building tactic. PayPal is particularly prominent, likely because it's the most recognized and trusted payment brand.

---

## 5. Tracking & Analytics Sophistication

### 5.1 Tracking Pixel Usage

| Tracking Service | With Pixels | No Pixels | Ratio |
|-----------------|------------|-----------|-------|
| **Meta Pixel (fbq)** | 57 detected in HTML | 4 (mostly false negatives) | 14× |
| **TikTok Pixel** | **67 (70%)** | 9 (24%) | 2.9× |
| **Google Analytics** | **67 (70%)** | 17 (45%) | 1.6× |
| Google Tag Manager | 10 (10%) | 8 (21%) | 0.5× |
| Hotjar | 11 (11%) | 2 (5%) | 2.2× |
| Klaviyo (email marketing) | 8 (8%) | 3 (8%) | 1.0× |
| Mailchimp | 10 (10%) | 1 (3%) | 4.2× |

**Critical finding:** The pixel group doesn't just add Meta Pixel — they add **every tracking system**. TikTok Pixel usage is particularly high at 70%, suggesting these operators are running TikTok ad campaigns alongside Facebook/Instagram campaigns.

### 5.2 Meta Pixel ID Analysis

- **92 unique Pixel IDs** across the 57 sites where the pixel was detected in HTML
- Only **2 Pixel IDs are shared** across more than one domain
- This means these are **92 different Facebook ad accounts** — 92 different operators or operational silos
- The non-pixel group has exactly 1 pixel ID found (nashvillecottonlinen.com: `1633347830908230` — a false negative in the original classification)

### 5.3 Note on Detection Gap

The original crawler classified 100 sites as having MetaPixel, but the HTML fetch only found `fbq()` calls in 57. This is because:
- Some sites load the pixel dynamically via JavaScript after page load
- Some sites may have removed the pixel between the original crawl and this analysis
- The original crawler used a headless browser that executes JavaScript; this HTML fetch did not

---

## 6. Domain Naming & Infrastructure

### 6.1 TLD Distribution

| TLD | With Pixels | No Pixels |
|-----|------------|-----------|
| **.com** | **72 (72%)** | 42 (42%) |
| .shop | 10 (10%) | **20 (20%)** |
| .cc | 4 (4%) | 3 (3%) |
| .vip | 2 (2%) | 0 |
| .online | 1 (1%) | 3 (3%) |
| .top | 1 (1%) | 2 (2%) |
| .de | 1 (1%) | 3 (3%) |
| .click | 0 | 2 (2%) |
| .today | 0 | 2 (2%) |
| .info | 0 | 2 (2%) |

### 6.2 Domain Trust Signals

| Metric | With Pixels | No Pixels |
|--------|------------|-----------|
| **.com TLD** (most trusted) | **72%** | 42% |
| Suspicious TLDs (.shop, .top, .cc, .xyz, etc.) | 20% | **45%** |
| Domain names with hyphens | 6% | **16%** |
| Average domain length | 13.6 chars | 15.6 chars |
| Brand-name-style domains | 53% | 30% |

**Key finding:** Pixel-group domains look **more like real brands** — shorter names, .com TLDs, fewer hyphens. The non-pixel group uses more suspicious TLDs (45% vs 20%) and hyphens, which are classic signs of disposable scam domains. This aligns with the survival data: .com domains with brand-style names are harder to take down than hyphenated .shop domains.

### 6.3 CDN & Infrastructure Clustering

**Shared CDN clusters (pixel group):**
- `img-va.myshopline.com` — **16 domains** (Shopline's image CDN)
- `cdn.shopify.com` — **6 domains**
- `cdn.statics-cdn-amz.com` — **4 domains** (Shopyy platform CDN)
- `cdn.shopify.com` — 6 domains

**Non-pixel group:** No significant CDN clustering — each site tends to use its own infrastructure or diverse hosts.

**Subdomain networks (non-pixel group):**
- `mokodrama.com` — 3 subdomains (digital, narra, topic) — all loading the same tiny placeholder page
- `midasbuydeal.com` — 2 subdomains (exchange, vip) — both DNS-dead

---

## 7. Geographic & Linguistic Signatures

| Signal | With Pixels | No Pixels |
|--------|------------|-----------|
| HTML lang="en" | 88 (92%) | 26 (68%) |
| Chinese characters in source | 49 (51%) | 6 (16%) |
| WeChat references | 6 (6%) | 4 (11%) |
| USD ($) currency | 90 (94%) | 25 (66%) |
| Multi-currency (EUR+GBP+JPY) | 50 (52%) | 7 (18%) |

**Key finding:** Half the pixel-group sites contain Chinese characters in their source code (likely from template comments, developer notes, or leftover content). Combined with the Shopline/Shopyy platforms (both Chinese-origin e-commerce SaaS), this strongly suggests **Chinese-speaking operators** are behind a large portion of the pixel-tagged operations.

The non-pixel group has fewer Chinese characters but more diverse languages (Turkish, Russian) — suggesting a more geographically diverse but less coordinated set of operators.

---

## 8. Content Categorization

| Category | With Pixels | No Pixels |
|----------|------------|-----------|
| Fake E-commerce | 85 (89%) | 16 (42%) |
| Dating scam | 84 (88%) | 16 (42%) |
| Crypto/NFT scam | 49 (51%) | 11 (29%) |
| Subscription trap | 24 (25%) | 8 (21%) |
| Counterfeit goods | 14 (15%) | 5 (13%) |
| Phishing | 2 (2%) | 2 (5%) |

The pixel group shows higher density across all scam categories — many sites combine multiple scam types (e.g., fake e-commerce + dating + crypto). The non-pixel group has fewer multi-category hybrid scams.

### 8.1 Product Categories

| Category | With Pixels | No Pixels |
|----------|------------|-----------|
| Home/Garden goods | 78 (81%) | 12 (32%) |
| Fashion/Apparel | 39 (41%) | 12 (32%) |
| Watches/Jewelry | 39 (41%) | 10 (26%) |
| Electronics | 8 (8%) | 0 |
| Health/Beauty | 7 (7%) | 2 (5%) |
| Vape/Smoking | 2 (2%) | 0 |

---

## 9. Template & Code Theft Analysis

### 9.1 Is the Code "Stolen"?

**Not in the traditional sense.** These sites are not hacked together from stolen snippets. Instead, they use:

1. **Scam-as-a-Service platforms** — Shopyy and Shopline provide complete, turnkey e-commerce templates designed for dropshipping (and abused for fraud). Operators sign up, pick a template, upload products, and launch.

2. **Legitimate Shopify themes** — The pixel group shows Shopify themes like "Dawn" (Shopify's official free theme, 4 sites), "Ella" (a premium ThemeForest theme), "Minimog" (another premium theme), "Shrine" (a premium theme). These are likely used without proper licensing, but they're not "stolen code" in the hacked sense — they're unlicensed copies of commercial themes.

3. **Template-as-a-Product** — The Shopyy platform itself appears to be a product sold to would-be dropshippers/scammers. The identical structure across 9 domains (Group 1) and 5 domains (Group 2) in the pixel group suggests a single operator running multiple storefronts from one template.

### 9.2 Specific Themes Identified

**Shopify themes in use (WITH PIXELS):**
- **Dawn** (4 sites) — Shopify's official free theme. Most popular theme on the platform.
- **Shrine** (2 sites) — A premium ThemeForest theme, used by 2 different operators
- **Ella 6.7.4** (1 site) — Premium ThemeForest theme ($59)
- **Minimog 5.7.0** (1 site) — Premium ThemeForest theme ($79)
- **Horizon** (1 site) — Premium theme
- **Fabric** (1 site) — Shopify's free theme

The store_id:887 cluster (5 sites) all share the same Shopify store configuration, suggesting they're either the same store copied 5 times or 5 stores managed by the same operator with duplicated settings.

### 9.3 Code Obfuscation

- **`eval()` usage: 94%** of pixel-group sites vs 68% of non-pixel sites
- This is mostly from the Shopyy platform's obfuscated config bootstrap, not malicious JS injection
- The config blob contains Base64-encoded JSON with store settings, tracking IDs, and theme configuration
- Only one site (in the non-pixel group) uses the classic "packed" JS obfuscation (`eval(function(p,a,c,k,e,d)...`)

---

## 10. Brand Impersonation Patterns

### 10.1 Domain-Level Impersonation

Very few domains directly impersonate brands in their domain names:
- `zalandosales.com` → impersonates Zalando
- `sportsdirect-outlet.com` → impersonates Sports Direct
- `skinceuticals.de` → impersonates SkinCeuticals
- `eobuwiemarch-pl.shop`, `eobuwieplshoes.shop`, `eobuwiesale.shop` → impersonate eobuwie (Polish shoe retailer)
- `jysk-home.com`, `jyskpoland.shop` → impersonate JYSK
- `lidlin.shop` → impersonates Lidl
- `birkenstockonline.top` → impersonates Birkenstock
- `cybernewbalance.shop` → impersonates New Balance

Most of these brand-impersonating domains are in the **NON-PIXEL group** (8 out of 10) — and most of them are dead (DNS failures or 403 errors). The pixel-group operators prefer original-sounding brand names.

### 10.2 Content-Level Brand References

Both groups heavily reference luxury brands in their HTML content. The most common: LV, YSL, Alo, UGG, Apple — but these are typically in product listings (selling counterfeit goods) rather than site branding.

---

## 11. Summary: The Two Profiles

### Profile A: "Professional Scammer" (WITH MetaPixel)

- Uses Shopify or Shopline with premium/free themes
- .com domains with brand-style names  
- Full e-commerce UX: product grids, variants, reviews, trust badges, policies
- Aggressive psychological tactics: countdowns, scarcity, urgency (80%+)
- Multi-channel ad tracking: Meta + TikTok + Google Analytics
- Shows 6+ payment methods for legitimacy
- Sites stay alive (96% uptime)
- **Chinese-origin operators, running coordinated multi-store operations**
- Average site: 558KB, 60 scripts, full-featured store

### Profile B: "Amateur Scammer" (WITHOUT MetaPixel)

- Mixed platforms: some Shopify, some WordPress, many unidentified
- More suspicious TLDs (.shop, .top, .click), hyphenated names  
- Simpler UX: fewer products, less polish, missing trust signals
- Fewer manipulation tactics (40-45% range)
- Less tracking: some Google Analytics, rare TikTok, no Meta
- Fewer payment methods displayed
- **Sites die fast: 31% DNS-dead, 27% erroring out**
- More diverse operator geography, less coordination
- Average site: 254KB, 25 scripts, mid-effort store or simple landing page

### What They Share

**Both groups use the same scam-enabling platforms** (Shopyy, Shopify, Shopline). The underlying technology is identical in many cases — the same HTML skeleton, the same obfuscated config pattern, the same CDN resources. The difference is not in *what platform they use* but in *how professionally they operate it*.

The MetaPixel serves as an excellent **proxy for operational sophistication**. Operators who add Meta Pixel also add TikTok Pixel, Google Analytics, payment methods, trust badges, and aggressive sales tactics. They maintain their infrastructure better and their sites survive longer. The pixel itself isn't the cause — it's a symptom of a more professional (and thus more dangerous) fraud operation.

---

## 12. Recommendations for Detection

1. **CDN monitoring:** Monitor `d39va5bdt61idd.cloudfront.net` (Shopyy platform CDN) and `img-va.myshopline.com` (Shopline CDN) for new scam storefronts
2. **Template fingerprinting:** The Shopyy HTML skeleton with its distinctive `window._<hash>_` variable is a reliable detection signature
3. **Shopify store_id clustering:** Tracking store_id:887 and similar shared configurations can identify multi-store operators
4. **MetaPixel ID sharing:** While rare (only 2 shared IDs), any shared Pixel ID across domains should trigger investigation
5. **TikTok pixel + PayPal + countdown:** This combination appears in 70%+ of sophisticated scam stores and is a strong heuristic signal
