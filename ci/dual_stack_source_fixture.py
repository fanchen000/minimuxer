#!/usr/bin/env python3
"""Compile the actual minimuxer tunnel-selection method in a standalone Swift fixture.

The macOS SwiftPM test target cannot link without the pinned idevice FFI library.
This fixture checks the production source's selection body without fabricating
that link dependency. It does NOT verify CoreDevice handshakes or full packaging.
"""
from pathlib import Path
import argparse

SOURCE = Path(__file__).resolve().parents[1] / "Sources/Services/DeviceConnectionManager.swift"
START = "    static func resolveCandidateTunnels(from interfaces: Set<NetInfo>) -> [TunnelNetInfo] {"
END = "    static func resolveCandidatePeers(from interfaces: Set<NetInfo>) -> [CandidatePeer] {"


def source_method():
    source = SOURCE.read_text(encoding="utf-8")
    if source.count(START) != 1 or source.count(END) != 1:
        raise RuntimeError("source method anchors changed; cannot run the approved native fixture")
    start = source.index(START)
    end = source.index(END, start)
    method = source[start:end].strip()
    required = (
        "interfaces",
        ".compactMap { $0 as? TunnelNetInfo }",
        "$0.tunnelType == .utun",
        "!$0.interfaceAddresses.v4.isEmpty",
        ".sorted { $0.name < $1.name }",
    )
    if any(token not in method for token in required):
        raise RuntimeError("expected production filter is absent")
    if "$0.interfaceAddresses.v6.isEmpty" in method:
        raise RuntimeError("production filter still rejects IPv4+IPv6")
    return method


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    method = source_method()
    fixture = """
import Foundation

struct IPAddresses {
    let v4: [String]
    let v6: [String]
}
enum TunnelType { case utun, ipsec }
class NetInfo: Hashable {
    let name: String
    let interfaceAddresses: IPAddresses
    init(name: String, v4: [String], v6: [String]) {
        self.name = name
        interfaceAddresses = IPAddresses(v4: v4, v6: v6)
    }
    static func == (lhs: NetInfo, rhs: NetInfo) -> Bool { lhs === rhs }
    func hash(into hasher: inout Hasher) { hasher.combine(ObjectIdentifier(self)) }
}
final class TunnelNetInfo: NetInfo {
    let tunnelType: TunnelType
    init(name: String, type: TunnelType, v4: [String], v6: [String]) {
        tunnelType = type
        super.init(name: name, v4: v4, v6: v6)
    }
}
enum ProductionFilter {
""" + method + """
}
let dualStack = TunnelNetInfo(name: "utun01", type: .utun, v4: ["10.7.1.1"], v6: ["fd00::1"])
let v4Only = TunnelNetInfo(name: "utun02", type: .utun, v4: ["10.7.1.2"], v6: [])
let v6Only = TunnelNetInfo(name: "utun03", type: .utun, v4: [], v6: ["fd00::3"])
let wrongType = TunnelNetInfo(name: "ipsec04", type: .ipsec, v4: ["10.7.1.4"], v6: [])
let all: Set<NetInfo> = [dualStack, v4Only, v6Only, wrongType]
let accepted = ProductionFilter.resolveCandidateTunnels(from: all).map(\\.name)
precondition(accepted == ["utun01", "utun02"], "Wrong tunnel eligibility/order: \\(accepted)")
print("PASS source-derived native Swift test: dual-stack and IPv4-only utun selected; IPv6-only/ipsec excluded")
"""
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(fixture, encoding="utf-8")
    print("Extracted production selection method and generated runnable Swift fixture")


if __name__ == "__main__":
    main()
