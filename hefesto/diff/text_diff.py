import difflib


def text_diff(old: str, new: str) -> str:
    lines = difflib.unified_diff(
        old.splitlines(), new.splitlines(),
        fromfile="champion", tofile="candidate", lineterm="",
    )
    return "\n".join(lines)
