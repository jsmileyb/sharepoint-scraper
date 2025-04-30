import json
import re
import os
from bs4 import BeautifulSoup
import urllib.parse

# Define file paths
# input_file = "data/20250224_175605_exported_pages.json"
input_file = input("Enter the path to the article data JSON file: ")
output_file = input_file.replace(".json", "_cleaned.json")

# Configuration
FONT_SIZE = "14px"

# Load JSON data
with open(input_file, "r", encoding="utf-8") as file:
    data = json.load(file)

# Regular expressions
div_pattern = re.compile(r'<div[^>]+data-instance-id="([^"]+)"[^>]*></div>')
image_plugin_pattern = re.compile(r'<div class="imagePlugin"[^>]*?data-imageurl="[^"]*?"[^>]*?data-uniqueid="[^"]*?"[^>]*?></div>')
p_tag_pattern = re.compile(r'<p(?![^>]*style)[^>]*>(.*?)</p>')
empty_p_pattern = re.compile(r'<p>\s*(&nbsp;)?\s*</p>') 
tr_tag_pattern = re.compile(r'<tr(?![^>]*style)[^>]*>(.*?)</tr>')

# Function to replace div tags with corresponding img tags
def replace_images_in_html(inner_html, images):
    print("\n🔍 Starting image processing...")
    print(f"Found {len(images) if images else 0} images in the data")
    
    # Create ID to image mapping
    id_to_image = {}
    for img in images:
        if "id" in img and "sys_id" in img:
            id_to_image[img["id"]] = img
            print(f"Mapped ID {img['id']} to sys_id {img['sys_id']}")
    
    def normalize_url(url):
        """Remove domain and decode URL for comparison"""
        # Decode URL
        url = urllib.parse.unquote(url)
        
        # Handle Graph API URLs
        if url.startswith('https://graph.microsoft.com/'):
            # Extract the path after "root:"
            match = re.search(r'root:/sites/[^/]+/([^/]+/.*)', url)
            if match:
                return match.group(1)
        
        # Handle SharePoint URLs
        elif url.startswith('https://gspnet4.sharepoint.com/'):
            # Extract the path after the domain and site name
            match = re.search(r'sharepoint\.com/sites/[^/]+/([^/]+/.*)', url)
            if match:
                return match.group(1)
        
        # Handle relative paths
        elif url.startswith('/sites/'):
            # Extract the path after the site name
            match = re.search(r'/sites/[^/]+/([^/]+/.*)', url)
            if match:
                return match.group(1)
        
        # If we can't parse it, return the original URL
        return url
    
    def replace_image_plugin_div(match, images):
        """Replace imagePlugin div with img tag"""
        full_div = match.group(0)
        url_match = re.search(r'data-imageurl="([^"]*)"', full_div)
        
        if url_match:
            html_image_url = url_match.group(1)
            normalized_html_url = normalize_url(html_image_url)
            print(f"\n🔍 Processing image URL: {normalized_html_url}")
            
            for img in images:
                if "imageLink" in img and "sys_id" in img:
                    normalized_json_url = normalize_url(img["imageLink"])
                    if normalized_html_url == normalized_json_url:
                        print(f"✅ Found matching image with sys_id: {img['sys_id']}")
                        
                        # Get image dimensions and convert to float first to handle decimal values
                        try:
                            img_width = float(img["imgWidth"]) if img["imgWidth"] else 0
                            img_height = float(img["imgHeight"]) if img["imgHeight"] else 0
                            
                            # If width is greater than 790px OR height is greater than 1000px, resize
                            if img_width > 790 or img_height > 1000:
                                original_width = img_width
                                original_height = img_height
                                
                                new_width = 395
                                
                                # Calculate new height to maintain aspect ratio
                                new_height = original_height * (new_width / original_width) if original_height and original_width else 0
                                
                                # Round the dimensions to integers
                                new_width = int(round(new_width))
                                new_height = int(round(new_height))
                                
                                print(f"📏 Resizing image from {original_width}x{original_height} to {new_width}x{new_height}")
                                
                                return f'<img style="display: block; margin-left: auto; margin-right: auto;" src="/sys_attachment.do?sys_id={img["sys_id"]}" alt="" width="{new_width}" height="{new_height}" data-selector="true" data-original-title="">'
                            else:
                                # Round dimensions to integers for the HTML
                                img_width_int = int(round(img_width))
                                img_height_int = int(round(img_height))
                                return f'<img style="display: block; margin-left: auto; margin-right: auto;" src="/sys_attachment.do?sys_id={img["sys_id"]}" alt="" width="{img_width_int}" height="{img_height_int}" data-selector="true" data-original-title="">'
                        except (ValueError, TypeError) as e:
                            print(f"⚠️ Error processing image dimensions: {e}. Using original dimensions.")
                            return f'<img style="display: block; margin-left: auto; margin-right: auto;" src="/sys_attachment.do?sys_id={img["sys_id"]}" alt="" data-selector="true" data-original-title="">'
            
            print("❌ No matching image found with sys_id")
        return full_div
    
    def replace_instance_div(match, id_to_image):
        """Replace instance-id div with img tag"""
        image_id = match.group(1)
        print(f"\n🔍 Looking for image with ID: {image_id}")
        
        if image_id in id_to_image:
            img = id_to_image[image_id]
            print(f"✅ Found matching image with sys_id: {img['sys_id']}")
            
            # Get image dimensions and convert to float first to handle decimal values
            try:
                img_width = float(img["imgWidth"]) if img["imgWidth"] else 0
                img_height = float(img["imgHeight"]) if img["imgHeight"] else 0
                
                # If width is greater than 790px OR height is greater than 1000px, resize
                if img_width > 790 or img_height > 1000:
                    original_width = img_width
                    original_height = img_height
                    
                    new_width = 395
                    
                    # Calculate new height to maintain aspect ratio
                    new_height = original_height * (new_width / original_width) if original_height and original_width else 0
                    
                    # Round the dimensions to integers
                    new_width = int(round(new_width))
                    new_height = int(round(new_height))
                    
                    print(f"📏 Resizing image from {original_width}x{original_height} to {new_width}x{new_height}")
                    
                    return f'<img style="display: block; margin-left: auto; margin-right: auto;" src="/sys_attachment.do?sys_id={img["sys_id"]}" alt="" width="{new_width}" height="{new_height}" data-selector="true" data-original-title="">'
                else:
                    # Round dimensions to integers for the HTML
                    img_width_int = int(round(img_width))
                    img_height_int = int(round(img_height))
                    return f'<img style="display: block; margin-left: auto; margin-right: auto;" src="/sys_attachment.do?sys_id={img["sys_id"]}" alt="" width="{img_width_int}" height="{img_height_int}" data-selector="true" data-original-title="">'
            except (ValueError, TypeError) as e:
                print(f"⚠️ Error processing image dimensions: {e}. Using original dimensions.")
                return f'<img style="display: block; margin-left: auto; margin-right: auto;" src="/sys_attachment.do?sys_id={img["sys_id"]}" alt="" data-selector="true" data-original-title="">'
        
        print(f"❌ No matching image found for ID: {image_id}")
        return match.group(0)

    result = inner_html
    
    # Process imagePlugin divs
    plugin_matches = list(image_plugin_pattern.finditer(inner_html))
    print(f"\n📊 Found {len(plugin_matches)} imagePlugin divs to process")
    
    for match in plugin_matches:
        original_div = match.group(0)
        new_img = replace_image_plugin_div(match, images)
        if original_div != new_img:
            print("🔄 Replacing imagePlugin div with new img tag")
            result = result.replace(original_div, new_img)
    
    # Process instance-id divs
    instance_matches = list(div_pattern.finditer(result))
    print(f"\n📊 Found {len(instance_matches)} instance-id divs to process")
    
    for match in instance_matches:
        original_div = match.group(0)
        new_img = replace_instance_div(match, id_to_image)
        if original_div != new_img:
            print("🔄 Replacing instance-id div with new img tag")
            result = result.replace(original_div, new_img)
    
    print("\n✨ Image processing complete")
    return result

# Function to apply all HTML replacements
def clean_html(html_content, images):
    # Replace images first
    html_content = replace_images_in_html(html_content, images)
    
    # Parse HTML with BeautifulSoup
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Extract all href values
    links = []
    for a in soup.find_all('a', href=True):
        href = a['href']
        # Fix SharePoint links
        if href.startswith('/sites'):
            href = f'https://gspnet4.sharepoint.com{href}'
            a['href'] = href
        links.append(href)
    
    # Process div tags
    for div in soup.find_all('div'):
        if 'class' in div.attrs:
            del div['class']
            
        # Check if div is empty or contains only &nbsp;
        if (not div.contents) or (len(div.contents) == 1 and div.string and div.string.strip() in ['', '&nbsp;']):
            # Replace empty div with br
            div.replace_with(soup.new_tag('br'))
        else:
            # Add font-size style to non-empty div
            if 'style' in div.attrs:
                # Append to existing style if it exists
                div['style'] = f'{div["style"]}; font-size: {FONT_SIZE}'
            else:
                div['style'] = f'font-size: {FONT_SIZE}'
            
            # If no p tags found inside div, wrap text content in span
            if not div.find('p'):
                if div.string and div.string.strip():
                    span = soup.new_tag('span')
                    span['style'] = f'font-size: {FONT_SIZE}'
                    div.string.wrap(span)
    
    # Convert back to string for remaining operations
    html_content = str(soup)
    
    # Fix for empty p tags - replace with <br>
    html_content = empty_p_pattern.sub('<br>', html_content)
    
    # REMOVE THE PROBLEMATIC REGEX REPLACEMENTS THAT CAUSE DUPLICATION
    # Instead of duplicating content with regex, we'll use BeautifulSoup to add styles
    
    # Parse HTML again to apply p and tr tag styling
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Process p tags - add font-size style without duplicating content
    for p in soup.find_all('p'):
        # Skip if p already has a span with font-size style
        if p.find('span', style=lambda s: s and f'font-size: {FONT_SIZE}' in s):
            continue
            
        # Add style to p tag content without duplicating it
        if p.contents and not all(isinstance(c, soup.new_tag('span').__class__) for c in p.contents):
            # Create a new span for the content
            span = soup.new_tag('span')
            span['style'] = f'font-size: {FONT_SIZE}'
            
            # Move all p contents to the span
            for content in list(p.contents):
                span.append(content.extract())
                
            # Add the span back to p
            p.append(span)
    
    # Process tr tags - add font-size style without duplicating content
    for tr in soup.find_all('tr'):
        # Skip if tr already has a span with font-size style
        if tr.find('span', style=lambda s: s and f'font-size: {FONT_SIZE}' in s):
            continue
            
        # Add style to each td in the tr
        for td in tr.find_all('td'):
            if td.contents and not all(isinstance(c, soup.new_tag('span').__class__) for c in td.contents):
                # Create a new span for the content
                span = soup.new_tag('span')
                span['style'] = f'font-size: {FONT_SIZE}'
                
                # Move all td contents to the span
                for content in list(td.contents):
                    span.append(content.extract())
                    
                # Add the span back to td
                td.append(span)
    
    return str(soup), links

# Process each item in the JSON data
for item in data:
    item["innerHtml"], item["article_links"] = clean_html(item["innerHtml"], item.get("images", []))

# Save the cleaned JSON
with open(output_file, "w", encoding="utf-8") as file:
    json.dump(data, file, indent=4, ensure_ascii=False)

print(f"Cleaned JSON file saved as {output_file}")
