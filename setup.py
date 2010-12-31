from setuptools import setup, find_packages
import glob, os
from stat import *

def executable(path):
    st = os.stat(path)[ST_MODE]
    return (st & S_IEXEC) and not S_ISDIR(st)

dependencies = """
Babel
PIL
argparse
CouchDB==0.8
genshi
gunicorn
lxml
psycopg2
pymarc
python-memcached
pyyaml
simplejson
sphinx
supervisor
web.py==0.33
"""

from openlibrary.core.setup_commands import commands

setup(
    name='openlibrary',
    version='2.0',
    description='OpenlibraryBot',
    packages=find_packages(exclude=["ez_setup"]),
    scripts=filter(executable, glob.glob('scripts/*')),
    install_requires=dependencies.split(),
    cmdclass=commands
)

