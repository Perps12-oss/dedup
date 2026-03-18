"""
DEDUP - Setup script
"""

from setuptools import setup, find_packages
from pathlib import Path

# Read README
readme_path = Path(__file__).parent / "README.md"
long_description = readme_path.read_text(encoding="utf-8") if readme_path.exists() else ""

setup(
    name="dedup",
    version="1.0.0",
    description="A minimal, high-performance duplicate file finder",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="DEDUP Project",
    python_requires=">=3.9",
    packages=find_packages(exclude=["dedup.tests", "dedup.tests.*"]),
    entry_points={
        "console_scripts": [
            "dedup=dedup.main:main",
        ],
        "gui_scripts": [
            "cerebro=dedup.main:run_gui",
        ],
    },
    install_requires=[
        # Core has no required dependencies - uses standard library only
    ],
    extras_require={
        "recommended": [
            "xxhash>=3.0.0",
            "send2trash>=1.8.0",
            "tkinterdnd2>=0.4.2",
            "Pillow>=9.0.0",
        ],
        "dev": [
            "pytest>=7.0.0",
            "pytest-cov>=4.0.0",
            "mypy>=1.0.0",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: End Users/Desktop",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: System :: Filesystems",
        "Topic :: Utilities",
    ],
)
