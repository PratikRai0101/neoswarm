from setuptools import setup

setup(
    name="neoswarm",
    version="0.1.0",
    description="NeoSwarm - AI Agent Orchestrator",
    author="Pratik Rai",
    py_modules=["__init__", "__main__", "main", "tui"],
    install_requires=[
        "click>=8.0",
        "httpx>=0.27",
        "rich>=13.0",
    ],
    entry_points={
        "console_scripts": [
            "neoswarm=main:cli",
        ],
    },
    python_requires=">=3.11",
)
