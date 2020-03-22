"""This is the entry point of the comment-scanning daemon subprocess."""
import helper
from lblogging import Logger, Level
import time
import os
import uuid
import json
from pypika import PostgreSQLQuery as Query, Table, Parameter
import traceback


def main():
    """Connects to the database and AMQP service, then periodically scans for
    new comments in relevant subreddits."""
    summons = []
    version = time.time()

    connection = helper.connect_to_database()
    logger = Logger(os.environ['APPNAME'], 'runners/comments.py', connection)
    logger.prepare()
    logger.print(Level.TRACE, 'Successfully initialized at version={}', version)
    logger.connection.commit()
    logger.close()
    connection.close()

    connection = None
    logger = None

    while True:
        connection = helper.connect_to_database()
        cursor = connection.cursor()
        logger = Logger(os.environ['APPNAME'], 'runners/comments.py', connection)
        logger.prepare()
        amqp = helper.connect_to_amqp(logger)

        scan_for_comments(connection, cursor, logger, amqp, version, summons)

        logger.close()
        cursor.close()
        connection.close()
        amqp.close()
        try:
            time.sleep(60)
        except:  # noqa
            break


def scan_for_comments(conn, cursor, logger, amqp, version, summons):
    """Scans for new comments using the given logger and amqp connection"""
    logger.print(Level.TRACE, 'Scanning for new comments..')
    logger.connection.commit()

    channel = amqp.channel()
    after = None

    handled_fullnames = Table('handled_fullnames')

    while True:
        comments, after = _fetch_comments(logger, channel, version, after)

        if not comments:
            logger.print(Level.DEBUG, 'Found no more comments!')
            logger.connection.commit()
            break

        fullnames = [comm['fullname'] for comm in comments]
        cursor.execute(
            Query.from_(handled_fullnames)
            .select('fullname')
            .where(handled_fullnames.fullname.isin([Parameter('%s') for f in fullnames]))
            .get_sql(),
            fullnames
        )
        rows = cursor.fetchall()
        conn.commit()

        logger.print(Level.TRACE, 'Found {} new comments', len(fullnames) - len(rows))
        logger.connection.commit()

        if len(fullnames) == len(rows):
            break
        num_to_find = len(fullnames) - len(rows)
        seen_set = set(row[0] for row in rows)
        for comment in comments:
            if comment['fullname'] in seen_set:
                continue
            logger.print(Level.TRACE, 'Checking comment {}', comment['fullname'])

            summon_to_use = None
            for summon in summons:
                if not summon.might_apply_to_comment(comment):
                    continue
                summon_to_use = summon
                break

            num_to_find = num_to_find - 1
            if summon_to_use is not None:
                # TODO check author

                logger.print(Level.DEBUG, 'Using summon {}', summon_to_use.name)
                try:
                    summon_to_use.handle_comment(logger, conn, amqp, channel, comment)
                except:  # noqa
                    conn.rollback()
                    logger.exception(
                        Level.WARN,
                        'While using summon {} on comment {}',
                        summon_to_use.name, comment
                    )
                    traceback.print_exc()
                    logger.connection.commit()

                conn.commit()
                logger.connection.commit()

            cursor.execute(
                Query.into(handled_fullnames)
                .columns('fullname')
                .insert(Parameter('%s'))
                .get_sql(),
                (comment['fullname'],)
            )
            conn.commit()

            logger.print(Level.TRACE, 'Finished handling comment {}', comment['fullname'])
            logger.connection.commit()
            if num_to_find <= 0:
                break


def _fetch_comments(logger, channel, version, after=None):
    reddit_queue = os.environ['AMQP_REDDIT_PROXY_QUEUE']
    response_queue = os.environ['AMQP_RESPONSE_QUEUE_PREFIX'] + '-comments'
    subreddits = os.environ['SUBREDDITS'].split(',')
    channel.queue_declare(reddit_queue)
    channel.queue_declare(response_queue)

    msg_uuid = str(uuid.uuid4())

    channel.basic_publish(
        '',
        reddit_queue,
        json.dumps({
            'type': 'subreddit_comments',
            'response_queue': response_queue,
            'uuid': msg_uuid,
            'version_utc_seconds': version,
            'sent_at': time.time(),
            'args': {
                'subreddit': subreddits,
                'after': after
            }
        })
    )

    logger.print(
        Level.TRACE,
        'Requesting subreddit comments (subreddits: {}) on request queue {} '
        'with the response sent to {}; our message uuid is {}',
        subreddits, reddit_queue, response_queue, msg_uuid
    )
    logger.connection.commit()

    for method_frame, properties, body_bytes in channel.consume(response_queue, inactivity_timeout=600):  # noqa: E501
        if method_frame is None:
            print(f'Still waiting on response from message {msg_uuid}!')
            logger.print(Level.ERROR, 'Got no response for message {} in 10 minutes!', msg_uuid)
            logger.connection.commit()
            continue

        body_str = body_bytes.decode('utf-8')
        body = json.loads(body_str)

        if body['uuid'] != msg_uuid:
            logger.print(
                Level.DEBUG,
                'Ignoring message {} to our response queue (expecting {})',
                body['uuid'], msg_uuid
            )
            logger.connection.commit()
            channel.basic_nack(method_frame.delivery_tag, requeue=False)
            continue

        logger.print(Level.TRACE, 'Found response to {}', msg_uuid)
        logger.connection.commit()
        channel.basic_ack(method_frame.delivery_tag)
        break

    channel.cancel()

    if body['type'] != 'copy':
        logger.print(
            Level.INFO,
            'Got unexpected response type {} from message {} '
            '- treating as if there are no messages',
            body['type'], msg_uuid
        )
        logger.connection.commit()
        return [], None
    return body['info']['comments'], body['info'].get('after')
