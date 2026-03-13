"""Tests to ensure the **kwargs authentication regression doesn't reappear."""

import inspect
import pkgutil
import importlib

import cxas_scrapi.core
from cxas_scrapi.core.common import Common


def test_core_classes_accept_kwargs():
    """
    Dynamically ensures all core API wrapper classes inheriting from Common
    accept **kwargs so that credentials and routing variables can be safely
    passed down the inheritance chain.
    """
    package = cxas_scrapi.core
    missing_kwargs_classes = []

    for _, module_name, _ in pkgutil.iter_modules(package.__path__):
        full_module_name = f"{package.__name__}.{module_name}"
        module = importlib.import_module(full_module_name)

        for name, obj in inspect.getmembers(module):
            # Check if it is a class and inherits from Common
            if inspect.isclass(obj) and issubclass(obj, Common):
                # Ignore the base Common class itself since it natively implements kwargs
                if obj is Common:
                    continue

                # Guarantee it's a class defined specifically in this module
                if obj.__module__ == full_module_name:
                    sig = inspect.signature(obj.__init__)
                    has_kwargs = any(
                        param.kind == inspect.Parameter.VAR_KEYWORD
                        for param in sig.parameters.values()
                    )
                    if not has_kwargs:
                        missing_kwargs_classes.append(
                            f"{full_module_name}.{obj.__name__}"
                        )

    assert not missing_kwargs_classes, (
        "The following core wrapper classes are missing **kwargs in their __init__ "
        f"signature, which breaks creds inheritance: {missing_kwargs_classes}"
    )
