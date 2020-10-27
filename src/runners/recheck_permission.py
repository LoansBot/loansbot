"""This runner is responsible for granting lenders who have completed a
certain number of loans the permission to automatically recheck comments.
It is possible to abuse this permission somewhat by constantly rechecking
another users comments causing them to get spam, so we have this fairly
small gate before granting the permission.
"""
from pypika import PostgreSQLQuery as Query, Table, Parameter
from pypika.functions import Count
from pypika.terms import Star
from lbshared.lazy_integrations import LazyIntegrations as LazyItgs
from lblogging import Level
from .utils import listen_event
import utils.reddit_proxy
from lbshared.responses import get_letter_response
from functools import partial
import time

LOGGER_IDEN = 'runners/recheck_permission.py'
"""The identifier for this runner in the logs"""

RECHECK_PERMISSION = 'recheck'
"""The permission this runner grants"""

MINIMUM_COMPLETED_LOANS = 5
"""The number of completed loans required to get this permission"""


def main():
    version = time.time()
    with LazyItgs(logger_iden=LOGGER_IDEN) as itgs:
        itgs.logger.print(Level.DEBUG, 'Successfully booted up')

    with LazyItgs(logger_iden=LOGGER_IDEN) as itgs:
        listen_event(itgs, 'loans.paid', partial(handle_loan_paid, version))


def handle_loan_paid(version, event):
    """Handles a loan.paid event (typically sent from utils/paid_utils.py); if
    the lender does not have the recheck permission and has an unknown/good
    trust status, and they don't have the recheck permission we grant them the
    recheck permission.
    """
    with LazyItgs(logger_iden=LOGGER_IDEN) as itgs:
        lender_id = event['lender']['id']
        lender_username = event['lender']['username']

        itgs.logger.print(
            Level.TRACE,
            'Detected /u/{} (id={}) had one of the loans he gave out paid back',
            lender_username, lender_id
        )

        trusts = Table('trusts')
        itgs.read_cursor.execute(
            Query.from_(trusts)
            .select(1)
            .where(trusts.user_id == Parameter('%s'))
            .where(trusts.status == Parameter('%s'))
            .get_sql(),
            (lender_id, 'bad')
        )
        row = itgs.read_cursor.fetchone()

        if row is not None:
            itgs.logger.print(
                Level.TRACE,
                'Ignoring lender /u/{} (id={}); he has bad trust status',
                lender_username, lender_id
            )
            return

        passwd_auths = Table('password_authentications')
        itgs.read_cursor.execute(
            Query.from_(passwd_auths)
            .select(passwd_auths.id)
            .where(passwd_auths.user_id == Parameter('%s'))
            .where(passwd_auths.human == Parameter('%s'))
            .where(passwd_auths.deleted == Parameter('%s'))
            .get_sql(),
            (lender_id, True, False)
        )
        row = itgs.read_cursor.fetchone()
        if row is None:
            itgs.logger.print(
                Level.TRACE,
                'Ignoring lender /u/{} (id={}); he has not signed up'
            )
            return

        (passwd_auth_id,) = row

        passwd_auth_perms = Table('password_auth_permissions')
        perms = Table('permissions')
        itgs.read_cursor.execute(
            Query.from_(passwd_auth_perms)
            .join(perms)
            .on(perms.id == passwd_auth_perms.permission_id)
            .select(1)
            .where(passwd_auth_perms.password_authentication_id == Parameter('%s'))
            .where(perms.name == Parameter('%s'))
            .get_sql(),
            (passwd_auth_id, RECHECK_PERMISSION)
        )
        if itgs.read_cursor.fetchone():
            itgs.logger.print(
                Level.TRACE,
                'Ignoring lender /u/{} (id={}); already has recheck permission',
                lender_username, lender_id
            )
            return

        usrs = Table('users')
        loans = Table('loans')
        itgs.read_cursor.execute(
            Query.from_(loans)
            .select(Count(Star()))
            .where(loans.lender_id == Parameter('%s'))
            .where(loans.repaid_at.notnull())
            .where(loans.deleted_at.isnull())
            .get_sql(),
            (lender_id,)
        )
        (num_loans_compl_as_lender,) = itgs.read_cursor.fetchone()

        if num_loans_compl_as_lender < MINIMUM_COMPLETED_LOANS:
            itgs.logger.print(
                Level.TRACE,
                'Ignoring lender /u/{} (has {} completed, threshold is {})',
                lender_username, num_loans_compl_as_lender, MINIMUM_COMPLETED_LOANS
            )
            return

        itgs.logger.print(
            Level.TRACE,
            'Going to grant recheck permission to lender '
            '/u/{} (has {} completed, threshold is {})',
            lender_username, num_loans_compl_as_lender,
            MINIMUM_COMPLETED_LOANS
        )

        itgs.read_cursor.execute(
            Query.from_(perms)
            .select(perms.id)
            .where(perms.name == Parameter('%s'))
            .get_sql(),
            (RECHECK_PERMISSION,)
        )
        row = itgs.read_cursor.fetchone()
        if row is None:
            itgs.logger.print(
                Level.INFO,
                'Detected there is no recheck permission in the database, '
                'automatically adding with name=%s',
                RECHECK_PERMISSION
            )
            itgs.write_cursor.execute(
                Query.into(perms)
                .columns(perms.name, perms.description)
                .insert(Parameter('%s'), Parameter('%s'))
                .returning(perms.id)
                .get_sql(),
                (RECHECK_PERMISSION, 'Ability to have the LoansBot revisit a comment')
            )
            row = itgs.write_cursor.fetchone()

        (recheck_perm_id,) = row
        itgs.write_cursor.execute(
            Query.into(passwd_auth_perms)
            .columns(passwd_auth_perms.password_authentication_id, passwd_auth_perms.permission_id)
            .insert(Parameter('%s'), Parameter('%s'))
            .get_sql(),
            (passwd_auth_id, recheck_perm_id)
        )
        itgs.write_conn.commit()
        itgs.logger.print(
            Level.INFO,
            'Granted /u/{} access to recheck permission - signed up and has '
            '{} loans completed as lender (threshold is {})',
            lender_username, num_loans_compl_as_lender, MINIMUM_COMPLETED_LOANS
        )

        (subject, body) = get_letter_response(
            itgs,
            'user_granted_recheck_pm',
            username=lender_username
        )

        utils.reddit_proxy.send_request(
            itgs, 'recheck_permission', version, 'compose',
            {
                'recipient': lender_username,
                'subject': subject,
                'body': body
            }
        )
