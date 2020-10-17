"""This module is intended to fill the caches that are used for fulfilling
requests to the /api/loans/stats/{unit}/{frequency} endpoint. These caches
are stored in memcached.
"""
from lbshared.lazy_integrations import LazyIntegrations
from lblogging import Level
from .utils import sleep_until_hour_and_minute
from pypika import Query, Table
from pypika.terms import Star
from pypika.functions import Count, Sum
from lbshared.pypika_funcs import DatePart
import time
import json


LOGGER_IDEN = 'runners/loans_stats.py#main'


def main():
    with LazyIntegrations(logger_iden=LOGGER_IDEN) as itgs:
        itgs.logger.print(Level.DEBUG, 'Successfully booted up')

    while True:
        # 8AM UTC = 1AM PST = 4AM EST = presumably off-peak hours
        sleep_until_hour_and_minute(8, 0)
        update_stats()


def update_stats():
    the_time = time.time()
    with LazyIntegrations(logger_iden=LOGGER_IDEN) as itgs:
        plots = {}
        for unit in ('count', 'usd'):
            plots[unit] = {}
            frequency = 'monthly'
            frequency_unit = 'month'
            plots[unit][frequency] = {
                'title': f'{frequency} {unit}'.title(),
                'x_axis': frequency_unit.title(),
                'y_axis': unit.title(),
                'generated_at': the_time,
                'data': {
                    #  Categories will be added later
                    'series': {}  # Will be listified later
                }
            }
            for style in ('lent', 'repaid', 'unpaid'):
                plots[unit][frequency]['data']['series'][style] = {
                    'name': style.title(),
                    'data': {}  # Will be listified later
                }

        loans = Table('loans')
        moneys = Table('moneys')
        principals = moneys.as_('principals')

        time_parts = {
            'month': DatePart('month', loans.created_at),
            'year': DatePart('year', loans.created_at)
        }

        query = (
            Query.from_(loans)
            .joins(principals).on(principals.id == loans.principal_id)
            .select(
                time_parts['year'],  # Which month are we counting?
                time_parts['month'],   # Which year are we counting?
                Count(Star()),  # Total # of Loans Lent In Interval
                Sum(principals.amount_usd_cents)  # Total USD of Loans Lent In Interval
            )
            .groupby(time_parts['year'], time_parts['month'])
            .where(loans.deleted_at.isnull())
        )
        sql = query.get_sql()
        itgs.logger.print(Level.TRACE, sql)

        count_series = plots['count']['monthly']['data']['series']['lent']
        usd_series = plots['usd']['monthly']['data']['series']['lent']
        itgs.read_cursor.execute(sql)
        row = itgs.read_cursor.fetchone()
        while row is not None:
            count_series[(row[0], row[1])] = row[2]
            usd_series[(row[0], row[1])] = row[3] / 100
            row = itgs.read_cursor.fetchone()

        time_parts = {
            'month': DatePart('month', loans.repaid_at),
            'year': DatePart('year', loans.repaid_at)
        }

        query = (
            Query.from_(loans)
            .joins(principals).on(principals.id == loans.principal_id)
            .select(
                time_parts['year'],
                time_parts['month'],
                Count(Star()),
                Sum(principals.amount_usd_cents)
            )
            .groupby(time_parts['year'], time_parts['month'])
            .where(loans.deleted_at.isnull())
            .where(loans.repaid_at.notnull())
        )
        sql = query.get_sql()
        itgs.logger.print(Level.TRACE, sql)

        count_series = plots['count']['monthly']['data']['series']['repaid']
        usd_series = plots['usd']['monthly']['data']['series']['repaid']
        itgs.read_cursor.execute(sql)
        row = itgs.read_cursor.fetchone()
        while row is not None:
            count_series[(row[0], row[1])] = row[2]
            usd_series[(row[0], row[1])] = row[3] / 100
            row = itgs.read_cursor.fetchone()

        time_parts = {
            'month': DatePart('month', loans.unpaid_at),
            'year': DatePart('year', loans.unpaid_at)
        }

        query = (
            Query.from_(loans)
            .joins(principals).on(principals.id == loans.principal_id)
            .select(
                time_parts['year'],
                time_parts['month'],
                Count(Star()),
                Sum(principals.amount_usd_cents)
            )
            .groupby(time_parts['year'], time_parts['month'])
            .where(loans.deleted_at.isnull())
            .where(loans.unpaid_at.notnull())
        )
        sql = query.get_sql()
        itgs.logger.print(Level.TRACE, sql)

        count_series = plots['count']['monthly']['data']['series']['unpaid']
        usd_series = plots['usd']['monthly']['data']['series']['unpaid']
        itgs.read_cursor.execute(sql)
        row = itgs.read_cursor.fetchone()
        while row is not None:
            count_series[(row[0], row[1])] = row[2]
            usd_series[(row[0], row[1])] = row[3] / 100
            row = itgs.read_cursor.fetchone()

        # We've now fleshed out all the monthly plots. We first standardize the
        # series to a categories list and series list, rather than a series dict.
        # So series[k]: {"foo": 3, "bar": 2} -> "categories": ["foo", "bar"],
        # series[k]: [3, 2]. This introduces time-based ordering

        all_keys = set()
        for unit_dict in plots.values():
            for plot in unit_dict.values():
                for series in plot['data']['series'].values():
                    for key in series.keys():
                        all_keys.add(key)

        categories = sorted(all_keys)
        categories_pretty = [f'{year}-{month}' for (year, month) in categories]
        for unit_dict in plots.values():
            for plot in unit_dict.values():
                plot['data']['categories'] = categories_pretty
                for key in tuple(plot['data']['series'].keys()):
                    dict_fmted = plot['data']['series'][key]
                    plot['data']['series'][key] = [
                        dict_fmted.get(cat, 0) for cat in categories
                    ]

        # We now map series from a dict to a list, moving the key into name
        for unit_dict in plots.values():
            for plot in unit_dict.values():
                plot['data']['series'] = [
                    {
                        'name': key.title(),
                        'data': val
                    }
                    for (key, val) in plot['data']['series'].items()
                ]

        # We can now augment monthly to quarterly. 1-3 -> q1, 4-6 -> q2, etc.
        def map_month_to_quarter(month):
            return int((month - 1) / 3) + 1

        quarterly_categories = []
        for (year, month) in categories:
            quarter = map_month_to_quarter(month)
            pretty_quarter = f'{year}Q{quarter}'
            if not quarterly_categories or quarterly_categories[-1] != pretty_quarter:
                quarterly_categories.append(pretty_quarter)

        for unit, unit_dict in plots.items():
            monthly_plot = unit_dict['monthly']
            quarterly_plot = {
                'title': f'Quarterly {unit}'.title(),
                'x_axis': 'Quarter',
                'y_axis': unit.title(),
                'generated_at': the_time,
                'data': {
                    'categories': quarterly_categories,
                    'series': []
                }
            }
            unit_dict['quarterly'] = quarterly_plot

            for series in monthly_plot['data']['series']:
                quartlery_series = []
                last_year_and_quarter = None
                for idx, (year, month) in enumerate(categories):
                    quarter = map_month_to_quarter(month)
                    year_and_quarter = (year, quarter)
                    if year_and_quarter == last_year_and_quarter:
                        quartlery_series[-1] += series[idx]
                    else:
                        last_year_and_quarter = year_and_quarter
                        quartlery_series.append(series[idx])

        # And finally we fill caches
        for unit, unit_dict in plots.items():
            for frequency, plot in unit_dict.items():
                cache_key = f'stats/loans/{unit}/{frequency}'
                jsonified = json.dumps(plot)
                itgs.logger.print(Level.TRACE, '{} -> {}', cache_key, jsonified)
                encoded = jsonified.encode('utf-8')
                itgs.cache.set(cache_key, encoded)
