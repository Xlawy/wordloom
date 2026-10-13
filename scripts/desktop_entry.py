"""Packaging entrypoint. Source launch remains python -m wordloom."""
from wordloom.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
