#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Tests for `web-platform-compat` fields module.
"""
from datetime import datetime
from pytz import UTC

from django.contrib.auth.models import User

from webplatformcompat.models import Browser, Version
from webplatformcompat.cache import Cache

from .base import TestCase


class TestCache(TestCase):
    def setUp(self):
        self.cache = Cache()

    def test_browser_v1_serializer(self):
        browser = self.create(Browser)
        out = self.cache.browser_v1_serializer(browser)
        expected = {
            'id': browser.id,
            'slug': u'',
            'icon': u'',
            'name': {},
            'note': {},
            'history:PKList': {
                'app': u'webplatformcompat',
                'model': 'historicalbrowser',
                'pks': [1],
            },
            'history_current:PK': {
                'app': u'webplatformcompat',
                'model': 'historicalbrowser',
                'pk': 1,
            },
            'versions:PKList': {
                'app': u'webplatformcompat',
                'model': 'version',
                'pks': [],
            },
        }
        self.assertEqual(out, expected)

    def test_browser_v1_serializer_empty(self):
        self.assertEqual(None, self.cache.browser_v1_serializer(None))

    def test_browser_v1_loader(self):
        browser = self.create(Browser)
        self.assertNumQueries(1)
        obj = self.cache.browser_v1_loader(browser.pk)
        self.assertNumQueries(3)
        serialized = self.cache.browser_v1_serializer(obj)
        self.assertTrue(serialized)
        self.assertNumQueries(3)

    def test_browser_v1_loader_not_exist(self):
        self.assertFalse(Browser.objects.filter(pk=666).exists())
        self.assertIsNone(self.cache.browser_v1_loader(666))

    def test_browser_v1_invalidator(self):
        browser = self.create(Browser)
        self.assertEqual([], self.cache.browser_v1_invalidator(browser))

    def test_version_v1_serializer(self):
        browser = self.create(Browser)
        version = self.create(Version, browser=browser)
        out = self.cache.version_v1_serializer(version)
        expected = {
            'id': version.id,
            'version': u'',
            'release_day:Date': None,
            'retirement_day:Date': None,
            'status': u'unknown',
            'release_notes_uri': {},
            'note': {},
            '_order': 0,
            'browser:PK': {
                'app': u'webplatformcompat',
                'model': 'browser',
                'pk': browser.id,
            },
            'history:PKList': {
                'app': u'webplatformcompat',
                'model': 'historicalversion',
                'pks': [1],
            },
            'history_current:PK': {
                'app': u'webplatformcompat',
                'model': 'historicalversion',
                'pk': 1,
            },
        }
        self.assertEqual(out, expected)

    def test_version_v1_serializer_empty(self):
        self.assertEqual(None, self.cache.version_v1_serializer(None))

    def test_version_v1_loader(self):
        browser = self.create(Browser)
        version = self.create(Version, browser=browser)
        self.assertNumQueries(1)
        obj = self.cache.version_v1_loader(version.pk)
        self.assertNumQueries(3)
        serialized = self.cache.version_v1_serializer(obj)
        self.assertTrue(serialized)
        self.assertNumQueries(3)

    def test_version_v1_loader_not_exist(self):
        self.assertFalse(Version.objects.filter(pk=666).exists())
        self.assertIsNone(self.cache.version_v1_loader(666))

    def test_version_v1_invalidator(self):
        browser = self.create(Browser)
        version = self.create(Version, browser=browser)
        expected = [('Browser', 1, True)]
        self.assertEqual(expected, self.cache.version_v1_invalidator(version))

    def test_historicalbrowser_v1_serializer(self):
        history_date = datetime(2014, 9, 22, 7, 49, 48, 2384, UTC)
        browser = self.create(Browser, _history_date=history_date)
        hbrowser = browser.history.all()[0]
        out = self.cache.historicalbrowser_v1_serializer(hbrowser)
        expected = {
            'id': 1,
            'date:DateTime': '1411372188.002384',
            'event': u'created',
            'user:PK': {
                'app': u'auth',
                'model': 'user',
                'pk': 1
            },
            'browser:PK': {
                'app': u'webplatformcompat',
                'model': 'browser',
                'pk': 1,
            },
            'browsers': {
                'history_current': 1,
                'icon': u'',
                'id': 1,
                'name': {},
                'note': {},
                'slug': u''
            },
        }
        self.assertEqual(out, expected)

    def test_historicalbrowser_v1_serializer_empty(self):
        self.assertEqual(
            None, self.cache.historicalbrowser_v1_serializer(None))

    def test_historicalbrowser_v1_loader(self):
        browser = self.create(Browser)
        hbrowser = browser.history.all()[0]
        self.assertNumQueries(1)
        obj = self.cache.historicalbrowser_v1_loader(hbrowser.history_id)
        self.assertNumQueries(3)
        serialized = self.cache.historicalbrowser_v1_serializer(obj)
        self.assertTrue(serialized)
        self.assertNumQueries(3)

    def test_historicalbrowser_v1_loader_not_exist(self):
        self.assertFalse(Browser.history.filter(pk=666).exists())
        self.assertIsNone(self.cache.historicalbrowser_v1_loader(666))

    def test_historicalbrowser_v1_invalidator(self):
        browser = self.create(Browser)
        hbrowser = browser.history.all()[0]
        self.assertEqual(
            [], self.cache.historicalbrowser_v1_invalidator(hbrowser))

    def test_user_v1_serializer(self):
        user = self.create(
            User, date_joined=datetime(2014, 9, 22, 8, 14, 34, 7, UTC))
        out = self.cache.user_v1_serializer(user)
        expected = {
            'id': user.id,
            'username': '',
            'date_joined:DateTime': '1411373674.000007',
        }
        self.assertEqual(out, expected)

    def test_user_v1_serializer_empty(self):
        self.assertEqual(None, self.cache.user_v1_serializer(None))

    def test_user_v1_inactive(self):
        user = self.create(
            User, date_joined=datetime(2014, 9, 22, 8, 14, 34, 7, UTC),
            is_active=False)
        out = self.cache.user_v1_serializer(user)
        self.assertEqual(out, None)

    def test_user_v1_loader(self):
        user = self.create(User)
        self.assertNumQueries(1)
        obj = self.cache.user_v1_loader(user.pk)
        self.assertNumQueries(3)
        serialized = self.cache.user_v1_serializer(obj)
        self.assertTrue(serialized)
        self.assertNumQueries(3)

    def test_user_v1_loader_not_exist(self):
        self.assertFalse(User.objects.filter(pk=666).exists())
        self.assertIsNone(self.cache.user_v1_loader(666))

    def test_user_v1_invalidator(self):
        user = self.create(User)
        self.assertEqual([], self.cache.user_v1_invalidator(user))