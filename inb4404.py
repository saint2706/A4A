#!/usr/bin/python3

import argparse
import json
import logging
import os
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
        "-r", "--retries", type=int, default=5,
        help="how often to resume download after thrown errors")

    args = parser.parse_args()


def parse_thread(url):
    # Custom header value is necessary to avoid 403 errors on 4chan.org
    # 4channel works just fine without
    req = Request(url, headers={'User-Agent': '4chan Archiver'})
    with urlopen(req) as resp:
        resp_json = resp.read()
        resp_json = json.loads(resp_json)

    files = [f"{p['tim']}{p['ext']}" for p in resp_json['posts'] if 'tim' in p]

    return files


def download_file(board, name):
    url = f"https://i.4cdn.org/{board}/{name}"
    with urlopen(url) as content, open(name, "wb") as f:
        f.write(content.read())


def download_thread(link):
    link = link.split("#")[0]
    info = link.partition(".org/")[2]
    # info has the form <board>/thread/<thread> or <board>/thread/<thread>/<dir name>
    if len(info.split("/")) > 3:
        board, _, thread_id, dir_name = info.split("/")
    else:
        board, _, thread_id = info.split("/")
        dir_name = thread_id

    out_dir = os.path.join(workpath, "downloads", board, dir_name)
    if not os.path.exists(out_dir):
        os.makedirs(out_dir)
    os.chdir(out_dir)

    api_call = f"https://a.4cdn.org/{board}/thread/{thread_id}.json"
    try:
        files = parse_thread(api_call)
    except urllib.error.HTTPError:
        time.sleep(5)
        try:
            files = parse_thread(api_call)
        except urllib.error.HTTPError:
            log.info("%s 404'd", link)
            sys.exit(1)
    except urllib.error.URLError:
        log.warning("Couldn't establish connection!")
        sys.exit(1)

    file_count = len(files)
    # Width of the overall file count in characters for prettier output
    width = len(str(file_count))

    # Retries imply attempts after the first try failed
    # So just increase the range by one to include the initial try
    for attempt in range(args.retries+1):
        if attempt > 0:
            log.info("Retrying... (%d out of %d attempts)", attempt, args.retries)
            time.sleep(5)

        count = 1
        try:
            for f in files:
                if not os.path.exists(f):
                    download_file(board, f)
                    progress = f"[{count: >{width}}/{file_count}]"
                    log.info("%s %s/%s/%s", progress, board, thread_id, f)
                count += 1
            # Leave attempt loop early if all files were downloaded successfully
            break
        except urllib.error.URLError:
            log.warning("Lost connection!")


def main():
    parse_cli()

    logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(message)s",
                        datefmt="%I:%M:%S %p")

    thread = args.thread[0].strip()
    download_thread(thread)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
