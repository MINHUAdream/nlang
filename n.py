"""n language command-line entry point.

`.n` sources use the native RTM frontend.  Historical command forms are still
forwarded to tl so the migration does not break the existing regression chain.
"""

from __future__ import annotations

from pathlib import Path
import sys


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if args and not args[0].startswith("-") and Path(args[0]).suffix.lower() == ".n":
        from n_run import main as rtm_main

        return rtm_main(args)
    from tl import main as tl_main

    return tl_main(args if argv is not None else None)


if __name__ == "__main__":
    sys.exit(main())
