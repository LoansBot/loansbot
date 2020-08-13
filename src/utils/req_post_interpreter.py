"""This module is responsible for interpreting the titles of request threads.
"""
from pydantic import BaseModel
import lbshared.money
import typing
import re

BLOB_REGEX = r'\(([^\)]+)\)'
PROCESSORS = [
    'venmo', 'paypal', 'bank', 'cashapp', 'zelle', 'chime'
]


class LoanRequest(BaseModel):
    """Describes a request for a loan as interpreted from a thread title.

    Attributes:
        - `title (str)`: The raw text title for the request
        - `location (str, None)`: What we interpret to be the raw location of the
            borrower from the request.
        - `city (str, None)`: From the location string what we interpret to be the
            city they are referring to, if we found one.
        - `state (str, None)`: From the location string what we interpret to be the
            state they are referring to, if we found one.
        - `country (str, None)`: From the location string what we interpret to be
            the country they are referring to, if we found one.
        - `terms (str, None)`: What we interpret to be the terms of the loan
            from the title.
        - `processor (str, None)`: What we interpret to be the payment processor
            they are using, if we found one
        - `notes (list[str])`: Any uninterpreted blobs from the title.
    """
    title: str
    location: str = None
    city: str = None
    state: str = None
    country: str = None
    terms: str = None
    processor: str = None
    notes: typing.List[str]


def interpret(title: str) -> LoanRequest:
    """Attempts to interpret the given loan request string as a loan request.

    Arguments:
        - `title (str)`: The title to interpret

    Returns:
        - `request (LoanRequest)`: The interpreted request
    """
    result = {
        'title': title,
        'notes': []
    }

    for m in re.finditer(BLOB_REGEX, title):
        blob = m.group(1)

        if result.get('location') is None and blob.startswith('#'):
            loc = blob[1:]
            result['location'] = loc
            loc_spl = loc.split(',')
            if len(loc_spl) == 3:
                (city, state, country) = loc_spl
                result['city'] = city.strip()
                result['state'] = state.strip()
                result['country'] = country.strip()
            continue

        if result.get('terms') is None:
            is_term = False
            is_term = is_term or re.match(r'\d/', blob)
            for symbol in lbshared.money.CURRENCY_SYMBOLS.keys():
                is_term = is_term or symbol in blob
            for isocode in lbshared.money.ISO_CODES_TO_EXP.keys():
                is_term = is_term or isocode.lower() in blob.lower()

            if is_term:
                result['terms'] = blob
                continue

        if result.get('processor') is None:
            is_processor = False
            for processor in PROCESSORS:
                is_processor = is_processor or processor.lower() in blob.lower()

            if is_processor:
                result['processor'] = blob
                continue

        result['notes'].append(blob)

    return LoanRequest(**result)
