import os
import json
import requests
import time
import argparse
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor
from tqdm import tqdm
import logging

# Set up argument parser
parser = argparse.ArgumentParser(description='Create knowledge articles in ServiceNow.')
parser.add_argument('--input-file', help='Path to the article data JSON file')
parser.add_argument('--batch-size', type=int, default=10, help='Number of concurrent requests (default: 10)')
parser.add_argument('--workflow-state', default='draft', help='Workflow state for the articles (default: draft)')
parser.add_argument('--dry-run', action='store_true', help='Print what would be updated without making API calls')
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

# Set up logging
logging.basicConfig(
    filename='update_articles.log',
    level=logging.INFO,
    format='%(asctime)s %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Constants
MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds
BATCH_SIZE = args.batch_size  # Number of concurrent requests


def load_json(file_path):
    """
    Load JSON data from a file.
    """
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            return json.load(file)
    except FileNotFoundError:
        print(f"Error: File not found - {file_path}")
        return None
    except json.JSONDecodeError:
        print(f"Error: Invalid JSON format in file - {file_path}")
        return None


def save_json(file_path, data):
    """
    Save JSON data to a file.
    """
    try:
        with open(file_path, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=4, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"Error saving JSON file: {e}")
        return False


def create_article(article, headers, workflow_state, retry_count=0, dry_run=False):
    """
    Create a single knowledge article in ServiceNow with retry logic.
    If dry_run is True, print the payload and skip the API call.
    Logs errors and warnings.
    """
    required_fields = ["sys_id", "innerHtml"]
    missing_article_fields = [field for field in required_fields if field not in article or not article.get(field)]
    if missing_article_fields:
        msg = f"Missing required fields in article: {', '.join(missing_article_fields)}. Skipping update."
        print(f"❌ {msg}")
        logging.error(msg + f" Article: {article.get('title', 'No title')}")
        return {"success": False, "article": article, "message": msg}

    article_payload = {
        "workflow_state": workflow_state,
        "text": article.get("innerHtml", "No content provided"),
        "active": "true",
        "display_attachments": "false"
    }
    patch_url = f"{KB_URL}/{article.get('sys_id', '')}"

    if dry_run:
        print(f"[DRY RUN] Would PATCH {patch_url} with payload:")
        print(json.dumps(article_payload, indent=2, ensure_ascii=False))
        return {"success": True, "article": article, "message": "Dry run: no API call made."}

    try:
        response = requests.patch(patch_url, json=article_payload, headers=headers, timeout=30)
        if response.status_code in [200, 201]:
            result = response.json().get("result", {})
            sys_id = result.get("sys_id")
            expected_fields = ["sys_id", "number", "workflow_state", "short_description"]
            missing_fields = [field for field in expected_fields if field not in result]
            if sys_id and not missing_fields:
                article["article_update_success"] = True
                return {"success": True, "article": article, "message": f"Updated article: {result.get('short_description', 'No short_description')} (sys_id: {sys_id})"}
            elif sys_id:
                msg = f"Article updated but missing fields: {', '.join(missing_fields)} (sys_id: {sys_id})"
                article["article_update_success"] = False
                print(f"⚠️ {msg}")
                logging.warning(msg + f" Article: {article.get('title', 'No title')}")
                return {"success": False, "article": article, "message": msg}
            else:
                msg = "Article updated, but no sys_id returned"
                article["article_update_success"] = False
                print(f"❌ {msg}")
                logging.error(msg + f" Article: {article.get('title', 'No title')}")
                return {"success": False, "article": article, "message": msg}
        elif response.status_code == 429 and retry_count < MAX_RETRIES:
            msg = f"Rate limited (429). Retrying... (Attempt {retry_count+1})"
            print(f"⚠️ {msg}")
            logging.warning(msg + f" Article: {article.get('title', 'No title')}")
            time.sleep(RETRY_DELAY * (retry_count + 1))
            return create_article(article, headers, workflow_state, retry_count + 1)
        else:
            msg = f"Failed with status {response.status_code}: {response.text}"
            print(f"❌ {msg}")
            logging.error(msg + f" Article: {article.get('title', 'No title')}")
            return {"success": False, "article": article, "message": msg}
    except requests.RequestException as e:
        msg = f"Request error: {str(e)}"
        print(f"❌ {msg}")
        logging.error(msg + f" Article: {article.get('title', 'No title')}")
        if retry_count < MAX_RETRIES:
            time.sleep(RETRY_DELAY * (retry_count + 1))
            return create_article(article, headers, workflow_state, retry_count + 1)
        return {"success": False, "article": article, "message": msg}


def create_service_now_articles(path, headers, articles, workflow_state, dry_run=False):
    """
    Create knowledge articles in ServiceNow using the updated JSON with parallel processing.
    If dry_run is True, only print what would be updated.
    Validate that sys_id is present and non-empty before making requests.
    """
    # Filter out articles missing sys_id
    valid_articles = [a for a in articles if a.get("sys_id")]
    skipped_articles = [a for a in articles if not a.get("sys_id")]

    if skipped_articles:
        print(f"⚠️ Skipping {len(skipped_articles)} articles missing sys_id.")
        for a in skipped_articles:
            logging.error(f"Missing sys_id. Skipped article: {a.get('title', 'No title')}")

    successful_count = 0
    failed_count = 0
    results = []

    print(f"{'[DRY RUN] ' if dry_run else ''}Creating {len(valid_articles)} articles in ServiceNow...")

    # Process valid articles in parallel
    with ThreadPoolExecutor(max_workers=BATCH_SIZE) as executor:
        futures = [executor.submit(create_article, article, headers, workflow_state, 0, dry_run) for article in valid_articles]
        for future in tqdm(futures, total=len(valid_articles), desc="Creating articles"):
            result = future.result()
            results.append(result)
            if result["success"]:
                successful_count += 1
            else:
                failed_count += 1

    # Only save if not dry run
    if not dry_run:
        for result in results:
            if result["success"] and "sys_id" in result["article"]:
                for i, article in enumerate(articles):
                    if article.get("title") == result["article"].get("title"):
                        articles[i]["sys_id"] = result["article"]["sys_id"]
                        break
        save_json(path, articles)

    # Print summary
    print(f"\nSummary:")
    print(f"✅ {'Would create' if dry_run else 'Successfully created'}: {successful_count} articles")
    print(f"❌ {'Would fail to create' if dry_run else 'Failed to create'}: {failed_count} articles")
    if skipped_articles:
        print(f"⚠️ Skipped {len(skipped_articles)} articles missing sys_id.")

    if failed_count > 0:
        print("\nFailed articles:")
        for result in results:
            if not result["success"]:
                print(f"- {result['article'].get('title', 'Unknown title')}: {result['message']}")

    return successful_count, failed_count


def main():
    """Main function to run the script."""
    # Get the path to the article data file from command line or prompt
    if args.input_file:
        article_data_path = args.input_file
    else:
        article_data_path = input("Enter the path to the article data JSON file: ")
    
    articles = load_json(article_data_path)
    if not articles:
        print("❌ Failed to load JSON articles.")
        return
    
    # Check if articles is a list
    if not isinstance(articles, list):
        print("❌ The JSON file does not contain a list of articles.")
        return
    
    # Check if there are any articles to process
    if len(articles) == 0:
        print("⚠️ The JSON file contains an empty list of articles.")
        return
    
    # Confirm with user
    print(f"Found {len(articles)} articles to create.")
    confirm = input("Do you want to proceed? (y/n): ")
    
    if confirm.lower() != 'y':
        print("Operation cancelled.")
        return
    
    # Get workflow state from command line or use default "draft"
    workflow_state = args.workflow_state if args.workflow_state else "draft"
    
    # Create articles
    dry_run = args.dry_run
    create_service_now_articles(article_data_path, HEADERS, articles, workflow_state, dry_run=dry_run)


if __name__ == "__main__":
    main()

