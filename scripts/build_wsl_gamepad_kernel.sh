#!/usr/bin/env bash
set -euo pipefail

usage() {
    cat <<'EOF'
Build a custom WSL kernel with JOYDEV + XPAD enabled for direct Xbox gamepad use.

Default behavior:
  - clones / updates the official Microsoft WSL2-Linux-Kernel repo
  - checks out the tag that matches the currently running WSL kernel
  - enables INPUT_JOYSTICK + INPUT_EVDEV + INPUT_JOYDEV + JOYSTICK_XPAD + HID_MICROSOFT
  - builds the kernel and modules.vhdx
  - copies artifacts into a Windows-accessible folder
  - writes a .wslconfig snippet next to the built artifacts

Usage:
  scripts/build_wsl_gamepad_kernel.sh
  scripts/build_wsl_gamepad_kernel.sh --tag linux-msft-wsl-6.6.87.2
  scripts/build_wsl_gamepad_kernel.sh --repo-dir ~/SOMA/DRIVERS/WSL2-Linux-Kernel
  scripts/build_wsl_gamepad_kernel.sh --install-dir /mnt/c/Users/<WINUSER>/wsl-kernels/wsl-6.6.87.2-xpad
  scripts/build_wsl_gamepad_kernel.sh --jobs 8
  scripts/build_wsl_gamepad_kernel.sh --skip-fetch

After the script finishes:
  1. Merge the generated .wslconfig snippet into %UserProfile%\.wslconfig
  2. Run: wsl --shutdown
  3. Re-open WSL
  4. Run scripts/attach_devices.bat on Windows as Administrator
  5. Run scripts/check_wsl_gamepad_support.sh inside WSL
EOF
}

package_modules_vhdx_rootless() {
    local modules_dir="$1"
    local kernel_release="$2"
    local output_file="$3"
    local tmp_dir=""
    local modules_size=0
    local image_size=0

    tmp_dir="$(mktemp -d)"
    cleanup() {
        rm -rf "$tmp_dir"
    }
    trap cleanup RETURN

    modules_size="$(du -bs "$modules_dir" | awk '{print $1}')"
    image_size=$((modules_size + (256 * (1 << 20))))

    truncate -s "$image_size" "$tmp_dir/modules.img"
    mke2fs -q -F -t ext4 \
        -d "$modules_dir/lib/modules/$kernel_release" \
        "$tmp_dir/modules.img"
    qemu-img convert -O vhdx "$tmp_dir/modules.img" "$output_file"
}

need_cmd() {
    local cmd="$1"
    if ! command -v "$cmd" >/dev/null 2>&1; then
        echo "ERROR: missing required command: $cmd" >&2
        exit 1
    fi
}

detect_windows_user() {
    local user=""
    if command -v cmd.exe >/dev/null 2>&1; then
        user="$(cmd.exe /c "echo %USERNAME%" 2>/dev/null | tr -d '\r' | tail -n 1 || true)"
    fi
    printf '%s' "$user"
}

RUNNING_KERNEL="$(uname -r)"
BASE_KERNEL="${RUNNING_KERNEL%-microsoft-standard-WSL2}"
DEFAULT_TAG="linux-msft-wsl-${BASE_KERNEL}"
DEFAULT_REPO_DIR="${HOME}/SOMA/DRIVERS/WSL2-Linux-Kernel"
WINDOWS_USER="$(detect_windows_user)"
DEFAULT_INSTALL_DIR=""
if [[ -n "$WINDOWS_USER" && -d "/mnt/c/Users/${WINDOWS_USER}" ]]; then
    DEFAULT_INSTALL_DIR="/mnt/c/Users/${WINDOWS_USER}/wsl-kernels/${DEFAULT_TAG}-xpad"
fi

REPO_DIR="$DEFAULT_REPO_DIR"
KERNEL_TAG="$DEFAULT_TAG"
INSTALL_DIR="$DEFAULT_INSTALL_DIR"
JOBS="$(nproc)"
SKIP_FETCH=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --repo-dir)
            REPO_DIR="$2"
            shift 2
            ;;
        --tag)
            KERNEL_TAG="$2"
            shift 2
            ;;
        --install-dir)
            INSTALL_DIR="$2"
            shift 2
            ;;
        --jobs)
            JOBS="$2"
            shift 2
            ;;
        --skip-fetch)
            SKIP_FETCH=1
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "ERROR: unknown argument: $1" >&2
            usage >&2
            exit 1
            ;;
    esac
done

need_cmd git
need_cmd make
need_cmd wslpath
need_cmd qemu-img
need_cmd mke2fs

mkdir -p "$(dirname "$REPO_DIR")"
if [[ ! -d "$REPO_DIR/.git" ]]; then
    echo "[wsl-kernel] cloning Microsoft WSL2-Linux-Kernel into $REPO_DIR"
    git clone https://github.com/microsoft/WSL2-Linux-Kernel.git "$REPO_DIR"
fi

cd "$REPO_DIR"

if [[ "$SKIP_FETCH" -eq 0 ]]; then
    echo "[wsl-kernel] fetching latest tags"
    git fetch --tags origin
fi

echo "[wsl-kernel] checking out $KERNEL_TAG"
git checkout "$KERNEL_TAG"

CONFIG_FILE="$REPO_DIR/.config-soma-gamepad"
    echo "[wsl-kernel] generating config: $CONFIG_FILE"
cp Microsoft/config-wsl "$CONFIG_FILE"
./scripts/config --file "$CONFIG_FILE" \
    -e INPUT_JOYSTICK \
    -e INPUT_EVDEV \
    -e INPUT_JOYDEV \
    -e JOYSTICK_XPAD \
    -e HID_MICROSOFT

echo "[wsl-kernel] resolving dependencies"
make KCONFIG_CONFIG="$CONFIG_FILE" olddefconfig

echo "[wsl-kernel] building kernel (jobs=$JOBS)"
make KCONFIG_CONFIG="$CONFIG_FILE" -j"$JOBS"

echo "[wsl-kernel] installing modules into a staging directory"
rm -rf "$REPO_DIR/modules" "$REPO_DIR/modules.vhdx"
make KCONFIG_CONFIG="$CONFIG_FILE" INSTALL_MOD_PATH="$REPO_DIR/modules" modules_install

KERNEL_RELEASE="$(make -s KCONFIG_CONFIG="$CONFIG_FILE" kernelrelease)"
echo "[wsl-kernel] packaging modules.vhdx for kernel release $KERNEL_RELEASE"
if ! package_modules_vhdx_rootless "$REPO_DIR/modules" "$KERNEL_RELEASE" "$REPO_DIR/modules.vhdx"; then
    if command -v sudo >/dev/null 2>&1; then
        echo "[wsl-kernel] rootless packaging failed, falling back to the Microsoft helper via sudo"
        sudo ./Microsoft/scripts/gen_modules_vhdx.sh "$REPO_DIR/modules" "$KERNEL_RELEASE" "$REPO_DIR/modules.vhdx"
    else
        echo "ERROR: failed to package modules.vhdx rootlessly and sudo is unavailable" >&2
        exit 1
    fi
fi

if [[ -z "$INSTALL_DIR" ]]; then
    echo
    echo "[wsl-kernel] build finished"
    echo "[wsl-kernel] kernel image : $REPO_DIR/arch/x86/boot/bzImage"
    echo "[wsl-kernel] modules.vhdx : $REPO_DIR/modules.vhdx"
    echo "[wsl-kernel] no --install-dir supplied, so nothing was copied into /mnt/c"
    echo "[wsl-kernel] rerun with --install-dir to stage files for .wslconfig"
    exit 0
fi

mkdir -p "$INSTALL_DIR"
cp "$REPO_DIR/arch/x86/boot/bzImage" "$INSTALL_DIR/bzImage"
cp "$REPO_DIR/modules.vhdx" "$INSTALL_DIR/modules.vhdx"

KERNEL_WIN="$(wslpath -w "$INSTALL_DIR/bzImage" | sed 's#\\#\\\\#g')"
MODULES_WIN="$(wslpath -w "$INSTALL_DIR/modules.vhdx" | sed 's#\\#\\\\#g')"
SNIPPET="$INSTALL_DIR/wslconfig.snippet.txt"

cat > "$SNIPPET" <<EOF
[wsl2]
kernel=$KERNEL_WIN
kernelModules=$MODULES_WIN
EOF

echo
echo "[wsl-kernel] build finished"
echo "[wsl-kernel] kernel image : $INSTALL_DIR/bzImage"
echo "[wsl-kernel] modules.vhdx : $INSTALL_DIR/modules.vhdx"
echo "[wsl-kernel] .wslconfig snippet written to:"
echo "             $SNIPPET"
echo
echo "[wsl-kernel] next steps"
echo "  1. Merge the snippet into %UserProfile%\\.wslconfig"
echo "  2. Run: wsl --shutdown"
echo "  3. Re-open WSL"
echo "  4. On Windows, run scripts/attach_devices.bat as Administrator"
echo "  5. In WSL, run scripts/check_wsl_gamepad_support.sh"
