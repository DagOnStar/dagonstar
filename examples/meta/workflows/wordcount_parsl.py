"""Unmodified Parsl program: counts words with two Parsl apps.

``main`` composes the apps and returns futures; DAGonStar's driver loads the
Parsl configuration, calls ``main(**inputs)``, and waits for the futures.
"""
from parsl import python_app


@python_app
def read_words(path):
    with open(path, encoding="utf-8") as stream:
        return stream.read().lower().split()


@python_app
def write_counts(words, destination, top):
    import os
    from collections import Counter
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    counts = Counter(words)
    with open(destination, "w", encoding="utf-8") as stream:
        for word, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:top]:
            stream.write("%s\t%d\n" % (word, count))
    return len(counts)


def main(text, top=10):
    distinct = write_counts(read_words(text), "results/counts.tsv", top)
    return {"distinct_words": distinct}


if __name__ == "__main__":
    import sys
    import parsl
    with parsl.load():
        print(main(sys.argv[1]))
