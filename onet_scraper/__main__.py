"""`python -m onet_scraper`.

The guard matters more than it looks. Without it, importing this module runs the
whole CLI - and the CI job that imports every module to prove none of them is
broken was therefore running the full scraper against O*NET on every push, for
minutes, silently. `python -m` still works: the runtime sets __name__ to
"__main__" for the module it executes, so the guard is true exactly when it
should be.
"""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
