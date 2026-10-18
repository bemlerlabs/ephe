// swift-tools-version: 5.9
// The root package exists for CodeQL's Swift autobuilder, which only scans a
// repository that carries a package (or an Xcode project) at its root.
import PackageDescription

let package = Package(
    name: "ephe-tools",
    platforms: [.macOS(.v14)],
    targets: [
        .executableTarget(
            name: "vision_cutout",
            path: "scripts/vision-cutout/Sources/vision_cutout"
        )
    ]
)
