#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"
REQ_FILE="requirements.txt"
REQ_HASH_FILE=".venv/.requirements.sha256"
VENV_DIR=".venv"
VENV_PYTHON="${VENV_DIR}/bin/python"
MANAGE_PY_PATH=""

print_usage() {
  cat <<'EOF'
用法:
  ./manage.sh [--init] [--reinstall] [--skip-install] [django_command ...]

参数:
  --init         只初始化/更新虚拟环境与依赖后退出
  --reinstall    强制重装依赖
  --skip-install 跳过依赖检查与安装
  -h, --help     显示帮助
EOF
}

calc_requirements_hash() {
  python3 - <<'PY'
import hashlib
from pathlib import Path
path = Path("requirements.txt")
print(hashlib.sha256(path.read_bytes()).hexdigest())
PY
}

resolve_manage_py_path() {
  if [ -n "${MANAGE_PY_PATH}" ]; then
    return 0
  fi

  if [ -f "manage.py" ]; then
    MANAGE_PY_PATH="manage.py"
    return 0
  fi

  if [ -f "core/manage.py" ]; then
    MANAGE_PY_PATH="core/manage.py"
    return 0
  fi

  echo "错误: 未找到 manage.py（已尝试: ./manage.py, ./core/manage.py），当前目录: ${SCRIPT_DIR}"
  exit 1
}

ensure_requirements_installed() {
  local force_install="$1"
  local skip_install="$2"

  if [ "${skip_install}" = "true" ]; then
    echo "跳过依赖检查与安装。"
    return 0
  fi

  if [ ! -f "${REQ_FILE}" ]; then
    echo "错误: 未找到 ${REQ_FILE}，当前目录: ${SCRIPT_DIR}"
    exit 1
  fi

  local current_hash
  current_hash="$(calc_requirements_hash)"
  local previous_hash=""

  if [ -f "${REQ_HASH_FILE}" ]; then
    previous_hash="$(<"${REQ_HASH_FILE}")"
  fi

  if [ "${force_install}" = "true" ] || [ "${current_hash}" != "${previous_hash}" ]; then
    echo "正在安装/更新依赖 ..."
    "${VENV_PYTHON}" -m pip install -r "${REQ_FILE}"
    printf '%s\n' "${current_hash}" > "${REQ_HASH_FILE}"
  else
    echo "依赖未变化，跳过安装。"
  fi
}

RUN_INIT_ONLY="false"
FORCE_REINSTALL="false"
SKIP_INSTALL="false"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --init)
      RUN_INIT_ONLY="true"
      shift
      ;;
    --reinstall)
      FORCE_REINSTALL="true"
      shift
      ;;
    --skip-install)
      SKIP_INSTALL="true"
      shift
      ;;
    -h|--help)
      print_usage
      exit 0
      ;;
    *)
      break
      ;;
  esac
done

if ! command -v python3 >/dev/null 2>&1; then
  echo "错误: 未找到 python3，请先安装 Python 3.10+。"
  exit 1
fi

if [ ! -d "${VENV_DIR}" ]; then
  echo "检测到首次运行，正在创建虚拟环境 .venv ..."
  python3 -m venv "${VENV_DIR}"
fi

if [ ! -x "${VENV_PYTHON}" ]; then
  echo "检测到虚拟环境不完整，正在重建 .venv ..."
  rm -rf "${VENV_DIR}"
  python3 -m venv "${VENV_DIR}"
fi

ensure_requirements_installed "${FORCE_REINSTALL}" "${SKIP_INSTALL}"
resolve_manage_py_path

if [ "${RUN_INIT_ONLY}" = "true" ]; then
  echo "初始化完成。"
  exit 0
fi

if [ "$#" -eq 0 ]; then
  echo "未传入参数，默认执行: .venv/bin/python ${MANAGE_PY_PATH} runserver"
  exec "${VENV_PYTHON}" "${MANAGE_PY_PATH}" runserver
else
  exec "${VENV_PYTHON}" "${MANAGE_PY_PATH}" "$@"
fi
