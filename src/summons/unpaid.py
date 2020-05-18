"""Describes the summon for marking that a particular user is delinquent. All
the loans from that user to the lender will be marked as unpaid.
"""
from .summon import Summon
from parsing.parser import Parser
import parsing.ext_tokens
import utils.reddit_proxy
from pypika import PostgreSQLQuery as Query, Table, Parameter
from pypika.functions import Now
import loan_format_helper
from lblogging import Level

PARSER = Parser(
    '$unpaid',
    [
        {'token': parsing.ext_tokens.create_user_token(), 'optional': False}
    ]
)


class UnpaidSummon(Summon):
    def __init__(self):
        self.name = 'unpaid'

    def might_apply_to_comment(self, comment):
        """Determines if the $unpaid command might be in the comment

        Returns:
            True if $unpaid is in the comment, false otherwise
        """
        return PARSER.parse(comment['body']) is not None

    def handle_comment(self, itgs, comment, rpiden, rpversion):
        token_vals = PARSER.parse(comment['body'])
        lender_username = comment['author']
        borrower_username = token_vals[0]

        comment_permalink = 'https://reddit.com/comments/{}/redditloans/{}'.format(
            comment['link_fullname'][3:],
            comment['fullname'][3:]
        )

        loans = Table('loans')
        lenders = Table('lenders')
        borrowers = Table('borrowers')
        itgs.write_cursor.execute(
            loan_format_helper.create_loans_query()
            .where(lenders.username == Parameter('%s'))
            .where(borrowers.username == Parameter('%s'))
            .where(loans.unpaid_at.isnull())
            .where(loans.repaid_at.isnull())
            .get_sql(),
            (lender_username.lower(), borrower_username.lower())
        )
        row = itgs.write_cursor.fetchone()

        affected_pre = []
        while row is not None:
            affected_pre.append(loan_format_helper.fetch_loan(row))
            row = itgs.write_cursor.fetchone()

        if affected_pre:
            itgs.write_cursor.execute(
                Query.update(loans)
                .set(loans.unpaid_at, Now())
                .where(loans.id.isin([Parameter('%s') for _ in affected_pre]))
                .get_sql(),
                tuple(loan.id for loan in affected_pre)
            )

            loan_unpaid_events = Table('loan_unpaid_events')
            itgs.write_cursor.execute(
                Query.into(loan_unpaid_events)
                .columns(
                    loan_unpaid_events.loan_id,
                    loan_unpaid_events.unpaid
                )
                .insert(
                    *[(Parameter('%s'), True) for _ in affected_pre]
                )
                .get_sql(),
                tuple(loan.id for loan in affected_pre)
            )

            itgs.write_cursor.execute(
                loan_format_helper.create_loans_query()
                .where(loans.id.isin([Parameter('%s') for _ in affected_pre]))
                .get_sql(),
                tuple(loan.id for loan in affected_pre)
            )
            row = itgs.write_cursor.fetchone()
            affected_post = []
            while row is not None:
                affected_post.append(itgs.fetch_loan(row))
                row = itgs.write_cursor.fetchone()
        else:
            affected_post = []

        itgs.logger.print(
            Level.INFO,
            '/u/{} marked {} loan{} sent to /u/{} unpaid at {}',
            lender_username,
            len(affected_pre),
            's' if len(affected_pre) != 1 else '',
            borrower_username,
            comment_permalink
        )

        borrower_summary = loan_format_helper.get_and_format_all_or_summary(
            itgs, borrower_username)

        formatted_response = get_response(
            itgs,
            'unpaid',
            lender_username=lender_username,
            borrower_username=borrower_username,
            loans_before=loan_format_helper.format_loan_table(affected_pre),
            loans_after=loan_format_helper.format_loan_table(affected_post),
            borrower_summary=borrower_summary
        )

        utils.reddit_proxy.send_request(
            itgs, rpiden, rpversion, 'post_comment',
            {
                'parent': comment['fullname'],
                'text': formatted_response
            }
        )
