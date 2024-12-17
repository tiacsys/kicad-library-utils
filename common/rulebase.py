import inspect
import json
import os
from enum import Enum
from typing import List, Optional, Callable

from print_color import PrintColor


def logError(
    log_file: str, rule_name: str, lib_name: str, item_name: str, warning: bool = False
) -> None:
    """
    Log KLC error output to a json file.
    The JSON file will contain a cumulative dict
    of the errors and the library items that do not comply.
    """

    if not log_file.endswith(".json"):
        log_file += ".json"

    if os.path.exists(log_file) and os.path.isfile(log_file):
        with open(log_file, "r") as json_file:
            try:
                log_data = json.load(json_file)
            except ValueError:
                print("Found bad JSON data - clearing")
                log_data = {}

    else:
        log_data = {}

    key = "warnings" if warning else "errors"

    if key not in log_data:
        log_data[key] = {}

    log_entry = {"library": lib_name, "item": item_name}

    if rule_name not in log_data[key]:
        log_data[key][rule_name] = []

    log_data[key][rule_name].append(log_entry)

    # Write the log data back to file
    with open(log_file, "w") as json_file:
        op = json.dumps(log_data, indent=4, sort_keys=True, separators=(",", ":"))
        json_file.write(op)


# Static functions
def isValidName(
    name, checkForGraphicSymbol: bool = False, checkForPowerSymbol: bool = False
) -> bool:
    name = str(name).lower()
    firstChar = True
    for c in name:
        # first character may be '~' in some cases
        if (checkForPowerSymbol or checkForGraphicSymbol) and firstChar and c == "~":
            continue

        firstChar = False
        # Numeric characters check
        if c.isalnum():
            continue

        # Alpha characters (simple set only)
        if "a" <= c <= "z":
            continue

        if c in "_-.+,":
            continue

        return False

    return True


def checkLineEndings(filename: str):
    """
    Check for proper (Unix) line endings
    """
    filecontentsraw = open(filename, "rb").readline()

    LE1 = ord(chr(filecontentsraw[-2]))
    LE2 = ord(chr(filecontentsraw[-1]))

    # 0x0D0A = Windows (CRLF)
    # 0x__0D = Mac OS 9 (CR)
    # 0x__0A = Unix (LF)
    if (LE1 == 0x0D and LE2 == 0x0A) or (LE2 == 0x0D):
        return False

    return True


class Verbosity(Enum):
    NONE = 0
    NORMAL = 1
    HIGH = 2


class Severity(Enum):
    INFO = 0
    WARNING = 1
    ERROR = 2
    SUCCESS = 3


class KLCRuleLogItem:
    def __init__(self, severity: Severity, message: str):
        self.severity = severity
        self.message = message
        self.extras = []

    def add_extra(self, extra: str):
        self.extras.append(extra)


class KLCRuleBase:
    """
    A base class to represent a KLC rule
    """

    verbosity: Verbosity = Verbosity.NONE
    logEntries: List[KLCRuleLogItem] = []

    @property
    def name(self) -> str:
        path = inspect.getfile(self.__class__)
        path = os.path.basename(path)
        path = "".join(path.split(".")[:-1])
        return path.replace("_", ".")

    @property
    def url(self) -> str:
        if self.name.startswith("EC"):
            return "(extended check)"

        categories = {"F": "footprint", "G": "general", "M": "model", "S": "symbol"}

        category = categories[self.name[0]]
        name = self.name.lower()
        group = name.split(".")[0]
        url = f"https://klc.kicad.org/{category}/{group}/{name}/"

        return url

    def __init__(self):
        self.description = self.__doc__.strip().splitlines()[0].strip()
        self.logEntries = []

        self.resetErrorCount()
        self.resetWarningCount()

    def resetErrorCount(self) -> None:
        self.error_count: int = 0

    def resetWarningCount(self) -> None:
        self.warning_count: int = 0

    @property
    def errorCount(self) -> int:
        return self.error_count

    def hasErrors(self) -> bool:
        return self.error_count > 0

    def warningCount(self) -> int:
        return self.warning_count

    @property
    def hasWarnings(self) -> bool:
        return self.warning_count > 0

    # adds message into buffer only if such level of verbosity is wanted
    def verboseOut(
        self, msgVerbosity: Verbosity, severity: Severity, message: str
    ) -> None:
        self.messageBuffer.append((message, msgVerbosity, severity, []))

    def warning(self, msg: str) -> None:
        self.warning_count += 1
        self.logEntries.append(KLCRuleLogItem(Severity.WARNING, msg))

    def warningExtra(self, msg: str) -> None:
        self.logEntries[-1].add_extra(msg)

    def error(self, msg: str) -> None:
        self.error_count += 1
        self.logEntries.append(KLCRuleLogItem(Severity.ERROR, msg))

    def errorExtra(self, msg: str) -> None:
        self.logEntries[-1].add_extra(msg)

    def info(self, msg: str) -> None:
        self.logEntries.append(KLCRuleLogItem(Severity.INFO, msg))

    def success(self, msg: str) -> None:
        self.logEntries.append(KLCRuleLogItem(Severity.SUCCESS, msg))

    def check(self, component) -> None:
        raise NotImplementedError("The check method must be implemented")

    def fix(self, component) -> None:
        raise NotImplementedError("The fix method must be implemented")

    def recheck(self) -> None:

        self.resetErrorCount()
        self.resetWarningCount()

        self.check()

        if self.hasErrors():
            self.error("Could not fix all errors")
        else:
            self.success("Everything fixed")

    def hasOutput(self) -> bool:
        return len(self.logEntries) > 0

    def processOutput(
        self,
        printer: PrintColor,
        verbosity: Verbosity = Verbosity.NONE,
        silent: bool = False,
        problem_callback_fn: Optional[Callable[[KLCRuleLogItem], None]] = None,
    ) -> bool:

        # No violations
        if len(self.logEntries) == 0:
            return False

        if verbosity.value > Verbosity.NONE.value:
            printer.light_blue(self.description, indentation=4, max_width=100)

        for entry in self.logEntries:
            s = entry.severity  # Severity
            entry_verbosity = {
                Severity.INFO: Verbosity.NONE,
                Severity.WARNING: Verbosity.NORMAL,
                Severity.ERROR: Verbosity.NORMAL,
                Severity.SUCCESS: Verbosity.NORMAL,
            }[s]

            if entry_verbosity.value <= verbosity.value:

                msg = entry.message

                # Join the message with the extra message
                if verbosity.value >= Verbosity.HIGH.value:
                    msg += '\n   -'.join(entry.extras)

                if s == Severity.INFO:
                    printer.gray(msg, indentation=4)
                elif s == Severity.WARNING:
                    printer.brown(msg, indentation=4)
                elif s == Severity.ERROR:
                    printer.red(msg, indentation=4)
                elif s == Severity.SUCCESS:
                    printer.green(msg, indentation=4)
                else:
                    printer.red("unknown severity: " + msg, indentation=4)

            if problem_callback_fn:
                problem_callback_fn(entry)

        # Clear message buffer
        self.logEntries = []
        return True
