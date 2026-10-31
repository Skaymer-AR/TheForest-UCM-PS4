#!/usr/bin/env python3
"""Read-only, bounded inspection of serialized PlayMaker FSM data in this title.

This supports verified Unity 5.6.6f2 / PlayMaker ActionData encodings present
in this title, including multi-action states and selected specialized
parameter arrays. It does not edit assets, construct IL2CPP objects, register
an FSM, or claim that an asset graph can be activated by a PRX. Reports contain
derived names, values, offsets, and hashes only; private round-trip byte buffers
are removed before JSON output.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from analyze_ps4_il2cpp_pipeline import (  # noqa: E402
    FIELD_RECORD,
    TYPE_RECORD,
    parse_metadata_v23,
)
from inspect_aot_registration import NativeImage  # noqa: E402
from inspect_unity_rewired_assets import Asset, monoscript  # noqa: E402
from verify_playmaker_gui_aot import inspect as inspect_gui_aot  # noqa: E402
from validate_playmaker_owner_graph import inspect as inspect_fsm_lifecycle  # noqa: E402

LEVEL2_SHA256 = "99fce056f65647f62ba52d9957317b4ed876e600f854f12e65a20897d37c396d"
GLOBALGAMEMANAGERS_SHA256 = "2518dad0f38f6357276d1e33b4653a907df82dc8b0eb56450b49cb3eb86af2a8"
SHAREDASSETS2_SHA256 = "806d65aa19fd86cbd20ac8cb3f7e5a11cd6a4bd9c9438f0e243b38580303c105"
MODULE_SHA256 = "0159ff61c99d25c8f0a821070e3d8b24aff58dbbe5429b8f29561f9960d02969"
METADATA_SHA256 = "238c400de31e28ed4f7f14e7781ea3b33de0d0bd6964ded680d78fce1d85a6c3"
METADATA_REGISTRATION = 0x032C4C98

MAX_COMPONENT_BYTES = 1 << 20
MAX_STRING_BYTES = 4096
MAX_STATES = 128
MAX_TRANSITIONS = 256
MAX_EVENTS = 256
MAX_ACTIONS = 64
MAX_PARAMETERS = 4096
MAX_ACTION_DATA_BYTES = 1 << 18
MAX_NATIVE_TYPE_NESTING = 16

ACTIONDATA_SPECIAL_ARRAYS = (
    "unityObjectParams", "fsmGameObjectParams", "fsmOwnerDefaultParams",
    "animationCurveParams", "functionCallParams", "fsmTemplateControlParams",
    "fsmEventTargetParams", "fsmPropertyParams", "layoutOptionParams",
    "fsmStringParams", "fsmObjectParams", "fsmVarParams",
)

PARAM_DATA_TYPES = {
    1: "System.Boolean",
    17: "HutongGames.PlayMaker.FsmBool",
    18: "HutongGames.PlayMaker.FsmString",
    19: "HutongGames.PlayMaker.FsmGameObject",
    20: "HutongGames.PlayMaker.FsmOwnerDefault",
    15: "HutongGames.PlayMaker.FsmFloat",
    16: "HutongGames.PlayMaker.FsmInt",
    23: "HutongGames.PlayMaker.FsmEvent",
    24: "HutongGames.PlayMaker.FsmObject",
    25: "HutongGames.PlayMaker.FsmColor",
    28: "HutongGames.PlayMaker.FsmVector3",
    30: "HutongGames.PlayMaker.FsmRect",
    32: "HutongGames.PlayMaker.FsmMaterial",
    31: "HutongGames.PlayMaker.FsmEventTarget",
    33: "HutongGames.PlayMaker.FsmTexture",
    35: "HutongGames.PlayMaker.FsmQuaternion",
    37: "HutongGames.PlayMaker.FsmVector2",
}

IL2CPP_PRIMITIVES = {
    0x01: "System.Void", 0x02: "System.Boolean", 0x03: "System.Char",
    0x04: "System.SByte", 0x05: "System.Byte", 0x06: "System.Int16",
    0x07: "System.UInt16", 0x08: "System.Int32", 0x09: "System.UInt32",
    0x0A: "System.Int64", 0x0B: "System.UInt64", 0x0C: "System.Single",
    0x0D: "System.Double", 0x0E: "System.String", 0x1C: "System.Object",
}


class Reader:
    def __init__(self, data: bytes, pos: int = 0):
        if len(data) > MAX_COMPONENT_BYTES:
            raise ValueError("PlayMaker component exceeds the byte limit")
        self.data = data
        self.pos = pos

    def take(self, size: int) -> bytes:
        if size < 0 or size > MAX_COMPONENT_BYTES or self.pos + size > len(self.data):
            raise ValueError("truncated or oversized PlayMaker data")
        result = self.data[self.pos:self.pos + size]
        self.pos += size
        return result

    def i32(self) -> int:
        return struct.unpack("<i", self.take(4))[0]

    def u32(self) -> int:
        return struct.unpack("<I", self.take(4))[0]

    def f32(self) -> float:
        value = struct.unpack("<f", self.take(4))[0]
        if not math.isfinite(value):
            raise ValueError("non-finite serialized float")
        return value

    def aligned_string(self) -> tuple[str, int]:
        start = self.pos
        length = self.i32()
        if length < 0 or length > MAX_STRING_BYTES:
            raise ValueError("PlayMaker string length outside bounds")
        raw = self.take(length)
        try:
            value = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("invalid UTF-8 in PlayMaker string") from exc
        self.pos = (self.pos + 3) & ~3
        if self.pos > len(self.data):
            raise ValueError("truncated PlayMaker string padding")
        return value, start

    def count(self, label: str, maximum: int) -> int:
        value = self.i32()
        if value < 0 or value > maximum:
            raise ValueError(f"{label} count outside bounds")
        return value

    def bool32(self, label: str) -> bool:
        value = self.i32()
        if value not in (0, 1):
            raise ValueError(f"invalid serialized boolean: {label}")
        return bool(value)

    def bool_array(self, label: str, maximum: int = MAX_ACTIONS) -> list[bool]:
        count = self.count(label, maximum)
        raw = self.take(count)
        if any(value not in (0, 1) for value in raw):
            raise ValueError(f"invalid packed serialized boolean array: {label}")
        padding = (-count) % 4
        if any(self.take(padding)):
            raise ValueError(f"nonzero serialized boolean array padding: {label}")
        return [bool(value) for value in raw]


class TypeResolver:
    """Resolve v23 field type indices through the title's native type table."""

    def __init__(self, module: bytes, metadata_data: bytes):
        if hashlib.sha256(module).hexdigest() != MODULE_SHA256:
            raise ValueError("wrong IL2CPP module hash")
        self.metadata = parse_metadata_v23(metadata_data)
        self.metadata_data = metadata_data
        if self.metadata.sha256 != METADATA_SHA256:
            raise ValueError("wrong global metadata hash")
        self.image = NativeImage(module)
        type_count, self.type_table = struct.unpack(
            "<QQ", self.image.read(METADATA_REGISTRATION + 16 * 3, 16))
        if type_count < 1 or type_count > 200_000:
            raise ValueError("native type table count outside bounds")
        self.type_count = type_count
        self.type_defs = {item.full_name: item for item in self.metadata.types}
        self.type_defs_by_index = {item.index: item for item in self.metadata.types}
        self.type_def_offset = self.metadata.sections["type_definitions"][0]
        self.field_offset = self.metadata.sections["fields"][0]

    def resolve(self, type_index: int) -> str:
        if not 0 <= type_index < self.type_count:
            raise ValueError("field type index outside native type table")
        pointer = struct.unpack("<Q", self.image.read(self.type_table + type_index * 8, 8))[0]
        return self._resolve_type_pointer(pointer, depth=0)

    def _resolve_type_pointer(self, pointer: int, *, depth: int) -> str:
        if depth > MAX_NATIVE_TYPE_NESTING:
            raise ValueError("nested IL2CPP type exceeds the recursion limit")
        if type(pointer) is not int or pointer <= 0:
            raise ValueError("invalid IL2CPP type pointer")
        data = struct.unpack("<Q", self.image.read(pointer, 8))[0]
        flags = struct.unpack("<I", self.image.read(pointer + 8, 4))[0]
        kind = (flags >> 16) & 0xFF
        if kind in (0x11, 0x12):
            definition = self.type_defs_by_index.get(data)
            if definition is None:
                raise ValueError("class field type does not resolve to a metadata type")
            return definition.full_name
        if kind in IL2CPP_PRIMITIVES:
            return IL2CPP_PRIMITIVES[kind]
        if kind == 0x1D:  # IL2CPP_TYPE_SZARRAY; data points to its element Il2CppType.
            if data <= 0:
                raise ValueError("SZARRAY element type pointer is invalid")
            element = self._resolve_type_pointer(data, depth=depth + 1)
            return element + "[]"
        raise ValueError(f"unsupported IL2CPP field type kind 0x{kind:02X}")

    def action_fields(self, full_name: str) -> list[dict[str, str]]:
        current = self.type_defs.get(full_name)
        if current is None:
            raise ValueError("action type missing from IL2CPP metadata: " + full_name)
        result: list[dict[str, str]] = []
        seen: set[str] = set()
        for _ in range(32):
            if current.full_name in ("HutongGames.PlayMaker.FsmStateAction", "System.Object"):
                return result
            for field in self.metadata.owned_fields(current):
                row = FIELD_RECORD.unpack_from(
                    self.metadata_data, self.field_offset + field.index * FIELD_RECORD.size)
                if field.name in seen:
                    continue
                result.append({"name": field.name, "type": self.resolve(row[1])})
                seen.add(field.name)
            raw = TYPE_RECORD.unpack_from(
                self.metadata_data,
                self.type_def_offset + current.index * TYPE_RECORD.size)
            parent_native_index = raw[6]
            if parent_native_index < 0:
                return result
            parent_name = self.resolve(parent_native_index)
            current = self.type_defs.get(parent_name)
            if current is None:
                raise ValueError("action base type missing from metadata: " + parent_name)
        raise ValueError("action inheritance exceeds the supported depth")

    def declared_fields(self, full_name: str,
                        names: set[str] | None = None) -> list[dict[str, str]]:
        """Return direct metadata fields for a title type, without inherited fields."""
        current = self.type_defs.get(full_name)
        if current is None:
            raise ValueError("type missing from IL2CPP metadata: " + full_name)
        result = []
        for field in self.metadata.owned_fields(current):
            if names is not None and field.name not in names:
                continue
            row = FIELD_RECORD.unpack_from(
                self.metadata_data, self.field_offset + field.index * FIELD_RECORD.size)
            result.append({"name": field.name, "type": self.resolve(row[1])})
        return result

    @property
    def metadata_data(self) -> bytes:
        return self._metadata_data

    @metadata_data.setter
    def metadata_data(self, value: bytes) -> None:
        self._metadata_data = value


def _read_int_array(reader: Reader, label: str, maximum: int = MAX_PARAMETERS) -> list[int]:
    count = reader.count(label, maximum)
    return [reader.i32() for _ in range(count)]


def _read_string_array(reader: Reader, label: str, maximum: int = MAX_PARAMETERS) -> list[str]:
    count = reader.count(label, maximum)
    return [reader.aligned_string()[0] for _ in range(count)]


def _read_pptr(reader: Reader, label: str) -> dict[str, int]:
    file_id = reader.i32()
    path_id = struct.unpack("<q", reader.take(8))[0]
    if file_id < 0 or path_id < 0:
        raise ValueError(f"negative serialized PPtr: {label}")
    return {"file_id": file_id, "path_id": path_id}


def _read_fsm_object(reader: Reader, label: str = "FsmObject") -> dict:
    """Read the common FsmObject payload used by object-backed parameters."""
    use_variable = reader.bool32(label + ".useVariable")
    name, _ = reader.aligned_string()
    tooltip, _ = reader.aligned_string()
    show_in_inspector = reader.bool32(label + ".showInInspector")
    network_sync = reader.bool32(label + ".networkSync")
    type_name, _ = reader.aligned_string()
    value_pointer = _read_pptr(reader, label + ".value")
    return {
        "use_variable": use_variable, "name": name, "tooltip": tooltip,
        "show_in_inspector": show_in_inspector, "network_sync": network_sync,
        "type_name": type_name, "value_pointer": value_pointer,
    }


def _read_fsm_game_object(reader: Reader) -> dict:
    """Read the wire order independently confirmed in level2 ActionData."""
    use_variable = reader.bool32("FsmGameObject.useVariable")
    name, _ = reader.aligned_string()
    tooltip, _ = reader.aligned_string()
    show_in_inspector = reader.bool32("FsmGameObject.showInInspector")
    network_sync = reader.bool32("FsmGameObject.networkSync")
    value_pointer = _read_pptr(reader, "FsmGameObject.value")
    return {
        "use_variable": use_variable, "name": name, "tooltip": tooltip,
        "show_in_inspector": show_in_inspector, "network_sync": network_sync,
        "value_pointer": value_pointer,
    }


def _read_fsm_owner_default(reader: Reader) -> dict:
    option = reader.i32()
    if option not in (0, 1):
        raise ValueError("unknown FsmOwnerDefault owner option")
    return {"owner_option": option, "game_object": _read_fsm_game_object(reader)}


def _read_fsm_bool_object(reader: Reader, label: str) -> dict:
    """Read the nested FsmBool field order observed in FsmEventTarget records."""
    use_variable = reader.bool32(label + ".useVariable")
    name, _ = reader.aligned_string()
    tooltip, _ = reader.aligned_string()
    show_in_inspector = reader.bool32(label + ".showInInspector")
    network_sync = reader.bool32(label + ".networkSync")
    value = reader.bool32(label + ".value")
    return {
        "use_variable": use_variable, "name": name, "tooltip": tooltip,
        "show_in_inspector": show_in_inspector, "network_sync": network_sync,
        "value": value,
    }


def _read_fsm_string(reader: Reader, label: str) -> dict:
    """Read the specialized-list FsmString wire order observed in title assets."""
    use_variable = reader.bool32(label + ".useVariable")
    name, _ = reader.aligned_string()
    tooltip, _ = reader.aligned_string()
    show_in_inspector = reader.bool32(label + ".showInInspector")
    network_sync = reader.bool32(label + ".networkSync")
    value, _ = reader.aligned_string()
    return {
        "use_variable": use_variable, "name": name, "tooltip": tooltip,
        "show_in_inspector": show_in_inspector, "network_sync": network_sync,
        "value": value,
    }


def _read_fsm_event_target(reader: Reader) -> dict:
    target = reader.i32()
    exclude_self = _read_fsm_bool_object(reader, "FsmEventTarget.excludeSelf")
    game_object = _read_fsm_owner_default(reader)
    fsm_name = _read_fsm_string(reader, "FsmEventTarget.fsmName")
    send_to_children = _read_fsm_bool_object(reader, "FsmEventTarget.sendToChildren")
    fsm_component = _read_pptr(reader, "FsmEventTarget.fsmComponent")
    return {
        "target_value": target, "exclude_self": exclude_self,
        "game_object": game_object, "fsm_name": fsm_name,
        "send_to_children": send_to_children, "fsm_component": fsm_component,
    }


def parse_action_data(reader: Reader, *, salvage_unknown_parameters: bool = False) -> dict:
    start = reader.pos
    action_count = reader.count("ActionData actionNames", MAX_ACTIONS)
    if action_count == 0:
        # The title's serialized zero-action states carry a fixed run of 27
        # zero words here. Keep it opaque: the nonempty ActionData path below
        # establishes named field boundaries, while this empty sentinel does not.
        empty_tail = [reader.i32() for _ in range(26)]
        if any(empty_tail):
            raise ValueError("unsupported nonempty payload in zero-action sentinel")
        return {
            "offset": start, "size": reader.pos - start, "action_names": [],
            "empty_sentinel_words": 27, "parameters": [],
        }

    action_names = [reader.aligned_string()[0] for _ in range(action_count)]
    custom_names = _read_string_array(reader, "ActionData customNames", MAX_ACTIONS)
    enabled = reader.bool_array("actionEnabled", MAX_ACTIONS)
    is_open = reader.bool_array("actionIsOpen", MAX_ACTIONS)
    start_indices = _read_int_array(reader, "actionStartIndex", MAX_ACTIONS)
    hash_codes = _read_int_array(reader, "actionHashCodes", MAX_ACTIONS)
    specialized: dict[str, list[dict]] = {}
    specialized_offsets: dict[str, list[dict[str, int]]] = {}
    for field_name in ACTIONDATA_SPECIAL_ARRAYS:
        count = reader.count("ActionData " + field_name, MAX_PARAMETERS)
        if field_name == "fsmGameObjectParams":
            values, offsets = [], []
            for _ in range(count):
                item_start = reader.pos
                values.append(_read_fsm_game_object(reader))
                offsets.append({"offset": item_start, "size": reader.pos - item_start})
            specialized[field_name], specialized_offsets[field_name] = values, offsets
        elif field_name == "fsmObjectParams":
            values, offsets = [], []
            for _ in range(count):
                item_start = reader.pos
                values.append(_read_fsm_object(reader))
                offsets.append({"offset": item_start, "size": reader.pos - item_start})
            specialized[field_name], specialized_offsets[field_name] = values, offsets
        elif field_name == "fsmOwnerDefaultParams":
            values, offsets = [], []
            for _ in range(count):
                item_start = reader.pos
                values.append(_read_fsm_owner_default(reader))
                offsets.append({"offset": item_start, "size": reader.pos - item_start})
            specialized[field_name], specialized_offsets[field_name] = values, offsets
        elif field_name == "fsmEventTargetParams":
            values, offsets = [], []
            for _ in range(count):
                item_start = reader.pos
                values.append(_read_fsm_event_target(reader))
                offsets.append({"offset": item_start, "size": reader.pos - item_start})
            specialized[field_name], specialized_offsets[field_name] = values, offsets
        elif field_name == "fsmStringParams":
            values, offsets = [], []
            for _ in range(count):
                item_start = reader.pos
                values.append(_read_fsm_string(reader, "ActionData.fsmStringParams"))
                offsets.append({"offset": item_start, "size": reader.pos - item_start})
            specialized[field_name], specialized_offsets[field_name] = values, offsets
        elif count:
            raise ValueError("unsupported nonempty ActionData array: " + field_name)
        else:
            specialized[field_name] = []
            specialized_offsets[field_name] = []

    byte_count = reader.count("ActionData byteData", MAX_ACTION_DATA_BYTES)
    byte_data_offset = reader.pos
    byte_data = reader.take(byte_count)
    raw_padding_size = (-byte_count) % 4
    raw_padding = reader.take(raw_padding_size)
    if any(raw_padding):
        raise ValueError("nonzero ActionData byteData alignment padding")

    array_param_sizes = _read_int_array(reader, "arrayParamSizes")
    array_param_types = _read_int_array(reader, "arrayParamTypes")
    custom_type_sizes = _read_int_array(reader, "customTypeSizes")
    custom_type_names = _read_string_array(reader, "customTypeNames")
    param_data_types = _read_int_array(reader, "paramDataType")
    param_names = _read_string_array(reader, "paramName")
    param_positions = _read_int_array(reader, "paramDataPos")
    param_sizes = _read_int_array(reader, "paramByteDataSize")

    if not (len(custom_names) == len(enabled) == len(is_open) ==
            len(start_indices) == len(hash_codes) == action_count):
        raise ValueError("ActionData per-action arrays have inconsistent lengths")
    param_count = len(param_names)
    if not (len(param_data_types) == len(param_positions) == len(param_sizes) == param_count):
        raise ValueError("ActionData parameter arrays have inconsistent lengths")
    if len(array_param_sizes) != len(array_param_types):
        raise ValueError("ActionData array parameter metadata lengths differ")
    if len(custom_type_sizes) != len(custom_type_names):
        raise ValueError("ActionData custom type metadata lengths differ")
    if any(size < 0 for size in array_param_sizes + custom_type_sizes):
        raise ValueError("negative ActionData array or custom type size")
    if any(index < 0 for index in start_indices) or (start_indices and start_indices[0] != 0):
        raise ValueError("ActionData actionStartIndex has an invalid first index")
    if any(left > right for left, right in zip(start_indices, start_indices[1:])):
        raise ValueError("ActionData actionStartIndex is not monotonic")
    if any(index > param_count for index in start_indices):
        raise ValueError("ActionData actionStartIndex outside parameter list")

    specialized_type_arrays = {
        18: "fsmStringParams", 19: "fsmGameObjectParams",
        20: "fsmOwnerDefaultParams", 24: "fsmObjectParams",
        31: "fsmEventTargetParams", 32: "fsmObjectParams",
        33: "fsmObjectParams",
    }
    spans = []
    unknown_parameter_types = []
    for code, position, size in zip(param_data_types, param_positions, param_sizes):
        type_name = PARAM_DATA_TYPES.get(code)
        if type_name is None:
            if not salvage_unknown_parameters:
                raise ValueError(f"unsupported ActionData serialized type code: {code}")
            unknown_parameter_types.append(code)
        array_name = specialized_type_arrays.get(code)
        if array_name is not None:
            if size != 0 or not 0 <= position < len(specialized[array_name]):
                raise ValueError("ActionData specialized parameter reference is invalid")
            continue
        if position < 0 or size < 0 or position + size > len(byte_data):
            raise ValueError("ActionData parameter slice is outside byteData")
        if size:
            spans.append((position, position + size))
    spans.sort()
    if any(left[1] > right[0] for left, right in zip(spans, spans[1:])):
        raise ValueError("ActionData parameter slices overlap")

    parameters = []
    for name, code, position, size in zip(
            param_names, param_data_types, param_positions, param_sizes):
        type_name = PARAM_DATA_TYPES.get(code)
        array_name = specialized_type_arrays.get(code)
        if array_name is not None:
            value = specialized[array_name][position]
            array_entry = specialized_offsets[array_name][position]
            parameters.append({
                "name": name, "serialized_type_code": code, "type": type_name,
                "byte_data_position": None, "byte_data_offset": None,
                "byte_data_size": 0, "specialized_array": array_name,
                "specialized_array_index": position,
                "specialized_array_offset": array_entry["offset"],
                "specialized_array_size": array_entry["size"], "value": value,
            })
            continue
        payload = byte_data[position:position + size]
        value = None
        if type_name is None:
            value = {"decoded": False, "serialized_type_code": code,
                     "payload_size": size}
        elif type_name == "HutongGames.PlayMaker.FsmColor":
            if size != 17:
                if salvage_unknown_parameters:
                    value = {"decoded": False, "serialized_type_code": code,
                             "payload_size": size}
                else:
                    raise ValueError("unsupported FsmColor ActionData encoding")
            else:
                color = struct.unpack("<4f", payload[:16])
                if not all(math.isfinite(item) for item in color) or payload[16] not in (0, 1):
                    if salvage_unknown_parameters:
                        value = {"decoded": False, "serialized_type_code": code,
                                 "payload_size": size}
                    else:
                        raise ValueError("invalid FsmColor ActionData payload")
                else:
                    value = {"rgba": list(color), "use_variable": bool(payload[16])}
        elif type_name == "HutongGames.PlayMaker.FsmInt":
            if size != 5 or payload[4] not in (0, 1):
                if salvage_unknown_parameters:
                    value = {"decoded": False, "serialized_type_code": code,
                             "payload_size": size}
                else:
                    raise ValueError("unsupported FsmInt ActionData encoding")
            else:
                value = {"value": struct.unpack("<i", payload[:4])[0],
                         "use_variable": bool(payload[4])}
        elif type_name == "HutongGames.PlayMaker.FsmRect":
            if size != 17 or payload[16] not in (0, 1):
                if salvage_unknown_parameters:
                    value = {"decoded": False, "serialized_type_code": code,
                             "payload_size": size}
                else:
                    raise ValueError("unsupported FsmRect ActionData encoding")
            else:
                rect = struct.unpack("<4f", payload[:16])
                if not all(math.isfinite(item) for item in rect):
                    if salvage_unknown_parameters:
                        value = {"decoded": False, "serialized_type_code": code,
                                 "payload_size": size}
                    else:
                        raise ValueError("non-finite FsmRect ActionData value")
                else:
                    value = {"rect": list(rect), "use_variable": bool(payload[16])}
        elif type_name in {
                "HutongGames.PlayMaker.FsmVector2",
                "HutongGames.PlayMaker.FsmVector3",
                "HutongGames.PlayMaker.FsmQuaternion"}:
            component_count = {
                "HutongGames.PlayMaker.FsmVector2": 2,
                "HutongGames.PlayMaker.FsmVector3": 3,
                "HutongGames.PlayMaker.FsmQuaternion": 4,
            }[type_name]
            expected_size = component_count * 4 + 1
            if size != expected_size or payload[-1] not in (0, 1):
                if salvage_unknown_parameters:
                    value = {"decoded": False, "serialized_type_code": code,
                             "payload_size": size}
                else:
                    raise ValueError("unsupported vector ActionData encoding")
            else:
                components = struct.unpack("<" + "f" * component_count,
                                           payload[:component_count * 4])
                if not all(math.isfinite(item) for item in components):
                    if salvage_unknown_parameters:
                        value = {"decoded": False, "serialized_type_code": code,
                                 "payload_size": size}
                    else:
                        raise ValueError("non-finite vector ActionData value")
                else:
                    value = {"components": list(components),
                             "use_variable": bool(payload[-1])}
        elif type_name == "HutongGames.PlayMaker.FsmFloat":
            if size < 5 or payload[4] not in (0, 1):
                if salvage_unknown_parameters:
                    value = {"decoded": False, "serialized_type_code": code,
                             "payload_size": size}
                    parameters.append({
                        "name": name, "serialized_type_code": code, "type": type_name,
                        "byte_data_position": position,
                        "byte_data_offset": byte_data_offset + position,
                        "byte_data_size": size, "value": value,
                    })
                    continue
                raise ValueError("unsupported FsmFloat ActionData encoding")
            variable = payload[5:].decode("ascii") if payload[4] else None
            if payload[4] and not variable:
                if salvage_unknown_parameters:
                    value = {"decoded": False, "serialized_type_code": code,
                             "payload_size": size}
                    parameters.append({
                        "name": name, "serialized_type_code": code, "type": type_name,
                        "byte_data_position": position,
                        "byte_data_offset": byte_data_offset + position,
                        "byte_data_size": size, "value": value,
                    })
                    continue
                raise ValueError("empty FsmFloat variable link")
            if payload[4] and any(not (32 <= char < 127) for char in payload[5:]):
                raise ValueError("invalid FsmFloat variable name")
            float_value = struct.unpack("<f", payload[:4])[0]
            if not math.isfinite(float_value):
                raise ValueError("non-finite FsmFloat ActionData value")
            value = {"value": float_value,
                     "use_variable": bool(payload[4]), "variable_name": variable}
        elif type_name == "HutongGames.PlayMaker.FsmBool":
            if size < 2 or payload[0] not in (0, 1) or payload[1] not in (0, 1):
                if salvage_unknown_parameters:
                    value = {"decoded": False, "serialized_type_code": code,
                             "payload_size": size}
                    parameters.append({
                        "name": name, "serialized_type_code": code, "type": type_name,
                        "byte_data_position": position,
                        "byte_data_offset": byte_data_offset + position,
                        "byte_data_size": size, "value": value,
                    })
                    continue
                raise ValueError("invalid FsmBool ActionData payload")
            variable = payload[2:].decode("ascii") if payload[1] else None
            if payload[1] and (not variable or any(not (32 <= char < 127) for char in payload[2:])):
                if salvage_unknown_parameters:
                    value = {"decoded": False, "serialized_type_code": code,
                             "payload_size": size}
                    parameters.append({
                        "name": name, "serialized_type_code": code, "type": type_name,
                        "byte_data_position": position,
                        "byte_data_offset": byte_data_offset + position,
                        "byte_data_size": size, "value": value,
                    })
                    continue
                raise ValueError("invalid FsmBool variable link")
            if not payload[1] and size != 2:
                if salvage_unknown_parameters:
                    value = {"decoded": False, "serialized_type_code": code,
                             "payload_size": size}
                    parameters.append({
                        "name": name, "serialized_type_code": code, "type": type_name,
                        "byte_data_position": position,
                        "byte_data_offset": byte_data_offset + position,
                        "byte_data_size": size, "value": value,
                    })
                    continue
                raise ValueError("unexpected FsmBool payload after a constant")
            value = {"value": bool(payload[0]), "use_variable": bool(payload[1]),
                     "variable_name": variable}
        elif type_name == "HutongGames.PlayMaker.FsmEvent":
            try:
                event_name = payload.decode("ascii")
            except UnicodeDecodeError as exc:
                raise ValueError("invalid FsmEvent ActionData payload") from exc
            if any(not (32 <= char < 127) for char in payload):
                raise ValueError("non-printable FsmEvent ActionData payload")
            value = {"event_name": event_name}
        elif type_name == "System.Boolean":
            if size != 1 or payload[0] not in (0, 1):
                raise ValueError("invalid boolean ActionData payload")
            value = bool(payload[0])
        parameters.append({
            "name": name, "serialized_type_code": code, "type": type_name,
            "byte_data_position": position, "byte_data_offset": byte_data_offset + position,
            "byte_data_size": size, "value": value,
        })

    return {
        "offset": start, "size": reader.pos - start,
        "action_names": action_names, "custom_names": custom_names,
        "enabled": enabled, "is_open": is_open, "start_indices": start_indices,
        "hash_codes_u32": [value & 0xFFFFFFFF for value in hash_codes],
        "unknown_parameter_type_codes": sorted(set(unknown_parameter_types)),
        "specialized_parameter_arrays": specialized,
        "specialized_parameter_array_offsets": specialized_offsets,
        "byte_data_offset": byte_data_offset, "byte_data_size": len(byte_data),
        "_byte_data": byte_data,
        "array_param_sizes": array_param_sizes, "array_param_types": array_param_types,
        "custom_type_sizes": custom_type_sizes, "custom_type_names": custom_type_names,
        "param_data_types": param_data_types, "param_names": param_names,
        "param_data_positions": param_positions, "param_byte_data_sizes": param_sizes,
        "parameters": parameters,
    }


def _encode_string_array(values: list[str]) -> bytes:
    if not isinstance(values, list) or len(values) > MAX_PARAMETERS:
        raise ValueError("PlayMaker string array count outside bounds")
    return struct.pack("<i", len(values)) + b"".join(_encode_aligned_string(value) for value in values)


def _encode_aligned_string(value: str) -> bytes:
    if not isinstance(value, str):
        raise ValueError("invalid PlayMaker string value")
    raw = value.encode("utf-8")
    if len(raw) > MAX_STRING_BYTES:
        raise ValueError("PlayMaker string length outside bounds")
    result = struct.pack("<i", len(raw)) + raw
    return result + bytes((-len(result)) % 4)


def _encode_pptr(pointer: dict[str, int]) -> bytes:
    file_id = pointer.get("file_id")
    path_id = pointer.get("path_id")
    if (type(file_id) is not int or type(path_id) is not int or
            not 0 <= file_id < (1 << 31) or not 0 <= path_id < (1 << 63)):
        raise ValueError("invalid serialized PPtr")
    return struct.pack("<iq", file_id, path_id)


def _encode_bool32(value: object, label: str) -> bytes:
    if not isinstance(value, bool):
        raise ValueError("invalid serialized boolean: " + label)
    return struct.pack("<i", int(value))


def _encode_fsm_game_object(value: dict) -> bytes:
    return (_encode_bool32(value["use_variable"], "FsmGameObject.useVariable") +
            _encode_aligned_string(value["name"]) +
            _encode_aligned_string(value["tooltip"]) +
            _encode_bool32(value["show_in_inspector"], "FsmGameObject.showInInspector") +
            _encode_bool32(value["network_sync"], "FsmGameObject.networkSync") +
            _encode_pptr(value["value_pointer"]))


def _encode_fsm_object(value: dict) -> bytes:
    return (_encode_bool32(value["use_variable"], "FsmObject.useVariable") +
            _encode_aligned_string(value["name"]) +
            _encode_aligned_string(value["tooltip"]) +
            _encode_bool32(value["show_in_inspector"], "FsmObject.showInInspector") +
            _encode_bool32(value["network_sync"], "FsmObject.networkSync") +
            _encode_aligned_string(value["type_name"]) +
            _encode_pptr(value["value_pointer"]))


def _encode_fsm_owner_default(value: dict) -> bytes:
    option = value.get("owner_option")
    if type(option) is not int or option not in (0, 1):
        raise ValueError("unknown FsmOwnerDefault owner option")
    return struct.pack("<i", option) + _encode_fsm_game_object(value["game_object"])


def _encode_fsm_bool_object(value: dict) -> bytes:
    return (_encode_bool32(value["use_variable"], "FsmBool.useVariable") +
            _encode_aligned_string(value["name"]) +
            _encode_aligned_string(value["tooltip"]) +
            _encode_bool32(value["show_in_inspector"], "FsmBool.showInInspector") +
            _encode_bool32(value["network_sync"], "FsmBool.networkSync") +
            _encode_bool32(value["value"], "FsmBool.value"))


def _encode_fsm_string(value: dict) -> bytes:
    return (_encode_bool32(value["use_variable"], "FsmString.useVariable") +
            _encode_aligned_string(value["name"]) +
            _encode_aligned_string(value["tooltip"]) +
            _encode_bool32(value["show_in_inspector"], "FsmString.showInInspector") +
            _encode_bool32(value["network_sync"], "FsmString.networkSync") +
            _encode_aligned_string(value["value"]))


def _encode_fsm_event_target(value: dict) -> bytes:
    target = value.get("target_value")
    if type(target) is not int or not -(1 << 31) <= target < (1 << 31):
        raise ValueError("invalid FsmEventTarget target value")
    return (struct.pack("<i", value["target_value"]) +
            _encode_fsm_bool_object(value["exclude_self"]) +
            _encode_fsm_owner_default(value["game_object"]) +
            _encode_fsm_string(value["fsm_name"]) +
            _encode_fsm_bool_object(value["send_to_children"]) +
            _encode_pptr(value["fsm_component"]))


def _encode_parameter_payload(parameter: dict) -> bytes | None:
    """Encode a semantically decoded byteData parameter, or preserve it raw.

    ``None`` means that this parameter is intentionally opaque and its bytes
    must be retained from the original byteData buffer. FsmTexture and FsmRect
    use formats verified from serialized GetEventInfo fields; GUIContent,
    UnityEngine.Rect and unknown/custom encodings remain unsupported.
    """
    code = parameter.get("serialized_type_code")
    value = parameter.get("value")
    if isinstance(value, dict) and value.get("decoded") is False:
        return None
    if code == 1:  # System.Boolean
        if not isinstance(value, bool):
            raise ValueError("invalid System.Boolean ActionData value")
        return bytes((int(value),))
    if code == 15:  # FsmFloat
        if not isinstance(value, dict):
            raise ValueError("invalid FsmFloat ActionData value")
        number = value.get("value")
        variable = value.get("use_variable")
        variable_name = value.get("variable_name")
        if (not isinstance(number, (int, float)) or not math.isfinite(number) or
                not isinstance(variable, bool)):
            raise ValueError("invalid FsmFloat ActionData fields")
        raw = struct.pack("<fB", number, int(variable))
        if variable:
            if not isinstance(variable_name, str) or not variable_name:
                raise ValueError("FsmFloat variable link is missing its name")
            encoded_name = variable_name.encode("ascii")
            if any(not 32 <= char < 127 for char in encoded_name):
                raise ValueError("invalid FsmFloat variable name")
            raw += encoded_name
        elif variable_name is not None:
            raise ValueError("constant FsmFloat has an unexpected variable name")
        return raw
    if code == 17:  # FsmBool; only emit the variable form when its link decoded.
        if not isinstance(value, dict):
            raise ValueError("invalid FsmBool ActionData value")
        current = value.get("value")
        variable = value.get("use_variable")
        variable_name = value.get("variable_name")
        if not isinstance(current, bool) or not isinstance(variable, bool):
            raise ValueError("invalid FsmBool ActionData fields")
        raw = bytes((int(current), int(variable)))
        if variable:
            if not isinstance(variable_name, str) or not variable_name:
                raise ValueError("FsmBool variable link is missing its name")
            encoded_name = variable_name.encode("ascii")
            if any(not 32 <= char < 127 for char in encoded_name):
                raise ValueError("invalid FsmBool variable name")
            raw += encoded_name
        elif variable_name is not None:
            raise ValueError("constant FsmBool has an unexpected variable name")
        return raw
    if code == 23:  # FsmEvent is stored as printable ASCII in this title.
        if not isinstance(value, dict) or not isinstance(value.get("event_name"), str):
            raise ValueError("invalid FsmEvent ActionData value")
        try:
            raw = value["event_name"].encode("ascii")
        except UnicodeEncodeError as exc:
            raise ValueError("invalid FsmEvent ActionData value") from exc
        if any(not 32 <= char < 127 for char in raw):
            raise ValueError("non-printable FsmEvent ActionData value")
        return raw
    if code == 25:  # FsmColor
        if not isinstance(value, dict):
            raise ValueError("invalid FsmColor ActionData value")
        rgba = value.get("rgba")
        use_variable = value.get("use_variable")
        if (not isinstance(rgba, list) or len(rgba) != 4 or
                not isinstance(use_variable, bool) or
                any(not isinstance(item, (int, float)) or not math.isfinite(item)
                    for item in rgba)):
            raise ValueError("invalid FsmColor ActionData fields")
        return struct.pack("<4fB", *rgba, int(use_variable))
    if code == 16:  # FsmInt
        if (not isinstance(value, dict) or type(value.get("value")) is not int or
                not -(1 << 31) <= value["value"] < (1 << 31) or
                not isinstance(value.get("use_variable"), bool)):
            raise ValueError("invalid FsmInt ActionData fields")
        return struct.pack("<iB", value["value"], int(value["use_variable"]))
    if code == 30:  # FsmRect
        rect = value.get("rect") if isinstance(value, dict) else None
        use_variable = value.get("use_variable") if isinstance(value, dict) else None
        if (not isinstance(rect, list) or len(rect) != 4 or
                not isinstance(use_variable, bool) or
                any(type(item) not in (int, float) or not math.isfinite(item)
                    for item in rect)):
            raise ValueError("invalid FsmRect ActionData fields")
        return struct.pack("<4fB", *rect, int(use_variable))
    vector_shapes = {
        28: 3, 35: 4, 37: 2,
    }
    if code in vector_shapes:
        components = value.get("components") if isinstance(value, dict) else None
        use_variable = value.get("use_variable") if isinstance(value, dict) else None
        count = vector_shapes[code]
        if (not isinstance(components, list) or len(components) != count or
                not isinstance(use_variable, bool) or
                any(type(item) not in (int, float) or not math.isfinite(item)
                    for item in components)):
            raise ValueError("invalid vector ActionData fields")
        return struct.pack("<" + "f" * count + "B",
                           *components, int(use_variable))
    # Unknown, unsupported, and specialized-array parameters carry no
    # independently verified byteData encoder.
    return None


def _encode_action_byte_data(action_data: dict) -> bytes:
    original = action_data.get("_byte_data")
    if not isinstance(original, bytes) or len(original) > MAX_ACTION_DATA_BYTES:
        raise ValueError("missing or oversized raw ActionData byteData")
    result = bytearray(original)
    parameters = action_data.get("parameters")
    if not isinstance(parameters, list) or len(parameters) != len(action_data["param_names"]):
        raise ValueError("ActionData decoded parameter count is inconsistent")
    if not (len(action_data["param_data_types"]) ==
            len(action_data["param_data_positions"]) ==
            len(action_data["param_byte_data_sizes"]) == len(parameters)):
        raise ValueError("ActionData parameter metadata lengths differ")
    spans = []
    specialized_type_arrays = {
        18: "fsmStringParams", 19: "fsmGameObjectParams",
        20: "fsmOwnerDefaultParams", 24: "fsmObjectParams",
        31: "fsmEventTargetParams", 32: "fsmObjectParams",
        33: "fsmObjectParams",
    }
    specialized = action_data.get("specialized_parameter_arrays")
    if not isinstance(specialized, dict):
        raise ValueError("ActionData specialized parameter arrays are missing")
    for parameter, name, code, position, size in zip(
            parameters, action_data["param_names"], action_data["param_data_types"],
            action_data["param_data_positions"], action_data["param_byte_data_sizes"]):
        if (parameter.get("name") != name or
                parameter.get("serialized_type_code") != code):
            raise ValueError("ActionData parameter identity disagrees with its metadata")
        array_name = specialized_type_arrays.get(code)
        if array_name is not None:
            index = parameter.get("specialized_array_index")
            array_values = specialized.get(array_name)
            if (size != 0 or parameter.get("specialized_array") != array_name or
                    index != position or type(index) is not int or
                    not isinstance(array_values, list) or
                    not 0 <= index < len(array_values)):
                raise ValueError("ActionData specialized parameter reference is invalid")
            if parameter.get("value") != array_values[index]:
                raise ValueError("ActionData specialized parameter value disagrees with its array entry")
            continue
        if (type(position) is not int or type(size) is not int or
                position < 0 or size < 0 or position + size > len(result)):
            raise ValueError("ActionData parameter slice is outside byteData")
        if size:
            spans.append((position, position + size))
        payload = _encode_parameter_payload(parameter)
        if payload is None:
            continue
        if len(payload) != size:
            raise ValueError("encoded ActionData parameter size changed")
        result[position:position + size] = payload
    spans.sort()
    if any(left[1] > right[0] for left, right in zip(spans, spans[1:])):
        raise ValueError("ActionData parameter slices overlap")
    return bytes(result)


def encode_action_data(action_data: dict) -> bytes:
    """Encode only the verified ActionData wire subset accepted by the parser."""
    if action_data.get("empty_sentinel_words") == 27:
        return bytes(27 * 4)
    names = action_data.get("action_names")
    if not isinstance(names, list) or not 1 <= len(names) <= MAX_ACTIONS:
        raise ValueError("ActionData action count outside bounds")
    custom_names = action_data.get("custom_names")
    if not isinstance(custom_names, list) or len(custom_names) != len(names):
        raise ValueError("ActionData custom name count mismatch")
    for name in names + custom_names:
        if not isinstance(name, str) or len(name.encode("utf-8")) > MAX_STRING_BYTES:
            raise ValueError("ActionData action name outside bounds")
    parameter_names = action_data.get("param_names")
    parameter_types = action_data.get("param_data_types")
    parameter_positions = action_data.get("param_data_positions")
    parameter_sizes = action_data.get("param_byte_data_sizes")
    if (not all(isinstance(values, list) for values in
                (parameter_names, parameter_types, parameter_positions, parameter_sizes)) or
            not (len(parameter_names) == len(parameter_types) ==
                 len(parameter_positions) == len(parameter_sizes)) or
            len(parameter_names) > MAX_PARAMETERS):
        raise ValueError("ActionData parameter metadata lengths differ")
    if any(type(value) is not int or not -(1 << 31) <= value < (1 << 31)
           for values in (parameter_types, parameter_positions, parameter_sizes)
           for value in values):
        raise ValueError("ActionData parameter metadata integer outside bounds")
    if any(size < 0 for size in parameter_sizes):
        raise ValueError("negative ActionData parameter size")
    start_indices = action_data.get("start_indices")
    hash_codes = action_data.get("hash_codes_u32")
    if (not isinstance(start_indices, list) or not isinstance(hash_codes, list) or
            len(start_indices) != len(names) or len(hash_codes) != len(names) or
            (start_indices and start_indices[0] != 0) or
            any(type(value) is not int or value < 0 or value > len(parameter_names)
                for value in start_indices) or
            any(left > right for left, right in zip(start_indices, start_indices[1:])) or
            any(type(value) is not int or not 0 <= value <= 0xFFFFFFFF
                for value in hash_codes)):
        raise ValueError("ActionData per-action indices or hashes are invalid")
    array_param_sizes = action_data.get("array_param_sizes")
    array_param_types = action_data.get("array_param_types")
    custom_type_sizes = action_data.get("custom_type_sizes")
    custom_type_names = action_data.get("custom_type_names")
    if (not isinstance(array_param_sizes, list) or
            not isinstance(array_param_types, list) or
            len(array_param_sizes) != len(array_param_types) or
            not isinstance(custom_type_sizes, list) or
            not isinstance(custom_type_names, list) or
            len(custom_type_sizes) != len(custom_type_names)):
        raise ValueError("ActionData array/custom type metadata lengths differ")
    result = struct.pack("<i", len(names)) + b"".join(_encode_aligned_string(x) for x in names)
    result += _encode_string_array(custom_names)
    for label in ("enabled", "is_open"):
        values = action_data[label]
        if len(values) != len(names):
            raise ValueError("ActionData per-action boolean length mismatch")
        if any(not isinstance(value, bool) for value in values):
            raise ValueError("ActionData per-action boolean value is invalid")
        raw = bytes(int(value) for value in values)
        result += struct.pack("<i", len(raw)) + raw
        result += bytes((-len(raw)) % 4)
    for values in (start_indices, hash_codes):
        result += struct.pack("<i", len(values))
        result += b"".join(struct.pack("<I", value) for value in values)

    specialized = action_data["specialized_parameter_arrays"]
    for field_name in ACTIONDATA_SPECIAL_ARRAYS:
        values = specialized.get(field_name, [])
        if not isinstance(values, list) or len(values) > MAX_PARAMETERS:
            raise ValueError("ActionData specialized array count outside bounds")
        result += struct.pack("<i", len(values))
        if field_name == "fsmGameObjectParams":
            result += b"".join(_encode_fsm_game_object(value) for value in values)
        elif field_name == "fsmObjectParams":
            result += b"".join(_encode_fsm_object(value) for value in values)
        elif field_name == "fsmOwnerDefaultParams":
            result += b"".join(_encode_fsm_owner_default(value) for value in values)
        elif field_name == "fsmEventTargetParams":
            result += b"".join(_encode_fsm_event_target(value) for value in values)
        elif field_name == "fsmStringParams":
            result += b"".join(_encode_fsm_string(value) for value in values)
        elif values:
            raise ValueError("cannot encode unsupported specialized ActionData array: " + field_name)

    byte_data = _encode_action_byte_data(action_data)
    result += struct.pack("<i", len(byte_data)) + byte_data
    result += bytes((-len(byte_data)) % 4)
    for key in ("array_param_sizes", "array_param_types", "custom_type_sizes"):
        values = action_data[key]
        if (not isinstance(values, list) or len(values) > MAX_PARAMETERS or
                any(type(value) is not int or not -(1 << 31) <= value < (1 << 31)
                    for value in values)):
            raise ValueError("ActionData integer array outside bounds: " + key)
        if key in ("array_param_sizes", "custom_type_sizes") and any(value < 0 for value in values):
            raise ValueError("negative ActionData size metadata")
        result += struct.pack("<i", len(values))
        result += b"".join(struct.pack("<i", value) for value in values)
    result += _encode_string_array(action_data["custom_type_names"])
    result += struct.pack("<i", len(parameter_types))
    result += b"".join(struct.pack("<i", value) for value in parameter_types)
    result += _encode_string_array(parameter_names)
    for values in (parameter_positions, parameter_sizes):
        result += struct.pack("<i", len(values))
        result += b"".join(struct.pack("<i", value) for value in values)
    if len(result) > MAX_COMPONENT_BYTES:
        raise ValueError("encoded ActionData exceeds the byte limit")
    return result


def _public_json(value):
    """Exclude private round-trip byte buffers from JSON-derived reports."""
    if isinstance(value, dict):
        return {key: _public_json(item) for key, item in value.items()
                if not key.startswith("_")}
    if isinstance(value, list):
        return [_public_json(item) for item in value]
    return value


def _parse_transition(reader: Reader) -> dict:
    event_name, event_offset = reader.aligned_string()
    is_system_event = reader.bool32("FsmEvent.isSystemEvent")
    is_global = reader.bool32("FsmEvent.isGlobal")
    to_state, to_state_offset = reader.aligned_string()
    link_style = reader.i32()
    link_constraint = reader.i32()
    color_index = reader.i32()
    return {
        "event": event_name, "event_offset": event_offset,
        "is_system_event": is_system_event, "is_global": is_global,
        "to_state": to_state, "to_state_offset": to_state_offset,
        "link_style": link_style, "link_constraint": link_constraint,
        "color_index": color_index,
    }


def _parse_camera_fade_fsm_variables(reader: Reader) -> dict:
    """Decode the one title-specific float variable layout in cameraFadeFSM."""
    start = reader.pos
    float_count = reader.count("FsmVariables.floatVariables", 128)
    if float_count > 1:
        raise ValueError("cameraFadeFSM float variable count is unsupported")
    float_variables = []
    if float_count:
        leading_word = reader.i32()  # preserve; its field meaning is not established.
        variable_name, name_offset = reader.aligned_string()
        reference_file_id = reader.i32()
        reference_path_id = struct.unpack("<q", reader.take(8))[0]
        value = reader.f32()
        float_variables.append({
            "name": variable_name, "name_offset": name_offset,
            "serialized_leading_word": leading_word,
            "reference_pointer": {"file_id": reference_file_id,
                                  "path_id": reference_path_id},
            "value": value,
        })
    empty_arrays = {}
    for name in ("intVariables", "boolVariables", "stringVariables", "vector2Variables",
                 "vector3Variables", "colorVariables", "rectVariables", "quaternionVariables",
                 "gameObjectVariables", "objectVariables", "materialVariables", "textureVariables"):
        count = reader.count("FsmVariables." + name, 128)
        if count:
            raise ValueError("nonempty cameraFadeFSM variable array is unsupported: " + name)
        empty_arrays[name] = count
    global_variables_synced = reader.bool32("FsmVariables.GlobalVariablesSynced")
    return {
        "offset": start, "size": reader.pos - start,
        "float_variables": float_variables,
        "empty_variable_arrays": empty_arrays,
        "global_variables_synced": global_variables_synced,
    }


def parse_fsm_component(blob: bytes, *, has_template_pointer: bool = True) -> dict:
    if len(blob) < 32 or len(blob) > MAX_COMPONENT_BYTES:
        raise ValueError("PlayMakerFSM component size outside bounds")
    reader = Reader(blob, 32)  # MonoBehaviour header is parsed by the Unity asset reader.
    template_file_id = reader.i32()
    template_path_id = struct.unpack("<q", reader.take(8))[0]
    fsm_name, name_offset = reader.aligned_string()
    start_state, start_state_offset = reader.aligned_string()
    state_count = reader.count("Fsm.states", MAX_STATES)
    states = []
    for _ in range(state_count):
        state_offset = reader.pos
        name, _ = reader.aligned_string()
        description, _ = reader.aligned_string()
        color_index = reader.i32()
        rect = [reader.f32() for _ in range(4)]
        flags = {
            "breakpoint": reader.bool32("FsmState.isBreakpoint"),
            "sequence": reader.bool32("FsmState.isSequence"),
            "hide_unused": reader.bool32("FsmState.hideUnused"),
        }
        transition_count = reader.count("FsmState.transitions", MAX_TRANSITIONS)
        transitions = [_parse_transition(reader) for _ in range(transition_count)]
        action_data = parse_action_data(reader)
        states.append({
            "name": name, "offset": state_offset, "description": description,
            "color_index": color_index, "rect": rect, **flags,
            "transitions": transitions, "action_data": action_data,
        })

    event_count = reader.count("Fsm.events", MAX_EVENTS)
    events = []
    for _ in range(event_count):
        event_name, offset = reader.aligned_string()
        events.append({"name": event_name, "offset": offset,
                       "is_system_event": reader.bool32("FsmEvent.isSystemEvent"),
                       "is_global": reader.bool32("FsmEvent.isGlobal")})
    global_transition_count = reader.count("Fsm.globalTransitions", MAX_TRANSITIONS)
    if global_transition_count:
        raise ValueError("nonempty Fsm.globalTransitions are unsupported")
    variables = _parse_camera_fade_fsm_variables(reader)

    # This title's PlayMakerFSM component has 40 bytes of still-opaque Fsm
    # state followed by the serialized FsmTemplate PPtr. A standalone
    # FsmTemplate's embedded Fsm has the same 40-byte tail but no component
    # reference. Keep those bytes opaque and decode only the PPtr whose field
    # identity is independently present in PlayMakerFSM metadata.
    tail_size = len(blob) - reader.pos
    expected_tail_size = 52 if has_template_pointer else 40
    if tail_size != expected_tail_size:
        raise ValueError("unsupported PlayMaker Fsm tail size")
    opaque_tail_size = 40
    opaque_tail_offset = reader.pos
    reader.take(opaque_tail_size)
    template_pointer = None
    if has_template_pointer:
        template_pointer_offset = reader.pos
        file_id = reader.i32()
        path_id = struct.unpack("<q", reader.take(8))[0]
        if file_id < 0 or path_id < 0:
            raise ValueError("negative serialized FsmTemplate PPtr")
        template_pointer = {
            "file_id": file_id, "path_id": path_id,
            "offset": template_pointer_offset,
        }

    state_names = [state["name"] for state in states]
    event_names = [event["name"] for event in events]
    if not fsm_name or len(set(state_names)) != len(state_names):
        raise ValueError("empty FSM name or duplicate state name")
    if start_state not in state_names:
        raise ValueError("Fsm.startState does not reference a serialized state")
    if len(set(event_names)) != len(event_names):
        raise ValueError("duplicate Fsm event name")
    for state in states:
        for transition in state["transitions"]:
            if transition["event"] not in event_names:
                raise ValueError("transition references an undeclared Fsm event")
            if transition["to_state"] not in state_names:
                raise ValueError("transition references an undeclared state")

    float_variable_names = {entry["name"] for entry in variables["float_variables"]}
    for state in states:
        for parameter in state["action_data"]["parameters"]:
            value = parameter["value"]
            if (parameter["type"] == "HutongGames.PlayMaker.FsmFloat" and
                    value and value["use_variable"] and
                    value["variable_name"] not in float_variable_names):
                raise ValueError("ActionData FsmFloat variable link is unresolved")

    return {
        "used_in_template_pointer": {"file_id": template_file_id,
                                      "path_id": template_path_id},
        "name": fsm_name, "name_offset": name_offset,
        "start_state": start_state, "start_state_offset": start_state_offset,
        "states": states, "events": events, "global_transitions_count": global_transition_count,
        "variables": variables,
        "opaque_fsm_tail": {"offset": opaque_tail_offset, "size": opaque_tail_size},
        "fsm_template_pointer": template_pointer,
    }


def _aligned_cstring(data: bytes, offset: int) -> tuple[str, int]:
    if offset < 0 or offset >= len(data):
        raise ValueError("FsmTemplate name offset outside object")
    end = data.find(b"\0", offset, min(len(data), offset + MAX_STRING_BYTES + 1))
    if end < 0:
        raise ValueError("unterminated FsmTemplate name")
    try:
        value = data[offset:end].decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("invalid UTF-8 in FsmTemplate name") from exc
    if not value:
        raise ValueError("empty FsmTemplate name")
    aligned = (end + 4) & ~3
    if aligned > len(data) or any(data[end + 1:aligned]):
        raise ValueError("invalid FsmTemplate name padding")
    return value, aligned


def parse_fsm_template_header(blob: bytes) -> dict:
    """Decode the verified FsmTemplate wrapper and its embedded Fsm header."""
    if len(blob) < 32 or len(blob) > MAX_COMPONENT_BYTES:
        raise ValueError("FsmTemplate object size outside bounds")
    template_name, at = _aligned_cstring(blob, 32)
    reader = Reader(blob, at)
    category, category_offset = reader.aligned_string()
    fsm_payload_offset = reader.pos
    template_file_id = reader.i32()
    template_path_id = struct.unpack("<q", reader.take(8))[0]
    fsm_name, fsm_name_offset = reader.aligned_string()
    start_state, start_state_offset = reader.aligned_string()
    state_count = reader.count("FsmTemplate Fsm.states", MAX_STATES)
    return {
        "name": template_name, "category": category,
        "category_offset": category_offset,
        "fsm_used_in_template_pointer": {"file_id": template_file_id,
                                          "path_id": template_path_id},
        "fsm_name": fsm_name, "fsm_name_offset": fsm_name_offset,
        "start_state": start_state, "start_state_offset": start_state_offset,
        "state_count": state_count,
        "fsm_payload_offset": fsm_payload_offset,
    }


def _semantic_fsm_summary(fsm: dict) -> dict:
    """Strip file offsets and editor rectangles for scene/template comparison."""
    return {
        "name": fsm["name"], "start_state": fsm["start_state"],
        "events": [{"name": item["name"], "is_system_event": item["is_system_event"],
                    "is_global": item["is_global"]} for item in fsm["events"]],
        "global_transitions_count": fsm["global_transitions_count"],
        "states": [{
            "name": state["name"], "description": state["description"],
            "transitions": [{key: item[key] for key in (
                "event", "is_system_event", "is_global", "to_state", "link_style",
                "link_constraint", "color_index")}
                for item in state["transitions"]],
            "actions": state["action_data"]["action_names"],
            "parameters": [{"name": item["name"], "type": item["type"],
                            "serialized_type_code": item["serialized_type_code"],
                            "byte_data_size": item["byte_data_size"], "value": item["value"]}
                           for item in state["action_data"]["parameters"]],
        } for state in fsm["states"]],
        "float_variables": [{"name": item["name"], "value": item["value"],
                             "reference_pointer": item["reference_pointer"]}
                            for item in fsm["variables"]["float_variables"]],
        "empty_variable_arrays": fsm["variables"]["empty_variable_arrays"],
        "global_variables_synced": fsm["variables"]["global_variables_synced"],
    }


def validate_action_data_schema(fsm: dict, resolver: TypeResolver) -> None:
    for state in fsm["states"]:
        action_data = state["action_data"]
        for action_name in action_data["action_names"]:
            fields = resolver.action_fields(action_name)
            params = action_data["parameters"]
            if action_name.endswith(".CameraFadeIn") or action_name.endswith(".CameraFadeOut"):
                if [field["name"] for field in fields[:len(params)]] != [p["name"] for p in params]:
                    raise ValueError("ActionData parameter names do not match AOT metadata fields")
                for field, parameter in zip(fields[:len(params)], params):
                    if PARAM_DATA_TYPES.get(parameter["serialized_type_code"]) != field["type"]:
                        raise ValueError("ActionData serialized type code disagrees with IL2CPP field type")
            elif params:
                raise ValueError("parameter decoding is only verified for camera fade actions")


def build_synthetic_menu_graph() -> dict:
    def p(type_name: str, value):
        return {"type": type_name, "value": value}

    rect = {
        "left": p("HutongGames.PlayMaker.FsmFloat", 80.0),
        "top": p("HutongGames.PlayMaker.FsmFloat", 60.0),
        "width": p("HutongGames.PlayMaker.FsmFloat", 560.0),
        "height": p("HutongGames.PlayMaker.FsmFloat", 420.0),
        "normalized": p("HutongGames.PlayMaker.FsmBool", False),
    }
    label_rect = {
        "left": p("HutongGames.PlayMaker.FsmFloat", 100.0),
        "top": p("HutongGames.PlayMaker.FsmFloat", 80.0),
        "width": p("HutongGames.PlayMaker.FsmFloat", 520.0),
        "height": p("HutongGames.PlayMaker.FsmFloat", 48.0),
        "normalized": p("HutongGames.PlayMaker.FsmBool", False),
    }
    button_rect = {
        "left": p("HutongGames.PlayMaker.FsmFloat", 500.0),
        "top": p("HutongGames.PlayMaker.FsmFloat", 420.0),
        "width": p("HutongGames.PlayMaker.FsmFloat", 100.0),
        "height": p("HutongGames.PlayMaker.FsmFloat", 40.0),
        "normalized": p("HutongGames.PlayMaker.FsmBool", False),
    }
    toggle = {
        "buttonName": p("HutongGames.PlayMaker.FsmString", "MenuToggle"),
        "sendEvent": p("HutongGames.PlayMaker.FsmEvent", "Open"),
        "storeResult": p("HutongGames.PlayMaker.FsmBool", False),
    }
    return {
        "name": "UCM_Menu_Synthetic", "start_state": "Closed",
        "events": ["Open", "Close", "MenuVisible"],
        "input_assumption": {
            "rewired_action": "MenuToggle",
            "binding_status": "no serialized DS4 ActionElementMap in the inspected defaults",
            "runtime_player_manager_focus_verified": False,
            "reserved_chord": "none; L1+R1 overlaps serialized gameplay/menu defaults",
        },
        "states": [
            {"name": "Closed", "actions": [
                {"type": "HutongGames.PlayMaker.Actions.GetButtonDown", "fields": toggle},
            ], "transitions": [{"event": "Open", "to_state": "Main"}]},
            {"name": "Main", "actions": [
                {"type": "HutongGames.PlayMaker.Actions.GUIBox", "fields": {
                    **rect, "text": p("HutongGames.PlayMaker.FsmString", "Ultimate Mod Menu"),
                }},
                {"type": "HutongGames.PlayMaker.Actions.GUILabel", "fields": {
                    **label_rect, "text": p("HutongGames.PlayMaker.FsmString", "UCM menu"),
                }},
                {"type": "HutongGames.PlayMaker.Actions.GUIButton", "fields": {
                    **button_rect, "text": p("HutongGames.PlayMaker.FsmString", "Close"),
                    "sendEvent": p("HutongGames.PlayMaker.FsmEvent", "Close"),
                    "storeButtonState": p("HutongGames.PlayMaker.FsmBool", False),
                }},
                {"type": "HutongGames.PlayMaker.Actions.GetButtonDown", "fields": {
                    "buttonName": p("HutongGames.PlayMaker.FsmString", "MenuToggle"),
                    "sendEvent": p("HutongGames.PlayMaker.FsmEvent", "Close"),
                    "storeResult": p("HutongGames.PlayMaker.FsmBool", False),
                }},
                {"type": "HutongGames.PlayMaker.Actions.SendEvent", "fields": {
                    "eventTarget": p("HutongGames.PlayMaker.FsmEventTarget", {
                        "symbolic_target": "Self", "serialization_verified": False,
                    }),
                    "sendEvent": p("HutongGames.PlayMaker.FsmEvent", "MenuVisible"),
                    "delay": p("HutongGames.PlayMaker.FsmFloat", 0.0),
                    "everyFrame": p("System.Boolean", False),
                }},
            ], "transitions": [{"event": "Close", "to_state": "Closed"}]},
        ],
    }


def validate_synthetic_menu_graph(graph: dict, action_fields: dict[str, list[dict[str, str]]],
                                  aot_actions: dict[str, dict]) -> dict:
    states = graph.get("states")
    if not isinstance(states, list) or not states or len(states) > MAX_STATES:
        raise ValueError("synthetic FSM state count outside bounds")
    names = [state.get("name") for state in states]
    if any(not isinstance(name, str) or not name for name in names) or len(set(names)) != len(names):
        raise ValueError("synthetic FSM has empty or duplicate state names")
    if graph.get("start_state") not in names:
        raise ValueError("synthetic FSM start state is unresolved")
    events = graph.get("events")
    if not isinstance(events, list) or len(set(events)) != len(events):
        raise ValueError("synthetic FSM events are invalid or duplicated")
    event_set, state_set = set(events), set(names)
    action_count = transition_count = 0
    action_types_seen: set[str] = set()
    omitted_metadata_fields: dict[str, set[str]] = {}
    for state in states:
        emitted_events: set[str] = set()
        for transition in state.get("transitions", []):
            transition_count += 1
            if transition.get("event") not in event_set or transition.get("to_state") not in state_set:
                raise ValueError("synthetic FSM transition has an unresolved event or state")
        for action in state.get("actions", []):
            action_count += 1
            name = action.get("type", "")
            short_name = name.rsplit(".", 1)[-1]
            if short_name not in aot_actions or name not in action_fields:
                raise ValueError("synthetic action is not an AOT action in this title")
            schema = {field["name"]: field["type"] for field in action_fields[name]}
            for field_name, typed_value in action.get("fields", {}).items():
                if field_name not in schema:
                    raise ValueError("synthetic action field is absent from IL2CPP metadata")
                if not isinstance(typed_value, dict) or typed_value.get("type") != schema[field_name]:
                    raise ValueError("synthetic action field type disagrees with IL2CPP metadata")
                value = typed_value.get("value")
                if schema[field_name] == "HutongGames.PlayMaker.FsmEvent" and value is not None:
                    if value not in event_set:
                        raise ValueError("synthetic action references an undeclared Fsm event")
                    if field_name == "sendEvent":
                        emitted_events.add(value)
                if schema[field_name] == "HutongGames.PlayMaker.FsmEventTarget":
                    if (not isinstance(value, dict) or value.get("symbolic_target") != "Self" or
                            value.get("serialization_verified") is not False):
                        raise ValueError("synthetic FsmEventTarget must stay explicitly symbolic")
            callbacks = aot_actions[short_name]
            expected_slot = {"GUIBox": 33, "GUILabel": 33, "GUIButton": 33,
                             "GetButtonDown": 32, "SendEvent": 30}.get(short_name)
            if callbacks.get("virtual_slot") != expected_slot:
                raise ValueError("synthetic action callback slot does not match the title audit")
            action_types_seen.add(short_name)
            omitted_metadata_fields.setdefault(short_name, set()).update(
                set(schema) - set(action.get("fields", {})))
            if (short_name in {"GUIButton", "GetButtonDown"} and
                    action.get("fields", {}).get("sendEvent", {}).get("value") is not None and
                    action["fields"]["sendEvent"]["value"] not in {
                        transition.get("event") for transition in state.get("transitions", [])}):
                raise ValueError("synthetic graphical/input action event has no state transition")
        if any(item.get("event") not in emitted_events for item in state.get("transitions", [])):
            raise ValueError("synthetic transition has no matching event-producing action")
    if action_count > MAX_ACTIONS or transition_count > MAX_TRANSITIONS:
        raise ValueError("synthetic FSM action or transition count outside bounds")
    required_types = {"GUIBox", "GUILabel", "GUIButton", "GetButtonDown", "SendEvent"}
    if not required_types.issubset(action_types_seen):
        raise ValueError("synthetic menu graph omits a required precompiled action")
    return {
        "validated": True, "states": len(states), "events": len(events),
        "transitions": transition_count, "actions": action_count,
        "input_binding_verified": False,
        "unmodeled_metadata_fields": {
            name: sorted(fields) for name, fields in sorted(omitted_metadata_fields.items())
            if fields
        },
        "limitations": [
            "normalized graph only; no Unity ActionData bytes were generated",
            "some AOT metadata fields remain unmodeled; FsmEventTarget Self is symbolic and its serialized payload is not verified",
            "MenuToggle has no serialized DS4 binding in the inspected defaults",
            "runtime player, active manager, focus, lifecycle, and component registration are unverified",
        ],
    }


def _component_fsm_name(blob: bytes) -> str:
    if len(blob) < 48:
        return ""
    return Reader(blob, 44).aligned_string()[0]


def inspect(level2_data: bytes, global_data: bytes, sharedassets2_data: bytes,
            module: bytes, metadata_data: bytes) -> dict:
    if hashlib.sha256(level2_data).hexdigest() != LEVEL2_SHA256:
        raise ValueError("wrong level2 asset hash")
    if hashlib.sha256(global_data).hexdigest() != GLOBALGAMEMANAGERS_SHA256:
        raise ValueError("wrong globalgamemanagers asset hash")
    if hashlib.sha256(sharedassets2_data).hexdigest() != SHAREDASSETS2_SHA256:
        raise ValueError("wrong sharedassets2 asset hash")
    resolver = TypeResolver(module, metadata_data)
    lifecycle = inspect_fsm_lifecycle(module, metadata_data)
    with tempfile.TemporaryDirectory(prefix="ucm-playmaker-readonly-") as tmp:
        temp_root = Path(tmp)
        level_path = temp_root / "level2"
        global_path = temp_root / "globalgamemanagers.assets"
        sharedassets2_path = temp_root / "sharedassets2.assets"
        level_path.write_bytes(level2_data)
        global_path.write_bytes(global_data)
        sharedassets2_path.write_bytes(sharedassets2_data)
        level = Asset(level_path)
        global_asset = Asset(global_path)
        sharedassets2 = Asset(sharedassets2_path)
        scripts = {pid: monoscript(global_asset.obj(pid)) for pid in global_asset.ids(115)}
        playmaker_scripts = {pid for pid, script in scripts.items()
                             if script["name"] == "PlayMakerFSM"
                             and script["class_name"] == "PlayMakerFSM"
                             and script["assembly"] == "PlayMaker.dll"}
        template_scripts = {pid for pid, script in scripts.items()
                            if script["class_name"] == "FsmTemplate"
                            and script["assembly"] == "PlayMaker.dll"}
        if not playmaker_scripts or not template_scripts:
            raise ValueError("PlayMakerFSM MonoScript is missing")

        playmaker_fields = resolver.declared_fields(
            "PlayMakerFSM", {"fsm", "fsmTemplate"})
        template_fields = resolver.declared_fields("FsmTemplate", {"category", "fsm"})
        fsm_fields = resolver.declared_fields(
            "HutongGames.PlayMaker.Fsm", {"owner", "usedInTemplate", "name", "startState"})
        if ({(item["name"], item["type"]) for item in playmaker_fields} != {
                ("fsm", "HutongGames.PlayMaker.Fsm"), ("fsmTemplate", "FsmTemplate")} or
                {(item["name"], item["type"]) for item in template_fields} != {
                    ("category", "System.String"), ("fsm", "HutongGames.PlayMaker.Fsm")} or
                {(item["name"], item["type"]) for item in fsm_fields} != {
                    ("owner", "UnityEngine.MonoBehaviour"),
                    ("usedInTemplate", "FsmTemplate"),
                    ("name", "System.String"), ("startState", "System.String")}):
            raise ValueError("PlayMakerFSM/FsmTemplate fields disagree with serialized references")

        candidates = []
        for path_id in level.ids(114):
            mono = level.mono(path_id)
            if mono["script_id"] not in playmaker_scripts:
                continue
            if level.external(mono["script_file"]) != "globalgamemanagers.assets":
                continue
            go = level.gameobject(mono["game_id"])
            if go["name"] == "CutSceneController":
                candidates.append((path_id, mono, go, level.obj(path_id)))
        if len(candidates) != 2:
            raise ValueError("expected the two serialized CutSceneController PlayMakerFSMs")
        selected = [(path_id, mono, go, blob) for path_id, mono, go, blob in candidates
                    if _component_fsm_name(blob) == "cameraFadeFSM"]
        if len(selected) != 1:
            raise ValueError("cameraFadeFSM component is missing or ambiguous")
        path_id, mono, go, blob = selected[0]
        fsm = parse_fsm_component(blob)

        scene_template_links = []
        resolved_templates = {}
        for component_id, component_mono, component_go, component_blob in candidates:
            component_name = _component_fsm_name(component_blob)
            if len(component_blob) < 12:
                raise ValueError("PlayMakerFSM component has no trailing fsmTemplate field")
            file_id, template_path_id = struct.unpack_from(
                "<iq", component_blob, len(component_blob) - 12)
            if file_id <= 0 or template_path_id <= 0:
                raise ValueError("CutSceneController PlayMakerFSM has no serialized FsmTemplate")
            external_name = level.external(file_id)
            if external_name != "sharedassets2.assets":
                raise ValueError("CutSceneController FsmTemplate points outside sharedassets2")
            if template_path_id not in sharedassets2.objects:
                raise ValueError("FsmTemplate PPtr pathID is missing from sharedassets2")
            template_item = sharedassets2.objects[template_path_id]
            if template_item.class_id != 114:
                raise ValueError("FsmTemplate PPtr does not target a MonoBehaviour object")
            template_mono = sharedassets2.mono(template_path_id)
            if (sharedassets2.external(template_mono["script_file"]) != "globalgamemanagers.assets" or
                    template_mono["script_id"] not in template_scripts):
                raise ValueError("FsmTemplate PPtr target has a different MonoScript")
            template_header = parse_fsm_template_header(sharedassets2.obj(template_path_id))
            if template_header["fsm_used_in_template_pointer"] != {
                    "file_id": 0, "path_id": template_path_id}:
                raise ValueError("FsmTemplate embedded Fsm template pointer is not self-referential")
            template_summary = {
                "path_id": template_path_id, "class_id": template_item.class_id,
                "size": template_item.size, "script": "FsmTemplate",
                "name": template_header["name"], "category": template_header["category"],
                "embedded_fsm_name": template_header["fsm_name"],
                "start_state": template_header["start_state"],
                "state_count": template_header["state_count"],
                "embedded_fsm_used_in_template_pointer":
                    template_header["fsm_used_in_template_pointer"],
            }
            resolved_templates[template_path_id] = template_summary
            scene_template_links.append({
                "component_path_id": component_id,
                "game_object_path_id": component_mono["game_id"],
                "game_object_name": component_go["name"],
                "component_fsm_name": component_name,
                "component_size": len(component_blob),
                "fsmTemplate_pointer": {"file_id": file_id, "path_id": template_path_id,
                                         "offset": len(component_blob) - 12},
                "external_asset": external_name,
                "template": template_summary,
            })

        camera_template_link = next(
            row for row in scene_template_links
            if row["component_path_id"] == path_id)
        if fsm["fsm_template_pointer"] != camera_template_link["fsmTemplate_pointer"]:
            raise ValueError("parsed cameraFadeFSM fsmTemplate pointer disagrees with component tail")
        camera_template_id = camera_template_link["template"]["path_id"]
        camera_template_blob = sharedassets2.obj(camera_template_id)
        camera_template_header = parse_fsm_template_header(camera_template_blob)
        template_fsm = parse_fsm_component(
            camera_template_blob[camera_template_header["fsm_payload_offset"] - 32:],
            has_template_pointer=False)
        if template_fsm["name"] != "cameraFadeFSM":
            raise ValueError("cameraFadeFSM template embedded Fsm name mismatch")
        validate_action_data_schema(template_fsm, resolver)
        component_semantics = _semantic_fsm_summary(fsm)
        template_semantics = _semantic_fsm_summary(template_fsm)
        if component_semantics != template_semantics:
            raise ValueError("cameraFadeFSM component graph differs from its FsmTemplate")

        prefab_component_count = 0
        prefab_null_template_count = 0
        for prefab_component_id in sharedassets2.ids(114):
            prefab_mono = sharedassets2.mono(prefab_component_id)
            if (sharedassets2.external(prefab_mono["script_file"]) != "globalgamemanagers.assets" or
                    prefab_mono["script_id"] not in playmaker_scripts):
                continue
            prefab_component_count += 1
            prefab_blob = sharedassets2.obj(prefab_component_id)
            if len(prefab_blob) < 12:
                raise ValueError("sharedassets2 PlayMakerFSM component is truncated")
            template_file_id, template_id = struct.unpack_from(
                "<iq", prefab_blob, len(prefab_blob) - 12)
            if (template_file_id, template_id) == (0, 0):
                prefab_null_template_count += 1
        if prefab_component_count != 13 or prefab_null_template_count != 13:
            raise ValueError("sharedassets2 embedded PlayMakerFSM inventory changed")
    if fsm["name"] != "cameraFadeFSM":
        raise ValueError("selected PlayMakerFSM name mismatch")
    validate_action_data_schema(fsm, resolver)

    aot = inspect_gui_aot(module, metadata_data)
    action_fields: dict[str, list[dict[str, str]]] = {}
    for short_name in ("GUIBox", "GUILabel", "GUIButton", "GetButtonDown", "SendEvent"):
        full_name = "HutongGames.PlayMaker.Actions." + short_name
        action_fields[full_name] = resolver.action_fields(full_name)
    aot_actions = {
        **aot["precompiled_gui_actions"], **aot["precompiled_input_event_actions"],
    }
    synthetic = validate_synthetic_menu_graph(
        build_synthetic_menu_graph(), action_fields, aot_actions)
    return {
        "title": "The Forest PS4 CUSA12398 v1.15",
        "source_hashes": {
            "level2": hashlib.sha256(level2_data).hexdigest(),
            "globalgamemanagers": hashlib.sha256(global_data).hexdigest(),
            "sharedassets2": hashlib.sha256(sharedassets2_data).hexdigest(),
            "module": hashlib.sha256(module).hexdigest(),
            "metadata": hashlib.sha256(metadata_data).hexdigest(),
        },
        "playmaker_serialized_fields": {
            "PlayMakerFSM": playmaker_fields, "FsmTemplate": template_fields,
            "Fsm": fsm_fields,
        },
        "fsm_lifecycle_audit": lifecycle,
        "cut_scene_controller_template_links": scene_template_links,
        "sharedassets2_embedded_fsm_inventory": {
            "PlayMakerFSM_components": prefab_component_count,
            "null_fsmTemplate_pointers": prefab_null_template_count,
        },
        "source_object": {
            "component_path_id": path_id, "component_size": len(blob),
            "script": "PlayMakerFSM", "enabled": mono["enabled"],
            "game_object_path_id": mono["game_id"], "game_object_name": go["name"],
            "game_object_active": go["active"],
            "fsm_used_in_template_pointer_serialized": fsm["used_in_template_pointer"],
            "fsm_used_in_template_pointer_is_null_in_component":
                fsm["used_in_template_pointer"] == {"file_id": 0, "path_id": 0},
            "owner_assignment_path_verified_in_native_code": True,
            "fsmTemplate_pointer": fsm["fsm_template_pointer"],
            "fsmTemplate_template": camera_template_link["template"],
        },
        "fsm": fsm,
        "template_comparison": {
            "component_graph_matches_embedded_template_ignoring_editor_rectangles": True,
            "state_layout_rectangles_differ": [
                {"state": component_state["name"],
                 "component": component_state["rect"], "template": template_state["rect"]}
                for component_state, template_state in zip(fsm["states"], template_fsm["states"])
                if component_state["rect"] != template_state["rect"]
            ],
            "component_fsm_used_in_template_pointer": fsm["used_in_template_pointer"],
            "template_fsm_used_in_template_pointer":
                template_fsm["used_in_template_pointer"],
        },
        "action_field_signatures": action_fields,
        "precompiled_action_audit": {
            short_name: aot_actions[short_name]
            for short_name in ("GUIBox", "GUILabel", "GUIButton", "GetButtonDown", "SendEvent")
        },
        "synthetic_menu_graph": synthetic,
        "synthetic_menu_graph_model": build_synthetic_menu_graph(),
        "limitations": [
            "the parser supports the pinned zero-action sentinel and verified multi-action ActionData subsets",
            "nonempty animationCurveParams, functionCallParams, fsmTemplateControlParams, fsmPropertyParams, layoutOptionParams, fsmVarParams and unityObjectParams are rejected",
            "ActionData encoding is limited to the decoded arrays and parameter type codes; it is not a Unity asset writer",
            "cameraFadeFSM floatVariables are decoded narrowly; 40 remaining Fsm bytes are opaque",
            "PlayMakerFSM.fsmTemplate is decoded as a trailing PPtr; it does not prove runtime loading or registration",
            "sharedassets2's 13 prefab PlayMakerFSM components are serialized inline and have null fsmTemplate pointers",
            "no scene, PKG, ELF, metadata, PRX, or console state was modified",
            "a structurally valid graph does not prove runtime creation, activation, focus, rendering, or teardown",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--level2", type=Path, required=True)
    parser.add_argument("--globalgamemanagers", type=Path, required=True)
    parser.add_argument("--sharedassets2", type=Path, required=True)
    parser.add_argument("--module", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        report = inspect(args.level2.read_bytes(), args.globalgamemanagers.read_bytes(),
                         args.sharedassets2.read_bytes(), args.module.read_bytes(),
                         args.metadata.read_bytes())
        rendered = json.dumps(_public_json(report), indent=2, sort_keys=True) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered, encoding="utf-8")
        else:
            print(rendered, end="")
        return 0
    except (OSError, ValueError, struct.error) as exc:
        print(f"playmaker-fsm-assets: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
