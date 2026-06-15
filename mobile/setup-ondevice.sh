#!/usr/bin/env bash
# Fetch + trim the on-device LLM engine (llama.cpp via LLM.swift) into Vendor/.
#
# Why vendored: the upstream package pulls swift-syntax + swift-testing + docc over
# the network (just for an optional macro we don't use), and the full-history clone
# is 368 MB and flaky. We shallow-clone the pinned tag (no history) and strip the
# macro deps so the app builds fully offline against the prebuilt llama xcframework.
#
# The result (~600 MB, mostly the prebuilt binary) is gitignored — run this once on
# a fresh checkout before building the mobile app.
set -euo pipefail

TAG="v2.1.0"
DIR="$(cd "$(dirname "$0")" && pwd)/Vendor/LLM.swift"

if [ -d "$DIR" ]; then
  echo "✓ $DIR already present — nothing to do."
  exit 0
fi

mkdir -p "$(dirname "$DIR")"
echo "→ shallow-cloning LLM.swift@$TAG …"
git clone --depth 1 --branch "$TAG" https://github.com/eastriverlee/LLM.swift.git "$DIR"

echo "→ trimming macro / swift-syntax dependencies …"
# Drop the macro + test targets and their network deps; keep llama + LLM only.
python3 - "$DIR/Package.swift" <<'PY'
import sys
p = sys.argv[1]
open(p, "w").write('''// swift-tools-version: 5.9
import PackageDescription

// TRIMMED for Maria One (see mobile/setup-ondevice.sh): macro-free, offline.
let package = Package(
    name: "LLM",
    platforms: [.iOS(.v16), .macOS(.v13), .watchOS(.v9), .tvOS(.v16), .visionOS(.v1)],
    products: [.library(name: "LLM", targets: ["LLM"])],
    targets: [
        .binaryTarget(name: "llama", path: "llama.cpp/llama.xcframework"),
        .target(name: "LLM", dependencies: ["llama"], path: "Sources/LLM"),
    ]
)
''')
PY

# Remove the three @Generatable / LLMMacros references from the source.
python3 - "$DIR/Sources/LLM/LLM.swift" <<'PY'
import re, sys
p = sys.argv[1]
src = open(p).read()
src = src.replace("@_exported import LLMMacros",
                  "// LLMMacros (@Generatable) removed — macro-free build.")
# Remove StructuredOutput struct + StructuredOutputError enum.
src = re.sub(r"public struct StructuredOutput<T: Generatable> \{.*?\n\}\n\n/// Errors that can occur during structured output generation\.\npublic enum StructuredOutputError: Error \{.*?\n\}\n",
             "// StructuredOutput + StructuredOutputError removed (macro-free build).\n",
             src, flags=re.S)
# Remove respond<T: Generatable>(...) method.
src = re.sub(r"    public func respond<T: Generatable>\(.*?\n    \}\n(\s*)\}",
             "    // respond<T: Generatable> removed (macro-free build).\n\\1}",
             src, flags=re.S)
open(p, "w").write(src)
PY

echo "✓ on-device engine ready at $DIR"
