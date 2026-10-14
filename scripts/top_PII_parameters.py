import argparse
import json
import os
from collections import Counter


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, os.pardir))
DEFAULT_RESULTS_DIR = os.path.join(REPO_ROOT, 'PIILeakage', 'temp_results')


def load_json(path):
    if not os.path.exists(path):
        raise FileNotFoundError(f'Missing required file: {path}')
    with open(path, 'r', encoding='utf-8') as handle:
        return json.load(handle)


def merge_parameter_maps(parameter_maps):
    combined = {}

    for per_domain_total_params in parameter_maps:
        for domain, params in per_domain_total_params.items():
            if not isinstance(params, list):
                continue

            domain_params = combined.setdefault(domain, set())
            for param in params:
                cleaned = str(param).strip()
                if cleaned:
                    domain_params.add(cleaned)

    return {domain: sorted(params) for domain, params in combined.items()}


def count_parameters(per_domain_total_params):
    domain_count = len(per_domain_total_params)
    param_domain_counter = Counter()

    for params in per_domain_total_params.values():
        if not isinstance(params, list):
            continue
        unique_params = {str(param).strip() for param in params if str(param).strip()}
        for param in unique_params:
            param_domain_counter[param] += 1

    return domain_count, param_domain_counter


def main():
    parser = argparse.ArgumentParser(
        description='Count how often each parameter appears across result domains.'
    )
    parser.add_argument(
        '--results-dir',
        nargs='+',
        default=[DEFAULT_RESULTS_DIR],
        help='One or more folders containing per_domain_total_params_all.json',
    )
    args = parser.parse_args()

    per_domain_total_params_list = []
    resolved_dirs = []
    per_dir_valid = []

    for results_dir in args.results_dir:
        params_path = os.path.join(results_dir, 'per_domain_total_params_all.json')
        valid_path = os.path.join(results_dir, 'valid_config_ids_all.json')
        per_domain_total_params_list.append(load_json(params_path))
        per_dir_valid.append(load_json(valid_path))
        resolved_dirs.append(os.path.abspath(results_dir))

    # merged mapping of domain -> sorted list of params
    per_domain_total_params = merge_parameter_maps(per_domain_total_params_list)

    domain_count, param_domain_counter = count_parameters(per_domain_total_params)

    # Per-directory PII summary: how many domains with pixels also leak PII
    combined_pixel_domains = set()
    combined_pii_domains = set()
    for results_dir, valid_map, per_total in zip(resolved_dirs, per_dir_valid, per_domain_total_params_list):
        pixel_domains = set(valid_map.keys())
        pii_domains = {d for d in pixel_domains if isinstance(per_total.get(d), list) and any(str(p).strip() for p in per_total.get(d, []))}
        combined_pixel_domains |= pixel_domains
        combined_pii_domains |= pii_domains
        pix = len(pixel_domains)
        pii = len(pii_domains)
        pct = (pii / pix * 100) if pix else 0.0
        print(f"\n{os.path.basename(results_dir)} : {pix} domains have Pixels.") 
        print(f"\n{os.path.basename(results_dir)} : {pii}/{pix} domains leak PII ({pct:.1f}%)")

    print('\nParameter prevalence by domain:')
    print('parameter\tdomains\tpercentage')

    for param, count in sorted(param_domain_counter.items(), key=lambda item: (-item[1], item[0])):
        percentage = (count / domain_count * 100) if domain_count else 0.0
        print(f'{param}\t{count}\t{percentage:.1f}%')


if __name__ == '__main__':
    main()