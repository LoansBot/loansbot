import os
import sys

curdir = os.getcwd()

if os.path.split(curdir)[1] == 'tests':
    os.chdir(os.path.split(os.getcwd())[0])


if 'src' not in sys.path:
    sys.path.append('src')
