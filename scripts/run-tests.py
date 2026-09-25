"""Run every offline regression test, also in an isolated embedded Python."""
import sys
import unittest
from pathlib import Path


def deny_network(event, args):
    # Mocks stay usable; an accidental real connection or DNS lookup fails.
    if event in {
        'socket.connect', 'socket.bind', 'socket.getaddrinfo',
        'socket.gethostbyname', 'socket.gethostbyaddr',
        'socket.sendto', 'socket.sendmsg',
    }:
        raise RuntimeError('Network access is forbidden in offline regression tests')


sys.addaudithook(deny_network)
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'src'))
result = unittest.TextTestRunner(verbosity=2).run(
    unittest.defaultTestLoader.discover(str(root / 'tests'))
)
raise SystemExit(0 if result.wasSuccessful() else 1)
