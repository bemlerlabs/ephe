import AppKit
import CoreImage
import Foundation
import Vision

// Foreground cutout for the onboarding actor. The Vision mask misses the thin
// forehead flame, which is why generate_bee_layers.py adds that layer by luminance.
let args = CommandLine.arguments
guard args.count >= 3 else {
    FileHandle.standardError.write("usage: vision_cutout <in.jpg> <out.png>\n".data(using: .utf8)!)
    exit(2)
}
let input = URL(fileURLWithPath: args[1])
let output = URL(fileURLWithPath: args[2])
guard let image = NSImage(contentsOf: input),
      let cg = image.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
    FileHandle.standardError.write("cannot read \(input.path)\n".data(using: .utf8)!)
    exit(1)
}
let request = VNGenerateForegroundInstanceMaskRequest()
let handler = VNImageRequestHandler(cgImage: cg, options: [:])
do {
    try handler.perform([request])
    guard let result = request.results?.first, !result.allInstances.isEmpty else {
        FileHandle.standardError.write("no foreground instance found\n".data(using: .utf8)!)
        exit(3)
    }
    let buffer = try result.generateScaledMaskForImage(forInstances: result.allInstances, from: handler)
    let context = CIContext()
    let extent = CGRect(x: 0, y: 0, width: cg.width, height: cg.height)
    let original = CIImage(cgImage: cg)
    var mask = CIImage(cvPixelBuffer: buffer)
    if mask.extent.width != extent.width || mask.extent.height != extent.height {
        mask = mask.transformed(by: CGAffineTransform(scaleX: extent.width / mask.extent.width,
                                                     y: extent.height / mask.extent.height))
    }
    let soft = mask
        .applyingFilter("CIGaussianBlur", parameters: [kCIInputRadiusKey: 1.6])
        .cropped(to: extent)
    let clear = CIImage(color: CIColor.clear).cropped(to: extent)
    let cut = original.applyingFilter("CIBlendWithMask", parameters: [
        kCIInputBackgroundImageKey: clear,
        kCIInputMaskImageKey: soft,
    ])
    guard let rendered = context.createCGImage(cut, from: extent) else {
        FileHandle.standardError.write("cannot render the cutout\n".data(using: .utf8)!)
        exit(4)
    }
    let rep = NSBitmapImageRep(cgImage: rendered)
    guard let data = rep.representation(using: .png, properties: [:]) else {
        FileHandle.standardError.write("cannot encode the cutout\n".data(using: .utf8)!)
        exit(5)
    }
    try data.write(to: output)
    print("wrote \(output.path) \(cg.width)x\(cg.height)")
} catch {
    FileHandle.standardError.write("vision failed: \(error)\n".data(using: .utf8)!)
    exit(6)
}
