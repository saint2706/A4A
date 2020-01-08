#!/usr/bin/python3

import argparse
import asyncio
from base64 import b64decode
import fnmatch
import json
import os
import sys
import time
import textwrap
import urllib.error
from urllib.request import Request, urlopen

import aiohttp


class DefaultOptions:
    """Store defaults for command line options."""

    def __init__(self):
        script_path = os.path.dirname(os.path.realpath(__file__))

        # Base directory
        self.PATH = os.path.join(script_path, "downloads")

        # Whether to use the original filenames or UNIX timestamps
        #   True  -> original filenames
        #   False -> UNIX timestamps
        self.USE_NAMES = False

        # Path to an archive file (holds MD5 hashes of downloaded files)
        self.ARCHIVE = None

        # How many connections to use with aiohttp's ClientSession
        self.CONNECTIONS = 10

        # How often to retry a thread (!) if errors occur
        self.RETRIES = 5


class DownloadableThread:
    """Store thread-related information and handle its processing."""

    def __init__(self, position, link):
        """Initialize thread object."""
        self.count = 0
        self.files = []
        self.pos = position
        self.link = link.split("#")[0]

        info = link.partition(".org/")[2]
        # info has the form <board>/thread/<thread> or <board>/thread/<thread>/<dir name>
        if len(info.split("/")) > 3:
            self.board, _, self.id, self.dir = info.split("/")
        else:
            self.board, _, self.id = info.split("/")
            self.dir = self.id

        resp_json = self.get_json()
        if not resp_json:
            return

        self.files = [
            {
                'link': f"https://i.4cdn.org/{self.board}/{p['tim']}{p['ext']}",
                'name': f"{p['filename'] if opts.names else p['tim']}{p['ext']}",
                'md5': b64decode(p['md5']).hex(),
            } for p in resp_json['posts'] if 'tim' in p
        ]

    def resolve_path(self):
        """Assemble final output path and change the working directory."""
        # This is the fixed directory template
        out_dir = os.path.join(opts.base_dir, self.board, self.dir)

        if not os.path.exists(out_dir):
            os.makedirs(out_dir)
        os.chdir(out_dir)

    def get_json(self):
        """Contact 4chan's API to get the names of all files in a thread."""
        api_call = f"https://a.4cdn.org/{self.board}/thread/{self.id}.json"
        # Custom header value is necessary to avoid 403 errors on 4chan.org
        # 4channel works just fine without
        req = Request(api_call, headers={'User-Agent': '4chan Archiver'})
        resp_json = None

        for _ in range(2):
            try:
                with urlopen(req) as resp:
                    resp_json = resp.read()
                    resp_json = json.loads(resp_json)
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

        return resp_json

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

    async def get_file(self, link, name, md5, session):
        """Download a single file."""
        if os.path.exists(name) or opts.archive and check_hash(md5):
            self.count += 1
            return

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

        if opts.archive:
            log_hash(md5)
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
                    tasks = [self.get_file(f['link'], f['name'], f['md5'], session)
                             for f in self.files]
                    await asyncio.gather(*tasks)
                # Leave attempt loop early if all files were downloaded successfully
                break
            except aiohttp.ClientConnectionError:
                err("Lost connection!")
                attempt += 1
            except aiohttp.ClientPayloadError:
                err("Malformed or missing chunk!")
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
    defaults = DefaultOptions()

    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawTextHelpFormatter,
        description="A4A is a Python script to download all files from 4chan(nel) threads."
    )
    parser.add_argument(
        "thread", nargs="+",
        help="url of the thread")
    parser.add_argument(
        "-f", "--filenames", dest="names", action="store_const",
        const=True, default=defaults.USE_NAMES,
        help="use original filenames instead of UNIX timestamps"
    )
    parser.add_argument(
        "-p", "--path", default=defaults.PATH, metavar="PATH", dest="base_dir",
        help="set output directory (def: %(default)s)"
    )
    parser.add_argument(
        "-a", "--archive", metavar="FILE", dest="archive", default=defaults.ARCHIVE,
        help="keep track of downloaded files by logging MD5 hashes"
    )
    parser.add_argument(
        "--connections", type=int, metavar="N", default=defaults.CONNECTIONS,
        help="number of connections to use (def: %(default)s)")
    parser.add_argument(
        "--retries", type=int, metavar="N", default=defaults.RETRIES,
        help=textwrap.dedent("""\
            how often to retry a thread if errors occur (def: %(default)s)
              %(metavar)s<0 to retry indefinitely (not recommended)""")
    )

    args = parser.parse_args()
    # Make sure base_dir is an absolute path
    args.base_dir = os.path.abspath(args.base_dir)
    # Read archive content into separate var
    if args.archive:
        args.archive = os.path.abspath(args.archive)
        try:
            with open(args.archive, "r") as f:
                _ = f.read(1)
        except FileNotFoundError:
            pass
        except (OSError, UnicodeError):
            err(f"'{args.archive}' is not a valid archive!")
            args.archive = None

    return args


def check_hash(md5):
    """Test archive for existence of a file's hash."""
    try:
        with open(opts.archive, "r") as f:
            content = [l.strip() for l in f]
    except FileNotFoundError:
        return False

    return bool(md5 in content)


def log_hash(md5):
    """Log file's hash in the archive."""
    with open(opts.archive, "a") as f:
        print(md5, file=f)


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
    opts = parse_cli()

    try:
        main()
    except KeyboardInterrupt:
        err("User interrupt!")
