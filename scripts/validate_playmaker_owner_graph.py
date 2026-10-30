#!/usr/bin/env python3
"""Read-only PlayMaker OnGUI ownership audit for the exact The Forest PS4 build.

No IL2CPP invocation, game-memory patch or managed action construction.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import struct
from pathlib import Path

from analyze_ps4_il2cpp_pipeline import parse_metadata_v23
from inspect_aot_registration import NativeImage

ELF_SHA = '0159ff61c99d25c8f0a821070e3d8b24aff58dbbe5429b8f29561f9960d02969'
META_SHA = '238c400de31e28ed4f7f14e7781ea3b33de0d0bd6964ded680d78fce1d85a6c3'
METADATA_REGISTRATION = 0x032C4C98
METHOD_POINTERS = 0x0316F8C0
FIELDS = {
    'HutongGames.PlayMaker.Fsm': {'activeStateName': 0xD0, 'activeState': 0xD8, 'handleOnGUI': 0xFF},
    'HutongGames.PlayMaker.FsmState': {'actions': 0x60, 'actionData': 0x68, 'activeActions': 0x70},
    'PlayMakerGUI': {'fsmList': 0, 'SortedFsmList': 0x18, 'instance': 0x30},
    'PlayMakerFSM': {'fsmList': 0, 'fsm': 0x18},
}
METHODS = {
    ('PlayMakerGUI', 'OnGUI'): 0x0113FAF0,
    ('PlayMakerGUI', 'CallOnGUI'): 0x01141320,
    ('PlayMakerGUI', 'OnDisable'): 0x01141550,
    ('HutongGames.PlayMaker.FsmState', 'get_Actions'): 0x01118D30,
    ('HutongGames.PlayMaker.FsmState', 'set_Actions'): 0x011305B0,
    ('HutongGames.PlayMaker.FsmState', 'LoadActions'): 0x01122C00,
    ('HutongGames.PlayMaker.FsmState', 'ActivateActions'): 0x01118A30,
    ('HutongGames.PlayMaker.FsmState', 'OnGUI'): 0x011276C0,
    ('HutongGames.PlayMaker.FsmStateAction', 'get_Enabled'): 0x01113490,
    ('HutongGames.PlayMaker.FsmStateAction', 'get_Active'): 0x01127490,
    ('HutongGames.PlayMaker.ActionData', 'LoadActions'): 0x010F2A20,
    ('HutongGames.PlayMaker.ActionData', 'CreateAction'): 0x010F2D80,
    ('PlayMakerFSM', 'OnDestroy'): 0x0113B200,
}
# Exact short native instructions: analysis markers, NOT detour recipes.
SITES = {
    'active_state_read': (0x1141351, '488bbbd8000000'),
    'get_actions_call': (0x114135d, 'e8ce79fdff'),
    'action_active_check': (0x114138e, '807f1a00'),
    'on_gui_virtual_dispatch': (0x114139e, 'ff9020030000'),
    'active_state_name_read': (0x11413bf, '4c8bb3d0000000'),
    'active_state_lookup': (0x11414ff, 'e85c35fdff'),
    'active_state_cache_write': (0x1141507, '4889bbd8000000'),
    'actions_array_read': (0x1118dbe, '488b4360'),
    'serialized_action_data_read': (0x1122c09, '488b7b68'),
    'actions_array_write': (0x1122c1a, '48894360'),
    'action_enabled_filter': (0x1118aa0, '807b1800'),
    'action_enabled_property_read': (0x1113490, '8a4718c3'),
    'action_active_property_read': (0x1127490, '8a471ac3'),
    'action_active_set_by_activation': (0x1118b7d, '66c7431a0100'),
    'action_init_virtual_slot_26': (0x1118b8d, 'ff90b0020000'),
    'action_onenter_virtual_slot_30': (0x1118ba4, 'ff90f0020000'),
    'set_actions_raw_pointer': (0x11305b0, '48897760c3'),
    'singleton_clear': (0x1141637, '48c7403000000000'),
    'fsm_removal_dispatch': (0x113b296, 'ff12'),
}


def verify_sites(read_va, sites=SITES):
    result = {}
    for label, (va, hexbytes) in sites.items():
        pattern = bytes.fromhex(hexbytes)
        if read_va(va, len(pattern)) != pattern:
            raise ValueError('native instruction mismatch: ' + label)
        result[label] = hex(va)
    return result


def inspect(elf: bytes, metadata: bytes) -> dict:
    if hashlib.sha256(elf).hexdigest() != ELF_SHA:
        raise ValueError('unexpected IL2CPP ELF identity')
    if hashlib.sha256(metadata).hexdigest() != META_SHA:
        raise ValueError('unexpected metadata identity')
    image = NativeImage(elf)
    meta = parse_metadata_v23(metadata)
    fields_count, fields_ptr = struct.unpack(
        '<QQ', image.read(METADATA_REGISTRATION + 16 * 5, 16))
    if fields_count != len(meta.types):
        raise ValueError('field-offset table count does not match TypeDefinitions')
    field_table = {}
    for owner, needed in FIELDS.items():
        candidates = [typ for typ in meta.types if typ.full_name == owner]
        if len(candidates) != 1:
            raise ValueError('missing/ambiguous PlayMaker owner: ' + owner)
        typ = candidates[0]
        offsets_ptr = struct.unpack('<Q', image.read(fields_ptr + typ.index * 8, 8))[0]
        decoded = {}
        for field in meta.owned_fields(typ):
            if field.name in needed:
                ordinal = field.index - typ.field_start
                decoded[field.name] = struct.unpack(
                    '<i', image.read(offsets_ptr + 4 * ordinal, 4))[0]
        if decoded != needed:
            raise ValueError('PlayMaker field offsets differ: ' + owner)
        field_table[owner] = {
            'type_definition': typ.index, 'offsets': decoded,
        }
    method_table = {}
    for (owner, method), expected_va in METHODS.items():
        typ = next(t for t in meta.types if t.full_name == owner)
        definitions = [m for m in meta.methods_named(typ, method)
                       if m.method_index >= 0]
        if len(definitions) != 1:
            raise ValueError('missing/ambiguous native method: ' + owner + '.' + method)
        definition = definitions[0]
        va = struct.unpack('<Q', image.read(
            METHOD_POINTERS + definition.method_index * 8, 8))[0]
        if va != expected_va or not image.executable(va):
            raise ValueError('native method address differs: ' + owner + '.' + method)
        method_table[owner + '.' + method] = {
            'method_index': definition.method_index, 'link_va': hex(va),
        }
    sites = verify_sites(image.read)
    return {
        'title': 'The Forest CUSA12398 1.15',
        'module_sha256': ELF_SHA,
        'metadata_sha256': META_SHA,
        'managed_field_offsets': field_table,
        'native_methods': method_table,
        'verified_native_instruction_sites': sites,
        'interpretation': [
            'CallOnGUI reads Fsm.activeState and resolves by Fsm.activeStateName if absent.',
            'FsmState.get_Actions lazily materializes FsmState.actions from serialized actionData.',
            'CallOnGUI dispatches virtual OnGUI only for existing FsmStateAction objects whose active byte at +0x1A is nonzero.',
            'FsmState.ActivateActions checks enabled at +0x18, adds enabled actions to activeActions, invokes virtual Init at slot 26 and OnEnter at slot 30, and sets active at +0x1A.',
            'FsmState.set_Actions is a raw pointer assignment to the actions field; it does not initialize or attach the supplied action array.',
            'OnDisable can clear PlayMakerGUI singleton; PlayMakerFSM.OnDestroy uses a list-removal call.',
            'Changing an actions array or class vtable is not a registered external extension mechanism.',
            'No runnable safe PRX callback or unload protocol was demonstrated.',
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--module', type=Path, required=True)
    parser.add_argument('--metadata', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    opts = parser.parse_args()
    try:
        result = json.dumps(
            inspect(opts.module.read_bytes(), opts.metadata.read_bytes()), indent=2) + '\n'
        if opts.output:
            opts.output.parent.mkdir(parents=True, exist_ok=True)
            opts.output.write_text(result)
        else:
            print(result, end='')
        return 0
    except (OSError, ValueError, struct.error) as exc:
        parser.exit(2, 'playmaker-owner-audit: %s\n' % exc)


if __name__ == '__main__':
    raise SystemExit(main())
