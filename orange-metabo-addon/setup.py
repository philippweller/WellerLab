from pathlib import Path
from setuptools import setup, find_packages

HERE = Path(__file__).parent

setup(
    name="orangemetabo",
    version="0.1.1",
    description="MetaboAnalyst-style univariate statistics for "
                "GC-MS / GC-IMS feature tables in Orange3",
    long_description=(HERE / "README.md").read_text(encoding="utf-8"),
    long_description_content_type="text/markdown",
    packages=find_packages(),
    include_package_data=True,
    author="Philipp Weller",
    author_email="philipp.weller@googlemail.com",
    install_requires=[
        "Orange3>=3.40.0",
        "numpy",
        "scipy",
        "matplotlib",
    ],
    entry_points={
        "orange.widgets": (
            "Metabo Weller = orangemetabo.widgets",
        ),
    },
    package_data={
        "orangemetabo": ["widgets/icons/*.svg"],
    },
    project_urls={
        "Source": "https://github.com/philippweller/WellerLab/tree/main/orange-metabo-addon",
        "Bug Tracker": "https://github.com/philippweller/WellerLab/issues",
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Topic :: Scientific/Engineering",
    ],
)
