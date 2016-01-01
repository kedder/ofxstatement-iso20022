from ofxstatement.plugin import Plugin
from ofxstatement.parser import StatementParser
from ofxstatement.statement import StatementLine


class Iso2022Plugin(Plugin):
    """ISO-20022 plugin
    """

    def getParser(self, filename):
        return Iso2022Parser(filename)


class Iso2022Parser(object):
    def __init__(self, filename):
        self.filename = filename

    def parse(self):
        """Main entry point for parsers
        """
        with open(self.filename, "r") as f:
            self.input = f
            pass