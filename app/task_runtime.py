from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable


def run_streaming_command(
    command: list[str],
    env: dict[str, str],
    log_path: Path,
    line_callback: Callable[[str], None],
) -> tuple[int, str]:
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        bufsize=1,
    )
    lines: list[str] = []
    if process.stdout is not None:
        for line in process.stdout:
            clean = line.rstrip("\n")
            lines.append(clean)
            line_callback(clean)
    return_code = process.wait()
    output = "\n".join(lines).strip()
    log_path.write_text(output, encoding="utf-8")
    return return_code, output
