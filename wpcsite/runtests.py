#!/usr/bin/env python

import os
import sys
try:
    from django.conf import settings
except:
    os.environ['DJANGO_SETTINGS_MODULE'] = 'wpcsite.settings'
    test_dir = os.path.dirname(__file__)
    sys.path.insert(0, test_dir)
    from django.conf import settings

from django import setup
from django.test.utils import get_runner


def runtests():
    setup()
    TestRunner = get_runner(settings)
    test_runner = TestRunner(verbosity=1, interactive=True)
    failures = test_runner.run_tests([])
    sys.exit(failures)

if __name__ == '__main__':
    runtests()
