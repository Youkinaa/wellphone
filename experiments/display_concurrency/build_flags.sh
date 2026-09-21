#!/usr/bin/env bash
# Build only. The experiment operator separately pushes this dex jar to the AVD.
set -euo pipefail

probe_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
probe_sdk_root=${WELLPHONE_PROBE_SDK_ROOT:?Set WELLPHONE_PROBE_SDK_ROOT to the Android SDK path}
probe_jdk_home=${WELLPHONE_PROBE_JDK_HOME:?Set WELLPHONE_PROBE_JDK_HOME to the JDK path}
probe_platform=${WELLPHONE_PROBE_PLATFORM:-36}
probe_build_tools=${WELLPHONE_PROBE_BUILD_TOOLS:-36.0.0}
probe_android_jar="$probe_sdk_root/platforms/android-$probe_platform/android.jar"
probe_d8_jar="$probe_sdk_root/build-tools/$probe_build_tools/lib/d8.jar"
for probe_file in "$probe_android_jar" "$probe_d8_jar" \
    "$probe_jdk_home/bin/java" "$probe_jdk_home/bin/javac" "$probe_jdk_home/bin/jar" \
    "$probe_root/DisplayFlags.java"; do
    [[ -f "$probe_file" ]] || { printf 'Missing tool/input: %s\n' "$probe_file" >&2; exit 2; }
done

mkdir -p "$probe_root/out"
probe_work=$(mktemp -d "$probe_root/out/flags-build.XXXXXX")
trap 'rm -rf -- "$probe_work"' EXIT
mkdir -p "$probe_work/classes" "$probe_work/dex"
"$probe_jdk_home/bin/javac" --release 8 -encoding UTF-8 \
    -d "$probe_work/classes" "$probe_root/DisplayFlags.java"
"$probe_jdk_home/bin/jar" --create --file "$probe_work/classes.jar" -C "$probe_work/classes" .
"$probe_jdk_home/bin/java" -cp "$probe_d8_jar" com.android.tools.r8.D8 \
    --lib "$probe_android_jar" --min-api 26 --output "$probe_work/dex" "$probe_work/classes.jar"
"$probe_jdk_home/bin/jar" --create --file "$probe_root/out/display-flags.jar" \
    -C "$probe_work/dex" classes.dex
printf 'Built: %s\n' "$probe_root/out/display-flags.jar"
