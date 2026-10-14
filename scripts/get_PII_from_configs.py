import argparse
import os
import re
import json
import sys
from urllib.parse import urlparse
import requests


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, os.pardir))
PII_LEAKAGE_DIR = os.path.join(REPO_ROOT, 'PIILeakage')
DEFAULT_OLD_CRAWLER_DIR = os.path.join(REPO_ROOT, 'CrawlerOutputs', 'crawler_output_10K_old')
DEFAULT_NEW_CRAWLER_DIR = os.path.join(REPO_ROOT, 'CrawlerOutputs', 'crawler_output_10K_new')
DEFAULT_RESULTS_ROOT = os.path.join(PII_LEAKAGE_DIR, 'temp_results')
DEFAULT_SINGLE_RESULTS_DIR = os.path.join(PII_LEAKAGE_DIR, 'temp_results_single')

config_pattern = r'config\.set\("(\d+)", "automaticMatching", ({.*?})\)'
per_user_param = {
    "em": 0,
    "ph": 0,
    "ge": 0,
    "db": 0,
    "ct": 0,
    "st": 0,
    "zp": 0,
    "country": 0,
    "fn": 0,
    "ln": 0,
    "external_id": 0
}

per_user_param_websites = {
    "em": [],
    "ph": [],
    "ge": [],
    "db": [],
    "ct": [],
    "st": [],
    "zp": [],
    "country": [],
    "fn": [],
    "ln": [],
    "external_id": []
}


def extract_numeric_ids(value, current_path=None):
    if current_path is None:
        current_path = []

    extracted = {}

    if isinstance(value, dict):
        for key, child_value in value.items():
            if key in {"found_flag", "state_type"}:
                continue

            child_path = current_path + [str(key)]
            if isinstance(child_value, str) and child_value.isdigit():
                extracted[child_value] = ".".join(child_path)
            else:
                extracted.update(extract_numeric_ids(child_value, child_path))

    elif isinstance(value, list):
        for child_value in value:
            if isinstance(child_value, str) and child_value.isdigit():
                extracted[child_value] = ".".join(current_path)
            else:
                extracted.update(extract_numeric_ids(child_value, current_path))

    elif isinstance(value, str) and value.isdigit():
        extracted[value] = ".".join(current_path)

    return extracted


def load_per_domain_configs(crawler_root):
    combined_configs = {}
    crawler_paths = []

    if os.path.isdir(crawler_root):
        for root, _, files in os.walk(crawler_root):
            for filename in files:
                if filename in {'pixels_found.json', 'state_fbq.json', 'state_fbw.json'}:
                    crawler_paths.append(os.path.join(root, filename))

    for candidate_path in crawler_paths:
        if not os.path.exists(candidate_path):
            continue

        with open(candidate_path, 'r') as f:
            raw_data = json.load(f)

        for domain, domain_data in raw_data.items():
            extracted_ids = extract_numeric_ids(domain_data)
            if not extracted_ids:
                continue

            if domain not in combined_configs:
                combined_configs[domain] = {}

            for pixel_id, source in extracted_ids.items():
                if isinstance(domain_data, dict) and (domain_data.get("state_type") == "CAPI_OR_NETWORK" or str(domain_data.get("state_type")).startswith("DEEP_EXTRACTION")):
                    source = "CAPI_OR_NETWORK"
                elif isinstance(domain_data, dict) and domain_data.get("state_type"):
                    source = domain_data.get("state_type")

                if pixel_id not in combined_configs[domain]:
                    combined_configs[domain][pixel_id] = source

    if combined_configs:
        print('Loaded config IDs from crawler files:')
        for candidate_path in sorted(crawler_paths):
            if os.path.exists(candidate_path):
                print(f'  - {candidate_path}')
        return combined_configs

    raise FileNotFoundError(
        f'Could not locate any pixels_found.json, state_fbq.json, or state_fbw.json files under {crawler_root}'
    )


def extract_hostname(url):
    parsed_url = urlparse(url)
    return parsed_url.netloc

def check_fb_pixel(unique_id,domain):
    base_url = f'https://connect.facebook.net/signals/config/{unique_id}?domain={domain}'
    
    try:
        response = requests.get(base_url, timeout=3, allow_redirects=True)
        
        if response.status_code != 200:
            print(f'Invalid status code for {unique_id}')
            return 0, []
        
        pattern = rf'fbq\.registerPlugin\("{unique_id}", \{{__fbEventsPlugin: 1, plugin: function\(fbq, instance, config\) \{{ /\* empty plugin \*/instance\.configLoaded\("{unique_id}"\); \}}\}}\);?\s*$'
        
        if re.search(pattern, response.text.strip()):
            print(f"Invalid ID: {unique_id} ({domain})")
            return 0, []
        else:
            found = re.findall(config_pattern, response.text)
            if found:
                for match in found:
                    if match[1]:
                        parameters = match[1].split('[')[1].replace(']}','').replace('"','').split(",")
                        return 1, parameters
            else:
                return 1, []
            
            return 0,[]
            
    except requests.exceptions.RequestException as e:
        print(f"Error checking {unique_id}: {str(e)}")
        return 0, []



def validate_config_ids(crawler_root, output_dir, output_suffix='all'):
    per_domain_configs = load_per_domain_configs(crawler_root)
    per_domain_valid_configs = dict()
    per_domain_all_pixel_params = dict()
    per_domain_total_params = dict()

    counter = 0
    configs_to_explore = list(per_domain_configs.keys())


    for domain in configs_to_explore:
        print('=========================================================================================')
        print(f'Validating configs for {domain} ({counter}/{len(configs_to_explore)})')
        valid_config_ids = dict()
        for config_id in per_domain_configs[domain].keys():
            print(f'Checking config {config_id}')
            is_valid,parameters = check_fb_pixel(config_id,domain)
            if is_valid == 0:
                print(f'Invalid {config_id} for domain: {domain}')
            else:
                valid_config_ids[config_id] = per_domain_configs[domain][config_id]
                if len(parameters) > 0:
                    if domain not in per_domain_all_pixel_params.keys():
                        per_domain_all_pixel_params[domain] = dict()

                    if config_id not in per_domain_all_pixel_params[domain].keys():              
                        per_domain_all_pixel_params[domain][config_id] = parameters


                    if domain not in per_domain_total_params.keys():
                        per_domain_total_params[domain] = list()

                    for param in parameters:
                        if param not in per_domain_total_params[domain]:
                            per_domain_total_params[domain].append(param)

                    print(f'{config_id}  ---> {str(parameters)}')
        counter += 1
        print('=========================================================================================')


        per_domain_valid_configs[domain] = valid_config_ids

    counter = 0
    print('Second round of validation: ....')
    domains_inval = []
    for domain in configs_to_explore:
        if domain not in per_domain_valid_configs.keys():
            domains_inval.append(domain)
        else:
            if len(per_domain_configs[domain]) == 0:
                domains_inval.append(domain)

    for domain in domains_inval:
        print('=========================================================================================')
        print(f'Validating configs for {domain} ({counter}/{len(domains_inval)})')
        valid_config_ids = dict()
        for config_id in per_domain_configs[domain].keys():
            print(f'Checking config {config_id}')
            is_valid,parameters = check_fb_pixel(config_id,domain)
            if is_valid == 0:
                print(f'Invalid {config_id} for domain: {domain}')
            else:
                valid_config_ids[config_id] = per_domain_configs[domain][config_id]
                if len(parameters) > 0:
                    if domain not in per_domain_all_pixel_params.keys():
                        per_domain_all_pixel_params[domain] = dict()

                    if config_id not in per_domain_all_pixel_params[domain].keys():              
                        per_domain_all_pixel_params[domain][config_id] = parameters


                    if domain not in per_domain_total_params.keys():
                        per_domain_total_params[domain] = list()

                    for param in parameters:
                        if param not in per_domain_total_params[domain]:
                            per_domain_total_params[domain].append(param)

                    print(f'{config_id}  ---> {str(parameters)}')

        print('=========================================================================================')
        counter += 1


    os.makedirs(output_dir, exist_ok=True)

    with open(os.path.join(output_dir, f'valid_config_ids_{output_suffix}.json'), 'w') as f:
        json.dump(per_domain_valid_configs, f, indent=4)
        f.close()

    with open(os.path.join(output_dir, f'per_domain_all_params_{output_suffix}.json'), 'w') as f: # per config params for every config belonging to a domain
        json.dump(per_domain_all_pixel_params, f, indent=4)
        f.close()

    with open(os.path.join(output_dir, f'per_domain_total_params_{output_suffix}.json'), 'w') as f: # all params as unique set been tracked in this domain regardless of Pixel ID
        json.dump(per_domain_total_params, f, indent=4)
        f.close()
        
    return per_domain_valid_configs


def run_validation_set(crawler_root, results_dir):
    run_name = os.path.basename(os.path.normpath(crawler_root))
    # Force results to be saved in a `validation` subfolder inside the crawler run
    results_dir = os.path.join(crawler_root, 'validation')
    print('=========================================================================================')
    print(f'Running validation for {run_name}')
    print(f'Input crawler root: {crawler_root}')
    print(f'Output directory: {results_dir}')
    print('=========================================================================================')
    validate_config_ids(crawler_root, results_dir)


def run_single_validation(crawler_root, results_dir):
    run_name = os.path.basename(os.path.normpath(crawler_root))
    # Save single-run results in a `validation` subfolder inside the crawler run
    results_dir = os.path.join(crawler_root, 'validation')
    print('=========================================================================================')
    print(f'Running validation for {run_name}')
    print(f'Input crawler root: {crawler_root}')
    print(f'Output directory: {results_dir}')
    print('=========================================================================================')
    validate_config_ids(crawler_root, results_dir, output_suffix='all')

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Validate Meta Pixel config IDs from crawler outputs.'
    )
    parser.add_argument(
        '--compare',
        action='store_true',
        help='Compare two crawler folders and write results_old and results_new.',
    )
    parser.add_argument(
        '--old-dir',
        default=DEFAULT_OLD_CRAWLER_DIR,
        help='Crawler output folder for the old run (compare mode only)',
    )
    parser.add_argument(
        '--new-dir',
        default=DEFAULT_NEW_CRAWLER_DIR,
        help='Crawler output folder for the new run (compare mode only)',
    )
    parser.add_argument(
        '--results-root',
        default=DEFAULT_RESULTS_ROOT,
        help='Root folder where results_old and results_new will be created (compare mode only)',
    )
    parser.add_argument(
        '--crawler-dir',
        help='Crawler output folder to process in single-folder mode',
    )
    parser.add_argument(
        '--results-dir',
        default=DEFAULT_SINGLE_RESULTS_DIR,
        help='Output folder for single-folder mode',
    )
    args = parser.parse_args()

    if args.compare:
        run_validation_set(args.old_dir, os.path.join(args.results_root, 'results_old'))
        run_validation_set(args.new_dir, os.path.join(args.results_root, 'results_new'))
    else:
        if not args.crawler_dir:
            parser.error('single-folder mode requires --crawler-dir')
        run_single_validation(args.crawler_dir, args.results_dir)