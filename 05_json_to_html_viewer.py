import json
import os
from html import escape
import re
from bs4 import BeautifulSoup
import argparse

def create_html_viewer(json_file_path, error_json_path, output_html_path):
    """
    Convert JSON data to an HTML file for easy viewing.
    
    Args:
        json_file_path: Path to the JSON file with successful migrations
        error_json_path: Path to the JSON file with failed migrations
        output_html_path: Path where the HTML file will be saved
    """
    # Read the JSON files
    with open(json_file_path, 'r', encoding='utf-8') as f:
        articles = json.load(f)
    
    with open(error_json_path, 'r', encoding='utf-8') as f:
        error_articles = json.load(f)

    # Separate successful and error articles from the main JSON file
    successful_articles = []
    additional_error_articles = []
    
    for article in articles:
        if "processing_error" in article and article["processing_error"]:
            # This is an article with an error in the main JSON file
            additional_error_articles.append(article)
        else:
            # This is a successful article
            successful_articles.append(article)
    
    # Combine all error articles
    all_error_articles = error_articles + additional_error_articles
    
    # Sort successful articles alphabetically by title
    successful_articles.sort(key=lambda x: x.get('title', '').lower())
    
    # Sort error articles alphabetically by title
    all_error_articles.sort(key=lambda x: x.get('title', '').lower())
    
    # Calculate statistics
    total_articles = len(successful_articles)
    total_images = sum(len(article.get('images', [])) for article in successful_articles)
    total_links = sum(len(article.get('article_links', [])) for article in successful_articles)
    
    # Count articles that need review
    needs_review = len(all_error_articles)
    
    # Count articles with image errors
    articles_with_image_errors = 0
    for article in successful_articles:
        has_image_error = False
        for img in article.get('images', []):
            if 'upload_error' in img or 'download_error' in img:
                has_image_error = True
                break
        if has_image_error:
            articles_with_image_errors += 1
    
    # Create HTML content
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>SharePoint Articles Viewer</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                line-height: 1.6;
                margin: 0;
                padding: 20px;
                color: #333;
            }
            .container {
                max-width: 1200px;
                margin: 0 auto;
            }
            h1 {
                color: #2c5282;
                border-bottom: 2px solid #eaeaea;
                padding-bottom: 10px;
            }
            .article {
                margin-bottom: 40px;
                border: 1px solid #ddd;
                border-radius: 5px;
                padding: 20px;
                background-color: #f9f9f9;
            }
            .article-title {
                color: #2c5282;
                margin-top: 0;
            }
            .article-content {
                background-color: white;
                padding: 15px;
                border-radius: 5px;
                border: 1px solid #eee;
                margin-top: 20px;
            }
            .article-images {
                margin-top: 10px;
            }
            .article-image {
                margin-bottom: 10px;
                padding: 10px;
                background-color: white;
                border: 1px solid #eee;
                border-radius: 5px;
            }
            .article-image.needs-review {
                border-left: 4px solid #e53e3e;
                background-color: #fff5f5;
            }
            .article-links {
                margin-top: 10px;
            }
            .article-link {
                display: block;
                margin-bottom: 5px;
            }
            .toc {
                position: fixed;
                top: 20px;
                right: 20px;
                width: 250px;
                max-height: 80vh;
                overflow-y: auto;
                background-color: white;
                border: 1px solid #ddd;
                border-radius: 5px;
                padding: 15px;
                font-size: 14px;
                z-index: 100;
            }
            .toc h2 {
                margin-top: 0;
                font-size: 18px;
            }
            .toc ul {
                padding-left: 20px;
            }
            .toc a {
                text-decoration: none;
                color: #2c5282;
            }
            .toc a:hover {
                text-decoration: underline;
            }
            .stats {
                background-color: #f0f4f8;
                padding: 15px;
                border-radius: 5px;
                margin-bottom: 20px;
                border-left: 4px solid #2c5282;
            }
            .modal {
                display: none;
                position: fixed;
                z-index: 1000;
                left: 0;
                top: 0;
                width: 100%;
                height: 100%;
                background-color: rgba(0,0,0,0.7);
                justify-content: center;
                align-items: center;
            }
            .modal.show {
                display: flex !important;
            }
            .modal-content {
                background-color: white;
                padding: 30px;
                border-radius: 8px;
                max-width: 500px;
                width: 80%;
                text-align: center;
            }
            .modal-content h2 {
                color: #2c5282;
                margin-top: 0;
            }
            .modal-content button {
                background-color: #2c5282;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 5px;
                cursor: pointer;
                font-size: 16px;
                margin-top: 20px;
            }
            .modal-content button:hover {
                background-color: #1a365d;
            }
            .metadata {
                background-color: #f5f5f5;
                padding: 10px;
                border-radius: 5px;
                margin-top: 10px;
            }
            .servicenow-link {
                font-size: 14px;
                color: #2c5282;
                margin-left: 10px;
            }
            .back-to-top {
                position: fixed;
                bottom: 20px;
                right: 20px;
                background-color: #2c5282;
                color: white;
                border-radius: 50%;
                width: 50px;
                height: 50px;
                text-align: center;
                line-height: 50px;
                font-size: 20px;
                text-decoration: none;
                opacity: 0.7;
                transition: opacity 0.3s;
                z-index: 1000;
            }
            .back-to-top:hover {
                opacity: 1;
            }
            .needs-review {
                color: #e53e3e;
                font-weight: bold;
            }
            .collapsible {
                background-color: #edf2f7;
                color: #2c5282;
                cursor: pointer;
                padding: 10px;
                width: 100%;
                border: none;
                text-align: left;
                outline: none;
                font-size: 16px;
                border-radius: 5px;
                margin-top: 10px;
                font-weight: bold;
                display: flex;
                justify-content: space-between;
                align-items: center;
            }
            .collapsible:after {
                content: '\\002B'; /* Unicode character for "plus" sign (+) */
                font-size: 20px;
                color: #2c5282;
            }
            .active:after {
                content: '\\2212'; /* Unicode character for "minus" sign (-) */
            }
            .collapsible-content {
                max-height: 0;
                overflow: hidden;
                transition: max-height 0.2s ease-out;
                background-color: white;
                border-radius: 0 0 5px 5px;
                padding: 0 18px;
            }
            @media (max-width: 1200px) {
                .toc {
                    position: static;
                    width: auto;
                    max-height: none;
                    margin-bottom: 30px;
                }
                .back-to-top {
                    bottom: 10px;
                    right: 10px;
                }
            }
            .error-message {
                background-color: #fed7d7;
                border-left: 4px solid #e53e3e;
                padding: 10px;
                margin-top: 10px;
                border-radius: 5px;
            }
            .success-indicator {
                color: #38a169;
                margin-right: 5px;
            }
            .error-indicator {
                color: #e53e3e;
                margin-right: 5px;
            }
            .warning-indicator {
                color: #dd6b20;
                margin-right: 5px;
            }
            .image-error-badge {
                display: inline-block;
                background-color: #e53e3e;
                color: white;
                border-radius: 50%;
                width: 20px;
                height: 20px;
                text-align: center;
                line-height: 20px;
                font-size: 12px;
                margin-left: 5px;
            }
            .toc-section {
                margin-top: 15px;
                border-top: 1px solid #eaeaea;
                padding-top: 10px;
            }
            .toc-section-title {
                font-weight: bold;
                margin-bottom: 5px;
                color: #2c5282;
            }
        </style>
    </head>
    <body>
        <!-- Login Modal -->
        <div id="loginModal" class="modal">
            <div class="modal-content">
                <h2>Important Note</h2>
                <p>This is a migration preview tool. Some articles may require additional processing.</p>
                <button onclick="dismissModal()">Understood</button>
            </div>
        </div>
        
        <!-- Back to Top Button -->
        <a href="#top" class="back-to-top" title="Back to Top">↑</a>
        
        <div id="top" class="container">
            <h1>SharePoint Articles Migration Preview</h1>
            
            <div class="stats">
                <h2>Content Summary</h2>
                <p><strong>Total Articles:</strong> """ + str(total_articles) + """</p>
                <p><strong>Total Images:</strong> """ + str(total_images) + """</p>
                <p><strong>Total Links:</strong> """ + str(total_links) + """</p>
                <p><strong>Articles with Image Errors:</strong> <span class="warning-indicator">""" + str(articles_with_image_errors) + """</span></p>
                <p><strong>Needs Review:</strong> <span class="needs-review">""" + str(needs_review) + """</span></p>
            </div>
            
            <div class="toc">
                <h2>Table of Contents</h2>
                <div class="toc-section">
                    <div class="toc-section-title">Successful Articles</div>
                    <ul>
    """
    
    # Helper function to create ServiceNow URL
    def create_servicenow_url(title, sys_id):
        # Convert title to lowercase and replace spaces with hyphens
        url_title = re.sub(r'[^a-zA-Z0-9\s-]', '', title).lower().replace(' ', '-')
        return f"https://greshamsmithdev.service-now.com/now/nav/ui/classic/params/target/kb/en/{url_title}?id=kb_article_view&sys_kb_id={sys_id}"
    
    # Helper function to update image paths in HTML content
    def update_image_paths(html_content):
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Find all img tags
        for img in soup.find_all('img'):
            # Check if src attribute exists and starts with /sys_attachment.do
            if img.has_attr('src') and img['src'].startswith('/sys_attachment.do'):
                # Add ServiceNow prefix to the src attribute
                img['src'] = f"https://greshamsmithdev.service-now.com{img['src']}"
        
        return str(soup)
    
    # Helper function to check if an article has image errors
    def has_image_errors(article):
        for img in article.get('images', []):
            if 'upload_error' in img or 'download_error' in img:
                return True
        return False
    
    # Create TOC for successful articles
    for article in successful_articles:
        if 'title' in article and article['title']:
            article_id = article['id']
            title = article['title']
            
            # Add image error indicator if needed
            image_error_indicator = ""
            if has_image_errors(article):
                image_error_indicator = ' <span class="warning-indicator">⚠</span>'
                
            html_content += f'<li><a href="#article-{article_id}">{escape(title)}{image_error_indicator}</a></li>\n'
    
    # Close successful articles section and add needs review section
    html_content += """
                    </ul>
                </div>
    """
    
    # Add needs review section to TOC if there are error articles
    if all_error_articles:
        html_content += """
                <div class="toc-section">
                    <div class="toc-section-title">Needs Review</div>
                    <ul>
        """
        
        for article in all_error_articles:
            if 'title' in article and article['title']:
                article_id = article['id']
                title = article['title']
                html_content += f'<li><a href="#article-{article_id}"><span class="error-indicator">⚠</span> {escape(title)}</a></li>\n'
        
        html_content += """
                    </ul>
                </div>
        """
    
    html_content += """
            </div>
            
            <h2>Successful Articles</h2>
    """
    
    # Generate article content for successful articles
    for i, article in enumerate(successful_articles):
        # Check if article has image errors
        has_image_error = has_image_errors(article)
        
        # Set title class and indicator based on status
        title_class = "success-indicator"
        title_indicator = "✓"
        
        if has_image_error:
            title_class = "warning-indicator"
            title_indicator = "⚠"
        
        html_content += f'<div id="article-{article["id"]}" class="article">\n'
        
        # Article title with ServiceNow link if sys_id exists
        if 'title' in article and article['title']:
            html_content += f'<h2 class="article-title"><span class="{title_class}">{title_indicator}</span> {escape(article["title"])}'
            
            # Add ServiceNow link if sys_id exists
            if 'sys_id' in article:
                servicenow_url = create_servicenow_url(article["title"], article["sys_id"])
                html_content += f' <a href="{servicenow_url}" target="_blank" class="servicenow-link">(ServiceNow Link)</a>'
            
            html_content += '</h2>\n'
        
        # Article description
        if 'description' in article and article['description']:
            html_content += f'<p><strong>Description:</strong> {escape(article["description"])}</p>\n'
        
        # Article metadata
        html_content += '<div class="metadata">\n'
        if 'id' in article:
            html_content += f'<p><strong>ID:</strong> {escape(article["id"])}</p>\n'
        if 'webUrl' in article:
            html_content += f'<p><strong>URL:</strong> <a href="{escape(article["webUrl"])}" target="_blank">{escape(article["webUrl"])}</a></p>\n'
        html_content += '</div>\n'
        
        # Article images (collapsible)
        if 'images' in article and article['images']:
            image_section_id = f"images-{i}"
            
            # Count images with errors
            error_images = sum(1 for img in article['images'] if 'upload_error' in img or 'download_error' in img)
            error_badge = f' <span class="image-error-badge">{error_images}</span>' if error_images > 0 else ''
            
            html_content += f'<button class="collapsible">Images ({len(article["images"])}{error_badge})</button>\n'
            html_content += f'<div id="{image_section_id}" class="collapsible-content">\n'
            html_content += '<div class="article-images">\n'
            
            for img in article['images']:
                # Add error class if image has errors
                image_class = "article-image"
                if 'upload_error' in img or 'download_error' in img:
                    image_class += " needs-review"
                
                html_content += f'<div class="{image_class}">\n'
                if 'id' in img:
                    html_content += f'<p><strong>Image ID:</strong> {escape(img["id"])}</p>\n'
                if 'download_path' in img:
                    html_content += f'<p><strong>Path:</strong> {escape(img["download_path"])}</p>\n'
                if 'sys_id' in img:
                    html_content += f'<p><strong>ServiceNow URL:</strong> <a href="https://greshamsmithdev.service-now.com/sys_attachment.do?sys_id={escape(img["sys_id"])}" target="_blank">https://greshamsmithdev.service-now.com/sys_attachment.do?sys_id={escape(img["sys_id"])}</a></p>\n'
                if 'imgWidth' in img and 'imgHeight' in img:
                    html_content += f'<p><strong>Dimensions:</strong> {img["imgWidth"]}x{img["imgHeight"]}</p>\n'
                if 'upload_error' in img:
                    html_content += f'<p class="needs-review"><strong>Upload Error:</strong> {escape(img["upload_error"])}</p>\n'
                if 'download_error' in img:
                    html_content += f'<p class="needs-review"><strong>Download Error:</strong> {escape(img["download_error"])}</p>\n'
                html_content += '</div>\n'
                
            html_content += '</div>\n'
            html_content += '</div>\n'
        
        # Article links (collapsible)
        if 'article_links' in article and article['article_links']:
            links_section_id = f"links-{i}"
            html_content += f'<button class="collapsible">Links ({len(article["article_links"])})</button>\n'
            html_content += f'<div id="{links_section_id}" class="collapsible-content">\n'
            html_content += '<div class="article-links">\n'
            
            for link in article['article_links']:
                html_content += f'<a class="article-link" href="{escape(link)}" target="_blank">{escape(link)}</a>\n'
                
            html_content += '</div>\n'
            html_content += '</div>\n'
        
        # Article content with updated image paths (collapsible)
        if 'innerHtml' in article and article['innerHtml']:
            content_section_id = f"content-{i}"
            html_content += f'<button class="collapsible">Article Content</button>\n'
            html_content += f'<div id="{content_section_id}" class="collapsible-content">\n'
            
            # Update image paths in the HTML content
            updated_html = update_image_paths(article['innerHtml'])
            html_content += updated_html
            
            html_content += '</div>\n'
            html_content += '</div>\n'
            html_content += '<div class="article-links"><a href="#top">top</a></div>\n'
        html_content += '</div>\n'
    
    # Add error section
    if all_error_articles:
        html_content += '<h2 id="needs-review-section">Articles Requiring Review</h2>\n'
        
        for article in all_error_articles:
            html_content += f'<div class="article" id="article-{article["id"]}">\n'
            if 'title' in article and article['title']:
                html_content += f'<h2 class="article-title"><span class="error-indicator">⚠</span> {escape(article["title"])}'
                
                # Add ServiceNow link if sys_id exists
                if 'sys_id' in article:
                    servicenow_url = create_servicenow_url(article["title"], article["sys_id"])
                    html_content += f' <a href="{servicenow_url}" target="_blank" class="servicenow-link">(ServiceNow Link)</a>'
                
                html_content += '</h2>\n'
            
            # Article description
            if 'description' in article and article['description']:
                html_content += f'<p><strong>Description:</strong> {escape(article["description"])}</p>\n'
            
            # Article metadata
            html_content += '<div class="metadata">\n'
            if 'id' in article:
                html_content += f'<p><strong>ID:</strong> {escape(article["id"])}</p>\n'
            if 'webUrl' in article:
                html_content += f'<p><strong>URL:</strong> <a href="{escape(article["webUrl"])}" target="_blank">{escape(article["webUrl"])}</a></p>\n'
            html_content += '</div>\n'
            
            # Display processing error if present
            if 'processing_error' in article and article['processing_error']:
                html_content += f'<div class="error-message"><strong>Error:</strong> {escape(article["processing_error"])}</div>\n'
            
            # Article images (if any)
            if 'images' in article and article['images']:
                html_content += f'<button class="collapsible">Images ({len(article["images"])})</button>\n'
                html_content += f'<div class="collapsible-content">\n'
                html_content += '<div class="article-images">\n'
                
                for img in article['images']:
                    html_content += '<div class="article-image">\n'
                    if 'id' in img:
                        html_content += f'<p><strong>Image ID:</strong> {escape(img["id"])}</p>\n'
                    if 'download_path' in img:
                        html_content += f'<p><strong>Path:</strong> {escape(img["download_path"])}</p>\n'
                    if 'sys_id' in img:
                        html_content += f'<p><strong>ServiceNow URL:</strong> <a href="https://greshamsmithdev.service-now.com/sys_attachment.do?sys_id={escape(img["sys_id"])}" target="_blank">https://greshamsmithdev.service-now.com/sys_attachment.do?sys_id={escape(img["sys_id"])}</a></p>\n'
                    if 'imgWidth' in img and 'imgHeight' in img:
                        html_content += f'<p><strong>Dimensions:</strong> {img["imgWidth"]}x{img["imgHeight"]}</p>\n'
                    if 'upload_error' in img:
                        html_content += f'<p class="needs-review"><strong>Error:</strong> {escape(img["upload_error"])}</p>\n'
                    html_content += '</div>\n'
                    
                html_content += '</div>\n'
                html_content += '</div>\n'
            
            # Article content (if any)
            if 'innerHtml' in article and article['innerHtml']:
                html_content += f'<button class="collapsible">Article Content</button>\n'
                html_content += f'<div class="collapsible-content">\n'
                
                # Update image paths in the HTML content
                updated_html = update_image_paths(article['innerHtml'])
                html_content += updated_html
                
                html_content += '</div>\n'
            
            html_content += '<div class="article-links"><a href="#top">top</a></div>\n'
            html_content += '</div>\n'
    
    # Close HTML
    html_content += """
            </div>
        </div>
        
        <script>
            // Show modal on page load
            window.onload = function() {
                document.getElementById('loginModal').classList.add('show');
                
                // Initialize collapsible elements
                var coll = document.getElementsByClassName("collapsible");
                for (var i = 0; i < coll.length; i++) {
                    coll[i].addEventListener("click", function() {
                        this.classList.toggle("active");
                        var content = this.nextElementSibling;
                        if (content.style.maxHeight) {
                            content.style.maxHeight = null;
                        } else {
                            content.style.maxHeight = content.scrollHeight + "px";
                        }
                    });
                }
            };
            
            // Dismiss modal
            function dismissModal() {
                document.getElementById('loginModal').classList.remove('show');
            }
        </script>
    </body>
    </html>
    """
    
    # Write HTML to file
    with open(output_html_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"HTML viewer created at: {output_html_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Create HTML viewer for SharePoint article migration')
    parser.add_argument('--input', '-i',
                      default="",
                      help='Path to input JSON file with successful migrations')
    parser.add_argument('--errors', '-e',
                      default="",
                      help='Path to JSON file containing migration errors')
    parser.add_argument('--output', '-o',
                      default="sharepoint_articles_viewer.html",
                      help='Path for output HTML file')

    args = parser.parse_args()
    
    # Create the HTML viewer
    create_html_viewer(args.input, args.errors, args.output) 
    create_html_viewer(args.input, args.errors, args.output) 

    # <div class="article-links"><a href="#top">top</a></div>