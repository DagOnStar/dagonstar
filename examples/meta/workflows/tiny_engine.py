"""A stand-in "external workflow engine" with no DAGonStar dependency.

    python tiny_engine.py PARAMETERS.json

It reads the JSON parameter document written by the generic ``command``
adapter, counts the words of ``text``, and writes ``results/counts.tsv`` in its
working directory.  It represents any engine that DAGonStar drives through its
command line without modifying it.
"""

import json
import os
import sys
from collections import Counter

parameters = json.load(open(sys.argv[1], encoding="utf-8"))
words = open(parameters["text"], encoding="utf-8").read().lower().split()
os.makedirs("results", exist_ok=True)
with open(os.path.join("results", "counts.tsv"), "w", encoding="utf-8") as stream:
    for word, count in sorted(Counter(words).items(), key=lambda item: (-item[1], item[0]))[:parameters.get("top", 10)]:
        stream.write("%s\t%d\n" % (word, count))
