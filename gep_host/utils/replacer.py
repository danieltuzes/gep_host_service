import subprocess
import sys


def LowerPriorityPopen(cmd, shell=False, cwd=None, stdout=None, stderr=None):
    if sys.platform.startswith('linux') or sys.platform.startswith('darwin'):
        cmd = ['nice', '-n', '10'] + \
            cmd if isinstance(cmd, list) else f"nice -n 10 {cmd}"
        print(f"Create a new detached process with lower priority: {cmd}",
              flush=True, file=stdout)
    elif sys.platform.startswith('win'):
        try:
            import win32process
            import win32con
            print(f"Create a new detached process with lower priority: {cmd}",
                  flush=True, file=stdout)
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

            process = subprocess.Popen(cmd, shell=shell, cwd=cwd,
                                       stdout=stdout,
                                       stderr=stderr,
                                       startupinfo=startupinfo)
            win32process.SetPriorityClass(process._handle,
                                          win32con.IDLE_PRIORITY_CLASS)
            return process
        except ImportError:
            print("pywin32 module is not installed.",
                  f"Running the command with normal priority: {cmd}",
                  flush=True, file=stdout)
            # Fall back to normal subprocess call without priority modification

    return subprocess.Popen(cmd, shell=shell, cwd=cwd, stdout=stdout, stderr=stderr)
