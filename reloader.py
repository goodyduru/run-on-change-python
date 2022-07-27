import os
import subprocess
import sys
import threading
import time
from pathlib import PurePath

import hello


_ignore_common_dirs = {
    "__pycache__",
    ".git",
    ".hg",
    ".tox",
    ".nox",
    ".pytest_cache",
    ".mypy_cache",
}

def get_prefix():
    return {sys.base_exec_prefix, sys.base_prefix, sys.prefix, sys.exec_prefix}


def get_module_path():
    for module in list(sys.modules.values()):
        name = getattr(module, '__file__', None)
        if name is None:
            continue

        while not os.path.isfile(name):
            old = name
            name = os.path.dirname(name)

            if old == name:
                break
        else:
            yield name


def find_common_roots(paths):
    root = {}

    for chunks in sorted((PurePath(x).parts for x in paths), key=len, reverse=True):
        node = root
        for chunk in chunks:
            node = node.setdefault(chunk, {})
        node.clear()
    
    rv = set()

    def _walk(node, path):
        for prefix, child in node.items():
            _walk(child, path+(prefix, ))
        
        if not node:
            rv.add(os.path.join(*path))
    return rv


def find_path():
    paths = set()
    ignore_files = tuple(get_prefix())
    for path in list(sys.path):
        path = os.path.abspath(path)
        
        if os.path.isfile(path):
            paths.add(path)
            continue
            
        parent_has_py = {os.path.dirname(path): True}

        for root, dirs, files in os.walk(path):

            if root.startswith(ignore_files) or os.path.basename(root) in _ignore_common_dirs:
                dirs.clear()
                continue

            has_py = False

            for name in files:
                if name.endswith(('.py', '.pyc')):
                    has_py = True
                    paths.add(os.path.join(root, name))
            
            if not (has_py or parent_has_py[os.path.dirname(root)]):
                dirs.clear()
                continue

            parent_has_py[root] = has_py
        
    paths.update(get_module_path())
    return paths


def get_args():
    rv = [sys.executable]
    py_script = sys.argv[0]
    args = sys.argv[1:]
    __main__ = sys.modules['__main__']
    py_script = os.path.abspath(py_script)
    rv.append(py_script)
    rv.extend(args)
    return rv


class Reloader:
    def __init__(self, interval=1) -> None:
        self.interval = interval
    
    def __enter__(self):
        self.mtimes = {}
        self.run_step()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def run(self):
        while True:
            self.run_step()
            time.sleep(self.interval)
    
    def run_step(self):
        for name in find_path():
            try:
                mtime = os.stat(name).st_mtime
            except OSError:
                continue

            old_time = self.mtimes.get(name)

            if old_time is None:
                self.mtimes[name] = mtime
                continue

            if mtime > old_time:
                self.trigger_reload(name)
    
    def restart_with_reloader(self):
        while True:
            args = get_args()
            new_environ = os.environ.copy()
            new_environ['reloader_run'] = "true"
            exit_code = subprocess.call(args, env=new_environ, close_fds=False)

            if exit_code != 3:
                return exit_code
    
    def trigger_reload(self, name):
        print(f"Detected changes in {os.path.abspath(name)}, reloading")
        sys.exit(3)


def ensure_echo_on():
    import termios

    attributes = termios.tcgetattr(sys.stdin)

    if not attributes[3] & termios.ECHO:
        attributes[3] |= termios.ECHO
        termios.tcsetattr(sys.stdin, termios.TCSANOW, attributes)


def run():
    print("Running the programs")


def run_with_reload(main_func):
    import signal

    signal.signal(signal.SIGTERM, lambda *args: sys.exit(0))
    reloader = Reloader()

    try:
        if os.environ.get("reloader_run") == "true":
            ensure_echo_on()
            print("Hi you!")
            t = threading.Thread(target=run, args=())
            t.daemon = True
            with reloader:
                t.start()
                reloader.run()
        else:
            sys.exit(reloader.restart_with_reloader())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    run_with_reload(run)

