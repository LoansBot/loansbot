"""Entry point of the process which is scanning for requests to
recheck specific comments coming from the "lbrechecks" queue on
RabbitMQ. This usually happens when someone wants to edit their
comment because they made a mistake"""
from lblogging import Level
from lbshared.lazy_integrations import LazyIntegrations
from summon_helper import handle_comment
import utils.reddit_proxy
import json
import time

QUEUE_NAME = 'lbrechecks'
"""The queue we listen for requests on. The requests should be utf-8 encoded
json objects with the following shape:
{
    "link_fullname": "t3_xyz",
    "comment_fullname": "t1_abc"
}
"""


def main():
    """Listens for requests to recheck comments."""
    version = time.time()

    with LazyIntegrations(no_read_only=True, logger_iden='runners/rechecks.py#main') as itgs:
        itgs.logger.print(Level.DEBUG, 'Successfully booted up')

        while True:
            for row in itgs.channel.consume(QUEUE_NAME, inactivity_timeout=3000):
                (method_frame, properties, body_bytes) = row
                if method_frame is None:
                    itgs.logger.print(Level.TRACE, 'No rechecks in last 30 minutes; still alive')
                    continue

                body_str = body_bytes.decode('utf-8')
                try:
                    body = json.loads(body_str)
                except json.JSONDecodeError as exc:
                    itgs.logger.exception(
                        Level.WARN,
                        (
                            'Received non-json packet! Error info: '
                            'doc={}, msg={}, pos={}, lineno={}, colno={}'
                        ),
                        exc.doc, exc.msg, exc.pos, exc.lineno, exc.colno
                    )
                    itgs.channel.basic_nack(method_frame.delivery_tag, requeue=False)
                    continue

                errors = get_packet_errors(body)
                if errors:
                    itgs.logger.print(
                        Level.WARN,
                        'Received packet {} which had {} errors:\n- {}',
                        body,
                        len(errors),
                        '\n- '.join(errors)
                    )
                    itgs.channel.basic_nack(method_frame.delivery_tag, requeue=False)
                    continue

                rp_body = utils.reddit_proxy.send_request(
                    itgs, 'rechecks', version, 'lookup_comment', {
                        'link_fullname': body['link_fullname'],
                        'comment_fullname': body['comment_fullname']
                    }
                )
                if rp_body['type'] != 'copy':
                    itgs.logger.print(
                        Level.INFO,
                        'Got unexpected response type {} for comment lookup request '
                        'during recheck; recheck suppressed (comment mightn to exist)',
                        rp_body['type']
                    )
                    itgs.channel.basic_nack(method_frame.delivery_tag, requeue=False)
                    continue

                comment = rp_body['info']
                handle_comment(itgs, comment, 'rechecks', version)
                itgs.channel.basic_ack(method_frame.delivery_tag)


def get_packet_errors(packet):
    result = []

    if not isinstance(packet, dict):
        result.append('Packet should be a dict, got {}'.format(type(packet)))
        return result

    if not isinstance(packet.get('link_fullname'), str):
        result.append(
            'packet[\'link_fullname\'] should be a str, got {} (a {})',
            packet.get('link_fullname'),
            type(packet.get('link_fullname'))
        )

    if not isinstance(packet.get('comment_fullname'), str):
        result.append(
            'packet[\'comment_fullname\'] should be a str, got {} (a {})',
            packet.get('comment_fullname'),
            type(packet.get('comment_fullname'))
        )

    return result
