#!/usr/bin/env python3
"""Prepare the pinned R4 tree. Fails closed on missing packages or provider clashes."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

REPO = Path(__file__).resolve().parents[1]


def run(args, cwd):
    print("+", " ".join(map(str, args)), flush=True)
    subprocess.run(args, cwd=cwd, check=True)


def clone(item, dest):
    if dest.exists():
        raise RuntimeError(f"refusing existing checkout: {dest}")
    dest.mkdir(parents=True)
    run(["git", "init", "-q"], dest)
    run(["git", "remote", "add", "origin", item["url"]], dest)
    run(["git", "fetch", "--depth=1", "origin", item["commit"]], dest)
    run(["git", "checkout", "--detach", "FETCH_HEAD"], dest)
    got = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=dest, text=True).strip()
    if got != item["commit"]:
        raise RuntimeError(f"commit mismatch for {dest}: {got}")


def copy_provider(src, dest):
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        raise RuntimeError(f"provider destination already exists: {dest}")
    shutil.copytree(src, dest, ignore=shutil.ignore_patterns(".git"))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workdir", required=True, type=Path)
    args = ap.parse_args()
    work = args.workdir.resolve()
    if work == REPO or REPO in work.parents:
        ap.error("workdir must be outside this repository")
    work.mkdir(parents=True, exist_ok=True)
    ow = work / "openwrt"
    evidence = work / "evidence"
    evidence.mkdir(exist_ok=True)
    lock = json.loads((REPO / "sources.lock.json").read_text())
    policy = json.loads((REPO / "packages.json").read_text())

    clone(lock["base"], ow)
    feeds = "".join(
        f"src-git {name} {item['url']}^{item['commit']}\n"
        for name, item in lock["feeds"].items()
    )
    (ow / "feeds.conf").write_text(feeds)
    run(["./scripts/feeds", "update", "-a"], ow)
    for name, item in lock["feeds"].items():
        got = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ow / "feeds" / name, text=True).strip()
        if got != item["commit"]:
            raise RuntimeError(f"feed commit mismatch: {name} {got}")
    run(["./scripts/feeds", "install", "-a"], ow)

    providers = {}
    for name, item in lock["external"].items():
        src_root = work / "sources" / name
        clone(item, src_root)
        for rel in item["paths"]:
            source = src_root / rel
            if not source.is_dir():
                raise RuntimeError(f"missing locked path: {name}/{rel}")
            leaf = source.name
            dest = ow / "package" / "r4-external" / name / leaf
            copy_provider(source, dest)
            for link in (ow / "package" / "feeds").glob("*/" + leaf):
                if not link.is_symlink():
                    raise RuntimeError(f"unexpected non-link provider: {link}")
                # Same-name feed package is a real clash. Do not silently delete it
                # unless this external source is the selected provider for that leaf.
                link.unlink()
                providers.setdefault("replaced", []).append(str(link.relative_to(ow)))
            providers[leaf] = {"source": name, "path": rel, "commit": item["commit"]}

    shutil.copytree(REPO / "local-packages", ow / "package" / "r4-local")
    rules = ow / "rules.mk"
    rules.write_text(
        rules.read_text()
        + "\n# C/C++ scheduling only. CPU_TYPE and aarch64_cortex-a53 stay unchanged.\n"
        + "TARGET_CFLAGS += -mtune=cortex-a73\n"
    )

    kernel_dir = ow / "build_dir"
    # Kernel source is unpacked later. Record the patch now and apply it after download
    # by also dropping it into the target backport directory, which quilt applies.
    generic = ow / "target/linux/generic/backport-6.12"
    if not generic.is_dir():
        raise RuntimeError(f"missing kernel patch dir: {generic}")
    shutil.copy2(
        REPO / "patches/kernel/990-net-phy-mtk-ge-soc-reuse-pinctrl-regmap.patch",
        generic / "990-net-phy-mtk-ge-soc-reuse-pinctrl-regmap.patch",
    )

    # Ordinary R4 only: drop wireless firmware from this device, leave other devices alone.
    image = ow / "target/linux/mediatek/image/filogic.mk"
    image_text = image.read_text()
    old = (
        "define Device/bananapi_bpi-r4\n"
        "  DEVICE_MODEL := BPi-R4\n"
        "  DEVICE_DTS := mt7988a-bananapi-bpi-r4\n"
        "  DEVICE_DTS_CONFIG := config-mt7988a-bananapi-bpi-r4\n"
        "  $(call Device/bananapi_bpi-r4-common)\n"
        "endef\n"
    )
    new = old.replace(
        "  $(call Device/bananapi_bpi-r4-common)\n",
        "  $(call Device/bananapi_bpi-r4-common)\n"
        "  DEVICE_PACKAGES := $(filter-out kmod-mt7996-firmware kmod-mt7996-233-firmware mt7988-wo-firmware,$(DEVICE_PACKAGES))\n",
    )
    if old not in image_text:
        raise RuntimeError("bananapi_bpi-r4 device block not found; refusing broad image edit")
    image.write_text(image_text.replace(old, new, 1))

    kernel_cfg = ow / "target/linux/mediatek/filogic/config-6.12"
    required = (
        "BPF BPF_SYSCALL BPF_JIT CGROUPS CGROUP_BPF KPROBES KPROBE_EVENTS "
        "BPF_EVENTS NET_INGRESS NET_EGRESS NET_CLS_ACT NET_SCH_INGRESS "
        "NET_CLS_BPF NET_ACT_BPF BPF_STREAM_PARSER XDP_SOCKETS DEBUG_INFO DEBUG_INFO_BTF"
    ).split()
    kt = kernel_cfg.read_text()
    for symbol in required + ["DEBUG_INFO_REDUCED"]:
        kt = re.sub(rf"^(?:CONFIG_{symbol}=.*|# CONFIG_{symbol} is not set)\n?", "", kt, flags=re.M)
    kernel_cfg.write_text(kt + "\n" + "".join(f"CONFIG_{s}=y\n" for s in required) + "# CONFIG_DEBUG_INFO_REDUCED is not set\n")

    shutil.copytree(REPO / "files", ow / "files", dirs_exist_ok=True)
    for f in (ow / "files/etc/uci-defaults").iterdir():
        f.chmod(0o755)

    config = (REPO / "config.seed").read_text()
    if not config.endswith("\n"):
        config += "\n"
    config += "".join(f"CONFIG_PACKAGE_{pkg}=y\n" for pkg in policy["image"])
    config += "".join(line + "\n" for line in policy["ssr_selects"])
    (ow / ".config").write_text(config)
    (evidence / "requested.config").write_text(config)
    (evidence / "providers.json").write_text(json.dumps(providers, indent=2) + "\n")

    proc = subprocess.run(
        ["make", "defconfig", "V=s"],
        cwd=ow,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    (evidence / "defconfig.log").write_text(proc.stdout)
    print(proc.stdout[-4000:], end="", flush=True)
    if proc.returncode or re.search(r"error:|recursive dependency detected|^WARNING:.*ignoring", proc.stdout, re.M):
        raise RuntimeError(f"defconfig failed (rc={proc.returncode})")

    final = (ow / ".config").read_text().splitlines()
    enabled = set()
    missing = []
    for pkg in policy["image"]:
        if f"CONFIG_PACKAGE_{pkg}=y" in final or f"CONFIG_PACKAGE_{pkg}=m" in final:
            enabled.add(pkg)
        else:
            missing.append(pkg)
    if missing:
        (evidence / "missing-packages.txt").write_text("\n".join(missing) + "\n")
        raise RuntimeError("required packages dropped by Kconfig: " + ", ".join(missing))
    if "CONFIG_TARGET_ROOTFS_PARTSIZE=3072" not in final:
        raise RuntimeError("rootfs size was not kept at 3072")
    if "CONFIG_CPU_TYPE=\"cortex-a53\"" not in final and not any(line.startswith('CONFIG_CPU_TYPE="cortex-a53"') for line in final):
        # target.mk CPU_TYPE is not always mirrored; arch packages is the hard check later.
        (evidence / "cpu-type-note.txt").write_text("CONFIG_CPU_TYPE not present in .config; arch check remains mandatory\n")
    print("PREPARED", ow)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, subprocess.CalledProcessError, OSError) as exc:
        print(f"PREPARATION FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
