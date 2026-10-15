"""Setup pyhiveapi package."""

# pylint: skip-file
import unasync
from setuptools import setup

setup(
    cmdclass={
        "build_py": unasync.cmdclass_build_py(
            rules=[
                unasync.Rule(
                    "/apyhiveapi/",
                    "/pyhiveapi/",
                    additional_replacements={
                        "apyhiveapi": "pyhiveapi",
                        "asyncio": "threading",
                    },
                ),
                unasync.Rule(
                    "/apyhiveapi/api/",
                    "/pyhiveapi/api/",
                    additional_replacements={"apyhiveapi": "pyhiveapi"},
                ),
                unasync.Rule(
                    "/apyhiveapi/devices/",
                    "/pyhiveapi/devices/",
                    additional_replacements={
                        "apyhiveapi": "pyhiveapi",
                        "asyncio": "threading",
                    },
                ),
                unasync.Rule(
                    "/apyhiveapi/session/",
                    "/pyhiveapi/session/",
                    additional_replacements={
                        "apyhiveapi": "pyhiveapi",
                        "asyncio": "threading",
                    },
                ),
            ]
        )
    },
)
