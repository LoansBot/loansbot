"""Moderators are sent a series of messages from the LoansBot that introduces
them to the tools available to them. We send each moderator one message per
day until they have received every message.
"""
from lbshared.lazy_integrations import LazyIntegrations
from lblogging import Level
from lbshared.responses import get_response
from .utils import sleep_until_hour_and_minute
import utils.reddit_proxy
import utils.mod_onboarding_utils
from pypika import PostgreSQLQuery as Query, Table, Parameter, Order
from pypika.functions import Max, CurTimestamp
import time


LOGGER_IDEN = 'runners/mod_onboarding_messages'


def main():
    version = time.time()
    with LazyIntegrations(logger_iden=LOGGER_IDEN) as itgs:
        itgs.logger.print(Level.DEBUG, 'Successfully booted up')

    while True:
        # 1PM UTC = 6AM PST = 9AM EST; at half to avoid conflict
        # with deprecated_alerts
        sleep_until_hour_and_minute(13, 30)
        send_messages(version)


def send_messages(version):
    with LazyIntegrations(logger_iden=LOGGER_IDEN) as itgs:
        itgs.logger.print(Level.TRACE, 'Sending moderator onboarding messages...')

        mod_onboarding_messages = Table('mod_onboarding_messages')
        itgs.read_cursor.execute(
            Query.from_(mod_onboarding_messages)
            .select(Max(mod_onboarding_messages.msg_order))
            .get_sql()
        )
        (max_msg_order,) = itgs.read_cursor.fetchone()
        if max_msg_order is None:
            itgs.logger.print(Level.DEBUG, 'There are no moderator onboarding messages.')
            return

        mod_onboarding_progress = Table('mod_onboarding_progress')
        moderators = Table('moderators')
        users = Table('users')
        itgs.read_cursor.execute(
            Query.from_(moderators)
            .join(users)
            .on(users.id == moderators.user_id)
            .left_join(mod_onboarding_progress)
            .on(mod_onboarding_progress.moderator_id == moderators.id)
            .select(
                users.id,
                moderators.id,
                users.username,
                mod_onboarding_progress.msg_order
            )
            .where(
                mod_onboarding_progress.msg_order.isnull() | (
                    mod_onboarding_progress.msg_order < Parameter('%s')
                )
            )
            .get_sql(),
            (max_msg_order,)
        )
        rows = itgs.read_cursor.fetchall()

        responses = Table('responses')
        titles = responses.as_('titles')
        bodies = responses.as_('bodies')
        for (user_id, mod_id, username, cur_msg_order) in rows:
            itgs.read_cursor.execute(
                Query.from_(mod_onboarding_messages)
                .join(titles).on(titles.id == mod_onboarding_messages.title_id)
                .join(bodies).on(bodies.id == mod_onboarding_messages.body_id)
                .select(
                    mod_onboarding_messages.msg_order,
                    titles.id,
                    titles.name,
                    bodies.id,
                    bodies.name
                )
                .where(
                    Parameter('%s').isnull() | (
                        mod_onboarding_messages.msg_order > Parameter('%s')
                    )
                )
                .orderby(mod_onboarding_messages.msg_order, order=Order.asc)
                .limit(1)
                .get_sql(),
                (cur_msg_order, cur_msg_order,)
            )
            (
                new_msg_order,
                title_id,
                title_name,
                body_id,
                body_name
            ) = itgs.read_cursor.fetchone()
            title_formatted = get_response(itgs, title_name, username=username)
            body_formatted = get_response(itgs, body_name, username=username)
            utils.reddit_proxy.send_request(
                itgs, 'mod_onboarding_messages', version, 'compose',
                {
                    'recipient': username,
                    'subject': title_formatted,
                    'body': body_formatted
                }
            )
            utils.mod_onboarding_utils.store_letter_message_with_id_and_names(
                itgs, user_id, title_id, title_name, body_id, body_name
            )
            if cur_msg_order is None:
                itgs.write_cursor.execute(
                    Query.into(mod_onboarding_progress)
                    .columns(
                        mod_onboarding_progress.moderator_id,
                        mod_onboarding_progress.msg_order
                    )
                    .insert(*(Parameter('%s') for _ in range(2)))
                    .get_sql(),
                    (mod_id, new_msg_order)
                )
            else:
                itgs.write_cursor.execute(
                    Query.update(mod_onboarding_progress)
                    .set(mod_onboarding_progress.msg_order, Parameter('%s'))
                    .set(mod_onboarding_progress.updated_at, CurTimestamp())
                    .where(mod_onboarding_progress.moderator_id == Parameter('%s'))
                    .get_sql(),
                    (new_msg_order, mod_id)
                )
            itgs.write_conn.commit()
            itgs.logger.print(
                Level.INFO,
                'Successfully sent moderator onboarding message (msg_order={}) to /u/{}',
                new_msg_order, username
            )
