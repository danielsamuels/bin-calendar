from functools import reduce

import requests
from bs4 import BeautifulSoup
from dateutil.parser import parse
from ics import Calendar, Event


class Page:
    def __init__(self, resp):
        self.resp = resp

    @property
    def soup(self):
        return BeautifulSoup(self.resp.content, 'html.parser')

    @property
    def collections(self):
        collections = self.soup.find_all('div', class_='collectionsrow')

        return [
            Collection(el)
            for el in collections
            if Collection(el).is_entry
        ]

    @property
    def collections_by_date(self):
        """Collections, grouped by date"""
        def date_reducer(output, collection):
            date = collection.date.date()

            if date not in output:
                output[date] = [collection]
            else:
                output[date].append(collection)

            return output

        dates = reduce(date_reducer, self.collections, dict())
        return [
            CollectionDate(collections)
            for collections in dates.values()
        ]

    @property
    def as_ical(self):
        ical = Calendar()

        # Dump out the ical headers

        # Then each of the collection items
        for collection in self.collections_by_date:
            ical.events.add(collection.as_ical)

        return ical


class Collection:
    TYPE_SELECTOR = 'col-sm-4'
    DATE_SELECTOR = 'col-sm-6'

    def __init__(self, el):
        self.el = el
        # col-sm-4 -> "Black Bag"
        # col-sm-6 -> "Sat - 11 May 2019"

    @property
    def is_entry(self):
        return self.type and self.date

    @property
    def type(self):
        element = self.el.find('div', class_=self.TYPE_SELECTOR)

        if not element:
            return None

        return element.string

    @property
    def date(self):
        element = self.el.find('div', class_=self.DATE_SELECTOR)

        if not element:
            return None

        parsed_date = parse(element.string)
        return parsed_date.replace(hour=7, minute=50)

    @property
    def as_ical(self):
        event = Event()
        event.name = self.type
        event.begin = self.date
        event.end = self.date.replace(hour=8, minute=10)
        return event


class CollectionDate:
    def __init__(self, collections):
        self._collections = collections

    @property
    def date(self):
        return self._collections[0].date

    @property
    def as_ical(self):
        event = Event()
        event.name = ' and '.join(collection.type for collection in self._collections)
        event.begin = self.date
        event.end = self.date.replace(hour=8, minute=10)
        return event


def generate_calendar(url) -> Calendar:
    resp = requests.get(url)
    resp.raise_for_status()

    page = Page(resp)
    return page.as_ical
