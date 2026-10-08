from pathlib import Path
from setuptools import setup, find_packages

HERE = Path(__file__).parent

setup(
    name="orangepca",
    version="0.1.2",
    description="Chemometrics PCA for Orange3 - preprocessing (autoscale/pareto/center), "
                "explained variance on axes, and Hotelling T2/Q-residual outlier diagnostics "
                "with filtering.",
    long_description=(HERE / "README.md").read_text(encoding="utf-8"),
    long_description_content_type="text/markdown",
    packages=find_packages(),
    include_package_data=True,
    author="Philipp Weller",
    author_email="philipp.weller@googlemail.com",
    install_requires=[
        "Orange3>=3.40.0",
        "numpy",
        "scikit-learn",
        "scipy",
        "pyqtgraph",
    ],
    entry_points={
        "orange.widgets": (
            "WellerLab PCA = orangepca.widgets",
        ),
    },
    package_data={
        "orangepca": ["widgets/icons/*.svg"],
    },
    project_urls={
        "Source": "https://github.com/philippweller/WellerLab/tree/main/orange-pca-addon",
        "Bug Tracker": "https://github.com/philippweller/WellerLab/issues",
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Science/Research",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
        "License :: OSI Approved :: MIT License",
    ],
    python_requires=">=3.9",
)