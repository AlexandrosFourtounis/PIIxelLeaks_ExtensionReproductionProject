import json

def extract_top_10(file_path, category_name):
    print(f"=== Top 10 {category_name} Domains by Pixel Count ===")
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        # Rank by number of unique pixel IDs
        ranked = sorted(data.items(), key=lambda x: len(x[1]) if x[1] else 0, reverse=True)
        
        # Print top 10
        print(f"{'Rank':<5} | {'Domain':<30} | {'Pixel Count'}")
        print("-" * 55)
        for i, (domain, pixels) in enumerate(ranked[:10], 1):
            print(f"{i:<5} | {domain:<30} | {len(pixels)}")
    except FileNotFoundError:
        print(f"Error: Could not find file for {category_name} at {file_path}")
    print("\n")

def main():
    datasets = [
        ('Benign (Top 50K)', 'CrawlerOutputs/crawler_output_top50K_new/validation/valid_config_ids_all.json'),
        ('Scam', 'CrawlerOutputs/crawler_output_scam/validation/valid_config_ids_all.json'),
        ('Malicious', 'CrawlerOutputs/crawler_output_malicious/validation/valid_config_ids_all.json')
    ]
    
    for category, path in datasets:
        extract_top_10(path, category)

if __name__ == "__main__":
    main()
