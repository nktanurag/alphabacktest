"""Document Q&A: upload PDFs, ask questions, get the best-matching passages and a generated answer.

A separate system from the backtester. It has its own database, tables and config, and is
only mounted into the same FastAPI app and web UI. See docs/DOCQA.md.
"""
