from component.handle.python_package_component.api import (
    install_python_package,
    query_python_package,
    uninstall_python_package,
)


def run_demo() -> None:
    package_name = "requests"
    print("查询：", query_python_package(package_name=package_name))
    print("安装：", install_python_package(package_name=package_name, upgrade=False))
    print("卸载：", uninstall_python_package(package_name=package_name))


if __name__ == "__main__":
    run_demo()
