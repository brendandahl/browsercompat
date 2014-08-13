#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Tests for `web-platform-compat` fields module.
"""

from django.core.exceptions import ValidationError
from django.test import TestCase

from webplatformcompat.fields import TranslatedTextField


class TestTranslatedTextField(TestCase):

    def setUp(self):
        self.ttf = TranslatedTextField()

    def test_to_native_falsy(self):
        '''Coverting to serializable form, falsy becomes None'''
        self.assertIsNone(self.ttf.to_native(''))

    def test_to_native_dict(self):
        '''Coverting to serializable form, dicts are passed through'''
        data = {"key": "value"}
        self.assertEqual(data, self.ttf.to_native(data))

    def test_from_native_falsy(self):
        '''Converting from serialized form, false values are None'''
        self.assertIsNone(self.ttf.from_native(''))

    def test_from_native_spaces(self):
        '''Converting from serialized form, spaces are None'''
        self.assertIsNone(self.ttf.from_native('  '))

    def test_from_native_json(self):
        '''Converting from serialized form, JSON becomes dict'''
        json_in = '{"key": "value"}'
        json_out = {"key": "value"}
        self.assertEqual(json_out, self.ttf.from_native(json_in))

    def test_from_native_bad_json(self):
        '''Converting from serialized form, bad JSON becomes ValidationError'''
        bad_json = "{'quotes': 'wrong ones'}"
        self.assertRaises(ValidationError, self.ttf.from_native, bad_json)
