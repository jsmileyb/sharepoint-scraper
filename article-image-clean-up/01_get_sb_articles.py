import os
import json
import requests
import time
import argparse
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor
from tqdm import tqdm
from datetime import datetime

# Set up argument parser
parser = argparse.ArgumentParser(description='Create knowledge articles in ServiceNow.')
parser.add_argument('--input-file', help='Path to the article data JSON file')
parser.add_argument('--batch-size', type=int, default=10, help='Number of concurrent requests (default: 10)')
parser.add_argument('--workflow-state', default='draft', help='Workflow state for the articles (default: draft)')
args = parser.parse_args()

# Load environment variables from .env file
load_dotenv()

# ServiceNow environment variables
AUTHOR = os.getenv("SERVICE_NOW_AUTHOR")
EDITOR = os.getenv("SERVICE_NOW_EDITOR")
SERVICE_NOW_BASE = os.getenv("SERVICE_NOW_BASE")
SERVICE_NOW_KB = os.getenv("SERVICE_NOW_KB")
TABLE_SYS_ID = os.getenv("TABLE_SYS_ID")
CATEGORY_ID = os.getenv("CATEGORY_ID")
TOKEN = os.getenv("API_KEY")
HEADERS = {
    "x-sn-apikey": TOKEN
}
KB_URL = f"{SERVICE_NOW_BASE}/{SERVICE_NOW_KB}/kb_knowledge"

# Constants
MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds
BATCH_SIZE = args.batch_size  # Number of concurrent requests
WORKFLOW_STATE = "draft"  # Default workflow state, can be overridden by command line argument


def get_articles_by_author(author, headers, workflow_state, max_retries=3, output_path=None):
    """
    Fetch all knowledge articles authored by the specified author and workflow state.
    Optionally export the result to a JSON file if output_path is provided.
    Only selected fields are exported.
    """
    params = {
        "sys_created_by": author,
        "workflow_state": workflow_state
    }
    retries = 0
    while retries < max_retries:
        try:
            response = requests.get(KB_URL, params=params, headers=headers, timeout=30)
            if response.status_code == 200:
                data = response.json().get("result", [])
                print(f"Fetched {len(data)} articles authored by {author}.")
                # Only keep selected fields
                fields = [
                    "sys_updated_on", "number", "sys_updated_by", "sys_created_on", "workflow_state",
                    "sys_created_by", "topic", "display_number", "short_description", "sys_class_name",
                    "article_id", "sys_id", "display_attachments", "kb_category"
                ]
                filtered_data = [
                    {k: v for k, v in article.items() if k in fields}
                    for article in data
                ]
                for article in filtered_data:
                    print(json.dumps(article, indent=2))
                if output_path:
                    os.makedirs(os.path.dirname(output_path), exist_ok=True)
                    with open(output_path, "w", encoding="utf-8") as f:
                        json.dump(filtered_data, f, indent=2, ensure_ascii=False)
                    print(f"Exported articles to {output_path}")
                return filtered_data
            elif response.status_code == 429:
                print("Rate limited. Retrying...")
                time.sleep(RETRY_DELAY * (retries + 1))
                retries += 1
            else:
                print(f"Failed with status {response.status_code}: {response.text}")
                return None
        except requests.RequestException as e:
            print(f"Request error: {e}. Retrying...")
            time.sleep(RETRY_DELAY * (retries + 1))
            retries += 1
    print("Max retries exceeded. Could not fetch articles.")
    return None


def main():
    """Main function to run the script."""
    # Generate prefix yyyyMMdd_hhss_
    prefix = datetime.now().strftime("%Y%m%d_%H%M_")
    output_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "data",
        "article_image_update",
        f"{prefix}articles_by_author.json"
    )
    get_articles_by_author(AUTHOR, HEADERS, WORKFLOW_STATE, output_path=output_path)


if __name__ == "__main__":
    main()

