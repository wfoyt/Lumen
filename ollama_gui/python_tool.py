"""Bundled MCP Python execution in a disposable bubblewrap sandbox."""
import asyncio
import os
from pathlib import Path
import shutil
import signal
import tempfile

from mcp.server.fastmcp import FastMCP

MAX_OUTPUT_BYTES = 64000

RUNNER = """import resource, runpy, sys
resource.setrlimit(resource.RLIMIT_CPU, (30, 30))
resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
resource.setrlimit(resource.RLIMIT_FSIZE, (8 * 1024 * 1024, 8 * 1024 * 1024))
resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
resource.setrlimit(resource.RLIMIT_NPROC, (32, 32))
runpy.run_path(sys.argv[1], run_name='__main__')
"""


async def execute_python(code: str, filename: str = "main.py", timeout_seconds: int = 20) -> dict:
    """Run a Python file for math, statistics, or data processing. Supply its source
    in code; print results to stdout. Standard-library modules (math, statistics,
    decimal, fractions, etc.) are available. No network, home-directory access,
    interactive input, or third-party libraries. Files in /work are temporary.
    """
    if not code.strip() or len(code.encode("utf-8")) > 100000:
        raise ValueError("Provide nonempty Python source up to 100 KB.")
    if Path(filename).name != filename or not filename.endswith(".py") or filename == "_runner.py":
        raise ValueError("Use a simple Python filename, such as calculation.py.")
    if not 1 <= timeout_seconds <= 30:
        raise ValueError("Use a timeout between 1 and 30 seconds.")
    flatpak = Path("/.flatpak-info").exists()
    launcher = shutil.which("flatpak-spawn" if flatpak else "bwrap")
    if not launcher:
        if flatpak:
            raise RuntimeError("Python execution needs the Flatpak sandbox portal (flatpak-spawn).")
        raise RuntimeError("Python execution needs bubblewrap. Install it with: sudo dnf install bubblewrap")
    with tempfile.TemporaryDirectory(prefix="ollama-python-") as directory:
        work = Path(directory)
        (work / filename).write_text(code, encoding="utf-8")
        (work / "_runner.py").write_text(RUNNER, encoding="utf-8")
        command = [launcher, "--unshare-all", "--die-with-parent", "--new-session",
                   "--ro-bind", "/usr", "/usr", "--proc", "/proc", "--dev", "/dev",
                   "--tmpfs", "/tmp", "--bind", directory, "/work", "--chdir", "/work",
                   "--clearenv", "--setenv", "PATH", "/usr/bin", "--setenv", "HOME", "/tmp",
                   "--setenv", "PYTHONIOENCODING", "utf-8"]
        for path in ("/lib", "/lib64"):
            if Path(path).exists():
                command.extend(["--ro-bind", path, path])
        command.extend(["/usr/bin/python3", "-I", "-S", "/work/_runner.py", f"/work/{filename}"])
        # Flatpak blocks creating nested user namespaces. Ask its portal for a
        # fresh, stricter sandbox instead, forwarding only the script descriptor.
        # No host-spawn permission, app data or document grants are passed on.
        script_fd = None
        if flatpak:
            script_fd = os.open(work / filename, os.O_RDONLY)
            command = [launcher, "--sandbox", "--no-network", "--watch-bus", "--clear-env",
                       "--env=HOME=/tmp", "--env=PATH=/usr/bin", "--env=PYTHONIOENCODING=utf-8",
                       "--directory=/tmp", f"--forward-fd={script_fd}",
                       "/usr/bin/python3", "-I", "-S", "-c", RUNNER, f"/proc/self/fd/{script_fd}"]
        try:
            process = await asyncio.create_subprocess_exec(*command, stdin=asyncio.subprocess.DEVNULL,
                                                       stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                                                       start_new_session=True,
                                                       pass_fds=() if script_fd is None else (script_fd,))
        finally:
            if script_fd is not None:
                os.close(script_fd)
        buffers = [bytearray(), bytearray()]
        output_limited = False
        def kill():
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        async def read(stream, buffer):
            nonlocal output_limited
            while chunk := await stream.read(8192):
                remaining = max(0, MAX_OUTPUT_BYTES - sum(map(len, buffers)))
                buffer.extend(chunk[:remaining])
                if len(chunk) > remaining:
                    output_limited = True
                    kill()
        readers = [asyncio.create_task(read(process.stdout, buffers[0])), asyncio.create_task(read(process.stderr, buffers[1]))]
        timed_out = False
        try:
            try:
                async with asyncio.timeout(timeout_seconds):
                    await process.wait()
                    await asyncio.gather(*readers)
            except TimeoutError:
                timed_out = True
                kill()
                await process.wait()
                await asyncio.gather(*readers, return_exceptions=True)
        except BaseException:
            kill()
            await process.wait()
            for reader in readers:
                reader.cancel()
            await asyncio.gather(*readers, return_exceptions=True)
            raise
        return {"filename": filename, "exit_code": process.returncode,
                "stdout": buffers[0].decode("utf-8", errors="replace"),
                "stderr": buffers[1].decode("utf-8", errors="replace"),
                "timed_out": timed_out, "output_limited": output_limited}


def create_server():
    server = FastMCP("Python")
    server.tool()(execute_python)
    return server


if __name__ == "__main__":
    create_server().run()
