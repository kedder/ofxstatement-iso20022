import datetime
import enum
import re
import xml.etree.ElementTree as ET
from decimal import Decimal
from typing import Dict, List, Optional

from ofxstatement import exceptions
from ofxstatement.parser import AbstractStatementParser
from ofxstatement.plugin import Plugin
from ofxstatement.statement import Statement, StatementLine

# ISO20022_NAMESPACE_ROOT = "urn:iso:std:iso:20022"
CAMT052_NAMESPACE_ROOT = "urn:iso:std:iso:20022:tech:xsd:camt.052"
CAMT053_NAMESPACE_ROOT = "urn:iso:std:iso:20022:tech:xsd:camt.053"


CD_CREDIT = "CRDT"
CD_DEBIT = "DBIT"


class CamtVersion(enum.Enum):
    CAMT052 = "urn:iso:std:iso:20022:tech:xsd:camt.052"
    CAMT053 = "urn:iso:std:iso:20022:tech:xsd:camt.053"


class Iso20022Plugin(Plugin):
    """ISO-20022 plugin"""

    def get_parser(self, filename: str) -> "Iso20022Parser":
        default_ccy = self.settings.get("currency")
        default_iban = self.settings.get("iban")
        parser = Iso20022Parser(filename, currency=default_ccy, iban=default_iban)
        return parser


class Iso20022Parser(AbstractStatementParser):
    version: CamtVersion
    xmlns: Dict[str, str]

    def __init__(
        self, filename: str, currency: Optional[str] = None, iban: Optional[str] = None
    ):
        self.filename = filename
        self.currency = currency
        self.iban = iban

    def parse(self) -> Statement:
        """Main entry point for parsers"""
        self.statement = Statement()
        self.statement.currency = self.currency
        self.statement.account_id = self.iban
        tree = ET.parse(self.filename)

        # Find out XML namespace and make sure we can parse it
        ns = self._get_namespace(tree.getroot())
        self.version = self._recognize_version(ns)
        self.xmlns = {"s": ns}

        self._parse_statement_properties(tree)
        self._parse_lines(tree)

        return self.statement

    def _recognize_version(self, ns: str) -> CamtVersion:
        for ver in CamtVersion:
            if ns.startswith(ver.value):
                return ver

        raise exceptions.ParseError(0, "Cannot recognize ISO20022 XML")

    def _get_namespace(self, elem: ET.Element) -> str:
        m = re.match(r"\{(.*)\}", elem.tag)
        return m.groups()[0] if m else ""

    def _get_statement_el(self, tree: ET.ElementTree) -> ET.Element:
        if self.version == CamtVersion.CAMT053:
            stmt = tree.find("./s:BkToCstmrStmt/s:Stmt", self.xmlns)
        else:
            assert self.version == CamtVersion.CAMT052
            stmt = tree.find("./s:BkToCstmrAcctRpt/s:Rpt", self.xmlns)

        assert stmt is not None
        return stmt

    def _parse_statement_properties(self, tree: ET.ElementTree) -> None:
        stmt = self._get_statement_el(tree)

        bnk = stmt.find("./s:Acct/s:Svcr/s:FinInstnId/s:BIC", self.xmlns)
        if bnk is None:
            bnk = stmt.find("./s:Acct/s:Svcr/s:FinInstnId/s:Nm", self.xmlns)
        ccy = stmt.find("./s:Acct/s:Ccy", self.xmlns)
        bals = stmt.findall("./s:Bal", self.xmlns)
        ibanfind = stmt.find(
            "./s:Acct/s:Id/s:IBAN",
            self.xmlns,
        )
        if ibanfind is None:
            ibanfind = stmt.find(
                "./s:Ntry/s:NtryDtls/s:TxDtls/s:RltdPties/s:CdtrAcct/s:Id/s:IBAN",
                self.xmlns,
            )
        # assert iban is not None

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

        acctIban = ibanfind.text if ibanfind is not None else None
        if acctIban:
            self.statement.account_id = acctIban
        else:
            if self.statement.account_id is None:
                raise exceptions.ParseError(
                    0,
                    "No iban found in the statement. Please specify one in the configuration file (e.g. iban=CH...)",
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

        # This statement is required to avoid overwriting account_id with None
        # when no IBAN can be found in the XML.
        # Instead the configured value for IBAN will be used.
        self.statement.account_id = (
            acctIban if acctIban is not None else self.statement.account_id
        )

        # From ISO 20022 Account Statement Guide:
        #
        # The following balance types are mandatory in the Bank-To-Customer
        # statement:
        #
        # OPBD – Book balance of the account at the beginning of the account
        # reporting period. - PRCD - Closing book balance of the previous day;
        # to be supplied in the material with the OPBD with similar data (see
        # the camt.053 example message), except for the PRCD type balance,
        # which has the same date as the previous day‟s CLBD type balance. The
        # date of OPBD type balance is the date of the reported account
        # statement.
        #
        # CLBD - Closing book balance of the account at the end of the account
        # reporting period.
        self.statement.start_balance = bal_amts.get("OPBD", bal_amts.get("PRCD"))
        self.statement.start_date = bal_dates.get("OPBD", bal_dates.get("PRCD"))
        self.statement.end_balance = bal_amts["CLBD"]
        self.statement.end_date = bal_dates["CLBD"]

    def _parse_lines(self, tree: ET.ElementTree) -> None:
        stmt = self._get_statement_el(tree)

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
