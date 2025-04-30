import os
import json
import requests
import time
import argparse
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor
from tqdm import tqdm

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


def create_article(article, headers, workflow_state, retry_count=0):
    """
    Create a single knowledge article in ServiceNow with retry logic.
    """
    article_payload = {
        "sys_updated_by": AUTHOR,
        "sys_created_by": EDITOR,
        "workflow_state": workflow_state,
        "text": article.get("innerHtml", "No content provided"),
        "active": "true",
        "topic": "General",
        "short_description": article.get("title", "No title provided"),
        "sys_class_name": "kb_knowledge",
        "valid_to": "2100-01-01",
        "display_attachments": "false",
        "kb_knowledge_base": TABLE_SYS_ID,
        "kb_category": CATEGORY_ID
    }

    try:
        response = requests.post(KB_URL, json=article_payload, headers=headers, timeout=30)
        
        if response.status_code in [200, 201]:
            result = response.json().get("result", {})
            sys_id = result.get("sys_id")
            
            if sys_id:
                article["sys_id"] = sys_id
                return {"success": True, "article": article, "message": f"Created article: {article_payload['short_description']} (sys_id: {sys_id})"}
            else:
                return {"success": False, "article": article, "message": "Article created, but no sys_id returned"}
        
        # Handle rate limiting
        elif response.status_code == 429 and retry_count < MAX_RETRIES:
            time.sleep(RETRY_DELAY * (retry_count + 1))
            return create_article(article, headers, workflow_state, retry_count + 1)
        
        else:
            return {"success": False, "article": article, "message": f"Failed with status {response.status_code}: {response.text}"}
    
    except requests.RequestException as e:
        if retry_count < MAX_RETRIES:
            time.sleep(RETRY_DELAY * (retry_count + 1))
            return create_article(article, headers, workflow_state, retry_count + 1)
        return {"success": False, "article": article, "message": f"Request error: {str(e)}"}


def create_service_now_articles(path, headers, articles, workflow_state):
    """
    Create knowledge articles in ServiceNow using the updated JSON with parallel processing.
    """
    successful_count = 0
    failed_count = 0
    results = []
    
    print(f"Creating {len(articles)} articles in ServiceNow...")
    
    # Process articles in parallel
    with ThreadPoolExecutor(max_workers=BATCH_SIZE) as executor:
        futures = [executor.submit(create_article, article, headers, workflow_state) for article in articles]
        
        # Show progress bar
        for future in tqdm(futures, total=len(articles), desc="Creating articles"):
            result = future.result()
            results.append(result)
            
            if result["success"]:
                successful_count += 1
            else:
                failed_count += 1
    
    # Update the original articles list with sys_ids
    for result in results:
        if result["success"] and "sys_id" in result["article"]:
            # Find the corresponding article in the original list and update it
            for i, article in enumerate(articles):
                if article.get("title") == result["article"].get("title"):
                    articles[i]["sys_id"] = result["article"]["sys_id"]
                    break
    
    # Save updated JSON with sys_id references
    save_json(path, articles)
    
    # Print summary
    print(f"\nSummary:")
    print(f"✅ Successfully created: {successful_count} articles")
    print(f"❌ Failed to create: {failed_count} articles")
    
    # Print failures if any
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
    
    # Get workflow state from command line
    workflow_state = args.workflow_state
    
    # Create articles
    create_service_now_articles(article_data_path, HEADERS, articles, workflow_state)


if __name__ == "__main__":
    main()

