"""This module supports converting between currencies using api layer. We cache
results for an hour for every currency from a particular source. So if we need
to convert JPY to USD, we'll get the conversion from JPY to USD, EUR, etc. This
avoids needless API requests as the charge to convert one currency is the same
as the charge to convert one to many currencies.

This requires a paid plan ($95.90/year) so that we can do source currency
swaps, e.g., GBP to EUR.
"""
import requests
import os
import time
from lblogging import Level
import pytypeutils as tus
from lbshared.lazy_integrations import LazyIntegrations
import money


MEMCACHED_KEY_PREFIX = 'loansbot/convert'
MEMCACHED_EXPIRE_TIME_SECONDS = int(os.environ.get('CURRENCY_LAYER_CACHE_TIME'), '14400')


def convert(itgs, source, target):
    """Get the conversion rate from the given source currency to the given
    target currency. Specifically, returns rate such that
    (source currency cents) * (rate) = (target currency cents)

    This is a bit different than other usages. Here's an example:
        1 u.s. dollar = 110 yen
        means
        1 u.s. cent = (110/100) yen
        means
        1 u.s. cent = 1.10 yen
        means
        1 u.s cent * (1.10 yen/u.s cent) = 1.10 yen
        means
        rate = 1.10
    """
    tus.check(
        itgs=(itgs, LazyIntegrations),
        source=(source, str),
        target=(target, str)
    )
    if source not in money.ISO_CODES_TO_EXP:
        raise ValueError(f'source={source} is not a 3-letter iso code')
    if target not in money.ISO_CODES_TO_EXP:
        raise ValueError(f'target={target} is not a 3-letter iso code')
    if source == target:
        return 1

    dollar_rate = itgs.cache.get(_cache_key(source, target))
    if dollar_rate is None:
        inv_dollar_rate = itgs.cache.get(_cache_key(target, source))
        if inv_dollar_rate is None:
            fill_cache(itgs, source)
            dollar_rate = float(itgs.cache.get(_cache_key(source, target)))
        else:
            dollar_rate = 1 / float(inv_dollar_rate)
    else:
        dollar_rate = float(dollar_rate)

    return dollar_rate * (10 ** (money.ISO_CODES_TO_EXP[target] - money.ISO_CODES_TO_EXP[source]))


def fill_cache(itgs, source):
    """Fills the cache from the given source currency to each target specifed
    in money.ISO_CODES_TO_EXP. This costs 1 API request and requires a paid
    plan.
    """
    tus.check(itgs=(itgs, LazyIntegrations), source=(source, str))
    if source not in money.ISO_CODES_TO_EXP:
        raise ValueError(f'source={source} is not a 3-letter uppercase iso code')

    api_key = os.environ['CURRENCY_LAYER_API_KEY']

    start_time = time.time()
    attempts = 0
    for attempt in range(1, 6):
        try:
            response = requests.get(
                'https://apilayer.net/api/live',
                params={
                    'access_key': api_key,
                    'currencies': list(money.ISO_CODES_TO_EXP.keys()),
                    'source': source,
                    'format': 1
                }
            )
            response.raise_for_status()
            attempts = attempt
            break
        except:  # noqa
            itgs.logger.exception(
                Level.WARN,
                'Currency convert from {} attempt {}/5',
                source, attempt)

            if attempt == 5:
                raise

        time.sleep(2 ** attempt)

    body = response.json()
    quotes = body['quotes']

    for conversion, rate in quotes.items():
        key = _cache_key(source, conversion[len(source):])
        itgs.cache.set(key, str(rate), expire=MEMCACHED_EXPIRE_TIME_SECONDS)

    time_req = time.time() - start_time
    itgs.logger.print(
        Level.TRACE,
        '({} ms, {} attempt{}) Currency cache fill: converted from source {}; rates: {}',
        int(time_req * 1000), attempts, ('s' if attempts > 1 else ''), source, quotes
    )


def _cache_key(source, target):
    return MEMCACHED_KEY_PREFIX + '/' + source + '-' + target
