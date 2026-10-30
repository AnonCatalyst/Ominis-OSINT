"""Package metadata for Ominis-OSINT.

MIT licensed. Maintained by AnonCatalyst with the WinterGate Intelligence
Collective. https://wintergate.org
"""

from pathlib import Path

from setuptools import find_packages, setup

HERE = Path(__file__).resolve().parent if "__file__" in globals() else Path.cwd()
README = (HERE / "README.md").read_text(encoding="utf-8")

setup(
    name="ominis-osint-suite",
    version="1.0.1",
    packages=find_packages(include=["ominis_src", "ominis_src.*"]),
    package_data={"ominis_src": ["*.json", "*.txt"]},
    py_modules=["ominis"],
    python_requires=">=3.10",
    install_requires=[
        "beautifulsoup4>=4.12",
        "colorama>=0.4.6",
        "httpx[http2,socks]>=0.28.1",
        "aiohttp>=3.10",
        # 0.36.0 dropped Python 3.10, so keep the last 3.10-compatible release
        # there and use the current line everywhere else.
        "validators==0.35.0; python_version < '3.11'",
        "validators>=0.36.0; python_version >= '3.11'",
    ],
    extras_require={
        "test": [
            "pytest>=8",
            "pytest-asyncio>=0.24",
            "trustme>=1.2",
            "build>=1.2",
        ],
    },
    entry_points={
        "console_scripts": [
            "ominis=ominis_src.cli:main",
        ],
    },
    include_package_data=True,
    description="Discover online mentions of a query or username. "
                "Identify potential social profiles and forums.",
    long_description=README,
    long_description_content_type="text/markdown",
    author="AnonCatalyst",
    author_email="hard2find.co.01@gmail.com",
    url="https://github.com/AnonCatalyst/Ominis-OSINT",
    project_urls={
        "Homepage": "https://wintergate.org",
        "Source": "https://github.com/AnonCatalyst/Ominis-OSINT",
        "Issues": "https://github.com/AnonCatalyst/Ominis-OSINT/issues",
        "Changelog": "https://github.com/AnonCatalyst/Ominis-OSINT/releases",
    },
    license="MIT",
    license_files=["LICENSE", "TRADEMARKS.md"],
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Environment :: Console",
        "Intended Audience :: Information Technology",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Security",
        "Topic :: Internet :: WWW/HTTP",
    ],
    keywords="osint reconnaissance search username privacy",
)
