# scraper/__init__.py

from .scraper import (
    fetch_html,
    parse_product_details,
    parse_descriptions,
    get_all_images_with_selenium,
    parse_reviews,
    generate_review_summary,
    scrape_product
)
from .utils import clean_text, random_delay, log
