import os
import sys

curdir = os.getcwd()

if os.path.split(curdir)[1] == 'tests':
    print(f'cwd was={os.getcwd()}')
    os.chdir(os.path.split(os.getcwd())[0])
    print(f'cwd={os.getcwd()}')


if 'src' not in sys.path:
    sys.path.append('src')
