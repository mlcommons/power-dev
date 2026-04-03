#!/usr/bin/env python3
# Copyright 2026 The MLPerf Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# =============================================================================

# Software-based GPU power sampler for MLPerf power measurement.
#
# Provides per-GPU power readings from vendor APIs to complement
# external power meter (e.g. Yokogawa) wall-power measurements.
# This enables per-GPU power breakdown alongside total system AC power.
#
# Supported platforms:
#   NVIDIA  - pynvml (in-process) or nvidia-smi (subprocess fallback)
#   AMD     - amdsmi (ROCm 5.7+) or rocm-smi (subprocess fallback)
#   Intel   - hl-smi for Gaudi accelerators
#
# Usage with sample_metrics.py:
#   cd power_meter_sampling
#   python sample_metrics.py -I 1 -D 60 -l /tmp/gpu_power.csv samplers.gpu_software
#
# Optional configuration via gpu_software.json:
#   {
#     "platform": "auto",        # "auto", "nvidia", "amd", or "gaudi"
#     "gpu_indices": null         # null for all GPUs, or [0, 1] for specific ones
#   }

import inspect
import json
import os
import re
import subprocess
import sys


class Sampler():
    """Per-GPU software power sampler for the MLPerf power measurement framework.

    Conforms to the power_meter_sampling sampler interface:
      - close()       -- cleanup resources
      - get_titles()  -- return CSV column headers
      - get_values()  -- return current power readings
    """

    def __init__(self):
        self._platform = None
        self._handles = []
        self._cleanup_fn = None
        self._num_gpus = 0
        self._gpu_indices = None

        # Load optional configuration
        parm_file = os.path.splitext(inspect.getfile(Sampler))[0] + ".json"
        try:
            with open(parm_file) as f:
                config = json.load(f)
                platform_hint = config.get("platform", "auto")
                self._gpu_indices = config.get("gpu_indices", None)
        except (FileNotFoundError, json.JSONDecodeError):
            platform_hint = "auto"

        self._detect(platform_hint)

        if self._num_gpus == 0:
            sys.stdout.write("WARNING: gpu_software sampler: no GPU power API detected\n")

    def close(self):
        """Required: called before shutdown for general cleanup."""
        if self._cleanup_fn:
            try:
                self._cleanup_fn()
            except Exception:
                pass
        self._handles = []
        self._num_gpus = 0
        self._platform = None
        self._cleanup_fn = None

    def get_titles(self):
        """Required: returns tuple of titles for first row of CSV file."""
        return tuple("GPU%d_Power_W" % i for i in range(self._num_gpus))

    def get_values(self):
        """Required: returns tuple of values for rows in CSV file."""
        if self._platform == "pynvml":
            return self._read_pynvml()
        elif self._platform == "nvidia-smi":
            return self._read_nvidia_smi()
        elif self._platform == "amdsmi":
            return self._read_amdsmi()
        elif self._platform == "rocm-smi":
            return self._read_rocm_smi()
        elif self._platform == "hl-smi":
            return self._read_hlsmi()
        return tuple(0.0 for _ in range(self._num_gpus))

    # ------------------------------------------------------------------
    # Platform detection
    # ------------------------------------------------------------------

    def _detect(self, platform_hint):
        """Probe hardware and configure for multi-GPU reading."""
        if platform_hint in ("auto", "nvidia"):
            if self._try_pynvml():
                return
            if self._try_nvidia_smi():
                return
        if platform_hint in ("auto", "amd"):
            if self._try_amdsmi():
                return
            if self._try_rocm_smi():
                return
        if platform_hint in ("auto", "gaudi"):
            if self._try_hlsmi():
                return
        self._num_gpus = 0

    def _filter_indices(self, count):
        """Apply gpu_indices filter if configured."""
        if self._gpu_indices is not None:
            return [i for i in self._gpu_indices if i < count]
        return list(range(count))

    def _try_pynvml(self):
        try:
            import pynvml
            pynvml.nvmlInit()
            count = pynvml.nvmlDeviceGetCount()
            if count == 0:
                return False
            indices = self._filter_indices(count)
            handles = []
            for i in indices:
                h = pynvml.nvmlDeviceGetHandleByIndex(i)
                mw = pynvml.nvmlDeviceGetPowerUsage(h)
                if mw <= 0:
                    return False
                handles.append(h)
            self._handles = handles
            self._num_gpus = len(handles)
            self._platform = "pynvml"
            self._cleanup_fn = lambda: pynvml.nvmlShutdown()
            return True
        except Exception:
            return False

    def _try_nvidia_smi(self):
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=power.draw",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode != 0:
                return False
            lines = [l.strip() for l in result.stdout.strip().split("\n") if l.strip()]
            values = [float(l) for l in lines]
            if not values or any(v <= 0 for v in values):
                return False
            indices = self._filter_indices(len(values))
            self._num_gpus = len(indices)
            self._platform = "nvidia-smi"
            return True
        except Exception:
            return False

    def _try_amdsmi(self):
        try:
            import amdsmi
            amdsmi.amdsmi_init()
            handles = amdsmi.amdsmi_get_processor_handles()
            if not handles:
                return False
            indices = self._filter_indices(len(handles))
            filtered_handles = [handles[i] for i in indices]
            for h in filtered_handles:
                info = amdsmi.amdsmi_get_power_info(h)
                if float(info.get("average_socket_power", 0)) <= 0:
                    return False
            self._handles = filtered_handles
            self._num_gpus = len(filtered_handles)
            self._platform = "amdsmi"
            self._cleanup_fn = lambda: amdsmi.amdsmi_shut_down()
            return True
        except Exception:
            return False

    def _try_rocm_smi(self):
        try:
            result = subprocess.run(
                ["rocm-smi", "--showpower", "--json"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode != 0:
                return False
            data = json.loads(result.stdout)
            powers = self._parse_rocm_smi_multi(data)
            if not powers or any(p <= 0 for p in powers):
                return False
            indices = self._filter_indices(len(powers))
            self._num_gpus = len(indices)
            self._platform = "rocm-smi"
            return True
        except Exception:
            return False

    def _try_hlsmi(self):
        try:
            result = subprocess.run(
                ["hl-smi", "-q", "-d", "POWER"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode != 0:
                return False
            powers = re.findall(r"Power Draw\s*:\s*([\d.]+)\s*W", result.stdout)
            if not powers:
                return False
            values = [float(p) for p in powers]
            if any(v <= 0 for v in values):
                return False
            indices = self._filter_indices(len(values))
            self._num_gpus = len(indices)
            self._platform = "hl-smi"
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Readers
    # ------------------------------------------------------------------

    def _read_pynvml(self):
        import pynvml
        values = []
        for h in self._handles:
            try:
                values.append(pynvml.nvmlDeviceGetPowerUsage(h) / 1000.0)
            except Exception:
                values.append(0.0)
        return tuple(values)

    def _read_nvidia_smi(self):
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=power.draw",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5,
            )
            lines = [l.strip() for l in result.stdout.strip().split("\n") if l.strip()]
            all_values = [float(l) for l in lines]
            indices = self._filter_indices(len(all_values))
            return tuple(all_values[i] for i in indices[:self._num_gpus])
        except Exception:
            return tuple(0.0 for _ in range(self._num_gpus))

    def _read_amdsmi(self):
        import amdsmi
        values = []
        for h in self._handles:
            try:
                info = amdsmi.amdsmi_get_power_info(h)
                values.append(float(info.get("average_socket_power", 0)))
            except Exception:
                values.append(0.0)
        return tuple(values)

    def _read_rocm_smi(self):
        try:
            result = subprocess.run(
                ["rocm-smi", "--showpower", "--json"],
                capture_output=True, text=True, timeout=5,
            )
            data = json.loads(result.stdout)
            all_powers = self._parse_rocm_smi_multi(data)
            indices = self._filter_indices(len(all_powers))
            return tuple(all_powers[i] for i in indices[:self._num_gpus])
        except Exception:
            return tuple(0.0 for _ in range(self._num_gpus))

    def _read_hlsmi(self):
        try:
            result = subprocess.run(
                ["hl-smi", "-q", "-d", "POWER"],
                capture_output=True, text=True, timeout=10,
            )
            matches = re.findall(r"Power Draw\s*:\s*([\d.]+)\s*W", result.stdout)
            all_values = [float(m) for m in matches]
            indices = self._filter_indices(len(all_values))
            values = [all_values[i] for i in indices[:self._num_gpus]]
            while len(values) < self._num_gpus:
                values.append(0.0)
            return tuple(values)
        except Exception:
            return tuple(0.0 for _ in range(self._num_gpus))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_rocm_smi_multi(data):
        """Extract per-GPU power from rocm-smi JSON (multi-GPU)."""
        powers = []
        for key in sorted(data.keys()):
            val = data[key]
            if not isinstance(val, dict):
                continue
            power = 0.0
            for subkey, subval in val.items():
                if "power" in subkey.lower() and "w" in subkey.lower():
                    try:
                        power = float(str(subval).replace("W", "").strip())
                        break
                    except (ValueError, TypeError):
                        pass
                if isinstance(subval, str):
                    m = re.search(r"(\d+\.?\d*)\s*W", subval)
                    if m:
                        power = float(m.group(1))
                        break
            if power > 0:
                powers.append(power)
        return powers


if __name__ == '__main__':
    import pprint as pp
    sampler = Sampler()
    sys.stdout.write("Platform: %s\n" % sampler._platform)
    sys.stdout.write("GPUs: %d\n" % sampler._num_gpus)
    sys.stdout.write("Titles:\n")
    pp.pprint(sampler.get_titles())
    sys.stdout.write("Values:\n")
    pp.pprint(sampler.get_values())
    sampler.close()
