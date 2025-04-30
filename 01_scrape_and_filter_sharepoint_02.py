import os
import json
import requests
import msal
from dotenv import load_dotenv
from datetime import datetime, timedelta
from urllib.parse import unquote
from time import sleep
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
import concurrent.futures
from functools import lru_cache
import sys
from typing import List
import urllib.parse
from bs4 import BeautifulSoup
import re

load_dotenv()

# Environment Variables
tenant_id = os.getenv("TENANT_ID")
client_secret = os.getenv("CLIENT_SECRET")
client_id = os.getenv("CLIENT_ID")
site_id = os.getenv("MS_SP_ID")

# Global variables for token caching
_token_cache = {
    'access_token': None,
    'expires_at': None
}

def create_session():
    """Create a requests session with retry logic"""
    session = requests.Session()
    retry_strategy = Retry(
        total=5,
        backoff_factor=1.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST"]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=10, pool_maxsize=20)
    session.mount("https://", adapter)
    return session

def acquire_token():
    """Get access token with caching"""
    global _token_cache
    
    if (_token_cache['access_token'] and _token_cache['expires_at'] and 
        datetime.now() < _token_cache['expires_at']):
        return _token_cache['access_token']

    authority_url = f'https://login.microsoftonline.com/{tenant_id}'
    app = msal.ConfidentialClientApplication(
        client_id, 
        authority=authority_url, 
        client_credential=client_secret
    )
    token = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])

    if "access_token" not in token:
        raise Exception(f"Authentication failed: {token.get('error_description', 'No details available')}")

    _token_cache['access_token'] = token['access_token']
    _token_cache['expires_at'] = datetime.now() + timedelta(seconds=token['expires_in'] - 300)

    return token["access_token"]

# Create a session to be reused
session = create_session()

def make_graph_request(url, headers=None, method='GET', params=None, json_data=None):
    """Helper function for making Graph API requests with rate limiting"""
    if headers is None:
        headers = {'Authorization': f'Bearer {acquire_token()}'}
    
    try:
        response = session.request(method, url, headers=headers, params=params, json=json_data)
        
        if response.status_code == 429:
            retry_after = int(response.headers.get('Retry-After', 30))
            print(f"Rate limited. Waiting for {retry_after} seconds...")
            sleep(retry_after)
            return make_graph_request(url, headers, method, params, json_data)
        
        response.raise_for_status()
        return response
    except requests.exceptions.RequestException as e:
        print(f"Request error: {str(e)}")
        if isinstance(e, (requests.exceptions.ConnectionError, requests.exceptions.Timeout)):
            print("Connection error or timeout. Retrying in 5 seconds...")
            sleep(5)
            return make_graph_request(url, headers, method, params, json_data)
        raise

def extract_url_segment(url: str) -> str:
    """Extract the last segment of a URL path."""
    try:
        parsed_url = urllib.parse.urlparse(url)
        path = parsed_url.path
        segments = [s for s in path.split('/') if s]
        if segments:
            return segments[-1].lower().strip()
        return ""
    except Exception:
        return ""

def read_url_segments_from_file(file_path: str) -> List[str]:
    """Read URL segments from a text file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            segments = [line.strip() for line in f if line.strip()]
        return segments
    except Exception as e:
        print(f"Error reading URL segments file: {e}")
        sys.exit(1)

def get_pages(limit=None, batch_size=10):
    """Retrieve SharePoint Site Pages with batching"""
    all_pages = []
    url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/lists/Site Pages/items"
    base_query = f"?$expand=fields&$top={batch_size}"
    next_link = url + base_query
    
    try:
        while next_link:
            response = make_graph_request(next_link)
            data = response.json()
            
            batch = data.get('value', [])
            all_pages.extend(batch)
            
            next_link = data.get('@odata.nextLink')
            
            if limit and len(all_pages) >= limit:
                all_pages = all_pages[:limit]
                break
                
            print(f"Retrieved {len(all_pages)} pages so far...")
                
        return all_pages
    except Exception as e:
        print(f"Error retrieving pages: {str(e)}")
        return all_pages

def extract_html_with_beautifulsoup(url):
    """Extract page content using BeautifulSoup as fallback"""
    try:
        # Use the existing session with auth token
        headers = {'Authorization': f'Bearer {acquire_token()}'}
        response = session.get(url, headers=headers)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Look for the Rich Text Editor div
        content_div = soup.find('div', attrs={'data-sp-feature-tag': 'Rich Text Editor'})
        if content_div:
            return content_div.decode_contents()  # Get inner HTML
        return ""
    except Exception as e:
        print(f"Error extracting HTML with BeautifulSoup: {str(e)}")
        return ""

def process_page_data(page, include_images=True):
    """Process page data with BeautifulSoup fallback"""
    try:
        etag = page['eTag']
        page_id = etag.split(',')[0].strip('"')

        core_json = {
            "description": page['fields'].get("Description", ""),
            "id": page_id,
            "webUrl": page.get("webUrl", ""),
            "title": page['fields'].get("Title", ""),
            "innerHtml": "",
            "processing_error": None,
            "processing_method": "graph"  # Track which method was used
        }

        if include_images:
            core_json["images"] = []

        page_url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/pages/{page_id}/microsoft.graph.sitePage?$expand=canvasLayout"
        try:
            page_data = make_graph_request(page_url).json()
            
            # Flag to track if we found images through webPartType
            found_images_via_webpart = False

            if "canvasLayout" in page_data:
                for section in page_data["canvasLayout"].get("horizontalSections", []):
                    for column in section.get("columns", []):
                        for webpart in column.get("webparts", []):
                            if "innerHtml" in webpart:
                                core_json["innerHtml"] = webpart["innerHtml"]
                            
                            if include_images and webpart.get("webPartType") == "d1d91016-032f-456d-98a4-721247c305e8":
                                found_images_via_webpart = True
                                image_link = webpart["data"]["serverProcessedContent"]["imageSources"][0].get("value", "")
                                filename = os.path.basename(image_link)
                                
                                image_data = {
                                    "id": webpart["id"],
                                    "imgHeight": webpart["data"]["properties"].get("imgHeight"),
                                    "imgWidth": webpart["data"]["properties"].get("imgWidth"),
                                    "imageLink": image_link,
                                    "pageId": page_id,
                                    "download_path": f"images/{page_id}/{filename}"
                                }
                                core_json["images"].append(image_data)
            
            # If we have HTML content and didn't find images via webPartType, try to extract from HTML
            if include_images and not found_images_via_webpart and core_json["innerHtml"]:
                # Extract images from innerHtml using regex
                image_divs = re.findall(r'<div class="imagePlugin"[^>]*?data-imageurl="[^"]*?"[^>]*?data-uniqueid="[^"]*?"[^>]*?></div>', 
                                       core_json["innerHtml"])
                
                for div in image_divs:
                    # Extract attributes using regex
                    image_url_match = re.search(r'data-imageurl="([^"]*?)"', div)
                    image_id_match = re.search(r'data-uniqueid="([^"]*?)"', div)
                    height_match = re.search(r'data-height="([^"]*?)"', div)
                    width_match = re.search(r'data-width="([^"]*?)"', div)
                    
                    if image_url_match:
                        image_link = image_url_match.group(1)
                        # Make sure the image link is properly formatted
                        if image_link.startswith('/'):
                            # This is a relative URL, prepend the site URL
                            image_link = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drive/root:{image_link}"
                        
                        filename = os.path.basename(image_link)
                        
                        image_data = {
                            "id": image_id_match.group(1) if image_id_match else f"img-{len(core_json['images'])}",
                            "imgHeight": height_match.group(1) if height_match else None,
                            "imgWidth": width_match.group(1) if width_match else None,
                            "imageLink": image_link,
                            "pageId": page_id,
                            "download_path": f"images/{page_id}/{filename}",
                            "source": "html"  # Mark that this was extracted from HTML
                        }
                        core_json["images"].append(image_data)

        except Exception as e:
            error_msg = f"Error processing page content with Graph API: {str(e)}"
            print(f"Attempting BeautifulSoup fallback for {page.get('webUrl')}")
            
            # Try BeautifulSoup fallback
            web_url = page.get('webUrl', '')
            if web_url:
                html_content = extract_html_with_beautifulsoup(web_url)
                if html_content:
                    core_json["innerHtml"] = html_content
                    core_json["processing_method"] = "beautifulsoup"
                    core_json["processing_error"] = f"{error_msg} (Recovered with BeautifulSoup)"
                    
                    # Also try to extract images from the BeautifulSoup content
                    if include_images:
                        image_divs = re.findall(r'<div class="imagePlugin"[^>]*?data-imageurl="[^"]*?"[^>]*?data-uniqueid="[^"]*?"[^>]*?></div>', 
                                              html_content)
                        
                        for div in image_divs:
                            # Extract attributes using regex
                            image_url_match = re.search(r'data-imageurl="([^"]*?)"', div)
                            image_id_match = re.search(r'data-uniqueid="([^"]*?)"', div)
                            height_match = re.search(r'data-height="([^"]*?)"', div)
                            width_match = re.search(r'data-width="([^"]*?)"', div)
                            
                            if image_url_match:
                                image_link = image_url_match.group(1)
                                # Make sure the image link is properly formatted
                                if image_link.startswith('/'):
                                    # This is a relative URL, prepend the site URL
                                    image_link = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drive/root:{image_link}"
                                
                                filename = os.path.basename(image_link)
                                
                                image_data = {
                                    "id": image_id_match.group(1) if image_id_match else f"img-{len(core_json['images'])}",
                                    "imgHeight": height_match.group(1) if height_match else None,
                                    "imgWidth": width_match.group(1) if width_match else None,
                                    "imageLink": image_link,
                                    "pageId": page_id,
                                    "download_path": f"images/{page_id}/{filename}",
                                    "source": "beautifulsoup"  # Mark that this was extracted from BeautifulSoup
                                }
                                core_json["images"].append(image_data)
                else:
                    core_json["processing_error"] = f"{error_msg} (BeautifulSoup fallback also failed)"
            else:
                core_json["processing_error"] = error_msg

        return core_json
    except Exception as e:
        error_msg = f"Error processing page metadata: {str(e)}"
        print(error_msg)
        return {
            "id": page.get('id', 'unknown'),
            "webUrl": page.get('webUrl', ''),
            "title": page.get('fields', {}).get('Title', ''),
            "processing_error": error_msg,
            "processing_method": "failed"
        }

def process_pages_parallel(pages, include_images=True, max_workers=5):
    """Process pages in parallel"""
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_page = {
            executor.submit(process_page_data, page, include_images): page 
            for page in pages
        }
        
        processed_pages = []
        for future in concurrent.futures.as_completed(future_to_page):
            try:
                result = future.result()
                if result:
                    processed_pages.append(result)
            except Exception as e:
                print(f"Error processing page: {str(e)}")
                
        return processed_pages

@lru_cache(maxsize=1)
def get_site_drives():
    """Cache site drives to avoid repeated calls"""
    url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives?select=weburl,system,name,id"
    try:
        response = make_graph_request(url)
        drives = response.json().get('value', [])
        print(f"Found {len(drives)} drives: {[d.get('name', '') for d in drives]}")
        return drives
    except Exception as e:
        print(f"Error retrieving drives: {str(e)}")
        return []

# Cache for drive ID lookups
drive_id_cache = {}

def get_drive_id(image_path, drives):
    """Get drive ID based on file path by matching the drive URL path."""
    # Check cache first
    if image_path in drive_id_cache:
        return drive_id_cache[image_path]
    
    # Handle full Graph API URLs with /drive/root: pattern
    if image_path.startswith('https://graph.microsoft.com/') and '/drive/root:' in image_path:
        # Extract the relative path from the URL
        match = re.search(r'/drive/root:(.+)', image_path)
        if match:
            relative_path = unquote(match.group(1).strip("/"))
            path_parts = relative_path.split('/')
            
            # Skip the /sites/site-name part and get the drive name
            if len(path_parts) >= 3 and path_parts[0] == 'sites':
                drive_path = path_parts[2]  # This should be the drive name (e.g., SiteAssets)
                file_path = '/'.join(path_parts[3:]) if len(path_parts) > 3 else ''
                
                print(f"Parsed Graph URL - Drive path: {drive_path}, File path: {file_path}")
            else:
                print(f"❌ Cannot parse path structure: {relative_path}")
                drive_id_cache[image_path] = None
                return None
        else:
            print(f"❌ Cannot extract relative path from: {image_path}")
            drive_id_cache[image_path] = None
            return None
    # Handle other URL formats
    elif image_path.startswith('https://'):
        # Parse the URL to extract components
        parsed_url = urllib.parse.urlparse(image_path)
        path_parts = parsed_url.path.strip('/').split('/')
        
        # Extract drive path
        if len(path_parts) >= 3:
            drive_path = path_parts[2]  # Assuming the third segment is the drive name
            file_path = '/'.join(path_parts[3:]) if len(path_parts) > 3 else ''
            
            print(f"Parsed URL - Drive path: {drive_path}, File path: {file_path}")
        else:
            print(f"❌ Cannot parse URL structure: {image_path}")
            drive_id_cache[image_path] = None
            return None
    # Handle relative paths
    else:
        relative_path = unquote(image_path.strip("/"))
        path_parts = relative_path.split('/')
        
        # Extract drive path
        if len(path_parts) >= 3 and path_parts[0] == 'sites':
            drive_path = path_parts[2]  # This should be the drive name
            file_path = '/'.join(path_parts[3:]) if len(path_parts) > 3 else ''
            
            print(f"Parsed relative path - Drive path: {drive_path}, File path: {file_path}")
        else:
            print(f"❌ Cannot parse relative path structure: {image_path}")
            drive_id_cache[image_path] = None
            return None
    
    # Now that we have the drive_path, find the matching drive by URL
    drive_path_encoded = urllib.parse.quote(drive_path)
    for drive in drives:
        drive_url = drive.get("webUrl", "")
        
        # Extract the last segment of the drive URL
        drive_url_parts = drive_url.split('/')
        drive_url_last_segment = drive_url_parts[-1] if drive_url_parts else ""
        
        # Check if the drive URL contains the drive path
        if (drive_path.lower() == drive_url_last_segment.lower() or 
            drive_path_encoded.lower() == drive_url_last_segment.lower()):
            drive_id = drive.get("id", "")
            drive_id_cache[image_path] = drive_id
            print(f"✅ Found matching drive by URL path: {drive_url} with ID: {drive_id}")
            return drive_id
    
    # If no match by URL, try matching by name as a fallback
    for drive in drives:
        drive_name = drive.get("name", "")
        if drive_name.lower() == drive_path.lower() or drive_name.lower().replace(" ", "") == drive_path.lower().replace(" ", ""):
            drive_id = drive.get("id", "")
            drive_id_cache[image_path] = drive_id
            print(f"✅ Found matching drive by name: {drive_name} with ID: {drive_id}")
            return drive_id
    
    print(f"❌ No matching drive found for path: {image_path}")
    print(f"Available drives: {[d.get('name', '') for d in drives]}")
    drive_id_cache[image_path] = None
    return None

def download_single_image(img, drives, base_image_dir):
    """Download a single image - for parallel processing"""
    try:
        image_path = img.get("imageLink", "")
        if not image_path:
            return img
            
        page_id = img.get("pageId")
        if not page_id:
            return img
            
        # Create page-specific directory
        page_image_dir = os.path.join(base_image_dir, page_id)
        os.makedirs(page_image_dir, exist_ok=True)

        # Extract the filename from the path
        filename = os.path.basename(image_path)
        
        # Parse the image path to get drive name and file path
        drive_name, file_path = parse_image_path(image_path)
        if not drive_name:
            img["download_error"] = f"Could not determine drive name from path: {image_path}"
            return img
            
        print(f"Looking for drive: {drive_name}")
        print(f"File path within drive: {file_path}")
        
        # Find the drive ID by matching the drive name in the URL
        drive_id = None
        
        # Try both encoded and decoded versions of the drive name
        drive_name_encoded = urllib.parse.quote(drive_name)
        drive_name_decoded = urllib.parse.unquote(drive_name)
        
        for drive in drives:
            drive_url = drive.get("webUrl", "")
            
            # Check if any version of the drive name is in the URL
            if (drive_name in drive_url or 
                drive_name_encoded in drive_url or 
                drive_name_decoded in drive_url):
                drive_id = drive.get("id")
                print(f"✅ Found matching drive by URL: {drive_url}")
                break
                
        if not drive_id:
            # Try matching by the last segment of the URL
            for drive in drives:
                drive_url = drive.get("webUrl", "")
                drive_url_parts = drive_url.split('/')
                last_segment = drive_url_parts[-1] if drive_url_parts else ""
                last_segment_decoded = urllib.parse.unquote(last_segment)
                
                if (drive_name == last_segment or 
                    drive_name == last_segment_decoded or
                    drive_name.replace(" ", "") == last_segment_decoded.replace(" ", "")):
                    drive_id = drive.get("id")
                    print(f"✅ Found matching drive by URL last segment: {drive_url}")
                    break
                    
        if not drive_id:
            # Try matching by name as final fallback
            for drive in drives:
                drive_name_from_api = drive.get("name", "")
                if (drive_name.lower() == drive_name_from_api.lower() or
                    drive_name.lower().replace(" ", "") == drive_name_from_api.lower().replace(" ", "")):
                    drive_id = drive.get("id")
                    print(f"✅ Found matching drive by name: {drive_name_from_api}")
                    break
                    
        if not drive_id:
            img["download_error"] = f"No matching drive found for: {drive_name}"
            print(f"❌ No matching drive found for: {drive_name}")
            print(f"Available drives: {[d.get('name', '') for d in drives]}")
            print(f"Drive URLs: {[d.get('webUrl', '') for d in drives]}")
            return img
            
        # Construct the URL to access the file
        site_id = "gspnet4.sharepoint.com,81f8d801-fd05-42f0-a751-d21262e3605f,ce25b37e-9b1d-4968-afdc-18288091664d"
        drive_url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives/{drive_id}/root:/{file_path}"
        print(f"Requesting file from: {drive_url}")
        
        try:
            response = make_graph_request(drive_url)
            download_url = response.json().get('@microsoft.graph.downloadUrl')
            
            if download_url:
                file_response = session.get(download_url, stream=True)
                file_path = os.path.join(page_image_dir, filename)
                
                with open(file_path, "wb") as handler:
                    for chunk in file_response.iter_content(chunk_size=8192):
                        handler.write(chunk)
                
                # Add download path to image data
                img["download_path"] = os.path.join("images", page_id, filename).replace("\\", "/")
                print(f"✅ Downloaded: {filename} to {page_image_dir}")
            else:
                img["download_error"] = f"No download URL found for: {image_path}"
        except Exception as e:
            img["download_error"] = f"Error accessing file: {str(e)}"
            print(f"❌ Error accessing file: {str(e)}")
        
        return img
    except Exception as e:
        print(f"Error downloading image {img.get('imageLink', 'unknown')}: {str(e)}")
        img["download_error"] = str(e)
        return img

def parse_image_path(image_path):
    """Parse image path to extract drive name and file path"""
    # Handle Graph API URLs
    if image_path.startswith('https://graph.microsoft.com/'):
        match = re.search(r'root:/sites/[^/]+/([^/]+)/(.*)', image_path)
        if match:
            drive_name = match.group(1)
            file_path = match.group(2)
            return drive_name, file_path
    
    # Handle SharePoint URLs
    elif image_path.startswith('https://gspnet4.sharepoint.com/'):
        parts = image_path.split('/sites/')[1].split('/', 2)
        if len(parts) >= 3:
            site_name = parts[0]
            drive_name = parts[1]
            file_path = parts[2]
            return drive_name, file_path
    
    # Handle relative paths
    elif image_path.startswith('/sites/'):
        parts = image_path.split('/sites/')[1].split('/', 2)
        if len(parts) >= 3:
            site_name = parts[0]
            drive_name = parts[1]
            file_path = parts[2]
            return drive_name, file_path
    
    print(f"❌ Could not parse image path: {image_path}")
    return None, None

def download_images(image_list, base_image_dir="images", max_workers=5):
    """Optimized image download with parallel processing"""
    os.makedirs(base_image_dir, exist_ok=True)
    drives = get_site_drives()
    
    # Use ThreadPoolExecutor for parallel downloads
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all download tasks
        future_to_img = {
            executor.submit(download_single_image, img, drives, base_image_dir): img 
            for img in image_list
        }
        
        # Process results as they complete
        for future in concurrent.futures.as_completed(future_to_img):
            img = future_to_img[future]
            try:
                future.result()  # This will raise any exceptions from the thread
            except Exception as e:
                print(f"Error processing image {img.get('imageLink', 'unknown')}: {str(e)}")
                img["download_error"] = str(e)

def main():
    if len(sys.argv) != 2:
        print("Usage: python scrape_and_filter_sharepoint.py <url_segments_file_path>")
        sys.exit(1)

    url_segments_file_path = sys.argv[1]
    url_segments_to_keep = read_url_segments_from_file(url_segments_file_path)
    
    try:
        print("Retrieving all SharePoint pages...")
        pages = get_pages(limit=None, batch_size=10)
        print(f"Retrieved {len(pages)} pages total")

        # Split pages into two groups based on URL segments
        pages_to_migrate = []
        pages_to_exclude = []
        
        for page in pages:
            url_segment = extract_url_segment(page.get('webUrl', ''))
            if url_segment in [seg.lower().strip() for seg in url_segments_to_keep]:
                pages_to_migrate.append(page)
            else:
                pages_to_exclude.append(page)

        # Process pages to migrate with images
        print(f"Processing {len(pages_to_migrate)} pages to migrate...")
        processed_migrate = process_pages_parallel(pages_to_migrate, include_images=True)

        # Process excluded pages without images
        print(f"Processing {len(pages_to_exclude)} pages to exclude...")
        processed_exclude = process_pages_parallel(pages_to_exclude, include_images=False)

        # Save results
        output_dir = "data"
        os.makedirs(output_dir, exist_ok=True)
        current_time = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Save both sets of pages
        migrate_path = os.path.join(output_dir, f"{current_time}_exported_pages_to_migrate.json")
        exclude_path = os.path.join(output_dir, f"{current_time}_exported_pages_to_exclude.json")
        error_path = os.path.join(output_dir, f"{current_time}_processing_errors.json")

        # Collect pages with errors
        error_pages = []
        for page in processed_migrate + processed_exclude:
            if page.get("processing_error"):
                error_pages.append({
                    "id": page.get("id"),
                    "title": page.get("title"),
                    "webUrl": page.get("webUrl"),
                    "error": page.get("processing_error"),
                    "processing_method": page.get("processing_method", "unknown")
                })

        with open(migrate_path, "w") as f:
            json.dump(processed_migrate, f, indent=4)
        with open(exclude_path, "w") as f:
            json.dump(processed_exclude, f, indent=4)
        with open(error_path, "w") as f:
            json.dump(error_pages, f, indent=4)

        # Download images only for pages to migrate that don't have errors
        successful_pages = [p for p in processed_migrate if not p.get("processing_error")]
        all_images = [img for page in successful_pages for img in page.get("images", [])]
        print(f"Found {len(all_images)} images to download")
        if all_images:
            print(f"Downloading {len(all_images)} images...")
            download_images(all_images, max_workers=5)

        # Add processing method statistics to final summary
        methods_count = {
            "graph": len([p for p in processed_migrate + processed_exclude if p.get("processing_method") == "graph"]),
            "beautifulsoup": len([p for p in processed_migrate + processed_exclude if p.get("processing_method") == "beautifulsoup"]),
            "failed": len([p for p in processed_migrate + processed_exclude if p.get("processing_method") == "failed"])
        }

        print("\nProcessing methods used:")
        print(f"Graph API: {methods_count['graph']}")
        print(f"BeautifulSoup: {methods_count['beautifulsoup']}")
        print(f"Failed: {methods_count['failed']}")

        print(f"\nProcessing complete:")
        print(f"Pages to migrate: {len(processed_migrate)}")
        print(f"Pages to exclude: {len(processed_exclude)}")
        print(f"Pages with errors: {len(error_pages)}")
        print(f"Migration JSON saved to: {migrate_path}")
        print(f"Excluded JSON saved to: {exclude_path}")
        print(f"Error report saved to: {error_path}")

    except Exception as e:
        print(f"Error in main execution: {str(e)}")
    finally:
        session.close()

if __name__ == "__main__":
    main() 