"""Helper functions for triggering summons, such as for the first pass at
comments or updating the seen set"""
from perms import can_interact, IGNORED_USERS
from lbshared.signal_helper import delay_signals
from lblogging import Level
import traceback

from summons.check import CheckSummon
from summons.confirm import ConfirmSummon
from summons.loan import LoanSummon
from summons.paid_with_id import PaidWithIdSummon
from summons.paid import PaidSummon
from summons.ping import PingSummon
from summons.unpaid import UnpaidSummon

SUMMONS = [
    CheckSummon(), ConfirmSummon(), LoanSummon(), PaidWithIdSummon(),
    PaidSummon(), PingSummon(), UnpaidSummon()
]


def handle_comment(itgs, comment, rpiden, version, summons=SUMMONS):
    itgs.logger.print(Level.TRACE, 'Checking comment {}', comment['fullname'])

    summon_to_use = None
    if can_interact(itgs, comment['author'], rpiden, version):
        for summon in summons:
            if not summon.might_apply_to_comment(comment):
                continue
            summon_to_use = summon
            break
    elif comment['author'].lower() not in IGNORED_USERS:
        # We don't print any log messages for users ignored via the env
        # var since they are usually us or other bots
        itgs.logger.print(
            Level.INFO,
            'Using no summons for {} by {}; insufficient access',
            comment['fullname'], comment['author']
        )

    with delay_signals(itgs):
        if summon_to_use is not None:
            itgs.logger.print(Level.DEBUG, 'Using summon {}', summon_to_use.name)
            try:
                summon_to_use.handle_comment(itgs, comment, rpiden, version)

                itgs.read_conn.commit()
                itgs.write_conn.commit()
            except:  # noqa
                itgs.read_conn.rollback()
                itgs.write_conn.rollback()
                itgs.logger.exception(
                    Level.WARN,
                    'While using summon {} on comment {}',
                    summon_to_use.name, comment
                )
                traceback.print_exc()

    itgs.logger.print(Level.TRACE, 'Finished handling comment {}', comment['fullname'])
