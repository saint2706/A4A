# A4A

A4A is a Python script to download all images/videos of a 4chan thread.

## This fork

The goal of A4A ("Asyncio 4chan Archiver" or "Async 4 Archiving" depending on how much the reader cares about the 4chan API ToS) is the provide a simple and easy to use script to archive 4chan threads. This script will be geared towards people, who want to download all media from an already archived thread or don't mind to run it again to catch any files posted in the meantime.

## Usage

```
usage: inb4404.py [-h] [-r N] [--connections N] thread

positional arguments:
  thread              url of the thread

optional arguments:
  -h, --help          show this help message and exit
  -r, --retries N     how often to resume download after thrown errors
                        (N<0 to retry indefinitely)  
  --connections N     number of connections to use
```
