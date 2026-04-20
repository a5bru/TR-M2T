"""
Setup script for TR-M2T with C++ extension support.
"""

from setuptools import setup, Extension
from setuptools.command.build_ext import build_ext
import sys
import os
import subprocess


class get_pybind_include:
    """Helper class to determine the pybind11 include path"""

    def __str__(self):
        try:
            import pybind11

            return pybind11.get_include()
        except ImportError:
            # If pybind11 is not installed, return empty string
            # setuptools will handle the error
            return ""


ext_modules = [
    Extension(
        "trm2t.rtcm_parser_native",
        ["src/trm2t/rtcm_parser.cpp"],
        include_dirs=[
            get_pybind_include(),
        ],
        language="c++",
        extra_compile_args=[
            "-std=c++17",
            "-O3",
            "-march=native",  # Optimize for local CPU (use -march=x86-64 for portability)
            "-ffast-math",
            "-Wall",
        ],
    ),
]


class BuildExt(build_ext):
    """Custom build extension to handle C++17 and platform-specific flags"""

    def build_extensions(self):
        # Check if compiler supports C++17
        ct = self.compiler.compiler_type
        opts = []

        if ct == "unix":
            opts.append('-DVERSION_INFO="%s"' % self.distribution.get_version())
            opts.append("-std=c++17")
            opts.append("-O3")
            opts.append("-fvisibility=hidden")
        elif ct == "msvc":
            opts.append('/DVERSION_INFO=\\"%s\\"' % self.distribution.get_version())
            opts.append("/std:c++17")
            opts.append("/O2")

        for ext in self.extensions:
            ext.extra_compile_args = opts

        build_ext.build_extensions(self)


setup(
    ext_modules=ext_modules,
    cmdclass={"build_ext": BuildExt},
    zip_safe=False,
)
