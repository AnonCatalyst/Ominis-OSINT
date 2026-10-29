"""Packaging for the legacy 0.5.x interactive build."""

from pathlib import Path

from setuptools import find_packages, setup

HERE = Path(__file__).resolve().parent
README = (HERE / "README.md").read_text(encoding="utf-8")

setup(
    name="Ominis-OSINT",
    version="0.5.0",
    packages=find_packages(include=["ominis_src", "ominis_src.*"]),
    package_data={"ominis_src": ["*.json", "*.txt"]},
    py_modules=["ominis"],
    python_requires=">=3.10",
    install_requires=[
        "beautifulsoup4>=4.12",
        "colorama>=0.4.6",
        "httpx[http2,socks]>=0.28.1",
        "validators>=0.34",
    ],
    extras_require={
        "test": [
            "pytest>=8",
            "pytest-asyncio>=0.24",
            "build>=1.2",
        ],
    },
    entry_points={"console_scripts": ["ominis=ominis:run"]},
    include_package_data=True,
    description="Discover online mentions of a query or username. "
                "Legacy interactive build with optional proxies.",
    long_description=README,
    long_description_content_type="text/markdown",
    author="AnonCatalyst",
    author_email="hard2find.co.01@gmail.com",
    url="https://github.com/AnonCatalyst/Ominis-OSINT",
    project_urls={
        "Homepage": "https://wintergate.org",
        "Issues": "https://github.com/AnonCatalyst/Ominis-OSINT/issues",
    },
    license="MIT",
    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Security",
        "Topic :: Internet :: WWW/HTTP",
    ],
    keywords="osint reconnaissance search username privacy",
)
