#!/usr/bin/env python3
"""Extract and plot infrastructure data from scam domain JSON files."""

import json
import os
from collections import Counter, defaultdict
from datetime import datetime, timedelta
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np

RESULTS_DIR = os.path.join(os.path.dirname(__file__), 'results')
PLOTS_DIR = os.path.join(os.path.dirname(__file__), 'plots')
os.makedirs(PLOTS_DIR, exist_ok=True)

# ---- Style ----
plt.rcParams.update({
    'figure.dpi': 150,
    'savefig.dpi': 150,
    'font.size': 10,
    'axes.titlesize': 13,
    'axes.labelsize': 11,
    'figure.titlesize': 15,
})


def get_vcard_value(item, field):
    """Safely extract a field from a vcardArray."""
    vcard = item.get('vcardArray')
    if not vcard or not isinstance(vcard, list) or len(vcard) < 2:
        return None
    entries = vcard[1]
    if not isinstance(entries, list):
        return None
    for entry in entries:
        if isinstance(entry, list) and entry[0] == field and len(entry) > 3 and entry[3]:
            return str(entry[3]).strip()
    return None


def parse_date(date_str):
    """Parse the various date formats seen in the data."""
    if not date_str or not isinstance(date_str, str):
        return None
    # Strip timezone suffix
    clean = date_str.split(' GMT')[0] if ' GMT' in date_str else date_str
    for fmt in ['%m/%d/%Y, %I:%M:%S %p', '%Y-%m-%dT%H:%M:%SZ', '%m/%d/%Y']:
        try:
            return datetime.strptime(clean, fmt)
        except ValueError:
            continue
    return None


def extract_all_data():
    """Extract all infrastructure data from JSON files."""
    files = sorted([f for f in os.listdir(RESULTS_DIR) if f.endswith('.json')])

    registrars = Counter()
    nameservers = Counter()
    tlds = Counter()
    reg_dates = []  # list of datetimes
    exp_dates = []  # list of datetimes
    ns_domains = Counter()  # nameserver domain (provider)
    reg_domain_pairs = []  # (domain, registrar) tuples

    for fname in files:
        filepath = os.path.join(RESULTS_DIR, fname)
        try:
            with open(filepath) as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError):
            continue

        domain = data.get('name') or fname.replace('.json', '').replace('_', '.')
        if not domain or not isinstance(domain, str):
            continue

        # TLD (normalize to lowercase)
        if '.' in domain:
            tld = domain.rsplit('.', 1)[-1].lower()
            tlds[tld] += 1

        # Parse dates
        reg_dt = parse_date(data.get('registrationDate', ''))
        exp_dt = parse_date(data.get('expirationDate', ''))
        if reg_dt:
            reg_dates.append(reg_dt)
        if exp_dt:
            exp_dates.append(exp_dt)

        # Process rawData
        for item in data.get('rawData', []):
            if not isinstance(item, dict):
                continue

            roles = item.get('roles') or []
            obj_class = item.get('objectClassName', '')

            # Registrar
            if isinstance(roles, list) and 'registrar' in roles:
                name = get_vcard_value(item, 'fn')
                if name:
                    registrars[name] += 1
                    reg_domain_pairs.append((domain, name))

            # Nameservers
            if obj_class == 'nameserver':
                ns_name = item.get('ldhName', '')
                if ns_name and isinstance(ns_name, str):
                    nameservers[ns_name] += 1
                    # Extract provider domain from nameserver
                    parts = ns_name.lower().split('.')
                    if len(parts) >= 2:
                        ns_domains['.'.join(parts[-2:])] += 1

            # Domain entity (may contain registrar, status)
            if obj_class == 'domain':
                for ent in (item.get('entities') or []):
                    if not isinstance(ent, dict):
                        continue
                    ent_roles = ent.get('roles') or []
                    if isinstance(ent_roles, list) and 'registrar' in ent_roles:
                        rname = get_vcard_value(ent, 'fn')
                        if rname:
                            registrars[rname] += 1
                            reg_domain_pairs.append((domain, rname))

    return {
        'registrars': registrars,
        'nameservers': nameservers,
        'tlds': tlds,
        'reg_dates': reg_dates,
        'exp_dates': exp_dates,
        'ns_domains': ns_domains,
        'reg_domain_pairs': reg_domain_pairs,
        'total_files': len(files),
    }


def shorten_label(label, max_len=35):
    """Shorten long registrar/nameserver labels."""
    if len(label) <= max_len:
        return label
    return label[:max_len-3] + '...'


def plot_tld_distribution(data):
    """Horizontal bar chart: TLD distribution."""
    tlds = data['tlds']
    top = tlds.most_common(20)

    fig, ax = plt.subplots(figsize=(10, 7))
    labels = [f".{t}" for t, _ in top]
    counts = [c for _, c in top]

    colors = plt.cm.viridis(np.linspace(0.15, 0.85, len(labels)))
    bars = ax.barh(range(len(labels)), counts, color=colors, edgecolor='white', linewidth=0.5)
    ax.set_yticks(range(len(labels)))
    ax.set_yticklabels(labels)
    ax.invert_yaxis()
    ax.set_xlabel('Number of Domains')
    ax.set_title(f'Top 20 TLDs Among {data["total_files"]} Scam Domains')

    # Add count labels
    for i, (bar, count) in enumerate(zip(bars, counts)):
        ax.text(bar.get_width() + 2, bar.get_y() + bar.get_height()/2,
                str(count), va='center', fontsize=9)

    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    plt.tight_layout()
    plt.savefig(os.path.join(PLOTS_DIR, 'tld_distribution.pdf'), bbox_inches='tight')
    plt.close()
    print(f"  ✓ TLD distribution saved")


def plot_registrar_distribution(data):
    """Horizontal bar chart: Top registrars."""
    registrars = data['registrars']
    top = registrars.most_common(20)

    fig, ax = plt.subplots(figsize=(11, 7))
    labels = [shorten_label(r) for r, _ in top]
    counts = [c for _, c in top]

    colors = plt.cm.plasma(np.linspace(0.1, 0.9, len(labels)))
    bars = ax.barh(range(len(labels)), counts, color=colors, edgecolor='white', linewidth=0.5)
    ax.set_yticks(range(len(labels)))
    ax.set_yticklabels(labels, fontsize=8)
    ax.invert_yaxis()
    ax.set_xlabel('Number of Domains')
    ax.set_title(f'Top 20 Registrars Used by Scam Domains')

    for bar, count in zip(bars, counts):
        ax.text(bar.get_width() + 1, bar.get_y() + bar.get_height()/2,
                str(count), va='center', fontsize=8)

    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    plt.tight_layout()
    plt.savefig(os.path.join(PLOTS_DIR, 'registrar_distribution.pdf'), bbox_inches='tight')
    plt.close()
    print(f"  ✓ Registrar distribution saved")


def plot_registration_timeline(data):
    """Histogram: Registration dates by month."""
    reg_dates = data['reg_dates']
    if not reg_dates:
        print("  ⚠ No registration dates to plot")
        return

    min_date = min(reg_dates)
    max_date = max(reg_dates)

    fig, ax = plt.subplots(figsize=(14, 6))

    # Filter to reasonable range (2020+), show outliers separately
    dates_filtered = [d for d in reg_dates if d.year >= 2020]
    old_count = len(reg_dates) - len(dates_filtered)

    # Monthly bins
    ax.hist(dates_filtered, bins=60, color='#e74c3c', edgecolor='white', alpha=0.85, linewidth=0.3)
    ax.set_xlabel('Registration Date')
    ax.set_ylabel('Number of Domains')
    ax.set_title(f'Scam Domain Registration Timeline ({len(dates_filtered)} domains, {old_count} pre-2020)')

    # Add a cumulative line
    ax2 = ax.twinx()
    sorted_dates = sorted(dates_filtered)
    ax2.plot(sorted_dates, range(1, len(sorted_dates) + 1), color='#2c3e50', linewidth=2, alpha=0.7)
    ax2.set_ylabel('Cumulative', color='#2c3e50')
    ax2.tick_params(axis='y', labelcolor='#2c3e50')

    ax.spines['top'].set_visible(False)
    plt.tight_layout()
    plt.savefig(os.path.join(PLOTS_DIR, 'registration_timeline.pdf'), bbox_inches='tight')
    plt.close()
    print(f"  ✓ Registration timeline saved")


def plot_registration_by_month(data):
    """Bar chart: Registrations per month (grouped bar)."""
    reg_dates = data['reg_dates']
    if not reg_dates:
        return

    # Count by year-month for 2024-2026
    monthly = Counter()
    for d in reg_dates:
        if d.year >= 2024:
            monthly[f"{d.year}-{d.month:02d}"] += 1

    sorted_months = sorted(monthly.keys())

    fig, ax = plt.subplots(figsize=(14, 6))

    months = sorted_months
    counts = [monthly[m] for m in months]

    colors = ['#e74c3c' if m.startswith('2026') else '#f39c12' if m.startswith('2025') else '#3498db' for m in months]
    bars = ax.bar(range(len(months)), counts, color=colors, edgecolor='white', linewidth=0.3)

    # Label every other month to avoid crowding
    tick_positions = range(0, len(months), max(1, len(months) // 15))
    tick_labels = [months[i] for i in tick_positions]
    ax.set_xticks(list(tick_positions))
    ax.set_xticklabels(tick_labels, rotation=45, ha='right', fontsize=8)

    ax.set_xlabel('Month')
    ax.set_ylabel('Number of Registrations')
    ax.set_title('Scam Domain Registrations by Month (2024–2026)')

    # Legend
    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor='#3498db', label='2024'),
        Patch(facecolor='#f39c12', label='2025'),
        Patch(facecolor='#e74c3c', label='2026'),
    ]
    ax.legend(handles=legend_elements, loc='upper left')

    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    plt.tight_layout()
    plt.savefig(os.path.join(PLOTS_DIR, 'registrations_by_month.pdf'), bbox_inches='tight')
    plt.close()
    print(f"  ✓ Registrations by month saved")


def plot_nameserver_concentration(data):
    """Horizontal bar chart: Top nameserver providers (grouped by domain)."""
    ns_domains = data['ns_domains']
    top = ns_domains.most_common(20)

    fig, ax = plt.subplots(figsize=(11, 7))
    labels = [shorten_label(d, 40) for d, _ in top]
    counts = [c for _, c in top]

    colors = plt.cm.cividis(np.linspace(0.1, 0.9, len(labels)))
    bars = ax.barh(range(len(labels)), counts, color=colors, edgecolor='white', linewidth=0.5)
    ax.set_yticks(range(len(labels)))
    ax.set_yticklabels(labels, fontsize=8)
    ax.invert_yaxis()
    ax.set_xlabel('Number of Domains Using')
    ax.set_title('Top 20 Nameserver Providers')

    for bar, count in zip(bars, counts):
        ax.text(bar.get_width() + 1, bar.get_y() + bar.get_height()/2,
                str(count), va='center', fontsize=8)

    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    plt.tight_layout()
    plt.savefig(os.path.join(PLOTS_DIR, 'nameserver_providers.pdf'), bbox_inches='tight')
    plt.close()
    print(f"  ✓ Nameserver concentration saved")


def plot_registration_age(data):
    """Histogram: How recently were domains registered?"""
    reg_dates = data['reg_dates']
    if not reg_dates:
        return

    # Calculate days since registration
    now = datetime(2026, 6, 23)  # current date
    ages = [(now - d).days for d in reg_dates if d <= now]

    fig, ax = plt.subplots(figsize=(12, 5))

    # Bucket: <30d, 30-90d, 90-180d, 180-365d, 1-2yr, 2-5yr, 5yr+
    bins = [0, 30, 90, 180, 365, 730, 1825, max(ages) + 1]
    labels = ['<30 days', '30-90 days', '90-180 days', '180-365 days',
              '1-2 years', '2-5 years', '5+ years']

    binned = [sum(1 for a in ages if bins[i] <= a < bins[i+1]) for i in range(len(bins)-1)]

    colors = ['#c0392b', '#e74c3c', '#e67e22', '#f39c12', '#27ae60', '#2980b9', '#8e44ad']
    bars = ax.bar(range(len(labels)), binned, color=colors, edgecolor='white', linewidth=0.5)
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=30, ha='right', fontsize=9)
    ax.set_ylabel('Number of Domains')
    ax.set_title(f'Age of Scam Domains (as of June 2026) — {len(ages)} domains')

    for bar, count in zip(bars, binned):
        if count > 0:
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1,
                    str(count), ha='center', fontsize=9)

    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    plt.tight_layout()
    plt.savefig(os.path.join(PLOTS_DIR, 'registration_age.pdf'), bbox_inches='tight')
    plt.close()
    print(f"  ✓ Registration age saved")


def plot_registrar_pie(data):
    """Pie chart: Top 10 registrars + 'Other'."""
    registrars = data['registrars']
    top = registrars.most_common(10)
    other_count = sum(c for _, c in registrars.most_common()[10:])

    labels = [shorten_label(r, 25) for r, _ in top] + ['Other']
    sizes = [c for _, c in top] + [other_count]

    fig, ax = plt.subplots(figsize=(10, 8))
    colors = plt.cm.tab20(np.linspace(0, 1, len(labels)))

    wedges, texts, autotexts = ax.pie(
        sizes, labels=None, autopct='%1.1f%%',
        colors=colors, startangle=140,
        pctdistance=0.8, explode=[0.02] * len(labels)
    )

    for autotext in autotexts:
        autotext.set_fontsize(8)

    ax.legend(wedges, [f"{l} ({c})" for l, c in zip(labels, sizes)],
              title='Registrars', loc='center left', bbox_to_anchor=(1, 0.5), fontsize=8)

    ax.set_title(f'Registrar Market Share ({data["total_files"]} Scam Domains)')
    plt.tight_layout()
    plt.savefig(os.path.join(PLOTS_DIR, 'registrar_pie.pdf'), bbox_inches='tight')
    plt.close()
    print(f"  ✓ Registrar pie chart saved")


def plot_combined_dashboard(data):
    """Single combined figure with multiple subplots."""
    fig = plt.figure(figsize=(16, 12))

    # -- 1. TLD distribution (top 10) --
    ax1 = fig.add_subplot(2, 3, 1)
    tlds = data['tlds']
    top_tld = tlds.most_common(10)
    labels1 = [f".{t}" for t, _ in top_tld]
    counts1 = [c for _, c in top_tld]
    colors1 = plt.cm.viridis(np.linspace(0.2, 0.9, len(labels1)))
    ax1.barh(range(len(labels1)), counts1, color=colors1, edgecolor='white')
    ax1.set_yticks(range(len(labels1)))
    ax1.set_yticklabels(labels1, fontsize=8)
    ax1.invert_yaxis()
    ax1.set_title('Top 10 TLDs', fontsize=11)
    ax1.spines['top'].set_visible(False)
    ax1.spines['right'].set_visible(False)

    # -- 2. Top registrars (top 10) --
    ax2 = fig.add_subplot(2, 3, 2)
    regs = data['registrars']
    top_reg = regs.most_common(10)
    labels2 = [shorten_label(r, 28) for r, _ in top_reg]
    counts2 = [c for _, c in top_reg]
    colors2 = plt.cm.plasma(np.linspace(0.15, 0.9, len(labels2)))
    ax2.barh(range(len(labels2)), counts2, color=colors2, edgecolor='white')
    ax2.set_yticks(range(len(labels2)))
    ax2.set_yticklabels(labels2, fontsize=7)
    ax2.invert_yaxis()
    ax2.set_title('Top 10 Registrars', fontsize=11)
    ax2.spines['top'].set_visible(False)
    ax2.spines['right'].set_visible(False)

    # -- 3. Registration timeline --
    ax3 = fig.add_subplot(2, 3, 3)
    reg_dates = [d for d in data['reg_dates'] if d.year >= 2020]
    if reg_dates:
        ax3.hist(reg_dates, bins=50, color='#e74c3c', edgecolor='white', alpha=0.85, linewidth=0.3)
        ax3.set_title('Registration Timeline (2020–2026)', fontsize=11)
        ax3.set_xlabel('Date')
        ax3.set_ylabel('Count')
    ax3.spines['top'].set_visible(False)
    ax3.spines['right'].set_visible(False)

    # -- 4. Domain age --
    ax4 = fig.add_subplot(2, 3, 4)
    now = datetime(2026, 6, 23)
    ages = [(now - d).days for d in data['reg_dates'] if d <= now]
    bins = [0, 30, 90, 180, 365, 730, 1825, max(ages) + 1 if ages else 3650]
    age_labels = ['<30d', '30-90d', '90-180d', '180d-1y', '1-2y', '2-5y', '5y+']
    binned = [sum(1 for a in ages if bins[i] <= a < bins[i+1]) for i in range(len(bins)-1)]
    age_colors = ['#c0392b', '#e74c3c', '#e67e22', '#f39c12', '#27ae60', '#2980b9', '#8e44ad']
    ax4.bar(age_labels, binned, color=age_colors, edgecolor='white')
    ax4.set_title('Domain Age Distribution', fontsize=11)
    ax4.set_ylabel('Count')
    ax4.tick_params(axis='x', rotation=30, labelsize=8)
    ax4.spines['top'].set_visible(False)
    ax4.spines['right'].set_visible(False)

    # -- 5. Nameserver providers --
    ax5 = fig.add_subplot(2, 3, 5)
    top_ns = data['ns_domains'].most_common(10)
    labels5 = [shorten_label(d, 30) for d, _ in top_ns]
    counts5 = [c for _, c in top_ns]
    colors5 = plt.cm.cividis(np.linspace(0.15, 0.9, len(labels5)))
    ax5.barh(range(len(labels5)), counts5, color=colors5, edgecolor='white')
    ax5.set_yticks(range(len(labels5)))
    ax5.set_yticklabels(labels5, fontsize=7)
    ax5.invert_yaxis()
    ax5.set_title('Top 10 NS Providers', fontsize=11)
    ax5.spines['top'].set_visible(False)
    ax5.spines['right'].set_visible(False)

    # -- 6. Summary stats --
    ax6 = fig.add_subplot(2, 3, 6)
    ax6.axis('off')

    stats_text = f"""Summary Statistics
    ─────────────────────────────
    Total scam domains: {data['total_files']}
    Unique TLDs: {len(data['tlds'])}
    Unique registrars: {len(data['registrars'])}
    Unique nameserver domains: {len(data['ns_domains'])}

    Top TLD: .{data['tlds'].most_common(1)[0][0]} ({data['tlds'].most_common(1)[0][1]})
    Top registrar: {shorten_label(data['registrars'].most_common(1)[0][0], 40)}
      ({data['registrars'].most_common(1)[0][1]} domains)

    Recent registrations (2026): {sum(1 for d in data['reg_dates'] if d.year == 2026)}
    Registered in 2025: {sum(1 for d in data['reg_dates'] if d.year == 2025)}
    Older domains (pre-2025): {sum(1 for d in data['reg_dates'] if d.year < 2025)}

    Median age: {np.median(ages):.0f} days
    """

    ax6.text(0.05, 0.95, stats_text, transform=ax6.transAxes, fontsize=9,
             verticalalignment='top', fontfamily='monospace',
             bbox=dict(boxstyle='round', facecolor='#ecf0f1', alpha=0.8))

    fig.suptitle(f'Scam Domain Infrastructure Analysis ({data["total_files"]} domains)',
                 fontweight='bold', y=1.01)
    plt.tight_layout()
    plt.savefig(os.path.join(PLOTS_DIR, 'infrastructure_dashboard.pdf'), bbox_inches='tight')
    plt.close()
    print(f"  ✓ Combined dashboard saved")


def main():
    print(f"Extracting data from {RESULTS_DIR}...")
    data = extract_all_data()

    print(f"\n  Total files processed: {data['total_files']}")
    print(f"  Unique TLDs: {len(data['tlds'])}")
    print(f"  Unique registrars: {len(data['registrars'])}")
    print(f"  Unique nameserver providers: {len(data['ns_domains'])}")
    print(f"  Domains with registration dates: {len(data['reg_dates'])}")
    print(f"  Domains with expiration dates: {len(data['exp_dates'])}")

    print(f"\nGenerating plots...")
    plot_tld_distribution(data)
    plot_registrar_distribution(data)
    plot_registration_timeline(data)
    plot_registration_by_month(data)
    plot_nameserver_concentration(data)
    plot_registration_age(data)
    plot_registrar_pie(data)
    plot_combined_dashboard(data)

    print(f"\n✓ All plots saved to {PLOTS_DIR}/")

if __name__ == '__main__':
    main()
