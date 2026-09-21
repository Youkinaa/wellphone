#!/usr/bin/env bash
set -euo pipefail

probe_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
probe_sdk_root=${WELLPHONE_PROBE_SDK_ROOT:-}
probe_jdk_home=${WELLPHONE_PROBE_JDK_HOME:-}
probe_platform=${WELLPHONE_PROBE_PLATFORM:-36}
probe_build_tools=${WELLPHONE_PROBE_BUILD_TOOLS:-36.0.0}
while (($#)); do
    case "$1" in
        --sdk-root) probe_sdk_root=${2:?missing SDK root}; shift 2 ;;
        --jdk-home) probe_jdk_home=${2:?missing JDK home}; shift 2 ;;
        --platform) probe_platform=${2:?missing platform number}; shift 2 ;;
        --build-tools) probe_build_tools=${2:?missing build-tools version}; shift 2 ;;
        *) printf 'Unknown argument: %s\n' "$1" >&2; exit 2 ;;
    esac
done
if [[ -z "$probe_sdk_root" || -z "$probe_jdk_home" ]]; then
    printf 'Usage: %s --sdk-root PATH --jdk-home PATH [--platform 36] [--build-tools 36.0.0]\nEnvironment: WELLPHONE_PROBE_SDK_ROOT, WELLPHONE_PROBE_JDK_HOME, WELLPHONE_PROBE_PLATFORM, WELLPHONE_PROBE_BUILD_TOOLS\n' "$0" >&2
    exit 2
fi
probe_tools="$probe_sdk_root/build-tools/$probe_build_tools"
probe_android_jar="$probe_sdk_root/platforms/android-$probe_platform/android.jar"
for probe_file in "$probe_android_jar" "$probe_tools/aapt2" "$probe_tools/zipalign" \
    "$probe_tools/lib/d8.jar" "$probe_tools/lib/apksigner.jar" \
    "$probe_jdk_home/bin/java" "$probe_jdk_home/bin/javac" "$probe_jdk_home/bin/jar" \
    "$probe_jdk_home/bin/keytool"; do
    [[ -f "$probe_file" ]] || { printf 'Missing tool/input: %s\n' "$probe_file" >&2; exit 2; }
done
command -v python3 >/dev/null
mkdir -p "$probe_root/out"
probe_work=$(mktemp -d "$probe_root/out/build.XXXXXX")
trap 'rm -rf -- "$probe_work"' EXIT

# Disposable signing identity for these experimental APKs only.
probe_keystore="$probe_root/out/fixture-signing.jks"
if [[ ! -f "$probe_keystore" ]]; then
    "$probe_jdk_home/bin/keytool" -genkeypair -keystore "$probe_keystore" \
        -alias synthetic-probe -storepass synthetic-probe -keypass synthetic-probe \
        -keyalg RSA -keysize 2048 -validity 30 -dname 'CN=Local Synthetic Probe' >/dev/null
fi

for probe_role in main agent ime; do
    probe_build="$probe_work/$probe_role"
    mkdir -p "$probe_build/classes" "$probe_build/dex"
    if [[ "$probe_role" == ime ]]; then
        probe_src="$probe_root/ime/src"
        probe_res="$probe_root/ime/res"
    else
        probe_src="$probe_root/common/src"
        probe_res="$probe_root/common/res"
    fi
    "$probe_tools/aapt2" compile --dir "$probe_res" -o "$probe_build/resources.zip"
    "$probe_tools/aapt2" link -I "$probe_android_jar" \
        --manifest "$probe_root/$probe_role/AndroidManifest.xml" \
        --min-sdk-version 26 --target-sdk-version 34 \
        -o "$probe_build/unsigned.apk" "$probe_build/resources.zip"
    mapfile -d '' probe_sources < <(find "$probe_src" -type f -name '*.java' -print0)
    "$probe_jdk_home/bin/javac" --release 8 -encoding UTF-8 \
        -classpath "$probe_android_jar" -d "$probe_build/classes" "${probe_sources[@]}"
    "$probe_jdk_home/bin/jar" --create --file "$probe_build/classes.jar" -C "$probe_build/classes" .
    "$probe_jdk_home/bin/java" -cp "$probe_tools/lib/d8.jar" com.android.tools.r8.D8 \
        --lib "$probe_android_jar" --min-api 26 --output "$probe_build/dex" "$probe_build/classes.jar"
    python3 - "$probe_build/unsigned.apk" "$probe_build/dex" <<'PY'
from pathlib import Path
import sys
import zipfile
with zipfile.ZipFile(sys.argv[1], 'a', compression=zipfile.ZIP_DEFLATED) as apk:
    for dex in sorted(Path(sys.argv[2]).glob('*.dex')):
        apk.write(dex, dex.name)
PY
    "$probe_tools/zipalign" -p -f 4 "$probe_build/unsigned.apk" "$probe_build/aligned.apk"
    probe_apk="$probe_root/out/probe-$probe_role.apk"
    "$probe_jdk_home/bin/java" -jar "$probe_tools/lib/apksigner.jar" sign \
        --ks "$probe_keystore" --ks-key-alias synthetic-probe \
        --ks-pass pass:synthetic-probe --key-pass pass:synthetic-probe \
        --out "$probe_apk" "$probe_build/aligned.apk"
    "$probe_jdk_home/bin/java" -jar "$probe_tools/lib/apksigner.jar" verify --verbose "$probe_apk"
    "$probe_tools/zipalign" -c -p 4 "$probe_apk"
    "$probe_tools/aapt2" dump badging "$probe_apk" > "$probe_root/out/probe-$probe_role.badging.txt"
    printf 'Built: %s\n' "$probe_apk"
done
python3 - "$probe_root/out" "$probe_sdk_root" "$probe_jdk_home" "$probe_platform" "$probe_build_tools" <<'PY'
from pathlib import Path
import hashlib
import json
import sys
out = Path(sys.argv[1])
result = {'sdk_root': sys.argv[2], 'jdk_home': sys.argv[3],
          'compile_platform': sys.argv[4], 'build_tools': sys.argv[5],
          'target_sdk': 34, 'min_sdk': 26,
          'apks': {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in sorted(out.glob('probe-*.apk'))}}
(out / 'build.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2))
PY
