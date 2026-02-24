#!/system/bin/python3

import datetime
import glob
import os
from pathlib import Path
import re
import subprocess
from typing import List

import check_utils as cu

config_obj = cu.Config.make_config()

Path(config_obj['out_dir']).mkdir(parents=True, exist_ok=True)

# jq has two test formats:
# - basic run shell script, get back 0 or 1
# - run shell script, execute any number of test cases and output the result,
#   then get back 0 or 1
case_pattern = r'^Test #[0-9]+: \'(.*)\' at line number ([0-9]+)'
f_pattern = r'^\*\*\* Expected .*, but got .*'

passed_suites: List[cu.PassedSuite] = []
failed_suites: List[cu.FailedSuite] = []
errored_suites: List[cu.ErroredSuite] = []

skipped = [skipped_obj
           for skipped_config in config_obj['custom']['skipped']
           if (skipped_obj := cu.Skipped.make_from_dict(skipped_config).filter_tests(cu.SystemSpec.from_uname())) is not None]

with open(config_obj['out_dir'] + '/' + config_obj['package'] + '.txt', 'w') as out:
    for path in config_obj['custom']['path'].splitlines():
        for f in glob.glob(path):
            if len([skip for skip in skipped if Path(f) == Path(skip.get_name())]) != 0:
                continue

            # There is nothing better to report for the suite.
            suite = Path(f).name
            passed_cases: List[cu.PassedCase] = []
            failed_cases: List[cu.FailedCase] = []
            errored_cases: List[cu.ErroredCase] = []

            case = None
            line = None

            timestamp = datetime.datetime.now().isoformat()
            status, output = subprocess.getstatusoutput(str(Path(f).absolute()))
            # Handle test suites (of test cases).
            for line in output.splitlines():
                if match := re.match(case_pattern, line):
                    if case is not None:
                        passed_cases.append(cu.PassedCase(case, line, '', ''))
                    case = match.group(1).strip()
                    line = match.group(2).strip()
                elif case is not None and (match := re.match(f_pattern, line)):
                    failed_cases.append(cu.FailedCase(case, line, '', '', match.group(0).strip(), ''))

                    case = None
                    line = None

            out.write(output)

            if case is not None:
                passed_cases.append(cu.PassedCase(case, line, '', ''))

            # Handle a basic test script.
            if (len(passed_cases) == 0) and (len(failed_cases) == 0):
                case = suite
                if not os.WIFEXITED(status):
                    # The test errored
                    errored_cases.append(cu.ErroredCase(case, '1', '', '', output, ''))
                elif os.WEXITSTATUS(status) != 0:
                    # The test failed
                    failed_cases.append(cu.FailedCase(case, '1', '', '', output, ''))
                else:
                    # The test passed
                    passed_cases.append(cu.PassedCase(case, '1', '', ''))

            if len(passed_cases) != 0:
                passed_suites.append(cu.PassedSuite(suite, '', timestamp, passed_cases))
            if len(failed_cases) != 0:
                failed_suites.append(cu.FailedSuite(suite, '', timestamp, failed_cases))
            if len(errored_cases) != 0:
                errored_suites.append(cu.FailedSuite(suite, '', timestamp, errored_cases))

# Handle manually skipped suites
skipped_suites = [skipped_suite for skip in skipped for skipped_suite in skip.get_suites()]

xml_report = cu.JUnitXML.make_from_passed(passed_suites)
xml_report += cu.JUnitXML.make_from_failed(failed_suites)
xml_report += cu.JUnitXML.make_from_skipped(skipped_suites)
xml_report += cu.JUnitXML.make_from_errored(errored_suites)

xml_report.write(Path(config_obj['out_dir']).joinpath(config_obj['package'] + '.xml'))

if xml_report.is_success():
    exit(cu.CheckExit.EXIT_SUCCESS)

exit(cu.CheckExit.EXIT_FAILURE)
