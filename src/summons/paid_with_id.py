"""Describes the summon for marking that a particular loan, identified by its
id, has had a repayment. This may only be a partial repayment.
"""
from .summon import Summon
from parsing.parser import Parser
import parsing.ext_tokens
import utils.reddit_proxy
from pypika import Table, Parameter, Order
import loan_format_helper
import utils.paid_utils
from lblogging import Level
from lbshared.responses import get_response


PARSER = Parser(
    '$paid_with_id',
    [
        {'token': parsing.ext_tokens.create_uint_token(), 'optional': False},
        {'token': parsing.ext_tokens.create_money_token(), 'optional': False}
    ]
)


class PaidWithIdSummon(Summon):
    def __init__(self):
        self.name = 'paid_with_id'

    def might_apply_to_comment(self, comment):
        """Determines if the $paid_with_id command might be in the comment

        Returns:
            True if $paid_with_id is in the comment, false otherwise
        """
        return PARSER.parse(comment['body']) is not None

    def handle_comment(self, itgs, comment, rpiden, rpversion):
        token_vals = PARSER.parse(comment['body'])
        lender_username = comment['author']
        loan_id = token_vals[0]
        amt = token_vals[1]

        comment_permalink = 'https://reddit.com/comments/{}/redditloans/{}'.format(
            comment['link_fullname'][3:],
            comment['fullname'][3:]
        )

        loans = Table('loans')
        itgs.write_cursor.execute(
            loan_format_helper.create_loans_query()
            .where(loans.id == Parameter('%s'))
            .get_sql(),
            (loan_id,)
        )
        row = itgs.write_cursor.fetchone()
        if row is None:
            itgs.logger.print(
                Level.INFO,
                '/u/{} tried to mark non-existent loan {} as paid at {}',
                lender_username, loan_id, comment_permalink
            )
            self.suggest_loan_ids(
                'paid_with_id_not_found', itgs, comment['fullname'],
                lender_username, loan_id, amt, rpiden, rpversion
            )
            return

        loan = loan_format_helper.fetch_loan(row)
        if loan.lender.lower() != lender_username.lower():
            itgs.logger.print(
                Level.INFO,
                '/u/{} tried to mark loan {} (lender: {}, borrower: {}) as paid at {}',
                lender_username, loan_id, loan.lender, loan.borrower, comment_permalink
            )
            self.suggest_loan_ids(
                'paid_with_id_wrong_lender', itgs, comment['fullname'],
                lender_username, loan_id, amt, rpiden, rpversion, loan=loan
            )
            return

        if loan.repaid_at is not None:
            itgs.logger.print(
                Level.INFO,
                '/u/{} tried to mark loan {} (already repaid) as paid at {}',
                lender_username, loan_id, comment_permalink
            )
            self.suggest_loan_ids(
                'paid_with_id_already_repaid', itgs, comment['fullname'],
                lender_username, loan_id, amt, rpiden, rpversion, loan=loan
            )
            return

        (applied, remaining, _) = utils.paid_utils.apply_repayment(itgs, loan_id, amt)

        itgs.write_cursor.execute(
            loan_format_helper.create_loans_query()
            .where(loans.id == Parameter('%s'))
            .get_sql(),
            (loan_id,)
        )
        loan_after = loan_format_helper.fetch_loan(itgs.write_cursor.fetchone())

        itgs.logger.print(
            Level.INFO,
            '/u/{} repaid /u/{} {} ({} ignored) toward loan {} - permalink: {}',
            loan.borrower, lender_username, applied, remaining, loan_id,
            comment_permalink
        )

        formatted_response = get_response(
            itgs,
            'paid_with_id',
            lender_username=lender_username,
            borrower_username=loan.borrower,
            loan_before=loan_format_helper.format_loan_table([loan], include_id=True),
            loan_after=loan_format_helper.format_loan_table([loan_after], include_id=True),
            amount=str(amt),
            applied=str(applied),
            remaining=str(remaining)
        )

        utils.reddit_proxy.send_request(
            itgs, rpiden, rpversion, 'post_comment',
            {
                'parent': comment['fullname'],
                'text': formatted_response
            }
        )

    def suggest_loan_ids(
            self, resp_name, itgs, comment_fullname, lender_username, loan_id, amt,
            rpiden, rpversion, loan=None):
        loans = Table('loans')
        lenders = Table('lenders')
        itgs.write_cursor.execute(
            loan_format_helper.create_loans_query()
            .where(lenders.username == Parameter('%s'))
            .where(loans.repaid_at.isnull())
            .orderby(loans.created_at, order=Order.desc)
            .limit(7)
            .get_sql(),
            (lender_username.lower(),)
        )

        loans = []
        row = itgs.write_cursor.fetchone()
        while row is not None:
            loans.append(loan_format_helper.fetch_loan(row))
            row = itgs.write_cursor.fetchone()

        suggested_loans = loan_format_helper.format_loan_table(loans, include_id=True)

        formatted_response = get_response(
            itgs,
            resp_name,
            lender_username=lender_username,
            loan_id=loan_id,
            amount=str(amt),
            loan=(
                'Loan Not Available'
                if loan is None
                else loan_format_helper.format_loan_table([loan], include_id=True)
            ),
            suggested_loans=suggested_loans
        )
        utils.reddit_proxy.send_request(
            itgs, rpiden, rpversion, 'post_comment',
            {
                'parent': comment_fullname,
                'text': formatted_response
            }
        )
