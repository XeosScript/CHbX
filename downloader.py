import os
import sys
import requests
from bs4 import BeautifulSoup
import urllib.parse
from utils import download_file, get_filename_from_url, is_resource_url
from config import get_config
import logging
import re
import json
import time
import random
import threading

from colorama import init, Fore, Back, Style

init()

import msvcrt

POLICY_ACCEPTED = False

MENU_ITEMS = [
    "Скачать веб-сайт",
    "Выход"
]

VISITED_URLS = set()

KEYPRESS_DELAY = 0.2

# ASCII Art Title
TITLE = f"""{Fore.GREEN}
 ░▒▓██████▓▒░░▒▓█▓▒░░▒▓█▓▒░▒▓███████▓▒░░▒▓█▓▒░░▒▓█▓▒░ 
░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░░▒▓█▓▒░ 
░▒▓█▓▒░      ░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░░▒▓█▓▒░ 
░▒▓█▓▒░      ░▒▓████████▓▒░▒▓███████▓▒░ ░▒▓██████▓▒░  
░▒▓█▓▒░      ░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░░▒▓█▓▒░ 
░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░░▒▓█▓▒░ 
 ░▒▓██████▓▒░░▒▓█▓▒░░▒▓█▓▒░▒▓███████▓▒░░▒▓█▓▒░░▒▓█▓▒░
{Style.RESET_ALL}
"""


def clear_screen():
    """Очищает консоль."""
    os.system('cls' if os.name == 'nt' else 'clear')


def check_policy_agreement():
    global POLICY_ACCEPTED
    policy_file = "policy.txt"
    policy_accepted_file = "policy_acc.txt"

    if not os.path.exists(policy_accepted_file):
        try:
            with open(policy_file, "r", encoding="utf-8") as f:
                policy_text = f.read()

            while True:
                clear_screen()
                print(TITLE)
                print(f"{Fore.YELLOW}{policy_text}{Style.RESET_ALL}")
                agreement = input(f"{Fore.CYAN}Вы согласны с условиями политики (y/n)? {Style.RESET_ALL}").lower()
                if agreement == "y":
                    try:
                        with open(policy_accepted_file, "w") as f:
                            f.write("Согласие принято")
                        POLICY_ACCEPTED = True
                        clear_screen()
                        break
                    except Exception as e:
                        logging.error(f"{Fore.RED}Ошибка при записи файла политики: {e}{Style.RESET_ALL}")
                        sys.exit(1)
                elif agreement == "n":
                    print(f"{Fore.RED}Вы должны принять условия политики для продолжения.{Style.RESET_ALL}")
                    sys.exit(1)
                else:
                    print(f"{Fore.YELLOW}Неверный ввод. Пожалуйста, введите 'y' или 'n'.{Style.RESET_ALL}")
        except FileNotFoundError:
            logging.error(f"{Fore.RED}Файл '{policy_file}' не найден.{Style.RESET_ALL}")
            sys.exit(1)
        except Exception as e:
            logging.error(f"{Fore.RED}Непредвиденная ошибка при чтении политики: {e}{Style.RESET_ALL}")
            sys.exit(1)
    else:
        POLICY_ACCEPTED = True


def generate_new_filename(filename):
    """Генерирует новое имя файла (1.css, 2.js, ...)."""
    base, ext = os.path.splitext(filename)
    i = 1
    save_path = get_config()['save_path']
    while os.path.exists(os.path.join(save_path, f"{i}{ext}")):
        i += 1
    return f"{i}{ext}"


def replace_absolute_urls(data, base_url):
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, str):
                try:
                    url_parsed = urllib.parse.urlparse(value)
                    if url_parsed.netloc:
                        relative_url = urllib.parse.urljoin('.', url_parsed.path)
                        data[key] = relative_url
                        logging.debug(
                            f"{Fore.BLUE}Заменена абсолютная ссылка в JSON-LD: {value} -> {relative_url}{Style.RESET_ALL}")
                except Exception as e:
                    logging.error(f"{Fore.RED}Ошибка при обработке ссылки {value}: {e}{Style.RESET_ALL}")
            else:
                replace_absolute_urls(value, base_url)
    elif isinstance(data, list):
        for item in data:
            replace_absolute_urls(item, base_url)
    return data


def fix_url(url):
    return urllib.parse.unquote(url)

def block_redirect_scripts(soup):
    redirect_patterns = [
        re.compile(r"window\.location\.href\s*=\s*['\"].*?['\"]", re.IGNORECASE),
        re.compile(r"window\.location\.replace\s*\(['\"].*?['\"]\)", re.IGNORECASE),
        re.compile(r"location\.href\s*=\s*['\"].*?['\"]", re.IGNORECASE),
        re.compile(r"location\.replace\s*\(['\"].*?['\"]\)", re.IGNORECASE)
    ]

    for script in soup.find_all('script'):
        if script.string:
            original_script = script.string 
            for pattern in redirect_patterns:
                script.string = pattern.sub('console.log("Перенаправление заблокировано")', script.string)
            if script.string != original_script:
                logging.info(f"{Fore.YELLOW}Заблокировано перенаправление в скрипте: {original_script[:50]}...{Style.RESET_ALL}")

def replace_absolute_links_in_file(file_path, base_url, save_path):
    """Заменяет абсолютные ссылки на локальные в файлах HTML и JS."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        def replace_url(match):
            absolute_url = match.group(0)
            try:
                parsed_url = urllib.parse.urlparse(absolute_url)
                if parsed_url.netloc:
                    if parsed_url.netloc == urllib.parse.urlparse(base_url).netloc:
                        filename = get_filename_from_url(absolute_url)
                        if not filename:
                            logging.warning(f"{Fore.YELLOW}Не удалось получить имя файла из URL: {absolute_url}{Style.RESET_ALL}")
                            return ""  # Удаляем ссылку, если не удалось получить имя

                        new_filename = generate_new_filename(filename)
                        #local_path = os.path.join(save_path, new_filename)  # Не используем local_path

                        # Скачиваем файл, если он еще не скачан
                        #if not os.path.exists(local_path):
                        #   if download_file(absolute_url, local_path):
                        #        logging.info(f"{Fore.BLUE}Скачан ресурс: {absolute_url} -> {local_path}{Style.RESET_ALL}")
                        #   else:
                        #       logging.warning(f"{Fore.YELLOW}Не удалось скачать ресурс: {absolute_url}{Style.RESET_ALL}")
                        #        return ""  #Удаляем ссылку, если не удалось скачать

                        return new_filename
                    else:
                        return ""
                else:
                    return absolute_url
            except Exception as e:
                logging.error(f"{Fore.RED}Ошибка при обработке URL {absolute_url}: {e}{Style.RESET_ALL}")
                return absolute_url

        # Регулярное выражение для поиска абсолютных URL
        url_pattern = re.compile(r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+', re.IGNORECASE)
        new_content = url_pattern.sub(replace_url, content)

        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(new_content)

        logging.info(f"{Fore.GREEN}Обработан файл: {file_path}{Style.RESET_ALL}")

    except Exception as e:
        logging.error(f"{Fore.RED}Ошибка при обработке файла {file_path}: {e}{Style.RESET_ALL}")


def analyze_html(soup, base_url):
    """Анализирует HTML на предмет проблем, мешающих локальному запуску."""
    problems = []

    for tag in soup.find_all(['script', 'link', 'img']):
        if tag.has_attr('src'):
            attr_name = 'src'
        elif tag.has_attr('href'):
            attr_name = 'href'
        else:
            continue

        resource_url = tag[attr_name]
        if resource_url and urllib.parse.urlparse(resource_url).netloc:
            if urllib.parse.urlparse(resource_url).netloc != urllib.parse.urlparse(base_url).netloc:
                problems.append(
                    f"{Fore.YELLOW}Абсолютная ссылка на сторонний ресурс: {resource_url} (возможна проблема CORS){Style.RESET_ALL}")

    if base_url.startswith('https'):
        for tag in soup.find_all(['script', 'link', 'img']):
            if tag.has_attr('src'):
                attr_name = 'src'
            elif tag.has_attr('href'):
                attr_name = 'href'
            else:
                continue

            resource_url = tag[attr_name]
            if resource_url and resource_url.startswith('http://'):
                problems.append(
                    f"{Fore.YELLOW}Небезопасный HTTP ресурс на HTTPS сайте: {resource_url} (Mixed Content){Style.RESET_ALL}")

    for tag in soup.find_all('meta', attrs={'name': 'referrer-policy'}):
        policy = tag.get('content')
        if policy and policy != "no-referrer":
            problems.append(f"{Fore.YELLOW}Referrer-Policy: {policy} (может блокировать Referer){Style.RESET_ALL}")

    return problems


def download_website(url, save_path, debug=False, is_recursive=False):
    """Скачивает веб-сайт по URL, сохраняет ресурсы, изменяет ссылки и анализирует HTML."""
    global VISITED_URLS

    config = get_config()
    os.makedirs(save_path, exist_ok=True)

    if url in VISITED_URLS:
        logging.info(f"{Fore.YELLOW}URL уже посещен: {url}{Style.RESET_ALL}")
        return

    VISITED_URLS.add(url)

    url = fix_url(url)

    try:
        if debug:
            logging.debug(f"{Fore.BLUE}Скачивание HTML: {url}{Style.RESET_ALL}")
        headers = {'User-Agent': config['user_agent']}
        response = requests.get(url, timeout=config['request_timeout'], headers=headers)
        response.raise_for_status()
        html_code = response.text
    except requests.exceptions.RequestException as e:
        logging.error(f"{Fore.RED}Ошибка при скачивании HTML: {e}{Style.RESET_ALL}")
        return

    soup = BeautifulSoup(html_code, 'html.parser')

    block_redirect_scripts(soup)

    for tag in soup.find_all(['img', 'link', 'script']):
        if tag.name == 'link' and tag.get('rel') != ['stylesheet']:
            continue

        if tag.has_attr('src'):
            attr_name = 'src'
        elif tag.has_attr('href'):
            attr_name = 'href'
        else:
            continue

        resource_url = tag[attr_name]

        resource_url = fix_url(resource_url)

        if resource_url and not urllib.parse.urlparse(resource_url).netloc:
            resource_url = urllib.parse.urljoin(url, resource_url)

        if not resource_url or not is_resource_url(resource_url):
            continue

        filename = get_filename_from_url(resource_url)
        if not filename:
            logging.warning(f"{Fore.YELLOW}Не удалось получить имя файла из URL: {resource_url}{Style.RESET_ALL}")
            continue

        new_filename = generate_new_filename(filename)
        local_path = os.path.join(save_path, new_filename)

        try:
            if debug:
                logging.debug(f"{Fore.BLUE}Скачивание ресурса: {resource_url} -> {local_path}{Style.RESET_ALL}")

            if download_file(resource_url, local_path):
                tag[attr_name] = new_filename
                if debug:
                    logging.debug(
                        f"{Fore.BLUE}Заменена ссылка: {resource_url} -> {new_filename}{Style.RESET_ALL}")
            else:
                tag[attr_name] = ''  
                logging.warning(f"{Fore.YELLOW}Не удалось скачать ресурс: {resource_url}, ссылка удалена.{Style.RESET_ALL}")

        except Exception as e:
            logging.error(f"{Fore.RED}Ошибка при обработке ресурса {resource_url}: {e}{Style.RESET_ALL}")
            continue  

    for script in soup.find_all('script', {'type': 'application/ld+json'}):
        try:
            json_data = json.loads(script.string)
            json_data = replace_absolute_urls(json_data, url)
            script.string = json.dumps(json_data, indent=4)
        except Exception as e:
            logging.error(f"{Fore.RED}Ошибка при обработке JSON-LD: {e}{Style.RESET_ALL}")

    parsed_url = urllib.parse.urlparse(url)
    path = parsed_url.path
    if not path or path == "/":
        filename = "index.html"
    else:
        filename = path.split("/")[-1]
        if "." not in filename:
            filename += ".html"

    index_path = os.path.join(save_path, filename)

    try:
        with open(index_path, 'w', encoding='utf-8') as f:
            f.write(str(soup))
        logging.info(f"{Fore.GREEN}Веб-сайт скачан в: {index_path}{Style.RESET_ALL}")
    except Exception as e:
        logging.error(f"{Fore.RED}Ошибка при записи файла HTML: {e}{Style.RESET_ALL}")
        return

    replace_absolute_links_in_file(index_path, url, save_path)

    problems = analyze_html(soup, url)
    if problems:
        print(f"{Fore.YELLOW}Обнаружены потенциальные проблемы, мешающие локальному запуску:{Style.RESET_ALL}")
        for problem in problems:
            print(problem)
    else:
        print(f"{Fore.GREEN}Проблем, мешающих локальному запуску, не обнаружено.{Style.RESET_ALL}")
        
    if is_recursive:
        try:
            for a_tag in soup.find_all('a', href=True):
                link_url = a_tag['href']
                if not urllib.parse.urlparse(link_url).netloc:
                    link_url = urllib.parse.urljoin(url, link_url)

                parsed_link_url = urllib.parse.urlparse(link_url)
                parsed_base_url = urllib.parse.urlparse(url)

                if parsed_link_url.netloc == parsed_base_url.netloc and not parsed_link_url.fragment:
                    time.sleep(1)
                    download_website(link_url, save_path, debug, is_recursive)
        except Exception as e:
            logging.error(f"{Fore.RED}Ошибка при рекурсивном скачивании: {e}{Style.RESET_ALL}")

    for root, _, files in os.walk(save_path):
        for file in files:
            if file.endswith(".js"):
                file_path = os.path.join(root, file)
                replace_absolute_links_in_file(file_path, url, save_path)



    input(f"{Fore.GREEN}Нажмите Enter для продолжения...{Style.RESET_ALL}")


def show_menu(selected_index, menu_type="main"):
    """Отображает консольное меню."""
    clear_screen()
    print(TITLE)  # Display title before menu

    if menu_type == "main":
        print(f"{Fore.CYAN}=== Главное меню ==={Style.RESET_ALL}")
        menu_items = MENU_ITEMS
    else:
        menu_items = []

    for i, item in enumerate(menu_items):
        if i == selected_index:
            print(f"{Fore.GREEN}> {item}{Style.RESET_ALL}")
        else:
            print(f"  {item}")


def download_menu(debug=False, recursive_download=False):
    """Меню для ввода URL и скачивания."""
    url = input(f"{Fore.CYAN}Введите URL сайта: {Style.RESET_ALL}")

    if url:
        url = url.strip()  # Remove leading/trailing whitespace
        try:
            download_website(url, get_config()['save_path'], debug, recursive_download)
        except Exception as e:
            logging.error(f"{Fore.RED}Критическая ошибка при скачивании сайта: {e}{Style.RESET_ALL}")
        finally:
            VISITED_URLS.clear()


def main():
    """Главная функция программы."""
    global stop_rain
    check_policy_agreement()

    if not POLICY_ACCEPTED:
        print(f"{Fore.RED}Программа завершена, так как вы не приняли условия политики.{Style.RESET_ALL}")
        return

    selected_index = 0
    show_menu(selected_index)

    try:
        while True:
            key = msvcrt.getch()

            try:
                key = key.decode('utf-8')
            except UnicodeDecodeError:
                key = ''

            if key == b'\\xe0':
                key = msvcrt.getch()
                if key == b'H':  # Up arrow
                    selected_index = (selected_index - 1) % len(MENU_ITEMS)
                    show_menu(selected_index)
                elif key == b'P':  # Down arrow
                    selected_index = (selected_index + 1) % len(MENU_ITEMS)
                    show_menu(selected_index)
            elif key == '\r':  # Enter
                if selected_index == 0:
                    download_menu()
                    show_menu(0)
                elif selected_index == 1:
                    print(f"{Fore.CYAN}Выход из программы.{Style.RESET_ALL}")
                    break
            elif key.lower() == '\x1b':  # Escape
                print(f"{Fore.CYAN}Выход из программы.{Style.RESET_ALL}")
                break

            time.sleep(KEYPRESS_DELAY)  # Add delay after key press
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    main()