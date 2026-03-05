"""Utility for running tests for CES agent callbacks."""

import glob
import os
import sys
import tempfile
import time

import pandas as pd
import pytest


class CallbackUtils:
    """Provides methods for orchestrating and executing agent callback tests."""

    def run_callback_tests(
        self,
        app_root_dir: str,
        *,
        agent_name: str = "*",
        callback_type: str = "*_callbacks",
        callback_name: str = "*",
        verbose: bool = True,
    ) -> pd.DataFrame:
        """Runs pytest against all callback tests in the given agent directory.

        Args:
            app_root_dir: The path to the CES app root directory.
            agent_name: Optional. The name of the agent to run tests for.
                If not provided, all agents will be tested.
            callback_type: Optional. The type of callback to run tests for.
                If not provided, all callback types will be tested.
            callback_name: Optional. The name of the callback to run tests for.
                If not provided, all callbacks will be tested.
            verbose: Optional. Whether to show verbose output from pytest.
                Defaults to True.

        Returns:
            A pandas DataFrame containing test execution results.
        """

        # Discover all test.py files within the agent directory
        # Expected: agents/<agent_name>/<type>_callbacks/<callback_name>/test.py
        search_pattern = os.path.join(
            app_root_dir,
            "agents",
            agent_name,
            callback_type,
            callback_name,
            "test.py",
        )
        test_files = glob.glob(search_pattern, recursive=True)

        if not test_files:
            print(f"No callback tests found in {app_root_dir}")
            return pd.DataFrame(
                columns=[
                    "agent_name",
                    "callback_type",
                    "test_name",
                    "status",
                    "error_message",
                ]
            )

        print(f"Found {len(test_files)} callback tests.")

        all_results = []

        for test_file in test_files:
            test_dir = os.path.dirname(os.path.abspath(test_file))
            python_code_path = os.path.join(test_dir, "python_code.py")

            if not os.path.exists(python_code_path):
                print(
                    f"Warning: {test_file} found, but no "
                    "python_code.py exists alongside it. Skipping."
                )
                continue

            print(f"Running test for: {python_code_path}")

            with open(python_code_path, "r", encoding="utf-8") as f:
                code_content = f.read()

            with open(test_file, "r", encoding="utf-8") as f:
                test_content = f.read()

            class TestResultCollector:
                """Collects execution results from pytest test runs."""

                def __init__(self, original_file, agent_name, callback_type):
                    self.results = []
                    self.original_file = original_file
                    self.agent_name = agent_name
                    self.callback_type = callback_type

                def _get_error_message(self, report):
                    if getattr(report, "longrepr", None):
                        if hasattr(report.longrepr, "reprcrash") and getattr(
                            report.longrepr, "reprcrash", None
                        ):
                            return report.longrepr.reprcrash.message
                        return str(report.longrepr)
                    return None

                def pytest_runtest_logreport(self, report):
                    if report.when == "call":
                        self.results.append(
                            {
                                "agent_name": self.agent_name,
                                "callback_type": self.callback_type,
                                "test_name": report.nodeid.split("::")[-1],
                                "status": report.outcome,
                                "error_message": self._get_error_message(
                                    report
                                ),
                            }
                        )
                    elif report.failed:
                        self.results.append(
                            {
                                "agent_name": self.agent_name,
                                "callback_type": self.callback_type,
                                "test_name": report.nodeid.split("::")[-1],
                                "status": report.outcome,
                                "error_message": self._get_error_message(
                                    report
                                ),
                            }
                        )

                def pytest_collectreport(self, report):
                    if report.failed:
                        self.results.append(
                            {
                                "agent_name": self.agent_name,
                                "callback_type": self.callback_type,
                                "test_name": "collection_error",
                                "status": "failed",
                                "error_message": self._get_error_message(
                                    report
                                ),
                            }
                        )

            with tempfile.TemporaryDirectory() as temp_dir:
                epoch = time.time()
                callback_path = os.path.join(temp_dir, "python_code.py")

                # Unique module names prevent pytest from caching imported files
                test_module_name = f"test_callback_{int(epoch * 1000)}"
                temp_test_path = os.path.join(
                    temp_dir, f"{test_module_name}.py"
                )

                with open(callback_path, "w", encoding="utf-8") as f:
                    f.write(
                        "from cxas_scrapi.utils.callback_libs import *\n\n"
                        + code_content
                    )

                with open(temp_test_path, "w", encoding="utf-8") as f:
                    f.write(test_content)

                original_sys_path = sys.path.copy()
                original_cwd = os.getcwd()
                try:
                    sys.path.insert(0, temp_dir)
                    os.chdir(temp_dir)

                    # Clear python_code from sys.modules so the new code is loaded
                    if "python_code" in sys.modules:
                        del sys.modules["python_code"]

                    agent_name = self._get_agent_name(test_file)
                    callback_type = self._get_callback_type(test_file)
                    collector = TestResultCollector(
                        test_file, agent_name, callback_type
                    )
                    pytest.main(
                        [
                            temp_test_path,
                            "--disable-warnings",
                            "--no-header",
                            "-v" if verbose else "-qq",
                        ],
                        plugins=[collector],
                    )
                    all_results.extend(collector.results)
                finally:
                    sys.path = original_sys_path
                    os.chdir(original_cwd)

        return pd.DataFrame(
            all_results,
            columns=[
                "agent_name",
                "callback_type",
                "test_name",
                "status",
                "error_message",
            ],
        )

    def _get_agent_name(self, original_file: str) -> str:
        """Extracts the agent name from the agent path."""
        return original_file.split("/")[-4]

    def _get_callback_type(self, original_file: str) -> str:
        """Extracts the callback type from the agent path."""
        return original_file.split("/")[-3]
