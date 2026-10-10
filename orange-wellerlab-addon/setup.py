from pathlib import Path

from setuptools import setup, find_packages

HERE = Path(__file__).parent

README = HERE / "README.md"
long_description = (README.read_text(encoding="utf-8") if README.exists()
                    else "WellerLab Orange3 tool suite: metabolomics feature-table "
                         "statistics, PLS-DA/OPLS-DA, PCA Pro and NMR preprocessing.")

setup(
    name="wellerlab",
    version="0.1.9",
    description="WellerLab Orange3 suite: Metabo statistics, PLS-DA/OPLS-DA, "
                "PCA Pro and NMR preprocessing in one category",
    long_description=long_description,
    long_description_content_type="text/markdown",
    packages=find_packages(include=["wellerlab", "wellerlab.*"]),
    include_package_data=True,
    author="Philipp Weller",
    author_email="philipp.weller@googlemail.com",
    install_requires=[
        "Orange3>=3.40.0",
        "numpy",
        "scipy",
        "matplotlib",
        "scikit-learn",
        "pandas",
    ],
    entry_points={
        "orange.widgets": (
            "Weller Lab = wellerlab.widgets",
        ),
    },
    package_data={
        "wellerlab": ["widgets/icons/*.svg",
                      "metabo/widgets/icons/*.svg",
                      "plsda/widgets/icons/*.svg",
                      "pca/widgets/icons/*.svg",
                      "nmr/widgets/icons/*.svg"],
    },
    project_urls={
        "Source": "https://github.com/philippweller/WellerLab/tree/main/orange-wellerlab-addon",
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
