#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
    echo "Run with sudo: sudo $0" >&2
    exit 1
fi

prune_stale_nodes() {
    local dev_dir="$1"
    local prefix="$2"
    local sys_dir="$3"
    local node name

    [[ -d "$dev_dir" ]] || return 0

    for node in "$dev_dir"/${prefix}*; do
        [[ -e "$node" ]] || continue
        name="$(basename "$node")"
        if [[ ! -e "${sys_dir}/${name}" ]]; then
            rm -f "$node"
            echo "removed stale ${node}"
        fi
    done
}

ensure_node() {
    local sys_class_path="$1"
    local target_path="$2"
    local group_name="$3"
    local mode="$4"

    [[ -e "${sys_class_path}/dev" ]] || return 0

    local devnums major minor
    devnums="$(<"${sys_class_path}/dev")"
    major="${devnums%%:*}"
    minor="${devnums##*:}"

    mkdir -p "$(dirname "${target_path}")"

    if [[ ! -e "${target_path}" ]]; then
        mknod "${target_path}" c "${major}" "${minor}"
        echo "created ${target_path} (${major}:${minor})"
    fi

    chgrp "${group_name}" "${target_path}" || true
    chmod "${mode}" "${target_path}"
}

prune_stale_nodes /dev/input js /sys/class/input
prune_stale_nodes /dev/input event /sys/class/input
prune_stale_nodes /dev ttyUSB /sys/class/tty
prune_stale_nodes /dev ttyACM /sys/class/tty

for js in /sys/class/input/js*; do
    [[ -e "${js}" ]] || continue
    ensure_node "${js}" "/dev/input/$(basename "${js}")" input 0664
done

for event in /sys/class/input/event*; do
    [[ -e "${event}" ]] || continue
    ensure_node "${event}" "/dev/input/$(basename "${event}")" input 0660
done

for tty in /sys/class/tty/ttyUSB*; do
    [[ -e "${tty}" ]] || continue
    ensure_node "${tty}" "/dev/$(basename "${tty}")" dialout 0660
done
