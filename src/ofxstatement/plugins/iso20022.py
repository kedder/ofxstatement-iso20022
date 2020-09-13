from typing import Optional, List
import xml.etree.ElementTree as ET
import datetime
import re
from decimal import Decimal

from ofxstatement import exceptions
from ofxstatement.plugin import Plugin
from ofxstatement.statement import Statement, StatementLine
from ofxstatement.parser import AbstractStatementParser


ISO20022_NAMESPACE_ROOT = "urn:iso:std:iso:20022:tech:xsd:camt.053.001"

CD_CREDIT = "CRDT"
CD_DEBIT = "DBIT"


class Iso20022Plugin(Plugin):
    """ISO-20022 plugin"""

    def get_parser(self, filename: str) -> "Iso20022Parser":
        default_ccy = self.settings.get("currency")
        parser = Iso20022Parser(filename, currency=default_ccy)
        return parser


class Iso20022Parser(AbstractStatementParser):
    def __init__(self, filename: str, currency: str = None):
        self.filename = filename
        self.currency = currency

    def parse(self) -> Statement:
        """Main entry point for parsers"""
        self.statement = Statement()
        self.statement.currency = self.currency
        tree = ET.parse(self.filename)

        # Find out XML namespace and make sure we can parse it
        ns = self._get_namespace(tree.getroot())
        if not ns.startswith(ISO20022_NAMESPACE_ROOT):
            raise exceptions.ParseError(0, "Cannot recognize ISO20022 XML")

        self.xmlns = {"s": ns}

        self._parse_statement_properties(tree)
        self._parse_lines(tree)

        return self.statement

    def _get_namespace(self, elem: ET.Element) -> str:
        m = re.match(r"\{(.*)\}", elem.tag)
        return m.groups()[0] if m else ""

    def _parse_statement_properties(self, tree: ET.ElementTree) -> None:
        stmt = tree.find("./s:BkToCstmrStmt/s:Stmt", self.xmlns)
        assert stmt is not None

        bnk = stmt.find("./s:Acct/s:Svcr/s:FinInstnId/s:BIC", self.xmlns)
        if bnk is None:
            bnk = stmt.find("./s:Acct/s:Svcr/s:FinInstnId/s:Nm", self.xmlns)
        iban = stmt.find("./s:Acct/s:Id/s:IBAN", self.xmlns)
        assert iban is not None
        ccy = stmt.find("./s:Acct/s:Ccy", self.xmlns)
        bals = stmt.findall("./s:Bal", self.xmlns)

        acctCurrency = ccy.text if ccy is not None else None
        if acctCurrency:
            self.statement.currency = acctCurrency
        else:
            if self.statement.currency is None:
                raise exceptions.ParseError(
                    0,
                    "No account currency provided in statement. Please "
                    "specify one in configuration file (e.g. currency=EUR)",
                )

        bal_amts = {}
        bal_dates = {}
        for bal in bals:
            cd = bal.find("./s:Tp/s:CdOrPrtry/s:Cd", self.xmlns)
            amt = bal.find("./s:Amt", self.xmlns)
            dt = bal.find("./s:Dt", self.xmlns)
            assert cd is not None
            assert amt is not None
            amt_ccy = amt.get("Ccy")
            # Amount currency should match with statement currency
            if amt_ccy != self.statement.currency:
                continue

            bal_amts[cd.text] = self._parse_amount(amt)
            bal_dates[cd.text] = self._parse_date(dt)

        if not bal_amts:
            raise exceptions.ParseError(
                0,
                "No statement balance found for currency '%s'. Check "
                "currency of statement file." % self.statement.currency,
            )

        self.statement.bank_id = bnk.text if bnk is not None else None
        self.statement.account_id = iban.text
        self.statement.start_balance = bal_amts["OPBD"]
        self.statement.start_date = bal_dates["OPBD"]
        self.statement.end_balance = bal_amts["CLBD"]
        self.statement.end_date = bal_dates["CLBD"]

    def _parse_lines(self, tree: ET.ElementTree) -> None:
        stmt = tree.find("./s:BkToCstmrStmt/s:Stmt", self.xmlns)
        assert stmt is not None

        for ntry in self._findall(stmt, "Ntry"):
            sline = self._parse_line(ntry)
            if sline is not None:
                self.statement.lines.append(sline)

    def _parse_line(self, ntry: ET.Element) -> Optional[StatementLine]:
        sline = StatementLine()

        crdeb = self._findstrict(ntry, "CdtDbtInd").text

        amtnode = self._findstrict(ntry, "Amt")
        amt_ccy = amtnode.get("Ccy")

        if amt_ccy != self.statement.currency:
            # We can't include amounts with incompatible currencies into the
            # statement.
            return None

        amt = self._parse_amount(amtnode)
        if crdeb == CD_DEBIT:
            amt = -amt
            payee = self._find(ntry, "NtryDtls/TxDtls/RltdPties/Cdtr/Nm")
        else:
            payee = self._find(ntry, "NtryDtls/TxDtls/RltdPties/Dbtr/Nm")

        sline.payee = payee.text if payee is not None else None
        sline.amount = amt

        dt = self._find(ntry, "ValDt")
        sline.date = self._parse_date(dt)

        bookdt = self._find(ntry, "BookgDt")
        sline.date_user = self._parse_date(bookdt)

        svcref = self._find(ntry, "NtryDtls/TxDtls/Refs/AcctSvcrRef")
        if svcref is None:
            svcref = self._find(ntry, "AcctSvcrRef")
        if svcref is not None:
            sline.refnum = svcref.text

        # Try to find memo from different possible locations
        refinf = self._find(ntry, "NtryDtls/TxDtls/RmtInf/Strd/CdtrRefInf/Ref")
        rmtinf = self._find(ntry, "NtryDtls/TxDtls/RmtInf/Ustrd")
        addinf = self._find(ntry, "AddtlNtryInf")
        if refinf is not None:
            sline.memo = refinf.text
        elif rmtinf is not None:
            sline.memo = rmtinf.text
        elif addinf is not None:
            sline.memo = addinf.text

        return sline

    def _parse_date(self, dtnode: Optional[ET.Element]) -> Optional[datetime.datetime]:
        if dtnode is None:
            return None

        dt = self._find(dtnode, "Dt")
        dttm = self._find(dtnode, "DtTm")

        if dt is not None and dt.text is not None:
            dtvalue = self._notimezone(dt.text)
            return datetime.datetime.strptime(dtvalue, "%Y-%m-%d")
        else:
            assert dttm is not None and dttm.text is not None
            dtvalue = self._notimezone(dttm.text)
            return datetime.datetime.strptime(dtvalue, "%Y-%m-%dT%H:%M:%S")

    def _notimezone(self, dt: str) -> str:
        # Sometimes we are getting time with ridiculous timezone, like
        # "2017-04-01+02:00", which is unparseable by any python parsers. Strip
        # out such timezone for good.
        if "+" not in dt:
            return dt
        dt, tz = dt.split("+")
        return dt

    def _parse_amount(self, amtnode: ET.Element) -> Decimal:
        assert amtnode.text is not None
        return Decimal(amtnode.text)

    def _find(self, tree: ET.Element, spath: str) -> Optional[ET.Element]:
        return tree.find(_toxpath(spath), self.xmlns)

    def _findstrict(self, tree: ET.Element, spath: str) -> ET.Element:
        found = self._find(tree, spath)
        if found is None:
            raise exceptions.ParseError(0, f"{spath} is not found in {tree}")
        return found

    def _findall(self, tree: ET.Element, spath: str) -> List[ET.Element]:
        return tree.findall(_toxpath(spath), self.xmlns)


def _toxpath(spath: str) -> str:
    tags = spath.split("/")
    path = ["s:%s" % t for t in tags]
    xpath = "./%s" % "/".join(path)
    return xpath
