from setuptools import setup, find_packages

setup(
    name="neoswarm",
    version="0.1.0",
    description="NeoSwarm - AI Agent Orchestrator",
    author="Pratik Rai",
    packages=find_packages(),
    install_requires=[
        "click>=8.0",
        "httpx>=0.27",
        "rich>=13.0",
    ],
    entry_points={
        "console_scripts": [
            "neoswarm=cli:main",
        ],
    },
    python_requires=">=3.11",
)
