import json
import os

# File paths
file_2025 = 'data/20250603b_ImageFix_exported_pages_to_migrate.json'
file_2024 = 'data/20250416_155718_exported_pages_to_migrate.json'
output_file = 'data/20250603b_ImageFix_exported_pages_to_migrate_corrected.json'

# Load JSON data
def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def main():
    data_2025 = load_json(file_2025)
    data_2024 = load_json(file_2024)

    # Build lookup by id for 2024 data
    id_to_2024 = {item.get('id'): item for item in data_2024 if 'id' in item}

    updated = 0
    for article in data_2025:
        article_id = article.get('id')
        if not article_id:
            print(f"No 'id' in 2025 article: {article.get('sys_id', '[no sys_id]')}")
            continue
        match = id_to_2024.get(article_id)
        if match and 'innerHtml' in match:
            article['innerHtml'] = match['innerHtml']
            updated += 1
        else:
            print(f"No match or no innerHtml for article id: {article_id}")

    # Write output
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data_2025, f, ensure_ascii=False, indent=4)
    print(f"Updated innerHtml for {updated} articles. Output written to {output_file}")

if __name__ == '__main__':
    main()
