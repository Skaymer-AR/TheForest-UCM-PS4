#!/usr/bin/env python3
"""Read-only audit for Unity 5.6.6f2 serialized objects without type trees.

Links MonoScripts, Unity GameObjects, RewiredSpawners, prefab references and
action names/IDs. No game binaries are emitted or changed. Action IDs are
not physical DS4 button bindings, and scene references are not runtime proof.
The parser deliberately supports only a verified narrow serialized layout.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
from dataclasses import dataclass
from pathlib import Path

ACTION_NAME = re.compile(rb"[A-Za-z0-9_ &-]{3,32}\Z")
UUID_TEXT = re.compile(rb"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}")


class Cursor:
    def __init__(self, data: bytes, pos: int):
        self.data, self.pos = data, pos

    def take(self, n: int) -> bytes:
        if n < 0 or self.pos + n > len(self.data):
            raise ValueError("truncated Unity asset metadata")
        result = self.data[self.pos:self.pos + n]
        self.pos += n
        return result

    def i32(self):
        return struct.unpack("<i", self.take(4))[0]

    def u32(self):
        return struct.unpack("<I", self.take(4))[0]

    def i16(self):
        return struct.unpack("<h", self.take(2))[0]

    def i64(self):
        return struct.unpack("<q", self.take(8))[0]

    def align(self):
        self.pos = (self.pos + 3) & ~3

    def z(self):
        end = self.data.find(b"\0", self.pos)
        if end < 0:
            raise ValueError("unterminated Unity string")
        result = self.data[self.pos:end].decode("utf-8")
        self.pos = end + 1
        return result


def aligned_string(data: bytes, pos: int) -> tuple[str, int]:
    if pos + 4 > len(data):
        raise ValueError("truncated aligned Unity string")
    size = struct.unpack_from("<i", data, pos)[0]
    if size < 0 or size > 16384 or pos + 4 + size > len(data):
        raise ValueError("invalid aligned Unity string")
    return (data[pos + 4:pos + 4 + size].decode("utf-8"),
            (pos + 4 + size + 3) & ~3)


@dataclass(frozen=True)
class Item:
    offset: int
    size: int
    type_index: int
    class_id: int


class Asset:
    def __init__(self, path: Path):
        self.path = path
        self.data = path.read_bytes()
        d = self.data
        if len(d) < 64:
            raise ValueError(f"{path.name}: short asset")
        metadata_size, file_size, fmt, data_offset = struct.unpack_from(">IIII", d)
        if (fmt != 17 or file_size != len(d) or data_offset >= len(d)
                or metadata_size < 32 or metadata_size > len(d)):
            raise ValueError(f"{path.name}: unsupported Unity serialized header")
        if d[16] != 0:
            raise ValueError(f"{path.name}: only little endian supported")
        r = Cursor(d, 20)
        self.version = r.z()
        if self.version != "5.6.6f2":
            raise ValueError(f"{path.name}: unsupported Unity version {self.version!r}")
        self.platform = r.i32()
        if r.take(1) != b"\0":
            raise ValueError(f"{path.name}: type tree enabled, unsupported")
        count = r.i32()
        if count < 0 or count > 10000:
            raise ValueError("type count outside bounds")
        self.types = []
        for _ in range(count):
            class_id = r.i32()
            r.take(1)
            r.i16()
            if class_id == 114:
                r.take(16)  # script id
            r.take(16)  # old type hash
            self.types.append(class_id)
        num_objects = r.i32()
        if not 0 <= num_objects <= 1000000:
            raise ValueError("object count outside bounds")
        self.objects: dict[int, Item] = {}
        self.byclass: dict[int, list[int]] = {}
        for _ in range(num_objects):
            r.align()
            pid = r.i64()
            start = r.u32() + data_offset
            size = r.u32()
            type_index = r.i32()
            if (type_index < 0 or type_index >= count or start < data_offset
                    or start + size > len(d)):
                raise ValueError("invalid object descriptor")
            if pid in self.objects:
                raise ValueError("duplicate object ID")
            class_id = self.types[type_index]
            self.objects[pid] = Item(start, size, type_index, class_id)
            self.byclass.setdefault(class_id, []).append(pid)
        scripts_count = r.i32()
        if not 0 <= scripts_count <= 100000:
            raise ValueError("script count outside bounds")
        for _ in range(scripts_count):
            r.i32()
            r.align()
            r.i64()
        externals_count = r.i32()
        if not 0 <= externals_count <= 10000:
            raise ValueError("externals count outside bounds")
        self.externals = []
        for _ in range(externals_count):
            r.z()
            r.take(16)
            r.i32()
            self.externals.append(r.z())
        r.z()  # user information
        if r.pos > data_offset:
            raise ValueError("metadata overlaps object data")

    def obj(self, pid: int) -> bytes:
        info = self.objects[pid]
        return self.data[info.offset:info.offset + info.size]

    def ids(self, class_id: int):
        return self.byclass.get(class_id, [])

    def external(self, file_id: int) -> str | None:
        if file_id == 0:
            return self.path.name
        if not 1 <= file_id <= len(self.externals):
            return None
        return Path(self.externals[file_id - 1]).name

    def mono(self, pid: int) -> dict:
        blob = self.obj(pid)
        if len(blob) < 32 or blob[12] not in (0, 1):
            raise ValueError("invalid MonoBehaviour header")
        go_file, go_id = struct.unpack_from("<iq", blob, 0)
        script_file, script_id = struct.unpack_from("<iq", blob, 16)
        return dict(game_file=go_file, game_id=go_id, enabled=bool(blob[12]),
                    script_file=script_file, script_id=script_id)

    def gameobject(self, pid: int) -> dict:
        blob = self.obj(pid)
        if len(blob) < 12:
            raise ValueError("short GameObject")
        n = struct.unpack_from("<i", blob)[0]
        if n < 0 or n > 512 or 4 + 12 * n + 8 > len(blob):
            raise ValueError("invalid GameObject component count")
        components = [struct.unpack_from("<iq", blob, 4 + 12 * i) for i in range(n)]
        name, end = aligned_string(blob, 4 + 12 * n + 4)
        if end + 3 > len(blob) or blob[end + 2] not in (0, 1):
            raise ValueError("invalid GameObject active flag")
        return dict(name=name, active=bool(blob[end + 2]), components=components)


def monoscript(data: bytes) -> dict[str, str]:
    name, at = aligned_string(data, 0)
    if at + 20 > len(data):
        raise ValueError("truncated MonoScript")
    at += 20  # execution order + Hash128
    class_name, at = aligned_string(data, at)
    namespace, at = aligned_string(data, at)
    assembly, at = aligned_string(data, at)
    return dict(name=name, class_name=class_name,
                namespace=namespace, assembly=assembly)


def action_catalog(blob: bytes) -> dict[str, int]:
    start = blob.find(b"MenuToggle")
    if start < 8 or blob[start - 4:start] != struct.pack("<I", 10):
        raise ValueError("missing verified Rewired MenuToggle action")
    start -= 8
    if struct.unpack_from("<I", blob, start)[0] != 2:
        raise ValueError("unexpected Rewired MenuToggle ID")
    end = blob.find(b"Navigate and interact with menu", start)
    if end <= start:
        raise ValueError("Rewired category boundary missing")
    actions: dict[str, int] = {}
    for at in range(start, end - 8, 4):
        aid, size = struct.unpack_from("<II", blob, at)
        if not (2 <= aid <= 100 and 3 <= size <= 32):
            continue
        name = blob[at + 8:at + 8 + size]
        if not ACTION_NAME.fullmatch(name) or name == b"Default":
            continue
        key = name.decode("ascii")
        if key in actions and actions[key] != aid:
            raise ValueError("conflicting Rewired action IDs")
        actions[key] = aid
    if len(actions) < 10:
        raise ValueError("too few validated Rewired actions")
    return actions


def analyze(root: Path) -> dict:
    names = ("globalgamemanagers.assets", "sharedassets0.assets",
             "level0", "level1", "level2")
    files = {name: Asset(root / name) for name in names}
    script_file = files["globalgamemanagers.assets"]
    scripts = {pid: monoscript(script_file.obj(pid))
               for pid in script_file.ids(115)}
    shared = files["sharedassets0.assets"]
    prefabs = {}
    for gid in shared.ids(1):
        go = shared.gameobject(gid)
        if go["name"] not in ("Rewired Input Manager VR", "Rewired Input Manager XInput"):
            continue
        managers = []
        attached_components = []
        for file_id, pid in go["components"]:
            if (file_id != 0 or pid not in shared.objects
                    or shared.objects[pid].class_id != 114):
                continue
            mb = shared.mono(pid)
            if shared.external(mb["script_file"]) != "globalgamemanagers.assets":
                continue
            sc = scripts.get(mb["script_id"])
            if sc:
                attached_components.append(dict(
                    object_id=pid,
                    script=sc["namespace"] + "." + sc["class_name"] if sc["namespace"] else sc["class_name"],
                    enabled=mb["enabled"]))
            if sc and sc["class_name"] == "InputManager" and sc["namespace"] == "Rewired":
                managers.append(dict(component_id=pid, enabled=mb["enabled"],
                                     actions=action_catalog(shared.obj(pid))))
        if len(managers) != 1:
            raise ValueError("InputManager prefab has ambiguous components")
        prefabs[gid] = dict(name=go["name"], active=go["active"],
                            components=attached_components, **managers[0])
    if len(prefabs) != 2:
        raise ValueError("expected two Rewired input prefabs")

    spawners = []
    for scene_name in ("level0", "level1", "level2"):
        scene = files[scene_name]
        found = []
        for mb_id in scene.ids(114):
            mb = scene.mono(mb_id)
            if scene.external(mb["script_file"]) != "globalgamemanagers.assets":
                continue
            sc = scripts.get(mb["script_id"])
            if (sc is None or sc["class_name"] != "RewiredSpawner"
                    or sc["namespace"] != "TheForest.Utils"):
                continue
            if mb["game_file"] != 0:
                raise ValueError("external spawner GameObject")
            go = scene.gameobject(mb["game_id"])
            blob = scene.obj(mb_id)
            if len(blob) < 56:
                raise ValueError("short RewiredSpawner")
            links = []
            for at in (32, 44):
                file_id, pid = struct.unpack_from("<iq", blob, at)
                external = scene.external(file_id)
                if external != "sharedassets0.assets" or pid not in prefabs:
                    raise ValueError("RewiredSpawner prefab reference mismatch")
                links.append(dict(file=external, path_id=pid, name=prefabs[pid]["name"]))
            found.append(dict(scene=scene_name, gameobject_id=mb["game_id"],
                              component_id=mb_id, name=go["name"],
                              gameobject_active=go["active"],
                              component_enabled=mb["enabled"], prefabs=links))
        if len(found) != 1:
            raise ValueError(f"expected one RewiredSpawner in {scene_name}")
        spawners.extend(found)

    hardware = []
    for pid in shared.ids(114):
        mb = shared.mono(pid)
        if shared.external(mb["script_file"]) != "globalgamemanagers.assets":
            continue
        sc = scripts.get(mb["script_id"])
        if (sc and sc["class_name"] == "HardwareJoystickMap"
                and sc["namespace"] == "Rewired.Data.Mapping"
                and b"SonyDualShock4" in shared.obj(pid)):
            identifiers = sorted({value.decode("ascii").lower()
                                  for value in UUID_TEXT.findall(shared.obj(pid))})
            hardware.append(dict(object_id=pid, profile="SonyDualShock4",
                                 kind="generic-hardware-joystick-map",
                                 identifiers=identifiers))
    hardware_ids = set()
    for hw in hardware:
        hardware_ids.update(hw["identifiers"])
    for pid, prefab in prefabs.items():
        manager_ids = {value.decode("ascii").lower()
                       for value in UUID_TEXT.findall(shared.obj(prefab["component_id"]))}
        prefab["matching_hardware_identifiers"] = sorted(hardware_ids & manager_ids)
    action_maps = [prefab["actions"] for prefab in prefabs.values()]
    shared_pairs = len(set(action_maps[0].items()) & set(action_maps[1].items()))
    variations = {
        name: {str(pid): prefab["actions"].get(name) for pid, prefab in prefabs.items()}
        for name in sorted(set(action_maps[0]) | set(action_maps[1]))
        if len({prefab["actions"].get(name) for prefab in prefabs.values()}) > 1
    }
    return dict(
        unity_version=shared.version,
        sources=[dict(file=name, sha256=hashlib.sha256(files[name].data).hexdigest(),
                      objects=len(files[name].objects)) for name in names],
        monoscripts_in_library=len(scripts),
        spawners=spawners,
        input_manager_prefabs={str(pid): prefab for pid, prefab in prefabs.items()},
        shared_action_name_id_pairs=shared_pairs,
        varying_action_name_ids=variations,
        generic_hardware_profiles=hardware,
        limitations=[
            "static Unity object links; active instantiated prefab not proven",
            "action ID is not a physical DualShock 4 button assignment",
            "not a Unity AOT registration, runtime hook, or installable PS4 mod",
        ],
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        output = json.dumps(analyze(args.assets_root), indent=2, ensure_ascii=False) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(output, encoding="utf-8")
        else:
            print(output, end="")
        return 0
    except (OSError, ValueError, UnicodeError, struct.error, KeyError) as exc:
        parser.exit(2, f"unity-rewired: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
