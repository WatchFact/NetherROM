#!/usr/bin/env python3
"""Adapt the archived r9s model selector without sed expressions or empty keys."""
import json
import re
import sys
from pathlib import Path


def adapt(config, properties):
    values = re.findall(r"^ro\.product\.device=(.+)$", properties.read_text(), re.M)
    if len(values) != 1 or not re.fullmatch(r"[A-Za-z0-9_]+", values[0]):
        raise ValueError("Missing or ambiguous source firmware device")
    device = values[0]
    data = json.loads(config.read_text())
    if data.get("device_property") not in ("ro.product.device", "ro.soc.model"):
        raise ValueError("Unsupported MIDAS device_property")
    selectors = data.get("midasSR_devices")
    if not isinstance(selectors, list) or not all(isinstance(v, str) for v in selectors):
        raise ValueError("Invalid MIDAS model selectors")
    # Preserve the legacy r9s capabilities. A modern source may already appear
    # in unrelated model lists; retaining those would enable unsupported modes.
    if selectors.count("r9s") != 1 and data.get("device_property") != "ro.product.device":
        raise ValueError("Archived MIDAS r9s selector is missing or ambiguous")
    if "r9s" in selectors and device != "r9s":
        for key, values in data.items():
            if key.endswith("_devices") and isinstance(values, list):
                data[key] = [device if v == "r9s" else v for v in values if v != device]
    elif device not in selectors:
        raise ValueError("No legacy MIDAS mapping for source device")
    data["device_property"] = "ro.product.device"
    config.write_text(json.dumps(data, indent=2) + "\n")
    return device


if __name__ == "__main__":
    print("MIDAS source model:", adapt(Path(sys.argv[1]), Path(sys.argv[2])))
