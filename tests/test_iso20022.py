import os
import datetime
from decimal import Decimal

import pytest

from ofxstatement import exceptions
from ofxstatement.ui import UI
from ofxstatement.plugins.iso20022 import Iso20022Plugin


HERE = os.path.dirname(__file__)
SAMPLES_DIR = os.path.join(HERE, "samples")


def test_parse_simple() -> None:
    # GIVEN
    plugin = Iso20022Plugin(UI(), {})

    parser = plugin.get_parser(os.path.join(SAMPLES_DIR, "simple.xml"))

    # WHEN
    stmt = parser.parse()

    # THEN
    assert stmt is not None

    assert stmt.account_id == "LT000000000000000000"
    assert stmt.currency == "EUR"
    assert stmt.bank_id == "AGBLLT2XXXX"
    assert stmt.end_balance == Decimal("125.52")
    assert stmt.end_date == datetime.datetime(2015, 12, 31, 0, 0)
    assert stmt.start_balance == Decimal("306.53")
    assert stmt.start_date == datetime.datetime(2015, 12, 1, 0, 0)

    assert len(stmt.lines) == 4

    assert all(l.amount for l in stmt.lines)

    line0 = stmt.lines[0]

    assert line0.amount == Decimal("-0.29")
    assert line0.memo == u"Sąskaitos aptarnavimo mokestis"
    assert line0.date == datetime.datetime(2016, 1, 1, 0, 0)
    assert line0.date_user == datetime.datetime(2015, 12, 31, 0, 0)
    assert line0.payee == u"AB DNB Bankas"
    assert line0.refnum == "FC1261858984"


def test_parse_unconfigured_currency() -> None:
    # GIVEN
    plugin = Iso20022Plugin(UI(), {})
    parser = plugin.get_parser(os.path.join(SAMPLES_DIR, "gcamp6.xml"))

    # WHEN
    with pytest.raises(exceptions.ParseError):
        stmt = parser.parse()


def test_parse_gcamp6() -> None:
    # GIVEN
    config = {"currency": "XXX"}
    plugin = Iso20022Plugin(UI(), config)

    parser = plugin.get_parser(os.path.join(SAMPLES_DIR, "gcamp6.xml"))

    # WHEN
    stmt = parser.parse()

    # THEN
    assert stmt is not None

    assert stmt.account_id == "CH2609000000924238861"
    assert stmt.currency is "XXX"

    assert stmt.bank_id is None
    assert stmt.end_balance == Decimal("10000.0")
    assert stmt.end_date == datetime.datetime(2017, 1, 31, 0, 0)
    assert stmt.start_balance == Decimal("0.0")
    assert stmt.start_date == datetime.datetime(2015, 12, 31, 0, 0)

    assert len(stmt.lines) == 5

    assert all(l.amount for l in stmt.lines)

    line0 = stmt.lines[0]

    assert line0.amount == Decimal("10000.0")
    assert line0.memo == "Account Transfer"
    assert line0.date == datetime.datetime(2016, 4, 23, 0, 0)
    assert line0.date_user == datetime.datetime(2016, 4, 23, 0, 0)
    assert line0.payee is None
    assert line0.refnum == "20160423000805545979476000000012"


def test_parse_davider80() -> None:
    # GIVEN
    config = {"currency": "CHF"}
    plugin = Iso20022Plugin(UI(), config)

    parser = plugin.get_parser(os.path.join(SAMPLES_DIR, "davider80.xml"))

    # WHEN
    stmt = parser.parse()

    # THEN
    assert stmt is not None

    assert stmt.account_id == "CHxxxxxxxxxxxxxxxxxxx"
    assert stmt.currency is "CHF"

    assert stmt.bank_id == "Raiffeisen"
    assert stmt.end_balance == Decimal("5753.46")
    assert stmt.end_date == datetime.datetime(2017, 4, 11, 0, 0)
    assert stmt.start_balance == Decimal("9433.31")
    assert stmt.start_date == datetime.datetime(2017, 4, 1, 0, 0)

    assert len(stmt.lines) == 16

    assert all(l.amount for l in stmt.lines)

    line0 = stmt.lines[0]

    assert line0.amount == Decimal("-905.3")
    assert line0.memo == "Sistema di addebitamento diretto xxxxxxxxxxxxxxxxxxxxxx AG"
    assert line0.date == datetime.datetime(2017, 4, 3, 0, 0)
    assert line0.date_user == datetime.datetime(2017, 4, 1, 0, 0)
    assert line0.payee is None
    assert line0.refnum == "210564431020000000024556150000"


def test_parse_camt052() -> None:
    # GIVEN
    config = {"currency": "CHF"}
    plugin = Iso20022Plugin(UI(), config)

    parser = plugin.get_parser(os.path.join(SAMPLES_DIR, "camt052.xml"))

    # WHEN
    stmt = parser.parse()

    # THEN
    assert stmt is not None

    assert stmt.account_type == "CHECKING"
    assert stmt.bank_id == "PZHSDE66XXX"
    assert stmt.currency == "EUR"
    assert stmt.end_balance == Decimal("16.95")
    assert stmt.end_date == datetime.datetime(2021, 2, 5, 0, 0)
    assert stmt.start_balance == Decimal("268.35")
    assert stmt.start_date == datetime.datetime(2021, 2, 4, 0, 0)

    assert len(stmt.lines) == 5
    line0 = stmt.lines[0]

    assert line0.check_no is None
    assert line0.date == datetime.datetime(2021, 2, 5, 0, 0)
    assert line0.date_user == datetime.datetime(2021, 2, 5, 0, 0)
    assert line0.id is None
    assert line0.memo == "Something"
    assert line0.payee == "SPARKASSE PFORZHEIM CALW"
    assert line0.refnum == "NONREF"


def test_unsupported() -> None:
    # GIVEN
    config = {"currency": "CHF"}
    plugin = Iso20022Plugin(UI(), config)

    # WHEN
    parser = plugin.get_parser(os.path.join(SAMPLES_DIR, "unsupported.xml"))

    # THEN
    with pytest.raises(exceptions.ParseError):
        parser.parse()

def test_parse_camt053() -> None:
    # GIVEN
    config = {"iban": "CHxxxxxxxxxxxxxxxxxxx"}
    plugin = Iso20022Plugin(UI(), config)

    parser = plugin.get_parser(os.path.join(SAMPLES_DIR, "camt053.xml"))

    # WHEN
    stmt = parser.parse()

    # THEN
    assert stmt is not None

    assert stmt.account_id == "CHxxxxxxxxxxxxxxxxxxx"
    assert stmt.currency == "CHF"
    assert stmt.bank_id == "SAMPLEBANK222"
    assert stmt.end_balance == Decimal("2116.31")
    assert stmt.end_date == datetime.datetime(2023, 1, 25, 0, 0)
    assert stmt.start_balance == Decimal("832.01")
    assert stmt.start_date == datetime.datetime(2023, 1, 25, 0, 0)

    assert len(stmt.lines) == 1

    assert all(l.amount for l in stmt.lines)

    line0 = stmt.lines[0]

    assert line0.amount == Decimal("1284.30")
    assert line0.memo == u"PAYMENT INFO"
    assert line0.date == datetime.datetime(2023, 1, 25, 0, 0)
    assert line0.date_user == datetime.datetime(2023, 1, 25, 0, 0)
    #assert line0.payee == u"PAYEE"
    assert line0.refnum == "A032-J30K20-03-JF021"
