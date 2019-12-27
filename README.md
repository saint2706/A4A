# A4A

A4A (*Asyncio 4chan Archiver* or *Asyncio 4 Archiving*, depending on how much the reader cares about the 4chan API ToS) is a Python script to download all images/videos of a 4chan thread.

## Usage

```
usage: inb4404.py [-h] [-r N] [--connections N] thread

positional arguments:
  thread              url of the thread

optional arguments:
  -h, --help          show this help message and exit
  -r, --retries N     how often to resume download after thrown errors (default: 5)
                        (N<0 to retry indefinitely)  
  --connections N     number of connections to use (default: 10)
```

## Requirements

Python >= 3.7

[aiohttp](https://aiohttp.readthedocs.io/en/stable/)

## Paths

Like Exceen's original version there's a fixed output path:

```
<path to inb4404.py>/downloads/<board>/<directory name>
```

`<directory name>` is the only variable component from a user's perspective (apart from changing the script's location) and can be set by adding the desired name to the thread link with a leading "/". If no particular name is requested, the directory name will default to the thread number.

For example:

```
https://boards.4channel.org/abc/thread/12345678        -> <path to inb4404.py>/downloads/abc/12345678
https://boards.4channel.org/abc/thread/12345678/my_dir -> <path to inb4404.py>/downloads/abc/my_dir
```