"""Trigger and recover the local demo service through its HTTP contract."""

from __future__ import annotations

import argparse
from urllib.request import Request, urlopen


def call(url: str) -> None:
    request = Request(url, method="POST")
    with urlopen(request, timeout=5) as response:
        print(response.read().decode("utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["break", "recover"])
    parser.add_argument("--base-url", default="http://127.0.0.1:9000")
    args = parser.parse_args()
    call(f"{args.base_url.rstrip('/')}/{args.action}")


if __name__ == "__main__":
    main()
