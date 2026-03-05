# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Utility for running tests for CES agent callbacks."""

import glob
import io
import os
import sys
import tempfile
import time
from contextlib import redirect_stderr, redirect_stdout
import logging

import pandas as pd
import pytest

logger = logging.getLogger(__name__)


class CallbackUtils:
    """Provides methods for orchestrating and executing agent callback tests."""

    def run_callback_tests(
        self,
        app_root_dir: str,
        agent_name: str = "*",
        callback_type: str = "*_callbacks",
        callback_name: str = "*",
        log_file: str = None,
        pytest_args: list[str] = None,
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
            log_file: Optional. Path to a file to log pytest output to.
                If not provided, output will be logged to the console.
            pytest_args: Optional. Additional arguments to pass to pytest.
                Defaults to None.

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
            logger.warning(f"No callback tests found in {app_root_dir}")
            return pd.DataFrame(
                columns=[
                    "agent_name",
                    "callback_type",
                    "test_name",
                    "status",
                    "error_message",
                ]
            )

        logger.info(f"Found {len(test_files)} callback tests.")

        if log_file:
            log_file = os.path.abspath(log_file)
            with open(log_file, "w", encoding="utf-8") as f:
                f.write("--- Starting callback tests ---\n")

        all_results = []

        for test_file in test_files:
            test_dir = os.path.dirname(os.path.abspath(test_file))
            python_code_path = os.path.join(test_dir, "python_code.py")

            if not os.path.exists(python_code_path):
                logger.warning(
                    f"Warning: {test_file} found, but no "
                    "python_code.py exists alongside it. Skipping."
                )
                continue

            logger.debug(f"Running test for: {python_code_path}")

            with open(python_code_path, "r", encoding="utf-8") as f:
                code_content = f.read()

            with open(test_file, "r", encoding="utf-8") as f:
                test_content = f.read()

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
                        "from cxas_scrapi.utils.callback_libs import *\n"
                        + "import json\n\n"
                        + code_content
                    )

                with open(temp_test_path, "w", encoding="utf-8") as f:
                    f.write(test_content)

                original_sys_path = sys.path.copy()
                original_cwd = os.getcwd()
                try:
                    sys.path.insert(0, temp_dir)
                    os.chdir(temp_dir)

                    # Clear python_code from sys.modules to load the new code
                    if "python_code" in sys.modules:
                        del sys.modules["python_code"]

                    agent_name = self._get_agent_name(test_file)
                    callback_type = self._get_callback_type(test_file)
                    collector = _TestResultCollector(
                        test_file, agent_name, callback_type
                    )
                    args = [temp_test_path] + (pytest_args or [])
                    if log_file:
                        with open(log_file, "a", encoding="utf-8") as f:
                            with redirect_stdout(f), redirect_stderr(f):
                                pytest.main(args, plugins=[collector])
                    else:
                        f = io.StringIO()
                        with redirect_stdout(f), redirect_stderr(f):
                            pytest.main(args, plugins=[collector])

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


class _TestResultCollector:
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
                    "status": report.outcome.upper(),
                    "error_message": self._get_error_message(report),
                }
            )
        elif report.failed:
            self.results.append(
                {
                    "agent_name": self.agent_name,
                    "callback_type": self.callback_type,
                    "test_name": report.nodeid.split("::")[-1],
                    "status": report.outcome.upper(),
                    "error_message": self._get_error_message(report),
                }
            )

    def pytest_collectreport(self, report):
        if report.failed:
            self.results.append(
                {
                    "agent_name": self.agent_name,
                    "callback_type": self.callback_type,
                    "test_name": "collection_error",
                    "status": "FAILED",
                    "error_message": self._get_error_message(report),
                }
            )
