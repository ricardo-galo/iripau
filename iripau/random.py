"""
Generic and stand-alone random utilities.
"""

import math
import random
import string

from typing import Any, List


def one(items: List[Any]) -> List[Any]:
    """ Return a new ``list`` containing only one element from ``items``.

        Args:
            items: The items to choose from.

        Returns:
            A ``list`` with only one of the ``items``.
    """
    return [random.choice(items)]


def some(
    items: List[Any],
    percentage: float = 50,
    at_least: int = 2,
    at_most: int = None
) -> List[Any]:
    """ Return a new ``list`` containing some elements from ``items``.
        Ordinality is preserved as much as possible.

        Args:
            items: The items to choose from.
            percentage: This percentage of the ``items`` will be chosen.
            at_least: If specified, do not choose less than this amount of ``items``.
            at_most: If specified, do not choose more that this amount of ``items``.

        Returns:
            Some ``items`` in the same order.
    """
    count = math.ceil(percentage * len(items) / 100)
    if at_least and at_least > count:
        count = at_least
    if at_most and at_most < count:
        count = at_most
    return sorted(random.sample(items, count), key=items.index)


def shuffled(items: List[Any]) -> List[Any]:
    """ Return a new ``list`` containing all of the elements from ``items`` but
        in a different order.

        Args:
            items: The items to choose from.

        Returns:
            The same ``items`` in different order.
    """
    return random.sample(items, len(items))


def random_string(length: int, chars: str = string.ascii_letters) -> str:
    """ Return a string of the desired ``length`` containing randomly chosen
        characters from ``chars``.

        Args:
            length: How long the returned string will be.
            chars: Set of chars to choose from.

        Returns:
            New string.
    """
    return "".join(random.choice(chars) for _ in range(length))
