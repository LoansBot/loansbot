"""This utility is responsible for proxying requests to reddit through the
reddit proxy.
"""
from lbshared.lazy_integrations import LazyIntegrations as LazyItgs

def send_request(itgs: LazyItgs, iden: str, version: float, typ: str, args: dict) -> dict:
    """Sends a request with the given type and arguments to the reddit proxy,
    waits for the response, and then parses and returns it. Raises an error if
    there is an issue getting the response.

    Arguments:
        itgs (LazyItgs): The service for connecting to networked components
        iden (str): An identifier for the response queue. Each response queue
            gives the impression of serialness - if a client drops their
            requests and responses are dropped. Hence it's important that two
            different threads/processes don't share the same identifier.
        version (float): The time at which this response queue was initialized,
            allowing the proxy server to drop requests which are stale.
        typ (str): The identifier for the request to be made
        args (dict): The arguments to forward alongside the request.

    Returns:
        The parsed response from the server. The uuid is included but has
        already been verified.
    """
    reddit_queue = os.environ['AMQP_REDDIT_PROXY_QUEUE']
    response_queue = os.environ['AMQP_RESPONSE_QUEUE_PREFIX'] + '-' + iden
    itgs.channel.queue_declare(reddit_queue)
    itgs.channel.queue_declare(response_queue)

    msg_uuid = str(uuid.uuid4())

    itgs.channel.basic_publish(
        '',
        reddit_queue,
        json.dumps({
            'type': typ,
            'response_queue': response_queue,
            'uuid': msg_uuid,
            'version_utc_seconds': version,
            'sent_at': time.time(),
            'args': args
        })
    )

    itgs.logger.print(
        Level.TRACE,
        'Sent request of type {} with response queue {} and version {} uuid={}',
        typ, response_queue, version, msg_uuid
    )


    consumer = itgs.channel.consume(response_queue, inactivity_timeout=600)
    for method_frame, properties, body_bytes in consumer:
        if method_frame is None:
            itgs.logger.print(
                Level.ERROR,
                'Got no response for message {} (type={}) in 10 minutes!',
                msg_uuid, typ
            )
            itgs.logger.connection.commit()
            continue

        body_str = body_bytes.decode('utf-8')
        body = json.loads(body_str)

        if body['uuid'] != msg_uuid:
            itgs.logger.print(
                Level.DEBUG,
                'Ignoring message {} to {} (expecting {})',
                body['uuid'], response_queue, msg_uuid
            )
            itgs.channel.basic_nack(method_frame.delivery_tag, requeue=False)
            continue

        itgs.logger.print(
            Level.TRACE,
            'Found response to request {} on {} (type={})',
            msg_uuid, response_queue, typ
        )
        itgs.channel.basic_ack(method_frame.delivery_tag)
        itgs.channel.cancel()
        return body
