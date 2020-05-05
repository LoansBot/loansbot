"""Describes the generic interface that summons are expected to support"""


class Summon:
    """An operation which can be triggered by comments or link posts on reddit.

    :param name: A unique name for this summon.
    """
    def might_apply_to_comment(self, comment):
        """Determines if this summon applies to the given comment. This should
        be fairly fast, since every comment will be checked by every summon.
        Further, this should have no side-effects.

        :param comment: The comment dictionary from the reddit-proxy
        :type comment: dict
        :returns: True if this summon might apply to the given comment and
            false otherwise.
        """
        raise NotImplementedError()

    def handle_comment(self, itgs, comment, rpiden, rpversion):
        """Handles the given comment. This is expected to have side-effects,
        such as saving things to the database, logging, and responding via
        reddit using the reddit proxy.

        :param itgs: The LazyIntegrations to use for connecting to other
            services
        :param comment: The comment that needs to be handled
        :param rpiden: The identifier suffix to use with the reddit proxy
        :param rpversion: The version to use with the reddit proxy
        """
        raise NotImplementedError()
