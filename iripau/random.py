"""
Handle random data
"""

import math
import random
import string


def one(items):
    """ Return a new list containing only one element from items """
    return [random.choice(items)]


def some(items, percentage=50, at_least=2, at_most=None):
    """ Return a new list containing some elements from items.
        Ordinality is preserved as much as possible.
    """
    count = math.ceil(percentage * len(items) / 100)
    if at_least and at_least > count:
        count = at_least
    if at_most and at_most < count:
        count = at_most
    return sorted(random.sample(items, count), key=items.index)


def shuffled(items):
    """ Return a new list containing all of the elements from items but in a
        different order.
    """
    return random.sample(items, len(items))


def random_string(length, chars=string.ascii_letters):
    """ Return a string of the desired length containing randomly chosen
        characters from chars.
    """
    return "".join(random.choice(chars) for _ in range(length))
