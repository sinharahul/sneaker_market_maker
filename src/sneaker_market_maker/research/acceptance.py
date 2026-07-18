from pathlib import Path


def verify_acceptance(checklist: Path) -> None:
    text = checklist.read_text()
    for number in range(1, 15):
        criterion = f"AC-{number:02d}"
        if f"- [x] {criterion}" not in text:
            raise AssertionError(f"{criterion} is not checked")
        section = text.split(f"- [x] {criterion}", maxsplit=1)[1].split("- [x]", maxsplit=1)[0]
        for field in ("command:", "artifact:", "result:"):
            value = next(
                (
                    line.split(field, maxsplit=1)[1].strip()
                    for line in section.splitlines()
                    if field in line
                ),
                "",
            )
            if not value:
                raise AssertionError(f"{criterion} missing {field[:-1]}")
