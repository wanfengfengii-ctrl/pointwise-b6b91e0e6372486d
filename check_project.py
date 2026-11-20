"""Run this project's full unittest suite from the repository root."""
import sys
import unittest

import stop_examples


def main():
    suite = unittest.defaultTestLoader.discover('tests', top_level_dir='.')
    if suite.countTestCases():
        result = unittest.TextTestRunner(verbosity=2).run(suite)
    else:
        print('No tests discovered in tests/', file=sys.stderr)
        result = unittest.TestResult()
    for status, failed_cases in (
        ('FAIL', (test for test, _ in result.failures)),
        ('ERROR', (test for test, _ in result.errors)),
        ('UNEXPECTED_SUCCESS', result.unexpectedSuccesses),
    ):
        for test in failed_cases:
            print(f'{status} {test.id()}')
    successful = result.testsRun > 0 and result.wasSuccessful()
    print(f'TEST SUMMARY total={result.testsRun} failures={len(result.failures)} '
          f'errors={len(result.errors)} skipped={len(result.skipped)} '
          f'expected_failures={len(result.expectedFailures)} '
          f'unexpected_successes={len(result.unexpectedSuccesses)} '
          f'result={"PASS" if successful else "FAIL"}')
    examples = _run_stop_examples()
    return 0 if successful and examples else 1


def _run_stop_examples() -> bool:
    try:
        stop_examples.main()
    except Exception as error:
        print(f'STOP EXAMPLES result=FAIL {error!r}')
        return False
    print('STOP EXAMPLES result=PASS')
    return True


if __name__ == '__main__':
    raise SystemExit(main())
