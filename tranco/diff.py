import json
from pathlib import Path

BASE_DIR = Path(__file__).parent
OLD_FILE = BASE_DIR / "top10K.txt"
NEW_FILE = BASE_DIR / "top10K-new.txt"
OUTPUT_FILE = BASE_DIR / "comparison_results.json"


def load_domains(filename):
    """
    Load domains into:
    - ordered list
    - dict(domain -> rank)
    """
    # accept either str or Path; resolve relative paths
    p = Path(filename)
    lines = p.read_text(encoding="utf-8").splitlines()

    domains = []
    rank_map = {}

    for idx, line in enumerate(lines, start=1):
        domain = line.strip()

        if not domain:
            continue

        domains.append(domain)
        rank_map[domain] = idx

    return domains, rank_map


def main():
    old_list, old_ranks = load_domains(OLD_FILE)
    new_list, new_ranks = load_domains(NEW_FILE)

    old_set = set(old_ranks.keys())
    new_set = set(new_ranks.keys())

    # =========================================================
    # 1. Exact matches (same rank + same domain)
    # =========================================================
    exact_matches = []

    max_len = min(len(old_list), len(new_list))

    for i in range(max_len):
        if old_list[i] == new_list[i]:
            exact_matches.append({
                "rank": i + 1,
                "domain": old_list[i]
            })

    # =========================================================
    # 2. Domains that moved rank
    # =========================================================
    moved_domains = []

    common_domains = old_set & new_set

    for domain in common_domains:
        old_rank = old_ranks[domain]
        new_rank = new_ranks[domain]

        if old_rank != new_rank:
            diff = new_rank - old_rank

            moved_domains.append({
                "domain": domain,
                "old_rank": old_rank,
                "new_rank": new_rank,
                "rank_difference": diff,
                "direction": "UP" if diff < 0 else "DOWN"
            })

    moved_domains.sort(
        key=lambda x: abs(x["rank_difference"]),
        reverse=True
    )

    # =========================================================
    # 3. Removed domains
    # =========================================================
    removed_domains = sorted(list(old_set - new_set))

    # =========================================================
    # 4. Added domains
    # =========================================================
    added_domains = sorted(list(new_set - old_set))

    # =========================================================
    # Final JSON structure
    # =========================================================
    results = {
        "summary": {
            "old_list_size": len(old_list),
            "new_list_size": len(new_list),
            "exact_rank_matches": len(exact_matches),
            "domains_with_rank_changes": len(moved_domains),
            "removed_domains": len(removed_domains),
            "added_domains": len(added_domains)
        },

        "exact_matches": exact_matches,

        "rank_changes": moved_domains,

        "removed_domains": removed_domains,

        "added_domains": added_domains
    }

    # =========================================================
    # Write JSON
    # =========================================================
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=4, ensure_ascii=False)

    print(f"Results written to: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()