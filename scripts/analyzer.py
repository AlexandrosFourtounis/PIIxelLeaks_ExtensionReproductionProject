import json
import os
import re
from statistics import mean
import sys
import argparse

class Tee:
    """Write to multiple streams (simple tee for sys.stdout)."""
    def __init__(self, *streams):
        self.streams = streams

    def write(self, data):
        for s in self.streams:
            s.write(data)

    def flush(self):
        for s in self.streams:
            try:
                s.flush()
            except Exception:
                pass

def get_line_count(filepath):
    if not os.path.exists(filepath):
        return 0
    with open(filepath, 'r', encoding='utf-8') as f:
        return sum(1 for _ in f)

def get_json_key_count(filepath):
    if not os.path.exists(filepath):
        return 0
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return len(data) if isinstance(data, dict) else 0
    except json.JSONDecodeError:
        return 0

def get_avg_timing(filepath):
    if not os.path.exists(filepath):
        return 0.0
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if not isinstance(data, dict):
                return 0.0
            times = []
            for value in data.values():
                if not value:
                    continue
                if isinstance(value, list):
                    times.extend(float(item) for item in value if item)
                else:
                    times.append(float(value))
            return mean(times) if times else 0.0
    except (json.JSONDecodeError, ValueError):
        return 0.0

def categorize_pixel_type(pixel_entry):
    """Return the exact state type used in the static phase."""
    if not isinstance(pixel_entry, dict) or not pixel_entry:
        return 'UNKNOWN'
    keys = list(pixel_entry.keys())
    if keys:
        return keys[0]
    return 'UNKNOWN'

def categorize_headless_pixel_type(state_entry):
    """Return the exact state type used in the headless phase."""
    if not isinstance(state_entry, dict) or not state_entry:
        return 'UNKNOWN'
    state_type = state_entry.get('state_type', '')
    if state_type:
        return str(state_type)
    return 'UNKNOWN'

def count_pixels_by_type(static_pixels, headless_pixels, valid_pixels_data):
    """Count pixels and valid pixels by exact state_type without grouping."""
    counts = {
        'Static': {},
        'Headless': {},
        'Valid_Static': {},
        'Valid_Headless': {}
    }
    
    for domain, pixel_entry in (static_pixels or {}).items():
        ptype = categorize_pixel_type(pixel_entry)
        if ptype not in counts['Static']:
            counts['Static'][ptype] = 0
            counts['Valid_Static'][ptype] = 0
        counts['Static'][ptype] += 1
        if domain in valid_pixels_data:
            counts['Valid_Static'][ptype] += 1
            
    for domain, state_entry in (headless_pixels or {}).items():
        ptype = categorize_headless_pixel_type(state_entry)
        if ptype not in counts['Headless']:
            counts['Headless'][ptype] = 0
            counts['Valid_Headless'][ptype] = 0
        counts['Headless'][ptype] += 1
        if domain in valid_pixels_data:
            counts['Valid_Headless'][ptype] += 1
            
    return counts

def analyze_run(run_dir):
    stats = {}
    
    pixels_found_path = os.path.join(run_dir, "pixels_found.json")
    state_fbq_path = os.path.join(run_dir, "state_fbq.json")
    
    valid_config_path = os.path.join(run_dir, "validation", "valid_config_ids_all.json")
    valid_pixels_data = load_json(valid_config_path)
    
    static_pixels = load_json(pixels_found_path)
    headless_pixels = load_json(state_fbq_path)
    
    type_counts = count_pixels_by_type(static_pixels, headless_pixels, valid_pixels_data)
    stats['type_breakdown'] = type_counts
    
    static_count = get_json_key_count(pixels_found_path)
    headless_count = get_json_key_count(state_fbq_path)
    stats["Static Pixels"] = static_count
    stats["Headless Pixels"] = headless_count
    stats["Pixels Found (Domains)"] = static_count + headless_count
    
    found_nothing_path = os.path.join(run_dir, "found_nothing.txt")
    stats["Found Nothing"] = max(0, get_line_count(found_nothing_path) - headless_count)
    
    invalid_html_path = os.path.join(run_dir, "invalid_html_no_response.txt")
    stats["Invalid HTML"] = get_line_count(invalid_html_path)
    
    total_hanged_path = os.path.join(run_dir, "total_hanged.txt")
    stats["Hanged"] = get_line_count(total_hanged_path)
    
    flagged_erroneous_path = os.path.join(run_dir, "flagged_erroneous_html_responses.json")
    stats["Erroneous HTML"] = get_json_key_count(flagged_erroneous_path)
    
    baseline_path = os.path.join(run_dir, "baseline_timings.json")
    stats["Avg Baseline Time (s)"] = get_avg_timing(baseline_path)
    
    headless_path = os.path.join(run_dir, "headless_timings.json")
    stats["Avg Headless Time (s)"] = get_avg_timing(headless_path)
    
    stats["Valid Pixels"] = len(valid_pixels_data)
    
    stats["Total Processed (Sum)"] = (
        stats["Pixels Found (Domains)"] +
        stats["Found Nothing"] +
        stats["Invalid HTML"] +
        stats["Hanged"] +
        stats["Erroneous HTML"]
    )
    
    return stats

def load_json(path: str):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {}

def get_batch_bucket_size(display_name: str):
    m = re.search(r'crawler_output_batch_(\d+)_(\d+)_(\d+)', display_name)
    if not m:
        return None
    try:
        min_rank = int(m.group(2))
        max_rank = int(m.group(3))
        return max_rank - min_rank + 1
    except ValueError:
        return None

def write_md_header(f, title, level=2):
    if f:
        f.write(f"\n{'#' * level} {title}\n\n")

def write_md_table(f, headers, align, rows):
    if not f:
        return
    f.write("| " + " | ".join(headers) + " |\n")
    sep = []
    for a in align:
        if a == 'left':
            sep.append(":---")
        elif a == 'right':
            sep.append("---:")
        elif a == 'center':
            sep.append(":---:")
        else:
            sep.append("---")
    f.write("| " + " | ".join(sep) + " |\n")
    for row in rows:
        f.write("| " + " | ".join(str(x) for x in row) + " |\n")
    f.write("\n")

def main():
    parser = argparse.ArgumentParser(description='Analyze crawler outputs.')
    parser.add_argument('--only', nargs='+', help='Paths to the specific run directories to analyze.', required=True)
    args = parser.parse_args()

    runs_found = []
    for path in args.only:
        full_path = os.path.abspath(path)
        if not os.path.isdir(full_path):
            print(f"Warning: directory not found at {full_path}")
            continue
        display = os.path.basename(full_path)
        runs_found.append((display, full_path))

    if not runs_found:
        print("No valid run directories provided.")
        return

    # Use the first directory to save the analyzer_output.md
    output_md_path = os.path.join(runs_found[0][1], 'analyzer_output.md')
    fout_md = open(output_md_path, 'w', encoding='utf-8')
    orig_stdout = sys.stdout
    
    write_md_header(fout_md, "Crawler Outputs Analysis Summary", level=1)
    
    print("\n" + "="*135)
    print("ALL RUNS ANALYSIS")
    print("="*135 + "\n")
    print(f"{ 'Run Name':<32} | {'Static':>7} | {'Headless':>9} | {'Total':>7} | {'Nothing':>8} | {'Invalid':>8} | {'Hanged':>7} | {'Total Proc':>11} | {'Base(s)':>8} | {'Head(s)':>8}")
    print("-" * 135)

    all_stats = {}
    for display_name, run_dir in runs_found:
        stats = analyze_run(run_dir)
        all_stats[display_name] = stats

    rows_c = []
    for display_name in sorted(all_stats.keys()):
        s = all_stats[display_name]
        print(f"{display_name:<32} | {s.get('Static Pixels',0):7} | {s.get('Headless Pixels',0):9} | {s.get('Pixels Found (Domains)',0):7} | {s.get('Found Nothing',0):8} | {s.get('Invalid HTML',0):8} | {s.get('Hanged',0):7} | {s.get('Total Processed (Sum)',0):11} | {s.get('Avg Baseline Time (s)',0):8.2f} | {s.get('Avg Headless Time (s)',0):8.2f}")
        rows_c.append([
            display_name,
            f"{s.get('Static Pixels',0):,}",
            f"{s.get('Headless Pixels',0):,}",
            f"{s.get('Pixels Found (Domains)',0):,}",
            f"{s.get('Found Nothing',0):,}",
            f"{s.get('Invalid HTML',0):,}",
            f"{s.get('Hanged',0):,}",
            f"{s.get('Total Processed (Sum)',0):,}",
            f"{s.get('Avg Baseline Time (s)',0):.2f}",
            f"{s.get('Avg Headless Time (s)',0):.2f}"
        ])
    
    headers_c = ["Run Name", "Static", "Headless", "Total", "Nothing", "Invalid", "Hanged", "Total Proc", "Base(s)", "Head(s)"]
    align_c = ["left", "right", "right", "right", "right", "right", "right", "right", "right", "right"]
    write_md_header(fout_md, "ALL RUNS ANALYSIS", level=2)
    write_md_table(fout_md, headers_c, align_c, rows_c)
    
    batch_stats = all_stats
    
    print("\n" + "="*110)
    print("STATIC VS HEADLESS DETECTION BREAKDOWN")
    print("="*110 + "\n")
    
    col_headers2 = [
        ("Run Name", 28),
        ("Total Pixels", 14),
        ("Static", 10),
        ("Static %", 10),
        ("Headless", 10),
        ("Headless %", 12),
    ]
    
    header2 = " | ".join([f"{h[0]:>{h[1]}}" for h in col_headers2])
    print(header2)
    print("-" * len(header2))
    
    rows_sh = []
    for display_name in sorted(batch_stats.keys()):
        stats = batch_stats[display_name]
        total = stats['Pixels Found (Domains)']
        static = stats['Static Pixels']
        headless = stats['Headless Pixels']
        static_pct = (static / total * 100) if total > 0 else 0
        headless_pct = (headless / total * 100) if total > 0 else 0
        
        values2 = [
            (display_name, 28),
            (total, 14),
            (static, 10),
            (f"{static_pct:.1f}%", 10),
            (headless, 10),
            (f"{headless_pct:.1f}%", 12),
        ]
        row2 = " | ".join([f"{str(v[0]):>{v[1]}}" for v in values2])
        print(row2)
        
        rows_sh.append([
            display_name,
            f"{total:,}",
            f"{static:,}",
            f"{static_pct:.1f}%",
            f"{headless:,}",
            f"{headless_pct:.1f}%"
        ])
        
    write_md_header(fout_md, "STATIC VS HEADLESS DETECTION BREAKDOWN", level=2)
    write_md_table(fout_md, 
                   ["Run Name", "Total Pixels", "Static", "Static %", "Headless", "Headless %"],
                   ["left", "right", "right", "right", "right", "right"],
                   rows_sh)
    
    print("\n" + "="*100)
    print("PIXEL TYPE BREAKDOWN (Static vs Headless)")
    print("="*100)

    for display_name in sorted(batch_stats.keys()):
        stats = batch_stats[display_name]
        type_breakdown = stats.get('type_breakdown', {})
        
        print(f"\n{display_name}")
        print("-" * 105)
        print(f"{'Detection':<12} | {'State Type':<35} | {'Total Found':>12} | {'Valid Found':>12} | {'Valid %':>10}")
        print("-" * 105)
        
        rows_pt = []
        for detection in ['Static', 'Headless']:
            counts = type_breakdown.get(detection, {})
            valid_counts = type_breakdown.get(f"Valid_{detection}", {})
            total_det = sum(counts.values())
            total_valid_det = sum(valid_counts.values())
            
            for ptype, count in sorted(counts.items(), key=lambda x: x[1], reverse=True):
                valid_count = valid_counts.get(ptype, 0)
                valid_pct = (valid_count / count * 100) if count > 0 else 0
                print(f"{detection:<12} | {ptype:<35} | {count:>12,} | {valid_count:>12,} | {valid_pct:>9.2f}%")
                rows_pt.append([detection, ptype, f"{count:,}", f"{valid_count:,}", f"{valid_pct:.2f}%"])
                
            if total_det > 0:
                total_valid_pct = (total_valid_det / total_det * 100) if total_det > 0 else 0
                print("-" * 105)
                print(f"{detection + ' Total':<12} | {'':<35} | {total_det:>12,} | {total_valid_det:>12,} | {total_valid_pct:>9.2f}%")
                print("-" * 105)
                rows_pt.append([f"**{detection} Total**", "", f"**{total_det:,}**", f"**{total_valid_det:,}**", f"**{total_valid_pct:.2f}%**"])
                
        write_md_header(fout_md, f"PIXEL TYPE BREAKDOWN - {display_name}", level=3)
        write_md_table(fout_md,
                       ["Detection", "State Type", "Total Found", "Valid Found", "Valid %"],
                       ["left", "left", "right", "right", "right"],
                       rows_pt)
    
    print("\n" + "="*120)
    print("DETECTION RATES (% of total domains)")
    print("="*120 + "\n")
    
    col_headers4 = [
        ("Run Name", 28),
        ("Pixels Found", 16),
        ("Valid Pixels", 14),
        ("Detection Rate", 15),
    ]
    
    header4 = " | ".join([f"{h[0]:>{h[1]}}" for h in col_headers4])
    print(header4)
    print("-" * len(header4))
    
    rows_dr = []
    for display_name in sorted(batch_stats.keys()):
        stats = batch_stats[display_name]
        valid_pixels = stats.get('Valid Pixels', 0)
        pixels_found = stats.get('Pixels Found (Domains)', 0)
        total_domains_processed = stats.get('Total Processed (Sum)', 10000)
        bucket_size = get_batch_bucket_size(display_name)
        if bucket_size is not None:
            total_domains_processed = bucket_size
        detection_rate = (valid_pixels / total_domains_processed * 100) if total_domains_processed else 0
        
        values4 = [
            (display_name, 28),
            (pixels_found, 16),
            (valid_pixels, 14),
            (f"{detection_rate:.1f}%", 15),
        ]
        row4 = " | ".join([f"{str(v[0]):>{v[1]}}" for v in values4])
        print(row4)
        
        rows_dr.append([
            display_name,
            f"{pixels_found:,}",
            f"{valid_pixels:,}",
            f"{detection_rate:.1f}%"
        ])
        
    write_md_header(fout_md, "DETECTION RATES (% of total domains)", level=2)
    write_md_table(fout_md,
                   ["Run Name", "Pixels Found", "Valid Pixels", "Detection Rate"],
                   ["left", "right", "right", "right"],
                   rows_dr)
    
    print("\n" + "="*100 + "\n")

    try:
        sys.stdout.flush()
    except Exception:
        pass
    sys.stdout = orig_stdout
    fout_md.close()

if __name__ == '__main__':
    main()
