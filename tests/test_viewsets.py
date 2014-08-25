#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Tests for `web-platform-compat` viewsets module.
"""
from __future__ import unicode_literals
from datetime import datetime
from json import dumps, loads
from pytz import UTC

from django.contrib.auth.models import User
from django.core.urlresolvers import reverse
from rest_framework.test import APITestCase as BaseAPITestCase

from webplatformcompat.models import Browser


class APITestCase(BaseAPITestCase):
    '''APITestCase with useful methods'''
    maxDiff = None

    def reverse(self, viewname, **kwargs):
        return 'http://testserver' + reverse(viewname, kwargs=kwargs)

    def login_superuser(self):
        user = User.objects.create(
            username='staff', is_staff=True, is_superuser=True)
        user.set_password('5T@FF')
        user.save()
        self.assertTrue(self.client.login(username='staff', password='5T@FF'))
        return user


class TestBrowserViewset(APITestCase):
    '''Test browsers list and detail, as well as common functionality'''

    def test_get_empty(self):
        browser = Browser.objects.create()
        url = self.reverse('browser-detail', pk=browser.pk)
        response = self.client.get(
            url, content_type="application/vnd.api+json")
        history = browser.history.get()
        history_url = self.reverse('historicalbrowser-detail', pk=history.pk)
        expected_data = {
            'id': browser.pk,
            'slug': '',
            'icon': None,
            'name': None,
            'note': None,
            'history': [history_url],
            'history_current': history_url,
            'browser_versions': [],
        }
        self.assertEqual(dict(response.data), expected_data)
        expected_content = {
            "browsers": {
                "id": str(browser.pk),
                "slug": "",
                "icon": None,
                "name": None,
                "note": None,
                "links": {
                    "history": [str(history.pk)],
                    "history_current": str(history.pk),
                    "browser_versions": [],
                }
            },
            "links": {
                "browsers.history": {
                    "type": "historical browsers",
                    "href": history_url.replace(
                        str(history.pk), "{browsers.history}"),
                },
                "browsers.history_current": {
                    "type": "historical browsers",
                    "href": history_url.replace(
                        str(history.pk), "{browsers.history_current}"),
                },
                "browsers.browser_versions": {
                    "type": "browser versions",
                },
            }
        }
        actual_content = loads(response.content.decode('utf-8'))
        self.assertEqual(expected_content, actual_content)

    def test_get_populated(self):
        browser = Browser.objects.create(
            slug="firefox",
            icon=("https://people.mozilla.org/~faaborg/files/shiretoko"
                  "/firefoxIcon/firefox-128.png"),
            name={"en": "Firefox"},
            note={"en": "Uses Gecko for its web browser engine"})
        url = reverse('browser-detail', kwargs={'pk': browser.pk})
        response = self.client.get(url)
        history = browser.history.get()
        history_url = self.reverse('historicalbrowser-detail', pk=history.pk)
        expected_data = {
            'id': browser.pk,
            'slug': 'firefox',
            'icon': ("https://people.mozilla.org/~faaborg/files/shiretoko"
                     "/firefoxIcon/firefox-128.png"),
            'name': {"en": "Firefox"},
            'note': {"en": "Uses Gecko for its web browser engine"},
            'history': [history_url],
            'history_current': history_url,
            'browser_versions': [],
        }
        self.assertEqual(response.data, expected_data)

    def test_get_list(self):
        firefox = Browser.objects.create(
            slug="firefox", name={"en": "Firefox"},
            icon=("https://people.mozilla.org/~faaborg/files/shiretoko"
                  "/firefoxIcon/firefox-128.png"),
            note={"en": "Uses Gecko for its web browser engine"})
        chrome = Browser.objects.create(
            slug="chrome", name={"en": "Chrome"})
        response = self.client.get(reverse('browser-list'))
        firefox_history_id = '%s' % firefox.history.get().pk
        chrome_history_id = '%s' % chrome.history.get().pk
        expected_content = {
            'browsers': [
                {
                    'id': '%s' % firefox.pk,
                    'slug': 'firefox',
                    'icon': ("https://people.mozilla.org/~faaborg/files/"
                             "shiretoko/firefoxIcon/firefox-128.png"),
                    'name': {"en": "Firefox"},
                    'note': {"en": "Uses Gecko for its web browser engine"},
                    'links': {
                        'history': [firefox_history_id],
                        'history_current': firefox_history_id,
                        'browser_versions': [],
                    },
                }, {
                    'id': '%s' % chrome.pk,
                    'slug': 'chrome',
                    'icon': None,
                    'name': {"en": "Chrome"},
                    'note': None,
                    'links': {
                        'history': [chrome_history_id],
                        'history_current': chrome_history_id,
                        'browser_versions': [],
                    },
                },
            ],
            'links': {
                'browsers.history': {
                    'href': (
                        'http://testserver/api/historical-browsers/'
                        '{browsers.history}'),
                    'type': 'historical browsers',
                },
                'browsers.history_current': {
                    'href': (
                        'http://testserver/api/historical-browsers/'
                        '{browsers.history_current}'),
                    'type': 'historical browsers',
                },
                'browsers.browser_versions': {
                    'type': 'browser versions',
                },
            }
        }
        actual_content = loads(response.content.decode('utf-8'))
        self.assertEqual(expected_content, actual_content)

    def test_get_browsable_api(self):
        self.login_superuser()
        browser = Browser.objects.create()
        url = self.reverse('browser-list')
        response = self.client.get(url, HTTP_ACCEPT="text/html")
        history = browser.history.get()
        history_url = self.reverse('historicalbrowser-detail', pk=history.pk)
        expected_data = [{
            'id': browser.pk,
            'slug': '',
            'icon': None,
            'name': None,
            'note': None,
            'history': [history_url],
            'history_current': history_url,
            'browser_versions': [],
        }]
        self.assertEqual(list(response.data), expected_data)
        self.assertTrue(response['content-type'].startswith('text/html'))

    def test_post_not_authorized(self):
        response = self.client.post(reverse('browser-list'), {})
        self.assertEqual(403, response.status_code)
        expected_data = {
            'detail': 'Authentication credentials were not provided.'
        }
        self.assertEqual(response.data, expected_data)

    def test_post_empty(self):
        self.login_superuser()
        response = self.client.post(reverse('browser-list'), {})
        self.assertEqual(400, response.status_code)
        expected_data = {
            "slug": ["This field is required."],
            "name": ["This field is required."],
        }
        self.assertEqual(response.data, expected_data)

    def test_post_minimal(self):
        self.login_superuser()
        data = {'slug': 'firefox', 'name': '{"en": "Firefox"}'}
        response = self.client.post(reverse('browser-list'), data)
        self.assertEqual(201, response.status_code, response.data)
        browser = Browser.objects.get()
        history = browser.history.get()
        history_url = self.reverse('historicalbrowser-detail', pk=history.pk)
        expected_data = {
            "id": browser.pk,
            "slug": "firefox",
            "icon": None,
            "name": {"en": "Firefox"},
            "note": None,
            'history': [history_url],
            'history_current': history_url,
            'browser_versions': [],
        }
        self.assertEqual(response.data, expected_data)

    def test_post_minimal_json_api(self):
        self.login_superuser()
        data = dumps({
            'browsers': {
                'slug': 'firefox',
                'name': {
                    "en": "Firefox"
                },
            }
        })
        response = self.client.post(
            reverse('browser-list'), data=data,
            content_type="application/vnd.api+json")
        self.assertEqual(201, response.status_code, response.data)
        browser = Browser.objects.get()
        history = browser.history.get()
        history_url = self.reverse('historicalbrowser-detail', pk=history.pk)
        expected_data = {
            "id": browser.pk,
            "slug": "firefox",
            "icon": None,
            "name": {"en": "Firefox"},
            "note": None,
            'history': [history_url],
            'history_current': history_url,
            'browser_versions': [],
        }
        self.assertEqual(response.data, expected_data)

    def test_post_full(self):
        self.login_superuser()
        data = {
            'slug': 'firefox',
            'icon': ("https://people.mozilla.org/~faaborg/files/shiretoko"
                     "/firefoxIcon/firefox-128.png"),
            'name': '{"en": "Firefox"}',
            'note': '{"en": "Uses Gecko for its web browser engine"}',
        }
        response = self.client.post(reverse('browser-list'), data)
        self.assertEqual(201, response.status_code, response.data)
        browser = Browser.objects.get()
        history = browser.history.get()
        history_url = self.reverse('historicalbrowser-detail', pk=history.pk)
        expected_data = {
            'id': browser.pk,
            'slug': 'firefox',
            'icon': ("https://people.mozilla.org/~faaborg/files/shiretoko"
                     "/firefoxIcon/firefox-128.png"),
            'name': {"en": "Firefox"},
            'note': {"en": "Uses Gecko for its web browser engine"},
            'history': [history_url],
            'history_current': history_url,
            'browser_versions': [],
        }
        self.assertEqual(response.data, expected_data)

    def test_post_bad_data(self):
        self.login_superuser()
        data = {
            'slug': 'bad slug',
            'icon': ("http://people.mozilla.org/~faaborg/files/shiretoko"
                     "/firefoxIcon/firefox-128.png"),
            'name': '"Firefox"',
            'note': '{"es": "Utiliza Gecko por su motor del navegador web"}',
        }
        response = self.client.post(reverse('browser-list'), data)
        self.assertEqual(400, response.status_code, response.data)
        expected_data = {
            'slug': [
                "Enter a valid 'slug' consisting of letters, numbers,"
                " underscores or hyphens."],
            'icon': ["URI must use the 'https' protocol."],
            'name': [
                "Value must be a JSON dictionary of language codes to"
                " strings."],
            'note': ["Missing required language code 'en'."],
        }
        self.assertEqual(response.data, expected_data)

    def test_put_as_json_api(self):
        '''If content is application/vnd.api+json, put is partial'''
        self.login_superuser()
        browser = Browser.objects.create(
            slug='browser', name={'en': 'Old Name'})
        data = dumps({
            'browsers': {
                'name': {
                    'en': 'New Name'
                }
            }
        })
        url = reverse('browser-detail', kwargs={'pk': browser.pk})
        response = self.client.put(
            url, data=data, content_type="application/vnd.api+json")
        self.assertEqual(200, response.status_code, response.data)
        current_history = browser.history.most_recent()
        histories = browser.history.all()
        view = 'historicalbrowser-detail'
        expected_data = {
            "id": browser.pk,
            "slug": "browser",
            "icon": None,
            "name": {"en": "New Name"},
            "note": None,
            "history": [
                self.reverse(view, pk=h.pk) for h in histories],
            "history_current": self.reverse(view, pk=current_history.pk),
            "browser_versions": [],
        }
        self.assertEqual(response.data, expected_data)

    def test_put_as_json(self):
        '''If content is application/json, put is full put'''
        self.login_superuser()
        browser = Browser.objects.create(
            slug='browser', name={'en': 'Old Name'})
        data = {'name': '{"en": "New Name"}'}
        url = reverse('browser-detail', kwargs={'pk': browser.pk})
        response = self.client.put(
            url, data=data)
        self.assertEqual(400, response.status_code, response.data)
        expected_data = {
            "slug": ["This field is required."],
        }
        self.assertEqual(response.data, expected_data)


class TestHistoricalBrowserViewset(APITestCase):
    def test_get(self):
        self.login_superuser()
        browser = Browser(slug='browser', name={'en': 'A Browser'})
        browser._history_date = datetime(2014, 8, 25, 20, 50, 38, 868903, UTC)
        browser.save()
        bh = browser.history.all()[0]
        url = reverse('historicalbrowser-detail', kwargs={'pk': bh.pk})
        response = self.client.get(
            url, HTTP_ACCEPT="application/vnd.api+json")
        self.assertEqual(200, response.status_code, response.data)

        expected_data = {
            'id': bh.history_id,
            'date': browser._history_date,
            'event': 'created',
            'user': None,
            'browser': self.reverse('browser-detail', pk=browser.pk),
            'browsers': {
                'id': '1',
                'slug': 'browser',
                'icon': None,
                'name': {'en': 'A Browser'},
                'note': None,
                'links': {'history_current': '1'}
            },
        }
        actual = dict(response.data)
        actual['browsers'] = dict(actual['browsers'])
        actual['browsers']['name'] = dict(actual['browsers']['name'])
        self.assertDictEqual(expected_data, actual)
        expected_json = {
            'historical browsers': {
                'id': '1',
                'date': '2014-08-25T20:50:38.868Z',
                'event': 'created',
                'browsers': {
                    'id': '1',
                    'slug': 'browser',
                    'icon': None,
                    'name': {
                        'en': 'A Browser'
                    },
                    'note': None,
                    'links': {
                        'history_current': '1'
                    },
                },
                'links': {
                    'browser': '1',
                    'user': None
                }
            },
            'links': {
                'historical browsers.browser': {
                    'href': (
                        'http://testserver/api/browsers/'
                        '{historical browsers.browser}'),
                    'type': 'browsers'
                },
                'historical browsers.user': {
                    'href': (
                        'http://testserver/api/users/'
                        '{historical browsers.user}'),
                    'type': 'users'
                }
            }
        }
        self.assertDictEqual(
            expected_json, loads(response.content.decode('utf-8')))