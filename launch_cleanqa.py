"""Optional transparent launcher. Uses existing dependencies; never installs packages."""
from pathlib import Path
import importlib.util
import os
import socket
import sys
import threading
import webbrowser


def main():
    root = Path(__file__).resolve().parent
    os.chdir(root)
    sys.dont_write_bytecode = True
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
    sys.path.insert(0, str(root))
    required = ('streamlit', 'numpy', 'lxml', 'openpyxl', 'spylls', 'docx', 'regex')
    missing = [name for name in required if importlib.util.find_spec(name) is None]
    if missing:
        print('Missing dependencies in this Python: ' + ', '.join(missing))
        print('Use a complete, freshly built distribution. No packages were installed automatically.')
        return 1
    with socket.socket() as probe:
        try:
            probe.bind(('127.0.0.1', 5000))
        except OSError:
            probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
    url = f'http://127.0.0.1:{port}'
    print(f'Clean&QA 6.7: {url}\nPress Ctrl+C in this window to stop the app.')
    timer = threading.Timer(2, lambda: webbrowser.open(url))
    timer.daemon = True
    timer.start()
    from streamlit.web import cli
    sys.argv = ['streamlit', 'run', str(root/'app.py'), '--server.address=127.0.0.1',
                f'--server.port={port}', '--server.headless=true', '--browser.gatherUsageStats=false']
    return cli.main()


if __name__ == '__main__':
    raise SystemExit(main())
