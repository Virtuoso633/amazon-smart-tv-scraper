import requests
import json
import os
import time
import re
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from .utils import clean_text, random_delay, log
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager


# Load environment variables
load_dotenv()
HF_API_KEY = os.getenv("HF_API_KEY")

# Headers to mimic a browser
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/90.0.4430.93 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9"
}

def fetch_html(url, retries=3, delay=5):
    """Fetch HTML with retry logic."""
    for attempt in range(retries):
        try:
            log(f"Fetching URL (Attempt {attempt+1}): {url}")
            response = requests.get(url, headers=HEADERS, timeout=10)
            response.raise_for_status()
            random_delay()
            return response.text
        except requests.RequestException as e:
            log(f"Error fetching URL {url} (Attempt {attempt+1}): {e}")
            time.sleep(delay)
    return None

def parse_element(soup, selector, attr=None):
    """Parse elements with error handling."""
    element = soup.select_one(selector)
    return clean_text(element.get(attr) if attr else element.get_text()) if element else None

def parse_product_details(soup):
    """Extract product details."""
    return {
        "name": parse_element(soup, "#productTitle"),
        "rating": parse_element(soup, "i[data-hook=average-star-rating]"),
        "number_of_ratings": parse_element(soup, "#acrCustomerReviewText"),
        "selling_price": parse_element(soup, "#priceblock_ourprice") or parse_element(soup, "#priceblock_dealprice"),
        "total_discount": parse_element(soup, "td:contains('Discount:') + td"),
    }

def parse_descriptions(soup):
    """Extract descriptions."""
    about = [clean_text(bp.get_text()) for bp in soup.select("#feature-bullets .a-list-item") if bp]
    prod_info = {clean_text(row.th.get_text()): clean_text(row.td.get_text()) for row in soup.select("#productDetails_techSpec_section_1 tr") if row.th and row.td}
    return {"about": about or None, "product_information": prod_info or None}

def get_all_images_with_selenium(url):
    """Use Selenium to extract all images from an Amazon product page, including product gallery and 'From the Manufacturer' section."""
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--log-level=3")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    driver.get(url)
    time.sleep(5)  # Wait for the page to load fully

    images = {"product_images": [], "thumbnail_images": []}

    try:
        # Extract product ASIN (unique identifier)
        asin = None
        try:
            # Try to extract ASIN from URL
            asin_match = re.search(r'/dp/([A-Z0-9]{10})', url)
            if asin_match:
                asin = asin_match.group(1)
            else:
                # Try to find ASIN in page
                asin_elem = driver.find_element(By.CSS_SELECTOR, "#ASIN, input[name='ASIN']")
                asin = asin_elem.get_attribute("value")
            
            log(f"Found product ASIN: {asin}")
        except Exception as e:
            log(f"Could not determine product ASIN: {e}")

        # PART 1: PRODUCT GALLERY IMAGES
        
        # Method 1: Main product image
        try:
            main_image = driver.find_element(By.CSS_SELECTOR, "#landingImage, #imgBlkFront")
            main_image_url = main_image.get_attribute("src")
            if main_image_url and "data:image" not in main_image_url:
                images["product_images"].append(main_image_url)
                log(f"Found main image: {main_image_url[:60]}...")
        except Exception as e:
            log(f"Could not get main image: {e}")
            
        # Method 2: Thumbnail images and their high-res versions
        try:
            thumbnails = driver.find_elements(By.CSS_SELECTOR, "#altImages li img, #imageBlock_feature_div img.imageThumbnail")
            log(f"Found {len(thumbnails)} thumbnail images")
            
            # Extract only product-related thumbnails
            valid_thumbnails = []
            for thumb in thumbnails:
                thumb_src = thumb.get_attribute("src")
                # Check if this thumbnail belongs to the current product
                if thumb_src and asin and asin in thumb_src:
                    valid_thumbnails.append(thumb)
                elif thumb_src and "sprite" not in thumb_src and "play-icon" not in thumb_src and "transparent-pixel" not in thumb_src:
                    valid_thumbnails.append(thumb)
                    
            log(f"Found {len(valid_thumbnails)} valid thumbnail images")
            
            for i, thumb in enumerate(valid_thumbnails[:15]):
                thumb_src = thumb.get_attribute("src")
                if not thumb_src or "sprite" in thumb_src or "play-icon" in thumb_src:
                    continue
                    
                # Store the thumbnail image
                images["thumbnail_images"].append(thumb_src)
                
                # Try to get high-resolution version
                # Method A: Use data attributes
                hi_res = None
                for attr in ["data-old-hires", "data-a-dynamic-image", "data-zoom-hires"]:
                    hi_res_url = thumb.get_attribute(attr)
                    if hi_res_url and "data:image" not in hi_res_url:
                        hi_res = hi_res_url
                        break
                
                # Method B: Convert thumbnail URL to hi-res URL
                if not hi_res and thumb_src:
                    hi_res = re.sub(r'_S[XY]\d+_?|_SR\d+,\d+_?|_CR\d+,\d+,\d+,\d+_?|_SS\d+_?', '_SX679_', thumb_src)
                
                if hi_res and hi_res not in images["product_images"]:
                    images["product_images"].append(hi_res)
                    log(f"Added hi-res image {i+1}: {hi_res[:60]}...")
                    
        except Exception as e:
            log(f"Error processing thumbnails: {e}")
        
        # Method 3: Extract from JS data in page source
        try:
            page_source = driver.page_source
            # Look for image data in different JS objects used by Amazon
            patterns = [
                r"'colorImages': { 'initial': (\[.*?\])",
                r"'colorImages':\s*{.*?'initial':\s*(\[.*?\])",
                r"\"colorImages\":\s*{.*?\"initial\":\s*(\[.*?\])",
                r"data\[\"imageGalleryData\"\]\s*=\s*(\[.*?\])"
            ]
            
            for pattern in patterns:
                image_data_match = re.search(pattern, page_source, re.DOTALL)
                if image_data_match:
                    # Clean and parse the JSON data
                    image_json_str = image_data_match.group(1)
                    # Clean up the string to make it valid JSON
                    image_json_str = re.sub(r"([{,])\s*(\w+):", r'\1"\2":', image_json_str)
                    image_json_str = image_json_str.replace("'", '"')
                    
                    try:
                        image_data = json.loads(image_json_str)
                        log(f"Found {len(image_data)} images in JS data")
                        
                        # Extract image URLs
                        for item in image_data:
                            if isinstance(item, dict):
                                # Try different fields Amazon might use for hi-res images
                                for field in ["hiRes", "large", "mainUrl", "url", "thumb"]:
                                    if field in item and item[field] and "data:image" not in str(item[field]):
                                        hi_res_url = item[field]
                                        if isinstance(hi_res_url, str) and "video" not in hi_res_url.lower():
                                            images["product_images"].append(hi_res_url)
                                            log(f"Added image from JS data: {hi_res_url[:60]}...")
                                        break
                    except json.JSONDecodeError as e:
                        log(f"Could not parse image JSON data: {e}")
                    
                    break  # If we found and processed one pattern successfully, stop
            
        except Exception as e:
            log(f"Error extracting images from page source: {e}")

        # PART 2: "FROM THE MANUFACTURER" SECTION IMAGES
        
        try:
            # Look for the manufacturer section with various possible selectors
            manufacturer_section = driver.find_elements(By.CSS_SELECTOR, 
                "#aplus, #dpx-aplus-product-description_feature_div, #aplus3p_feature_div, .aplus-v2")
            
            for section in manufacturer_section:
                # Scroll to the section to ensure images are loaded
                driver.execute_script("arguments[0].scrollIntoView(true);", section)
                time.sleep(1)
                
                # Find all images in this section
                mfr_images = section.find_elements(By.TAG_NAME, "img")
                log(f"Found {len(mfr_images)} images in manufacturer section")
                
                for img in mfr_images:
                    try:
                        img_url = img.get_attribute("src")
                        # Skip small icons, spacers, and video thumbnails
                        if (img_url and 
                            "data:image" not in img_url and 
                            "video" not in img_url.lower() and
                            "icon" not in img_url.lower() and
                            "spacer" not in img_url.lower()):
                            
                            # Get larger version if possible (often Amazon uses _SL1500_ for full size)
                            hi_res_url = re.sub(r'_(S[XY]\d+|SR\d+,\d+|CR[\d,]+|SS\d+)_', '_SL1500_', img_url)
                            
                            if hi_res_url not in images["product_images"]:
                                images["product_images"].append(hi_res_url)
                                log(f"Added manufacturer image: {hi_res_url[:60]}...")
                    except Exception as e:
                        log(f"Error processing manufacturer image: {e}")
        except Exception as e:
            log(f"Error processing manufacturer section: {e}")
            
        # PART 3: ADDITIONAL IMAGE CONTAINERS (sometimes Amazon has images in other sections)
        
        try:
            # Look for other product image containers
            other_image_containers = driver.find_elements(By.CSS_SELECTOR, 
                ".image-block, .image-wrapper, .item-view-left-col-inner, #productDescription img, #feature-bullets img")
            
            for container in other_image_containers:
                # Scroll to container
                driver.execute_script("arguments[0].scrollIntoView(true);", container)
                time.sleep(0.5)
                
                # Find images
                other_images = []
                try:
                    other_images = container.find_elements(By.TAG_NAME, "img")
                except:
                    # If container itself is an image
                    if container.tag_name.lower() == "img":
                        other_images = [container]
                
                for img in other_images:
                    try:
                        img_url = img.get_attribute("src")
                        if (img_url and 
                            "data:image" not in img_url and
                            "video" not in img_url.lower() and
                            "sprite" not in img_url.lower() and
                            "transparent-pixel" not in img_url.lower()):
                            
                            # Try to get hi-res version
                            hi_res_url = re.sub(r'_(S[XY]\d+|SR\d+,\d+|CR[\d,]+|SS\d+)_', '_SX679_', img_url)
                            
                            if hi_res_url not in images["product_images"]:
                                images["product_images"].append(hi_res_url)
                                log(f"Added other product image: {hi_res_url[:60]}...")
                    except Exception:
                        pass
        except Exception as e:
            log(f"Error finding other product images: {e}")

    except Exception as e:
        log(f"General error in image extraction: {e}")
    finally:
        driver.quit()
    
    # Filter out duplicate images and non-product images
    def normalize_url(url):
        # Remove size parameters from Amazon image URLs
        return re.sub(r'_(S[XY]\d+|SR\d+,\d+|CR[\d,]+|SS\d+)_', '_', url)
    
    # Remove duplicates while preserving order
    unique_images = []
    normalized_urls = set()
    
    for img_url in images["product_images"]:
        norm_url = normalize_url(img_url)
        # Filter out icons, small images, and non-product images
        if (norm_url not in normalized_urls and 
            "icon" not in img_url.lower() and
            "button" not in img_url.lower() and
            "logo" not in img_url.lower() and
            "banner" not in img_url.lower()):
            normalized_urls.add(norm_url)
            unique_images.append(img_url)
    
    images["product_images"] = unique_images
    
    # If we have thumbnail images but no product images, use thumbnails
    if not images["product_images"] and images["thumbnail_images"]:
        images["product_images"] = images["thumbnail_images"]
    
    log(f"Found {len(images['product_images'])} unique product images")
    return images

def parse_reviews(soup):
    """Extract customer reviews."""
    return [clean_text(review.get_text()) for review in soup.select("[data-hook=review-body]")]

def generate_review_summary(reviews):
    """Generate review summary using Hugging Face API."""
    if not reviews or not HF_API_KEY:
        return "No summary available."
    full_text = " ".join(reviews[:10])
    url = "https://api-inference.huggingface.co/models/facebook/bart-large-cnn"
    headers = {"Authorization": f"Bearer {HF_API_KEY}"}
    payload = {"inputs": full_text}
    for attempt in range(3):
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=10)
            response.raise_for_status()
            result = response.json()
            return result[0].get("summary_text", "No summary available.") if isinstance(result, list) else "No summary available."
        except requests.exceptions.RequestException as e:
            log(f"API request failed (attempt {attempt + 1}): {e}")
            time.sleep(2 ** attempt)
    return "No summary available."

def scrape_product(url):
    """Scrape product details."""
    html = fetch_html(url)
    if not html:
        return None
    soup = BeautifulSoup(html, 'html.parser')

    # Get images using Selenium
    images = get_all_images_with_selenium(url)

    return {
        "product_details": parse_product_details(soup),
        "descriptions": parse_descriptions(soup),
        "images": images,
        "reviews": parse_reviews(soup),
        "review_summary": generate_review_summary(parse_reviews(soup))
    }

def save_to_markdown(data, filename="scraped_product.md"):
    """Save scraped data to Markdown."""
    md_lines = ["# Scraped Product Data\n"]
    def safe_text(value): return str(value) if value else "N/A"
    md_lines.append("## Product Details\n")
    for key, value in data.get("product_details", {}).items():
        md_lines.append(f"- **{key.capitalize()}**: {safe_text(value)}\n")
    md_lines.append("\n## Descriptions\n")
    for key, value in data.get("descriptions", {}).items():
        if isinstance(value, list):
            md_lines.append(f"### {key.replace('_', ' ').title()}\n")
            md_lines.extend(f"- {safe_text(v)}\n" for v in value)
        elif isinstance(value, dict):
            md_lines.append(f"### {key.replace('_', ' ').title()}\n")
            md_lines.extend(f"- **{k}**: {safe_text(v)}\n" for k, v in value.items())
    md_lines.append("\n## Images\n")
    for img in data.get("images", {}).get("product_images", []):
        md_lines.append(f"![Product Image]({safe_text(img)})\n")
    md_lines.append("\n## AI-Generated Review Summary\n")
    md_lines.append(safe_text(data.get("review_summary", "No summary available.")) + "\n")
    with open(filename, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))
    log(f"Data saved to {filename}")

if __name__ == "__main__":
    test_url = "https://www.amazon.in/VW-inches-Ultra-Google-VW43GQ1/dp/B0DRV6WTZY/ref=sr_1_17?crid=1QE3E6PC2G0IZ&dib=eyJ2IjoiMSJ9.7a4PA9QG0Zy8Q_9j5EtJ2lC06CPsgW3uIy1SaL4lehxd_Duchyl0dzFiKPCMDRTNGFoghJGfOabbv8aJaIR7ZYqLFRQWQQPO_LMXj9I63qvPkxxVz_eBs6_V48F4WDscWQAj5t7pC7huh7_b5Qk1DoJLT3rb__twshg1VMa3Nj0Kj_LKc9Cu0KM9g8ojUUPL8ar0GvmAg399RwKiPkvxOXjnG3YMe3xmsWCCNZ3jgLEd9yZywMxpX1UsVY-fMt1msx8AWUe7UU2xsc7HjvaC8ch_JnIjhSw5K5KHTGoqRQSxX7zhwUImFKA-9exMgCgsIxhB5wVA1sUgHjU7NWDt3T8DcaAjukiKebSijAxs8Og.RC47v-aksR8FEFc7U6n1FKtFV7VBKSW_5nyLncLVNJE&dib_tag=se&keywords=smart%2Btv&qid=1743572875&s=electronics&sprefix=smart%2Bt%2Celectronics%2C286&sr=1-17&th=1"
    data = scrape_product(test_url)
    if data:
        save_to_markdown(data)
    else:
        log("Scraping failed.")
