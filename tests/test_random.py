"""
Tests to validate iripau.random module
"""

import pytest
import random

from iripau.random import one
from iripau.random import some
from iripau.random import shuffled
from iripau.random import random_string


class TestRandom(object):

    def test_one(self):
        items = range(10)
        sample = one(items)
        assert 1 == len(sample)
        assert all(item in items for item in sample)

    @pytest.mark.parametrize("percentage", range(0, 101, 10))
    def test_some(self, percentage):
        items = range(100)
        sample = some(items, percentage=percentage, at_least=30, at_most=70)
        length = 30 if percentage < 30 else 70 if percentage > 70 else percentage
        assert length == len(sample)
        assert all(item in items for item in sample)
        assert sorted(sample) == sample

    def test_shuffled(self):
        items = [1, 2, 3, 4, 5, 6, 7, 8, 9, 0]
        shuffled_items = shuffled(items)
        assert items != shuffled_items
        assert len(items) == len(shuffled_items)
        for item in items:
            assert item in shuffled_items

    def test_random_string(self):
        length = random.randint(0, 20)
        assert length == len(random_string(length))
