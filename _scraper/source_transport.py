"""Bounded retries for interrupted read-only HTTP responses, never rate limits."""
import time
import requests


def interrupted_get(get, url, **kwargs):
    for attempt in range(4):
        try:
            return get(url, **kwargs)
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError,
                requests.exceptions.ChunkedEncodingError):
            if attempt == 3:
                raise
            time.sleep((3, 10, 30)[attempt])
