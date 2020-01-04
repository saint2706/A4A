#!/usr/bin/python3

import argparse
import asyncio
import fnmatch
import json
import os
import sys
import time
import urllib.error

from urllib.request import Request, urlopen

import aiohttp


class DownloadableThread():
    """Store thread-related information and handle its processing."""

    def __init__(self, position, link):
        """Initialize thread object."""
        self.pos = position
        self.link = link.split("#")[0]

        info = link.partition(".org/")[2]
        # info has the form <board>/thread/<thread> or <board>/thread/<thread>/<dir name>
        if len(info.split("/")) > 3:
            self.board, _, self.id, self.dir = info.split("/")
        else:
            self.board, _, self.id = info.split("/")
            self.dir = self.id

        self.files = self.gather_files()
        self.count = 0

    def resolve_path(self):
        """Assemble final output path and change the working directory."""
        # This is the fixed directory template
        out_dir = os.path.join(script_path, "downloads", self.board, self.dir)

        if not os.path.exists(out_dir):
            os.makedirs(out_dir)
        os.chdir(out_dir)

    def gather_files(self):
        """Contact 4chan's API to get the names of all files in a thread."""
        api_call = f"https://a.4cdn.org/{self.board}/thread/{self.id}.json"
        # Custom header value is necessary to avoid 403 errors on 4chan.org
        # 4channel works just fine without
        req = Request(api_call, headers={'User-Agent': '4chan Archiver'})
        files = []

        for _ in range(2):
            try:
                with urlopen(req) as resp:
                    resp_json = resp.read()
                    resp_json = json.loads(resp_json)

                files = [f"{p['tim']}{p['ext']}"
                         for p in resp_json['posts'] if 'tim' in p]
                break
            except urllib.error.HTTPError:
                time.sleep(5)
                continue
            except urllib.error.URLError:
                if self.pos == 1:
                    err("Couldn't establish connection!")
                else:
                    err("Lost connection!")
                sys.exit(1)

        return files

    def fetch_progress(self):
        """Return thread-wise and file-wise progress."""
        threads = len(opts.thread)
        files = len(self.files)
        t_width = len(str(threads))
        f_width = len(str(files))

        t_progress = f"[{self.pos: >{t_width}}/{threads}]"
        f_progress = f"[{self.count: >{f_width}}/{files}]"

        if self.count:
            progress = f"{t_progress} {f_progress}"
        else:
            progress = t_progress

        return progress

    async def get_file(self, name, session):
        """Download a single file."""
        if os.path.exists(name):
            self.count += 1
            return

        link = f"https://i.4cdn.org/{self.board}/{name}"
        async with session.get(link) as media:
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

        self.count += 1
        msg(f"{self.fetch_progress()} {self.board}/{self.dir}/{name}")

    async def download(self):
        """Download a thread."""
        if not self.files:
            # In this case the progress line gets printed to stderr
            err(f"{self.fetch_progress()} {self.link}")
            err(f"Thread 404'd!")
            return

        msg(f"{self.fetch_progress()} {self.link}")

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
                    tasks = [self.get_file(f, session) for f in self.files]
                    await asyncio.gather(*tasks)
                # Leave attempt loop early if all files were downloaded successfully
                break
            except aiohttp.ClientConnectionError:
                err("Lost connection!")
                attempt += 1
            finally:
                clean()


def err(*args, **kwargs):
    """Print to stderr."""
    print(f"[{time.strftime('%X')}]", *args, file=sys.stderr, **kwargs)


def msg(*args, **kwargs):
    """Print to stdout."""
    print(f"[{time.strftime('%X')}]", *args, **kwargs)


def parse_cli():
    """Parse the command line arguments with argparse."""
    parser = argparse.ArgumentParser(description="inb4404")
    parser.add_argument(
        "thread", nargs="+",
        help="url of the thread")
    parser.add_argument(
        "-r", "--retries", type=int, default=5,
        help="how often to resume download after thrown errors (N<0 to retry indefinitely)")
    parser.add_argument(
        "--connections", type=int, default=10,
        help="number of connections to use")

    return parser.parse_args()


def clean():
    """Clean output directory of any partially downloaded (.part) files."""
    for f in [f for f in os.listdir() if f.endswith(".part")]:
        os.remove(f)


def main():
    """Run the main function body."""
    # Weed out clearly wrong input
    opts.thread = fnmatch.filter(opts.thread, "*boards.4chan*.org/*/thread/*")

    for i in range(len(opts.thread)):
        thread = DownloadableThread(i+1, opts.thread[i])
        thread.resolve_path()
        asyncio.run(thread.download(), debug=False)


if __name__ == '__main__':
    script_path = os.path.dirname(os.path.realpath(__file__))
    opts = parse_cli()

    try:
        main()
    except KeyboardInterrupt:
        err("User interrupt!")
