"""The `cookierookie` command that `pip install` creates.

It runs main.py exactly like `python main.py ...`, so both take the same arguments:
    cookierookie --interactive
    cookierookie "Your bug description"
"""
import os
import runpy


def main():
    # So the help shows "cookierookie ..." instead of "python main.py ..."
    os.environ.setdefault("COOKIEROOKIE_PROG", "cookierookie")
    # alter_sys: main.py sees sys.argv[0] and __file__ as if it had been started directly
    runpy.run_module("main", run_name="__main__", alter_sys=True)


if __name__ == "__main__":
    main()
