"""Describes the summon for marking that a particular user has repaid them a
certain amount of money. This will apply it toward the principal of the
borrowers loan to that lender in oldest-first order, rolling funds over.
"""
from .summon import Summon
from parsing.parser import Parser
import parsing.ext_tokens
import utils.reddit_proxy
import loan_format_helper
import utils.paid_utils
from pypika import Table, Parameter, Order
from lblogging import Level
from lbshared.responses import get_response


PARSER = Parser(
    '$paid',
    [
        {'token': parsing.ext_tokens.create_user_token(), 'optional': False},
        {'token': parsing.ext_tokens.create_money_token(), 'optional': False}
    ]
)


class PaidSummon(Summon):
    def __init__(self):
        self.name = 'paid'

    def might_apply_to_comment(self, comment):
        """Determines if the $paid command might be in the comment

        Returns:
            True if $paid is in the comment, false otherwise
        """
        return PARSER.parse(comment['body']) is not None

    def handle_comment(self, itgs, comment, rpiden, rpversion):
        token_vals = PARSER.parse(comment['body'])
        lender_username = comment['author']
        borrower_username = token_vals[0]
        amt = token_vals[1]

        comment_permalink = 'https://www.reddit.com/comments/{}/redditloans/{}'.format(
            comment['link_fullname'][3:],
            comment['fullname'][3:]
        )

        loans = Table('loans')
        lenders = Table('lenders')
        borrowers = Table('borrowers')

        effected_loans_pre = []
        effected_loans_post = []
        remaining = amt
        while remaining.minor > 0:
            itgs.write_cursor.execute(
                loan_format_helper.create_loans_query()
                .where(lenders.username == Parameter('%s'))
                .where(borrowers.username == Parameter('%s'))
                .where(loans.repaid_at.isnull())
                .orderby(loans.created_at, order=Order.asc)
                .limit(1)
                .get_sql(),
                (lender_username.lower(), borrower_username.lower())
            )
            row = itgs.write_cursor.fetchone()
            if row is None:
                break
            loan_pre = loan_format_helper.fetch_loan(row)
            old_minor = remaining.minor
            (_, _, remaining) = utils.paid_utils.apply_repayment(itgs, loan_pre.id, remaining)
            itgs.write_cursor.execute(
                loan_format_helper.create_loans_query()
                .where(loans.id == Parameter('%s'))
                .get_sql(),
                (loan_pre.id,)
            )
            row = itgs.write_cursor.fetchone()
            if row is None:
                itgs.logger.print(
                    Level.WARN,
                    'Somehow, while handling the paid summon by /u/{} at {}, ' +
                    'the loan was deleted while applying repayment. We stopped ' +
                    'propagating the loan early. If nobody was deleting loans this ' +
                    'is definitely developer error.',
                    lender_username, comment_permalink
                )
                effected_loans_pre.append(loan_pre)
                break
            loan_post = loan_format_helper.fetch_loan(row)
            if old_minor <= remaining.minor:
                # Sanity check to prevent loops
                break
            effected_loans_pre.append(loan_pre)
            effected_loans_post.append(loan_post)

        itgs.logger.print(
            Level.INFO,
            '/u/{} was repaid by /u/{} by {} over {} loan{} at {}',
            lender_username, borrower_username, amt,
            len(effected_loans_pre), 's' if len(effected_loans_pre) != 1 else '',
            comment_permalink
        )

        formatted_response = get_response(
            itgs,
            'paid',
            lender_username=lender_username,
            borrower_username=borrower_username,
            loans_before=loan_format_helper.format_loan_table(effected_loans_pre),
            loans_after=loan_format_helper.format_loan_table(effected_loans_post),
            num_loans_affected=len(effected_loans_pre),
            amount=str(amt),
            remaining=str(remaining)
        )

        utils.reddit_proxy.send_request(
            itgs, rpiden, rpversion, 'post_comment',
            {
                'parent': comment['fullname'],
                'text': formatted_response
            }
        )
