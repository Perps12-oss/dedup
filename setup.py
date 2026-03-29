"""
DEDUP - Setup script
"""

from pathlib import Path

from setuptools import find_packages, setup

# Read README
readme_path = Path(__file__).parent / "README.md"
long_description = readme_path.read_text(encoding="utf-8") if readme_path.exists() else ""

setup(
    name="dedup",
    version="3.0.0",
    description="A minimal, high-performance duplicate file finder",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="DEDUP Project",
    python_requires=">=3.11",
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
        "customtkinter>=5.2.0",
        "xxhash>=3.0.0",
        "send2trash>=1.8.0",
    ],
    extras_require={
        "recommended": [
            "tkinterdnd2>=0.4.2",
            "Pillow>=9.0.0",
        ],
        "modern-ui": [
            "sv-ttk>=2.6.0",
            "pywinstyles>=1.9.0",
        ],
        "dev": [
            "pytest>=7.0.0",
            "pytest-cov>=4.0.0",
            "mypy>=1.0.0",
        ],
    },
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: End Users/Desktop",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Topic :: System :: Filesystems",
        "Topic :: Utilities",
    ],
)
