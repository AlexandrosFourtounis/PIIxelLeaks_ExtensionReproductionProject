import os
import re
import sys
import json
import time
import requests
import threading
import logging
import aiohttp
import asyncio
import socket
import warnings
import random
import base64

from bs4 import BeautifulSoup
from bs4 import Tag

from urllib.parse import urljoin, urlparse, unquote
from pathlib import Path
from functools import partial


from urllib3.exceptions import InsecureRequestWarning
from requests.exceptions import RequestException




from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities

from multiprocessing import Process, Queue
import concurrent.futures

from concurrent.futures import ThreadPoolExecutor, as_completed
from concurrent.futures import ProcessPoolExecutor  
from typing import Dict, List, Set, Optional
from dataclasses import dataclass, asdict


warnings.filterwarnings('ignore')
import urllib3
urllib3.disable_warnings()  # preferred over requests.packages.urllib3.disable_warnings()

# Configure logging once, at INFO level. The old code set the root logger to
# CRITICAL first, which made the subsequent basicConfig(INFO) call a no-op
# (basicConfig is ignored when the root logger already has a level set).
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

pattern_init = r'fbq\(\s*["\']init["\']\s*,\s*["\'](\d+)["\'](?:\s*,\s*[^)]*)?\s*\)'
pattern_track = r'fbq\(\s*["\']track["\']\s*,\s*["\'][^"\']*["\'](?:\s*,\s*[^;]*)?\s*\);'
keywords = {'facebook', 'fbevents', 'fbq'}



valid_html_but_flagged = dict()
invalid_html_no_response = []
pixels_found = dict()
found_nothing = list()
second_run_stateless = list()
hanging_doms = []
dns_errors = {}
baseline_timing_dict = {}
headless_timing_dict = {}

# Locks to protect global state when find_FBP runs in parallel
_global_lock = threading.Lock()


def sanitize_for_json(obj):
    if isinstance(obj, dict):
        return {k: sanitize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [sanitize_for_json(i) for i in obj]
    elif hasattr(obj, '__dict__'):
        return sanitize_for_json(obj.__dict__)
    else:
        try:
            json.dumps(obj)
            return obj
        except (TypeError, OverflowError):
            return str(obj)


async def fetch_html_async(i, domain):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'DNT': '1',
        'Connection': 'close',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1'
    }
    
    if not domain.startswith(('http://', 'https://')):
        url = 'https://' + domain
        base_domain = domain
    else:
        url = domain
        parsed = urlparse(domain)
        base_domain = parsed.netloc
        
    if ':' in base_domain:
        base_domain = base_domain.split(':')[0]
    
    try:
        ip_info = await asyncio.to_thread(socket.gethostbyname, base_domain)
        dns_success = True
    except socket.gaierror:
        dns_success = False
        dns_errors[base_domain] = "DNS_PROBE_FINISHED_NXDOMAIN"
        print(f"{i}) DNS resolution failed for {domain}")
        return None
    
    try:
        timeout = aiohttp.ClientTimeout(total=8)
        ssl_context = False  
        
        connector = aiohttp.TCPConnector(
            ssl=ssl_context,
            force_close=True,
            enable_cleanup_closed=True
        )
        
        async with aiohttp.ClientSession(
            timeout=timeout,
            connector=connector,
            headers=headers
        ) as session:
            async with session.get(url, allow_redirects=True) as response:
                final_url = str(response.url)
                
                if response.status == 200:
                    print(f"{i}) Got HTML for {domain} -> {final_url}")
                    return await response.text()
                else:
                    print(f"{i}) Error status {response.status} for {domain} -> {final_url}")
                    return f"Error fetching HTML for {domain} -> {final_url} | status code: {response.status}"
                
    except aiohttp.ClientConnectorError as e:
        dns_errors[base_domain] = str(e)
        print(f"{i}) Connection error for {domain}: {str(e)}")
        return None
    except asyncio.TimeoutError:
        print(f"{i}) Timeout fetching {domain}")
        return None
    except aiohttp.ClientError as e:
        print(f"{i}) Client error fetching {domain}: {str(e)}")
        return f"Error - Client error fetching {domain}: {str(e)}"
    except Exception as e:
        print(f"{i}) Unexpected error fetching {domain}: {str(e)}")
        return f"Error: Unexpected error fetching {domain}: {str(e)}"

def fetch_html(i, domain):
    # asyncio.run() creates a fresh event loop each call, which is safe to use
    # from any thread as long as no loop is already running in that thread.
    # We explicitly create and close the loop to avoid "loop already running"
    # errors that can occur on some platforms when called from thread pools.
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(fetch_html_async(i, domain))
    finally:
        loop.close()



def get_domains_as_list(path=None):
    with open(path, 'r') as file:
        domains = [line.strip() for line in file if line.strip()]
        return domains

def extract_fb_pixel_id(text):
    pattern1 = r'fbq\((?:\\?[\'"])\s*init\s*(?:\\?[\'"])\s*,\s*(?:\\?[\'"])\s*(\d{10,16})\s*(?:\\?[\'"])'
    pattern2 = r'facebook\.com\\?/tr\?id=(\d{10,16})'
    
    pixel_ids = set()  


    matches1 = re.findall(pattern1, text)
    pixel_ids.update(matches1)
    
    matches2 = re.findall(pattern2, text)
    pixel_ids.update(matches2)
    
    return list(pixel_ids) if pixel_ids else None

def check_fb_pixel(unique_id,domain):
    base_url = f'https://connect.facebook.net/signals/config/{unique_id}?domain={domain}'
    try:
        response = requests.get(base_url, timeout=3, verify=False, allow_redirects=True)
        
        if response.status_code != 200:
            print(f'Invalid status code for {unique_id}')
            return 0
        
        pattern = rf'fbq\.registerPlugin\("{unique_id}", \{{__fbEventsPlugin: 1, plugin: function\(fbq, instance, config\) \{{ /\* empty plugin \*/instance\.configLoaded\("{unique_id}"\); \}}\}}\);?\s*$'
        
        if re.search(pattern, response.text.strip()):
            print(f"Invalid ID: {unique_id} ({domain})")
            return 0
        return 1    
    except requests.exceptions.RequestException as e:
        print(f"Error checking {unique_id}: {str(e)}")
        return 0

# =================================================================================== FACEBOOK PIXEL IMPLEMENTATION SOLE ==========================================================================
def identify_fbp_basecode(domain, html_content):
    pixels_found = []

    soup = BeautifulSoup(html_content, 'html.parser')
    script_tags = soup.find_all('script')
    for script in script_tags:
      script_content = str(script)
      if any(keyword in script_content for keyword in keywords):
        init_calls = re.findall(pattern_init, script_content)
        track_calls = re.findall(pattern_track, script_content)

        if init_calls or track_calls:
            print(f'Basecode implementation of FB Pixel found for {domain}: {str(init_calls)}/{str(track_calls)}')


            pixels_found.append({
                "domain": domain,
                "init": init_calls,
                "track": track_calls
                })


    return pixels_found if pixels_found else None

def identify_fbp_lightweight(domain, html_content):

    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        
        img_tags = soup.find_all('img')
        
        pattern = r'facebook\.com/tr\?id=([^&]+)&'
        
        pixels = []
        for img in img_tags:
            src = img.get('src', '')
            if 'facebook.com/tr?' in src:
                matches = re.findall(pattern, src)  
                for pixel_id in matches:
                    pixels.append((pixel_id, str(img)))
                    print(f'Lightweight implementation of FB Pixel found for {domain}: {str(img)}')
        
        if len(pixels) > 0:
            return pixels
        else:
            return None
    except Exception as e:
        return None


def identify_facebook_pixel_core_implementation(domain,html_content):

    fbp_base_code = identify_fbp_basecode(domain,html_content)
    fbp_light_code = identify_fbp_lightweight(domain,html_content)

    if fbp_base_code or fbp_light_code:
        return {
            "base_code" : fbp_base_code,
            "lightweight" : fbp_light_code
        }
    else:
        return None
    
def identify_fbp_basecode_in_the_wild(domain, html_content):
    
    pixels_found = []
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        script_tags = soup.find_all('script')
        for script in script_tags:
            script_content = str(script)
            if 'connect.facebook.net/en_US/fbevents.js' not in script_content:
                init_calls = re.findall(pattern_init, script_content)
                track_calls = re.findall(pattern_track, script_content)

                if init_calls or track_calls:
                    print(f'Implementation of FB Pixel (found in the wild) for {domain}: {str(init_calls)}/{str(track_calls)}')
                    pixels_found.append({
                        "domain": domain,
                        "init": init_calls,
                        "track": track_calls
                    })
    except Exception as e:
        print(e)
        return None

    return pixels_found if pixels_found else None    
# =================================================================================================================================================================================================
# =================================================================================== FB PIXEL IMPLEMENTATION IN GTM ==============================================================================
def search_in_gtm(domain, html_content):
    base_code_gtm = find_gtm_scripts(domain, html_content)
    lightweight_gtm = find_gtm_noscripts(domain, html_content)
    per_gtm_tag = {
        domain: {
            "found_flag": 0,
            "base_code_gtm": dict(),
            "base_code_type": '',
            "lightweight_gtm": dict(),
            "light_code_type": ''
        }
    }

    # Build the list of (tag, bucket) pairs to analyze concurrently
    tasks = []  # (tag, bucket)  bucket = 'base' | 'light'
    if base_code_gtm:
        for tag in base_code_gtm:
            tasks.append((tag, 'base'))
    if lightweight_gtm:
        for tag in lightweight_gtm:
            if base_code_gtm and tag not in base_code_gtm:
                tasks.append((tag, 'light'))

    if not tasks:
        return per_gtm_tag

    def _analyze_tag(tag_bucket):
        tag, bucket = tag_bucket
        print(f"Analyzing: {tag}")
        type_, fbps = search_for_pixel_in_gtm(domain, tag)
        return tag, bucket, type_, fbps

    # GTM lookups are network I/O — threads are ideal here
    with ThreadPoolExecutor(max_workers=min(len(tasks), 8)) as ex:
        futures = {ex.submit(_analyze_tag, tb): tb for tb in tasks}
        for future in as_completed(futures):
            try:
                tag, bucket, type_, fbps = future.result()
                if fbps:
                    per_gtm_tag[domain]['found_flag'] = 1
                    if bucket == 'base':
                        per_gtm_tag[domain]['base_code_type'] = type_
                        per_gtm_tag[domain]['base_code_gtm'][tag] = fbps
                    else:
                        per_gtm_tag[domain]['light_code_type'] = type_
                        per_gtm_tag[domain]['lightweight_gtm'][tag] = fbps
            except Exception as exc:
                logger.warning(f"Error analyzing GTM tag for {domain}: {exc}")

    return per_gtm_tag


def find_gtm_scripts(domain, html_content):
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        script_tags = soup.find_all('script')
        
        patterns = [
            # r'\(window,document,\'script\',\'dataLayer\',\'(GTM-[A-Z0-9]+)\'\)',
            r'\(\s*window\s*,\s*document\s*,\s*[\'"]script[\'"]\s*,\s*[\'"]dataLayer[\'"]\s*,\s*[\'"]?(GTM-[A-Z0-9]+)[\'"]?\s*\)',
            r'googletagmanager\.com/gtm\.js\?id=(GTM-[A-Z0-9]+)',
            r'(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}/gtm\.js\?id=(GTM-[A-Z0-9]+)',
            r'ga\(\'require\', \'(GTM-[A-Z0-9]+)\'\)',
            r'\'(GTM-[A-Z0-9]+)\':true',
            r'\'GTM-[A-Z0-9]+\'\s*\+\s*dl|\'(GTM-[A-Z0-9]+)\'\s*\+\s*dl'
        ]

        gtm_ids = []
        for script in script_tags:
            script_content = str(script)
            for pattern in patterns:
                matches = re.findall(pattern, script_content)
                for match in matches:
                    if isinstance(match, tuple):  
                        match = next((m for m in match if m), '')
                    if match and match not in gtm_ids:
                        gtm_ids.append(match)
                        print(f'Found GTM for {domain} : {match}')

        if len(gtm_ids) > 0:
            return gtm_ids
        else:
            return None
    except Exception as e:
        return None

def find_gtm_noscripts(domain, html_content):
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        noscript_tags = soup.find_all('noscript')
        pattern = r'https://www\.googletagmanager\.com/ns\.html\?id=(GTM-[A-Z0-9]+)'
        
        gtm_urls = []
        for noscript in noscript_tags:
            iframe = noscript.find('iframe')
            if iframe and iframe.get('src'):
                match = re.search(pattern, iframe.get('src'))
                if match:
                    gtm_urls.append(match.group(1))
                    print(f'Found GTM lightweight for {domain} : {str(match.group(1))}')
        
        if len(gtm_urls) > 0:
            return gtm_urls
        else:
            return None
    except Exception as e:
        return None


def get_fbpid_from_vtp(text,domain):
    pattern = r'"vtp_pixelId"\s*:\s*"(\d+)"'
    
    matches = re.findall(pattern, text)   
    unique_ids = list(set(matches))
    final_ids = []
    for unique_id in unique_ids:
        ret_val = check_fb_pixel(unique_id,domain)
        if ret_val != 0:
            final_ids.append(unique_id)

    if len(final_ids) > 0:
        return final_ids
    else:
        return None

def extract_tags_array(content):
    try:
        start_marker = '"tags":['
        start_idx = content.find(start_marker)
        if start_idx == -1:
            print("No macros array found")
            return None
        
        start_idx += len(start_marker) - 1  
        bracket_count = 0
        in_string = False
        escape_char = False
        
        for i in range(start_idx, len(content)):
            char = content[i]
            
            if char == '"' and not escape_char:
                in_string = not in_string
            
            if char == '\\' and not escape_char:
                escape_char = True
                continue
            escape_char = False
            
            if not in_string:
                if char == '[':
                    bracket_count += 1
                elif char == ']':
                    bracket_count -= 1
                    if bracket_count == 0:
                        tags_str = content[start_idx:i+1]
                        try:
                            # Parse and return a list, consistent with extract_macros_array,
                            # so callers receive a list rather than a raw JSON string.
                            return json.loads(tags_str)
                        except json.JSONDecodeError as e:
                            print(f"Error parsing extracted array: {str(e)}")
                            return None

    except Exception as e:
        print(f"Error processing text: {str(e)}")
        return None

def extract_macros_array(content):
    try:
        start_marker = '"macros":['
        start_idx = content.find(start_marker)
        if start_idx == -1:
            print("No macros array found")
            return None
        
        start_idx += len(start_marker) - 1  
        bracket_count = 0
        in_string = False
        escape_char = False
        
        for i in range(start_idx, len(content)):
            char = content[i]
            
            if char == '"' and not escape_char:
                in_string = not in_string
            
            if char == '\\' and not escape_char:
                escape_char = True
                continue
            escape_char = False
            
            if not in_string:
                if char == '[':
                    bracket_count += 1
                elif char == ']':
                    bracket_count -= 1
                    if bracket_count == 0:
                        macros_str = content[start_idx:i+1]
                        try:
                            return json.loads(macros_str)
                        except json.JSONDecodeError as e:
                            print(f"Error parsing extracted array: {str(e)}")
                            return None

    except Exception as e:
        print(f"Error processing text: {str(e)}")
        return None

def get_facebook_vtp_functions(tags_array):
    facebook_related_funcs = []

    # tags_array is already a parsed list (returned by extract_tags_array via json.loads)
    for tag in tags_array:
        if "once_per_load" in tag.keys():
            if tag['once_per_load'] is True:
                if 'vtp_html' in tag.keys():
                    vtp_html = str(tag['vtp_html'])
                    if 'https://connect.facebook.net/en_US/fbevents.js' in vtp_html and 'fbq("track","PageView");' in vtp_html:
                        facebook_related_funcs.append(str(vtp_html))
                        break
        else:
            pass


    return facebook_related_funcs


def parse_domain_list(domain_list):
    mappings = domain_list[1:]
    
    result = {}
    for item in mappings:
        if len(item) == 5 and item[0] == 'map' and item[1] == 'key' and item[3] == 'value':
            domain = item[2]
            clean_domain = (domain.replace('^', '').replace('$', '').replace('(?:www\\.)?', '').replace('\\', '').replace('m\\.', '').replace('mlite\\.', ''))
            result[clean_domain] = item[4]
    
    if len(result.keys()) > 0:
        return result
    else:
        return None

def find_fbq_macro_value(content):
    macros = extract_macros_array(content)
    if not macros:
        return None
    
    try:
        tags_array = extract_tags_array(content)
        fb_vtp_funcs = get_facebook_vtp_functions(tags_array)
        fbq_macros = {}
        for vtp_func in fb_vtp_funcs:
            init_pattern = r'fbq\(["\']init["\'],\s*["\']["\']?,\s*\[\s*["\']escape["\'],\s*\[\s*["\']macro["\'],\s*(\d+)\s*\]'

            init_pattern2 = r'fbq\(["\']init["\'],.*?\[\s*["\']escape["\'],\s*\[\s*["\']macro["\'],\s*(\d+)\s*\]'


            macro_indices = re.findall(init_pattern, vtp_func)
            
            
            if macro_indices:
                for index in list(set(macro_indices)):
                    index = int(index)
                    if index < len(macros):
                        fbq_macros[index] = macros[index]
            else:
                macro_indices = re.findall(init_pattern2, vtp_func)
                for index in list(set(macro_indices)):
                    index = int(index)
                    if index < len(macros):
                        fbq_macros[index] = macros[index]

        pixel_ids = []
        mappings_domain_to_fbID = {}
        if fbq_macros:
            for macro in fbq_macros.keys():
                as_array = fbq_macros[macro]
                if 'function' in as_array.keys():
                    if as_array['function'] == "__c":
                        if 'vtp_value' in as_array.keys():
                            pixel_ids.append(as_array['vtp_value'])
                    
                    if as_array['function'] == "__smm":
                        if 'vtp_setDefaultValue' in as_array.keys():
                            if as_array['vtp_setDefaultValue'] is True:
                                pixel_ids.append(as_array['vtp_defaultValue'])
                            else:
                                mappings_domain_to_fbID = parse_domain_list(as_array['vtp_map'])
                                
        if len(pixel_ids) > 0:
            return list(set(pixel_ids))
        else:
            if len(mappings_domain_to_fbID.keys()) > 0:
                return mappings_domain_to_fbID
            else:
                return None

    except Exception as e:
        print(f"Error processing: {str(e)}")
        return None

def validate_html_script(tags):
    fb_ids = []
    if len(tags) == 1:
        temp_ids = extract_fb_pixel_id(tags[0]['vtp_html'])
        if temp_ids:
            fb_ids = temp_ids
    else:
        for tag in tags:
            if 'vtp_supportDocumentWrite' in tag:
                    if tag['vtp_supportDocumentWrite'] is True:
                        temp_ids = extract_fb_pixel_id(tag['vtp_html'])
                        if temp_ids:
                            for temp_id in temp_ids:
                                fb_ids.append(temp_id)

    if len(fb_ids) > 0:
        return list(set(fb_ids))
    else:
        return None

def search_in_tags(tag_html,content):

    init_pattern = r'fbq\(["\']init["\'],\s*["\']["\']?,\s*\[\s*["\']escape["\'],\s*\[\s*["\']macro["\'],\s*(\d+)\s*\]'
    init_pattern2 = r'fbq\(["\']init["\'],.*?\[\s*["\']escape["\'],\s*\[\s*["\']macro["\'],\s*(\d+)\s*\]'

    baseline_ids = extract_fb_pixel_id(str(tag_html))
    if baseline_ids:
        print(baseline_ids)
    else:
        tag_html = str(tag_html)

        macros = extract_macros_array(content)
        init_pattern = r'fbq\(["\']init["\'],\s*["\']["\']?,\s*\[\s*["\']escape["\'],\s*\[\s*["\']macro["\'],\s*(\d+)\s*\]'

        init_pattern2 = r'fbq\(["\']init["\'],.*?\[\s*["\']escape["\'],\s*\[\s*["\']macro["\'],\s*(\d+)\s*\]'

        macro_indices = re.findall(init_pattern, tag_html)
        fbq_macros = dict()


        if macro_indices:
            for index in list(set(macro_indices)):
                index = int(index)
                if index < len(macros):
                    fbq_macros[index] = macros[index]
        else:
            macro_indices = re.findall(init_pattern2, tag_html)
            for index in list(set(macro_indices)):
                index = int(index)
                if index < len(macros):
                    fbq_macros[index] = macros[index]
        
        pixel_ids = []
        mappings_domain_to_fbID = []
        if fbq_macros:
            for macro in fbq_macros.keys():
                as_array = fbq_macros[macro]      
                if 'vtp_setDefaultValue' in as_array.keys():                  
                    if as_array['vtp_setDefaultValue'] is True:
                        pixel_ids.append(as_array['vtp_defaultValue'])
                    else:
                        mappings_domain_to_fbID = parse_domain_list(as_array['vtp_map'])


        if mappings_domain_to_fbID:
            return mappings_domain_to_fbID
        elif pixel_ids:
            return pixel_ids
        else:
            return None

def find_pixel_ids(content, tag):
   try:           
        pattern = r'\b\d{15,16}\b'
        pixel_ids = re.findall(pattern, content)
        
        if pixel_ids:
            print(f"Found Pixel IDs in {tag} (generic heuristic)")
            return list(set(pixel_ids))
        else:
            print(f"No pixel IDs found in {tag} (generic heuristic)")
            return None
   except Exception as e:
       print(f"Error reading file: {str(e)}")
       return None

def search_for_pixel_in_gtm(domain,tag):

    try:
        gtm_url = 'https://www.googletagmanager.com/gtm.js?id='+tag
        response = requests.get(gtm_url, timeout=5, verify=False, allow_redirects=True)

        if response.status_code == 200:
            content = str(response.text)
            fbp = extract_fb_pixel_id(content)
            if fbp:
                print(f"GTM: {tag} has FB Pixel with ID: {fbp}")
                return "basic", fbp
            else:
                print('Searching for VTP')
                fbp_ids_vtp = get_fbpid_from_vtp(content,domain)
                if fbp_ids_vtp:
                    if len(fbp_ids_vtp) > 0:
                        return "vtp", fbp_ids_vtp
                else:
                    print('* No VTP values found searching for macros')
                    fbp_ids_macros = find_fbq_macro_value(content)
                    if isinstance(fbp_ids_macros, dict):
                        return "mappings", fbp_ids_macros
                    elif isinstance(fbp_ids_macros, list):
                        return "simple_list", fbp_ids_macros
                    else:

                        print('* No macros values found searching for generic')
                        pixel_ids = find_pixel_ids(content, tag)
                        if pixel_ids:
                            return "potential", list(set(pixel_ids))
        else:
            print(f'Unexpected status code {response.status_code} for GTM tag {tag}')
    except Exception as e:
        return None, None                    

    return None, None

# =================================================================================================================================================================================================
def count_html_lines(html_content, pretty=True):
    raw_lines = len(html_content.splitlines())
    
    if pretty:
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            formatted_content = soup.prettify()
            formatted_lines = len(formatted_content.splitlines())
        except Exception as e:
            print(f"Error formatting HTML: {e}")
            return raw_lines, raw_lines, html_content
            
        return raw_lines, formatted_lines, formatted_content
    
    return raw_lines, raw_lines, html_content

def check_meta_refresh(html_content, domain):
    if not domain.startswith(('http://', 'https://')):
        base_url = 'https://' + domain
    else:
        base_url = domain

    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        meta = soup.find('meta', attrs={'http-equiv': re.compile('^refresh$', re.I)})
        
        if not meta:
            print("No meta refresh found")
            return False, None
            
        content = meta.get('content', '')
        if not content:
            print("Meta refresh found but no content attribute")
            return False, None
            
        match = re.search(r'url\s*=\s*(.+)', content, re.I)
        
        if not match:
            print(f"No URL found in content: {content}")
            return False, None
            
        url = match.group(1).strip()
        
        url = url.strip('"\'')
        
        if not url.startswith(('http://', 'https://')):
            if url.startswith('/'):
                url = base_url+url
            else:
                url = base_url+'/'+url

            
        print(f"Found meta refresh redirect to: {url}")
        return True, url
        
    except Exception as e:
        print(f"Error parsing HTML: {e}")
        return False, None




# def get_fbq_state(domain):
#     chrome_options = Options()
#     chrome_options.add_argument("--headless=new")
#     chrome_options.add_argument("--no-sandbox")
#     chrome_options.add_argument("--disable-dev-shm-usage")
#     chrome_options.add_argument("--disable-gpu")
#     chrome_options.add_argument('--enable-javascript')
#     chrome_options.add_argument('--window-size=1920,1080')
#     chrome_options.add_argument('--dns-prefetch-disable')
#     chrome_options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')

#     # chrome_options.page_load_strategy = 'eager'

#     driver = webdriver.Chrome(options=chrome_options)
#     driver.set_page_load_timeout(60)

#     try:
#         if not domain.startswith(('http://', 'https://')):
#             domain = 'https://' + domain

#         driver.get(domain)

#         WebDriverWait(driver, 20).until(
#             EC.presence_of_element_located((By.TAG_NAME, 'body'))
#         )

#         start_time = time.time()
#         fbq_state = None

#         while time.time() - start_time < 10:
#             try:
#                 fbq_state = driver.execute_script("""
#                     if (typeof fbq !== 'undefined' && typeof fbq.getState === 'function') {
#                         try {
#                             const state = fbq.getState();
#                             if (state && state.pixels && state.pixels.length > 0) {
#                                 return JSON.stringify(state);
#                             }
#                         } catch (e) {}
#                     }
#                     return null;
#                 """)
                
#                 if fbq_state:
#                     break  

#             except Exception:
#                 pass

#             time.sleep(0.5)

#         if fbq_state:
#             parsed_state = json.loads(fbq_state)
#             print(f"\nFacebook Pixel State for {domain}:")
#             print(json.dumps(parsed_state, indent=2))
#             driver.quit()
#             return 'FBP', parsed_state

#         try:
#             gtm_ids = driver.execute_script("""
#                 return Array.from(new Set([...document.documentElement.innerHTML.match(/GTM-[A-Z0-9]+/g) || []]));
#             """)
#         except Exception:
#             gtm_ids = []

#         if gtm_ids:
#             print(f'Found GTM in headless: {str(gtm_ids)}')
#             implementations = []
#             patterns = get_fb_patterns()

#             for gtm_id in gtm_ids:
#                 print(f'Analyzing : {gtm_id}')
#                 implementation_type, pixel_ids = search_for_pixel_in_gtm(domain,gtm_id)
#                 if pixel_ids:
#                     print(f'Found Pixel for {domain} in GTM {gtm_id}')
#                     for pixel_id in pixel_ids:
#                         implementations.append(pixel_id)
#                 else:
#                     print(f'No Pixels found in {gtm_id}')
#             driver.quit()
#             if implementations:
#                 return 'GTM', implementations 
            

#         try:
#             print(f"\n\nHTML for {domain} (no pixel found):")
#             html_content = driver.page_source
#             if "fbq(" in html_content or "facebook-jssdk" in html_content or "connect.facebook.net" in html_content:
#                 print("\nFacebook Pixel related code detected in HTML but not accessible via fbq.getState()")                
#                 pixel_id_pattern = r"fbq\(\s*['\"]init['\"]\s*,\s*['\"](\d+)['\"]\s*\)"
#                 import re
#                 pixel_matches = re.findall(pixel_id_pattern, html_content)
#                 if pixel_matches:
#                     print(f"Potential Facebook Pixel IDs found in HTML: {pixel_matches}")
            
#         except Exception as e:
#             print(f"Error printing HTML: {str(e)}")
        
#         driver.quit()
#         driver.quit()
#         return None, None

#     except Exception as e:
#         print(f"Error getting fbq state for {domain}: {str(e)}")
#         try:
#             driver.quit()
#         except:
#             pass
#         return None, None

# ============================== NEW EXTENSION HELPERS ==============================

def decode_obfuscated_pixel_ids(content):
    """Decode base64-encoded and URL-encoded strings that might contain pixel IDs."""
    pixel_ids = []
    
    # Base64: atob('...') calls
    b64_pattern = r'atob\s*\(\s*["\']([A-Za-z0-9+/=]+)["\']\s*\)'
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
            ids = re.findall(r'fbq\s*\(\s*["\']init["\']\s*,\s*["\'](\d{15,16})["\']', decoded_content)
            pixel_ids.extend(ids)
    except Exception:
        pass
    
    return list(set(pixel_ids)) if pixel_ids else None


def search_in_other_tag_managers(domain, html_content):
    """Fetch and scan Tealium, Adobe Launch, and Segment configs for FB pixel IDs."""
    soup = BeautifulSoup(html_content, 'html.parser')
    results = {}
    
    for script in soup.find_all('script', src=True):
        src = script.get('src', '')
        
        # Tealium iQ
        if 'utag.js' in src or 'tealium.com' in src or 'tiqcdn.com' in src:
            try:
                full_src = src if src.startswith('http') else 'https:' + src
                resp = requests.get(full_src, timeout=5, verify=False)
                ids = extract_fb_pixel_id(resp.text)
                if ids:
                    results['tealium'] = ids
                    print(f"  Found pixel IDs in Tealium for {domain}: {ids}")
            except Exception:
                pass
        
        # Adobe Launch / DTM
        if 'adobedtm.com' in src or 'launch-' in src:
            try:
                full_src = src if src.startswith('http') else 'https:' + src
                resp = requests.get(full_src, timeout=5, verify=False)
                ids = extract_fb_pixel_id(resp.text)
                if ids:
                    results['adobe_launch'] = ids
                    print(f"  Found pixel IDs in Adobe Launch for {domain}: {ids}")
            except Exception:
                pass
        
        # Segment analytics.js
        if 'cdn.segment.com' in src or ('analytics' in src and 'segment' in src):
            try:
                full_src = src if src.startswith('http') else 'https:' + src
                resp = requests.get(full_src, timeout=5, verify=False)
                ids = extract_fb_pixel_id(resp.text)
                if ids:
                    results['segment'] = ids
                    print(f"  Found pixel IDs in Segment for {domain}: {ids}")
            except Exception:
                pass
    
    return results if results else None


# WordPress / WooCommerce plugin-specific pixel patterns
wp_pixel_patterns = [
    r'pys_fb_pixel_id\s*[:=]\s*["\'](\d{15,16})["\']',           # PixelYourSite
    r'wc_facebook_pixel_id\s*[:=]\s*["\'](\d{15,16})["\']',      # WooCommerce FB
    r'pixel_coffee\s*[:=]\s*\{[^}]*id\s*[:=]\s*["\'](\d{15,16})', # Pixel Caffeine
    r'officialfacebookpixel.*?pixel_id.*?(\d{15,16})',            # Official FB for WP
    r'FacebookPixelPlugin.*?pixel_id\s*[:=]\s*["\'](\d{15,16})', # Generic FB WP Plugin
    r'"facebookPixelId"\s*:\s*"(\d{15,16})"',                     # Squarespace / generic JSON config
    r'"fbPixelId"\s*:\s*"(\d{15,16})"',                           # Squarespace variant
]

def search_wordpress_pixel_plugins(domain, html_content):
    """Check for WordPress/WooCommerce/Squarespace pixel plugin patterns in HTML."""
    all_ids = []
    for pattern in wp_pixel_patterns:
        matches = re.findall(pattern, html_content)
        if matches:
            all_ids.extend(matches)
    
    # Also check for WP plugin script paths
    if 'wp-content/plugins/' in html_content and ('facebook' in html_content.lower() or 'pixel' in html_content.lower()):
        soup = BeautifulSoup(html_content, 'html.parser')
        for script in soup.find_all('script', src=True):
            src = script.get('src', '')
            if 'wp-content/plugins/' in src and ('facebook' in src.lower() or 'pixel' in src.lower()):
                try:
                    full_src = src if src.startswith('http') else 'https://' + domain + src
                    resp = requests.get(full_src, timeout=5, verify=False)
                    ids = extract_fb_pixel_id(resp.text)
                    if ids:
                        all_ids.extend(ids)
                        print(f"  Found pixel IDs in WP plugin script for {domain}: {ids}")
                except Exception:
                    pass
    
    return list(set(all_ids)) if all_ids else None

# ==================================================================================

def get_fbq_state(domain, chromedriver_path=None):
    driver = None
    try:
        chrome_options = Options()
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument('--enable-javascript')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--dns-prefetch-disable')
        chrome_options.add_argument('--disable-extensions')
        chrome_options.add_argument('--disable-plugins')
        chrome_options.add_argument('--disable-images')  
        chrome_options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        chrome_options.add_argument('--disable-background-timer-throttling')
        chrome_options.add_argument('--disable-renderer-backgrounding')
        chrome_options.add_argument('--disable-backgrounding-occluded-windows')
        
        # Extension 1: Anti-bot-detection flags
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        chrome_options.set_capability("goog:loggingPrefs", {"performance": "ALL"})

        # Use pre-resolved path if provided (avoids concurrent installs across processes)
        driver_path = chromedriver_path or ChromeDriverManager().install()
        service = Service(driver_path)
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.set_page_load_timeout(60)

        # Extension 1: Hide navigator.webdriver flag
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        })

        # Extension 5: Intercept navigator.sendBeacon calls
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

        # Extension 9: Intercept eval() calls containing FB pixel code
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

        if not domain.startswith(('http://', 'https://')):
            domain = 'https://' + domain

        print(f"Loading {domain}...")
        driver.get(domain)

        # Extension 1: Detect bot-protection challenge pages
        try:
            page_title = driver.title.lower() if driver.title else ''
            challenge_indicators = ['just a moment', 'attention required', 'checking your browser',
                                    'access denied', 'please wait', 'ddos-guard', 'verification',
                                    'you are being redirected', 'security check']
            if any(ind in page_title for ind in challenge_indicators):
                print(f"  Bot protection detected for {domain}: '{driver.title}'")
                return 'BLOCKED_BY_BOT_PROTECTION', None
        except Exception:
            pass

        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.TAG_NAME, 'body'))
        )

        # Consent wall auto-accept: click common cookie consent buttons
        try:
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
            consent_texts = ['accept all', 'accept cookies', 'i agree', 'agree', 'allow all',
                             'accept', 'ok', 'got it', 'allow cookies', 'consent']
            consent_clicked = False
            # Try CSS selectors first
            for selector in consent_selectors:
                try:
                    btn = driver.find_element(By.CSS_SELECTOR, selector)
                    if btn.is_displayed():
                        btn.click()
                        consent_clicked = True
                        print(f"  Consent accepted via selector: {selector}")
                        break
                except:
                    pass
            # Fallback: try matching button text
            if not consent_clicked:
                try:
                    buttons = driver.find_elements(By.TAG_NAME, 'button')
                    for btn in buttons:
                        try:
                            btn_text = btn.text.strip().lower()
                            if btn_text and any(ct == btn_text for ct in consent_texts) and btn.is_displayed():
                                btn.click()
                                consent_clicked = True
                                print(f"  Consent accepted via button text: '{btn.text.strip()}'")
                                break
                        except:
                            pass
                except:
                    pass
            if consent_clicked:
                time.sleep(2)  # Wait for pixels to load after consent
        except Exception as e:
            print(f"  Consent handling skipped: {str(e)}")

        print("Page loaded, checking for Facebook Pixel...")
        
        start_time = time.time()
        fbq_state = None
        network_pixel_ids = []

        while time.time() - start_time < 10:
            try:
                # 1. Check Network Performance Logs for CAPI or Event Endpoints
                logs = driver.get_log("performance")
                for entry in logs:
                    try:
                        log_message = json.loads(entry["message"])["message"]
                        if log_message["method"] == "Network.requestWillBeSent":
                            request_data = log_message["params"]["request"]
                            url = request_data["url"]
                            if ('facebook.com/tr' in url or '/events?' in url or '/.tr?' in url or
                                    'graph.facebook.com' in url or 'connect.facebook.net/signals/' in url or
                                    'pixel.facebook.com' in url or
                                    'capig.facebook.com' in url or    # Extension 7: CAPI Gateway
                                    'web.facebook.com/tr' in url or   # Extension 7: Regional variant
                                    'm.facebook.com/tr' in url or     # Extension 7: Mobile variant
                                    'business.facebook.com' in url or # Extension 7: Business API
                                    re.search(r'/tr\?.*id=\d{15,16}', url)):  # Extension 8: First-party proxy
                                # Extract from URL params
                                match = re.search(r'id=(\d+)', url)
                                if match:
                                    network_pixel_ids.append(match.group(1))
                                # Extract pixel_id param (first-party proxies)
                                match_pid = re.search(r'pixel_id=(\d{15,16})', url)
                                if match_pid:
                                    network_pixel_ids.append(match_pid.group(1))
                                # Extract from POST body (CAPI calls use POST with JSON)
                                post_data = request_data.get("postData", "")
                                if post_data:
                                    post_ids = re.findall(r'(?:"id"|"pixel_id"|"pixelId")\s*[:"]\s*"?(\d{15,16})"?', post_data)
                                    network_pixel_ids.extend(post_ids)
                    except:
                        pass
                        
                # 2. Check window.fbq.getState() and window._fbq variant
                fbq_state = driver.execute_script("""
                    // Check standard fbq
                    if (typeof fbq !== 'undefined' && typeof fbq.getState === 'function') {
                        try {
                            const state = fbq.getState();
                            if (state && state.pixels && state.pixels.length > 0) {
                                return JSON.stringify(state);
                            }
                        } catch (e) {}
                    }
                    // Check _fbq variant (underscore)
                    if (typeof _fbq !== 'undefined' && typeof _fbq.getState === 'function') {
                        try {
                            const state = _fbq.getState();
                            if (state && state.pixels && state.pixels.length > 0) {
                                return JSON.stringify(state);
                            }
                        } catch (e) {}
                    }
                    // Check fbq.queue for queued init commands
                    if (typeof fbq !== 'undefined' && fbq.queue) {
                        try {
                            var queueStr = JSON.stringify(fbq.queue);
                            var initMatch = queueStr.match(/init["'],\\s*["'](\\d{15,16})["']/g);
                            if (initMatch && initMatch.length > 0) {
                                var ids = initMatch.map(function(m) {
                                    var id = m.match(/(\\d{15,16})/);
                                    return id ? {id: id[1]} : null;
                                }).filter(Boolean);
                                if (ids.length > 0) return JSON.stringify({pixels: ids});
                            }
                        } catch (e) {}
                    }
                    return null;
                """)
                
                if fbq_state or network_pixel_ids:
                    break  

            except Exception as e:
                print(f"Error executing script or reading logs: {str(e)}")
                break

            time.sleep(0.5)

        # 3. Check for First-Party Cookies _fbp, _fbc, fr
        fbp_cookie_present = False
        try:
            cookies = driver.get_cookies()
            fb_cookie_names = {'_fbp', '_fbc', 'fr'}
            for cookie in cookies:
                if cookie['name'] in fb_cookie_names:
                    fbp_cookie_present = True
                    break
        except Exception:
            pass

        if fbq_state:
            parsed_state = json.loads(fbq_state)
            print(f"\nFacebook Pixel State for {domain}:")
            print(json.dumps(parsed_state, indent=2))
            if fbp_cookie_present:
                parsed_state['_fbp_cookie_detected'] = True
            if network_pixel_ids:
                parsed_state['network_pixels'] = list(set(network_pixel_ids))
            return 'FBP', parsed_state
            
        if network_pixel_ids or fbp_cookie_present:
            # === Deep extraction: try every method to find hidden pixel IDs ===
            found_methods = []
            if network_pixel_ids:
                found_methods.append('CAPI_OR_NETWORK')
            
            deep_extracted_ids = []

            # Method 1: localStorage (Shopify apps like Parkour store pixel config here)
            try:
                print("Checking localStorage for pixel config...")
                storage_values = driver.execute_script("""
                    var results = [];
                    try {
                        for (var i = 0; i < localStorage.length; i++) {
                            var key = localStorage.key(i);
                            if (key.toLowerCase().includes('pixel') || key.toLowerCase().includes('facebook') ||
                                key.toLowerCase().includes('fb') || key.toLowerCase().includes('parkour') ||
                                key.toLowerCase().includes('trekkie')) {
                                results.push(localStorage.getItem(key));
                            }
                        }
                    } catch(e) {}
                    return results;
                """)
                if storage_values:
                    for val in storage_values:
                        if val:
                            found = re.findall(r'\b(\d{15,16})\b', str(val))
                            if found:
                                print(f"  Found IDs in localStorage: {set(found)}")
                                deep_extracted_ids.extend(found)
                                if 'DEEP_EXTRACTION_LOCALSTORAGE' not in found_methods:
                                    found_methods.append('DEEP_EXTRACTION_LOCALSTORAGE')
            except Exception as e:
                print(f"Error checking localStorage: {str(e)}")

            # Method 2: Shopify analytics / trekkie objects
            try:
                print("Checking Shopify analytics objects...")
                shopify_ids = driver.execute_script("""
                    var ids = [];
                    try {
                        var sa = JSON.stringify(window.ShopifyAnalytics);
                        var matches = sa.match(/\\b\\d{15,16}\\b/g);
                        if (matches) ids = ids.concat(matches);
                    } catch(e) {}
                    try {
                        var tr = JSON.stringify(window.trekkie);
                        var matches = tr.match(/\\b\\d{15,16}\\b/g);
                        if (matches) ids = ids.concat(matches);
                    } catch(e) {}
                    return ids;
                """)
                if shopify_ids:
                    print(f"  Found IDs in Shopify objects: {set(shopify_ids)}")
                    deep_extracted_ids.extend(shopify_ids)
                    if 'DEEP_EXTRACTION_SHOPIFY' not in found_methods:
                        found_methods.append('DEEP_EXTRACTION_SHOPIFY')
            except Exception as e:
                print(f"Error checking Shopify objects: {str(e)}")

            # Method 3: Full page source scan for 15-16 digit numbers
            try:
                print("Scanning full page source for pixel IDs...")
                page_source = driver.page_source
                all_numbers = re.findall(r'\b(\d{15,16})\b', page_source)
                if all_numbers:
                    print(f"  Found {len(set(all_numbers))} unique candidate IDs in page source")
                    deep_extracted_ids.extend(all_numbers)
                    if 'DEEP_EXTRACTION_SOURCE' not in found_methods:
                        found_methods.append('DEEP_EXTRACTION_SOURCE')
            except Exception as e:
                print(f"Error scanning page source: {str(e)}")

            # Method 4: Inline scripts with tracking keywords
            try:
                print("Checking inline scripts for hidden Pixel IDs...")
                hidden_ids = driver.execute_script("""
                    return Array.from(document.querySelectorAll('script')).map(s => s.innerHTML)
                        .filter(html => html.toLowerCase().includes('facebook') || html.toLowerCase().includes('fbq') || html.toLowerCase().includes('trekkie') || html.toLowerCase().includes('pixel'))
                        .map(html => html.match(/\\b\\d{15,16}\\b/g) || [])
                        .flat();
                """)
                if hidden_ids:
                    found_inline = [hid for hid in hidden_ids if hid.isdigit()]
                    if found_inline:
                        deep_extracted_ids.extend(found_inline)
                        if 'DEEP_EXTRACTION_INLINE' not in found_methods:
                            found_methods.append('DEEP_EXTRACTION_INLINE')
            except Exception as e:
                print(f"Error checking inline scripts: {str(e)}")

            # Method 5: sessionStorage scan (mirrors localStorage)
            try:
                print("Checking sessionStorage for pixel config...")
                session_values = driver.execute_script("""
                    var results = [];
                    try {
                        for (var i = 0; i < sessionStorage.length; i++) {
                            var key = sessionStorage.key(i);
                            if (key.toLowerCase().includes('pixel') || key.toLowerCase().includes('facebook') ||
                                key.toLowerCase().includes('fb') || key.toLowerCase().includes('parkour') ||
                                key.toLowerCase().includes('trekkie')) {
                                results.push(sessionStorage.getItem(key));
                            }
                        }
                    } catch(e) {}
                    return results;
                """)
                if session_values:
                    for val in session_values:
                        if val:
                            found = re.findall(r'\b(\d{15,16})\b', str(val))
                            if found:
                                print(f"  Found IDs in sessionStorage: {set(found)}")
                                deep_extracted_ids.extend(found)
                                if 'DEEP_EXTRACTION_SESSIONSTORAGE' not in found_methods:
                                    found_methods.append('DEEP_EXTRACTION_SESSIONSTORAGE')
            except Exception as e:
                print(f"Error checking sessionStorage: {str(e)}")

            # Method 6: dataLayer inspection (GTM push events contain pixel configs)
            try:
                print("Checking dataLayer for pixel config...")
                datalayer_ids = driver.execute_script("""
                    var ids = [];
                    try {
                        if (window.dataLayer && Array.isArray(window.dataLayer)) {
                            var dlStr = JSON.stringify(window.dataLayer);
                            if (dlStr.toLowerCase().includes('facebook') || dlStr.toLowerCase().includes('fbq') ||
                                dlStr.toLowerCase().includes('pixel')) {
                                var matches = dlStr.match(/\\b\\d{15,16}\\b/g);
                                if (matches) ids = matches;
                            }
                        }
                    } catch(e) {}
                    return ids;
                """)
                if datalayer_ids:
                    print(f"  Found IDs in dataLayer: {set(datalayer_ids)}")
                    deep_extracted_ids.extend(datalayer_ids)
                    if 'DEEP_EXTRACTION_DATALAYER' not in found_methods:
                        found_methods.append('DEEP_EXTRACTION_DATALAYER')
            except Exception as e:
                print(f"Error checking dataLayer: {str(e)}")

            # Method 7: SPA framework configs (__NEXT_DATA__, __NUXT__, __initialData)
            try:
                print("Checking SPA framework configs...")
                spa_ids = driver.execute_script("""
                    var ids = [];
                    var globals = ['__NEXT_DATA__', '__NUXT__', '__initialData', '__APP_DATA__'];
                    globals.forEach(function(g) {
                        try {
                            if (window[g]) {
                                var str = JSON.stringify(window[g]);
                                if (str.toLowerCase().includes('facebook') || str.toLowerCase().includes('pixel') ||
                                    str.toLowerCase().includes('fbq')) {
                                    var matches = str.match(/\\b\\d{15,16}\\b/g);
                                    if (matches) ids = ids.concat(matches);
                                }
                            }
                        } catch(e) {}
                    });
                    return ids;
                """)
                if spa_ids:
                    print(f"  Found IDs in SPA framework configs: {set(spa_ids)}")
                    deep_extracted_ids.extend(spa_ids)
                    if 'DEEP_EXTRACTION_SPA' not in found_methods:
                        found_methods.append('DEEP_EXTRACTION_SPA')
            except Exception as e:
                print(f"Error checking SPA configs: {str(e)}")

            # Method 8: Shopify Web Pixels sandbox iframes
            try:
                print("Checking Shopify Web Pixels sandbox...")
                sandbox_ids = driver.execute_script("""
                    var ids = [];
                    try {
                        var iframes = document.querySelectorAll('iframe[id*="web-pixel"], iframe[src*="web-pixel"], iframe[src*="myshopify.com"]');
                        iframes.forEach(function(iframe) {
                            try {
                                var src = iframe.getAttribute('src') || '';
                                var matches = src.match(/\\b\\d{15,16}\\b/g);
                                if (matches) ids = ids.concat(matches);
                            } catch(e) {}
                        });
                    } catch(e) {}
                    return ids;
                """)
                if sandbox_ids:
                    print(f"  Found IDs in Shopify Web Pixels sandbox: {set(sandbox_ids)}")
                    deep_extracted_ids.extend(sandbox_ids)
                    if 'DEEP_EXTRACTION_WEBPIXELS' not in found_methods:
                        found_methods.append('DEEP_EXTRACTION_WEBPIXELS')
            except Exception as e:
                print(f"Error checking Shopify Web Pixels: {str(e)}")

            # Method 9: sendBeacon() intercepted calls (Extension 5)
            try:
                print("Checking intercepted sendBeacon calls...")
                beacons = driver.execute_script("return window.__beaconCalls || []")
                for b in beacons:
                    beacon_url = b.get('url', '')
                    beacon_data = b.get('data', '')
                    if 'facebook.com' in beacon_url or 'fbevents' in beacon_url:
                        match = re.search(r'id=(\d{15,16})', beacon_url)
                        if match:
                            deep_extracted_ids.append(match.group(1))
                            if 'DEEP_EXTRACTION_BEACON' not in found_methods:
                                found_methods.append('DEEP_EXTRACTION_BEACON')
                        # Also check POST data of beacon
                        if beacon_data:
                            bid = re.findall(r'\b(\d{15,16})\b', beacon_data)
                            if bid:
                                deep_extracted_ids.extend(bid)
                                if 'DEEP_EXTRACTION_BEACON' not in found_methods:
                                    found_methods.append('DEEP_EXTRACTION_BEACON')
                        print(f"  Found beacon call to: {beacon_url[:100]}")
            except Exception as e:
                print(f"Error checking beacons: {str(e)}")

            # Method 10: eval() intercepted calls (Extension 9)
            try:
                print("Checking intercepted eval() calls...")
                eval_calls = driver.execute_script("return window.__evalCalls || []")
                for code in eval_calls:
                    if code:
                        ids = re.findall(r'\b(\d{15,16})\b', str(code))
                        if ids:
                            deep_extracted_ids.extend(ids)
                            if 'DEEP_EXTRACTION_EVAL' not in found_methods:
                                found_methods.append('DEEP_EXTRACTION_EVAL')
                            print(f"  Found IDs in eval'd code: {set(ids)}")
            except Exception as e:
                print(f"Error checking eval calls: {str(e)}")

            # Method 11: Wix platform detection (Extension 6)
            try:
                print("Checking Wix platform objects...")
                wix_ids = driver.execute_script("""
                    var ids = [];
                    try {
                        if (window.warmupData) {
                            var str = JSON.stringify(window.warmupData);
                            if (str.toLowerCase().includes('facebook') || str.toLowerCase().includes('pixel')) {
                                var matches = str.match(/\\b\\d{15,16}\\b/g);
                                if (matches) ids = ids.concat(matches);
                            }
                        }
                    } catch(e) {}
                    try {
                        if (window.wixDevelopersAnalytics) {
                            var str = JSON.stringify(window.wixDevelopersAnalytics);
                            var matches = str.match(/\\b\\d{15,16}\\b/g);
                            if (matches) ids = ids.concat(matches);
                        }
                    } catch(e) {}
                    try {
                        if (window.wixAnalytics) {
                            var str = JSON.stringify(window.wixAnalytics);
                            var matches = str.match(/\\b\\d{15,16}\\b/g);
                            if (matches) ids = ids.concat(matches);
                        }
                    } catch(e) {}
                    return ids;
                """)
                if wix_ids:
                    print(f"  Found IDs in Wix platform: {set(wix_ids)}")
                    deep_extracted_ids.extend(wix_ids)
                    if 'DEEP_EXTRACTION_WIX' not in found_methods:
                        found_methods.append('DEEP_EXTRACTION_WIX')
            except Exception as e:
                print(f"Error checking Wix: {str(e)}")

            # Method 12: Squarespace platform detection (Extension 6)
            try:
                page_source = driver.page_source
                sq_patterns = [
                    r'"facebookPixelId"\s*:\s*"(\d{15,16})"',
                    r'"fbPixelId"\s*:\s*"(\d{15,16})"',
                    r'"facebook_pixel_id"\s*:\s*"(\d{15,16})"',
                ]
                sq_ids = []
                for pattern in sq_patterns:
                    matches = re.findall(pattern, page_source)
                    sq_ids.extend(matches)
                if sq_ids:
                    print(f"  Found IDs in Squarespace/JSON config: {set(sq_ids)}")
                    deep_extracted_ids.extend(sq_ids)
                    if 'DEEP_EXTRACTION_SQUARESPACE' not in found_methods:
                        found_methods.append('DEEP_EXTRACTION_SQUARESPACE')
            except Exception as e:
                print(f"Error checking Squarespace: {str(e)}")

            # Method 13: Base64/obfuscation decoding (Extension 4)
            try:
                print("Checking for obfuscated pixel IDs (base64/URL-encoded)...")
                page_source = driver.page_source
                obf_ids = decode_obfuscated_pixel_ids(page_source)
                if obf_ids:
                    print(f"  Found IDs via obfuscation decoding: {set(obf_ids)}")
                    deep_extracted_ids.extend(obf_ids)
                    if 'DEEP_EXTRACTION_OBFUSCATED' not in found_methods:
                        found_methods.append('DEEP_EXTRACTION_OBFUSCATED')
            except Exception as e:
                print(f"Error checking obfuscation: {str(e)}")

            # Deduplicate all found IDs
            unique_ids = list(set(network_pixel_ids + deep_extracted_ids))
            print(f"  Total unique candidate IDs: {len(unique_ids)}")

            state = {
                'pixels': [{'id': pid} for pid in unique_ids],
                '_fbp_cookie_detected': fbp_cookie_present,
                'network_pixels': list(set(network_pixel_ids)),
                'deep_extracted_pixels': list(set(deep_extracted_ids))
            }
            
            # If nothing was found, don't pretend it's CAPI_OR_NETWORK
            if not unique_ids and not fbp_cookie_present and not found_methods:
                return None, None
            
            final_state_type = found_methods[0] if found_methods else 'CAPI_OR_NETWORK'
            return final_state_type, state

        try:
            print("Checking for GTM...")
            gtm_ids = driver.execute_script("""
                return Array.from(new Set([...document.documentElement.innerHTML.match(/GTM-[A-Z0-9]+/g) || []]));
            """)
        except Exception as e:
            print(f"Error checking for GTM: {str(e)}")
            gtm_ids = []

        if gtm_ids:
            print(f'Found GTM in headless: {str(gtm_ids)}')
            implementations = []
            
            for gtm_id in gtm_ids:
                print(f'Analyzing : {gtm_id}')
                try:
                    implementation_type, pixel_ids = search_for_pixel_in_gtm(domain, gtm_id)
                    if pixel_ids:
                        print(f'Found Pixel for {domain} in GTM {gtm_id}')
                        for pixel_id in pixel_ids:
                            implementations.append(pixel_id)
                    else:
                        print(f'No Pixels found in {gtm_id}')
                except Exception as e:
                    print(f"Error analyzing GTM {gtm_id}: {str(e)}")
            
            if implementations:
                return 'GTM', implementations 

        try:
            print(f"Checking HTML source for Facebook Pixel code...")
            html_content = driver.page_source
            
            if "fbq(" in html_content or "facebook-jssdk" in html_content or "connect.facebook.net" in html_content:
                pixel_patterns = [
                    r"fbq\(\s*['\"]init['\"]\s*,\s*['\"](\d+)['\"]\s*\)",
                    r"facebook\.com/tr\?id=(\d+)",
                    r"pixelId['\"]?\s*[:=]\s*['\"](\d+)['\"]",
                ]
                
                all_pixel_ids = []
                for pattern in pixel_patterns:
                    matches = re.findall(pattern, html_content)
                    all_pixel_ids.extend(matches)
                
                unique_pixel_ids = list(set(all_pixel_ids))
                if unique_pixel_ids:
                    return 'HTML', unique_pixel_ids
                else:
                    print("Facebook Pixel code found but no pixel IDs extracted")
            else:
                print("No Facebook Pixel code detected")
                
        except Exception as e:
            print(f"Error checking HTML: {str(e)}")
        
        return None, None

    except Exception as e:
        print(f"Error getting fbq state for {domain}: {str(e)}")
        return None, None
        
    finally:
        if driver:
            try:
                driver.current_url
                driver.quit()
                print("Driver closed successfully")
            except Exception as e:
                print(f"Driver was already closed or crashed: {str(e)}")
                try:
                    driver.service.stop()
                except:
                    pass


# ========================================================================== CHECK FOR FACEBOOK PIXEL ON OTHER THIRD PARTIES =====================================================================
@dataclass
class FacebookPixelImplementation:
    pixel_id: str
    implementation_type: str
    script_url: Optional[str]
    script_content: str
    context: str
    custom_config: Dict

def get_fb_patterns():
    patterns = {
        'pixel_ids': [
            r'fbq\s*\(\s*[\'"]init[\'"]\s*,\s*[\'"](\d{15,16})[\'"]',
            r'https://connect\.facebook\.net/.+/fbevents\.js#xfbml=1&version=.*&pixelid=(\d{15,16})',
            r'fb_pixel_id\s*[:=]\s*[\'"](\d{15,16})[\'"]',
            r'pixel_id\s*[:=]\s*[\'"](\d{15,16})[\'"]',
            r'facebook_pixel_id\s*[:=]\s*[\'"](\d{15,16})[\'"]',
            r'facebook\.com/tr\?id=(\d{15,16})',
            r'pixel:\s*{[^}]*id:\s*[\'"]?(\d{15,16})[\'"]?',
        ],
        'base_code': [
            r'!function\(f,b,e,v,n,t,s\).*fbevents\.js.*\(window,\s*document,\s*[\'"]script[\'"]\s*,\s*[\'"]https://connect\.facebook\.net/en_US/fbevents\.js[\'"]',
            r'fbq\s*\(\s*[\'"]init[\'"]',
            r'window\.fbq\s*=\s*function\(\)',
        ],
        'lightweight': [
            r'<img\s+height="1"\s+width="1"\s+.*?facebook\.com/tr\?id=\d{15,16}',
            r'<noscript>.*?facebook\.com/tr\?id=\d{15,16}.*?</noscript>',
            r'https://connect\.facebook\.net/.+/fbevents\.js#.*?pixelid=\d{15,16}',
        ],
        'custom_events': [
            r'fbq\s*\(\s*[\'"]track[\'"]',
            r'fbq\s*\(\s*[\'"]trackCustom[\'"]',
        ]
    }
    
    return {
        category: [re.compile(pat, re.IGNORECASE | re.MULTILINE)
                  for pat in pattern_list]
        for category, pattern_list in patterns.items()
    }

def extract_pixel_id(content, patterns):
    """Extract Facebook Pixel ID from content."""
    for pattern in patterns['pixel_ids']:
        match = re.search(pattern, content)
        if match and match.group(1):
            pixel_id = match.group(1)
            if re.match(r'^\d{15,16}$', pixel_id):
                return pixel_id
    return None

def analyze_script_content(content, url, patterns):
    """Analyze script content for Facebook Pixel implementations."""
    pixel_id = extract_pixel_id(content, patterns)
    if not pixel_id:
        return None

    implementation_type = 'standard'
    if any(pattern.search(content) for pattern in patterns['lightweight']):
        implementation_type = 'lightweight'
    elif url and 'facebook' not in url.lower():
        implementation_type = 'third-party'

    custom_events = []
    for pattern in patterns['custom_events']:
        matches = pattern.finditer(content)
        for match in matches:
            start = max(0, match.start() - 50)
            end = min(len(content), match.end() + 150)
            custom_events.append(content[start:end])
    
    custom_config = {'custom_events': custom_events} if custom_events else {}

    pixel_match = re.search(re.escape(pixel_id), content)
    context = ""
    if pixel_match:
        start = max(0, pixel_match.start() - 100)
        end = min(len(content), pixel_match.end() + 100)
        context = content[start:end]

    return FacebookPixelImplementation(
        pixel_id=pixel_id,
        implementation_type=implementation_type,
        script_url=url,
        script_content=content[:1000] if len(content) > 1000 else content,
        context=context,
        custom_config=custom_config
    )

def fetch_and_analyze_script(script_url, patterns):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'DNT': '1',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1'
    }

    try:
        response = requests.get(script_url, headers=headers, timeout=10)
        response.raise_for_status()
        return analyze_script_content(response.text, script_url, patterns)
    except RequestException as e:
        return None

def analyze_single_script(script, base_url, patterns, processed_urls, processed_urls_lock):
    try:
        if hasattr(script, 'src') and script.get('src'):
            script_url = urljoin(base_url, script.get('src'))
            # Use a lock so two threads can't both pass the "not in" check
            # before either has called .add(), which would cause duplicate
            # fetches and silent misses due to set corruption.
            with processed_urls_lock:
                if script_url in processed_urls:
                    return None
                processed_urls.add(script_url)
            return fetch_and_analyze_script(script_url, patterns)
        elif script.string:
            return analyze_script_content(script.string, base_url, patterns)
        elif isinstance(script, Tag):
            return analyze_script_content(str(script), base_url, patterns)
    except Exception as e:
        logging.error(f"Error analyzing script: {e}")
    return None



def find_fbp_on_other_thirdparties(domain, content):
    logger = logging.getLogger(__name__)
    
    base_url = domain if domain.startswith(('http://', 'https://')) else 'https://' + domain
    logger.info(f"Analyzing {base_url}")

    try:
        patterns = get_fb_patterns()
        implementations = []
        processed_urls = set()
        processed_urls_lock = threading.Lock()
        soup = BeautifulSoup(content, 'html.parser')

        scripts_to_analyze = []
        scripts_to_analyze.extend(soup.find_all('noscript'))
        scripts_to_analyze.extend(soup.find_all('script', src=False))
        scripts_to_analyze.extend(soup.find_all('script', src=True))

        analyze_script = partial(analyze_single_script,
                               base_url=base_url,
                               patterns=patterns,
                               processed_urls=processed_urls,
                               processed_urls_lock=processed_urls_lock)

        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_script = {
                executor.submit(analyze_script, script): script 
                for script in scripts_to_analyze
            }

            for future in as_completed(future_to_script):
                try:
                    implementation = future.result()
                    if implementation:
                        implementations.append(implementation)
                except Exception as e:
                    logger.error(f"Error processing script: {e}")

        if implementations:
            return {
                'url': base_url,
                'implementations': [asdict(impl) for impl in implementations],
                'total_implementations': len(implementations),
                'unique_pixels': len(set(impl.pixel_id for impl in implementations))
            }
        
        return None

    except Exception as e:
        logger.error(f"Error analyzing {base_url}: {str(e)}")
        return None

# ================================================================================================================================================================================================
# ================================================================================= CHECK FOR FACEBOOK SOCIAL MEDIA PRESENCE =====================================================================
def find_facebook_page(html_string):
    soup = BeautifulSoup(html_string, 'html.parser')
    
    indicators = [
        {'class_': re.compile(r'(?i)(facebook|fb|social|follow)')},
        {'id': re.compile(r'(?i)(facebook|fb|social|follow)')},
        {'string': re.compile(r'(?i)(facebook|follow us|social)')}
    ]
    
    url_patterns = [
        r'facebook\.com/(?!sharer|share|login|photo|events|groups|gaming|watch|marketplace)[\w\.-]+/?$',
        r'fb\.me/[\w\.-]+/?$'
    ]
    
    potential_links = set()
    
    for indicator in indicators:
        anchors = soup.find_all('a', **indicator)
        for anchor in anchors:
            href = anchor.get('href')
            if href:
                if any(re.search(pattern, href.lower()) for pattern in url_patterns):
                    potential_links.add(href)
    
    
    icon_elements = soup.find_all(['i', 'span', 'div'], class_=re.compile(r'(?i)(fa-facebook|facebook-icon|icon-fb)'))
    for icon in icon_elements:
        parent_anchor = icon.find_parent('a')
        if parent_anchor and parent_anchor.get('href'):
            href = parent_anchor.get('href')
            if any(re.search(pattern, href.lower()) for pattern in url_patterns):
                potential_links.add(href)
    
    social_containers = soup.find_all(['div', 'section', 'footer'], class_=re.compile(r'(?i)(social|footer)'))
    for container in social_containers:
        anchors = container.find_all('a')
        for anchor in anchors:
            href = anchor.get('href')
            if href and any(re.search(pattern, href.lower()) for pattern in url_patterns):
                potential_links.add(href)
    
    return list(potential_links)

def check_website_facebook(content):
    try:
        facebook_pages = find_facebook_page(content)
        return facebook_pages
    except Exception as e:
        print(f"Error: {e}")
        return []
    
# ================================================================================================================================================================================================
# ================================================================================================================================================================================================
#                                                                                                    CORE
# ================================================================================================================================================================================================

def _process_single_domain(args):
    """
    Worker function used by find_FBP's thread pool.
    Returns a dict of state changes so the caller can merge them under a lock.
    """
    i, domain, total = args
    result = {
        'domain': domain,
        'pixels_found': None,
        'valid_html_but_flagged': None,
        'invalid_html': False,
        'hanged': False,
        'found_nothing': False,
        'second_run': False,
        'timing': None,
    }
    start_time = time.time()
    print('================================================================================================================================')
    print(f"{i}) Processing domain: {domain}    | total: {total}")
    try:
        content = fetch_html(i, domain)
        if content:
            if content.startswith('Error'):
                result['invalid_html'] = True
            else:
                redirect_flag, url = check_meta_refresh(content, domain)
                if redirect_flag:
                    redirected_content = fetch_html(i, url)
                    # Only use the redirect content if it's real HTML, not an error string
                    if redirected_content and not redirected_content.startswith('Error'):
                        content = redirected_content
                    elif redirected_content is None:
                        # Redirect target completely failed — treat as hanged
                        print(f'Redirect hanged: {domain}')
                        result['hanged'] = True
                        return result
                    # If redirect returned an Error string, keep the original content

                if content:
                    raw_lines, formatted_lines, formatted_content = count_html_lines(content)
                    if (raw_lines < 30) and (formatted_lines < 30):
                        result['valid_html_but_flagged'] = formatted_content
                    else:
                        print(f'Fetched {domain}')
                        fbpixel_core = identify_facebook_pixel_core_implementation(domain, content)
                        if fbpixel_core:
                            result['pixels_found'] = {'PIXEL_CORE': fbpixel_core}
                        else:
                            fbpixel_in_the_wild = identify_fbp_basecode_in_the_wild(domain, content)
                            if fbpixel_in_the_wild:
                                result['pixels_found'] = {'PIXEL_WILD': fbpixel_in_the_wild}
                            else:
                                pixel_in_gtm = search_in_gtm(domain, content)
                                if pixel_in_gtm[domain]['found_flag'] == 1:
                                    result['pixels_found'] = {'PIXEL_GTM': pixel_in_gtm}
                                else:
                                    pixels_in_other_tp = find_fbp_on_other_thirdparties(domain, content)
                                    if pixels_in_other_tp:
                                        print('Found Pixel in other third party scripts')
                                        result['pixels_found'] = {'PIXEL_IN_OTHER_TP': pixels_in_other_tp}
                                    else:
                                        # Extension 2: Check non-GTM tag managers (Tealium, Adobe Launch, Segment)
                                        other_tm_results = search_in_other_tag_managers(domain, content)
                                        if other_tm_results:
                                            # Determine best state type from results
                                            if 'tealium' in other_tm_results:
                                                tm_type = 'PIXEL_TEALIUM'
                                            elif 'adobe_launch' in other_tm_results:
                                                tm_type = 'PIXEL_ADOBE_LAUNCH'
                                            elif 'segment' in other_tm_results:
                                                tm_type = 'PIXEL_SEGMENT'
                                            else:
                                                tm_type = 'PIXEL_OTHER_TM'
                                            print(f'Found Pixel in {tm_type} for {domain}')
                                            result['pixels_found'] = {tm_type: other_tm_results}
                                        else:
                                            # Extension 3: Check WordPress/WooCommerce plugin patterns
                                            wp_ids = search_wordpress_pixel_plugins(domain, content)
                                            if wp_ids:
                                                print(f'Found Pixel via WordPress plugin for {domain}: {wp_ids}')
                                                result['pixels_found'] = {'PIXEL_WORDPRESS': wp_ids}
                                            else:
                                                # Extension 4: Check for obfuscated pixel IDs (base64/URL-encoded)
                                                obf_ids = decode_obfuscated_pixel_ids(content)
                                                if obf_ids:
                                                    print(f'Found obfuscated Pixel IDs for {domain}: {obf_ids}')
                                                    result['pixels_found'] = {'PIXEL_OBFUSCATED': obf_ids}
                                                else:
                                                    # Check for <link> preconnect/prefetch hints to Facebook
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
                                                        result['second_run'] = True
                                                    else:
                                                        result['found_nothing'] = True

                    result['timing'] = f"{time.time() - start_time:.2f}"
                else:
                    print(f'Redirect hanged: {domain}')
                    result['hanged'] = True
        else:
            print(f'Totally hanged {domain}')
            result['hanged'] = True
        print('================================================================================================================================')
    except Exception as e:
        print(f"Exception processing domain {domain}: {e}")
        print('================================================================================================================================')
    return result


def find_FBP(domains_list_path=None, domain_single=None, flag=0, skip_domains=None):

    global valid_html_but_flagged, invalid_html_no_response, pixels_found, found_nothing, baseline_timing_dict, hanging_doms

    if skip_domains is None:
        skip_domains = set()

    domains = []
    if flag == 0:
        domains = get_domains_as_list(domains_list_path)
    else:
        domains = [domain_single]

    original_total = len(domains)
    domains = [d for d in domains if d not in skip_domains]
    if original_total > len(domains):
        print(f"Resume Mode: Skipping {original_total - len(domains)} already successful domains. Crawling {len(domains)} domains.")

    total = len(domains)
    found_so_far = 0

    # Phase 1 is I/O-bound (aiohttp fetches + BS4 parsing + sync HTTP calls).
    # Use threads so all cores can overlap on network waits.
    # 10 workers matches the 10 available cores; tune down if memory is tight.
    max_fetch_workers = 10

    args_list = [(i, domains[i], total) for i in range(total)]

    with ThreadPoolExecutor(max_workers=max_fetch_workers) as executor:
        futures = {executor.submit(_process_single_domain, args): args[1] for args in args_list}
        for future in as_completed(futures):
            domain = futures[future]
            try:
                r = future.result()
                with _global_lock:
                    if r['pixels_found'] is not None:
                        pixels_found[domain] = r['pixels_found']
                        found_so_far += 1
                    if r['valid_html_but_flagged'] is not None:
                        valid_html_but_flagged[domain] = r['valid_html_but_flagged']
                    if r['invalid_html']:
                        invalid_html_no_response.append(domain)
                    if r['hanged']:
                        hanging_doms.append(domain)
                    if r['found_nothing']:
                        found_nothing.append(domain)
                    if r['second_run']:
                        second_run_stateless.append(domain)
                    if r['timing'] is not None:
                        baseline_timing_dict[domain] = r['timing']
            except Exception as e:
                print(f"Error processing {domain}: {e}")

    return domains



def process_domain(domain, chromedriver_path=None):
    try:
        start_time = time.time()
        state_type, state = get_fbq_state(domain, chromedriver_path=chromedriver_path)
        print('====================')
        print(state_type)
        print(state)
        print('====================')

        domain_pixel_ids = []
        
        if state: 
            if 'pixels' in state:
                for pixel in state['pixels']:
                    domain_pixel_ids.append(pixel['id'])
            else:
                if len(state) > 0:
                    for pixel_id in state:
                        domain_pixel_ids.append(pixel_id)
        
        processing_time = f"{time.time() - start_time:.2f}"
        logger.info(f"Processed {domain} in {processing_time} seconds")
        
        return domain, domain_pixel_ids,processing_time, state_type  
    
    except Exception as e:
        logger.error(f"Error processing {domain}: {e}")
        return domain, [], "0.00", None
    


def find_pixel_ids_state(domains, max_workers=8):
    global found_nothing
    pixels_found = {}
    timing_dict = {} 
    timeout_count = 0
    error_count = 0
    empty_count = 0
    
    logger.info(f"Starting processing of {len(domains)} domains")

    if len(domains) < 3:
        max_workers = max(1, len(domains))

    # Resolve ChromeDriver path once here, before spawning subprocesses.
    # Calling ChromeDriverManager().install() inside each subprocess causes
    # concurrent network requests and file-locking races on the binary.
    try:
        chromedriver_path = ChromeDriverManager().install()
        logger.info(f"ChromeDriver resolved at: {chromedriver_path}")
    except Exception as e:
        logger.error(f"Failed to resolve ChromeDriver: {e}")
        chromedriver_path = None

    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(process_domain, domain, chromedriver_path): domain for domain in domains}
        
        try:
            for future in as_completed(futures):
                domain = futures[future]
                try:
                    domain, pixel_ids, process_time, state_type = future.result() 
                    timing_dict[domain] = process_time  
                    if pixel_ids:
                        serializable_ids = []
                        for pid in pixel_ids:
                            try:
                                json.dumps(pid)
                                serializable_ids.append(pid)
                            except (TypeError, OverflowError):
                                serializable_ids.append(str(pid))

                        pixels_found[domain] = {
                            'pixel_ids': serializable_ids,
                            'state_type': str(state_type)
                        }
                    else:
                        empty_count += 1
                        logger.info(f"No pixels found for domain: {domain}")
                        found_nothing.append(domain)
                except concurrent.futures.TimeoutError:
                    timeout_count += 1
                    logger.warning(f"Timeout for domain: {domain}")
                except Exception as exc:
                    error_count += 1
                    logger.error(f'{domain} generated an exception: {exc}')
        
        except concurrent.futures.TimeoutError:
            remaining = sum(1 for f in futures if not f.done())
            logger.error(f"Overall process timed out with {remaining} domains remaining")
        
        finally:
            cancelled = 0
            for future in futures:
                if not future.done():
                    future.cancel()
                    cancelled += 1
            
            avg_time = sum(float(t) for t in timing_dict.values()) / len(timing_dict) if timing_dict else 0
            logger.info(f"""
                Processing complete:
                - Successful with pixels: {len(pixels_found)}
                - No pixels found: {empty_count}
                - Individual timeouts: {timeout_count}
                - Errors: {error_count}
                - Cancelled: {cancelled}
                Total domains: {len(domains)}
                Average processing time: {avg_time:.2f} seconds
            """)
            
            executor.shutdown(wait=True)
    
    return pixels_found, timing_dict 


# ================================================================================================================================================================================================
# ================================================================================================================================================================================================


def main():

    help_panel = """Example execution: python3 get_statically_all_pixel_instances.py -[f/d] -[path/domain]
    where:
    \t  -f -path  : specify a text file (of domains) usage and providing the corresponding path
    \t  -d -domain: specify a single domain usage and providing the domain 
    """
    path = ''
    domain = ''

    if len(sys.argv) != 3:
        print(help_panel)
        exit()
    else:
        if sys.argv[1] == '-f':
            path = sys.argv[2]
        elif sys.argv[1] == '-d':
            domain = sys.argv[2]
        else:
            print(help_panel)
            exit()

    global found_nothing, second_run_stateless, valid_html_but_flagged, invalid_html_no_response, pixels_found
    global headless_timing_dict, baseline_timing_dict, hanging_doms
    start_time = time.time()
    
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    batch_label = 'single_domain'
    if path:
        batch_label = os.path.splitext(os.path.basename(path))[0]
    output_dir = os.path.join(project_root, 'CrawlerOutputs', f'crawler_output_{batch_label}')
    os.makedirs(output_dir, exist_ok=True)
    
    # Load previously successful domains to skip them
    existing_pixels_found = {}
    existing_state_fbq = {}
    if os.path.exists(os.path.join(output_dir, 'pixels_found.json')):
        try:
            with open(os.path.join(output_dir, 'pixels_found.json'), 'r') as f:
                existing_pixels_found = json.load(f)
        except: pass
    if os.path.exists(os.path.join(output_dir, 'state_fbq.json')):
        try:
            with open(os.path.join(output_dir, 'state_fbq.json'), 'r') as f:
                existing_state_fbq = json.load(f)
        except: pass
        
    skip_domains = set(existing_pixels_found.keys()).union(set(existing_state_fbq.keys()))

    total_doms = []
    
    if len(domain) > 1:
        if domain.startswith('www.'):
            pass
        else:
            domain = 'www.'+domain
        
        total_doms = find_FBP(None,domain,1, skip_domains)
    else:
        total_doms = find_FBP(path,None,0, skip_domains)
    
    print('--------------------------------------------------------------------------------------------------------------')
    print('                                 PERFORMING STATE SEARCH                                                      ')
    print('--------------------------------------------------------------------------------------------------------------')
    max_workers = 8  
    
    try:
        total_headless = []
        for domain in total_doms:
            if domain not in pixels_found.keys(): 
                total_headless.append(domain)

        # Also include second_run_stateless domains (hinted at Facebook but not found statically)
        for domain in second_run_stateless:
            if domain not in pixels_found.keys():
                total_headless.append(domain)

        total_headless = list(set(total_headless))
        

        state_fbq, timings = find_pixel_ids_state(total_headless, max_workers=max_workers)
        headless_timing_dict = timings
        logger.info(f"State search completed. Found pixel IDs for {len(state_fbq)} domains")
    except Exception as e:
        logger.error(f"Error during state search: {e}")
        state_fbq = {}  



    total_static_detected = len(pixels_found.keys())
    total_headless_detected = len(state_fbq.keys()) if state_fbq else 0
    grand_total = total_static_detected + total_headless_detected

    print('\nFINAL EXECUTION SUMMARY')
    print(f"\nTotal domains processed: {len(total_doms)}")
    print(f"Domains detected via Static Analysis: {total_static_detected}")
    print(f"Domains detected via Headless Fallback: {total_headless_detected}")
    print(f"Total domains with pixels found: {grand_total}")
    if len(total_doms) > 0:
        print(f"Overall Detection Rate: {(grand_total / len(total_doms)) * 100:.2f}%")
    print(f'Total execution time: {time.time() - start_time:.2f} seconds')
    
    def load_txt_list(filepath):
        if not os.path.exists(filepath): return []
        with open(filepath, 'r') as f: return [line.strip() for line in f if line.strip()]
        
    def save_txt_list(filepath, data_set):
        with open(filepath, 'w') as f:
            for d in data_set: f.write(d + '\n')
            
    def load_json_dict(filepath):
        if not os.path.exists(filepath): return {}
        try:
            with open(filepath, 'r') as f: return json.load(f)
        except: return {}

    existing_baseline = load_json_dict(os.path.join(output_dir, 'baseline_timings.json'))
    existing_headless = load_json_dict(os.path.join(output_dir, 'headless_timings.json'))
    existing_erroneous = load_json_dict(os.path.join(output_dir, 'flagged_erroneous_html_responses.json'))
    
    existing_invalid = set(load_txt_list(os.path.join(output_dir, 'invalid_html_no_response.txt')))
    existing_found_nothing = set(load_txt_list(os.path.join(output_dir, 'found_nothing.txt')))
    existing_hanged = set(load_txt_list(os.path.join(output_dir, 'total_hanged.txt')))
    merged_pixels_found = {**existing_pixels_found, **pixels_found}
    merged_state_fbq = {**existing_state_fbq, **(state_fbq if state_fbq else {})}
    merged_baseline = {**existing_baseline, **baseline_timing_dict}
    merged_headless = {**existing_headless, **headless_timing_dict}
    merged_erroneous = {**existing_erroneous, **valid_html_but_flagged}
    
    all_success = set(merged_pixels_found.keys()).union(set(merged_state_fbq.keys()))
    
    merged_invalid = existing_invalid.union(invalid_html_no_response) - all_success
    merged_found_nothing = existing_found_nothing.union(found_nothing) - all_success
    merged_hanged = existing_hanged.union(hanging_doms) - all_success

    with open(os.path.join(output_dir, 'baseline_timings.json'), 'w') as f:
        json.dump(merged_baseline, f, indent=4)

    with open(os.path.join(output_dir, 'headless_timings.json'), 'w') as f:
        json.dump(merged_headless, f, indent=4)

    with open(os.path.join(output_dir, 'flagged_erroneous_html_responses.json'), 'w') as f:
        json.dump(merged_erroneous, f, indent=4)

    with open(os.path.join(output_dir, 'pixels_found.json'), 'w') as f:
        json.dump(merged_pixels_found, f, indent=4)

    save_txt_list(os.path.join(output_dir, 'invalid_html_no_response.txt'), merged_invalid)
    save_txt_list(os.path.join(output_dir, 'found_nothing.txt'), merged_found_nothing)
    save_txt_list(os.path.join(output_dir, 'total_hanged.txt'), merged_hanged)

    with open(os.path.join(output_dir, 'state_fbq.json'), 'w') as f:
        json.dump(merged_state_fbq, f, indent=4)

if __name__ == "__main__":
    main()