#!/usr/bin/env swift
import Foundation
import Vision
import AppKit

func recognizeText(from imagePath: String) throws -> String {
    let url = URL(fileURLWithPath: imagePath)
    guard let image = NSImage(contentsOf: url) else {
        throw NSError(domain: "ocr_image", code: 1, userInfo: [NSLocalizedDescriptionKey: "Cannot open image: \(imagePath)"])
    }

    var rect = NSRect(origin: .zero, size: image.size)
    guard let cgImage = image.cgImage(forProposedRect: &rect, context: nil, hints: nil) else {
        throw NSError(domain: "ocr_image", code: 2, userInfo: [NSLocalizedDescriptionKey: "Cannot decode CGImage: \(imagePath)"])
    }

    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.usesLanguageCorrection = true
    request.recognitionLanguages = ["zh-Hant", "zh-Hans", "en-US"]

    let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])
    try handler.perform([request])

    let observations = request.results ?? []
    let lines = observations.compactMap { $0.topCandidates(1).first?.string }
    return lines.joined(separator: "\n")
}

let args = CommandLine.arguments.dropFirst()
if args.isEmpty {
    fputs("usage: ocr_image.swift <image-path> [<image-path> ...]\n", stderr)
    exit(2)
}

var out: [[String: String]] = []
for p in args {
    do {
        let text = try recognizeText(from: p)
        out.append(["path": p, "text": text])
    } catch {
        out.append(["path": p, "text": "", "error": error.localizedDescription])
    }
}

let data = try JSONSerialization.data(withJSONObject: out, options: [.prettyPrinted])
FileHandle.standardOutput.write(data)
