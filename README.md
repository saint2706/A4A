# 4chan-archiver

4chan-archiver is a Python script to download all images/videos of a 4chan thread.

## This fork

The goal of 4chan-archiver (as I call this fork unofficially) is the provide a simple and easy to use script to archive 4chan threads. This script will be geared towards people, who want to download all media from an already archived thread or don't mind to run it again to catch any files posted in the meantime.

## Usage

```
usage: inb4404.py [-h] [-d] [-n] [-r N] thread

positional arguments:
  thread              url of the thread

optional arguments:
  -h, --help          show this help message and exit
  -d, --date          show date as well
  -n, --use-names     use thread names instead of the thread ids
  -r, --retries N     how often to resume download after thrown errors
```
