import xml.etree.ElementTree as ET
import datetime

from ofxstatement import exceptions
from ofxstatement.plugin import Plugin
from ofxstatement.statement import Statement, StatementLine


XMLNS = {
    's': 'urn:iso:std:iso:20022:tech:xsd:camt.053.001.02'
}

CD_CREDIT = 'CRDT'
CD_DEBIT = 'DBIT'

class Iso20022Plugin(Plugin):
    """ISO-20022 plugin
    """

    def get_parser(self, filename):
        default_ccy = self.settings.get('currency')
        parser = Iso20022Parser(filename, currency=default_ccy)
        return parser


class Iso20022Parser(object):
    def __init__(self, filename, currency=None):
        self.filename = filename
        self.currency = currency

    def parse(self):
        """Main entry point for parsers
        """
        self.statement = Statement()
        self.statement.currency = self.currency
        tree = ET.parse(self.filename)

        self._parse_statement_properties(tree)
        self._parse_lines(tree)

        return self.statement

    def _parse_statement_properties(self, tree):
        stmt = tree.find('./s:BkToCstmrStmt/s:Stmt', XMLNS)

        bnk = stmt.find('./s:Acct/s:Svcr/s:FinInstnId/s:BIC', XMLNS)
        iban =stmt.find('./s:Acct/s:Id/s:IBAN', XMLNS)
        ccy =stmt.find('./s:Acct/s:Ccy', XMLNS)
        bals = stmt.findall('./s:Bal', XMLNS)

        acctCurrency = ccy.text if ccy is not None else None
        if acctCurrency:
            self.statement.currency = acctCurrency
        else:
            if self.statement.currency is None:
                raise exceptions.ParseError(
                    0, "No account currency provided in statement. Please "
                    "specify one in configuration file (e.g. currency=EUR)")

        bal_amts = {}
        bal_dates = {}
        for bal in bals:
            cd = bal.find('./s:Tp/s:CdOrPrtry/s:Cd', XMLNS)
            amt = bal.find('./s:Amt', XMLNS)
            dt = bal.find('./s:Dt', XMLNS)
            amt_ccy = amt.get('Ccy')
            # Amount currency should match with statement currency
            if amt_ccy != self.statement.currency:
                continue

            bal_amts[cd.text] = self._parse_amount(amt)
            bal_dates[cd.text] = self._parse_date(dt)

        self.statement.bank_id = bnk.text if bnk is not None else None
        self.statement.account_id = iban.text
        self.statement.start_balance = bal_amts['OPBD']
        self.statement.start_date = bal_dates['OPBD']
        self.statement.end_balance = bal_amts['CLBD']
        self.statement.end_date = bal_dates['CLBD']

    def _parse_lines(self, tree):
        for ntry in _findall(tree, 'BkToCstmrStmt/Stmt/Ntry'):
            sline = self._parse_line(ntry)
            if sline is not None:
                self.statement.lines.append(sline)

    def _parse_line(self, ntry):
        sline = StatementLine()

        crdeb = _find(ntry, 'CdtDbtInd').text

        amtnode = _find(ntry, 'Amt')
        amt_ccy = amtnode.get('Ccy')

        if amt_ccy != self.statement.currency:
            # We can't include amounts with incompatible currencies into the
            # statement.
            return None

        amt = self._parse_amount(amtnode)
        if crdeb == CD_DEBIT:
            amt = -amt
            payee = _find(ntry, 'NtryDtls/TxDtls/RltdPties/Cdtr/Nm')
        else:
            payee = _find(ntry, 'NtryDtls/TxDtls/RltdPties/Dbtr/Nm')

        sline.payee = payee.text if payee is not None else None
        sline.amount = amt

        dt = _find(ntry, 'ValDt')
        sline.date = self._parse_date(dt)

        bookdt = _find(ntry, 'BookgDt')
        sline.date_user = self._parse_date(bookdt)

        svcref = _find(ntry, 'NtryDtls/TxDtls/Refs/AcctSvcrRef')
        sline.refnum = svcref.text

        # Try to find memo from different possible locations
        rmtinf = _find(ntry, 'NtryDtls/TxDtls/RmtInf/Ustrd')
        addinf = _find(ntry, 'AddtlNtryInf')
        if rmtinf is not None:
            sline.memo = rmtinf.text
        elif addinf is not None:
            sline.memo = addinf.text

        return sline

    def _parse_date(self, dtnode):
        if dtnode is None:
            return None

        dt = _find(dtnode, 'Dt')
        dttm = _find(dtnode, 'DtTm')

        if dt is not None:
            return datetime.datetime.strptime(dt.text, "%Y-%m-%d")
        else:
            assert dttm is not None
            return datetime.datetime.strptime(dttm.text, "%Y-%m-%dT%H:%M:%S")

    def _parse_amount(self, amtnode):
        return float(amtnode.text)


def _toxpath(spath):
    tags = spath.split('/')
    path = ['s:%s' % t for t in tags]
    xpath = './%s' % '/'.join(path)
    return xpath


def _find(tree, spath):
    return tree.find(_toxpath(spath), XMLNS)


def _findall(tree, spath):
    return tree.findall(_toxpath(spath), XMLNS)
