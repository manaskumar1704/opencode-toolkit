"""Sentinel-block upserting: OCTK-managed regions survive user edits.

Auto-managed text is wrapped in ``<!-- OCTK:START --> ... <!-- OCTK:END -->``.
Upserting replaces *only* the text between those markers, leaving everything
outside byte-for-byte untouched. A file without markers is (re)created whole.
"""

from __future__ import annotations

from pathlib import Path

SENTINEL_START = "<!-- OCTK:START -->"
SENTINEL_END = "<!-- OCTK:END -->"


def _inner_block(text: str) -> str:
    """Return the text between the sentinel markers, or the whole text if absent."""
    start = text.find(SENTINEL_START)
    end = text.find(SENTINEL_END)
    if start == -1 or end == -1 or end <= start:
        return text
    return text[start + len(SENTINEL_START) : end]


def upsert_in_text(text: str, new_content: str) -> str:
    """Return ``text`` with its sentinel block replaced by ``new_content``'s block.

    When ``text`` has both markers, only the block between them changes and all
    surrounding user text is preserved. When it has none, ``new_content`` is
    returned verbatim (full replace of a legacy/unmanaged file).
    """
    new_block = _inner_block(new_content)
    start = text.find(SENTINEL_START)
    end = text.find(SENTINEL_END)
    if start != -1 and end != -1 and end > start:
        block_start = start + len(SENTINEL_START)
        if text[block_start:end] == new_block:
            return text
        return text[:block_start] + new_block + text[end:]
    return new_content


def upsert_sentinel_block(file_path: Path, new_content: str) -> bool:
    """Ensure ``file_path`` carries ``new_content``'s sentinel block.

    Returns ``True`` when the file changed, ``False`` when already up-to-date.
    User text outside the markers is always preserved.
    """
    if file_path.exists():
        text = file_path.read_text(encoding="utf-8")
        updated = upsert_in_text(text, new_content)
        if updated == text:
            return False
        file_path.write_text(updated, encoding="utf-8")
        return True
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(new_content, encoding="utf-8")
    return True
