

import os, sys

BASE_NAME = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_NAME)

from core import main

if __name__ == "__main__":
    main.ArgvHandler(sys.argv)