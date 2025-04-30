import os
import json
import requests
import argparse
from dotenv import load_dotenv

# Set up argument parser
parser = argparse.ArgumentParser(description='Upload images for articles and update JSON with the returned sys_id.')
parser.add_argument('--input-file', help='Path to the article data JSON file')
args = parser.parse_args()

# Load environment variables from .env file
load_dotenv()

# ServiceNow environment variables
SERVICE_NOW_BASE = os.getenv("SERVICE_NOW_BASE")
SERVICE_NOW_ATTACHMENT_API = "api/now/attachment/upload"
TOKEN = os.getenv("API_KEY")
TABLE_SYS_ID = os.getenv("TABLE_SYS_ID")
# TABLE_SYS_ID = os.getenv("TABLE_SYS_ID_DEV")
HEADERS = {
    "x-sn-apikey": TOKEN
}

ATTACHMENT_URL = f"{SERVICE_NOW_BASE}/{SERVICE_NOW_ATTACHMENT_API}"


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


def upload_images(headers, articles):
    """
    Upload images for articles and update JSON with the returned sys_id.
    """
    # Add a counter to track progress
    total_images = sum(len(article.get("images", [])) for article in articles)
    processed = 0
    errors = 0

    for article in articles:
        if "images" in article and article["images"]:  # Check if images array exists and is not empty
            for image in article["images"]:
                processed += 1
                if "download_path" in image and image["download_path"]:
                    image_path = image["download_path"]

                    if "sys_id" in image and image["sys_id"]:
                        print(f"[{processed}/{total_images}] ⏭️ Skipping already uploaded image: {image_path} (sys_id: {image['sys_id']})")
                        continue  # Skip if image already has a sys_id

                    if not os.path.exists(image_path):
                        print(f"[{processed}/{total_images}] ⚠️ Image file not found: {image_path}")
                        image["upload_error"] = "File not found"  # Add error indicator
                        errors += 1
                        # Save immediately after recording the error
                        save_json(article_data_path, articles)
                        continue  # Skip missing files

                    # Use multipart form-data with separate file and data parameters
                    try:
                        print(f"[{processed}/{total_images}] 🔄 Uploading image: {image_path}")
                        with open(image_path, 'rb') as file_obj:
                            files = {'file': (os.path.basename(image_path), file_obj, 'application/octet-stream')}
                            data = {
                                'table_name': 'kb_knowledge',
                                'table_sys_id': TABLE_SYS_ID  # Temp value, articles not created yet
                            }
                            
                            response = requests.post(ATTACHMENT_URL, headers=headers, files=files, data=data)

                        if response.status_code in [200, 201]:
                            result = response.json().get("result", {})
                            image_sys_id = result.get("sys_id")

                            if image_sys_id:
                                image["sys_id"] = image_sys_id  # Store image reference
                                # Remove any previous error if it exists
                                if "upload_error" in image:
                                    del image["upload_error"]
                                print(f"[{processed}/{total_images}] ✅ Image uploaded successfully: {image_path} (sys_id: {image_sys_id})")
                            else:
                                image["upload_error"] = "No sys_id returned"
                                errors += 1
                                print(f"[{processed}/{total_images}] ⚠️ Image uploaded, but no sys_id returned.")
                        else:
                            error_message = f"HTTP {response.status_code}: {response.text}"
                            image["upload_error"] = error_message
                            errors += 1
                            print(f"[{processed}/{total_images}] ❌ Failed to upload image: {image_path}")
                            print(f"Error: {error_message}")
                    except Exception as e:
                        error_message = str(e)
                        image["upload_error"] = error_message
                        errors += 1
                        print(f"[{processed}/{total_images}] ❌ Exception while uploading image: {image_path}")
                        print(f"Error: {error_message}")
                    
                    # Save after each attempt, whether successful or not
                    save_json(article_data_path, articles)
                else:
                    # Handle case where download_path is missing
                    image["upload_error"] = "Missing download_path"
                    errors += 1
                    print(f"[{processed}/{total_images}] ⚠️ Image missing download_path")
                    save_json(article_data_path, articles)

    print(f"\nUpload summary: {processed} images processed, {errors} errors")
    return articles


if __name__ == "__main__":
    # Get the path to the article data file from command line or prompt
    if args.input_file:
        article_data_path = args.input_file
    else:
        article_data_path = input("Enter the path to the article data JSON file: ")
    
    articles = load_json(article_data_path)
    
    if articles:
        updated_articles = upload_images(HEADERS, articles)  # Upload images and get updated articles
        # Save the updated JSON after all uploads
        save_json(article_data_path, updated_articles)
        print(f"✅ Updated JSON saved to {article_data_path}")
    else:
        print("❌ Failed to load JSON articles.")

