"""
Setup script for the Vimeo to Roku SDK.
"""

from setuptools import setup, find_packages
from pathlib import Path

# Read README for long description
readme_path = Path(__file__).parent / "README.md"
long_description = readme_path.read_text(encoding="utf-8") if readme_path.exists() else ""

setup(
    name="vimeo-roku-sdk",
    version="1.0.0",
    author="Knox Media Group",
    author_email="dev@knoxmediagroup.com",
    description="SDK for syncing video content from Vimeo to Roku Direct Publisher channels",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/Knox-Media-Group/KMGI",
    packages=find_packages(exclude=["tests", "tests.*"]),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Multimedia :: Video",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
    python_requires=">=3.8",
    install_requires=[
        "requests>=2.28.0",
        "PyYAML>=6.0",
    ],
    extras_require={
        "s3": ["boto3>=1.26.0"],
        "scheduler": ["schedule>=1.2.0"],
        "dev": [
            "pytest>=7.0.0",
            "pytest-cov>=4.0.0",
            "responses>=0.23.0",
            "black>=23.0.0",
            "flake8>=6.0.0",
            "mypy>=1.0.0",
        ],
        "all": [
            "boto3>=1.26.0",
            "schedule>=1.2.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "vimeo-roku=vimeo_roku_sdk.cli:main",
        ],
    },
    keywords=[
        "vimeo",
        "roku",
        "video",
        "streaming",
        "ott",
        "direct-publisher",
        "content-sync",
    ],
    project_urls={
        "Bug Reports": "https://github.com/Knox-Media-Group/KMGI/issues",
        "Source": "https://github.com/Knox-Media-Group/KMGI",
    },
)
