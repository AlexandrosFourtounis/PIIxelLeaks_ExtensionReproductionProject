import json
import matplotlib.pyplot as plt
import numpy as np

def get_counts(file_path, exclude=None):
    counts = []
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        for domain, pixels in data.items():
            if exclude and exclude in domain:
                continue
            if pixels:
                counts.append(len(pixels))
    return counts

def find_ecdf_y(x_sorted, y_ecdf, value):
    """Find the ECDF y-value for a given x value."""
    idx = np.searchsorted(x_sorted, value, side='right') - 1
    if idx < 0:
        return 0.0
    return y_ecdf[idx]

def plot_ecdf(benign_path, other_path, other_label, out_file):
    benign_counts = get_counts(benign_path, exclude='ticketmaster')
    other_counts = get_counts(other_path)
    
    fig, ax = plt.subplots(figsize=(10, 6))
    
    # Plot lines (no steps, no interpolation — just connecting data points)
    x_benign = np.sort(benign_counts)
    y_benign = np.arange(1, len(x_benign) + 1) / len(x_benign)
    ax.plot(x_benign, y_benign, label=f'Benign (Top 50K) [n={len(benign_counts)}]', color='#2196F3', linewidth=2)
    
    x_other = np.sort(other_counts)
    y_other = np.arange(1, len(x_other) + 1) / len(x_other)
    ax.plot(x_other, y_other, label=f'{other_label} [n={len(other_counts)}]', color='#E53935', linewidth=2)
    
    # Stats
    benign_med = int(np.median(benign_counts))
    benign_max = int(max(benign_counts))
    other_med = int(np.median(other_counts))
    other_max = int(max(other_counts))
    
    benign_med_y = find_ecdf_y(x_benign, y_benign, benign_med)
    other_med_y = find_ecdf_y(x_other, y_other, other_med)

    # --- Benign Median arrow: point DOWN-RIGHT, text sits below-right of the point ---
    ax.annotate(f'Benign Median: {benign_med}',
                xy=(benign_med, benign_med_y),
                xytext=(60, -50),
                textcoords='offset points',
                fontsize=9, fontweight='bold', color='#1565C0',
                arrowprops=dict(arrowstyle='->', color='#1565C0', lw=1.5))

    # --- Benign Max arrow: point LEFT, text sits to the left of the point ---
    ax.annotate(f'Benign Max: {benign_max}',
                xy=(benign_max, 1.0),
                xytext=(-120, -40),
                textcoords='offset points',
                fontsize=9, fontweight='bold', color='#1565C0',
                arrowprops=dict(arrowstyle='->', color='#1565C0', lw=1.5))

    # --- Other Median arrow: point UP-RIGHT, text sits above-right ---
    ax.annotate(f'{other_label} Median: {other_med}',
                xy=(other_med, other_med_y),
                xytext=(60, 40),
                textcoords='offset points',
                fontsize=9, fontweight='bold', color='#B71C1C',
                arrowprops=dict(arrowstyle='->', color='#B71C1C', lw=1.5))

    # --- Other Max arrow: point DOWN-LEFT, text sits below-left ---
    ax.annotate(f'{other_label} Max: {other_max}',
                xy=(other_max, 1.0),
                xytext=(-100, -50),
                textcoords='offset points',
                fontsize=9, fontweight='bold', color='#B71C1C',
                arrowprops=dict(arrowstyle='->', color='#B71C1C', lw=1.5))

    ax.set_title(f'ECDF: Number of Meta Pixels per Domain (Benign vs {other_label})', fontsize=13)
    ax.set_xlabel('Number of Unique Pixel IDs (Log Scale)', fontsize=11)
    ax.set_ylabel('ECDF', fontsize=11)
    ax.grid(True, linestyle='--', alpha=0.5)
    ax.legend(fontsize=10)
    ax.set_xscale('log')
    
    plt.tight_layout()
    plt.savefig(out_file)
    plt.close()
    print(f'Saved {out_file}')

# Generate both plots
plot_ecdf('CrawlerOutputs/crawler_output_top50K_new/validation/valid_config_ids_all.json',
          'CrawlerOutputs/crawler_output_scam/validation/valid_config_ids_all.json',
          'Scam', 'plots/ecdf_pixels_per_domain_scam.pdf')
          
plot_ecdf('CrawlerOutputs/crawler_output_top50K_new/validation/valid_config_ids_all.json',
          'CrawlerOutputs/crawler_output_malicious/validation/valid_config_ids_all.json',
          'Malicious', 'plots/ecdf_pixels_per_domain_malicious.pdf')
