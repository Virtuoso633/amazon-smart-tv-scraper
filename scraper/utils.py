# scraper/utils.py

import time
import random
import re

def clean_text(text):
    """
    Clean the input text by removing extra spaces and newline characters.
    
    Args:
        text (str): The text to clean.
    
    Returns:
        str: Cleaned text.
    """
    if text:
        text = re.sub(r'\s+', ' ', text).strip()
    return text

def random_delay(min_delay=1, max_delay=3):
    """
    Sleep for a random amount of time between min_delay and max_delay seconds.
    
    Args:
        min_delay (int): Minimum seconds to wait.
        max_delay (int): Maximum seconds to wait.
    """
    delay = random.uniform(min_delay, max_delay)
    time.sleep(delay)

def log(message):
    """
    Print a log message with a timestamp.
    
    Args:
        message (str): The message to log.
    """
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}")
