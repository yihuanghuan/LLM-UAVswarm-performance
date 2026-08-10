from setuptools import find_packages, setup


package_name = "lfs_policy"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        ("share/" + package_name + "/config", ["config/lfs_policy.migration.yaml"]),
    ],
    install_requires=["setuptools", "PyYAML"],
    zip_safe=True,
    maintainer="yihuang",
    maintainer_email="yihuang@example.com",
    description="Shared typed policy loader for Candidate LFS runtime",
    license="Apache-2.0",
)
