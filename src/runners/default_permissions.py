"""This runner listens for users signing up via the website and assigns them
the default permissions.
"""
from lblogging import Level
from lbshared.lazy_integrations import LazyIntegrations
from lbshared.pypika_crits import exists
from pypika import PostgreSQLQuery as Query, Table, Parameter
from pypika.functions import Count
import utils.reddit_proxy
import json
import time
import os


DEFAULT_PERMISSIONS = tuple(os.getenv('DEFAULT_PERMISSIONS', '').split(','))
"""The list of permissions we grant to new users when they sign up"""


def main():
    version = time.time()

    with LazyIntegrations(logger_iden='runners/default_permissions.py#main') as itgs:
        itgs.logger.print(Level.DEBUG, 'Successfully booted up')

    with LazyIntegrations(logger_iden='runners/default_permissions.py#main') as itgs:
        # Keeps as few connections alive as possible when not working
        consumer_channel = itgs.amqp.channel()
        consumer_channel.exchange_declare('events', 'topic')
        queue_declare_result = consumer_channel.queue_declare('', exclusive=True)
        queue_name = queue_declare_result.method.queue

        consumer_channel.queue_bind(queue_name, 'events', 'user.signup')
        consumer = consumer_channel.consume(queue_name, inactivity_timeout=600)
        for method_frame, props, body_bytes in consumer:
            if method_frame is None:
                continue
            body_str = body_bytes.decode('utf-8')
            body = json.loads(body_str)
            handle_user_signup(version, body)
            consumer_channel.basic_ack(method_frame.delivery_tag)
        consumer.cancel()


def handle_user_signup(version, body):
    """Called when we detect that a user has just signed up. Assigns their
    human authentication method some default permissions.

    Arguments:
    - `version (float)`: Our version string when using the reddit proxy.
    - `body (dict)`: The event body. Has the following keys:
      - `user_id (int)`: The id of the user who just signed up.
    """
    with LazyIntegrations(
            logger_iden='runners/default_permissions.py#handle_user_signup',
            no_read_only=True) as itgs:
        itgs.logger.print(
            Level.TRACE,
            'Detected user signup: id={}',
            body['user_id']
        )

        usrs = Table('users')
        itgs.read_cursor.execute(
            Query.from_(usrs)
            .select(usrs.username)
            .where(usrs.id == Parameter('%s'))
            .get_sql(),
            (body['user_id'],)
        )
        row = itgs.read_cursor.fetchone()
        if row is None:
            itgs.logger.print(
                Level.WARN,
                'Race condition detected! Got user signup event for user id {} ' +
                'but that user is not in the database. They will not receive ' +
                'the expected default permissions.',
                body['user_id']
            )
            return
        (username,) = row

        passwd_auths = Table('password_authentications')
        itgs.read_cursor.execute(
            Query.from_(passwd_auths)
            .select(passwd_auths.id)
            .where(passwd_auths.user_id == Parameter('%s'))
            .where(passwd_auths.human.eq(True))
            .get_sql(),
            (body['user_id'],)
        )
        row = itgs.read_cursor.fetchone()
        if row is None:
            itgs.logger.print(
                Level.WARN,
                'Race condition detected! Got user signup event for user id {} ' +
                'which corresponds to user /u/{} but that user does not have a ' +
                'password set! They will not get the default permissions.',
                body['user_id'], username
            )
            return

        (passwd_auth_id,) = row

        perms = Table('permissions')
        passwd_auth_perms = Table('password_auth_permissions')
        passwd_auth_perms_inner = passwd_auth_perms.as_('pap_inner')
        itgs.write_cursor.execute(
            Query.into(passwd_auth_perms)
            .columns(
                passwd_auth_perms.password_authentication_id,
                passwd_auth_perms.permission_id
            )
            .from_(perms)
            .select(
                Parameter('%s'),
                perms.id
            )
            .where(perms.name.isin([Parameter('%s') for _ in DEFAULT_PERMISSIONS]))
            .where(
                exists(
                    Query.from_(passwd_auth_perms_inner)
                    .where(passwd_auth_perms_inner.password_authentication_id == Parameter('%s'))
                    .where(passwd_auth_perms_inner.permission_id == perms.id)
                )
                .negate()
            )
            .get_sql(),
            (
                passwd_auth_id,
                *DEFAULT_PERMISSIONS,
                passwd_auth_id
            )
        )
        itgs.write_conn.commit()

        itgs.logger.print(
            Level.INFO,
            '/u/{} just signed up and was granted default permissions',
            username
        )
