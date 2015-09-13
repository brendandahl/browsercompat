#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Tests for `web-platform-compat` renderers module."""

from json import loads

from django.core.urlresolvers import reverse

from webplatformcompat.models import Browser
from webplatformcompat.renderers import JsonApiRC2Renderer
from .base import TestCase


class TestJsonApiRC2Renderers(TestCase):

    def setUp(self):
        self.renderer = JsonApiRC2Renderer()

    def test_model_to_resource_type(self):
        self.assertEqual(
            'browsers', self.renderer.model_to_resource_type(Browser()))
        self.assertEqual(
            'historical_browsers',
            self.renderer.model_to_resource_type(Browser().history.model))
        self.assertEqual(
            'data',
            self.renderer.model_to_resource_type(None))

    def test_options(self):
        url = reverse('browser-list')
        response = self.client.options(
            url, HTTP_ACCEPT="application/vnd.api+json")
        self.assertEqual(200, response.status_code, response.content)
        expected_content = {
            'meta': {
                'name': 'Browser',
                'description': '',
                'renders': ['application/vnd.api+json', u'text/html'],
                'parses': [
                    'application/vnd.api+json',
                    'application/x-www-form-urlencoded',
                    'multipart/form-data']}}
        content = loads(response.content.decode('utf8'))
        self.assertEqual(expected_content, content)

    def test_parser_error(self):
        data = "{'people': {'name': 'Jason Api'}}"  # Bad JSON, wrong quotes
        self.login_user()
        response = self.client.post(
            reverse("browser-list"), data=data,
            content_type="application/vnd.api+json")

        self.assertEqual(400, response.status_code, response.content)
        expected_content = {
            "errors": [{
                "status": "400",
                "detail": (
                    "JSON parse error - Expecting property name enclosed in"
                    " double quotes: line 1 column 2 (char 1)"),
            }]
        }
        content = loads(response.content.decode('utf8'))
        self.assertEqual(expected_content, content)
