import json
import os
import argparse
from collections import defaultdict, Counter


def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def analyze(results_dir):
    def find_file(root, name):
        # Check direct path
        p = os.path.join(root, name)
        if os.path.exists(p):
            return p
        # Check validation subfolder
        p = os.path.join(root, 'validation', name)
        if os.path.exists(p):
            return p
        # Fallback: walk directory to find the first match
        for dirpath, _, files in os.walk(root):
            if name in files:
                return os.path.join(dirpath, name)
        return None

    valid_path = find_file(results_dir, 'valid_config_ids_all.json')
    all_params_path = find_file(results_dir, 'per_domain_all_params_all.json')
    total_params_path = find_file(results_dir, 'per_domain_total_params_all.json')

    missing = [n for n, p in (('valid', valid_path), ('all_params', all_params_path), ('total_params', total_params_path)) if p is None]
    if missing:
        raise FileNotFoundError(f'Missing expected files ({", ".join(missing)}) under {results_dir} (tried direct, validation/, and recursive search)')

    valid = load_json(valid_path)
    all_params = load_json(all_params_path)
    total_params = load_json(total_params_path)

    # Map pixel_id -> set(domains)
    pixel_domains = defaultdict(set)
    pixel_configs = defaultdict(list)
    for domain, configs in valid.items():
        for pid in configs.keys():
            pixel_domains[pid].add(domain)
            pixel_configs[pid].append((domain, configs[pid]))

    total_pixel_mentions = sum(len(configs) for configs in valid.values())
    unique_pixels = set(pixel_domains.keys())

    reused = {pid: domains for pid, domains in pixel_domains.items() if len(domains) > 1}

    # Gather params per pixel (across domains/configs)
    pixel_params = defaultdict(Counter)
    for domain, configs in all_params.items():
        for pid, params in configs.items():
            for p in params:
                pixel_params[pid][p] += 1

    # Output a concise report
    print('ANALYSIS REPORT')
    print('==============')
    print(f'Results folder: {results_dir}')
    print(f'Domains processed: {len(valid)}')
    print(f'Total pixel mentions (domain-config pairs): {total_pixel_mentions}')
    print(f'Unique pixel IDs found: {len(unique_pixels)}')
    print(f'Pixel IDs used on multiple domains: {len(reused)}')
    if reused:
        print('\nTop reused pixel IDs (up to 20):')
        # sort by number of domains
        items = sorted(reused.items(), key=lambda kv: -len(kv[1]))[:20]
        for pid, domains in items:
            print(f'  {pid}  -> {len(domains)} domains')
        # Show sample of pixels with their domains and params
        print('\nSample details for reused pixels (up to 20):')
        for pid, domains in items:
            print('\n---')
            print(f'Pixel ID: {pid}')
            print(f'Domains ({len(domains)}): {", ".join(sorted(domains))}')
            params = pixel_params.get(pid, {})
            if params:
                print('Top params and counts:')
                for p, c in params.most_common(10):
                    print(f'  {p}: {c}')
            else:
                print('No params captured for this pixel in per_domain_all_params_all.json')
    else:
        print('\nNo reused pixel IDs found, so there are no sample reused-pixel details to show.')

    # Also list pixels that appear only once (unique to a domain)
    unique_only_count = sum(1 for pid, domains in pixel_domains.items() if len(domains) == 1)
    print(f'\nPixels unique to a single domain: {unique_only_count}')

    # Group pixels by identical domain sets so repeated domain coverage is emitted once.
    grouped_by_domains = defaultdict(list)
    for pid, domains in pixel_domains.items():
        grouped_by_domains[tuple(sorted(domains))].append(pid)

    grouped_pixels = []
    for domains, pixel_ids in sorted(grouped_by_domains.items(), key=lambda item: (-len(item[0]), tuple(item[0]))):
        grouped_pixels.append({
            'pixel_id': [int(pid) if pid.isdigit() else pid for pid in sorted(pixel_ids, key=lambda value: int(value) if value.isdigit() else value)],
            'domains': list(domains),
            'domain_count': len(domains)
        })
    print('\n===========================================================')
    print('INFRASTRUCTURE OVERLAP FOR DOMAIN CLUSTERS')
    print('===========================================================\n')
    
    import socket
    import concurrent.futures
    import whois
    from ipwhois import IPWhois
    
    # Set a short global timeout so WHOIS/DNS lookups don't hang the script
    socket.setdefaulttimeout(3.0)

    def get_ips(domain):
        try:
            _, _, ipaddrlist = socket.gethostbyname_ex(domain)
            return set(ipaddrlist)
        except Exception:
            return set()

    def get_asn(ip):
        try:
            obj = IPWhois(ip)
            res = obj.lookup_rdap(depth=1)
            return res.get('asn_description') or res.get('asn')
        except Exception:
            return None

    def get_registrar(domain):
        try:
            w = whois.whois(domain)
            return w.registrar
        except Exception:
            return None

    multi_domain_clusters = [c for c in grouped_pixels if c['domain_count'] > 1]
    shared_ip_count = 0
    shared_asn_count = 0
    shared_reg_count = 0
        
    # We will gather all domains across all multi_domain_clusters and resolve them concurrently
    all_domains_to_resolve = set()
    for c in multi_domain_clusters:
        all_domains_to_resolve.update(c['domains'])

    total_domains = len(all_domains_to_resolve)
    skip_registrar = total_domains > 500  # Skip slow WHOIS for large datasets
    
    if skip_registrar:
        print(f"Resolving IPs for {total_domains} unique domains across {len(multi_domain_clusters)} clusters concurrently (skipping WHOIS registrar for large dataset)...")
    else:
        print(f"Resolving infrastructure for {total_domains} unique domains across {len(multi_domain_clusters)} clusters concurrently...")
    
    global_domain_ips = {}
    global_domain_regs = {}
    
    def resolve_domain_info(d):
        ips = get_ips(d)
        reg = None if skip_registrar else get_registrar(d)
        return d, ips, reg

    resolved_count = [0]  # Use list for closure mutability
    with concurrent.futures.ThreadPoolExecutor(max_workers=30) as executor:
        future_to_domain = {executor.submit(resolve_domain_info, d): d for d in all_domains_to_resolve}
        for future in concurrent.futures.as_completed(future_to_domain):
            d = future_to_domain[future]
            try:
                domain, ips, reg = future.result()
                global_domain_ips[domain] = ips if ips else set()
                global_domain_regs[domain] = reg
            except Exception:
                global_domain_ips[d] = set()
                global_domain_regs[d] = None
            resolved_count[0] += 1
            if resolved_count[0] % 200 == 0:
                print(f"  ...resolved {resolved_count[0]}/{total_domains} domains")

    print(f"  Done resolving {resolved_count[0]}/{total_domains} domains.")

    # Now get ASNs for all discovered IPs concurrently
    all_discovered_ips = set()
    for ips in global_domain_ips.values():
        if ips:
            all_discovered_ips.update(ips)
            
    print(f"Resolving ASNs for {len(all_discovered_ips)} unique IP addresses concurrently...")
    global_ip_asns = {}
    
    resolved_ip_count = [0]
    total_ips = len(all_discovered_ips)
    with concurrent.futures.ThreadPoolExecutor(max_workers=30) as executor:
        future_to_ip = {executor.submit(get_asn, ip): ip for ip in all_discovered_ips}
        for future in concurrent.futures.as_completed(future_to_ip):
            ip = future_to_ip[future]
            try:
                global_ip_asns[ip] = future.result()
            except Exception:
                global_ip_asns[ip] = None
            resolved_ip_count[0] += 1
            if resolved_ip_count[0] % 200 == 0:
                print(f"  ...resolved {resolved_ip_count[0]}/{total_ips} IPs")

    print(f"  Done resolving {resolved_ip_count[0]}/{total_ips} IPs.")

    for c in multi_domain_clusters:
        doms = c['domains']
        
        domain_ips = {d: global_domain_ips.get(d, set()) for d in doms if global_domain_ips.get(d)}
        domain_regs = {d: global_domain_regs.get(d) for d in doms if global_domain_regs.get(d)}
                
        shared_ips = set()
        if len(domain_ips) > 1:
            shared_ips = set.intersection(*domain_ips.values())
            
        shared_regs = set()
        if len(domain_regs) > 1:
            regs_set = [set([r.lower() if isinstance(r, str) else str(r).lower()]) for r in domain_regs.values() if r]
            if regs_set:
                shared_regs = set.intersection(*regs_set)

        shared_asns = set()
        domain_asns = {}
        for d, ips in domain_ips.items():
            dasns = {global_ip_asns[ip] for ip in ips if ip in global_ip_asns and global_ip_asns[ip]}
            if dasns:
                domain_asns[d] = dasns

        if len(domain_asns) > 1:
            shared_asns = set.intersection(*domain_asns.values())
            
        c['shared_infrastructure'] = []
        if shared_ips:
            c['shared_infrastructure'].append(f"IPs: {', '.join(shared_ips)}")
            shared_ip_count += 1
        if shared_asns:
            c['shared_infrastructure'].append(f"ASN: {', '.join(shared_asns)}")
            shared_asn_count += 1
        if shared_regs:
            c['shared_infrastructure'].append(f"Registrar: {', '.join(shared_regs)}")
            shared_reg_count += 1
            
        if c['shared_infrastructure']:
            print(f"Cluster with pixels {c['pixel_id']} ({len(doms)} domains):")
            print(f"  Domains: {', '.join(doms)}")
            print(f"  Shared Infra: {', '.join(c['shared_infrastructure'])}\n")
            
    if multi_domain_clusters:
        print(f"\nSummary of Infrastructure overlap:")
        print(f"Total multi-domain clusters: {len(multi_domain_clusters)}")
        print(f"  -> {shared_ip_count} clusters share exact IP addresses")
        print(f"  -> {shared_asn_count} clusters share an ASN")
        print(f"  -> {shared_reg_count} clusters share a Registrar")
    else:
        print("No multi-domain clusters found.")

    # Create a small summary JSON next to the results
    summary = {
        'domains_processed': len(valid),
        'total_pixel_mentions': total_pixel_mentions,
        'unique_pixel_count': len(unique_pixels),
        'reused_pixel_count': len(reused),
        'unique_pixel_count_no_reuse': unique_only_count,
        'grouped_by_domains': grouped_pixels,
    }

    out_path = os.path.join(results_dir, 'pixel_usage_summary.json')
    with open(out_path, 'w', encoding='utf-8') as fh:
        json.dump(summary, fh, indent=2)



def main():
    parser = argparse.ArgumentParser(description='Analyze pixel usage across domains in malicious_results')
    parser.add_argument('results_dir', nargs='?', default=os.path.join('PIILeakage', 'malicious_results'))
    args = parser.parse_args()
    analyze(args.results_dir)


if __name__ == '__main__':
    main()
