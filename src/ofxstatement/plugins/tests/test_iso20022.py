import os
import datetime

from ofxstatement.ui import UI

from ofxstatement.plugins.iso20022 import Iso20022Plugin


HERE = os.path.dirname(__file__)
SAMPLES_DIR = os.path.join(HERE, 'samples')


def test_parse_simple():
    # GIVEN
    plugin = Iso20022Plugin(UI(), {})

    parser = plugin.get_parser(os.path.join(SAMPLES_DIR, 'simple.xml'))

    # WHEN
    stmt = parser.parse()

    # THEN
    assert stmt is not None

    assert stmt.account_id == 'LT000000000000000000'
    assert stmt.currency == 'EUR'
    assert stmt.bank_id == 'AGBLLT2XXXX'
    assert stmt.end_balance == 125.52
    assert stmt.end_date == datetime.datetime(2015, 12, 31, 0, 0)
    assert stmt.start_balance == 306.53
    assert stmt.end_date == datetime.datetime(2015, 12, 31, 0, 0)

    assert len(stmt.lines) == 4

    assert all(l.amount for l in stmt.lines)

    line0 = stmt.lines[0]

    assert line0.amount == -0.29
    assert line0.memo == u'Sąskaitos aptarnavimo mokestis'
    assert line0.date == datetime.datetime(2016, 1, 1, 0, 0)
    assert line0.date_user == datetime.datetime(2015, 12, 31, 0, 0)
    assert line0.payee == u'AB DNB Bankas'
    assert line0.refnum == 'FC1261858984'
