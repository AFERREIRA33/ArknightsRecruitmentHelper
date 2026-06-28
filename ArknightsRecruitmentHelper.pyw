from pathlib import Path
import os

from arkrecruit.app import main


if __name__ == "__main__":
    os.chdir(Path(__file__).resolve().parent)
    main()

