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

parameters_overall_dict = {
    "em": 0,
    "fn": 0,
    "ln": 0,
    "ph": 0,
    "ge": 0,
    "zp": 0,
    "ct": 0,
    "st": 0,
    "country": 0,
    "db": 0,
    "external_id": 0,
}


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
        if basename == 'crawler_output_scam_active':
            label = 'Scam Domains'
        elif basename == 'crawler_output_active_domains':
            label = 'Malicious Domains'
        else:
            label = basename

    return start, end, label


def custom_sort_(parameters):
    sorted_params = []
    for param in parameters_overall_dict.keys():
        if param in parameters:
            sorted_params.append(param)
    return sorted_params


def load_rank_bin_combinations(results_dirs):
    loaded_results = []
    for index, results_dir in enumerate(results_dirs):
        params_path = os.path.join(results_dir, 'validation', 'per_domain_total_params_all.json')
        loaded_results.append((parse_results_dir(results_dir, index), os.path.abspath(results_dir), load_json(params_path)))

    loaded_results.sort(key=lambda item: (item[0][0], item[0][1], item[1]))

    per_rank_bins_combinations = {}
    bin_labels = []

    for bin_id, ((_, _, bin_label), _, per_domain_total_params) in enumerate(loaded_results):
        bin_labels.append(bin_label)
        bin_combinations = {}

        for params in per_domain_total_params.values():
            if not isinstance(params, list):
                continue

            filtered_parameters = [str(item).strip() for item in params if str(item).strip()]
            if filtered_parameters:
                combo_key = str(custom_sort_(filtered_parameters))
            else:
                combo_key = 'None'

            bin_combinations[combo_key] = bin_combinations.get(combo_key, 0) + 1

        per_rank_bins_combinations[bin_id] = bin_combinations

    return per_rank_bins_combinations, bin_labels


def visualize_rank_bin_combinations(per_rank_bins_combinations, bin_labels, top_n=4):
    all_combinations = {}
    for combinations in per_rank_bins_combinations.values():
        for combo, count in combinations.items():
            all_combinations[combo] = all_combinations.get(combo, 0) + count

    top_10_combos = sorted(all_combinations.items(), key=lambda item: item[1], reverse=True)[:11]

    for combo in top_10_combos:
        print(f'Combination: {combo[0]} | Count: {combo[1]}')

    top_combinations = sorted(all_combinations.items(), key=lambda item: item[1], reverse=True)[:top_n]
    top_combo_names = [combo for combo, _ in top_combinations]

    plot_data = []
    for bin_id, combinations in per_rank_bins_combinations.items():
        bin_data = {'Bin': bin_labels[bin_id], 'BinID': bin_id}
        bin_total = sum(combinations.values())

        for combo_name in top_combo_names:
            if combo_name in combinations and bin_total:
                percentage = (combinations[combo_name] / bin_total) * 100
                bin_data[combo_name] = percentage
            else:
                bin_data[combo_name] = 0

        other_percentage = 100 - sum(bin_data.get(combo, 0) for combo in top_combo_names)
        bin_data['Other'] = other_percentage if other_percentage > 0 else 0
        plot_data.append(bin_data)

    plot_data.sort(key=lambda item: item['BinID'])
    df = pd.DataFrame(plot_data)

    n_bins = len(bin_labels)
    if n_bins == 1:
        plt.figure(figsize=(12, 12))
        bar_width = 0.3
    else:
        plt.figure(figsize=(25, 20))
        bar_width = 0.6

    bottom = np.zeros(len(plot_data))

    colors = ['#8B2500', '#FF6B45', '#FFDA8A', '#FFFCDD']
    if top_n < 4:
        colors = colors[:top_n] + ['#5A5A5A']
    else:
        colors = colors + ['#5A5A5A']

    legend_labels = {}
    for combo in top_combo_names:
        short_label = combo
        if combo == str(list(parameters_overall_dict.keys())):
            short_label = 'All Parameters'
        elif combo == 'None':
            short_label = 'No Parameters'
        legend_labels[combo] = short_label

    for i, combo in enumerate(top_combo_names):
        values = df[combo].values
        plt.bar(df['Bin'], values, bottom=bottom, width=bar_width, label=legend_labels[combo], color=colors[i])
        bottom += values

    plt.bar(df['Bin'], df['Other'].values, bottom=bottom, width=bar_width, label='Other', color=colors[-1])

    bottom = np.zeros(len(plot_data))
    for combo in top_combo_names + ['Other']:
        values = df[combo].values
        for i, value in enumerate(values):
            if value > 0:
                plt.text(i, bottom[i] + value / 2, f'{value:.1f}%', ha='center', va='center', color='black', fontweight='bold', fontsize=24)
        bottom += values

    plt.xticks(fontsize=35 if n_bins == 1 else 45, rotation=0 if n_bins == 1 else 60)
    plt.yticks(fontsize=35 if n_bins == 1 else 45)
    plt.xlabel('Dataset' if n_bins == 1 else 'Website Rank Range', fontsize=40 if n_bins == 1 else 50, fontweight='bold')
    plt.ylabel('Percentage (%)', fontsize=40 if n_bins == 1 else 50, fontweight='bold')

    legend = plt.legend(title='Parameter Combinations', fontsize=20 if n_bins == 1 else 24, loc='upper left' if n_bins == 1 else 'best')
    plt.setp(legend.get_title(), fontsize=20 if n_bins == 1 else 24)
    plt.grid(axis='y', linestyle='--', alpha=0.3)

    plt.tight_layout()
    return plt.gcf()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Plot parameter combination distributions by batch.')
    parser.add_argument(
        '--results-dir',
        nargs='+',
        default=DEFAULT_RESULTS_DIRS,
        help='One or more folders containing per_domain_total_params_all.json',
    )
    parser.add_argument(
        '--top-n',
        type=int,
        default=4,
        help='Number of most common combinations to highlight',
    )
    parser.add_argument(
        '--output-file',
        type=str,
        default='parameter_combo_distribution.pdf',
        help='Output PDF filename',
    )
    args = parser.parse_args()

    plots_dir = os.path.join(REPO_ROOT, 'plots')
    os.makedirs(plots_dir, exist_ok=True)

    print(f"Processing {len(args.results_dir)} batches...")
    per_rank_bins_combinations, bin_labels = load_rank_bin_combinations(args.results_dir)
    fig = visualize_rank_bin_combinations(per_rank_bins_combinations, bin_labels, top_n=args.top_n)
    plt.savefig(os.path.join(plots_dir, args.output_file), dpi=300, bbox_inches='tight')
    plt.close(fig)
