import argparse
import json
import os
import re

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, os.pardir))
DEFAULT_RESULTS_DIRS = [
    os.path.join(REPO_ROOT, 'CrawlerOutputs', 'crawler_output_active_domains'),

]


def load_json(path):
    if not os.path.exists(path):
        raise FileNotFoundError(f'Missing required file: {path}')
    with open(path, 'r', encoding='utf-8') as handle:
        return json.load(handle)


def format_bin_label(start, end):
    def format_bound(value):
        return '0' if value == 0 else f'{value // 1000}K'

    return f'{format_bound(start)}-{format_bound(end)}'


def parse_results_dir(results_dir, fallback_index):
    basename = os.path.basename(os.path.normpath(results_dir))
    if basename.endswith('_old'):
        basename_stripped = basename[:-4]
    else:
        basename_stripped = basename
    match = re.search(r'_(\d+)_(\d+)$', basename_stripped)
    if match:
        start = int(match.group(1))
        end = int(match.group(2)) + 1
        label = format_bin_label(start, end)
    else:
        start = fallback_index * 10000
        end = start + 10000
        label = basename

    return start, end, label


def load_batch_parameter_maps(results_dirs):
    loaded_results = []
    for index, results_dir in enumerate(results_dirs):
        params_path = os.path.join(results_dir, 'validation', 'per_domain_total_params_all.json')
        start, end, bin_label = parse_results_dir(results_dir, index)
        loaded_results.append((start, end, bin_label, os.path.abspath(results_dir), load_json(params_path)))

    loaded_results.sort(key=lambda item: (item[0], item[1], item[3]))
    return loaded_results


def plot_parameter_adoption_bars(batch_results, output_filename):
    all_params = [
        'em', 'fn', 'ln', 'ph', 'ge', 'zp',
        'ct', 'st', 'country', 'db', 'external_id',
    ]

    bin_labels = [bin_label for _, _, bin_label, _, _ in batch_results]
    param_counts = {param: {label: 0 for label in bin_labels} for param in all_params}
    bin_domain_totals = {label: 0 for label in bin_labels}

    for _, _, bin_label, _, params_dict in batch_results:
        for params in params_dict.values():
            if not isinstance(params, list):
                continue

            unique_params = {str(param).strip() for param in params if str(param).strip()}
            if not unique_params:
                continue

            bin_domain_totals[bin_label] += 1
            for param in unique_params:
                if param in all_params:
                    param_counts[param][bin_label] += 1

    df = pd.DataFrame({param: [param_counts[param][bin] for bin in bin_labels] for param in all_params})
    df.index = bin_labels

    fig, ax = plt.subplots(figsize=(24, 15))

    n_bins = len(bin_labels)
    n_params = len(all_params)
    width = 0.7 / n_params

    param_totals = {param: df[param].sum() for param in all_params}
    sorted_params = sorted(all_params, key=lambda item: param_totals[item], reverse=True)
    percentage_denominator = total_domains_with_params if total_domains_with_params else 0

    blues = plt.cm.Blues(np.linspace(0.9, 0.3, len(sorted_params)))

    for i, param in enumerate(sorted_params):
        if param_totals[param] > 0:
            x = np.arange(n_bins) + (i - n_params / 2 + 0.5) * width
            percentage = (param_totals[param] / percentage_denominator * 100) if percentage_denominator else 0.0
            ax.bar(x, df[param], width, label=f'{param} ({percentage:.2f} %)', color=blues[i])

    ax.set_xticks(np.arange(n_bins))
    ax.set_xticklabels(bin_labels, rotation=45)
    ax.set_xlabel('Website Rank Range', fontsize=50, fontweight='bold')
    ax.set_ylabel('Number of Websites', fontsize=50, fontweight='bold')
    ax.legend(fontsize=30, loc='lower center', bbox_to_anchor=(0.5, 0.05), ncol=3, framealpha=0.8, facecolor='white', edgecolor='lightgray')

    plt.xticks(fontsize=45)
    plt.yticks(fontsize=45)
    plt.tight_layout(rect=[0, 0.1, 1, 1])
    plt.grid(axis='y', linestyle='--', alpha=0.3)

    print('Parameter prevalence by batch:')
    for bin_label in bin_labels:
        domain_total = bin_domain_totals[bin_label]
        print(f'\n{bin_label} (domains with parameters: {domain_total})')
        print('parameter\tdomains\tpercentage')

        sorted_bin_params = sorted(
            ((param, param_counts[param][bin_label]) for param in all_params if param_counts[param][bin_label] > 0),
            key=lambda item: (-item[1], item[0]),
        )
        for param, count in sorted_bin_params:
            percentage = (count / domain_total * 100) if domain_total else 0.0
            print(f'{param}\t{count}\t{percentage:.1f}%')

    plt.savefig(output_filename, dpi=300, bbox_inches='tight')
    return df


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Plot parameter adoption by batch rank range.')
    parser.add_argument(
        '--results-dir',
        nargs='+',
        default=DEFAULT_RESULTS_DIRS,
        help='One or more folders containing per_domain_total_params_all.json',
    )
    parser.add_argument(
        '--output-file',
        type=str,
        default='parameter_adoption_per_rank.pdf',
        help='Output PDF filename',
    )
    args = parser.parse_args()

    plots_dir = os.path.join(REPO_ROOT, 'plots')
    os.makedirs(plots_dir, exist_ok=True)

    print(f"Processing {len(args.results_dir)} batches...")
    batch_results = load_batch_parameter_maps(args.results_dir)
    total_domains_with_params = 0
    for _, _, _, _, params_dict in batch_results:
        for params in params_dict.values():
            if not isinstance(params, list):
                continue
            unique_params = {str(param).strip() for param in params if str(param).strip()}
            if unique_params:
                total_domains_with_params += 1
    print(f'Total websites tracking at least one parameter: {total_domains_with_params}')
    df_params = plot_parameter_adoption_bars(batch_results, os.path.join(plots_dir, args.output_file))