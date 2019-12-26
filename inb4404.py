#!/usr/bin/python3

import argparse
import logging
import os
import re
import sys
import time

import urllib.error
from urllib.request import Request, urlopen

log = logging.getLogger("inb4404")
workpath = os.path.dirname(os.path.realpath(__file__))
args = None


def parse_cli():
    global args

    parser = argparse.ArgumentParser(description="inb4404")
    parser.add_argument(
        "thread", nargs=1,
        help="url of the thread")
    parser.add_argument(
        "-d", "--date", action="store_true",
        help="show date as well")
    parser.add_argument(
        "-n", "--use-names", action="store_true",
        help="use thread names instead of the thread ids")
    parser.add_argument(
        "-r", "--retries", type=int, default=5,
        help="how often to resume download after thrown errors")

    args = parser.parse_args()


def load_regex(url):
    # Custom header value is necessary to avoid 403 errors on 4chan.org
    # 4channel works just fine without
    req = Request(url, headers={'User-Agent': '4chan Archiver'})
    with urlopen(req) as resp:
        data = resp.read()

    regex = '(\/\/i(?:s|)\d*\.(?:4cdn|4chan)\.org\/\w+\/(\d+\.(?:jpg|png|gif|webm)))'
    regex_result = list(set(re.findall(regex, data.decode("utf-8"))))
    regex_result = sorted(regex_result, key=lambda tup: tup[1])

    return regex_result


def download_file(url, path):
    with urlopen(url) as content, open(path, "wb") as f:
        f.write(content.read())


def download_thread(thread_link):
    board = thread_link.split("/")[3]
    thread = thread_link.split("/")[5].split("#")[0]
    if len(thread_link.split("/")) > 6:
        thread_tmp = thread_link.split("/")[6].split("#")[0]

        if args.use_names or \
           os.path.exists(os.path.join(workpath, "downloads", board, thread_tmp)):
            thread = thread_tmp

    directory = os.path.join(workpath, "downloads", board, thread)
    if not os.path.exists(directory):
        os.makedirs(directory)

    try:
        results = load_regex(thread_link)
    except urllib.error.HTTPError:
        time.sleep(5)
        try:
            results = load_regex(thread_link)
        except urllib.error.HTTPError:
            log.info("%s 404'd", thread_link)
            sys.exit(1)
    except urllib.error.URLError:
        log.warning("Couldn't establish connection!")
        sys.exit(1)

    results_len = len(results)
    # Width of the overall result count in characters for prettier output
    len_width = len(str(results_len))

    # Retries imply attempts after the first try failed
    # So just increase the range by one to include the initial try
    for attempt in range(args.retries+1):
        if attempt > 0:
            log.info("Retrying... (%d out of %d attempts)", attempt, args.retries)
            time.sleep(5)

        count = 1
        try:
            for link, img in results:
                img_path = os.path.join(directory, img)
                if not os.path.exists(img_path):
                    download_file(f"https:{link}", img_path)

                    progress = f"[{count: >{len_width}}/{results_len}]"
                    log.info("%s %s/%s/%s", progress, board, thread, img)
                count += 1
            # Leave attempt loop early if all files were downloaded successfully
            break
        except urllib.error.URLError:
            log.warning("Lost connection!")


def main():
    parse_cli()

    if args.date:
        logging.basicConfig(
            level=logging.INFO,
            format="[%(asctime)s] %(message)s",
            datefmt="%Y-%m-%d %I:%M:%S %p")
    else:
        logging.basicConfig(
            level=logging.INFO,
            format="[%(asctime)s] %(message)s",
            datefmt="%I:%M:%S %p")

    thread = args.thread[0].strip()
    download_thread(thread)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
