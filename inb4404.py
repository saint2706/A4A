#!/usr/bin/python3

import argparse
import json
import os
import sys
import time

import urllib.error
from urllib.request import Request, urlopen

import asyncio
import aiohttp

workpath = os.path.dirname(os.path.realpath(__file__))
opts = None
count = 0


def err(*args, **kwargs):
    """Print to stderr."""
    print(f"[{time.strftime('%X')}]", *args, file=sys.stderr, **kwargs)


def msg(*args, **kwargs):
    """Print to stdout."""
    print(f"[{time.strftime('%X')}]", *args, **kwargs)


def parse_cli():
    global opts

    parser = argparse.ArgumentParser(description="inb4404")
    parser.add_argument(
        "thread", nargs=1,
        help="url of the thread")
    parser.add_argument(
        "-r", "--retries", type=int, default=5,
        help="how often to resume download after thrown errors (N<0 to retry indefinitely)")
    parser.add_argument(
        "--connections", type=int, default=10,
        help="number of connections to use")

    opts = parser.parse_args()


def parse_thread(url):
    # Custom header value is necessary to avoid 403 errors on 4chan.org
    # 4channel works just fine without
    req = Request(url, headers={'User-Agent': '4chan Archiver'})
    with urlopen(req) as resp:
        resp_json = resp.read()
        resp_json = json.loads(resp_json)

    files = [f"{p['tim']}{p['ext']}" for p in resp_json['posts'] if 'tim' in p]

    return files


async def download_file(board, dir_name, name, file_count, session):
    global count

    if os.path.exists(name):
        count += 1
        return

    url = f"https://i.4cdn.org/{board}/{name}"
    async with session.get(url) as media:
        # Open file initially with .part suffix
        with open(f"{name}.part", "wb") as f:
            while True:
                chunk = await media.content.read(1024)
                if not chunk:
                    break
                f.write(chunk)

    # Remove .part suffix once complete
    # After this point file won't get removed if script gets interrupted
    os.rename(f"{name}.part", name)

    count += 1
    progress = f"[{count: >{len(str(file_count))}}/{file_count}]"
    msg(f"{progress} {board}/{dir_name}/{name}")


async def download_thread(link):
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
            err(f"{link} 404'd!")
            sys.exit(1)
    except urllib.error.URLError:
        err("Couldn't establish connection!")
        sys.exit(1)

    tout = aiohttp.ClientTimeout(total=None)
    conn = aiohttp.TCPConnector(limit=opts.connections)
    # Retries imply attempts after the first try failed
    # So the max. number of attempts is opts.retries+1
    attempt = 0
    while attempt <= opts.retries or opts.retries < 0:
        if attempt > 0:
            err(f"Retrying... ({attempt} out of "
                f"{opts.retries if opts.retries > 0 else 'Inf'} attempts)")
            time.sleep(5)

        try:
            async with aiohttp.ClientSession(timeout=tout, connector=conn) as session:
                tasks = [download_file(board, dir_name, f, len(files), session) for f in files]
                await asyncio.gather(*tasks)
            # Leave attempt loop early if all files were downloaded successfully
            break
        except aiohttp.ClientConnectionError:
            err("Lost connection!")
            attempt += 1
        finally:
            clean()


def clean():
    """Clean output directory of any partially downloaded (.part) files."""
    for f in [f for f in os.listdir() if f.endswith(".part")]:
        os.remove(f)


def main():
    parse_cli()
    thread = opts.thread[0].strip()
    asyncio.run(download_thread(thread), debug=False)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
