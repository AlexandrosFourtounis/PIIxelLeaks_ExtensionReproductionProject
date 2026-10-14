import os
import argparse
import pandas as pd


def split_domains(input_file, batch_size, output_dir):
    if not os.path.isabs(input_file):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        candidate = os.path.join(script_dir, input_file)
        if os.path.exists(candidate):
            input_file = candidate

    if input_file.lower().endswith('.csv'):
        df = pd.read_csv(input_file, header=None)
        domains = df.iloc[:, 1].astype(str).tolist()
    else:
        with open(input_file, 'r', encoding='utf-8') as f:
            domains = [line.strip() for line in f if line.strip()]

    os.makedirs(output_dir, exist_ok=True)

    batch_names = []
    for batch_index, start in enumerate(range(0, len(domains), batch_size), start=1):
        batch = domains[start:start + batch_size]
        batch_name = f"batch_{batch_index:02d}_{start}_{start + len(batch) - 1}.txt"
        batch_path = os.path.join(output_dir, batch_name)

        with open(batch_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(batch))

        batch_names.append(batch_name)

    return batch_names


def main():
    parser = argparse.ArgumentParser(description='Split Tranco domains into fixed-size batches.')
    parser.add_argument('--input', default='top100K-new.txt', help='Input domain list file')
    parser.add_argument('--batch-size', type=int, default=10000, help='Number of domains per batch')
    parser.add_argument('--output-dir', default='./batches', help='Directory to write batch files to')
    args = parser.parse_args()

    batch_names = split_domains(args.input, args.batch_size, args.output_dir)
    print('\n'.join(batch_names))


if __name__ == '__main__':
    main()