"""This runner scans for users which are using authenticated endpoints and
sends them the necessary reddit personal messages. Specifically, this will
send pms to any user which used a deprecated endpoint in the last calendar
month but did not receive an alert. If it within 30 days of sunsetting this
frequency increases to every 3 days.
"""
from lblogging import Level
from lbshared.lazy_integrations import LazyIntegrations
from lbshared.queries import convert_numbered_args
from pypika import PostgreSQLQuery as Query, Table, Parameter, Interval, Not
from pypika.functions import Max, Min, Count, Now, Function, Floor
from lbshared.pypika_crits import ExistsCriterion as Exists
from datetime import datetime, timedelta
import utils.reddit_proxy
import time


class MissingAlertInfo:
    """A simple slots object for the rows returned from get_missing_alerts,
    which allows dot-access for each element while avoiding excessive
    overhead.
    """
    __slots__ = (
        'user_id', 'username', 'endpoint_id', 'first_use_in_interval',
        'last_use_in_interval', 'count_in_interval'
    )

    def __init__(
            self, user_id, username, endpoint_id, first_use_in_interval,
            last_use_in_interval, count_in_interval):
        self.user_id = user_id
        self.username = username
        self.endpoint_id = endpoint_id
        self.first_use_in_interval = first_use_in_interval
        self.last_use_in_interval = last_use_in_interval
        self.count_in_interval = count_in_interval


class EndpointInfoForAlert:
    """A simple slots object for endpoint information required for making
    useful alerts.
    """
    __slots__ = ('id', 'slug', 'path', 'verb', 'deprecated_on', 'sunsets_on')

    def __init__(self, id, slug, path, verb, deprecated_on, sunsets_on):
        self.id = id
        self.slug = slug
        self.path = path
        self.verb = verb
        self.deprecated_on = deprecated_on
        self.sunsets_on = sunsets_on


class DatePart(Function):
    def __init__(self, part, expr):
        super(DatePart, self).__init__('DATE_PART', part, expr)


def main():
    with LazyIntegrations(logger_iden='runners/deprecated_alerts.py#main') as itgs:
        itgs.logger.print(Level.DEBUG, 'Successfully booted up')

    version = time.time()

    while True:
        # 1pm utc = 6am pst = 9am est -> a good time for sending reddit messages
        # we want people to read and process
        sleep_until_hour_and_minute(13, 0)
        send_messages(version)


def send_messages(version):
    alert_executors = [
        execute_get_missing_initial_alerts,
        execute_get_missing_alerts_by_calendar_month,
        execute_get_missing_alerts_by_urgent
    ]
    with LazyIntegrations(no_read_only=True) as itgs:
        for alert_executor in alert_executors:
            alert_executor(itgs)
            alerts_grouped_by_user_id = group_alerts_by_user_id(itgs)
            unique_endpoint_ids = get_unique_endpoint_ids(alerts_grouped_by_user_id)
            endpoint_info_by_id = get_endpoint_info_by_id(itgs, tuple(unique_endpoint_ids))
            title_message_format, body_message_format = get_letter_message_format(itgs, 'reminder')
            send_grouped_alerts(
                itgs,
                alerts_grouped_by_user_id,
                endpoint_info_by_id,
                title_message_format,
                body_message_format,
                'reminder',
                version
            )


def get_letter_message_format(itgs, alert_type):
    """Get the body and title format for the given deprecated alert type.

    Arguments:
    - `itgs (LazyIntegrations)`: How to connect to the database
    - `alert_type (str)`: A unique identifier for the alert type being sent;
      see `endpoint_alerts` for valid alert types.

    Returns:
    - `title_format (str)`: The format for the title of the message
    - `body_format (str)`: The format for the body of the message.
    """
    responses = Table('responses')
    itgs.read_cursor.execute(
        Query.from_(responses).select(responses.response_body)
        .where(responses.name.isin(tuple(Parameter('%s') for _ in range(2))))
        .orderby(responses.name)
        .get_sql(),
        (
            f'deprecated_alerts_{alert_type}_body',
            f'deprecated_alerts_{alert_type}_title'
        )
    )
    rows = itgs.read_cursor.fetchall()
    return rows[1][0], rows[0][0]


def get_unique_endpoint_ids(alerts_grouped_by_user_id):
    """Returns the unique endpoint ids, as a set, that are in any of the given
    alerts which are grouped by user id.

    Arguments:
    - `alerts_grouped_by_user_id (list[list[MissingAlertInfo]])`: The alerts

    Returns:
    - `unique_endpoint_ids (set[int])`: The unique endpoint ids in all the alerts
    """
    unique_endpoint_ids = set()
    for grouped_alerts in alerts_grouped_by_user_id:
        for alert in grouped_alerts:
            unique_endpoint_ids.add(alert.endpoint_id)
    return unique_endpoint_ids


def get_endpoint_info_by_id(itgs, endpoint_ids):
    """Fetch the endpoint info (as EndpointInfoForAlert) for each endpoint
    specified. We prefer to do this over including endpoint information in
    the main request because we expect there to be significantly fewer
    endpoints than users so it would cause a lot of duplicated memory usage
    to include endpoint information in the MissingAlertInfo objects.

    Arguments:
    - `itgs (LazyIntegrations)`: How to connect to the database
    - `endpoint_ids (tuple[int])`: The endpoint ids to fetch information on

    Returns:
    - `info_by_id (dict[int, EndpointInfoForAlert])` A mapping from endpoint ids
      to the corresponding information.
    """
    endpoint_info_by_id = {}
    if not endpoint_ids:
        return endpoint_info_by_id

    endpoints = Table('endpoints')
    itgs.read_cursor.execute(
        Query.from_(endpoints)
        .select(
            endpoints.id,
            endpoints.slug,
            endpoints.path,
            endpoints.verb,
            endpoints.deprecated_on,
            endpoints.sunsets_on
        )
        .where(
            endpoints.id.isin(tuple(
                Parameter('%s') for _ in endpoint_ids
            ))
        )
        .get_sql(),
        endpoint_ids
    )
    row = itgs.read_cursor.fetchone()
    while row is not None:
        endpoint_info_by_id[row[0]] = EndpointInfoForAlert(*row)
        row = itgs.read_cursor.fetchone()
    return endpoint_info_by_id


def group_alerts_by_user_id(itgs):
    """Reads the alerts in itgs.read_cursor's result set and groups them into
    a list of lists, where each inner list contains all the alerts (as
    MissingAlertInfo) for that user.

    This assumes the read cursor was fetched as if by
    `execute_get_missing_alerts`
    """
    alerts_grouped_by_user_id = []
    current_info = None

    row = itgs.read_cursor.fetchone()
    if row is not None:
        current_info = [MissingAlertInfo(*row)]
        row = itgs.read_cursor.fetchone()

    while row is not None:
        alert_info = MissingAlertInfo(*row)
        if current_info[0].user_id != alert_info.user_id:
            alerts_grouped_by_user_id.append(current_info)
            current_info = [alert_info]
        else:
            current_info.append(alert_info)
        row = itgs.read_cursor.fetchone()

    if current_info is not None:
        alerts_grouped_by_user_id.append(current_info)

    return alerts_grouped_by_user_id


def execute_get_missing_initial_alerts(itgs):
    endpoint_users = Table('endpoint_users')
    endpoint_alerts = Table('endpoint_alerts')
    users = Table('users')
    usage_after_filters = Table('usage_after_filters')

    query = (
        Query.with_(
            Query.from_(endpoint_users)
            .where(
                Not(
                    Exists(
                        Query.from_(endpoint_alerts)
                        .where(endpoint_alerts.endpoint_id == endpoint_users.endpoint_id)
                        .where(endpoint_alerts.user_id == endpoint_users.user_id)
                    )
                )
            )
            .select(
                endpoint_users.endpoint_id.as_('endpoint_id'),
                endpoint_users.user_id.as_('user_id'),
                Min(endpoint_users.created_at).as_('first_usage'),
                Max(endpoint_users.created_at).as_('last_usage'),
                Count(endpoint_users.id).as_('count_usage')
            )
            .groupby(
                endpoint_users.endpoint_id,
                endpoint_users.user_id
            ),
            'usage_after_filters'
        )
        .from_(usage_after_filters)
        .join(users)
        .on(users.id == usage_after_filters.user_id)
        .select(
            usage_after_filters.user_id,
            users.username,
            usage_after_filters.endpoint_id,
            usage_after_filters.first_usage,
            usage_after_filters.last_usage,
            usage_after_filters.count_usage
        )
        .orderby(usage_after_filters.user_id)
    )
    sql = query.get_sql()
    itgs.read_cursor.execute(sql)


def execute_get_missing_alerts_by_calendar_month(itgs):
    """Gets the set of all alerts which should have been sent out already
    according to the business rule regarding alerting users which have used
    deprecated endpoints once per month.

    The result is sorted by user id.

    Arguments:
    - `itgs (LazyIntegrations)`: The integrations to use for sending alerts.

    Returns:
    - Same as `get_missing_alerts`.
    """
    curtime = datetime.now()
    ignore_before = datetime(
        year=curtime.year if curtime.month > 1 else curtime.year - 1,
        month=curtime.month - 1 if curtime.month > 1 else 12,
        day=1
    )
    ignore_after = datetime(
        year=curtime.year,
        month=curtime.month,
        day=1
    )

    def bonus_filters(query, add_param, endpoint_users, **kwargs):
        return (
            query.where(endpoint_users.created_at >= add_param(ignore_before))
            .where(endpoint_users.created_at <= add_param(ignore_after))
        )

    execute_get_missing_alerts(itgs, bonus_filters)


def execute_get_missing_alerts_by_urgent(itgs):
    """Gets the set of all alerts which should have been sent out already
    according to the business rule regarding alerting users which have used
    deprecated endpoints in the final month before sunsetting.

    The result is sorted by user id.

    Arguments:
    - `itgs (LazyIntegrations)`: The integrations to use for sending alerts.

    Returns:
    - Same as `get_missing_alerts`.
    """
    def bonus_filters(query, add_param, endpoint_users, **kwargs):
        endpoints = Table('endpoints')
        return (
            query
            .where(
                Exists(
                    Query.from_(endpoints)
                    .where(endpoints.id == endpoint_users.endpoint_id)
                    .where(endpoints.sunsets_on > Now() - Interval(days=27))
                    .where(endpoints.sunsets_on < Now())
                    .where(
                        DatePart('day', endpoints.sunsets_on - Now()) < (
                            30 - Floor(
                                DatePart(
                                    'day',
                                    endpoint_users.created_at - endpoints.sunsets_on
                                ) / 3
                            ) * 3
                        )
                    )
                )
            )
        )

    execute_get_missing_alerts(itgs, bonus_filters)


def execute_get_missing_alerts(itgs, bonus_filters):
    """Executes the read to get all alerts which should have been sent out already
    for endpoint usage. The endpoint users is filtered using `bonus_filters`.
    If `bonus_filters` is a no-op then this function will return one row
    for each use of an endpoint by any user for which there is no later alert.

    The result is sorted by user id.

    Arguments:
    - `itgs (LazyIntegrations)`: The integrations to use for sending alerts.
    - `bonus_filters (callable)`: A callable which accepts the query, a
      callable which accepts an argument and returns the Parameter which will
      refer to that argment, and keyword arguments for each Table reference we
      have. This should return the new Query to use after filtering the results.

    Returns (via `itgs.read_cursor.fetchall()`):
    - `rows (list)`: A list of lists, where each inner list has the following
      elements:
      - `user_id (int)`: The id of the user which should be sent an alert.
      - `username (str)`: The username of the user with id `user_id`.
      - `endpoint_id (int)`: The id of the endpoint the user used
      - `endpoint_slug (str)`: The slug of the endpoint with id `endpoint_id`
      - `first_use_in_interval (datetime)`: The earliest time within the
        interval that the user used the endpoint.
      - `last_use_in_interval (datetime)`: The latest time within the interval
        that the user used the endpoint.
      - `count_in_interval (int)`: The number of times the user used the endpoint
        within the interval.
    """
    endpoint_users = Table('endpoint_users')
    endpoint_alerts = Table('endpoint_alerts')
    most_recent_alerts = Table('most_recent_alerts')
    usage_after_filters = Table('usage_after_filters')

    users = Table('users')

    args = []

    def add_param(arg):
        args.append(arg)
        return Parameter(f'${len(args)}')

    query = (
        Query.with_(
            Query.from_(endpoint_alerts)
            .select(
                endpoint_alerts.endpoint_id.as_('endpoint_id'),
                endpoint_alerts.user_id.as_('user_id'),
                Max(endpoint_alerts.sent_at).as_('max_sent_at')
            )
            .groupby(
                endpoint_alerts.endpoint_id,
                endpoint_alerts.user_id
            ),
            'most_recent_alerts'
        ).with_(
            bonus_filters(
                Query.from_(endpoint_users)
                .join(most_recent_alerts)
                .on(
                    (most_recent_alerts.endpoint_id == endpoint_users.endpoint_id)
                    & (most_recent_alerts.user_id == endpoint_users.user_id)
                )
                .select(
                    endpoint_users.endpoint_id.as_('endpoint_id'),
                    endpoint_users.user_id.as_('user_id'),
                    Min(endpoint_users.created_at).as_('first_usage'),
                    Max(endpoint_users.created_at).as_('last_usage'),
                    Count(endpoint_users.id).as_('count_usage')
                )
                .where(endpoint_users.user_id.notnull())
                .where(endpoint_users.created_at > most_recent_alerts.max_sent_at)
                .groupby(
                    endpoint_users.endpoint_id,
                    endpoint_users.user_id
                ),
                add_param,
                endpoint_users=endpoint_users,
                endpoint_alerts=endpoint_alerts,
                most_recent_alerts=most_recent_alerts
            ),
            'usage_after_filters'
        )
        .from_(usage_after_filters)
        .join(users)
        .on(users.id == usage_after_filters.user_id)
        .select(
            usage_after_filters.user_id,
            users.username,
            usage_after_filters.endpoint_id,
            usage_after_filters.first_usage,
            usage_after_filters.last_usage,
            usage_after_filters.count_usage
        )
        .orderby(usage_after_filters.user_id)
    )

    (sql, ordered_args) = convert_numbered_args(query.get_sql(), args)
    itgs.read_cursor.execute(sql, ordered_args)


def send_grouped_alerts(
        itgs, alerts_grouped_by_user_id, endpoint_info_by_id, title_format, body_format,
        alert_type, version):
    """Send all the alerts specified in `alerts_grouped_by_user_id` using the
    pre-fetched endpoint information in `endpoint_info_by_id`.
    """
    for alerts in alerts_grouped_by_user_id:
        send_alerts_for_user(
            itgs, alerts, endpoint_info_by_id, title_format, body_format,
            alert_type, version
        )


def send_alerts_for_user(
        itgs, alerts_for_user, endpoint_info_by_id, title_format, body_format,
        alert_type, version):
    """Sends an alert to the given user to warn them that they are still using
    deprecated endpoints and inform them of the deprecation/sunset schedule. This
    will store that we sent them an alert in `endpoint_alerts` and will wait for
    a response from the reddit proxy so that we don't cause a really long queue
    to build up.
    """
    date_fmt = '%b %d, %Y'
    endpoints_table_lines = [
        'Endpoint | Deprecated on | Sunsets on',
        ':--|:--|:--'
    ]

    for alert in alerts_for_user:
        alert: MissingAlertInfo
        endpoint: EndpointInfoForAlert = endpoint_info_by_id[alert.endpoint_id]
        endpoints_table_lines.append(
            f'[{endpoint.slug}](https://redditloans.com/endpoints.html?slug={endpoint.slug})|'
            + endpoint.deprecated_on.strftime(date_fmt) + '|'
            + endpoint.sunsets_on.strftime(date_fmt)
        )

    username = alerts_for_user[0].username
    title = title_format.format(username=username)
    body = body_format.format(
        username=username,
        endpoints_table='\n'.join(endpoints_table_lines)
    )

    endpoint_alerts = Table('endpoint_alerts')
    query = (
        Query.into(endpoint_alerts)
        .columns(
            endpoint_alerts.endpoint_id,
            endpoint_alerts.user_id,
            endpoint_alerts.alert_type
        )
    )
    args = []
    for alert in alerts_for_user:
        query = query.insert(*(Parameter('%s') for _ in range(3)))
        args.append(alert.endpoint_id)
        args.append(alert.user_id),
        args.append(alert_type)

    itgs.write_cursor.execute(query.get_sql(), args)
    itgs.write_conn.commit()
    utils.reddit_proxy.send_request(
        itgs, 'deprecated_alerts', version, 'compose',
        {
            'recipient': username,
            'subject': title,
            'body': body
        }
    )


def sleep_until_hour_and_minute(hour, minute):
    curtime = datetime.now()
    target_time = datetime(
        year=curtime.year,
        month=curtime.month,
        day=curtime.day,
        hour=hour,
        minute=minute
    )
    if curtime.hour > hour or curtime.hour == hour and curtime.minute >= minute:
        target_time += timedelta(days=1)
    time.sleep(target_time.timestamp() - time.time())
