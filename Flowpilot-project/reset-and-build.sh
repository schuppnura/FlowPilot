#!/bin/bash
# Completely reset and rebuild FlowPilot-demo

set -e

echo "1. Killing any running instances..."
killall FlowPilot-demo 2>/dev/null || true
sleep 1

echo "2. Clearing all derived data..."
rm -rf ~/Library/Developer/Xcode/DerivedData/flowpilot-project-*

echo "3. Resetting Launch Services cache..."
/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -kill -r -domain local -domain system -domain user > /dev/null 2>&1

echo "4. Cleaning build..."
xcodebuild -project flowpilot-project.xcodeproj -scheme FlowPilot-demo -configuration Debug clean > /dev/null 2>&1

echo "5. Building..."
xcodebuild -project flowpilot-project.xcodeproj -scheme FlowPilot-demo -configuration Debug

echo "6. Finding and registering the new build..."
BUILD_APP=$(find ~/Library/Developer/Xcode/DerivedData/flowpilot-project-*/Build/Products/Debug -name "FlowPilot-demo.app" -type d 2>/dev/null | head -1)

if [ -z "$BUILD_APP" ]; then
    echo "Error: Build not found!"
    exit 1
fi

echo "7. Registering with Launch Services..."
/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister "$BUILD_APP" > /dev/null 2>&1

echo "8. Opening: $BUILD_APP"
open "$BUILD_APP"

echo ""
echo "✓ Done! The app should now be the latest version."
