import os
from setuptools import setup, find_packages

def read(fname):
  return open(os.path.join(os.path.dirname(__file__), fname)).read()

setup(
  name = "mlt-serato-tags",
  version = "1.0.1",
  author = "Jan Holthuis",
  author_email = "holthuis.jan@googlemail.com",
  description = ("Serato DJ Pro GEOB tags documentation"),
  license = "MIT",
  url = "https://github.com/eidoriantan/serato-tags",
  packages=find_packages(),
  long_description=read('README.md'),
  classifiers=[
    "Programming Language :: Python :: 3",
    "Operating System :: OS Independent",
  ]
)
