"""Run the suite and expose failure details as a machine-readable CI report."""
import json
from pathlib import Path
import sys
import unittest

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))
suite = unittest.defaultTestLoader.discover(str(root))
result = unittest.TextTestRunner(verbosity=2).run(suite)
details = '\n\n'.join(f'{test.id()}\n{trace}' for test, trace in result.failures + result.errors)
report = {
    'success': result.wasSuccessful(),
    'summary': f'{result.testsRun} tests; {len(result.failures)} failures; '
               f'{len(result.errors)} errors; {len(result.skipped)} skipped.',
    'details': details[-55000:],
}
(root / 'test-results.json').write_text(json.dumps(report), encoding='utf-8')
sys.exit(0 if result.wasSuccessful() else 1)
