import os
import re
import sys
import json

import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns
from matplotlib.ticker import FixedLocator
from tabulate import tabulate


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, os.pardir, os.pardir))


def load_json_file(file_path):
    if not os.path.exists(file_path):
        return {}

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except json.JSONDecodeError:
        return {}

    return data if isinstance(data, dict) else {}


def normalize_domain(domain):
    return str(domain).strip().lower().replace('www.', '')


def parse_batch_metadata(run_name):
    if run_name.endswith('_new'):
        return None

    match = re.match(r'^crawler_output_batch_(\d+)_(\d+)_(\d+)$', run_name)
    if not match:
        return None

    min_rank = int(match.group(2))
    max_rank = int(match.group(3))

    return {
        'name': run_name,
        'label': f'{min_rank:,}-{max_rank:,}',
        'min_rank': min_rank,
        'max_rank': max_rank,
    }


def resolve_tranco_path():
    candidates = [
        os.path.join(REPO_ROOT, 'tranco', 'top-1m-new.csv'),
    ]

    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate

    return candidates[0]



def read_tranco_list(file_path):
    domains_dict = {}
    
    try:
        df = pd.read_csv(file_path, header=None, names=['rank', 'domain'])
        df['domain'] = df['domain'].astype(str).map(normalize_domain)
        df['rank'] = pd.to_numeric(df['rank'], errors='coerce')
        df = df.dropna(subset=['rank'])
        domains_dict = {row['domain']: int(row['rank']) for _, row in df.iterrows()}
        
    except FileNotFoundError:
        print(f"Error: File not found at {file_path}")
    except Exception as e:
        print(f"Error reading file: {e}")
    
    return domains_dict


def categorize_static_entry(pixel_entry):
    if not isinstance(pixel_entry, dict):
        return 'Static.Other_TP'

    entry_keys = set(pixel_entry.keys())

    if entry_keys & {'PIXEL_CORE', 'PIXEL_FACEBOOK', 'PIXEL_META', 'PIXEL_FBQ'}:
        return 'Static.Meta_Pixel'

    if 'PIXEL_GTM' in entry_keys or any('gtm' in key.lower() for key in entry_keys):
        return 'Static.GTM'

    if entry_keys:
        return 'Static.Other_TP'

    return 'Static.Other_TP'


def categorize_headless_entry(state_entry):
    if not isinstance(state_entry, dict):
        return 'Dynamic.Other_TP'

    state_type = str(state_entry.get('state_type', '')).upper()

    if state_type == 'FBP':
        return 'Dynamic.Meta_Pixel'
    if state_type == 'GTM':
        return 'Dynamic.GTM'

    return 'Dynamic.Other_TP'


def find_batch_directories(crawler_outputs_dir):
    preferred_roots = []

    for container_name in ('NewTranco_in_Batches',):
        container_path = os.path.join(crawler_outputs_dir, container_name)
        if not os.path.isdir(container_path):
            continue

        batch_dirs = []
        for run_name in sorted(os.listdir(container_path)):
            batch_meta = parse_batch_metadata(run_name)
            if not batch_meta:
                continue

            path = os.path.join(container_path, run_name)
            if os.path.isdir(path):
                batch_dirs.append((path, batch_meta))

        if batch_dirs:
            preferred_roots.append((container_path, batch_dirs))

    if preferred_roots:
        return preferred_roots

    fallback_dirs = []
    for run_name in sorted(os.listdir(crawler_outputs_dir)):
        batch_meta = parse_batch_metadata(run_name)
        if not batch_meta:
            continue

        path = os.path.join(crawler_outputs_dir, run_name)
        if os.path.isdir(path):
            fallback_dirs.append((path, batch_meta))

    return [(crawler_outputs_dir, fallback_dirs)] if fallback_dirs else []


def load_crawler_batch_dataset(crawler_outputs_dir):
    fbpixel_websites = {}
    batch_buckets = []

    if not os.path.isdir(crawler_outputs_dir):
        print(f"CrawlerOutputs directory not found at {crawler_outputs_dir}")
        return fbpixel_websites, batch_buckets

    batch_dirs = 0
    batch_roots = find_batch_directories(crawler_outputs_dir)

    if not batch_roots:
        print(f"No batch folders found under {crawler_outputs_dir}")
        return fbpixel_websites, batch_buckets

    for root_path, batch_entries in batch_roots:
        print(f"Scanning batch root: {root_path}")

        for path, batch_meta in batch_entries:
            if not os.path.isdir(path):
                continue

            print(f"Found batch folder: {path}")

            static_path = os.path.join(path, 'pixels_found.json')
            headless_path = os.path.join(path, 'state_fbq.json')

            if not os.path.exists(static_path) and not os.path.exists(headless_path):
                continue

            batch_dirs += 1
            batch_domains = set()

            static_pixels = load_json_file(static_path)
            for domain, pixel_entry in static_pixels.items():
                domain = normalize_domain(domain)
                batch_domains.add(domain)
                record = fbpixel_websites.setdefault(domain, {'Pixel_Types': []})
                pixel_type = categorize_static_entry(pixel_entry)
                if pixel_type not in record['Pixel_Types']:
                    record['Pixel_Types'].append(pixel_type)

            headless_pixels = load_json_file(headless_path)
            for domain, state_entry in headless_pixels.items():
                domain = normalize_domain(domain)
                batch_domains.add(domain)
                record = fbpixel_websites.setdefault(domain, {'Pixel_Types': []})
                pixel_type = categorize_headless_entry(state_entry)
                if pixel_type not in record['Pixel_Types']:
                    record['Pixel_Types'].append(pixel_type)

            batch_meta['domains'] = sorted(batch_domains)
            batch_buckets.append(batch_meta)

    batch_buckets.sort(key=lambda item: item['min_rank'])
    print(f"Loaded {len(fbpixel_websites)} unique domains from {batch_dirs} crawler batch folders")
    return fbpixel_websites, batch_buckets


def select_primary_pixel_type(pixel_types):
    if not pixel_types:
        return 'Unknown'

    priority = [
        'Dynamic.Meta_Pixel',
        'Dynamic.GTM',
        'Static.Meta_Pixel',
        'Static.GTM',
        'Static.Other_TP',
        'Dynamic.Other_TP',
    ]

    pixel_type_set = set(pixel_types)
    for candidate in priority:
        if candidate in pixel_type_set:
            return candidate

    return sorted(pixel_type_set)[0]


def plot_pixel_adoption_by_rank(batch_buckets, tranco_domains):
    buckets_with_ranked_domains = []
    for bucket in batch_buckets:
        ranked_domains = [
            domain for domain in bucket.get('domains', [])
            if domain in tranco_domains
            and bucket['min_rank'] <= tranco_domains[domain] <= bucket['max_rank']
        ]
        buckets_with_ranked_domains.append((bucket, ranked_domains))

    total_bucket_domains = sum(len(bucket.get('domains', [])) for bucket in batch_buckets)
    total_ranked_domains = sum(len(ranked_domains) for _, ranked_domains in buckets_with_ranked_domains)

    print(f"Total Facebook Pixel domains across batches: {total_bucket_domains}")
    print(f"Domains with ranking information across batches: {total_ranked_domains}")

    if not buckets_with_ranked_domains:
        print("No batch buckets found. Check CrawlerOutputs folder structure.")
        return

    adoption_rates = []
    labels = []
    for bucket, ranked_domains in buckets_with_ranked_domains:
        total_in_bucket = bucket['max_rank'] - bucket['min_rank'] + 1
        with_pixel = len(ranked_domains)
        adoption_rate = (with_pixel / total_in_bucket) * 100 if total_in_bucket > 0 else 0
        adoption_rates.append(adoption_rate)
        labels.append(bucket['label'])
    
    fig, ax = plt.subplots(figsize=(24, 17))
    dark_blue = 'royalblue'
    
    bars = ax.bar(labels, adoption_rates, color=dark_blue)
    for i, rate in enumerate(adoption_rates):
        ax.text(i, rate + 0.5, f"{rate:.2f}%", ha='center', fontsize=45, fontweight='bold')
    
    ax.set_ylim(0, 30)    
    ax.set_xlabel("Website Ranking Bracket", fontsize=30, fontweight='bold')
    ax.set_ylabel("Meta's Pixel Adoption Rate (%)", fontsize=50, fontweight='bold')

    plt.xticks(fontsize=45, rotation=45)
    plt.yticks(fontsize=45)
    
    plt.grid(axis='y', linestyle='--', alpha=0.3)
    plt.tight_layout(rect=[0, 0.03, 1, 0.97])  
    plt.savefig("facebook_pixel_adoption_by_rank.pdf", dpi=300)
    plt.show()



def filter_top_10k_domains_EC2(items_dict, tranco_domains):
    top_10k = {}
    
    for domain in items_dict:
        if domain in tranco_domains and tranco_domains[domain] <= 10000:
            top_10k[domain] = items_dict[domain]
    
    print(f"Total domains: {len(items_dict)}")
    print(f"Domains in top 10K: {len(top_10k)}")
    
    return top_10k


def get_domains_dynamic_found(dynamic_folder):
    fbp_domains = []
    for path, subdirs, files in os.walk(dynamic_folder):
        for name in files:
            if name.endswith("_config_urls.json"):
                temp_path = os.path.join(path,name)
                # print(temp_path)
                temp = []
                with open(temp_path,"r") as f:
                    temp = json.load(f)
                # total += (len(list(set(temp.keys()))))
                    for key in temp.keys():
                        fbp_domains.append(key.replace('www.',''))

    for path, subdirs, files in os.walk(dynamic_folder):
        for name in files:
            if name.endswith("_report_urls.json"):
                temp_path = os.path.join(path,name)
                # print(temp_path)
                temp = []
                with open(temp_path,"r") as f:
                    temp = json.load(f)
                # total += (len(list(set(temp.keys()))))
                    for key in temp.keys():
                        if key.replace('www.','') not in fbp_domains:
                            fbp_domains.append(key.replace('www.',''))

    fbp_domains = list(set(fbp_domains))
    return fbp_domains





def get_domains_static_found(directory_path):
    static_only = dict()
    for path, subdirs, files in os.walk(directory_path):
        for name in files:
            if name.endswith("pixels_found.json"):
                temp_path = os.path.join(path,name)
                # print(temp_path)
                with open(temp_path,'r') as f:
                    temp_domains = json.load(f)
                    for domain in temp_domains:
                        if domain not in static_only.keys():
                            static_only[domain] = temp_domains[domain]

    headless_only = dict()
    for path, subdirs, files in os.walk(directory_path):
        for name in files:
            if name.endswith("state_fbq.json"):
                temp_path = os.path.join(path,name)
                # print(temp_path)
                with open(temp_path,'r') as f:
                    temp_domains = json.load(f)
                    for domain in temp_domains:
                        if domain not in headless_only.keys():
                            headless_only[domain] = temp_domains[domain]
    


    return static_only, headless_only


def EC2_10K_analysis():
    static_only, headless_only = get_domains_static_found('../RESULTS_EC2')

    top10K_ec2 = filter_top_10k_domains_EC2(fbpixel_websites, tranco_domains)
    top10K_dynamic = get_domains_dynamic_found('../../Consecutive_Runs/Dynamic')

    not_in_static = []
    for domain in top10K_dynamic:
        if domain not in top10K_ec2.keys():
            not_in_static.append(domain)


    not_in_total = []
    for domain in not_in_static:
        if domain not in static_only.keys() and domain not in headless_only.keys():
            not_in_total.append(domain)


    static_only, headless_only = get_domains_static_found('../../Consecutive_Runs/Static/')
    not_in_total_ec2 = []
    for domain in not_in_static:
        if domain not in static_only.keys() and domain not in headless_only.keys():
            not_in_total_ec2.append(domain)

    print('-------------------------------------------------------------------------------------------------------------------------------------')
    print(f'\t Domains in 10K not found in Static EC2: {len(not_in_static)} (after validation and cleanup)')
    print(f'\t Domains in 10K not found in Static EC2: {len(not_in_total)} (before validation and cleanup)')
    print(f'\t Domains in 10K not found in Static EC2: {len(not_in_total_ec2)} (excluding domains found locally)')
    print('-------------------------------------------------------------------------------------------------------------------------------------')



def get_implementation_statistics(fbpixel_websites):
    per_case_pixels = dict()
    per_case_pixels_high_level = dict()
    for domain in fbpixel_websites.keys():
        types = fbpixel_websites[domain].get('Pixel_Types', [])
        key = select_primary_pixel_type(types)

        if key not in per_case_pixels:
            per_case_pixels[key] = 1
        else:
            per_case_pixels[key] += 1

        high_level_key = 'Static.GTM' if key.startswith('Static.GTM_') else key

        if high_level_key not in per_case_pixels_high_level:
            per_case_pixels_high_level[high_level_key] = 1
        else:
            per_case_pixels_high_level[high_level_key] += 1        

    total_pixels = sum(per_case_pixels.values())
    sorted_pixels = sorted(per_case_pixels.items(), key=lambda x: x[1], reverse=True)
    print('------------------- HIGH LEVEL ------------------')
    sorted_pixels = sorted(per_case_pixels_high_level.items(), key=lambda x: x[1], reverse=True)
    table_data = [[key, value] for key, value in sorted_pixels]
    headers = ["Implementation type", "Website count"]
    print(tabulate(table_data, headers=headers, tablefmt="grid"))

    


if __name__ == "__main__":

    crawler_outputs_dir = os.path.join(REPO_ROOT, 'CrawlerOutputs')
    tranco_path = resolve_tranco_path()

    fbpixel_websites, batch_buckets = load_crawler_batch_dataset(crawler_outputs_dir)
    tranco_domains = read_tranco_list(tranco_path)


    get_implementation_statistics(fbpixel_websites)


    df_analysis = plot_pixel_adoption_by_rank(batch_buckets, tranco_domains)

