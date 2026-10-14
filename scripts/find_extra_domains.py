import json
import os
from typing import Dict, Any, Set


def load_json(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        return {}
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def domains_from_run(run_dir: str) -> Set[str]:
    static = load_json(os.path.join(run_dir, 'pixels_found.json'))
    headless = load_json(os.path.join(run_dir, 'state_fbq.json'))
    return set(static.keys()) | set(headless.keys())


def collect_details_for_domains(runs: Dict[str, str], domains: Set[str]) -> Dict[str, Any]:
    details = {}
    for d in sorted(domains):
        details[d] = {}
        for name, rd in runs.items():
            static = load_json(os.path.join(rd, 'pixels_found.json')).get(d)
            head = load_json(os.path.join(rd, 'state_fbq.json')).get(d)
            details[d][name + '_static'] = static
            details[d][name + '_headless'] = head
    return details


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    co = os.path.join(project_root, 'CrawlerOutputs')
    tranco = os.path.join(project_root, 'tranco')

    runs = {
        'old_serial': os.path.join(co, 'crawler_output_10K_old'),
        'old_parallel': os.path.join(co, 'crawler_output_10K_parallel_old'),
        'new_serial': os.path.join(co, 'crawler_output_10K_new'),
        'new_parallel': os.path.join(co, 'crawler_output_10K_parallel_new'),
    }

    # domains present per run
    old_s = domains_from_run(runs['old_serial'])
    old_p = domains_from_run(runs['old_parallel'])
    new_s = domains_from_run(runs['new_serial'])
    new_p = domains_from_run(runs['new_parallel'])

    # symmetric differences between serial and parallel for old/new
    extras_old = old_s.symmetric_difference(old_p)
    extras_new = new_s.symmetric_difference(new_p)

    # combined set of domains to rerun (found by one crawler but not the other in either dataset)
    combined = sorted(list(extras_old | extras_new))

    os.makedirs(tranco, exist_ok=True)
    out_list = os.path.join(tranco, 'rerun_extra_domains.txt')
    out_details = os.path.join(tranco, 'rerun_extra_domains_details.json')

    with open(out_list, 'w', encoding='utf-8') as f:
        for d in combined:
            f.write(d + '\n')

    # produce compact details across runs for diagnosis
    details = collect_details_for_domains(runs, set(combined))
    with open(out_details, 'w', encoding='utf-8') as f:
        json.dump(details, f, indent=2, ensure_ascii=False)

    print(f'Wrote rerun list: {out_list} ({len(combined)} domains)')
    print(f'Wrote details JSON: {out_details}')


if __name__ == '__main__':
    main()
