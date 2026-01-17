from pathlib import Path

import pytest

from agentc.core.config import BACKUP_SUFFIX, TEMP_SUFFIX
from agentc.core.patching import transaction
from agentc.core.patching.errors import PatchTransactionError


def test_apply_updates_transactionally_rolls_back(tmp_path: Path, monkeypatch) -> None:
    file_one = tmp_path / "one.txt"
    file_two = tmp_path / "two.txt"
    file_one.write_text("one\n", encoding="utf-8")
    file_two.write_text("two\n", encoding="utf-8")

    updates = {
        file_one: "ONE\n",
        file_two: "TWO\n",
    }

    original_write = transaction.write_text_atomic

    def flaky_write(path: Path, content: str, *, temp_suffix: str) -> None:
        if path.name == "two.txt":
            raise PatchTransactionError("boom")
        original_write(path, content, temp_suffix=temp_suffix)

    monkeypatch.setattr(transaction, "write_text_atomic", flaky_write)

    with pytest.raises(PatchTransactionError):
        transaction.apply_updates_transactionally(
            updates,
            backup_suffix=BACKUP_SUFFIX,
            temp_suffix=TEMP_SUFFIX,
        )

    assert file_one.read_text(encoding="utf-8") == "one\n"
    assert file_two.read_text(encoding="utf-8") == "two\n"
    assert list(tmp_path.glob(f"one.txt{BACKUP_SUFFIX}.*"))
    assert list(tmp_path.glob(f"two.txt{BACKUP_SUFFIX}.*"))
