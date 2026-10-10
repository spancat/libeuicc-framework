#!/usr/bin/env bash
set -euo pipefail

: "${PLATFORM:?}"
: "${ARCHITECTURES:?}"
: "${UPSTREAM_SHA:?}"
: "${UPSTREAM_TAG:?}"
: "${UPSTREAM_VERSION:?}"

if [[ "$DISPATCHED" == true ]]; then
  git -C lpac fetch --no-tags --depth=1 origin "refs/tags/$UPSTREAM_TAG"
  [[ "$(git -C lpac rev-parse 'FETCH_HEAD^{commit}')" == "$UPSTREAM_SHA" ]] || exit 1
  git -C lpac checkout --detach "$UPSTREAM_SHA"
fi
[[ "$(git -C lpac rev-parse HEAD)" == "$UPSTREAM_SHA" ]] || {
  echo "lpac checkout does not match resolved commit" >&2
  exit 1
}

xcode-select -p
xcodebuild -version
cmake --version

build_dir="build/ci-$PLATFORM"
stage_dir="build/ci-stage/$PLATFORM"
cmake_args=(
  -S . -B "$build_dir" -G Xcode
  -DCMAKE_TOOLCHAIN_FILE=./cmake/ios/ios.toolchain.cmake
  "-DPLATFORM=$PLATFORM"
  "-DARCHS=$ARCHITECTURES"
  -DENABLE_VISIBILITY=ON
  -DCMAKE_XCODE_ATTRIBUTE_CODE_SIGNING_ALLOWED=NO
  -DCMAKE_XCODE_ATTRIBUTE_DEBUG_INFORMATION_FORMAT=dwarf-with-dsym
)
if [[ "$DISPATCHED" == true ]]; then
  cmake_args+=("-DLIBEUICC_VERSION_OVERRIDE=$UPSTREAM_VERSION")
fi
cmake "${cmake_args[@]}"
for config in Debug Release; do
  cmake --build "$build_dir" --config "$config" --target libeuicc --parallel 3 -- \
    GCC_GENERATE_DEBUGGING_SYMBOLS=YES \
    DEBUG_INFORMATION_FORMAT=dwarf-with-dsym \
    CODE_SIGNING_ALLOWED=NO
  framework="$build_dir/Frameworks/$config/libeuicc.framework"
  [[ -d "$framework" ]] || {
    echo "Missing $framework" >&2
    exit 1
  }

done

mkdir -p "$stage_dir"
archive_entries=(Debug/libeuicc.framework Release/libeuicc.framework)
for config in Debug Release; do
  symbols="$build_dir/Frameworks/$config/libeuicc.framework.dSYM"
  [[ -d "$symbols" ]] || {
    echo "Missing $symbols" >&2
    exit 1
  }
  archive_entries+=("$config/libeuicc.framework.dSYM")
done
tar -czf "$stage_dir/framework-$PLATFORM.tar.gz" -C "$build_dir/Frameworks" \
  "${archive_entries[@]}"
