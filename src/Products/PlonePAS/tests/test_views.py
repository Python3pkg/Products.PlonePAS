# -*- encoding: utf-8 -*-
from Products.PlonePAS.tests import base


class TestPASSearchView(base.TestCase):

    def test_sort(self):
        pas_search = self.portal.restrictedTraverse('@@pas_search')
        values = [{'title': 'Sociologie'}, {'title': 'Économie'},
                  {'title': 'anthropologie'}]
        sorted_values = pas_search.sort(values, 'title')
        # do not modify original
        self.assertEqual(values,
                         [{'title': 'Sociologie'}, {'title': 'Économie'},
                          {'title': 'anthropologie'}])
        # sorted here
        self.assertEqual(sorted_values,
                         [{'title': 'anthropologie'}, {'title': 'Économie'},
                          {'title': 'Sociologie'}])
