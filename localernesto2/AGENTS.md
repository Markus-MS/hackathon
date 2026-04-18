All generated code and scripts in Python must handle dependencies via UV. Bundle all dependencies via /// script header uv provides. An example of this is:

#!/usr/bin/env -S uv run --script
#
# /// script
# dependencies = [
#   "pwntools",
# ]
# ///

def main():
    print("Code")

if __name__ == "__main__":
    main()

All generated scripts can be tested by you (the AI agent) by just running the executable script with `./script`. Requires `script` to be executable and `uv` installed.
