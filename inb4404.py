#!/usr/bin/python3

import argparse
import asyncio
from base64 import b64decode
import fnmatch
import json
import os
import sys
import time
from textwrap import dedent
import urllib.error
from urllib.request import Request, urlopen

import aiohttp

# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# Classes
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~

class DefaultOptions:
    """Store defaults for command line options."""

    def __init__(self):
        script_path = os.path.dirname(os.path.realpath(__file__))

        # Verbosity of the terminal output
        #  <0 -> really quiet mode (no output at all)
        #   0 -> quiet mode (errors/warnings only)
        #   1 -> default mode (0 + basic progress information)
        self.VERBOSITY = 1

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
        #   N>0 -> retry N times
        #   N=0 -> disable
        #   N<0 -> retry indefinitely (not recommended)
        self.RETRIES = 5


class CustomArgumentParser(argparse.ArgumentParser):
    """Override ArgumentParser's automatic help text."""

    def format_help(self):
        """Return custom help text."""
        help_text = dedent(f"""\
        A4A is a Python script to download all files from 4chan(nel) threads.

        Usage: {self.prog} [OPTIONS] THREAD [THREAD]...

        Thread:
          4chan(nel) thread URL

        Options:
          -h, --help          show help
          -q, --quiet         suppress non-error output
          -p, --path PATH     set output directory (def: {self.get_default("base_dir")})
          -f, --filenames     use original filenames instead of UNIX timestamps
          -a, --archive FILE  keep track of downloaded files by logging MD5 hashes
          --connections N     number of connections to use (def: {self.get_default("connections")})
          --retries N         how often to retry a thread if errors occur (def: {self.get_default("retries")})
                                N<0 to retry indefinitely (not recommended)
        """)

        return help_text


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
        if os.path.exists(name) or md5 in opts.archived_md5:
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

# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# Functions
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~

def err(*args, level=0, **kwargs):
    """Print to stderr."""
    if level <= opts.verbosity:
        print(f"[{time.strftime('%X')}]", *args, file=sys.stderr, **kwargs)


def msg(*args, level=1, **kwargs):
    """Print to stdout."""
    if level <= opts.verbosity:
        print(f"[{time.strftime('%X')}]", *args, **kwargs)


def positive_int(string):
    """Convert string provided by argparse to a positive int."""
    try:
        value = int(string)
        if value <= 0:
            raise ValueError
    except ValueError:
        error = f"invalid positive int value: {string}"
        raise argparse.ArgumentTypeError(error)

    return value


def valid_archive(string):
    """Convert string provided by argparse to an archive path."""
    path = os.path.abspath(string)
    try:
        with open(path, "r") as f:
            _ = f.read(1)
    except FileNotFoundError:
        pass
    except (OSError, UnicodeError):
        error = f"{path} is not a valid archive!"
        raise argparse.ArgumentTypeError(error)

    return path


def parse_cli():
    """Parse the command line arguments with argparse."""
    defaults = DefaultOptions()
    parser = CustomArgumentParser(usage="%(prog)s [OPTIONS] THREAD [THREAD]...")

    parser.add_argument("thread", nargs="+", help="thread URL")
    parser.add_argument(
        "-q", "--quiet", dest="verbosity", action="store_const",
        const=0, default=defaults.VERBOSITY
    )
    parser.add_argument("-p", "--path", dest="base_dir", default=defaults.PATH)
    parser.add_argument(
        "-f", "--filenames", dest="names", action="store_true",
        default=defaults.USE_NAMES
    )
    parser.add_argument(
        "-a", "--archive", dest="archive", type=valid_archive,
        default=defaults.ARCHIVE
    )
    parser.add_argument(
        "--connections", type=positive_int, default=defaults.CONNECTIONS
    )
    parser.add_argument("--retries", type=int, default=defaults.RETRIES)

    args = parser.parse_args()
    # Make sure base_dir is an absolute path
    args.base_dir = os.path.abspath(args.base_dir)
    # Weed out clearly wrong thread URLs
    args.thread = fnmatch.filter(args.thread, "*boards.4chan*.org/*/thread/*")

    return args


def reload_archive():
    """Re-read archive for each new thread."""
    if not (opts.archive and os.path.exists(opts.archive)):
        content = []
    else:
        with open(opts.archive, "r") as f:
            content = [l.strip() for l in f]

    return content


def log_hash(md5):
    """Log file's hash in the archive."""
    with open(opts.archive, "a") as f:
        print(md5, file=f)


def clean():
    """Clean output directory of any partially downloaded (.part) files."""
    for f in [f for f in os.listdir() if f.endswith(".part")]:
        os.remove(f)

# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# Main Function
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~

def main():
    """Run the main function body."""
    for i, url in enumerate(opts.thread, start=1):
        opts.archived_md5 = reload_archive()
        thread = DownloadableThread(i, url)
        thread.resolve_path()
        asyncio.run(thread.download(), debug=False)


if __name__ == '__main__':
    opts = parse_cli()

    try:
        main()
    except KeyboardInterrupt:
        err("User interrupt!")
