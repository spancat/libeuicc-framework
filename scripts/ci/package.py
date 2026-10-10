#!/usr/bin/env python3
"""Assemble verified XCFrameworks from independently built SDK variants."""

import hashlib
import json
import os
import plistlib
import re
import shutil
import subprocess
import tarfile
import zipfile
from pathlib import Path

ROOT = Path.cwd()
COLLECTED = ROOT / "build/ci-collected"
EXTRACTED = ROOT / "build/ci-extracted"
PACKAGE = ROOT / "build/ci-package"
SLICES = {
    "OS64": ("ios", None, {"arm64"}, "IOS"),
    "SIMULATORARM64": ("ios", "simulator", {"arm64", "x86_64"}, "IOSSIMULATOR"),
    "TVOS": ("tvos", None, {"arm64"}, "TVOS"),
    "SIMULATORARM64_TVOS": ("tvos", "simulator", {"arm64", "x86_64"}, "TVOSSIMULATOR"),
    "WATCHOS": ("watchos", None, {"arm64_32", "arm64"}, "WATCHOS"),
    "SIMULATORARM64_WATCHOS": (
        "watchos",
        "simulator",
        {"arm64", "x86_64"},
        "WATCHOSSIMULATOR",
    ),
    "MAC_UNIVERSAL": ("macos", None, {"arm64", "x86_64"}, "MACOS"),
}


def run(*args):
    return subprocess.check_output(args, text=True).strip()


def verify_framework(framework, version, platform, expected_architectures, macho_platform):
    binary = framework / "libeuicc"
    assert binary.is_file(), f"Missing binary: {binary}"
    plist = framework / "Resources/Info.plist"
    if not plist.is_file():
        plist = framework / "Info.plist"
    with plist.open("rb") as file:
        info = plistlib.load(file)
    assert info["CFBundleShortVersionString"] == version, (framework, info)
    assert info["CFBundleVersion"] == version, (framework, info)
    assert (framework / "Headers/libeuicc.h").is_file(), framework
    assert (framework / "Headers/version.h").is_file(), framework
    assert (framework / "Modules/module.modulemap").is_file(), framework
    resources = framework / "Resources"
    if not resources.is_dir():
        resources = framework
    for license_name in ("LICENSE", "libeuicc-LICENSE", "cjson-LICENSE"):
        assert (resources / license_name).is_file(), (framework, license_name)
    actual_architectures = set(run("lipo", "-archs", str(binary)).split())
    assert actual_architectures == expected_architectures, (
        framework,
        actual_architectures,
        expected_architectures,
    )
    for arch in actual_architectures:
        build_info = run("xcrun", "vtool", "-show-build", "-arch", arch, str(binary))
        match = re.search(r"platform\s+([A-Z0-9_]+)", build_info, re.IGNORECASE)
        assert match and match.group(1).upper() == macho_platform, (
            framework,
            arch,
            build_info,
        )
        symbols = run("nm", "-arch", arch, "-gU", str(binary))
        assert re.search(r"\b_euicc_init\b", symbols), (framework, arch)
        assert re.search(r"\b_libeuicc_get_version\b", symbols), (framework, arch)
    return sorted(actual_architectures)


def verify_dsym(framework, dsym):
    debug_binary = dsym / "Contents/Resources/DWARF/libeuicc"
    assert debug_binary.is_file(), dsym

    def uuids(binary):
        found = re.findall(
            r"UUID: ([0-9A-Fa-f-]+) \(([^)]+)\)",
            run("xcrun", "dwarfdump", "--uuid", str(binary)),
        )
        return {arch: uuid.lower() for uuid, arch in found}

    binary_uuids = uuids(framework / "libeuicc")
    dsym_uuids = uuids(debug_binary)
    assert binary_uuids and binary_uuids == dsym_uuids, dsym


def smoke_macos(framework, version):
    """Compile and execute small C/Objective-C clients against the packaged framework."""
    source = PACKAGE / "smoke.c"
    source.write_text(
        '#include <libeuicc/libeuicc.h>\n'
        '#include <string.h>\n'
        'int main(void) { const char *v = 0; libeuicc_get_version(&v); '
        f'return !v || strcmp(v, "{version}"); }}\n'
    )
    objc = PACKAGE / "smoke.m"
    objc.write_text(
        '@import libeuicc;\n'
        '#include <string.h>\n'
        'int main(void) { const char *v = 0; libeuicc_get_version(&v); '
        f'return !v || strcmp(v, "{version}"); }}\n'
    )
    swift = PACKAGE / "smoke.swift"
    swift.write_text(
        'import libeuicc\n'
        'var version: UnsafePointer<CChar>? = nil\n'
        'libeuicc_get_version(&version)\n'
        f'if version == nil || String(cString: version!) != "{version}" {{ fatalError("wrong version") }}\n'
    )
    env = os.environ.copy()
    env["DYLD_FRAMEWORK_PATH"] = str(framework.parent)
    for language, input_file in (("c", source), ("objective-c", objc)):
        executable = PACKAGE / f"smoke-{language}"
        subprocess.run(
            [
                "xcrun", "clang", "-fmodules", "-F", str(framework.parent),
                "-framework", "libeuicc", str(input_file), "-o", str(executable),
            ],
            check=True,
        )
        subprocess.run([str(executable)], env=env, check=True)
        executable.unlink()
        input_file.unlink()
    swift_executable = PACKAGE / "smoke-swift"
    subprocess.run(
        [
            "xcrun", "swiftc", "-F", str(framework.parent),
            "-framework", "libeuicc", str(swift), "-o", str(swift_executable),
        ],
        check=True,
    )
    subprocess.run([str(swift_executable)], env=env, check=True)
    swift_executable.unlink()
    swift.unlink()


def verify_xcframework(xcframework, version):
    with (xcframework / "Info.plist").open("rb") as file:
        info = plistlib.load(file)
    libraries = info["AvailableLibraries"]
    assert len(libraries) == len(SLICES), (xcframework, libraries)
    actual = {}
    for entry in libraries:
        key = (entry["SupportedPlatform"], entry.get("SupportedPlatformVariant"))
        assert key not in actual, (xcframework, key)
        actual[key] = entry
    for platform, variant, archs, macho_platform in SLICES.values():
        entry = actual[(platform, variant)]
        assert set(entry["SupportedArchitectures"]) == archs, entry
        framework = xcframework / entry["LibraryIdentifier"] / entry["LibraryPath"]
        verify_framework(framework, version, platform, archs, macho_platform)


def main():
    version = os.environ["UPSTREAM_VERSION"]
    assert re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version)
    for variable in ("UPSTREAM_SHA", "TOOLCHAIN_SHA", "WRAPPER_SHA"):
        assert re.fullmatch(r"[0-9a-f]{40}", os.environ[variable]), variable
    if EXTRACTED.exists():
        shutil.rmtree(EXTRACTED)
    PACKAGE.mkdir(parents=True, exist_ok=True)
    provenance = []
    for name, (platform, variant, archs, macho_platform) in SLICES.items():
        archive = COLLECTED / f"framework-{name}" / f"framework-{name}.tar.gz"
        assert archive.is_file(), archive
        destination = EXTRACTED / name
        destination.mkdir(parents=True)
        with tarfile.open(archive, "r:gz") as tar:
            for member in tar.getmembers():
                path = Path(member.name)
                assert not path.is_absolute() and ".." not in path.parts, member.name
            tar.extractall(destination)
        for config in ("Debug", "Release"):
            framework = destination / config / "libeuicc.framework"
            verify_framework(framework, version, platform, archs, macho_platform)
            dsym = destination / config / "libeuicc.framework.dSYM"
            assert dsym.is_dir(), dsym
            verify_dsym(framework, dsym)
        provenance.append(
            {
                "build_platform": name,
                "platform": platform,
                "variant": variant or "device",
                "architectures": sorted(archs),
            }
        )
    checksums = {}
    for config in ("Debug", "Release"):
        xcframework = PACKAGE / f"libeuicc-{config}.xcframework"
        command = ["xcodebuild", "-create-xcframework"]
        for name in SLICES:
            framework = EXTRACTED / name / config / "libeuicc.framework"
            command += ["-framework", str(framework)]
            dsym = EXTRACTED / name / config / "libeuicc.framework.dSYM"
            assert dsym.is_dir(), dsym
            command += ["-debug-symbols", str(dsym)]
        command += ["-output", str(xcframework)]
        subprocess.run(command, check=True)
        verify_xcframework(xcframework, version)
        smoke_macos(xcframework / next(
            entry["LibraryIdentifier"] for entry in plistlib.load(
                (xcframework / "Info.plist").open("rb")
            )["AvailableLibraries"] if entry["SupportedPlatform"] == "macos"
        ) / "libeuicc.framework", version)
        archive = PACKAGE / f"libeuicc-{config.lower()}.xcframework.zip"
        subprocess.run(
            ["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", str(xcframework), str(archive)],
            check=True,
        )
        subprocess.run(["unzip", "-tqq", str(archive)], check=True)
        with zipfile.ZipFile(archive) as zipped:
            names = set(zipped.namelist())
            root_name = xcframework.name + "/"
            assert root_name + "Info.plist" in names, archive
            assert any(
                name.startswith(root_name) and name.endswith("/libeuicc.framework/libeuicc")
                for name in names
            ), archive
        checksum = run("swift", "package", "compute-checksum", str(archive))
        assert checksum == hashlib.sha256(archive.read_bytes()).hexdigest(), archive
        checksums[archive.name] = checksum
        (PACKAGE / f"{archive.name}.sha256").write_text(checksum + "\n")
        shutil.rmtree(xcframework)
    manifest = {
        "version": version,
        "upstream_tag": os.environ["UPSTREAM_TAG"],
        "upstream_sha": os.environ["UPSTREAM_SHA"],
        "wrapper_sha": os.environ["WRAPPER_SHA"],
        "toolchain_sha": os.environ["TOOLCHAIN_SHA"],
        "xcode_version": run("xcodebuild", "-version"),
        "cmake_version": run("cmake", "--version").splitlines()[0],
        "slices": provenance,
        "swift_package_checksums": checksums,
    }
    manifest_path = PACKAGE / "libeuicc-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    files = sorted(PACKAGE.iterdir())
    (PACKAGE / "SHA256SUMS").write_text(
        "".join(
            f"{hashlib.sha256(file.read_bytes()).hexdigest()}  {file.name}\n"
            for file in files
            if file.is_file()
        )
    )


if __name__ == "__main__":
    main()
