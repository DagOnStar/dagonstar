"""Lesson 11: run the deterministic local LLM-task example."""
import sys
from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))
from examples.tutorial.lesson_12_llm_tasks import main

if __name__ == "__main__":
    main()
