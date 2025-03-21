import requests
import os
from urllib.parse import urlparse
from config import get_config
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def download_file(url, save_path):
    """Скачивает файл по URL."""
    config = get_config()
    try:
        logging.info(f"Скачивание: {url} -> {save_path}")
        headers = {'User-Agent': config['user_agent']}
        response = requests.get(url, stream=True, timeout=config['request_timeout'], headers=headers)
        response.raise_for_status()

        with open(save_path, 'wb') as file:
            for chunk in response.iter_content(chunk_size=8192):
                file.write(chunk)
        return True
    except requests.exceptions.RequestException as e:
        logging.error(f"Ошибка при скачивании {url}: {e}")
        return False

def get_filename_from_url(url):
    path = urlparse(url).path
    return os.path.basename(path)

def is_resource_url(url):
    config = get_config()
    filename = get_filename_from_url(url)
    if not filename:
        return False

    _, ext = os.path.splitext(filename)
    return ext.lower() in config['resource_extensions']